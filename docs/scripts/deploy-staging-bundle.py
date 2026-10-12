#!/usr/bin/env python3
"""Owner-invoked first Staging installation; never reuses existing Staging resources."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from types import SimpleNamespace

PROJECT = "heshan-staging"
SUBNET = ipaddress.ip_network("172.30.20.0/24")


def archive_identities(path, image, revision):
    with tarfile.open(path) as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
        if len(manifest) != 1 or manifest[0].get("RepoTags") != [image]:
            raise ValueError("Image archive must contain only the approved SHA tag")
        config_bytes = archive.extractfile(manifest[0]["Config"]).read()
        config = json.loads(config_bytes)
        if (config.get("os"), config.get("architecture")) != ("linux", "amd64"):
            raise ValueError("Expected AMD64 Linux image")
        if config.get("config", {}).get("Labels", {}).get("org.opencontainers.image.revision") != revision:
            raise ValueError("Image source revision mismatch")
        config_id = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
        identities = {config_id}

        def inspect(descriptor):
            digest = descriptor["digest"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise ValueError("Invalid OCI digest")
            value = archive.extractfile("blobs/sha256/" + digest.split(":")[1]).read()
            if "sha256:" + hashlib.sha256(value).hexdigest() != digest:
                raise ValueError("OCI descriptor checksum mismatch")
            model = json.loads(value)
            valid = model.get("config", {}).get("digest") == config_id
            if "manifests" in model:
                valid = any([inspect(child) for child in model["manifests"]])
            if valid:
                identities.add(digest)
            return valid
        if "index.json" in archive.getnames():
            for descriptor in json.load(archive.extractfile("index.json"))["manifests"]:
                if descriptor.get("annotations", {}).get("io.containerd.image.name") not in (image, "docker.io/library/" + image):
                    raise ValueError("Unexpected OCI image tag")
                if not inspect(descriptor):
                    raise ValueError("OCI index does not reference approved config")
        return identities


def verified_files(bundle):
    entries = {}
    for line in (bundle / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("Invalid checksum manifest")
        digest, name = match.groups()
        parts = Path(name).parts
        if name in entries or name.startswith("/") or ".." in parts:
            raise ValueError("Unsafe or duplicate manifest path")
        allowed = name in {"backend-image.tar", "SOURCE_REVISION", "deploy/postgres-init.sh",
                           "deploy/staging/compose.yml", "deploy/staging/nginx.conf",
                           "docs/scripts/staging.py", "docs/scripts/staging-http-smoke.py",
                           "docs/scripts/deploy-staging-bundle.py", "tls/fullchain.pem", "tls/privkey.pem", "tls/rootCA.pem"}
        if not allowed and not name.startswith("frontend/"):
            raise ValueError("Unexpected bundle file")
        path = bundle / name
        if path.is_symlink() or path.resolve() != path or not path.is_file():
            raise ValueError("Missing or aliased bundle file")
        hash_value = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                hash_value.update(chunk)
        if hash_value.hexdigest() != digest:
            raise ValueError("Bundle checksum mismatch")
        entries[name] = digest
    required = {"backend-image.tar", "SOURCE_REVISION", "deploy/postgres-init.sh", "deploy/staging/compose.yml",
                "deploy/staging/nginx.conf", "docs/scripts/staging.py", "docs/scripts/staging-http-smoke.py",
                "docs/scripts/deploy-staging-bundle.py", "frontend/index.html", "frontend/release.json",
                "tls/fullchain.pem", "tls/privkey.pem", "tls/rootCA.pem"}
    if not required <= entries.keys():
        raise ValueError("Incomplete bundle")
    return entries


def new_directory(path, mode=0o700):
    path.mkdir(mode=mode)
    # mkdir is filtered by the private process umask, including group traversal.
    path.chmod(mode)


def copy_public_assets(bundle, release, entries):
    for name in entries:
        if not name.startswith(("frontend/", "deploy/", "docs/")):
            continue
        target = release / name
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copyfile(bundle / name, target)
        target.chmod(0o644)
    # Only newly copied public directories; never relax the private release root.
    for directory in release.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)


def safe_parent(path):
    if path.exists():
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise ValueError("Existing parent is not a trusted root directory")
    else:
        new_directory(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("Interactive sudo and a full approved SHA are required")
    os.umask(0o077)
    lock = os.open("/run/lock/heshan-staging-deployment.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    bundle = Path(args.bundle).resolve()
    report_dir = Path(tempfile.mkdtemp(prefix="heshan-staging-deploy-", dir="/var/tmp"))
    report = {"revision": args.revision, "project": PROJECT, "status": "RUNNING", "checks": [],
              "samples": [], "services_left_running": False, "report_directory": str(report_dir)}
    hidden = []
    touched = False
    controller = None
    docker = None
    done = threading.Event()
    faults = []

    def clean(value):
        for secret in hidden:
            value = value.replace(secret, "[REDACTED]")
        return re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED-JWT]", value)

    def save():
        (report_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def emit(message):
        message = clean(str(message))
        with (report_dir / "execution.log").open("a") as output:
            output.write(message + "\n")
        print(message, flush=True)

    def run(command, data=None, accepted=(0,), private=False):
        environment = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/root",
                       "DOCKER_HOST": "unix:///var/run/docker.sock"}
        result = subprocess.run(command, input=data, capture_output=True, timeout=600, env=environment)
        if result.returncode not in accepted:
            raise RuntimeError(clean(result.stderr.decode(errors="replace")) or "Command failed")
        if not private and result.stdout:
            emit(result.stdout.decode(errors="replace"))
        return result

    def check(name, action):
        entry = {"name": name, "status": "RUNNING", "exit_code": None}
        report["checks"].append(entry)
        save()
        emit("START: " + name)
        try:
            result = action()
            entry.update(status="PASS", exit_code=0)
            emit("PASS: " + name)
            return result
        except Exception as error:
            entry.update(status="FAIL", exit_code=1, reason=clean(str(error)))
            emit("FAIL: " + name + ": " + entry["reason"])
            raise
        finally:
            save()

    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    def sample():
        ids = run(["docker", "ps", "-a", "-q", "--filter", "label=com.docker.compose.project=" + PROJECT], private=True).stdout.decode().split()
        states = []
        for container in ids:
            state = json.loads(run(["docker", "inspect", "--format",
                '{"name":{{json .Name}},"state":{{json .State}},"restarts":{{.RestartCount}},"ports":{{json .HostConfig.PortBindings}}}',
                container], private=True).stdout)
            states.append(state)
            if state["state"].get("OOMKilled") or state["restarts"] >= 2:
                faults.append("Staging OOM or repeated restart detected")
        memory = Path("/proc/meminfo").read_text()
        available = next(int(line.split()[1]) for line in memory.splitlines() if line.startswith("MemAvailable:"))
        if available < 128 * 1024:
            faults.append("Available memory below 128 MiB")
        statistics = run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids], private=True).stdout.decode() if ids else ""
        report["samples"].append({"time": datetime.now(timezone.utc).isoformat(), "states": states,
                                  "docker_stats": statistics, "meminfo": memory,
                                  "loadavg": Path("/proc/loadavg").read_text(),
                                  "disk": run(["df", "-h", "/", "/var/lib/docker"], private=True).stdout.decode()})
        return states

    def monitor():
        while not done.is_set():
            try:
                sample()
                if faults:
                    docker.compose("stop")
                    return
            except Exception:
                faults.append("Resource monitor failed; cannot verify safety")
                return
            done.wait(5)

    thread = None
    try:
        entries = check("Bundle checksums and whitelist", lambda: verified_files(bundle))
        require((bundle / "SOURCE_REVISION").read_text().strip() == args.revision, "Source SHA mismatch")
        check("Docker inventory", lambda: run(["docker", "ps", "-a", "--format", "{{.Names}} | {{.Status}} | {{.Ports}} "]))
        check("Existing volumes", lambda: run(["docker", "volume", "ls"]))
        require(not run(["docker", "ps", "-q"], private=True).stdout.strip(), "Running Docker services found; approved inventory changed")
        listeners = run(["ss", "-lntH"], private=True).stdout.decode()
        for line in listeners.splitlines():
            fields = line.split()
            if len(fields) >= 4:
                require(fields[3].rsplit(":", 1)[-1] not in {"80", "443", "8080", "5432", "18443"}, "Server port inventory changed; installation paused")
        existing = run(["docker", "ps", "-a", "-q", "--filter", "label=com.docker.compose.project=" + PROJECT], private=True).stdout.strip()
        require(not existing, "Existing Staging containers found; refusing to modify them")
        volumes = run(["docker", "volume", "ls", "--format", "{{.Name}}"], private=True).stdout.decode().split()
        require(PROJECT + "_staging_data" not in volumes, "Existing Staging volume found; first-install refused")
        network_output = run(["docker", "network", "ls", "--format", "json"], private=True).stdout.decode()
        networks = [json.loads(line) for line in network_output.splitlines() if line.strip()]
        require(not any(item["Name"].startswith(PROJECT + "_") for item in networks), "Existing Staging network found")
        available = next(int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))
        require(available >= 1300 * 1024, "Insufficient available RAM; no services started")
        docker_root = run(["docker", "info", "--format", "{{.DockerRootDir}}"], private=True).stdout.decode().strip()
        for location in ("/srv", "/var/tmp", docker_root):
            storage = os.statvfs(location)
            require(storage.f_bavail * storage.f_frsize >= 4 * 1024 ** 3, "Insufficient disk; no services started")
        routes = json.loads(run(["ip", "-j", "-4", "route"], private=True).stdout)
        for route in routes:
            destination = route.get("dst", "default")
            if destination != "default":
                require(not ipaddress.ip_network(destination, strict=False).overlaps(SUBNET), "Staging subnet overlaps host route")
        release = Path("/srv/heshan-staging/releases") / args.revision
        env_dir = Path("/etc/heshan-staging")
        require(not release.exists() and not env_dir.exists(), "Existing release/config found; nothing will be overwritten")
        # Copy verified public assets/scripts into a NEW immutable release directory.
        safe_parent(Path("/srv/heshan-staging"))
        safe_parent(release.parent)
        new_directory(release)
        copy_public_assets(bundle, release, entries)
        new_directory(env_dir)
        new_directory(env_dir / "tls", 0o750)
        os.chown(env_dir / "tls", 0, 101)
        for name, mode in (("fullchain.pem", 0o644), ("privkey.pem", 0o640), ("rootCA.pem", 0o644)):
            shutil.copyfile(bundle / "tls" / name, env_dir / "tls" / name)
            os.chown(env_dir / "tls" / name, 0, 101)
            (env_dir / "tls" / name).chmod(mode)
        spec = importlib.util.spec_from_file_location("staging_control", release / "docs/scripts/staging.py")
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        env_file = env_dir / "staging.env"
        controller.init_env(SimpleNamespace(revision=args.revision, static_dir=str(release / "frontend"),
                                          tls_dir=str(env_dir / "tls"), env_file=str(env_file)))
        values = controller.read_env(env_file)
        hidden.extend(values[key] for key in controller.SECRET_KEYS)
        image = values["STAGING_BACKEND_IMAGE"]
        identities = check("Approved AMD64 image archive", lambda: archive_identities(bundle / "backend-image.tar", image, args.revision))
        inspection = run(["docker", "image", "inspect", "--format", "{{.Id}}", image], accepted=(0, 1), private=True)
        if inspection.returncode == 0:
            require(inspection.stdout.decode().strip() in identities, "Existing SHA tag differs; not overwritten")
        else:
            check("Load new SHA-tagged backend image", lambda: run(["docker", "load", "--input", str(bundle / "backend-image.tar")]))
        for dependency in ("postgres:16-bookworm", "nginx:stable-alpine"):
            inspected = run(["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", dependency], accepted=(0, 1), private=True)
            if inspected.returncode == 1:
                check("Prepare missing official image " + dependency, lambda dependency=dependency: run(["docker", "pull", "--platform", "linux/amd64", dependency]))
            else:
                require(inspected.stdout.decode().strip() == "linux/amd64", "Existing dependency architecture mismatch; not replaced")
        docker = controller.Docker(values, env_file)
        check("Full Staging preflight", lambda: controller.preflight(docker, values))
        touched = True
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        check("Compose healthy startup", lambda: docker.compose("up", "-d", "--wait", "--wait-timeout", "300"))
        require(not faults, "; ".join(faults))
        def sql(query):
            return run(docker.base + ["exec", "-T", "db", "sh", "-ec", 'PGPASSWORD="$APP_DB_PASSWORD"; export PGPASSWORD; exec psql -h 127.0.0.1 -U "$APP_DB_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1'], data=query.encode(), private=True).stdout.decode().strip()
        check("PostgreSQL 16", lambda: require(160000 <= int(sql("SHOW server_version_num;")) < 170000, "Wrong PG version"))
        check("Flyway V1", lambda: require(sql("SELECT count(*) FROM flyway_schema_history WHERE success AND version='1';") == "1", "Flyway V1 not successful"))
        logs = docker.compose("logs", "--no-color", "backend").decode(errors="replace")
        check("Spring Boot 4.1.1 and Hibernate validate startup", lambda: require("(v4.1.1)" in logs and values["STAGING_BACKEND_REVISION"] == args.revision, "Startup version mismatch"))
        check("HTTPS, SPA, registration/login, USER JWT/post/comment/admin denial", lambda: run(["python3", "-I", str(release / "docs/scripts/staging-http-smoke.py"),
            "--origin", "https://localhost:18443", "--ca-cert", str(env_dir / "tls/rootCA.pem"), "--exercise-test-user"]))
        check("No automatic founder or admin creation", lambda: require(sql("SELECT (SELECT count(*) FROM founder_identity)+(SELECT count(*) FROM users WHERE role IN ('ADMIN','SUPER_ADMIN'));") == "0", "Unexpected administrator initialization"))
        emit("Monitoring new Staging for 60 seconds; no existing services will be stopped")
        for _ in range(12):
            if faults:
                raise RuntimeError("; ".join(faults))
            time.sleep(5)
        done.set()
        thread.join(timeout=30)
        states = sample()
        check("Healthy containers, no OOM/restarts or public DB/backend ports", lambda: require(
            len(states) == 3 and all(state["state"].get("Running") and not state["state"].get("OOMKilled") and state["restarts"] == 0
                                    and state["state"].get("Health", {}).get("Status") == "healthy" for state in states)
            and all(not state["ports"] or (state["name"].endswith("-web-1") and state["ports"] == {"8443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18443"}]}) for state in states)
            and not faults, "Health/resource/port validation failed"))
        report.update(status="PASS", services_left_running=True)
    except (Exception, KeyboardInterrupt) as error:
        report.update(status="FAIL", failure_reason=clean(str(error)))
        emit("FAIL: " + report["failure_reason"])
        if touched and docker:
            try:
                docker.compose("stop")
                report["containers_stopped"] = not run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=" + PROJECT], private=True).stdout.strip()
            except Exception:
                report["containers_stopped"] = False
    finally:
        done.set()
        if thread:
            thread.join(timeout=30)
        if docker:
            try:
                (report_dir / "container-logs.log").write_text(clean(docker.compose("logs", "--no-color", "--timestamps").decode(errors="replace")))
            except Exception:
                emit("Container log capture unavailable")
        save()
        emit("Final status: " + report["status"])
        emit("Report: " + str(report_dir / "result.json"))
        emit("Execution log: " + str(report_dir / "execution.log"))
        emit("Staging data/logs/config retained; no existing resource deleted")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
