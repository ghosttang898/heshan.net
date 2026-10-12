#!/usr/bin/env python3
"""Local Docker staging controls. Never SSH, initialize founders or clean resources."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import stat
import subprocess
import sys
from datetime import datetime, timezone
import hashlib
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy/staging/compose.yml"
PROJECT = "heshan-staging"
SUBNET = ipaddress.ip_network("172.30.20.0/24")
KEYS = {"STAGING_BACKEND_REVISION", "STAGING_BACKEND_IMAGE", "STAGING_FRONTEND_REVISION",
        "STAGING_STATIC_DIR", "STAGING_TLS_DIR", "STAGING_DB_NAME", "STAGING_DB_USER",
        "STAGING_DB_PASSWORD", "STAGING_DB_ADMIN_PASSWORD", "STAGING_JWT_SECRET",
        "STAGING_CORS_ALLOWED_ORIGINS"}
SECRET_KEYS = {"STAGING_DB_PASSWORD", "STAGING_DB_ADMIN_PASSWORD", "STAGING_JWT_SECRET"}


def read_env(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("Use an absolute regular private staging env file")
    if stat.S_IMODE(path.stat().st_mode) != 0o600 or path.stat().st_uid != os.geteuid():
        raise ValueError("Env file must be owned by the executing user, mode 0600")
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in KEYS or key in values or not value or any(c in value for c in "\r\n$\"'"):
            raise ValueError("Invalid, duplicate, missing or non-staging env setting")
        values[key] = value
    validate_env(values)
    return values


def validate_env(values):
    if set(values) != KEYS:
        raise ValueError("Staging env keys must exactly match the example")
    revision = values["STAGING_BACKEND_REVISION"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or values["STAGING_BACKEND_IMAGE"] != "heshan-backend:" + revision:
        raise ValueError("Backend must use its full approved Git SHA tag")
    if values["STAGING_FRONTEND_REVISION"] != revision:
        raise ValueError("Frontend and backend revisions must match")
    if (values["STAGING_DB_NAME"], values["STAGING_DB_USER"]) != ("heshan_staging", "heshan_staging_app"):
        raise ValueError("Only the isolated staging database/role names are allowed")
    for key in SECRET_KEYS:
        if not re.fullmatch(r"[0-9a-f]{64,128}", values[key]):
            raise ValueError("Generate fresh random hex staging secrets; placeholders/defaults rejected")
    if len({values[key] for key in SECRET_KEYS}) != 3:
        raise ValueError("Staging passwords and JWT secret must be different")
    for origin in values["STAGING_CORS_ALLOWED_ORIGINS"].split(","):
        url = urlsplit(origin)
        if url.scheme != "https" or not url.hostname or "*" in origin or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError("CORS requires explicit HTTPS origins, not wildcards")
        if url.hostname in {"heshan.net", "www.heshan.net", "api.heshan.net"}:
            raise ValueError("Production origins are forbidden in staging")
    if values["STAGING_STATIC_DIR"] != f"/srv/heshan-staging/releases/{revision}/frontend" or values["STAGING_TLS_DIR"] != "/etc/heshan-staging/tls":
        raise ValueError("Use isolated versioned staging artifact and certificate paths")


def redact(text, values):
    for key in SECRET_KEYS:
        text = text.replace(values[key], "[REDACTED]")
    return re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED-JWT]", text)


class Docker:
    def __init__(self, values, env_file, compose_overlay=None):
        endpoint = os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")
        if not endpoint.startswith("unix://") or os.environ.get("DOCKER_CONTEXT"):
            raise ValueError("Only an explicit local Unix Docker socket is allowed")
        self.values = values
        self.environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/root"),
                            "DOCKER_HOST": endpoint, **values}
        self.base = ["docker", "compose", "--project-name", PROJECT, "--env-file", str(env_file), "-f", str(COMPOSE)]
        installed_overlay = Path("/etc/heshan-staging/web-ingress.override.yml")
        if installed_overlay.exists() and compose_overlay is None:
            raise ValueError("Installed ingress overlay must be preserved with --compose-overlay")
        if compose_overlay:
            overlay = Path(compose_overlay)
            if (not overlay.is_absolute() or overlay.is_symlink() or not overlay.is_file()
                    or overlay.resolve() != overlay):
                raise ValueError("Compose overlay must be an absolute regular non-aliased file")
            info = overlay.stat()
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("Compose overlay must be owned by the executing user, mode 0600")
            self.base.extend(["-f", str(overlay)])

    def run(self, args, data=None, output=None):
        result = subprocess.run(args, input=data, stdout=output or subprocess.PIPE,
                                stderr=subprocess.PIPE, env=self.environment, timeout=600)
        if result.returncode:
            raise RuntimeError(redact(result.stderr.decode(errors="replace"), self.values) or "Docker command failed")
        return result.stdout

    def compose(self, *args, output=None):
        return self.run(self.base + list(args), output=output)


def validate_model(model, values):
    if model["name"] != PROJECT or set(model["services"]) != {"db", "backend", "web"}:
        raise ValueError("Unexpected staging Compose project/services")
    for name, service in model["services"].items():
        ports = service.get("ports", [])
        if name != "web" and ports:
            raise ValueError("Database/backend ports must never be published")
        if name == "web" and (len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1"
                or str(ports[0].get("published")) != "18443" or ports[0]["target"] != 8443):
            raise ValueError("Only loopback HTTPS port 18443 is allowed")
        if service.get("pull_policy") != "never":
            raise ValueError("Images must be reviewed and preloaded")
    backend = model["services"]["backend"]
    if backend["image"] != values["STAGING_BACKEND_IMAGE"] or backend["environment"]["DB_URL"] != "jdbc:postgresql://db:5432/heshan_staging":
        raise ValueError("Backend image/database isolation mismatch")
    networks = model["networks"]
    if (set(networks) != {"database", "application", "ingress"}
            or not networks["database"].get("internal")
            or not networks["application"].get("internal")
            or networks["ingress"].get("internal")
            or networks["ingress"].get("driver") != "bridge"):
        raise ValueError("Only the web ingress bridge may be non-internal")
    for service, expected in (("db", {"database"}), ("backend", {"database", "application"}),
                              ("web", {"application", "ingress"})):
        if set(model["services"][service]["networks"]) != expected:
            raise ValueError("Database/backend must never join the ingress network")
    if set(model["volumes"]) != {"staging_data"} or model["volumes"]["staging_data"]["name"] != PROJECT + "_staging_data":
        raise ValueError("Unexpected staging volume")


def check_web_access(path, required):
    info = path.stat()
    shift = 6 if info.st_uid == 101 else 3 if info.st_gid == 101 else 0
    if ((info.st_mode >> shift) & required) != required:
        raise ValueError(f"Container UID/GID 101 cannot access {path}")


def check_artifacts(values):
    static = Path(values["STAGING_STATIC_DIR"])
    tls = Path(values["STAGING_TLS_DIR"])
    for path in (static, tls, tls / "privkey.pem", tls / "fullchain.pem"):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("Staging paths must not alias another environment")
    metadata = json.loads((static / "release.json").read_text())
    if metadata != {"revision": values["STAGING_FRONTEND_REVISION"], "api_base_url": "/api"} or not (static / "index.html").is_file():
        raise ValueError("Use same-SHA frontend with relative /api and release.json")
    key = (tls / "privkey.pem").stat()
    if stat.S_IMODE(key.st_mode) & 0o007:
        raise ValueError("TLS private key must not be world-readable")
    if not ((key.st_uid == 101 and key.st_mode & 0o400) or (key.st_gid == 101 and key.st_mode & 0o040)):
        raise ValueError("TLS private key must be readable by container UID/GID 101")
    check_web_access(tls, 0o1)
    check_web_access(tls / "fullchain.pem", 0o4)
    check_web_access(static, 0o5)
    check_web_access(static / "index.html", 0o4)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tls / "fullchain.pem", tls / "privkey.pem")


def preflight(docker, values):
    docker.run(["docker", "info", "--format", "{{.ServerVersion}}"])
    model = json.loads(docker.compose("config", "--format", "json"))
    validate_model(model, values)
    check_artifacts(values)
    mem = Path("/proc/meminfo").read_text()
    available = next(int(line.split()[1]) for line in mem.splitlines() if line.startswith("MemAvailable:"))
    if available < 1300 * 1024:
        raise ValueError("At least 1300 MiB available RAM required; no other service will be stopped")
    disk = os.statvfs(values["STAGING_STATIC_DIR"])
    free = disk.f_bavail * disk.f_frsize
    if free < 4 * 1024 ** 3:
        raise ValueError("At least 4 GiB free artifact disk required")
    docker_root = docker.run(["docker", "info", "--format", "{{.DockerRootDir}}"] ).decode().strip()
    storage = os.statvfs(docker_root)
    if storage.f_bavail * storage.f_frsize < 4 * 1024 ** 3:
        raise ValueError("At least 4 GiB free Docker data disk required")
    running = docker.run(["docker", "ps", "--format", "{{.Names}} {{.Status}} {{.Ports}}"])
    print(running.decode().strip() or "No running containers")
    network_ids = docker.run(["docker", "network", "ls", "-q"]).decode().split()
    if network_ids:
        for network in json.loads(docker.run(["docker", "network", "inspect", *network_ids])):
            owned = (network.get("Labels") or {}).get("com.docker.compose.project") == PROJECT
            for item in network.get("IPAM", {}).get("Config") or []:
                if item.get("Subnet"):
                    subnet = ipaddress.ip_network(item["Subnet"])
                    if subnet.version == SUBNET.version and subnet.overlaps(SUBNET) and not owned:
                        raise ValueError("Staging subnet overlaps an existing Docker network")
    # Ports in use are never reclaimed; stop only approved staging containers explicitly.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 18443))
    for image in (values["STAGING_BACKEND_IMAGE"], "postgres:16-bookworm", "nginx:stable-alpine"):
        platform = docker.run(["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", image]).decode().strip()
        if platform != "linux/amd64":
            raise ValueError("Preload reviewed linux/amd64 images")
    revision = docker.run(["docker", "image", "inspect", "--format",
                           '{{index .Config.Labels "org.opencontainers.image.revision"}}', values["STAGING_BACKEND_IMAGE"]]).decode().strip()
    if revision != values["STAGING_BACKEND_REVISION"]:
        raise ValueError("Backend image revision label mismatch")
    user = docker.run(["docker", "image", "inspect", "--format", "{{.Config.User}}", values["STAGING_BACKEND_IMAGE"]]).decode().strip()
    if user != "10001:10001":
        raise ValueError("Backend image must run as the existing non-root app user")
    volumes = docker.run(["docker", "volume", "ls", "--format", "{{.Name}}"] ).decode().split()
    target = PROJECT + "_staging_data"
    if target in volumes:
        labels = json.loads(docker.run(["docker", "volume", "inspect", "--format", "{{json .Labels}}", target])) or {}
        if labels.get("com.docker.compose.project") != PROJECT or labels.get("com.docker.compose.volume") != "staging_data":
            raise ValueError("Existing target volume is not owned by this staging project")
    print(f"PASS: preflight; available RAM {available // 1024} MiB; artifact disk {free // 1024**3} GiB free")


def init_env(args):
    values = {"STAGING_BACKEND_REVISION": args.revision, "STAGING_BACKEND_IMAGE": "heshan-backend:" + args.revision,
              "STAGING_FRONTEND_REVISION": args.revision, "STAGING_STATIC_DIR": args.static_dir,
              "STAGING_TLS_DIR": args.tls_dir, "STAGING_DB_NAME": "heshan_staging", "STAGING_DB_USER": "heshan_staging_app",
              "STAGING_CORS_ALLOWED_ORIGINS": "https://localhost:18443", **{key: secrets.token_hex(48) for key in SECRET_KEYS}}
    validate_env(values)
    path = Path(args.env_file)
    if not path.is_absolute():
        raise ValueError("Env path must be absolute")
    # Exclusive creation: do not rotate credentials or overwrite an existing env.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write("\n".join(key + "=" + values[key] for key in sorted(values)) + "\n")
    print("Created private staging env; secrets were not printed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init-env", "preflight", "deploy", "status", "logs", "stop", "backup"])
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--compose-overlay", help="Explicitly preserve an installed private ingress overlay")
    parser.add_argument("--execute", action="store_true", help="Explicitly allow the selected mutation")
    parser.add_argument("--revision")
    parser.add_argument("--static-dir")
    parser.add_argument("--tls-dir")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    if args.action in {"init-env", "deploy", "stop", "backup"} and not args.execute:
        parser.error("Mutations require --execute after owner approval")
    if args.action == "init-env":
        if not all((args.revision, args.static_dir, args.tls_dir)):
            parser.error("init-env requires --revision, --static-dir and --tls-dir")
        init_env(args)
        return
    values = read_env(args.env_file)
    docker = Docker(values, args.env_file, args.compose_overlay)
    validate_model(json.loads(docker.compose("config", "--format", "json")), values)
    if args.action in {"preflight", "deploy"}:
        preflight(docker, values)
    if args.action == "deploy":
        try:
            docker.compose("up", "-d", "--wait", "--wait-timeout", "300")
            print("PASS: staging containers healthy; run HTTPS/API/browser checklist next")
        except Exception:
            docker.compose("stop")
            raise
    elif args.action == "stop":
        docker.compose("stop")
        remaining = docker.run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=" + PROJECT])
        if remaining.strip():
            raise RuntimeError("Some staging containers remain running")
        print("PASS: staging stopped; all data and resources retained")
    elif args.action in {"status", "logs"}:
        output = docker.compose("ps", "--all") if args.action == "status" else docker.compose("logs", "--no-color", "--tail", "200")
        print(redact(output.decode(errors="replace"), values))
    elif args.action == "backup":
        if not args.backup_dir or not Path(args.backup_dir).is_absolute():
            parser.error("backup requires an absolute --backup-dir")
        directory = Path(args.backup_dir)
        if directory.name != "heshan-staging":
            raise ValueError("Use a separate heshan-staging backup directory")
        if directory.is_symlink():
            raise ValueError("Backup directory must not be a symlink")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if stat.S_IMODE(directory.stat().st_mode) != 0o700:
            raise ValueError("Backup directory must be mode 0700")
        filename = directory / ("staging-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4) + ".dump")
        partial = filename.with_suffix(".dump.partial")
        with partial.open("xb") as output:
            partial.chmod(0o600)
            docker.compose("exec", "-T", "db", "sh", "-ec", 'PGPASSWORD="$APP_DB_PASSWORD"; export PGPASSWORD; exec pg_dump -h 127.0.0.1 -U "$APP_DB_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl', output=output)
        if not partial.stat().st_size:
            raise ValueError("Empty backup rejected")
        if filename.exists():
            raise ValueError("Refusing to overwrite an existing backup")
        partial.rename(filename)
        digest = hashlib.sha256()
        with filename.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        filename.with_suffix(".dump.sha256").write_text(digest.hexdigest() + "  " + filename.name + "\n")
        print("PASS: private local staging backup retained:", filename)
        print("Offsite transfer/restore/retention require separate approval; nothing was pruned")


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception as error:
        # Validation errors contain no values; command errors are already redacted.
        print("FAIL:", str(error), file=sys.stderr)
        sys.exit(1)
