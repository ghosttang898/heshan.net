#!/usr/bin/env python3
"""Run owner-approved read-only persistence prechecks via interactive SSH sudo."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys

NAMES = ["heshan-staging-db-1", "heshan-staging-backend-1", "heshan-staging-web-1"]
FORMAT = ('{"id":"{{.Id}}","image":"{{.Config.Image}}",'
          '"project":"{{index .Config.Labels "com.docker.compose.project"}}",'
          '"compose_files":"{{index .Config.Labels "com.docker.compose.project.config_files"}}",'
          '"state":{{json .State}},"restarts":{{.RestartCount}},'
          '"restart_policy":{{json .HostConfig.RestartPolicy}},'
          '"memory":{{.HostConfig.Memory}},"memory_swap":{{.HostConfig.MemorySwap}},'
          '"cpus":{{.HostConfig.NanoCpus}},"mounts":{{json .Mounts}},'
          '"ports":{{json .NetworkSettings.Ports}}}')
SQL = """BEGIN READ ONLY;
SELECT json_build_object(
 'users', (SELECT count(*) FROM public.users),
 'posts', (SELECT count(*) FROM public.posts),
 'comments', (SELECT count(*) FROM public.comments),
 'role_change_audit', (SELECT count(*) FROM public.role_change_audit),
 'founder_identity_count', (SELECT count(*) FROM public.founder_identity),
 'ghost', (SELECT json_build_object('id',id,'role',role) FROM public.users WHERE username='ghost'),
 'flyway', (SELECT json_agg(json_build_object('version',version,'success',success) ORDER BY installed_rank)
            FROM public.flyway_schema_history));
