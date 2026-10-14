from copy import deepcopy
import contextlib
import importlib.util
import json
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("restart_check", ROOT / "verify-staging-restart-persistence.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def model(name):
    index = list(module.IDS).index(name)
    return {"id": module.IDS[name], "project": "heshan-staging", "image_id": "sha256:fixed",
            "files": "base.yml," + str(module.OVERLAY), "running": True, "oom": False,
            "health": "healthy", "started": "before", "restarts": 0,
            "mounts": [{"Destination": "/var/lib/postgresql/data", "Type": "volume", "RW": True,
                        "Name": "heshan-staging_staging_data",
                        "Source": "/var/lib/docker/volumes/heshan-staging_staging_data/_data"}] if index == 0 else [],
            "bindings": {}, "memory": (384, 768, 64)[index] * 1024**2,
            "memory_swap": (768, 1536, 128)[index] * 1024**2, "cpus": (350000000, 600000000, 100000000)[index],
            "policy": "unless-stopped", "networks": {},
            "ports": {"8443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18443"}]} if index == 2 else {}}


class RestartTest(unittest.TestCase):
    def run_fixture(self, failure=None):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory)
            backup = report / "new.dump"
            backup.write_bytes(b"fixture")
            Path(str(backup) + ".sha256").write_text("a" * 64 + "  " + str(backup) + "\n")
            backup_report = report / "backup"
            backup_report.mkdir()
            (backup_report / "result.json").write_text(json.dumps({"status": "PASS", "exit_code": 0, "backup": str(backup),
                "containers_modified": False, "database_restored": False}))
            actions = []
            class Runtime:
                def __init__(self, core, report):
                    self.before = None
                    self.active = set()
                    self.states = {name: model(name) for name in module.IDS}
                def inspect(self, name):
                    return deepcopy(self.states[name])
                def sample(self, force=False):
                    if failure == "resource" and actions:
                        raise ValueError("Resource gate")
                def snapshot(self):
                    if failure == "data" and actions:
                        return {"tables": {"users": {"count": 999}}}
                    return {"tables": {"users": {"count": 5}}}
                def https(self):
                    pass
                def run(self, args, timeout=None):
                    if args[0] == "bash":
                        if failure == "backup":
                            raise ValueError("Backup failed")
                        return ("Report: " + str(backup_report) + "\n").encode()
                    actions.append(args)
                    name = next(name for name, container_id in module.IDS.items() if container_id == args[-1])
                    self.states[name]["started"] = "after"
                    return b"ok"
            def compare(before, after):
                require(before == after, "Data mismatch")
            core = SimpleNamespace(require=require, resources=lambda *a: {"host_swap_used_mib": 2},
                digest=lambda path: module.OVERLAY_SHA if path == module.OVERLAY else "a" * 64,
                private_file=lambda path: Path(path), BACKUP_DIR=report,
                validate_snapshot=lambda *a: None, compare_snapshot=compare)
            def health(runtime, names, timeout):
                if failure == "backend" or (failure == "db" and module.DB in names):
                    raise ValueError("Health timeout")
            with patch.object(module, "Runtime", Runtime), patch.object(module, "wait_healthy", health), contextlib.redirect_stdout(io.StringIO()):
                code = module.execute(core, report)
            result = json.loads((report / "result.json").read_text())
            return code, result, actions

    def test_success_only_two_captured_id_restarts(self):
        code, result, actions = self.run_fixture()
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(actions, [["docker", "restart", "--time", "60", module.IDS[name]]
                                   for name in (module.BACKEND, module.DB)])
        self.assertFalse(result["database_rebuilt"])
        self.assertFalse(result["database_restored"])
        self.assertFalse(result["founder_initialized"])

    def test_backup_failure_never_restarts(self):
        code, result, actions = self.run_fixture("backup")
        self.assertEqual(code, 1)
        self.assertEqual(actions, [])

    def test_backend_timeout_or_data_or_resource_failure_never_restarts_db(self):
        for failure in ("backend", "data", "resource"):
            with self.subTest(failure=failure):
                code, result, actions = self.run_fixture(failure)
                self.assertEqual(code, 1)
                self.assertEqual(len(actions), 1)
                self.assertEqual(actions[0][-1], module.IDS[module.BACKEND])

    def test_db_timeout_does_not_repeat_restart(self):
        code, result, actions = self.run_fixture("db")
        self.assertEqual(code, 1)
        self.assertEqual(len(actions), 2)
        self.assertFalse(result["automatic_recovery_actions"])

    def test_stable_identity_mount_image_and_oom_mismatches_fail(self):
        core = SimpleNamespace(require=require)
        before = model(module.DB)
        for field, value in (("id", "other"), ("image_id", "new"), ("mounts", []),
                             ("oom", True), ("restarts", 1), ("files", "missing-overlay")):
            changed = deepcopy(before)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.validate_state(core, module.DB, changed, before, {module.DB, module.BACKEND})

    def test_only_expected_transition_can_be_unhealthy(self):
        core = SimpleNamespace(require=require)
        before = model(module.BACKEND)
        changed = deepcopy(before)
        changed["health"] = "starting"
        module.validate_state(core, module.BACKEND, changed, before, {module.BACKEND})
        with self.assertRaises(ValueError):
            module.validate_state(core, module.BACKEND, changed, before, set())

    def test_pinned_dependencies(self):
        for file, sha in module.PINS.items():
            self.assertEqual(module.hashlib.sha256((ROOT / file).read_bytes()).hexdigest(), sha)


if __name__ == "__main__":
    unittest.main()
