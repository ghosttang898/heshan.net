import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

SCRIPT = Path(__file__).with_name("staging.py")
spec = importlib.util.spec_from_file_location("staging", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_values():
    revision = "a" * 40
    return {"STAGING_BACKEND_REVISION": revision, "STAGING_BACKEND_IMAGE": "heshan-backend:" + revision,
            "STAGING_FRONTEND_REVISION": revision, "STAGING_STATIC_DIR": "/srv/heshan-staging/releases/" + revision + "/frontend",
            "STAGING_TLS_DIR": "/etc/heshan-staging/tls", "STAGING_DB_NAME": "heshan_staging",
            "STAGING_DB_USER": "heshan_staging_app", "STAGING_DB_PASSWORD": secrets.token_hex(48),
            "STAGING_DB_ADMIN_PASSWORD": secrets.token_hex(48), "STAGING_JWT_SECRET": secrets.token_hex(48),
            "STAGING_CORS_ALLOWED_ORIGINS": "https://localhost:18443"}


class StagingSafety(unittest.TestCase):
    def test_explicit_overlay_preserved_and_private_file_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "overlay.yml"
            path.write_text("services: {}\n")
            path.chmod(0o600)
            docker = module.Docker(fixture_values(), "/tmp/fixture.env", str(path))
            self.assertEqual(docker.base[-2:], ["-f", str(path)])
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "0600"):
                module.Docker(fixture_values(), "/tmp/fixture.env", str(path))
            with self.assertRaisesRegex(ValueError, "absolute"):
                module.Docker(fixture_values(), "/tmp/fixture.env", "relative.yml")

    def test_installed_overlay_cannot_be_silently_omitted(self):
        with patch.object(Path, "exists", return_value=True):
            with self.assertRaisesRegex(ValueError, "must be preserved"):
                module.Docker(fixture_values(), "/tmp/fixture.env")

    def test_container_access_rejects_private_directory_before_start(self):
        path = MagicMock()
        for uid, gid, mode, required, allowed in (
                (0, 101, 0o40700, 1, False),
                (0, 101, 0o40750, 1, True),
                (0, 0, 0o40700, 5, False),
                (0, 0, 0o40755, 5, True),
                (0, 101, 0o100640, 4, True),
                (0, 0, 0o100600, 4, False)):
            with self.subTest(uid=uid, gid=gid, mode=oct(mode)):
                path.stat.return_value = MagicMock(st_uid=uid, st_gid=gid, st_mode=mode)
                if allowed:
                    module.check_web_access(path, required)
                else:
                    with self.assertRaisesRegex(ValueError, "cannot access"):
                        module.check_web_access(path, required)

    def model(self, values):
        environment = dict(os.environ, **values)
        result = subprocess.run(["docker", "compose", "--env-file", "/dev/null", "-f", str(module.COMPOSE),
                                 "config", "--format", "json"], env=environment, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_compose_isolation_security_resources_and_mounts(self):
        values = fixture_values()
        model = self.model(values)
        module.validate_model(model, values)
        self.assertEqual(sum(int(service["mem_limit"]) for service in model["services"].values()), 1216 * 1024 ** 2)
        for name, service in model["services"].items():
            self.assertEqual(service["restart"], "unless-stopped")
            self.assertIn("healthcheck", service)
            self.assertEqual(service["logging"]["options"], {"max-size": "10m", "max-file": "3"})
            for volume in service.get("volumes", []):
                self.assertTrue(volume["target"].startswith("/"))
                if volume["type"] == "bind":
                    self.assertTrue(volume["read_only"])
                    self.assertFalse(volume["bind"].get("create_host_path", False))
            if name != "db":
                self.assertTrue(service["read_only"])
                self.assertIn("ALL", service["cap_drop"])
                self.assertIn("no-new-privileges:true", service["security_opt"])
        self.assertEqual(model["services"]["backend"]["tmpfs"], ["/tmp:size=64m,mode=1777"])
        self.assertEqual(model["services"]["web"]["user"], "101:101")
        self.assertEqual(set(model["services"]["web"]["networks"]), {"application", "ingress"})
        self.assertFalse(model["networks"]["ingress"].get("internal", False))
        self.assertEqual(model["services"]["backend"]["environment"]["APP_GEOLOCATION_TRUSTED_PROXIES"], "172.30.20.10/32")

    def test_rejects_public_ports_and_production_volume(self):
        values = fixture_values()
        for mutation in (lambda model: model["services"]["web"]["ports"][0].update(host_ip="0.0.0.0"),
                         lambda model: model["services"]["backend"]["networks"].update(ingress={}),
                         lambda model: model["services"]["db"]["networks"].update(ingress={}),
                         lambda model: model["networks"]["application"].update(internal=False),
                         lambda model: model["networks"]["ingress"].update(internal=True),
                         lambda model: model["volumes"]["staging_data"].update(name="heshan_postgres_data")):
            model = self.model(values)
            mutation(model)
            with self.assertRaises(ValueError):
                module.validate_model(model, values)

    def test_env_rejects_defaults_reused_secrets_and_production(self):
        cases = (("STAGING_DB_NAME", "heshan"), ("STAGING_BACKEND_IMAGE", "heshan-backend:latest"),
                 ("STAGING_CORS_ALLOWED_ORIGINS", "https://heshan.net"), ("STAGING_CORS_ALLOWED_ORIGINS", "*"),
                 ("STAGING_CORS_ALLOWED_ORIGINS", "https://*.example.net"),
                 ("STAGING_JWT_SECRET", "replace-me"), ("STAGING_FRONTEND_REVISION", "b" * 40))
        for key, value in cases:
            with self.subTest(key=key, value=value):
                values = fixture_values(); values[key] = value
                with self.assertRaises(ValueError):
                    module.validate_env(values)
        values = fixture_values(); values["STAGING_JWT_SECRET"] = values["STAGING_DB_PASSWORD"]
        with self.assertRaises(ValueError):
            module.validate_env(values)

    def test_env_exclusive_creation_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "staging.env"
            args = MagicMock(env_file=str(path), revision="a" * 40, static_dir=fixture_values()["STAGING_STATIC_DIR"], tls_dir="/etc/heshan-staging/tls")
            module.init_env(args)
            values = module.read_env(path)
            self.assertEqual(values["STAGING_DB_NAME"], "heshan_staging")
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                module.init_env(args)
            self.assertEqual(path.read_bytes(), before)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                module.read_env(path)

    def test_env_rejects_unknown_keys_duplicates_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "staging.env"
            values = fixture_values()
            base = "\n".join(key + "=" + value for key, value in values.items()) + "\n"
            for extra in ("DB_URL=jdbc:postgresql://production/db\n", "STAGING_DB_NAME=heshan_staging\n"):
                path.write_text(base + extra); path.chmod(0o600)
                with self.assertRaises(ValueError):
                    module.read_env(path)
            link = Path(directory) / "link.env"; link.symlink_to(path)
            with self.assertRaises(ValueError):
                module.read_env(link)

    def test_secrets_redacted_and_environment_not_inherited(self):
        values = fixture_values()
        with patch.dict(os.environ, {"STAGING_DB_NAME": "production", "DOCKER_HOST": "unix:///var/run/docker.sock"}):
            docker = module.Docker(values, "/tmp/private.env")
        self.assertEqual(docker.environment["STAGING_DB_NAME"], "heshan_staging")
        for key in module.SECRET_KEYS:
            self.assertNotIn(values[key], module.redact(values[key], values))
        self.assertNotIn("eyJabc.def.ghi", module.redact("eyJabc.def.ghi", values))

    def test_remote_docker_and_implicit_mutations_rejected(self):
        with patch.dict(os.environ, {"DOCKER_HOST": "ssh://production"}):
            with self.assertRaises(ValueError):
                module.Docker(fixture_values(), "/tmp/fixture.env")
        for action in ("deploy", "stop", "backup", "init-env"):
            with patch("sys.argv", [str(SCRIPT), action, "--env-file", "/tmp/fixture.env"]), patch.object(module, "read_env") as read:
                with self.assertRaises(SystemExit):
                    module.main()
                read.assert_not_called()

    def test_resource_shortage_exits_without_stop_or_start(self):
        values = fixture_values(); model = self.model(values)
        docker = MagicMock(); docker.compose.return_value = json.dumps(model).encode()
        with patch.object(module, "check_artifacts"), patch.object(Path, "read_text", return_value="MemAvailable: 100000 kB\n"):
            with self.assertRaisesRegex(ValueError, "1300"):
                module.preflight(docker, values)
        self.assertFalse(any(call.args[0] in ("stop", "up") for call in docker.compose.call_args_list))

    def test_disk_network_port_image_and_foreign_volume_guards(self):
        values = fixture_values(); model = self.model(values)
        for failure in ("disk", "network", "port", "image", "volume"):
            docker = MagicMock(); docker.compose.return_value = json.dumps(model).encode()
            def reply(args, **kwargs):
                if args[1:3] == ["network", "ls"]: return b"fixture-network\n"
                if args[1:3] == ["network", "inspect"]:
                    return json.dumps([{"Labels": {}, "IPAM": {"Config": [{"Subnet": "172.30.20.0/24" if failure == "network" else "172.31.0.0/24"}]}}]).encode()
                if args[1:3] == ["image", "inspect"]:
                    if "{{.Os}}/{{.Architecture}}" in args: return b"linux/arm64" if failure == "image" else b"linux/amd64"
                    if "{{.Config.User}}" in args: return b"10001:10001"
                    return values["STAGING_BACKEND_REVISION"].encode()
                if args[1:3] == ["volume", "ls"]: return b"heshan-staging_staging_data\n" if failure == "volume" else b""
                if args[1:3] == ["volume", "inspect"]: return b'{"com.docker.compose.project":"production"}'
                return b"/tmp\n" if "{{.DockerRootDir}}" in args else b""
            docker.run.side_effect = reply
            space = MagicMock(f_bavail=1 if failure == "disk" else 10 * 1024 ** 3, f_frsize=1)
            probe = MagicMock()
            if failure == "port": probe.__enter__.return_value.bind.side_effect = OSError("port occupied")
            with self.subTest(failure=failure), patch.object(module, "check_artifacts"), \
                    patch.object(Path, "read_text", return_value="MemAvailable: 1600000 kB\n"), \
                    patch.object(module.os, "statvfs", return_value=space), patch.object(module.socket, "socket", return_value=probe):
                with self.assertRaises((ValueError, OSError)):
                    module.preflight(docker, values)
            self.assertFalse(any(call.args[0] in ("up", "stop") for call in docker.compose.call_args_list))

    def test_backup_uses_stream_and_has_no_cleanup_or_founder_actions(self):
        source = SCRIPT.read_text()
        self.assertIn("output=output", source)
        self.assertNotIn("prune", source.replace("nothing was pruned", ""))
        for forbidden in ("volume rm", "system prune", "--initialize-founder", 'compose("down"', "ssh ", "sudo -S"):
            self.assertNotIn(forbidden, source)

    def test_backup_success_streams_and_failure_retains_partial_and_old_backup(self):
        for failure in (False, True):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                path = Path(directory); env = path / "staging.env"; values = fixture_values()
                env.write_text("\n".join(key + "=" + value for key, value in values.items())); env.chmod(0o600)
                backups = path / "heshan-staging"; backups.mkdir(mode=0o700)
                existing = backups / "old.dump"; existing.write_bytes(b"old-backup")
                docker = MagicMock()
                model = self.model(values)
                def compose(*args, **kwargs):
                    if args[0] == "config": return json.dumps(model).encode()
                    kwargs["output"].write(b"fixture-dump")
                    if failure: raise RuntimeError("Synthetic dump failure")
                    return None
                docker.compose.side_effect = compose
                argv = [str(SCRIPT), "backup", "--env-file", str(env), "--backup-dir", str(backups), "--execute"]
                with patch("sys.argv", argv), patch.object(module, "Docker", return_value=docker):
                    if failure:
                        with self.assertRaises(RuntimeError): module.main()
                    else: module.main()
                self.assertEqual(existing.read_bytes(), b"old-backup")
                self.assertEqual(bool(list(backups.glob("*.partial"))), failure)
                self.assertEqual(len(list(backups.glob("*.sha256"))), 0 if failure else 1)
                self.assertFalse(any(call.args[0] in ("up", "stop", "down") for call in docker.compose.call_args_list))

    def test_docker_failure_does_not_expose_credentials(self):
        values = fixture_values()
        docker = module.Docker(values, "/tmp/fixture.env")
        reply = subprocess.CompletedProcess([], 1, b"", values["STAGING_DB_PASSWORD"].encode())
        with patch.object(module.subprocess, "run", return_value=reply), self.assertRaises(RuntimeError) as error:
            docker.run(["docker", "fixture"])
        self.assertNotIn(values["STAGING_DB_PASSWORD"], str(error.exception))

    def test_http_smoke_rejects_production_and_redirects(self):
        spec = importlib.util.spec_from_file_location("http_smoke", SCRIPT.with_name("staging-http-smoke.py"))
        smoke = importlib.util.module_from_spec(spec); spec.loader.exec_module(smoke)
        for origin in ("https://heshan.net", "https://api.heshan.net", "http://localhost:18443", "https://localhost:18443?secret=x"):
            with self.assertRaises(ValueError):
                smoke.validate_origin(origin)
        self.assertEqual(smoke.validate_origin("https://localhost:18443"), "https://localhost:18443")
        self.assertIsNone(smoke.NoRedirects().redirect_request(None, None, 302, "", {}, "https://heshan.net"))


if __name__ == "__main__":
    unittest.main()
