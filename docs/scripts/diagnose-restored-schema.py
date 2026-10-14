#!/usr/bin/env python3
"""Read-only schema diagnosis of one explicitly approved, retained restore target."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tempfile

TARGET = "d80ebe641bc61fc116a286db3bd9dc134cd72e7b4e7d7d6ec048507d84e1e601"
NAME = "heshan-restore-test-b21f953a0b230fb3080f2b4b"
VOLUME = "heshan-restore-data-33a647148132f16c72a9c189"
SOURCE = "heshan-staging-db-1"
PINS = {
    "isolated-postgresql-restore.py": "319b069765d89c3abbb3b488d361c14fa137adc15435c6b25ff52e68acc81d7c",
    "restore-reference.sql": "d24b8d898d197a5dff8b80992704267763655bddd412bbb411eadb7e38f87001",
}


def structural_sql(sql):
    head, marker, tail = sql.partition("), structure AS (\n")
    body, end, unused = tail.partition("\n)\nSELECT json_build_object(")
    if not marker or not end or not head.startswith("-- Capture"):
        raise ValueError("Pinned SQL structure unexpected")
    return ("BEGIN READ ONLY;\nSET LOCAL search_path = public, pg_catalog;\n"
            "SET LOCAL TIME ZONE 'UTC';\nWITH structure AS (\n" + body +
            "\n) SELECT json_object_agg(key, definition ORDER BY key) FROM structure;\nCOMMIT;\n")


def differences(source, restored):
    return [{"key": key, "source": source.get(key), "restored": restored.get(key)}
            for key in sorted(set(source) | set(restored)) if source.get(key) != restored.get(key)]


def read_only_query(commands, core, container, database, sql):
    if container not in {SOURCE, TARGET} or database not in {"heshan_staging", "restore_test"}:
        raise ValueError("Unapproved database target")
    if (container == SOURCE) != (database == "heshan_staging"):
        raise ValueError("Container/database mismatch")
    if not sql.startswith(("-- Capture", "BEGIN READ ONLY;")) or "COMMIT;" not in sql:
        raise ValueError("Read-only transaction required")
    return core.snapshot_output(commands.run([
        "exec", "-i", container, "psql", "-X", "-q", "-A", "-t", "-U", "postgres",
        "-d", database, "-v", "ON_ERROR_STOP=1"], sql.encode()))


METADATA_SQL = """BEGIN READ ONLY;
SELECT json_build_object('server_version', current_setting('server_version'),
 'encoding', pg_encoding_to_char(encoding), 'collate', datcollate,
 'ctype', datctype, 'locale_provider', datlocprovider, 'icu_locale', daticulocale)
