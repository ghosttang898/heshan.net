import importlib.util
import io
import hashlib
from pathlib import Path
import subprocess
import tarfile
import tempfile
import json
import os
import shutil
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("test-vps-postgresql.py")
spec = importlib.util.spec_from_file_location("vps_test", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class IsolatedTestSafety(unittest.TestCase):
    def test_configurable_founder_and_revision_are_forwarded(self):
        revision = "a" * 40
        with patch.object(module, "execute") as execute, patch("sys.argv", [str(SCRIPT),
                "--execute-isolated-tests", "--image", "fixture:" + revision,
                "--founder-username", "ghost", "--expected-revision", revision]):
            module.main()
            execute.assert_called_once_with("fixture:" + revision, None, "ghost", revision)

    def test_unsafe_founder_and_invalid_revision_rejected_before_docker(self):
        for options in (("--founder-username", "ghost'; DROP TABLE users;--"),
                        ("--expected-revision", "latest")):
            with self.subTest(options=options), patch.object(module, "execute") as execute, \
                    patch("sys.argv", [str(SCRIPT), "--execute-isolated-tests", "--image", "fixture:local", *options]):
                with self.assertRaises(SystemExit):
                    module.main()
                execute.assert_not_called()

    def test_revision_mismatch_aborts_before_compose_start(self):
        calls = []
        def fake(args, data=None, ok=True):
            calls.append(args)
            output = b"linux/amd64\n" if "{{.Os}}/{{.Architecture}}" in args else b"wrong-revision\n"
            return subprocess.CompletedProcess(args, 0, output, b"")
        with tempfile.TemporaryDirectory() as directory, patch.object(module, "run", side_effect=fake), \
                patch.object(module, "local_docker_environment", return_value=None):
            with self.assertRaises(module.CommandFailure):
                module.execute("fixture:local", directory, "ghost", "a" * 40)
            report = json.loads((Path(directory) / "result.json").read_text())
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(report["containers_stopped"])
            self.assertFalse(any("up" in args for args in calls))

    def test_release_image_archive_validation(self):
        script = SCRIPT.with_name("run-vps-release-test.sh").read_text()
        code = script.split('archive_ids=$(python3 - "$image" "$revision" <<\'PY\'\n', 1)[1].split("\nPY\n", 1)[0]
        revision = "a" * 40
        for platform, tags, label, success in (("amd64", ["fixture:" + revision], revision, True),
                ("arm64", ["fixture:" + revision], revision, False),
                ("amd64", ["fixture:pg-test"], revision, False),
                ("amd64", ["fixture:" + revision], "b" * 40, False)):
            with self.subTest(platform=platform, tags=tags, label=label), tempfile.TemporaryDirectory() as directory:
                config = json.dumps({"os": "linux", "architecture": platform,
                    "config": {"Labels": {"org.opencontainers.image.revision": label}}}).encode()
                manifest = json.dumps([{"RepoTags": tags, "Config": "config.json"}]).encode()
                with tarfile.open(Path(directory) / "backend-image.tar", "w") as archive:
                    for name, value in (("manifest.json", manifest), ("config.json", config)):
                        info = tarfile.TarInfo(name); info.size = len(value)
                        archive.addfile(info, io.BytesIO(value))
                result = subprocess.run(["python3", "-c", code, "fixture:" + revision, revision],
                                        cwd=directory, capture_output=True)
                self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_release_wrapper_preserves_resources_and_requires_interactive_sudo(self):
        wrapper = SCRIPT.with_name("run-vps-release-test.sh")
        self.assertEqual(subprocess.run(["bash", "-n", str(wrapper)], capture_output=True).returncode, 0)
        source = wrapper.read_text()
        self.assertIn('Running containers detected; aborting', source)
        self.assertIn('refusing to overwrite', source)
        self.assertIn('"$image" "$founder_username" "$revision"', source)
        for forbidden in ("sudo -S", "sudoers", "ufw", "usermod", "volume rm", "prune", "down -v"):
            self.assertNotIn(forbidden, source)

    def test_engine29_oci_archive_ids_and_descriptor_integrity(self):
        source = SCRIPT.with_name("run-vps-release-test.sh").read_text()
        code = source.split('archive_ids=$(python3 - "$image" "$revision" <<\'PY\'\n', 1)[1].split("\nPY\n", 1)[0]
        revision = "a" * 40
        image = "fixture:" + revision
        config = json.dumps({"os": "linux", "architecture": "amd64",
            "config": {"Labels": {"org.opencontainers.image.revision": revision}}}).encode()
        config_id = hashlib.sha256(config).hexdigest()
        model = json.dumps({"config": {"digest": "sha256:" + config_id}}).encode()
        model_id = hashlib.sha256(model).hexdigest()
        index = json.dumps({"manifests": [{"digest": "sha256:" + model_id}]}).encode()
        index_id = hashlib.sha256(index).hexdigest()
        for corrupt, success in ((False, True), (True, False)):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as directory:
                files = {"manifest.json": json.dumps([{"RepoTags": [image], "Config": "config.json"}]).encode(),
                         "config.json": config, "blobs/sha256/" + config_id: config,
                         "blobs/sha256/" + model_id: b"corrupt" if corrupt else model,
                         "blobs/sha256/" + index_id: index,
                         "index.json": json.dumps({"manifests": [{"digest": "sha256:" + index_id,
                             "annotations": {"io.containerd.image.name": "docker.io/library/" + image}}]}).encode()}
                with tarfile.open(Path(directory) / "backend-image.tar", "w") as archive:
                    for name, value in files.items():
                        info = tarfile.TarInfo(name); info.size = len(value)
                        archive.addfile(info, io.BytesIO(value))
                result = subprocess.run(["python3", "-c", code, image, revision], cwd=directory, capture_output=True)
                self.assertEqual(result.returncode == 0, success, result.stderr)
                if success:
                    self.assertEqual(set(result.stdout.decode().split()), {"sha256:" + item for item in (config_id, model_id, index_id)})

    def normalized_compose(self, *files):
        environment = dict(os.environ, TEST_BACKEND_IMAGE="fixture:local", TEST_ADMIN_PASSWORD="fixture",
                           TEST_APP_PASSWORD="fixture", TEST_JWT_SECRET="fixture", BACKEND_IMAGE="fixture:local",
                           POSTGRES_DB="fixture", POSTGRES_USER="fixture", POSTGRES_PASSWORD="fixture",
                           POSTGRES_ADMIN_PASSWORD="fixture", APP_JWT_SECRET="fixture",
                           APP_CORS_ALLOWED_ORIGINS="https://fixture.invalid",
                           GEOIP_DATABASE_FILE="/tmp/fixture-not-a-real-database.mmdb")
        args = ["docker", "compose", "--env-file", "/dev/null"]
        for file in files:
            args.extend(["-f", str(file)])
        result = subprocess.run(args + ["config", "--format", "json"], env=environment, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return json.loads(result.stdout)

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI required; no daemon needed")
    def test_normalized_mounts_and_security_in_all_compose_configs(self):
        root = SCRIPT.parents[2]
        cases = [(module.COMPOSE,), (root / "deploy/compose.yml",),
                 (root / "deploy/compose.yml", root / "deploy/compose.geoip.yml")]
        for files in cases:
            with self.subTest(files=files):
                model = self.normalized_compose(*files)
                module.validate_compose_mounts(model)
                backend = model["services"]["backend"]
                self.assertEqual(backend["tmpfs"], ["/tmp:size=64m,mode=1777"])
                self.assertTrue(backend["read_only"])
                self.assertIn("ALL", backend["cap_drop"])
                self.assertIn("no-new-privileges:true", backend["security_opt"])
                self.assertEqual(int(backend["mem_limit"]), 768 * 1024 * 1024)
                self.assertFalse(backend.get("ports"))
                self.assertFalse(model["services"]["db"].get("ports"))
                for service in model["services"].values():
                    for mount in service.get("volumes", []):
                        if mount["type"] == "bind":
                            self.assertTrue(mount.get("read_only"))

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI required; no daemon needed")
    def test_original_unquoted_comma_reproduces_and_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            compose = Path(directory) / "broken.yml"
            compose.write_text("services:\n  backend:\n    image: fixture:local\n    tmpfs: [/tmp:size=64m,mode=1777]\n")
            model = self.normalized_compose(compose)
            self.assertEqual(model["services"]["backend"]["tmpfs"], ["/tmp:size=64m", "mode=1777"])
            with self.assertRaisesRegex(module.CommandFailure, "Invalid tmpfs target"):
                module.validate_compose_mounts(model)

    def test_mount_validation_rejects_relative_volume_target(self):
        model = {"services": {"backend": {"tmpfs": ["/tmp:size=64m,mode=1777"],
                  "volumes": [{"type": "bind", "target": "relative/path"}]}}}
        with self.assertRaisesRegex(module.CommandFailure, "Volume target must be absolute"):
            module.validate_compose_mounts(model)

    def test_preflight_failure_already_has_report_and_absolute_log(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(module, "local_docker_environment",
                side_effect=module.CommandFailure("Docker unavailable", 7)):
            with self.assertRaises(module.CommandFailure):
                module.execute("fixture:local", directory)
            report = json.loads((Path(directory) / "result.json").read_text())
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["checks"][0]["exit_code"], 7)
            self.assertEqual(report["checks"][0]["status"], "FAIL")
            self.assertTrue(report["containers_stopped"])
            self.assertEqual(report["log_directory"], str(Path(directory).resolve()))
            self.assertIn("Docker unavailable", (Path(directory) / "execution.log").read_text())

    def test_backend_health_failure_preserves_commands_container_logs_and_report(self):
        calls = []

        def fake(args, data=None, ok=True):
            calls.append(args)
            stdout, stderr, code = b"", b"", 0
            if args[:3] == ["docker", "image", "inspect"]:
                stdout = b"linux/amd64\n"
            elif "{{json .HostConfig.PortBindings}}" in args:
                stdout = b"{}\n"
            elif data and b"server_version_num" in data:
                stdout = b"160013\n"
            elif "config" in args and "json" in args:
                stdout = b'{"services":{"backend":{"tmpfs":["/tmp:size=64m,mode=1777"]}}}'
            elif "up" in args and args[-1] == "backend":
                code, stderr = 1, b"backend unhealthy: Hibernate SchemaManagementException\n"
            elif data and b"information_schema.tables" in data:
                stdout = b"0\n"
            elif "logs" in args:
                stdout = b"PostgreSQL database system is ready; backend startup failed\n"
            elif args[:2] == ["docker", "inspect"]:
                stdout = b'{"OOMKilled":false,"ExitCode":1}\n'
            elif "ps" in args and "-a" in args and "-q" in args:
                stdout = b"fixture-container\n"
            return subprocess.CompletedProcess(args, code, stdout, stderr)

        with tempfile.TemporaryDirectory() as directory, patch.object(module, "run", side_effect=fake), \
                patch.object(module, "local_docker_environment", return_value=None):
            with self.assertRaises(module.CommandFailure):
                module.execute("fixture:local", directory)
            path = Path(directory)
            report = json.loads((path / "result.json").read_text())
            failures = [item for item in report["checks"] if item["status"] == "FAIL"]
            self.assertTrue(failures)
            self.assertEqual(failures[0]["exit_code"], 1)
            self.assertIn("SchemaManagementException", failures[0]["reason"])
            self.assertIn("SchemaManagementException", (path / "execution.log").read_text())
            self.assertIn("database system is ready", (path / "before-stop-container-logs.log").read_text())
            self.assertTrue((path / "after-stop-fixture-container-container.log").exists())
            self.assertTrue((path / "before-stop-fixture-container-state.json").exists())
            self.assertTrue((path / "test.env").exists())
            self.assertTrue(report["containers_stopped"])
            self.assertFalse(any("--rm" in args or "down" in args for args in calls))

    def test_timeout_partial_output_and_secrets_are_handled(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = module.Journal(Path(directory), "fixture")
            journal.secrets.append("private-password")
            error = subprocess.TimeoutExpired(["fixture"], 10, output=b"partial startup", stderr=b"private-password")
            with patch.object(module, "run", side_effect=error), self.assertRaises(subprocess.TimeoutExpired):
                journal.command("Startup timeout", ["fixture"])
            report = json.loads((Path(directory) / "result.json").read_text())
            self.assertEqual(report["checks"][0]["exit_code"], 124)
            log = (Path(directory) / "execution.log").read_text()
            self.assertIn("partial startup", log)
            self.assertNotIn("private-password", log)

    def test_private_auth_response_and_backup_are_not_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = module.Journal(Path(directory), "fixture")
            reply = subprocess.CompletedProcess([], 0, b'private-token-and-backup', b'')
            with patch.object(module, "run", return_value=reply):
                journal.command("Private response", ["fixture"], private_stdout=True)
            self.assertNotIn("private-token-and-backup", (Path(directory) / "execution.log").read_text())

    def test_expected_nonzero_command_does_not_mark_suite_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = module.Journal(Path(directory), "fixture")
            with patch.object(module, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"confirmed identity rejected")):
                result = journal.command("Expected rejection", ["fixture"], ok=False, expected_rejection=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(journal.report["checks"][0]["exit_code"], 1)
            self.assertEqual(journal.report["checks"][0]["status"], "PASS")
            self.assertEqual(journal.report["status"], "RUNNING")

    def test_stop_failure_never_claims_containers_stopped(self):
        def fake(args, data=None, ok=True):
            stdout, stderr, code = b"", b"", 0
            if args[:3] == ["docker", "image", "inspect"]:
                stdout = b"linux/amd64\n"
            elif "{{json .HostConfig.PortBindings}}" in args:
                stdout = b"{}\n"
            elif data and b"server_version_num" in data:
                stdout = b"160013\n"
            elif "config" in args and "json" in args:
                stdout = b'{"services":{"backend":{"tmpfs":["/tmp:size=64m,mode=1777"]}}}'
            elif data and b"information_schema.tables" in data:
                stdout = b"0\n"
            elif "up" in args and args[-1] == "backend":
                code, stderr = 1, b"backend unhealthy"
            elif "stop" in args:
                code, stderr = 1, b"Docker stop failed"
            elif args[:2] == ["docker", "ps"]:
                stdout = b"remaining-fixture\n"
            return subprocess.CompletedProcess(args, code, stdout, stderr)
        with tempfile.TemporaryDirectory() as directory, patch.object(module, "run", side_effect=fake), \
                patch.object(module, "local_docker_environment", return_value=None):
            with self.assertRaises(module.CommandFailure):
                module.execute("fixture:local", directory)
            report = json.loads((Path(directory) / "result.json").read_text())
            self.assertEqual(report["status"], "FAIL")
            self.assertFalse(report["containers_stopped"])
            self.assertIn("backend unhealthy", report["failure_reason"])
            self.assertTrue(any(item["status"] == "FAIL" and "Stop only" in item["name"] for item in report["checks"]))

    def test_requires_explicit_execution_flag_before_docker_access(self):
        with patch.object(module, "execute") as execute, patch("sys.argv", [str(SCRIPT), "--image", "fixture:local"]):
            with self.assertRaises(SystemExit):
                module.main()
            execute.assert_not_called()

    def test_rejects_remote_docker_socket(self):
        reply = subprocess.CompletedProcess([], 0, b'[{"Endpoints":{"docker":{"Host":"tcp://remote:2375"}}}]', b'')
        with patch.object(module, "run", return_value=reply), patch.dict(module.os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "local Unix"):
                module.local_docker_environment()

    def test_running_containers_abort_before_creating_project(self):
        replies = [subprocess.CompletedProcess([], 0, b'[{"Endpoints":{"docker":{"Host":"unix:///var/run/docker.sock"}}}]', b''),
                   subprocess.CompletedProcess([], 0, b'', b''), subprocess.CompletedProcess([], 0, b'existing-container\n', b'')]
        with patch.object(module, "run", side_effect=replies), patch.dict(module.os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Running containers"):
                module.local_docker_environment()

    def test_no_credentials_leak_on_command_error(self):
        result = subprocess.CompletedProcess([], 1, b'secret', b'secret')
        with patch.object(module.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as caught:
                module.run(["fixture", "secret"])
            self.assertNotIn("secret", str(caught.exception))

    def test_static_isolation_guards(self):
        config = module.COMPOSE.read_text()
        source = SCRIPT.read_text()
        self.assertNotIn("ports:", config)
        self.assertNotIn("container_name:", config)
        self.assertIn("internal: true", config)
        self.assertIn("mem_limit: 384m", config)
        self.assertIn("mem_limit: 768m", config)
        self.assertIn("pull_policy: never", config)
        self.assertNotIn('"down"', source)
        self.assertNotIn("docker compose down -v", source)
        self.assertIn('env_file.chmod(0o600)', source)

    def test_interactive_wrapper_syntax_and_privilege_guards(self):
        wrapper = SCRIPT.with_name("run-vps-postgresql-test.sh")
        result = subprocess.run(["bash", "-n", str(wrapper)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        text = wrapper.read_text()
        self.assertIn('${EUID} -ne 0', text)
        self.assertIn('DOCKER_HOST=unix:///var/run/docker.sock', text)
        self.assertIn('chmod 0644 "$workspace/deploy/postgres-init.sh"', text)
        self.assertNotIn("sudo -S", text)
        self.assertNotIn("usermod", text)
        self.assertNotIn("docker.sock chmod", text)

    def test_bundle_whitelist_and_refusal_to_overwrite(self):
        package = SCRIPT.with_name("package-vps-postgresql-test.sh")
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "bundle.tar.gz"
            result = subprocess.run(["bash", str(package), str(archive)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = archive.read_bytes()
            with tarfile.open(archive) as bundle:
                self.assertEqual(set(bundle.getnames()), {
                    "docs/scripts/run-vps-postgresql-test.sh", "docs/scripts/test-vps-postgresql.py",
                    "docs/scripts/pg-test-compose.yml", "deploy/postgres-init.sh"})
            retry = subprocess.run(["bash", str(package), str(archive)], capture_output=True)
            self.assertNotEqual(retry.returncode, 0)
            self.assertEqual(archive.read_bytes(), before)

    def test_image_preparation_never_changes_security_or_deletes_resources(self):
        prepare = SCRIPT.with_name("prepare-vps-postgresql-images.sh")
        self.assertEqual(subprocess.run(["bash", "-n", str(prepare)], capture_output=True).returncode, 0)
        text = prepare.read_text()
        self.assertIn('docker --host unix:///var/run/docker.sock', text)
        self.assertIn('[[ $available -ge 1300 ]]', text)
        self.assertIn('refusing to overwrite', text)
        self.assertIn('sha256sum --check SHA256SUMS', text)
        for forbidden in ("docker_local rm", "docker_local volume rm", "prune", "sudoers", "ufw", "usermod"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
