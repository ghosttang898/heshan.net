#!/usr/bin/env python3
"""Explicitly approved backup, Backend restart, then DB restart; never recreate."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time

IDS = {
    "heshan-staging-db-1": "6e806dc8ec333d7acc1055975c8096bf1f7f1dea10366091c7fcdb38c980c938",
    "heshan-staging-backend-1": "f1c8c270b1e985afe1943b9fc020757ebef80301e8202d892c6a019e9e993fca",
    "heshan-staging-web-1": "ea92a09e020a8e685aef83eaf1ea93a3de22d3b64b984e96be069ae5a57453cd",
}
DB, BACKEND, WEB = IDS
PINS = {
    "isolated-postgresql-restore.py": "319b069765d89c3abbb3b488d361c14fa137adc15435c6b25ff52e68acc81d7c",
    "restore-reference.sql": "d24b8d898d197a5dff8b80992704267763655bddd412bbb411eadb7e38f87001",
    "staging-preupdate-backup.sh": "e698c1db31ad5d5845ee487c8373d1194f12c24084e93caa19f28672a820a9b6",
}
OVERLAY = Path("/etc/heshan-staging/web-ingress.override.yml")
OVERLAY_SHA = "a6f5ee400296d5629e049e001253bd2f51af94536482e4f6bca1f93a75cf051e"
FORMAT = ('{"id":"{{.Id}}","image_id":"{{.Image}}",'
          '"project":"{{index .Config.Labels "com.docker.compose.project"}}",'
          '"files":"{{index .Config.Labels "com.docker.compose.project.config_files"}}",'
          '"running":{{.State.Running}},"oom":{{.State.OOMKilled}},'
          '"health":"{{if .State.Health}}{{.State.Health.Status}}{{end}}",'
          '"started":"{{.State.StartedAt}}","restarts":{{.RestartCount}},'
          '"mounts":{{json .Mounts}},"bindings":{{json .HostConfig.PortBindings}},'
          '"memory":{{.HostConfig.Memory}},"memory_swap":{{.HostConfig.MemorySwap}},'
          '"cpus":{{.HostConfig.NanoCpus}},"policy":"{{.HostConfig.RestartPolicy.Name}}",'
          '"networks":{{json .NetworkSettings.Networks}},"ports":{{json .NetworkSettings.Ports}}}')
STABLE = ("id", "image_id", "project", "files", "mounts", "bindings", "memory", "memory_swap", "cpus", "policy")


class Runtime:
    def __init__(self, core, report):
        self.core, self.report = core, report
        self.before = None
        self.active = set()
        self.in_sample = False
        self.last_sample = 0
        self.swap_baseline = None
        self.env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/root",
                    "DOCKER_HOST": "unix:///var/run/docker.sock"}

    def run(self, args, data=None, timeout=40):
        self.sample()
        process = subprocess.Popen(args, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env)
        deadline = time.monotonic() + timeout
        first = True
        try:
            while True:
                try:
                    output, error = process.communicate(data if first else None, timeout=2)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    self.core.require(time.monotonic() < deadline, "Command timeout; no automatic retry")
                    self.sample()
            with (self.report / "execution.log").open("a") as stream:
                stream.write("COMMAND " + " ".join(args) + "\nEXIT " + str(process.returncode) + "\n")
            if args[0] == "bash":
                (self.report / "backup-command-output.txt").write_bytes(output)
            self.core.require(process.returncode == 0, "Command failed (exit " + str(process.returncode) + "); output withheld")
            return output
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
                with (self.report / "execution.log").open("a") as stream:
                    stream.write("COMMAND cancelled by safety gate/timeout; server may have accepted restart\n")

    def inspect(self, name):
        model = json.loads(self.run(["docker", "inspect", IDS[name], "--format", FORMAT]))
        # A restart may replace Docker endpoint IDs without changing attachment/IP.
        model["networks"] = {network: {key: value.get(key) for key in
            ("NetworkID", "IPAddress", "IPPrefixLen", "GlobalIPv6Address", "GlobalIPv6PrefixLen", "IPAMConfig")}
            for network, value in model["networks"].items()}
        return model

    def sample(self, force=False):
        if self.in_sample or (not force and time.monotonic() - self.last_sample < 2):
            return
        self.in_sample = True
        self.last_sample = time.monotonic()
        entry = {"unix_time": time.time(), "phase_allowed_transitions": sorted(self.active), "status": "FAIL"}
        try:
            resources = self.core.resources("/var/lib/docker/volumes/heshan-staging_staging_data/_data")
            self.core.resources("/var/backups/heshan-staging")
            if self.swap_baseline is not None:
                self.core.require(resources["host_swap_used_mib"] <= self.swap_baseline + 128,
                                  "Swap grew more than 128 MiB; stop advancement")
            entry["host"] = resources
            if self.before:
                entry["states"] = {}
                for name in IDS:
                    current = self.inspect(name)
                    validate_state(self.core, name, current, self.before[name], self.active)
                    entry["states"][name] = {key: current[key] for key in ("health", "running", "oom", "restarts", "started")}
                stats = self.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *IDS.values()])
                entry["stats"] = [json.loads(line) for line in stats.decode().splitlines() if line]
            entry["status"] = "PASS"
        except Exception as error:
            entry["reason"] = str(error) if isinstance(error, ValueError) else type(error).__name__
            raise
        finally:
            with (self.report / "resources.jsonl").open("a") as stream:
                stream.write(json.dumps(entry) + "\n")
            self.in_sample = False

    def snapshot(self):
        return self.core.snapshot_output(self.run(["docker", "exec", "-i", IDS[DB], "psql", "-X", "-qAt",
            "-U", "postgres", "-d", "heshan_staging", "-v", "ON_ERROR_STOP=1"], self.core.SQL.read_bytes()))

    def https(self):
        for route in ("/api/health", "/", "/chat", "/find", "/login", "/register"):
            self.run(["curl", "--fail", "--silent", "--show-error", "--connect-timeout", "5", "--max-time", "15",
                      "--cacert", "/etc/heshan-staging/tls/rootCA.pem", "-o", "/dev/null", "https://localhost:18443" + route])


def validate_state(core, name, current, before, active):
    core.require(current["id"] == IDS[name] and current["project"] == "heshan-staging", "Container identity changed")
    core.require(all(current[key] == before[key] for key in STABLE), "Image/mount/limits/Compose identity changed")
    core.require(not current["oom"] and current["restarts"] == before["restarts"], "OOM or unexpected automatic restart")
    if name not in active:
        core.require(current["running"] and current["health"] == "healthy", "Unrelated service unhealthy")
        core.require(current["networks"] == before["networks"] and current["ports"] == before["ports"], "Network or ingress changed")


def wait_healthy(runtime, names, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        runtime.sample(force=True)
        states = [runtime.inspect(name) for name in names]
        if all(s["running"] and s["health"] == "healthy" for s in states):
            return
        time.sleep(2)
    raise ValueError("Health recovery timeout; do not retry/recreate automatically")


def execute(core, report):
    started = time.monotonic()
    runtime = Runtime(core, report)
    result = {"status": "FAIL", "checks": [], "restarts_requested": [], "database_rebuilt": False,
              "database_restored": False, "founder_initialized": False, "report_directory": str(report)}
    def check(label, action):
        try:
            output = action()
            result["checks"].append({"name": label, "status": "PASS", "exit_code": 0})
            print("PASS: " + label, flush=True)
            return output
        except Exception as error:
            result["checks"].append({"name": label, "status": "FAIL", "exit_code": 1,
                                     "reason": str(error) if isinstance(error, ValueError) else type(error).__name__})
            raise
    try:
        result["resources_before"] = core.resources()
        runtime.swap_baseline = result["resources_before"]["host_swap_used_mib"]
        before = {name: runtime.inspect(name) for name in IDS}
        def preflight():
            for name, model in before.items():
                validate_state(core, name, model, model, set())
                core.require(model["restarts"] == 0 and model["policy"] == "unless-stopped", "Unexpected restart policy/count")
            for name, memory, cpu in ((DB, 384, 350000000), (BACKEND, 768, 600000000), (WEB, 64, 100000000)):
                core.require(before[name]["memory"] == memory * 1024**2 and before[name]["cpus"] == cpu,
                             "Approved memory/CPU limits changed")
            core.require(before[WEB]["ports"].get("8443/tcp") == [{"HostIp": "127.0.0.1", "HostPort": "18443"}]
                         and not before[DB]["ports"].get("5432/tcp") and not before[BACKEND]["ports"].get("8080/tcp"), "Port exposure changed")
            mount = [m for m in before[DB]["mounts"] if m["Destination"] == "/var/lib/postgresql/data"]
            core.require(len(mount) == 1 and mount[0].get("Name") == "heshan-staging_staging_data"
                         and mount[0]["Type"] == "volume" and mount[0]["RW"] is True
                         and mount[0]["Source"] == "/var/lib/docker/volumes/heshan-staging_staging_data/_data", "Source volume changed")
            core.require(core.digest(core.private_file(OVERLAY)) == OVERLAY_SHA, "Overlay changed")
            for name in (BACKEND, WEB):
                core.require(str(OVERLAY) in before[name]["files"].split(","), "Active overlay missing")
            runtime.https()
        check("Resources, identities, persistent volume, limits, overlay and HTTPS", preflight)
        runtime.before = before
        baseline = check("Read-only full data/owner/schema baseline", runtime.snapshot)
        core.validate_snapshot(baseline, 1, "ghost", "1")
        (report / "baseline-before.json").write_text(json.dumps(baseline))
        output = check("Fresh logical backup", lambda: runtime.run(
            ["bash", str(Path(__file__).with_name("staging-preupdate-backup.sh")), "--execute-backup"], timeout=240))
        paths = [line[8:] for line in output.decode().splitlines() if line.startswith("Report: ")]
        core.require(len(paths) == 1, "Backup report missing")
        backup_report = json.loads(core.private_file(Path(paths[0]) / "result.json").read_text())
        core.require(backup_report["status"] == "PASS" and backup_report["exit_code"] == 0
                     and backup_report.get("containers_modified") is False
                     and backup_report.get("database_restored") is False, "Backup-only report failed")
        backup = core.private_file(Path(backup_report["backup"]))
        core.require(backup.parent == core.BACKUP_DIR and backup.stat().st_size > 0, "Wrong/empty backup")
        sha = core.digest(backup)
        check("Fresh backup SHA256 and idle full baseline", lambda: (
            core.require(core.private_file(str(backup) + ".sha256").read_text().strip() == sha + "  " + str(backup), "Backup checksum mismatch"),
            core.compare_snapshot(baseline, runtime.snapshot())))
        result["backup"] = {"path": str(backup), "sha256": sha, "report_directory": paths[0]}
        for name in (BACKEND, DB):
            check("Pre-restart baseline: " + name, lambda: core.compare_snapshot(baseline, runtime.snapshot()))
            runtime.sample(force=True)
            runtime.active = {BACKEND} if name == BACKEND else {DB, BACKEND}
            result["restarts_requested"].append(name)
            # Bind each action to the captured full ID, never a changing service name.
            check("Restart only " + name, lambda: runtime.run(["docker", "restart", "--time", "60", IDS[name]], timeout=100))
            if name == DB:
                check("PostgreSQL health after restart", lambda: wait_healthy(runtime, [DB], 180))
            check("Backend connectivity recovery", lambda: wait_healthy(runtime, [BACKEND], 240))
            runtime.active = set()
            check("All three healthy, immutable mounts/images/networks", lambda: runtime.sample(force=True))
            check("Verified HTTPS/API/SPA after " + name, runtime.https)
            actual = runtime.snapshot()
            check("Full persistence/roles/founder/Flyway after " + name, lambda: (
                core.compare_snapshot(baseline, actual), core.validate_snapshot(actual, 1, "ghost", "1")))
            (report / ("baseline-after-backend.json" if name == BACKEND else "baseline-after-db.json")).write_text(json.dumps(actual))
            core.require(runtime.inspect(name)["started"] != before[name]["started"], "Restart was not observed")
        result["table_counts"] = {key: value["count"] for key, value in baseline["tables"].items()}
        result["ghost_user_preserved"] = True
        result["founder_uninitialized"] = True
        result["resources_after"] = core.resources()
        result["status"] = "PASS"
    except Exception as error:
        result["reason"] = str(error) if isinstance(error, ValueError) else type(error).__name__
    finally:
        runtime.active = set()
        try:
            core.require(runtime.before is not None, "Preflight incomplete; final health not established")
            runtime.sample(force=True)
            result["all_three_healthy_final"] = True
        except Exception:
            result["all_three_healthy_final"] = False
            result["status"] = "FAIL"
        result["automatic_recovery_actions"] = False
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        samples_file = report / "resources.jsonl"
        if samples_file.exists():
            try:
                samples = [json.loads(line) for line in samples_file.read_text().splitlines()]
                good = [item for item in samples if item.get("status") == "PASS"]
                peaks = {}
                for item in good:
                    for container in item.get("stats", []):
                        name = container.get("Name", "unknown")
                        value = float(container["CPUPerc"].rstrip("%"))
                        peaks[name] = max(peaks.get(name, 0), value)
                result["sampled_resources"] = {
                    "sample_count": len(samples), "cpu_percent_sampled_max": peaks,
                    "available_ram_mib_sampled_min": min(item["host"]["available_ram_mib"] for item in good),
                    "swap_used_mib_sampled_max": max(item["host"]["host_swap_used_mib"] for item in good),
                    "free_disk_bytes_sampled_min": min(item["host"]["free_disk_bytes"] for item in good),
                    "instantaneous_peaks_not_guaranteed": True}
            except (KeyError, ValueError):
                result["sampled_resources"] = {"summary": "UNAVAILABLE; inspect protected resources.jsonl"}
        if (report / "backup-command-output.txt").exists():
            result["backup_command_output_file"] = str(report / "backup-command-output.txt")
        (report / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)
        print("Absolute report directory: " + str(report), flush=True)
    return 0 if result["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved-restarts", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0 or not args.execute_approved_restarts:
        parser.error("Linux, interactive sudo and explicit restart approval required")
    os.umask(0o077)
    root = Path(__file__).resolve().parent
    for name, sha in PINS.items():
        path = root / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Unsafe pinned file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError("Pinned file mismatch")
    lock = os.open("/var/tmp/heshan-isolated-restore.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    info = os.fstat(lock)
    if not (stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1):
        raise ValueError("Unsafe exclusive lock")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    def interrupt(signum, frame):
        raise InterruptedError("Interrupted; preserve scene and inspect, do not automatically retry")
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGHUP, interrupt)
    spec = importlib.util.spec_from_file_location("restore_core", root / "isolated-postgresql-restore.py")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    report = Path(tempfile.mkdtemp(prefix="heshan-persistence-report-", dir="/var/tmp"))
    return execute(core, report)


if __name__ == "__main__":
    raise SystemExit(main())
