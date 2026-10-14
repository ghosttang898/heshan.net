#!/usr/bin/env python3
"""Owner-run app-only update for the explicitly approved staging release."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

REVISION = "2e176e0de59784297e3253c97806db09989dc7fe"
BASE = "eca42d278f39c64415f9946fec9f51aa6c113459"
ARCHIVE_SHA = "1cf827d16dbb46d9a48da4562ba763b1ed5220681d71117042bf86a28475797c"
IMAGE_ID = "sha256:7a5577bcb8e21070086d1c84131bc508525c579f2f9936c1ca57f1b02ad4b0b2"
OVERLAY_SHA = "a6f5ee400296d5629e049e001253bd2f51af94536482e4f6bca1f93a75cf051e"
ENV = Path("/etc/heshan-staging/staging.env")
OVERLAY = ENV.parent / "web-ingress.override.yml"
RELEASES = Path("/srv/heshan-staging/releases")
CHANGED_KEYS = {"STAGING_BACKEND_REVISION", "STAGING_BACKEND_IMAGE",
                "STAGING_FRONTEND_REVISION", "STAGING_STATIC_DIR"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def private(path, directory=False):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), "Aliased private path")
    info = path.stat()
    require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600), "Private ownership/mode mismatch")
    require(path.is_dir() if directory else path.is_file(), "Invalid private file type")
    return path


def backup_gate(report):
    report = private(report, directory=True)
    result = json.loads(private(report / "result.json").read_text())
    require(result.get("status") == "PASS" and result.get("exit_code") == 0
            and result.get("containers_modified") is False and result.get("database_restored") is False
            and result.get("report_directory") == str(report), "Backup report is not a successful backup-only run")
    dump = private(result["backup"])
    private(dump.parent, directory=True)
    require(dump.parent == Path("/var/backups/heshan-staging") and dump.stat().st_size > 0, "Unexpected backup path")
    checksum = private(str(dump) + ".sha256").read_text().strip()
    require(checksum == digest(dump) + "  " + str(dump), "Backup checksum mismatch")
    before = private(report / "baseline-before.txt").read_bytes()
    require(before == private(report / "baseline-after.txt").read_bytes(), "Backup has concurrent writes")
    require(private(report / "backup-toc.txt").stat().st_size > 0, "Missing archive listing")
    return before


def unpack(archive, destination):
    require(digest(archive) == ARCHIVE_SHA, "Approved bundle checksum mismatch")
    with tarfile.open(archive, "r:gz") as tar:
        files = {}
        for member in tar.getmembers():
            name = member.name.removeprefix("./")
            path = PurePosixPath(name)
            require(not path.is_absolute() and ".." not in path.parts and not member.issym()
                    and not member.islnk() and (member.isfile() or member.isdir()), "Unsafe bundle entry")
            # macOS tar adds AppleDouble metadata; never install those files.
            if path.name.startswith("._"):
                continue
            if member.isdir():
                continue
            require(name not in files and member.size <= 400 * 1024 * 1024, "Duplicate/oversized bundle entry")
            files[name] = member
        require("SHA256SUMS" in files, "Bundle manifest missing")
        manifest = tar.extractfile(files["SHA256SUMS"]).read().decode()
        expected = {}
        for line in manifest.splitlines():
            sha, name = line.split("  ", 1)
            require(name not in expected and len(sha) == 64, "Invalid bundle manifest")
            expected[name] = sha
        require(set(files) == set(expected) | {"SHA256SUMS"}, "Unexpected bundle files")
        for name, member in files.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            if name != "SHA256SUMS":
                require(digest(target) == expected[name], "Bundle member checksum mismatch")
    metadata = json.loads((destination / "UPDATE_METADATA.json").read_text())
    require(metadata["revision"] == REVISION and metadata["base_revision"] == BASE
            and metadata["migrations_changed"] is False and metadata["database_rebuild"] is False
            and metadata["founder_initialization"] is False, "Unexpected update scope")
    require((destination / "SOURCE_REVISION").read_text().strip() == REVISION, "Source revision mismatch")


def updated_values(old):
    require(old["STAGING_BACKEND_REVISION"] == BASE, "Current release is not the approved base")
    new = {**old, "STAGING_BACKEND_REVISION": REVISION, "STAGING_BACKEND_IMAGE": "heshan-backend:" + REVISION,
           "STAGING_FRONTEND_REVISION": REVISION, "STAGING_STATIC_DIR": str(RELEASES / REVISION / "frontend")}
    require({key for key in old if old[key] != new[key]} == CHANGED_KEYS, "Unexpected environment changes")
    return new


def atomic_env(content):
    descriptor, name = tempfile.mkstemp(prefix=".staging-update-", dir=ENV.parent)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(name, ENV)


def update_apps(docker):
    for service in ("backend", "web"):
        docker.compose("up", "-d", "--no-deps", "--force-recreate", "--wait", "--wait-timeout", "240", service)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--backup-report", type=Path, required=True)
    parser.add_argument("--execute-update", action="store_true")
    args = parser.parse_args()
    require(os.geteuid() == 0 and args.execute_update, "Use interactive sudo and explicit --execute-update")
    require(sys.platform == "linux", "This execution command is Linux-only")
    os.umask(0o077)
    os.environ.pop("DOCKER_CONTEXT", None)
    os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    private(ENV.parent, directory=True)
    lock = (ENV.parent / ".app-update.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    report = Path(tempfile.mkdtemp(prefix="heshan-staging-app-update-", dir="/var/tmp"))
    result = {"status": "FAIL", "checks": [], "database_rebuilt": False, "founder_initialized": False,
              "persistence_restart": "NOT TESTED", "restore_drill": "NOT TESTED", "report_directory": str(report)}
    control = None
    docker = None
    previous = None
    env_changed = False

    def log(message):
        with (report / "execution.log").open("a") as stream:
            stream.write(message + "\n")

    def check(name, function):
        try:
            value = function()
            result["checks"].append({"name": name, "status": "PASS", "exit_code": 0})
            log("PASS: " + name)
            print("PASS: " + name, flush=True)
            return value
        except Exception as error:
            result["checks"].append({"name": name, "status": "FAIL", "exit_code": 1})
            log("FAIL: " + name)
            raise error

    try:
        baseline = check("Backup report and checksum", lambda: backup_gate(args.backup_report))
        require(args.bundle.is_file() and not args.bundle.is_symlink(), "Bundle must be a regular file")
        snapshot = report / "approved-bundle.tar.gz"
        shutil.copyfile(args.bundle, snapshot)
        bundle = report / "bundle"
        bundle.mkdir()
        check("Pinned release bundle", lambda: unpack(snapshot, bundle))
        spec = importlib.util.spec_from_file_location("staging_update_control", bundle / "docs/scripts/staging.py")
        control = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(control)

        class LoggedDocker(control.Docker):
            def run(self, commands, data=None, output=None):
                process = subprocess.run(commands, input=data, stdout=output or subprocess.PIPE,
                                         stderr=subprocess.PIPE, env=self.environment, timeout=600)
                log(control.redact("COMMAND: " + " ".join(commands) + "\nEXIT: " + str(process.returncode)
                                   + "\n" + (process.stdout or b"").decode(errors="replace")
                                   + process.stderr.decode(errors="replace"), self.values))
                if process.returncode:
                    raise RuntimeError("Command failed (exit " + str(process.returncode) + "); consult protected execution.log")
                return process.stdout

        control.Docker = LoggedDocker
        old = control.read_env(ENV)
        new = updated_values(old)
        private(OVERLAY)
        require(digest(OVERLAY) == OVERLAY_SHA, "Ingress overlay changed")
        previous = ENV.read_bytes()
        (report / "previous.env").write_bytes(previous)
        control.COMPOSE = RELEASES / BASE / "deploy/staging/compose.yml"
        docker = control.Docker(old, ENV, OVERLAY)

        def inspect(service):
            return json.loads(docker.run(["docker", "inspect", "heshan-staging-" + service + "-1"]))[0]

        def healthy():
            for service in ("db", "backend", "web"):
                item = inspect(service)
                require(item["Config"]["Labels"]["com.docker.compose.project"] == control.PROJECT
                        and item["State"].get("Health", {}).get("Status") == "healthy"
                        and not item["State"]["OOMKilled"] and item["RestartCount"] == 0, "Staging container unhealthy/OOM/restarted")
                ports = item["NetworkSettings"]["Ports"]
                bindings = {key: value for key, value in ports.items() if value}
                require(bindings == ({"8443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18443"}]} if service == "web" else {}), "Unexpected published port")

        def data_baseline():
            # Reuse the exact read-only SQL used by the approved backup script.
            source = (bundle / "docs/scripts/staging-preupdate-backup.sh").read_text()
            sql = source.split("<<'SQL'\n", 1)[1].split("\nSQL\n", 1)[0] + "\n"
            return docker.run(["docker", "exec", "-i", "heshan-staging-db-1", "psql", "-X", "-U", "postgres", "-d", "heshan_staging", "-v", "ON_ERROR_STOP=1", "-At"], data=sql.encode())

        check("Current containers and loopback ingress", healthy)
        db = inspect("db")
        require(any(mount.get("Name") == "heshan-staging_staging_data" for mount in db["Mounts"]), "Unexpected database volume")
        require(data_baseline() == baseline, "Data changed after backup; take a fresh backup while idle")
        memory = next(int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))
        require(memory >= 512 * 1024 and shutil.disk_usage(RELEASES).free >= 4 * 1024**3, "Insufficient RAM/disk for in-place update")
        release = RELEASES / REVISION
        require(RELEASES.resolve() == RELEASES and RELEASES.stat().st_uid == 0, "Unsafe releases directory")
        require(not release.exists() and not release.is_symlink(), "Release directory already exists; no overwrite allowed")
        release.mkdir(mode=0o700)
        for folder in ("frontend", "deploy", "docs"):
            shutil.copytree(bundle / folder, release / folder)
            for path in [release / folder, *(release / folder).rglob("*")]:
                path.chmod(0o755 if path.is_dir() else 0o644)
        control.COMPOSE = release / "deploy/staging/compose.yml"
        candidate = control.Docker(new, ENV, OVERLAY)
        check("Permanent ingress Compose and TLS/frontend permissions", lambda: (control.validate_model(json.loads(candidate.compose("config", "--format", "json")), new), control.check_artifacts(new)))
        found = subprocess.run(["docker", "image", "inspect", new["STAGING_BACKEND_IMAGE"]], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=candidate.environment)
        if found.returncode:
            check("Load approved new image", lambda: candidate.run(["docker", "load", "--input", str(bundle / "backend-image.tar")]))
        image = json.loads(candidate.run(["docker", "image", "inspect", new["STAGING_BACKEND_IMAGE"]]))[0]
        require(image["Id"] == IMAGE_ID and image["Architecture"] == "amd64" and image["Os"] == "linux"
                and image["Config"]["User"] == "10001:10001"
                and image["Config"]["Labels"]["org.opencontainers.image.revision"] == REVISION, "Image identity/architecture/security mismatch")
        check("Final pre-change health and unchanged data", healthy)
        require(data_baseline() == baseline and inspect("db")["Id"] == db["Id"], "Data/container changed during preparation; abort update")
        env_changed = True
        atomic_env("".join(key + "=" + value + "\n" for key, value in sorted(new.items())).encode())
        docker = candidate
        check("Recreate Backend/Web only, preserving ingress", lambda: update_apps(docker))
        check("Final health, OOM, restart and port checks", healthy)
        require(inspect("db")["Id"] == db["Id"] and inspect("db")["Mounts"] == db["Mounts"], "Database container/volume changed")
        require(data_baseline() == baseline, "Data baseline changed during update")
        check("Verified HTTPS, API and SPA routes", lambda: docker.run(["python3", str(release / "docs/scripts/staging-http-smoke.py"), "--origin", "https://localhost:18443", "--ca-cert", "/etc/heshan-staging/tls/rootCA.pem"]))
        (report / "resources.txt").write_bytes(docker.run(["free", "-m"]) + docker.run(["df", "-h", "/"])
            + docker.run(["docker", "stats", "--no-stream", "heshan-staging-db-1", "heshan-staging-backend-1", "heshan-staging-web-1"]))
        result["status"] = "PASS"
        result["revision"] = REVISION
    except Exception as error:
        message = str(error)
        if control and docker:
            message = control.redact(message, docker.values)
        result["reason"] = message
        print("FAIL: " + message, flush=True)
        if env_changed:
            try:
                atomic_env(previous)
                rollback = control.Docker(old, ENV, OVERLAY)
                check("Rollback old Backend/Web only; no database restore", lambda: update_apps(rollback))
                docker = rollback
                check("Rollback health and loopback ingress", healthy)
                result["rollback"] = "PASS"
            except Exception:
                result["rollback"] = "FAIL; keep reports and seek manual recovery"
    finally:
        if docker:
            for service in ("db", "backend", "web"):
                try:
                    logs = docker.run(["docker", "logs", "--tail", "300", "heshan-staging-" + service + "-1"])
                    (report / (service + ".log")).write_text(control.redact(logs.decode(errors="replace"), docker.values))
                except Exception:
                    pass
        (report / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        log("FINAL: " + result["status"])
        print("Report: " + str(report), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
