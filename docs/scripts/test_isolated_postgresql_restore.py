"""Mock-only restore tests. Never contact Docker or an actual database."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from unittest.mock import Mock

SPEC = importlib.util.spec_from_file_location("isolated_restore", Path(__file__).with_name("isolated-postgresql-restore.py"))
RESTORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESTORE)
ID = "a" * 64


def snapshot():
    return {"database_name": "heshan_staging", "tables": {table: {"count": 1 if table in {"users", "flyway_schema_history"} else 0, "fingerprint": "b" * 32} for table in RESTORE.TABLES},
            "schema_fingerprint": "c" * 32, "sequences": [],
            "identities": [{"id": 8, "username": "owner-fixture", "role": "USER"}],
            "founders": [], "role_counts": {"USER": 1}, "migrations": [{"version": "1", "checksum": 42, "success": True}],
            "invalid_links": 0, "database_size_bytes": 8 * 1024**2}


class FakeCommands:
    def __init__(self, empty=True, mismatch=False, restore_failure=False, mounts=None, existing_collision=False, token_race=False,
                 resource_drop=False):
        self.calls = []
        self.running = False
        self.name = None
        self.empty = empty
        self.mismatch = mismatch
        self.restore_failure = restore_failure
        self.mounts = mounts
        self.volume = None
        self.existing_collision = existing_collision
        self.token_race = token_race
        self.resource_drop = resource_drop
        self.low_memory = False

    def run(self, args, data=None):
        self.calls.append(args)
        if args[:2] == ["volume", "ls"]:
            return ("heshan-staging_staging_data\n" + ("heshan-restore-data-" + "f" * 24 + "\n" if self.existing_collision else "")).encode()
        if args[:2] == ["volume", "create"]:
            labels = dict(item.split("=", 1) for index, item in enumerate(args) if index > 0 and args[index - 1] == "--label")
            self.volume = {"Name": args[-1], "Driver": "local", "Scope": "local", "Options": None,
                           "Mountpoint": "/new/isolated/data", "Labels": labels}
            if self.token_race:
                self.volume["Labels"]["net.heshan.restore-token"] = "wrong-token"
            return args[-1].encode()
        if args[0] == "create":
            self.name = args[args.index("--name") + 1]
            return ID.encode()
        if args[0] == "start":
            self.running = True
        if args[0] == "stop":
            self.running = False
        if "pg_restore" in args and self.restore_failure:
            raise ValueError("fixture restore error")
        if "pg_restore" in args and self.resource_drop:
            self.low_memory = True
            self.monitor.sample(force=True)
        if args[0] == "stats":
            return b'{"Name":"fixture","CPUPerc":"0.0%","MemUsage":"32MiB / 384MiB"}\n'
        if "psql" in args:
            if b"server_version_num" in data:
                return b"160010\n"
            if b"FROM pg_class" in data:
                return b"0\n" if self.empty else b"1\n"
            actual = snapshot()
            actual["database_name"] = "restore_test"
            if self.mismatch:
                actual["tables"]["posts"]["fingerprint"] = "d" * 32
            return json.dumps(actual).encode() + b"\n"
        return b"fixture\n"

    def json(self, args):
        self.calls.append(args)
        if args[0] == "image":
            return [{"Id": "sha256:" + "e" * 64, "Os": "linux", "Architecture": "amd64"}]
        if args[:2] == ["volume", "inspect"]:
            return [deepcopy(self.volume)]
        mounts = self.mounts if self.mounts is not None else [{"Type": "volume", "Name": self.volume["Name"],
                    "Source": self.volume["Mountpoint"], "Destination": "/var/lib/postgresql/data", "RW": True}]
        return [{"Id": ID, "Name": "/" + self.name, "Config": {"Labels": {"net.heshan.restore-test": self.name}},
                 "HostConfig": {"NetworkMode": "none", "PortBindings": {}, "Binds": [], "Privileged": False,
                                "CgroupnsMode": "private",
                                "ReadonlyRootfs": True, "Memory": 384 * 1024**2, "MemorySwap": 384 * 1024**2,
                                "NanoCpus": 250000000, "Tmpfs": {"/tmp": "rw"}},
                 "Mounts": mounts, "State": {"Running": self.running, "OOMKilled": False}}]


class RestoreTests(unittest.TestCase):
    def exercise(self, commands, bad_checksum=False, resource_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            dump = root / "fixture.dump"
            dump.write_bytes(b"fixture dump")
            sha = RESTORE.digest(dump)
            checksum = Path(str(dump) + ".sha256")
            checksum.write_text(("0" * 64 if bad_checksum else sha) + "  " + str(dump) + "\n")
            reference = root / "reference.json"
            reference.write_text(json.dumps({"format_version": 1, "backup_sha256": sha, "snapshot": snapshot(),
                                             "source_project": "heshan-staging", "source_database": "heshan_staging"}))
            for path in (dump, checksum, reference):
                path.chmod(0o600)
            args = SimpleNamespace(backup=dump, reference=reference, expected_owner_id=8,
                                   expected_owner_username="owner-fixture", expected_migration_version="1")
            report = root / "report"
            report.mkdir()
            def sample_resources(*args):
                if resource_failure or commands.low_memory:
                    raise ValueError("Insufficient resources")
                return {"available_ram_mib": 1200, "free_disk_bytes": 8 * 1024**3}
            with patch.object(RESTORE, "resources", return_value={"available_ram_mib": 1200},
                              side_effect=sample_resources), \
                 patch.object(RESTORE, "staging_state", return_value={"db": {"id": "existing"}}), \
                 patch.object(RESTORE, "BACKUP_DIR", root):
                code = RESTORE.execute(args, report, commands)
            return code, json.loads((report / "result.json").read_text())

    def test_success_uses_only_new_id_and_retains_container(self):
        commands = FakeCommands()
        code, result = self.exercise(commands)
        self.assertEqual(code, 0)
        self.assertTrue(result["data_consistent"])
        self.assertTrue(result["containers_stopped"])
        self.assertEqual(result["founder_verification"], "PRESERVED_UNINITIALIZED")
        self.assertTrue(any(call[0] == "stop" and call[-1] == ID for call in commands.calls))
        self.assertFalse(any(call[0] in {"rm", "restart", "compose"} or call[:2] == ["volume", "rm"] for call in commands.calls))
        self.assertTrue(result["target_volume_retained"])
        self.assertGreaterEqual(result["resource_sample_count"], 3)
        for call in commands.calls:
            if "pg_restore" in call:
                self.assertEqual(call[2], ID)
                self.assertEqual(call[-1], "restore_test")
                self.assertIn("--single-transaction", call)

    def test_bad_checksum_never_creates_container(self):
        commands = FakeCommands()
        code, result = self.exercise(commands, bad_checksum=True)
        self.assertEqual(code, 1)
        self.assertEqual(commands.calls, [])
        self.assertFalse(result["restore_success"])

    def test_nonempty_database_never_restored_and_temp_stopped(self):
        commands = FakeCommands(empty=False)
        code, result = self.exercise(commands)
        self.assertEqual(code, 1)
        self.assertTrue(result["containers_stopped"])
        self.assertTrue(result["target_volume_retained"])
        self.assertFalse(any("pg_restore" in call for call in commands.calls))

    def test_any_volume_rejected_before_start(self):
        commands = FakeCommands(mounts=[{"Type": "volume", "Name": "heshan-staging_staging_data"}])
        code, result = self.exercise(commands)
        self.assertEqual(code, 1)
        self.assertTrue(result["unverified_target_retained"])
        self.assertFalse(any(call[0] == "start" for call in commands.calls))

    def test_restore_failure_stops_new_container_and_records_failure(self):
        code, result = self.exercise(FakeCommands(restore_failure=True))
        self.assertEqual(code, 1)
        self.assertFalse(result["restore_success"])
        self.assertTrue(result["containers_stopped"])
        self.assertTrue(any(check["status"] == "FAIL" for check in result["checks"]))

    def test_fingerprint_mismatch_cannot_pass(self):
        code, result = self.exercise(FakeCommands(mismatch=True))
        self.assertEqual(code, 1)
        self.assertTrue(result["restore_success"])
        self.assertFalse(result["data_consistent"])

    def test_owner_mismatch_and_inconsistent_founder_rejected(self):
        with self.assertRaises(ValueError):
            RESTORE.validate_snapshot(snapshot(), 9, "owner-fixture", "1")
        invalid = snapshot()
        invalid["identities"][0]["role"] = "SUPER_ADMIN"
        invalid["role_counts"] = {"SUPER_ADMIN": 1}
        with self.assertRaisesRegex(ValueError, "without protected"):
            RESTORE.validate_snapshot(invalid, 8, "owner-fixture", "1")
        invalid["founders"] = [{"id": 1, "user_id": 8}]
        invalid["tables"]["founder_identity"]["count"] = 1
        with self.assertRaisesRegex(ValueError, "uninitialized USER"):
            RESTORE.validate_snapshot(invalid, 8, "owner-fixture", "1")

    def test_invalid_roles_failed_migrations_and_large_database_rejected(self):
        for field, value in (("invalid_links", 1), ("database_size_bytes", 65 * 1024**2),
                             ("migrations", [{"version": "1", "success": False}])):
            invalid = deepcopy(snapshot())
            invalid[field] = value
            with self.assertRaises(ValueError):
                RESTORE.validate_snapshot(invalid, 8, "owner-fixture", "1")

    def test_bind_and_network_targets_rejected(self):
        commands = FakeCommands()
        commands.name = "fixture"
        commands.volume = {"Name": "heshan-restore-data-fixture", "Mountpoint": "/new/isolated/data"}
        model = commands.json(["inspect", ID])[0]
        for key, value in (("NetworkMode", "bridge"), ("Binds", ["/existing:/data"]),
                           ("CgroupnsMode", "host"),
                           ("PortBindings", {"5432/tcp": [{"HostPort": "5432"}]})):
            invalid = deepcopy(model)
            invalid["HostConfig"][key] = value
            with self.assertRaises(ValueError):
                RESTORE.validate_target(invalid, ID, "fixture", commands.volume)

    def test_existing_volume_name_and_idempotent_create_race_are_rejected(self):
        commands = FakeCommands(existing_collision=True)
        with patch.object(RESTORE.secrets, "token_hex", side_effect=lambda size: "f" * (size * 2)):
            code, result = self.exercise(commands)
        self.assertEqual(code, 1)
        self.assertFalse(any(call[:2] == ["volume", "create"] for call in commands.calls))
        commands = FakeCommands(token_race=True)
        code, result = self.exercise(commands)
        self.assertEqual(code, 1)
        self.assertFalse(any(call[0] == "create" for call in commands.calls))

    def test_options_and_staging_path_alias_are_rejected(self):
        volume = {"Name": "heshan-restore-data-fixture", "Mountpoint": "/new/isolated/data", "Driver": "local",
                  "Scope": "local", "Options": {}, "Labels": {"net.heshan.restore-test": "fixture", "net.heshan.restore-token": "token"}}
        with self.assertRaisesRegex(ValueError, "alias"):
            RESTORE.validate_volume(volume, volume["Name"], "fixture", "token", set(), {volume["Mountpoint"]})
        volume["Options"] = {"device": "/existing/staging/data"}
        with self.assertRaises(ValueError):
            RESTORE.validate_volume(volume, volume["Name"], "fixture", "token", set(), set())

    def test_resource_drop_during_restore_stops_only_new_target_and_preserves_volume(self):
        commands = FakeCommands(resource_drop=True)
        code, result = self.exercise(commands)
        self.assertEqual(code, 1)
        self.assertTrue(result["containers_stopped"])
        self.assertTrue(result["target_volume_retained"])
        self.assertIn("Insufficient resources", result["reason"])
        self.assertFalse(any(call[:2] == ["volume", "rm"] or call[0] == "rm" for call in commands.calls))
        self.assertEqual([call[-1] for call in commands.calls if call[0] == "stop"], [ID])

    def test_memory_disk_and_additional_swap_limits(self):
        for available, disk in ((767 * 1024, 8 * 1024**3), (1200 * 1024, 4 * 1024**3 - 1)):
            with patch.object(RESTORE.Path, "read_text", return_value=f"MemAvailable: {available} kB\nSwapTotal: 1024 kB\nSwapFree: 1024 kB\n"), \
                 patch.object(RESTORE.shutil, "disk_usage", return_value=SimpleNamespace(free=disk)):
                with self.assertRaises(ValueError):
                    RESTORE.resources()
        commands = FakeCommands()
        commands.name = "fixture"
        commands.volume = {"Name": "heshan-restore-data-fixture", "Mountpoint": "/new/isolated/data"}
        model = commands.json(["inspect", ID])[0]
        model["HostConfig"]["MemorySwap"] += 1
        with self.assertRaises(ValueError):
            RESTORE.validate_target(model, ID, "fixture", commands.volume)

    def test_in_flight_command_is_killed_on_monitor_failure_without_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            commands = RESTORE.Commands(Path(directory))
            commands.monitor = Mock()
            commands.monitor.sample.side_effect = [None, ValueError("memory gate")]
            process = Mock()
            process.communicate.side_effect = [subprocess.TimeoutExpired("fixture", 2), (b"", b"")]
            process.poll.return_value = None
            with patch.object(RESTORE.subprocess, "Popen", return_value=process):
                with self.assertRaisesRegex(ValueError, "memory gate"):
                    commands.run(["exec", "-i", ID, "pg_restore"], data=b"fixture")
            process.kill.assert_called_once()

    def test_random_volume_is_created_before_mount_and_no_data_tmpfs(self):
        commands = FakeCommands()
        self.exercise(commands)
        create_volume = next(index for index, call in enumerate(commands.calls) if call[:2] == ["volume", "create"])
        create_container = next(index for index, call in enumerate(commands.calls) if call[0] == "create")
        self.assertLess(create_volume, create_container)
        args = commands.calls[create_container]
        self.assertIn("type=volume,src=" + commands.volume["Name"] + ",dst=/var/lib/postgresql/data,volume-nocopy", args)
        self.assertFalse(any(arg.startswith("/var/lib/postgresql/data:") for arg in args))
        self.assertNotEqual(commands.volume["Name"], "heshan-staging_staging_data")

    def test_readiness_uses_tcp_and_retries_only_normal_not_ready_codes(self):
        commands = Mock()
        commands.run.side_effect = [RESTORE.CommandFailure("starting", 12), b"ready"]
        state = Mock(return_value={"State": {"Running": True, "OOMKilled": False}})
        with patch.object(RESTORE.time, "sleep") as sleep:
            RESTORE.wait_for_postgres(commands, ID, state, Mock())
        self.assertEqual(commands.run.call_count, 2)
        sleep.assert_called_once_with(1)
        self.assertIn("pg_isready -h 127.0.0.1", commands.run.call_args.args[0][-1])

    def test_readiness_does_not_retry_safety_failures_or_docker_errors(self):
        state = Mock(return_value={"State": {"Running": True, "OOMKilled": False}})
        for error in (ValueError("resource safety gate"), RESTORE.CommandFailure("Docker failed", 125),
                      RESTORE.CommandFailure("Docker daemon error", 1),
                      RESTORE.CommandFailure("timeout", 124)):
            commands = Mock()
            commands.run.side_effect = error
            with patch.object(RESTORE.time, "sleep") as sleep:
                with self.assertRaises(ValueError):
                    RESTORE.wait_for_postgres(commands, ID, state, Mock())
            self.assertEqual(commands.run.call_count, 1)
            sleep.assert_not_called()

    def test_exact_peak_and_unavailable_are_distinguished(self):
        commands = Mock()
        commands.run.return_value = b"50331648\n"
        self.assertEqual(RESTORE.memory_peak(commands, ID)["bytes"], 50331648)
        commands.run.return_value = b"unavailable"
        self.assertIsNone(RESTORE.memory_peak(commands, ID)["bytes"])

    def test_reference_sql_is_read_only_and_covers_all_tables(self):
        sql = RESTORE.SQL.read_text()
        self.assertIn("BEGIN READ ONLY", sql)
        for table in RESTORE.TABLES:
            self.assertIn(table, sql)
        for command in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE "):
            self.assertNotIn(command, sql)

    def test_resource_failure_never_creates_container(self):
        commands = FakeCommands()
        code, result = self.exercise(commands, resource_failure=True)
        self.assertEqual(code, 1)
        self.assertEqual(commands.calls, [])
        self.assertIn("Insufficient resources", result["reason"])

    def test_existing_staging_changes_force_failure(self):
        original = RESTORE.compare_snapshot
        # Install a persistent replacement from inside the exercise's baseline
        # fixture only for the final service verification.
        def compare(expected, actual):
            original(expected, actual)
            RESTORE.staging_state.return_value = {"db": {"id": "different"}}
        with patch.object(RESTORE, "compare_snapshot", side_effect=compare):
            code, result = self.exercise(FakeCommands())
        self.assertEqual(code, 1)
        self.assertFalse(result["existing_services_unchanged"])

    def test_legacy_invocation_refuses_without_touching_docker(self):
        result = subprocess.run(["bash", str(Path(__file__).with_name("test-restore-postgresql.sh")), "/not/a/backup.dump"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--reference", result.stderr)


if __name__ == "__main__":
    unittest.main()
