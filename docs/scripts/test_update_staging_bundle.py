import importlib.util
import hashlib
import io
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("update_staging", Path(__file__).with_name("update-staging-bundle.py"))
UPDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATE)


class UpdateTests(unittest.TestCase):
    def test_only_four_release_fields_change(self):
        original = {"STAGING_BACKEND_REVISION": UPDATE.BASE,
                    "STAGING_BACKEND_IMAGE": "heshan-backend:" + UPDATE.BASE,
                    "STAGING_FRONTEND_REVISION": UPDATE.BASE,
                    "STAGING_STATIC_DIR": str(UPDATE.RELEASES / UPDATE.BASE / "frontend"),
                    "STAGING_JWT_SECRET": "unmodified", "STAGING_DB_PASSWORD": "unmodified"}
        result = UPDATE.updated_values(original)
        self.assertEqual({key for key in original if original[key] != result[key]}, UPDATE.CHANGED_KEYS)
        self.assertEqual(original["STAGING_JWT_SECRET"], result["STAGING_JWT_SECRET"])

    def test_wrong_base_rejected(self):
        with self.assertRaisesRegex(ValueError, "approved base"):
            UPDATE.updated_values({"STAGING_BACKEND_REVISION": "f" * 40})

    def test_only_apps_are_recreated_without_dependencies(self):
        docker = Mock()
        UPDATE.update_apps(docker)
        self.assertEqual(len(docker.compose.call_args_list), 2)
        for call, service in zip(docker.compose.call_args_list, ("backend", "web")):
            self.assertEqual(call.args[-1], service)
            self.assertIn("--no-deps", call.args)
            self.assertIn("--wait", call.args)
            self.assertNotIn("db", call.args)

    def test_backend_failure_prevents_web_update(self):
        docker = Mock()
        docker.compose.side_effect = RuntimeError("unhealthy")
        with self.assertRaises(RuntimeError):
            UPDATE.update_apps(docker)
        self.assertEqual(docker.compose.call_count, 1)

    def test_unapproved_bundle_never_extracted(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            archive = root / "bad.tar.gz"
            archive.write_bytes(b"unapproved")
            target = root / "extract"
            target.mkdir()
            with self.assertRaisesRegex(ValueError, "checksum"):
                UPDATE.unpack(archive, target)
            self.assertEqual(list(target.iterdir()), [])

    def test_atomic_env_is_private_and_replaces_only_target(self):
        with tempfile.TemporaryDirectory() as name:
            env = Path(name) / "staging.env"
            env.write_bytes(b"previous")
            with patch.object(UPDATE, "ENV", env):
                UPDATE.atomic_env(b"new")
            self.assertEqual(env.read_bytes(), b"new")
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)

    def test_symlink_and_traversal_entries_rejected(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / "bad.tar.gz"
                with tarfile.open(archive, "w:gz") as output:
                    entry = tarfile.TarInfo(name)
                    entry.type = kind
                    entry.linkname = "/etc/shadow" if kind == tarfile.SYMTYPE else ""
                    output.addfile(entry)
                target = root / "extract"
                target.mkdir()
                with patch.object(UPDATE, "ARCHIVE_SHA", UPDATE.digest(archive)):
                    with self.assertRaisesRegex(ValueError, "Unsafe"):
                        UPDATE.unpack(archive, target)
                self.assertEqual(list(target.iterdir()), [])

    def test_macos_metadata_not_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "fixture.tar.gz"
            data = {"SOURCE_REVISION": (UPDATE.REVISION + "\n").encode(),
                    "UPDATE_METADATA.json": json.dumps({"revision": UPDATE.REVISION, "base_revision": UPDATE.BASE,
                         "migrations_changed": False, "database_rebuild": False, "founder_initialization": False}).encode()}
            data["SHA256SUMS"] = "".join(hashlib.sha256(value).hexdigest() + "  " + key + "\n" for key, value in data.items()).encode()
            data["._SOURCE_REVISION"] = b"AppleDouble"
            with tarfile.open(archive, "w:gz") as output:
                for name, value in data.items():
                    entry = tarfile.TarInfo("./" + name)
                    entry.size = len(value)
                    output.addfile(entry, io.BytesIO(value))
            target = root / "extract"
            target.mkdir()
            with patch.object(UPDATE, "ARCHIVE_SHA", UPDATE.digest(archive)):
                UPDATE.unpack(archive, target)
            self.assertFalse((target / "._SOURCE_REVISION").exists())

    def test_failed_backup_report_aborts(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory).resolve()
            (report / "result.json").write_text(json.dumps({"status": "FAIL", "exit_code": 1}))
            with patch.object(UPDATE, "private", side_effect=lambda path, directory=False: Path(path)):
                with self.assertRaisesRegex(ValueError, "successful backup"):
                    UPDATE.backup_gate(report)

    def test_no_destructive_or_founder_commands(self):
        source = Path(SPEC.origin).read_text()
        for forbidden in ("down", "prune", "--initialize-founder", "pg_restore", "first-install"):
            self.assertNotIn('"' + forbidden + '"', source)
        self.assertIn("control.Docker(old, ENV, OVERLAY)", source)
        self.assertIn("control.Docker(new, ENV, OVERLAY)", source)


if __name__ == "__main__":
    unittest.main()