FROM pg_database WHERE datname = current_database();
COMMIT;
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-readonly-diagnosis", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0 or not args.execute_readonly_diagnosis:
        parser.error("Linux, interactive sudo and explicit diagnosis approval required")
    os.umask(0o077)
    root = Path(__file__).resolve().parent
    for name, expected in PINS.items():
        path = root / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Unsafe pinned input")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Pinned script mismatch")
    spec = importlib.util.spec_from_file_location("restore_core", root / "isolated-postgresql-restore.py")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    lock = os.open("/var/tmp/heshan-isolated-restore.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    info = os.fstat(lock)
    core.require(info.st_uid == 0 and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                 and stat.S_IMODE(info.st_mode) == 0o600, "Unsafe lock")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    def interrupted(signum, frame):
        raise InterruptedError("Diagnosis interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    report = Path(tempfile.mkdtemp(prefix="heshan-schema-diagnosis-", dir="/var/tmp"))
    commands = core.Commands(report)
    result = {"status": "FAIL", "restore_reexecuted": False, "target_stopped": False,
              "report_directory": str(report), "checks": {}}
    before = None
    touched = False
    inspect_target = lambda: commands.json(["inspect", TARGET])[0]
    try:
        result["resources_before"] = core.resources()
        before = core.staging_state(commands)
        source = commands.json(["inspect", SOURCE])[0]
        target = inspect_target()
        volume = commands.json(["volume", "inspect", VOLUME])[0]
        token = volume.get("Labels", {}).get("net.heshan.restore-token", "")
        core.require(bool(re.fullmatch(r"[0-9a-f]{64}", token)), "Missing volume ownership token")
        core.validate_volume(volume, VOLUME, NAME, token,
                             {m.get("Name") for m in source["Mounts"]},
                             {m.get("Source") for m in source["Mounts"]})
        core.validate_target(target, TARGET, NAME, volume)
        core.require(not target["State"]["Running"] and not target["State"]["OOMKilled"],
                     "Target must be the retained stopped container without OOM")
        core.require(any(m.get("Name") == "heshan-staging_staging_data"
                         and m["Destination"] == "/var/lib/postgresql/data" for m in source["Mounts"]),
                     "Unexpected source volume")
        core.resources(volume["Mountpoint"])
        sql = (root / "restore-reference.sql").read_text()
        schema_sql = structural_sql(sql)
        original = read_only_query(commands, core, SOURCE, "heshan_staging", sql)
        core.validate_snapshot(original, 1, "ghost", "1")
        touched = True
        commands.run(["start", TARGET])
        monitor = core.ResourceMonitor(report, commands, TARGET, volume["Mountpoint"], before, inspect_target)
        commands.monitor = monitor
        core.wait_for_postgres(commands, TARGET, inspect_target, monitor)
        actual = read_only_query(commands, core, TARGET, "restore_test", sql)
        result["checks"] = {key: "PASS" if original[key] == actual[key] else "FAIL" for key in
                            ("tables", "schema_fingerprint", "sequences", "identities", "founders",
                             "role_counts", "migrations", "invalid_links")}
        try:
            result["schema_validation"] = core.compare_schema(original, actual)
            result["checks"]["schema_fingerprint"] = "PASS"
        except ValueError as error:
            result["schema_validation"] = {"status": "FAIL", "reason": str(error)}
        result["table_counts"] = {key: {"source": original["tables"][key]["count"],
                                       "restored": actual["tables"].get(key, {}).get("count")}
                                  for key in sorted(core.TABLES)}
        source_schema = read_only_query(commands, core, SOURCE, "heshan_staging", schema_sql)
        target_schema = read_only_query(commands, core, TARGET, "restore_test", schema_sql)
        result["schema_differences"] = differences(source_schema, target_schema)
        result["schema_fingerprints"] = {"source": original["schema_fingerprint"], "restored": actual["schema_fingerprint"]}
        result["database_metadata"] = {
            "source": read_only_query(commands, core, SOURCE, "heshan_staging", METADATA_SQL),
            "restored": read_only_query(commands, core, TARGET, "restore_test", METADATA_SQL)}
        result["ghost_user_preserved"] = any(i == {"id": 1, "username": "ghost", "role": "USER"}
                                             for i in actual["identities"])
        result["founder_uninitialized"] = actual["founders"] == []
        core.compare_snapshot(original, read_only_query(commands, core, SOURCE, "heshan_staging", sql))
        result["source_data_unchanged"] = True
        (report / "schema-source.json").write_text(json.dumps(source_schema, indent=2) + "\n")
        (report / "schema-restored.json").write_text(json.dumps(target_schema, indent=2) + "\n")
        result["resources_after"] = core.resources(volume["Mountpoint"])
        result["diagnosis_completed"] = True
        result["status"] = "PASS"  # Diagnosis completion, not restore acceptance.
    except Exception as error:
        result["reason"] = str(error) if isinstance(error, ValueError) else type(error).__name__
    finally:
        commands.monitor = None
        if touched:
            try:
                model = inspect_target()
                core.validate_target(model, TARGET, NAME, volume)
                if model["State"]["Running"]:
                    commands.run(["stop", "--time", "30", TARGET])
                result["target_stopped"] = not inspect_target()["State"]["Running"]
            except Exception:
                result["status"] = "FAIL"
                result["stop_error"] = "Could not verify/stop approved temporary target; owner inspection required"
        if before is not None:
            try:
                result["staging_unchanged_and_healthy"] = core.staging_state(commands) == before
            except Exception:
                result["staging_unchanged_and_healthy"] = False
            if not result["staging_unchanged_and_healthy"]:
                result["status"] = "FAIL"
        if touched and not result["target_stopped"]:
            result["status"] = "FAIL"
        result["data_verification"] = "PASS" if result["checks"] and all(
            status == "PASS" for key, status in result["checks"].items() if key != "schema_fingerprint") else "FAIL"
        result["structure_verification"] = result["checks"].get("schema_fingerprint", "NOT TESTED")
        result["retained_restore_verification"] = "PASS" if (
            result["status"] == "PASS" and result["data_verification"] == "PASS"
            and result["structure_verification"] == "PASS" and result["target_stopped"]
            and result.get("source_data_unchanged") and result.get("ghost_user_preserved")
            and result.get("founder_uninitialized") and result.get("staging_unchanged_and_healthy")) else "FAIL"
        result["original_restore_report"] = "Original FAIL report remains unchanged; this is a new read-only verification"
        result["diagnosis_status"] = result["status"]
        result["status"] = result["retained_restore_verification"]
        (report / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