COMMIT;
"""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(args, data=None):
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/root",
           "DOCKER_HOST": "unix:///var/run/docker.sock"}
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=90)
    require(result.returncode == 0, "Read-only command failed: " + args[0] + " (output withheld)")
    return result.stdout


def server_check():
    require(sys.platform == "linux" and os.geteuid() == 0, "Linux interactive sudo required")
    result = {"status": "FAIL", "read_only": True, "checks": {}}
    try:
        mem = {line.split()[0].rstrip(":"): int(line.split()[1])
               for line in Path("/proc/meminfo").read_text().splitlines()}
        fs = os.statvfs("/var/lib/docker")
        result["resources"] = {"available_ram_mib": mem["MemAvailable"] // 1024,
                               "swap_used_mib": (mem["SwapTotal"] - mem["SwapFree"]) // 1024,
                               "free_disk_bytes": fs.f_bavail * fs.f_frsize,
                               "load_average": list(os.getloadavg())}
        require(mem["MemAvailable"] >= 768 * 1024 and fs.f_bavail * fs.f_frsize >= 4 * 1024**3,
                "Resource gate failed")
        result["containers"] = {}
        for name in NAMES:
            model = json.loads(run(["docker", "inspect", name, "--format", FORMAT]))
            # Healthcheck output is not printed; it can contain application details.
            health = model["state"].get("Health", {}).get("Status")
            model["state"] = {key: model["state"][key] for key in ("Status", "Running", "OOMKilled", "StartedAt")}
            model["state"]["health"] = health
            result["containers"][name] = model
            require(model["project"] == "heshan-staging" and model["state"]["Running"]
                    and health == "healthy" and not model["state"]["OOMKilled"]
                    and model["restarts"] == 0, "Staging identity/health/restart gate failed")
        result["checks"]["current_staging_health"] = "PASS"
        db = result["containers"][NAMES[0]]
        data = [m for m in db["mounts"] if m["Destination"] == "/var/lib/postgresql/data"]
        require(len(data) == 1 and data[0]["Type"] == "volume"
                and data[0]["Name"] == "heshan-staging_staging_data" and data[0]["RW"], "Unexpected data mount")
        volume = json.loads(run(["docker", "volume", "inspect", data[0]["Name"], "--format",
            '{"name":"{{.Name}}","driver":"{{.Driver}}","path":"{{.Mountpoint}}"}']))
        require(volume["driver"] == "local" and volume["path"] == data[0]["Source"], "Volume source mismatch")
        result["volume"] = volume
        result["checks"]["persistent_volume"] = "PASS"
        require(not result["containers"][NAMES[0]]["ports"].get("5432/tcp")
                and not result["containers"][NAMES[1]]["ports"].get("8080/tcp")
                and result["containers"][NAMES[2]]["ports"].get("8443/tcp") ==
                [{"HostIp": "127.0.0.1", "HostPort": "18443"}], "Ingress gate failed")
        result["checks"]["loopback_ingress"] = "PASS"
        overlay = Path("/etc/heshan-staging/web-ingress.override.yml")
        info = overlay.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
                "Unsafe/missing overlay")
        files = result["containers"][NAMES[2]]["compose_files"].split(",")
        require(str(overlay) in files and len(files) == 2, "Active Web compose must include overlay")
        result["overlay_sha256"] = hashlib.sha256(overlay.read_bytes()).hexdigest()
        # Never read staging.env or print resolved Compose environment values.
        command = ["docker", "compose", "--project-name", "heshan-staging", "--env-file", "/dev/null"]
        for file in files:
            require(Path(file).is_absolute() and Path(file).is_file(), "Missing recorded Compose file")
            command.extend(["-f", file])
        config = json.loads(run(command + ["config", "--no-interpolate", "--format", "json"]))
        result["compose"] = {name: {key: config["services"][name].get(key) for key in
                            ("restart", "depends_on", "networks", "ports", "mem_limit", "cpus")}
                            for name in ("db", "backend", "web")}
        require(all(config["services"][s].get("restart") == "unless-stopped" for s in ("db", "backend", "web")),
                "Unexpected restart policy")
        result["checks"]["compose_and_overlay"] = "PASS"
        backups = Path("/var/backups/heshan-staging")
        info = backups.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
                "Unsafe backup directory")
        backup = max(backups.glob("*.dump"), key=lambda p: p.lstat().st_mtime)
        sidecar = Path(str(backup) + ".sha256")
        for file in (backup, sidecar):
            info = file.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
                    "Unsafe backup input")
        require(backup.stat().st_size > 0, "Empty backup")
        digest = hashlib.sha256()
        with backup.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        require(sidecar.read_text().strip() == digest.hexdigest() + "  " + str(backup), "Backup SHA256/path mismatch")
        with backup.open("rb") as stream:
            process = subprocess.run(["docker", "exec", "-i", NAMES[0], "pg_restore", "--list"],
                                     stdin=stream, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     env={"PATH": "/usr/bin:/bin", "DOCKER_HOST": "unix:///var/run/docker.sock"}, timeout=90)
        require(process.returncode == 0, "Archive listing failed; error body withheld")
        result["backup"] = {"path": str(backup), "bytes": backup.stat().st_size,
                            "sha256": digest.hexdigest(), "mtime_unix": backup.stat().st_mtime}
        result["checks"]["backup_checksum_and_archive"] = "PASS"
        raw = run(["docker", "exec", "-i", NAMES[0], "psql", "-X", "-qAt", "-U", "postgres",
                   "-d", "heshan_staging", "-v", "ON_ERROR_STOP=1"], SQL.encode())
        result["database_baseline"] = json.loads(raw)
        require(result["database_baseline"]["ghost"] == {"id": 1, "role": "USER"}
                and result["database_baseline"]["founder_identity_count"] == 0, "Owner baseline differs; do not change it")
        result["checks"]["owner_unmodified_baseline"] = "PASS"
        result["status"] = "PASS"
    except Exception as error:
        result["reason"] = str(error) if isinstance(error, ValueError) else type(error).__name__
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--server-readonly"]:
        raise SystemExit(server_check())
    require(not sys.argv[1:], "No arguments expected for Mac launcher")
    payload = "sudo python3 -c " + shlex.quote(Path(__file__).read_text()) + " --server-readonly"
    raise SystemExit(subprocess.call(["ssh", "-t", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30",
                                     "-i", str(Path.home() / ".ssh/id_ed25519"), "heshan@165.232.156.104", payload]))
