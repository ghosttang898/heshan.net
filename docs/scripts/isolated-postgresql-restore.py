#!/usr/bin/env python3
"""Owner-approved restore using a new retained container and dedicated volume."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

TABLES = {"users", "posts", "comments", "founder_identity", "role_change_audit", "flyway_schema_history"}
STAGING = ["heshan-staging-db-1", "heshan-staging-backend-1", "heshan-staging-web-1"]
SQL = Path(__file__).with_name("restore-reference.sql")
BACKUP_DIR = Path("/var/backups/heshan-staging")


def require(condition, message):
    if not condition:
        raise ValueError(message)


class CommandFailure(ValueError):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def private_file(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink() and path.is_file(), "Use an absolute non-aliased regular file")
    info = path.stat()
    require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600, "Input must be owner-only mode 0600")
    return path


def validate_snapshot(snapshot, owner_id, owner_name, version):
    require(snapshot["database_name"] == "heshan_staging", "Reference must originate from Staging, not production")
    require(set(snapshot["tables"]) == TABLES, "Missing/unexpected reference tables")
    for table in snapshot["tables"].values():
        require(type(table["count"]) is int and table["count"] >= 0
                and re.fullmatch(r"[0-9a-f]{32}", table["fingerprint"]), "Invalid table reference")
    require(re.fullmatch(r"[0-9a-f]{32}", snapshot["schema_fingerprint"]), "Invalid schema reference")
    require(snapshot["invalid_links"] == 0, "Orphaned reference data")
    identities = snapshot["identities"]
    require(len(identities) == snapshot["tables"]["users"]["count"]
            and len({item["id"] for item in identities}) == len(identities)
            and len({item["username"] for item in identities}) == len(identities), "Identity count/uniqueness mismatch")
    require(all(item["role"] in {"USER", "ADMIN", "SUPER_ADMIN"} for item in identities), "Invalid user role")
    require(dict(Counter(item["role"] for item in identities)) == snapshot["role_counts"], "Role counts mismatch")
    owners = [item for item in identities if item["id"] == owner_id and item["username"] == owner_name]
    require(len(owners) == 1, "Confirmed owner ID and username do not match reference")
    super_ids = {item["id"] for item in identities if item["role"] == "SUPER_ADMIN"}
    founders = snapshot["founders"]
    require(len(founders) == snapshot["tables"]["founder_identity"]["count"], "Founder count mismatch")
    require(len(founders) <= 1 and len(super_ids) <= 1, "Multiple founder/super-admin records")
    if founders:
        require(founders[0]["id"] == 1 and super_ids == {founders[0]["user_id"]}
                and founders[0]["user_id"] == owner_id, "Confirmed founder identity/role mismatch")
    else:
        require(not super_ids, "SUPER_ADMIN exists without protected founder identity")
    require(owners[0]["role"] == "USER" and not founders and not super_ids,
            "This approved drill requires an uninitialized USER owner; no elevation allowed")
    require(snapshot["migrations"] and all(item["success"] is True for item in snapshot["migrations"])
            and snapshot["migrations"][-1]["version"] == version, "Unexpected/failed Flyway migration")
    require(len(snapshot["migrations"]) == snapshot["tables"]["flyway_schema_history"]["count"], "Flyway count mismatch")
    require(type(snapshot["database_size_bytes"]) is int and 0 < snapshot["database_size_bytes"] <= 64 * 1024**2,
            "This small-VPS drill is limited to a source database <=64 MiB")


ENUM_CHECKS = {
    "constraint:comments:comments_status_check": ("status", ("PUBLISHED", "HIDDEN", "DELETED")),
    "constraint:posts:posts_status_check": ("status", ("PUBLISHED", "HIDDEN", "DELETED")),
    "constraint:posts:posts_type_check": ("type", ("CHAT", "FIND_PERSON")),
    "constraint:role_change_audit:role_change_audit_action_check":
        ("action", ("GRANT_ADMIN", "REVOKE_ADMIN", "INITIALIZE_FOUNDER")),
    "constraint:role_change_audit:role_change_audit_new_role_check": ("new_role", ("USER", "ADMIN", "SUPER_ADMIN")),
    "constraint:role_change_audit:role_change_audit_old_role_check": ("old_role", ("USER", "ADMIN", "SUPER_ADMIN")),
    "constraint:users:users_role_check": ("role", ("USER", "ADMIN", "SUPER_ADMIN")),
}


def equivalent_check_forms(column, values):
    # Only fixed, non-NULL varchar literals in the seven observed enum CHECKs.
    literals = ["'" + value + "'::character varying" for value in values]
    prefix = "CHECK (((" + column + ")::text = ANY ("
    return (prefix + "(ARRAY[" + ", ".join(literals) + "])::text[])))",
            prefix + "ARRAY[" + ", ".join("(" + value + ")::text" for value in literals) + "])))")


def normalize_check(key, definition):
    if key in ENUM_CHECKS:
        source, restored = equivalent_check_forms(*ENUM_CHECKS[key])
        if definition in (source, restored):
            return source
    return definition


def compare_schema(expected, actual):
    raw_equal = actual.get("schema_fingerprint") == expected["schema_fingerprint"]
    left, right = expected.get("schema_definitions"), actual.get("schema_definitions")
    if left is None or right is None:
        require(raw_equal, "Structure definitions required to resolve differing raw fingerprints")
        return {"raw_fingerprint_match": True, "normalized_checks": [], "mode": "legacy exact fingerprint"}
    require(isinstance(left, dict) and isinstance(right, dict) and bool(left) and set(left) == set(right),
            "Schema definition keys differ")
    required = set(ENUM_CHECKS) | {key.replace("constraint:", "constraint_flags:", 1) for key in ENUM_CHECKS}
    require(required.issubset(left), "Required CHECK definitions/flags missing")
    normalized = []
    for key in sorted(left):
        require(isinstance(left[key], str) and isinstance(right[key], str), "Invalid schema definition")
        require(normalize_check(key, left[key]) == normalize_check(key, right[key]),
                "Restored schema definition mismatch: " + key)
        if left[key] != right[key]:
            normalized.append(key)
    return {"raw_fingerprint_match": raw_equal, "normalized_checks": normalized,
            "mode": "strict definitions with seven exact enum-CHECK equivalents"}


def compare_snapshot(expected, actual):
    for key in ("tables", "schema_fingerprint", "sequences", "identities", "founders", "role_counts", "migrations", "invalid_links"):
        if key == "schema_fingerprint":
            compare_schema(expected, actual)
        else:
            require(actual.get(key) == expected[key], "Restored reference mismatch: " + key)


def validate_volume(model, volume_name, name, token, existing_names, forbidden_sources):
    require(volume_name.startswith("heshan-restore-data-") and volume_name not in existing_names
            and volume_name != "heshan-staging_staging_data", "Existing/staging volume forbidden")
    require(model["Name"] == volume_name and model["Driver"] == "local" and not model.get("Options")
            and model.get("Scope") == "local", "Volume must be a new local volume without driver options")
    require(model.get("Labels", {}).get("net.heshan.restore-test") == name
            and model.get("Labels", {}).get("net.heshan.restore-token") == token, "Volume ownership token mismatch")
    require(model.get("Mountpoint") and model["Mountpoint"] not in forbidden_sources, "Existing data path alias forbidden")


def validate_target(model, container_id, name, volume):
    require(model["Id"] == container_id and model["Name"] == "/" + name
            and model["Config"]["Labels"].get("net.heshan.restore-test") == name, "Target identity/label mismatch")
    require(model["HostConfig"]["NetworkMode"] == "none"
            and not model["HostConfig"].get("PortBindings")
            and not model["HostConfig"].get("Binds")
            and not model["HostConfig"].get("Privileged"), "Unsafe target network/bind/privilege")
    require(set(model.get("NetworkSettings", {}).get("Networks", {})).issubset({"none"}), "Unexpected target network connection")
    require(model["HostConfig"].get("CgroupnsMode") == "private", "Private container cgroup namespace required for peak measurements")
    mounts = model["Mounts"]
    require(all(item["Type"] in {"volume", "tmpfs"} for item in mounts), "Bind mounts are forbidden")
    data = [item for item in mounts if item["Type"] == "volume"]
    require(len(data) == 1 and data[0].get("Name") == volume["Name"]
            and data[0].get("Destination") == "/var/lib/postgresql/data"
            and data[0].get("Source") == volume["Mountpoint"] and data[0].get("RW") is True,
            "Only this run's dedicated data volume is allowed")
    require("/var/lib/postgresql/data" not in model["HostConfig"]["Tmpfs"], "Data must survive temporary container stop")
    require(model["HostConfig"]["Memory"] == 384 * 1024**2
            and model["HostConfig"]["MemorySwap"] == 384 * 1024**2
            and model["HostConfig"]["NanoCpus"] == 250000000
            and model["HostConfig"]["ReadonlyRootfs"], "Target resource/read-only limit mismatch")


def resources(data_path=None):
    memory = {line.split()[0].rstrip(":"): int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()}
    available = memory["MemAvailable"]
    free = min(shutil.disk_usage(path).free for path in ["/var/tmp", *([data_path] if data_path else [])])
    require(available >= 768 * 1024 and free >= 4 * 1024**3, "Need >=768 MiB available RAM and >=4 GiB free disk")
    return {"available_ram_mib": available // 1024, "free_disk_bytes": free,
            "host_swap_used_mib": (memory["SwapTotal"] - memory["SwapFree"]) // 1024,
            "load_average": list(os.getloadavg())}


class ResourceMonitor:
    def __init__(self, report, commands, target, volume_path, before, inspect_target):
        self.report, self.commands, self.target = report, commands, target
        self.volume_path, self.before, self.inspect_target = volume_path, before, inspect_target
        self.last = 0
        self.samples = 0

    def sample(self, force=False):
        if not force and time.monotonic() - self.last < 2:
            return
        self.last = time.monotonic()
        entry = {"timestamp_unix": time.time(), "status": "FAIL"}
        self.commands.in_monitor = True
        try:
            entry["host"] = resources(self.volume_path)
            state = self.inspect_target()["State"]
            require(state["Running"] and not state["OOMKilled"], "Temporary target stopped/OOM during monitoring")
            require(staging_state(self.commands) == self.before, "Staging changed/unhealthy during monitoring")
            stats = self.commands.run(["stats", "--no-stream", "--format", "{{json .}}", *STAGING, self.target])
            entry["containers"] = [json.loads(line) for line in stats.decode().splitlines() if line]
            entry["status"] = "PASS"
        except Exception as error:
            entry["reason"] = str(error) if isinstance(error, ValueError) else type(error).__name__
            raise
        finally:
            self.samples += 1
            with (self.report / "resource-samples.jsonl").open("a") as stream:
                stream.write(json.dumps(entry) + "\n")
            self.commands.in_monitor = False


class Commands:
    def __init__(self, report):
        self.report = report
        self.password = secrets.token_hex(32)
        self.monitor = None
        self.in_monitor = False
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/root",
                    "DOCKER_HOST": "unix:///var/run/docker.sock", "POSTGRES_PASSWORD": self.password}

    def run(self, args, data=None):
        if self.monitor and not self.in_monitor:
            self.monitor.sample()
        process = None
        safe_command = re.sub(r"net\.heshan\.restore-token=[0-9a-f]+", "net.heshan.restore-token=[REDACTED]", " ".join(args))
        try:
            process = subprocess.Popen(["docker", *args], stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env)
            deadline = time.monotonic() + (300 if "pg_restore" in args else 30)
            first = True
            while True:
                try:
                    stdout, stderr = process.communicate(input=data if first else None,
                                                         timeout=min(2, max(0.01, deadline - time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    if time.monotonic() >= deadline:
                        raise
                    if self.monitor and not self.in_monitor:
                        self.monitor.sample()
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            with (self.report / "execution.log").open("a") as log:
                log.write("COMMAND " + safe_command + "\nEXIT 124 TIMEOUT\n")
            raise CommandFailure("Docker command timeout; see protected execution.log", 124)
        except BaseException:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
            with (self.report / "execution.log").open("a") as log:
                log.write("COMMAND " + safe_command + "\nCANCELLED by safety gate or interruption\n")
            raise
        # SQL output can contain private identities. Never log stdout or credentials.
        with (self.report / "execution.log").open("a") as log:
            log.write("COMMAND " + safe_command + "\nEXIT " + str(process.returncode) + "\n")
            # Restore errors may include COPY row contents. Keep only sanitized
            # exit metadata; raw data/credentials must not enter reports.
            if stderr:
                log.write("STDERR present (body omitted for data privacy)\n")
        if process.returncode:
            raise CommandFailure("Docker command failed; see protected execution.log", process.returncode)
        return stdout

    def json(self, args):
        return json.loads(self.run(args))


def staging_state(commands):
    result = {}
    for name in STAGING:
        model = commands.json(["inspect", name, "--format", '{{json .State}}'])
        require(model["Running"] and model.get("Health", {}).get("Status") == "healthy" and not model["OOMKilled"], "Existing staging is not healthy; abort")
        result[name] = commands.json(["inspect", name, "--format",
            '{"id":"{{.Id}}","restarts":{{.RestartCount}},"mounts":{{json .Mounts}},"ports":{{json .NetworkSettings.Ports}}}'])
    return result


def snapshot_output(data):
    lines = [line for line in data.decode().splitlines() if line.startswith("{")]
    require(len(lines) == 1, "Expected exactly one read-only JSON snapshot")
    return json.loads(lines[0])


def wait_for_postgres(commands, target, inspect_target, monitor):
    for _ in range(60):
        monitor.sample()
        state = inspect_target()["State"]
        require(state["Running"] and not state["OOMKilled"], "Temporary target exited/OOM")
        try:
            # The entrypoint's temporary initialization server has no TCP
            # listener. Socket readiness alone can accept it prematurely.
            commands.run(["exec", target, "sh", "-c",
                "pg_isready -h 127.0.0.1 -t 2 -U postgres -d restore_test; code=$?; "
                "case $code in 0) exit 0;; 1) exit 11;; 2) exit 12;; *) exit 13;; esac"])
            return
        except CommandFailure as error:
            # Docker exec errors often also return 1. Only the controlled
            # wrapper's 11/12 codes identify pg_isready's normal retry states.
            if error.code not in {11, 12}:
                raise
            time.sleep(1)
    raise ValueError("Temporary PostgreSQL readiness timeout")


def memory_peak(commands, target):
    raw = commands.run(["exec", target, "sh", "-ec",
        "if [ -r /sys/fs/cgroup/memory.peak ]; then cat /sys/fs/cgroup/memory.peak; "
        "elif [ -r /sys/fs/cgroup/memory/memory.max_usage_in_bytes ]; then "
        "cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes; else printf unavailable; fi"]).decode().strip()
    return {"bytes": int(raw), "source": "container cgroup peak"} if raw.isdigit() else {
        "bytes": None, "source": "UNAVAILABLE; sampled values are not an exact peak"}


def execute(args, report, commands):
    result = {"status": "FAIL", "checks": [], "restore_success": False, "data_consistent": False,
              "containers_stopped": True, "existing_services_unchanged": "NOT TESTED",
              "report_directory": str(report), "volumes_deleted": False}
    result["impact_check_scope"] = "Periodic RAM/disk/Swap/load/stats and staging health/state; not browser latency monitoring"
    target = None
    verified = False
    before = None
    name = "heshan-restore-test-" + secrets.token_hex(12)
    volume_name = "heshan-restore-data-" + secrets.token_hex(12)
    volume_token = secrets.token_hex(32)
    volume = None
    monitor = None
    started_at = time.monotonic()
    result["planned_volume_name"] = volume_name

    def check(label, action):
        try:
            output = action()
            result["checks"].append({"name": label, "status": "PASS", "exit_code": 0})
            print("PASS: " + label, flush=True)
            return output
        except Exception as error:
            result["checks"].append({"name": label, "status": "FAIL", "exit_code": getattr(error, "code", 1),
                                     "reason": str(error) if isinstance(error, ValueError) else type(error).__name__})
            raise

    def inspect_target():
        live_volume = commands.json(["volume", "inspect", volume_name])[0]
        validate_volume(live_volume, volume_name, name, volume_token, existing_names, forbidden_sources)
        require(live_volume["Mountpoint"] == volume["Mountpoint"], "Volume data path changed")
        model = commands.json(["inspect", target])[0]
        validate_target(model, target, name, volume)
        return model

    def psql(sql):
        inspect_target()
        return commands.run(["exec", "-i", target, "psql", "-X", "-U", "postgres", "-d", "restore_test",
                             "-v", "ON_ERROR_STOP=1", "-At"], data=sql.encode())

    try:
        backup = private_file(args.backup)
        require(backup.parent == BACKUP_DIR and not BACKUP_DIR.is_symlink(), "Only protected Staging backups are allowed")
        reference = json.loads(private_file(args.reference).read_text())
        checksum = private_file(str(backup) + ".sha256").read_text().strip()
        sha = digest(backup)
        require(backup.stat().st_size > 0 and backup.stat().st_size <= 128 * 1024**2
                and checksum == sha + "  " + str(backup), "Backup size/checksum/path mismatch")
        require(reference.get("format_version") == 1 and reference.get("backup_sha256") == sha
                and reference.get("source_project") == "heshan-staging"
                and reference.get("source_database") == "heshan_staging", "Reference is not bound to this Staging backup")
        expected = reference["snapshot"]
        check("Bound backup and owner/roles/Flyway reference", lambda: validate_snapshot(expected, args.expected_owner_id, args.expected_owner_username, args.expected_migration_version))
        result["resources_before"] = check("RAM/disk preflight", resources)
        before = check("Existing staging baseline (read-only)", lambda: staging_state(commands))
        existing_names = set(commands.run(["volume", "ls", "--format", "{{.Name}}"]).decode().splitlines())
        forbidden_sources = {mount["Source"] for item in before.values() for mount in item.get("mounts", []) if mount.get("Source")}
        require(volume_name not in existing_names, "Random volume name already exists; no reuse allowed")
        image = commands.json(["image", "inspect", "postgres:16-bookworm"])[0]
        require(image["Os"] == "linux" and image["Architecture"] == "amd64"
                and re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"]), "Preloaded Linux AMD64 immutable PostgreSQL image required")
        result["volume_creation_attempted"] = True
        check("Create NEW dedicated volume", lambda: commands.run([
            "volume", "create", "--driver", "local", "--label", "net.heshan.restore-test=" + name,
            "--label", "net.heshan.restore-token=" + volume_token, volume_name]))
        volume = commands.json(["volume", "inspect", volume_name])[0]
        check("Verify fresh volume ownership/no options/no existing-data alias", lambda: validate_volume(
            volume, volume_name, name, volume_token, existing_names, forbidden_sources))
        result["target_volume_name"] = volume_name
        result["target_volume_retained"] = True
        check("Data-volume filesystem resource gate", lambda: resources(volume["Mountpoint"]))
        # A secret ownership label detects an idempotent volume-create race;
        # Docker container create itself refuses same-name container reuse.
        target = check("Create NEW isolated target", lambda: commands.run([
            "create", "--pull=never", "--name", name, "--label", "net.heshan.restore-test=" + name,
            "--network", "none", "--cgroupns", "private", "--read-only", "--security-opt", "no-new-privileges:true",
            "--memory", "384m", "--memory-swap", "384m", "--cpus", "0.25", "--pids-limit", "64",
            "--mount", "type=volume,src=" + volume_name + ",dst=/var/lib/postgresql/data,volume-nocopy",
            "--tmpfs", "/var/run/postgresql:rw,size=8m,mode=3775",
            "--tmpfs", "/tmp:rw,size=16m,mode=1777", "--env", "POSTGRES_PASSWORD",
            "--env", "POSTGRES_DB=restore_test", image["Id"],
            "postgres", "-c", "shared_buffers=32MB", "-c", "work_mem=1MB", "-c", "max_connections=5",
            "-c", "log_statement=none", "-c", "log_min_error_statement=panic"]).decode().strip())
        require(re.fullmatch(r"[0-9a-f]{64}", target), "Invalid new target ID")
        require(all(item["id"] != target for item in before.values()), "Existing staging container cannot be a restore target")
        check("Only new dedicated volume/no bind/network/port target", inspect_target)
        verified = True
        result["target_container_id"] = target
        result["target_container_name"] = name
        commands.run(["start", target])
        result["containers_stopped"] = False
        monitor = ResourceMonitor(report, commands, target, volume["Mountpoint"], before, inspect_target)
        commands.monitor = monitor
        monitor.sample(force=True)
        check("Final PostgreSQL TCP readiness", lambda: wait_for_postgres(commands, target, inspect_target, monitor))
        require(160000 <= int(psql("SHOW server_version_num;\n").strip()) < 170000, "PostgreSQL 16 required")
        empty_sql = """SELECT
 (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','S','v','m','f'))
 + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%')
 + (SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema') AND nspname NOT LIKE 'pg_%');
"""
        check("Restore database is NEW and empty", lambda: require(psql(empty_sql).strip() == b"0", "Target already has user objects; restore forbidden"))
        frozen = report / "verified-backup.dump"
        shutil.copyfile(backup, frozen)
        require(digest(frozen) == sha, "Backup changed during preparation")
        inspect_target()
        monitor.sample(force=True)
        restore_started = time.monotonic()
        check("Restore into new restore_test only", lambda: commands.run([
            "exec", "-i", target, "pg_restore", "--exit-on-error", "--single-transaction",
            "--no-owner", "--no-acl", "-U", "postgres", "-d", "restore_test"], data=frozen.read_bytes()))
        result["restore_elapsed_seconds"] = round(time.monotonic() - restore_started, 3)
        result["restore_success"] = True
        actual = snapshot_output(psql(SQL.read_text()))
        require(actual["database_name"] == "restore_test", "Unexpected restored database name")
        check("Counts/full-row fingerprints/schema/sequences/roles/founder/Flyway", lambda: compare_snapshot(expected, actual))
        result["schema_validation"] = compare_schema(expected, actual)
        result["data_consistent"] = True
        result["table_counts"] = {key: value["count"] for key, value in actual["tables"].items()}
        result["owner_account_preserved"] = True
        result["owner_is_initialized_founder"] = any(item["user_id"] == args.expected_owner_id for item in actual["founders"])
        result["founder_verification"] = "PASS" if actual["founders"] else "PRESERVED_UNINITIALIZED"
        result["database_login_grants_and_web_permissions"] = "NOT TESTED; dump excludes ACL/ownership"
        require(not inspect_target()["State"]["OOMKilled"], "Target OOM detected")
        monitor.sample(force=True)
        result["container_resources"] = commands.run(["stats", "--no-stream", "--format", "{{json .}}", *STAGING, target]).decode()
        result["resources_after"] = resources()
        result["status"] = "PASS"
    except Exception as error:
        result["reason"] = str(error) if isinstance(error, ValueError) else type(error).__name__
        print("FAIL: " + result["reason"], flush=True)
    finally:
        # Monitoring may fail because resources are low. Cleanup must still be
        # able to stop ONLY the verified temporary container and retain its data.
        commands.monitor = None
        if monitor:
            result["resource_sample_count"] = monitor.samples
        result["total_elapsed_seconds"] = round(time.monotonic() - started_at, 3)
        if target and verified:
            try:
                inspect_target()
                if inspect_target()["State"]["Running"]:
                    try:
                        result["temporary_memory_peak"] = memory_peak(commands, target)
                    except Exception:
                        result["temporary_memory_peak"] = {"bytes": None, "source": "UNAVAILABLE; measurement failed"}
                check("Stop only verified temporary target", lambda: commands.run(["stop", "--time", "20", target]))
                final_state = inspect_target()["State"]
                result["containers_stopped"] = not final_state["Running"]
                result["temporary_container_state"] = {"oom_killed": final_state["OOMKilled"],
                                                         "exit_code": final_state.get("ExitCode", 0)}
                if result["status"] == "PASS":
                    require(not final_state["OOMKilled"] and final_state.get("ExitCode", 0) == 0, "Temporary target exited abnormally")
                # Persist no raw PostgreSQL messages: they can contain user data.
                messages = commands.run(["logs", "--tail", "200", target]).decode(errors="replace")
                (report / "postgres-log-summary.json").write_text(json.dumps({
                    "stdout_lines": len(messages.splitlines()),
                    "error_lines": sum(bool(re.search(r"\b(ERROR|FATAL|PANIC)\b", line)) for line in messages.splitlines()),
                    "raw_messages_omitted": True}) + "\n")
            except Exception:
                result["containers_stopped"] = False
                result["status"] = "FAIL"
                result.setdefault("reason", "Temporary target stop/log verification failed; manual review required")
        elif target:
            result["status"] = "FAIL"
            result["containers_stopped"] = False
            result["unverified_target_retained"] = True
        if before is not None:
            try:
                after = staging_state(commands)
                check("Existing staging remains healthy and unchanged", lambda: require(before == after, "Existing staging identity/mount/ports/restarts changed"))
                result["existing_services_unchanged"] = True
            except Exception:
                result["existing_services_unchanged"] = False
                result["status"] = "FAIL"
                result.setdefault("reason", "Existing staging health/state changed; review without restarting existing services")
        if not result["containers_stopped"]:
            result["status"] = "FAIL"
        result["exit_code"] = 0 if result["status"] == "PASS" else 1
        (report / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print("Final status: " + result["status"] + "\nAbsolute report directory: " + str(report), flush=True)
    return 0 if result["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--expected-owner-id", type=int, required=True)
    parser.add_argument("--expected-owner-username", required=True)
    parser.add_argument("--expected-migration-version", default="1")
    parser.add_argument("--execute-isolated-restore", action="store_true")
    args = parser.parse_args()
    if not (sys.platform == "linux" and os.geteuid() == 0 and args.execute_isolated_restore):
        parser.error("Linux, interactive sudo and explicit restore approval required")
    if not (args.expected_owner_id > 0 and re.fullmatch(r"[A-Za-z0-9_-]{3,50}", args.expected_owner_username)):
        parser.error("Confirm owner ID and username explicitly")
    os.umask(0o077)
    lock_fd = os.open("/var/tmp/heshan-isolated-restore.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    info = os.fstat(lock_fd)
    require(info.st_uid == 0 and stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_nlink == 1, "Unsafe restore lock file")
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    def interrupted(signum, frame):
        raise InterruptedError("Interrupted by signal")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    report = Path(tempfile.mkdtemp(prefix="heshan-restore-report-", dir="/var/tmp"))
    return execute(args, report, Commands(report))


if __name__ == "__main__":
    raise SystemExit(main())
