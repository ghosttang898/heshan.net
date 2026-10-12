#!/usr/bin/env python3
"""Opt-in isolated integration rehearsal. Never targets an existing database."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import sys
import re
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = Path(__file__).with_name("pg-test-compose.yml")


def run(args, data=None, ok=True):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    if ok and result.returncode:
        # No response bodies, commands or environment values in error output.
        raise RuntimeError("Isolated test command failed; inspect the protected test directory")
    return result


class CommandFailure(RuntimeError):
    def __init__(self, reason, code=1):
        super().__init__(reason)
        self.code = code


class Journal:
    def __init__(self, directory, project):
        self.directory = directory.resolve()
        self.secrets = []
        self.report = {"project": project, "status": "RUNNING", "checks": [],
                       "containers_stopped": False, "failure_reason": None,
                       "log_directory": str(self.directory)}
        self.save()

    def redact(self, value):
        text = value.decode(errors="replace") if isinstance(value, bytes) else str(value)
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED-JWT]", text)
        text = re.sub(r"(?i)(password|secret|token)(\s*[=:]\s*)([^\s,;]+)", r"\1\2[REDACTED]", text)
        return text

    def save(self):
        temporary = self.directory / "result.json.partial"
        temporary.write_text(json.dumps(self.report, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(self.directory / "result.json")

    def emit(self, message):
        text = self.redact(message)
        with (self.directory / "execution.log").open("a") as log:
            log.write(text + "\n")
        print(text, flush=True)

    def perform(self, label, action, expected_nonzero=False):
        item = {"name": label, "status": "RUNNING", "exit_code": None, "reason": None,
                "started_at": datetime.now(timezone.utc).isoformat()}
        self.report["checks"].append(item)
        self.save()
        self.emit("START: " + label)
        try:
            result = action()
            item.update(status="PASS", exit_code=getattr(result, "returncode", 0))
            if item["exit_code"] != 0:
                if expected_nonzero:
                    item["reason"] = "Expected rejection; separately asserted"
                else:
                    item.update(status="FAIL", reason=self.redact(getattr(result, "stderr", b"")).strip() or "Command returned nonzero")
                    self.report["status"] = "FAIL"
                    self.report["failure_reason"] = self.report["failure_reason"] or label + ": " + item["reason"]
            self.emit(f"{item['status']}: {label} (exit {item['exit_code']})")
            return result
        except (Exception, KeyboardInterrupt) as exception:
            code = 130 if isinstance(exception, KeyboardInterrupt) else 124 if isinstance(exception, subprocess.TimeoutExpired) else getattr(exception, "code", 1)
            reason = "Interrupted by operator" if code == 130 else "Command timed out" if code == 124 else self.redact(str(exception))
            item.update(status="FAIL", exit_code=code, reason=reason)
            if self.report["failure_reason"] is None:
                self.report["failure_reason"] = label + ": " + reason
            self.report["status"] = "FAIL"
            self.emit(f"FAIL: {label} (exit {code}): {reason}")
            raise
        finally:
            item["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.save()

    def command(self, label, args, data=None, ok=True, private_stdout=False, expected_rejection=False):
        def action():
            try:
                result = run(args, data=data, ok=False)
            except subprocess.TimeoutExpired as exception:
                if exception.stderr:
                    self.emit(exception.stderr)
                if exception.stdout and not private_stdout:
                    self.emit(exception.stdout)
                raise
            if result.stdout and not private_stdout:
                self.emit(result.stdout)
            if result.stderr:
                self.emit(result.stderr)
            if ok and result.returncode:
                detail = self.redact(result.stderr).strip()[-4000:] or "Command returned no stderr; see saved container logs"
                raise CommandFailure(detail, result.returncode)
            return result
        return self.perform(label, action, expected_nonzero=expected_rejection)


def local_docker_environment(runner=None):
    runner = runner or run
    context = runner(["docker", "context", "inspect"]).stdout
    endpoint = os.environ.get("DOCKER_HOST") or json.loads(context)[0]["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith("unix://") or os.environ.get("DOCKER_CONTEXT"):
        raise RuntimeError("Only the local Unix Docker socket is allowed; unset DOCKER_CONTEXT")
    runner(["docker", "info"])
    if runner(["docker", "ps", "-q"]).stdout.strip():
        raise RuntimeError("Running containers detected; obtain a separately reviewed plan")
    memory = Path("/proc/meminfo").read_text()
    available = next(int(line.split()[1]) for line in memory.splitlines() if line.startswith("MemAvailable:"))
    if available < 1300 * 1024:
        raise RuntimeError("At least 1300 MiB available RAM is required")


def validate_compose_mounts(model):
    for name, service in model["services"].items():
        for mount in service.get("tmpfs", []):
            if not isinstance(mount, str) or not mount.split(":", 1)[0].startswith("/"):
                raise CommandFailure("Invalid tmpfs target for " + name + "; quote comma-containing YAML strings")
        for mount in service.get("volumes", []):
            if not mount.get("target", "").startswith("/"):
                raise CommandFailure("Volume target must be absolute for " + name)
    if model["services"]["backend"].get("tmpfs") != ["/tmp:size=64m,mode=1777"]:
        raise CommandFailure("Backend requires one /tmp tmpfs with size=64m and mode=1777")


def execute(image, report_dir=None, founder_username="verified-test-owner", expected_revision=None):
    project = "heshan-it-" + secrets.token_hex(6)
    directory = Path(report_dir).resolve() if report_dir else Path(tempfile.mkdtemp(prefix=project + "-", dir="/var/tmp"))
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "result.json").exists():
        raise RuntimeError("Refusing to overwrite an existing test report")
    directory.chmod(0o700)
    journal = Journal(directory, project)
    journal.report.update(backend_image=image, expected_revision=expected_revision,
                          founder_username=founder_username, resources=[])
    journal.emit("Absolute log directory: " + str(directory))
    journal.emit("Unique Compose project: " + project)
    (directory / "project.txt").write_text(project + "\n")
    env_file = directory / "test.env"
    credentials = {"TEST_ADMIN_PASSWORD": secrets.token_hex(32), "TEST_APP_PASSWORD": secrets.token_hex(32),
                   "TEST_JWT_SECRET": secrets.token_hex(48)}
    journal.secrets.extend(credentials.values())
    env_file.write_text("TEST_BACKEND_IMAGE=" + image + "\n" + "\n".join(key + "=" + value for key, value in credentials.items()) + "\n")
    env_file.chmod(0o600)
    base = ["docker", "compose", "--project-name", project, "--env-file", str(env_file), "-f", str(COMPOSE)]

    touched = False

    def compose(*args, data=None, ok=True, private_stdout=False, label=None, expected_rejection=False):
        label = label or "Compose " + args[0] + (" " + args[-1] if args[0] in ("up", "stop") and len(args) > 1 else "")
        return journal.command(label, base + list(args), data, ok, private_stdout, expected_rejection)

    def sql(query, database="heshan_test", admin=False):
        command = 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U postgres' if admin else 'PGPASSWORD="$APP_DB_PASSWORD" psql -h 127.0.0.1 -U "$APP_DB_USER"'
        return compose("exec", "-T", "db", "sh", "-ec", command + ' -v ON_ERROR_STOP=1 -At -d "$1"', "sh", database,
                       data=query.encode(), private_stdout=True,
                       label="SQL " + database + ": " + query[:160]).stdout.decode().strip()

    def request(method, path, body=None, token=None, expected=200):
        config = ['silent', 'show-error', 'max-time = 15', 'request = "' + method + '"',
                  'url = "http://127.0.0.1:8080/api' + path + '"', 'write-out = "\\n%{http_code}"']
        if token:
            config.append('header = "Authorization: Bearer ' + token + '"')
        if body is not None:
            config.append('header = "Content-Type: application/json"')
            config.append('data = ' + json.dumps(json.dumps(body)))
        output = compose("exec", "-T", "backend", "curl", "--config", "-", data="\n".join(config).encode(), private_stdout=True,
                         label=f"HTTP {method} {path}").stdout.decode()
        content, status = output.rsplit("\n", 1)
        require(int(status) == expected, f"HTTP {method} {path}: expected {expected}, received {status}")
        result = json.loads(content) if content and expected == 200 else None
        if isinstance(result, dict) and result.get("token"):
            journal.secrets.append(result["token"])
        require(True, f"HTTP {method} {path}: expected status {expected}")
        return result

    def bootstrap(user_id, username, confirmation, expected_rejection=False):
        return compose("run", "--no-deps", "backend", "--initialize-founder",
                       "--founder-id=" + str(user_id), "--confirm-founder-id=" + str(confirmation),
                       "--founder-username=" + username, "--confirm-founder-username=" + username, ok=False,
                       expected_rejection=expected_rejection,
                       label="Founder initialization command, confirmed ID " + str(confirmation))

    def require(condition, message):
        def assertion():
            if not condition:
                raise CommandFailure(message)
        journal.perform(message, assertion)

    def record(check):
        require(True, check)

    def resources(phase):
        ids = compose("ps", "-q", label="Resource container IDs: " + phase).stdout.decode().split()
        stats = journal.command("Container resources: " + phase,
                                ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids],
                                private_stdout=True).stdout.decode() if ids else ""
        snapshot = {"phase": phase, "time": datetime.now(timezone.utc).isoformat(),
                    "containers": [json.loads(line) for line in stats.splitlines() if line.strip()],
                    "host_meminfo": Path("/proc/meminfo").read_text(),
                    "host_loadavg": Path("/proc/loadavg").read_text(),
                    "host_cpu_stat": Path("/proc/stat").read_text(),
                    "host_disk": journal.command("Host disk: " + phase, ["df", "-Pk", str(directory)]).stdout.decode()}
        journal.report["resources"].append(snapshot)
        journal.save()
        (directory / "resources.json").write_text(json.dumps(journal.report["resources"], indent=2) + "\n")

    def diagnostics(phase):
        # Save logs BEFORE stop and again AFTER stop; no full inspect/Env output.
        for name, args in (("containers", ("ps", "-a", "--format", "json")),
                           ("container-logs", ("logs", "--no-color", "--timestamps"))):
            try:
                result = compose(*args, ok=False, private_stdout=True)
                (directory / f"{phase}-{name}.log").write_text(journal.redact(result.stdout + result.stderr))
            except Exception as exception:
                journal.emit("Diagnostics unavailable: " + name + ": " + journal.redact(str(exception)))
        try:
            ids = compose("ps", "-a", "-q", ok=False, private_stdout=True).stdout.decode().split()
            for container in ids:
                ports = journal.command("Retained container published ports", ["docker", "inspect", "--format",
                                        "{{json .HostConfig.PortBindings}}", container], private_stdout=True)
                require(ports.stdout.decode().strip() in ("null", "{}"), "Retained test container has no published ports")
                state = journal.command("Container state and health", ["docker", "inspect", "--format", "{{json .State}}", container], ok=False, private_stdout=True)
                (directory / f"{phase}-{container}-state.json").write_text(journal.redact(state.stdout + state.stderr))
                logs = journal.command("Retained container log", ["docker", "logs", "--timestamps", container], ok=False, private_stdout=True)
                (directory / f"{phase}-{container}-container.log").write_text(journal.redact(logs.stdout + logs.stderr))
        except Exception as exception:
            journal.emit("Container state capture unavailable: " + journal.redact(str(exception)))

    try:
        journal.perform("Local Docker and available memory preflight", lambda: local_docker_environment(
            runner=lambda args: journal.command("Docker preflight", args)))
        for candidate in (image, "postgres:16-bookworm"):
            inspection = journal.command("Image architecture: " + candidate,
                                         ["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", candidate])
            require(inspection.stdout.decode().strip() == "linux/amd64", "AMD64 image: " + candidate)
        if expected_revision:
            revision = journal.command("Backend source revision", ["docker", "image", "inspect", "--format",
                                       '{{index .Config.Labels "org.opencontainers.image.revision"}}', image]).stdout.decode().strip()
            require(revision == expected_revision, "Backend image matches approved Git commit")
        compose("config", "--quiet")
        model = compose("config", "--format", "json", private_stdout=True)
        journal.perform("Normalized Compose tmpfs and volume target verification",
                        lambda: validate_compose_mounts(json.loads(model.stdout)))
        touched = True
        compose("up", "-d", "--wait", "--wait-timeout", "240", "db")
        health = compose("exec", "-T", "db", "pg_isready", "-h", "127.0.0.1", "-U", "integration_app", "-d", "heshan_test")
        require(health.returncode == 0, "PostgreSQL accepts TCP connections")
        require(sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';") == "0", "Empty PostgreSQL schema verification")
        require(160000 <= int(sql("SHOW server_version_num;")) < 170000, "PostgreSQL 16 server version verification")
        compose("up", "-d", "--wait", "--wait-timeout", "300", "backend")
        if expected_revision:
            logs = compose("logs", "--no-color", "backend", private_stdout=True).stdout.decode()
            require("(v4.1.1)" in logs, "Spring Boot 4.1.1 startup banner verification")
        require(sql("SELECT count(*) FROM flyway_schema_history WHERE success;") == "1", "Flyway V1 migration verification")
        require(sql("SELECT rolsuper OR rolcreatedb OR rolcreaterole FROM pg_roles WHERE rolname=current_user;") == "f", "Non-privileged application DB role verification")
        # Capture only resource/port metadata, never inspect container environment.
        ids = compose("ps", "-q").stdout.decode().split()
        for container in ids:
            ports = journal.command("Published port verification", ["docker", "inspect", "--format", "{{json .HostConfig.PortBindings}}", container]).stdout.decode().strip()
            require(ports in ("null", "{}"), "No publicly published container ports")
        stats = journal.command("Container resource snapshot", ["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}} {{.CPUPerc}}", *ids]).stdout
        (directory / "resources.txt").write_bytes(stats)
        (directory / "host-memory.txt").write_text(Path("/proc/meminfo").read_text())
        resources("initial-startup")
        record("PostgreSQL startup, Flyway V1, Hibernate validate, private ports and DB role")
        owner_name = founder_username
        password = secrets.token_hex(16)
        journal.secrets.append(password)
        owner = request("POST", "/auth/register", {"username": owner_name, "displayName": "Test owner", "password": password, "role": "SUPER_ADMIN"})
        ordinary = request("POST", "/auth/register", {"username": "ordinary-test", "displayName": "Test user", "password": password})
        require(owner["role"] == ordinary["role"] == "USER", "Registration defaults to USER despite injected role")
        owner_id = int(sql("SELECT id FROM users WHERE username='" + owner_name + "';"))
        target_id = int(sql("SELECT id FROM users WHERE username='ordinary-test';"))
        request("GET", "/admin/dashboard", token=ordinary["token"], expected=403)
        compose("stop", "backend")
        require(bootstrap(owner_id, owner_name, owner_id + 1, expected_rejection=True).returncode != 0, "Wrong founder confirmation is rejected")
        require(sql("SELECT count(*) FROM founder_identity;") == "0", "Rejected initialization leaves no founder identity")
        require(bootstrap(owner_id, owner_name, owner_id).returncode == 0, "Confirmed founder initialization succeeds")
        require(bootstrap(owner_id, owner_name, owner_id, expected_rejection=True).returncode != 0, "Repeated founder initialization is rejected")
        compose("up", "-d", "--wait", "--wait-timeout", "300", "backend")
        owner = request("POST", "/auth/login", {"username": owner_name, "password": password})
        request("PATCH", f"/admin/users/{target_id}/role", {"role": "SUPER_ADMIN", "expectedRole": "USER"}, owner["token"], 400)
        request("PATCH", f"/admin/users/{target_id}/role", {"role": "ADMIN", "expectedRole": "USER"}, owner["token"])
        admin = request("POST", "/auth/login", {"username": "ordinary-test", "password": password})
        request("GET", "/admin/posts", token=admin["token"])
        request("GET", "/admin/administrators", token=admin["token"], expected=403)
        request("PATCH", f"/admin/users/{owner_id}/role", {"role": "USER", "expectedRole": "SUPER_ADMIN"}, admin["token"], 403)
        request("PATCH", f"/admin/users/{owner_id}/role", {"role": "USER", "expectedRole": "SUPER_ADMIN"}, owner["token"], 403)
        request("PATCH", f"/admin/users/{target_id}/role", {"role": "USER", "expectedRole": "ADMIN"}, owner["token"])
        request("GET", "/admin/posts", token=admin["token"], expected=403)
        require(sql("SELECT count(*) FROM role_change_audit;") == "3", "Missing audit")
        resources("permissions-verified")
        record("Registration USER, founder one-time confirmation, role protection, old JWT revocation and audits")
        sql("INSERT INTO posts(title,content,type,author_id,created_at) SELECT 'test','persistent fixture','CHAT',id,CURRENT_TIMESTAMP FROM users WHERE username='" + owner_name + "'; INSERT INTO comments(content,post_id,created_at) SELECT 'test reply',id,CURRENT_TIMESTAMP FROM posts;")
        compose("stop", "backend")
        # Recreate the DB container, keeping only this run's named volume.
        compose("stop", "db")
        diagnostics("before-recreate")
        compose("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "240", "db")
        compose("up", "-d", "--wait", "--wait-timeout", "300", "backend")
        request("GET", "/admin/dashboard", token=owner["token"])
        resources("persistence-verified")
        require(sql("SELECT count(*) FROM flyway_schema_history WHERE success;") == "1", "Migration rerun changed history")
        record("Named-volume persistence and repeat Flyway validation")
        compose("stop", "backend")
        dump = compose("exec", "-T", "db", "sh", "-ec", 'PGPASSWORD="$APP_DB_PASSWORD" pg_dump -h 127.0.0.1 -U "$APP_DB_USER" -d heshan_test -Fc --no-owner --no-acl', private_stdout=True).stdout
        require(bool(dump), "Nonempty pg_dump backup")
        backup = directory / "isolated.dump"
        backup.write_bytes(dump)
        backup.chmod(0o600)
        (directory / "isolated.dump.sha256").write_text(hashlib.sha256(dump).hexdigest() + "  isolated.dump\n")
        sql("CREATE DATABASE heshan_restore OWNER integration_app;", admin=True)
        compose("exec", "-T", "db", "sh", "-ec", 'PGPASSWORD="$APP_DB_PASSWORD" pg_restore -h 127.0.0.1 -U "$APP_DB_USER" -d heshan_restore --exit-on-error --no-owner --no-acl', data=dump)
        for table in ("users", "posts", "comments", "founder_identity", "role_change_audit", "flyway_schema_history"):
            query = f"SELECT row_to_json(t)::text FROM {table} t ORDER BY id;" if table != "flyway_schema_history" else "SELECT row_to_json(t)::text FROM flyway_schema_history t ORDER BY installed_rank;"
            require(sql(query) == sql(query, "heshan_restore"), "Restore rows differ: " + table)
        # Validate restored schema through real application startup, private network only.
        result = compose("run", "--no-deps", "--entrypoint", "sh", "backend", "-ec",
                         'export DB_URL=jdbc:postgresql://db:5432/heshan_restore; '
                         'java -jar /app/app.jar & pid=$!; '
                         'trap \'kill "$pid" 2>/dev/null || true\' EXIT; '
                         'i=0; while [ "$i" -lt 120 ]; do '
                         'kill -0 "$pid" || exit 1; '
                         'if curl --fail --silent --max-time 3 http://127.0.0.1:8080/actuator/health >/dev/null; then exit 0; fi; '
                         'i=$((i+1)); sleep 2; done; exit 1', ok=False)
        require(result.returncode == 0, "Restored application Flyway/Hibernate/health verification")
        record("pg_dump, row-for-row isolated restore and restored Hibernate validation")
        resources("restore-verified")
        if journal.report["status"] != "FAIL":
            journal.report["status"] = "PASS"
    except (Exception, KeyboardInterrupt) as exception:
        journal.report["status"] = "FAIL"
        if journal.report["failure_reason"] is None:
            try:
                journal.perform("Test assertion or response parsing", lambda: (_ for _ in ()).throw(exception))
            except (Exception, KeyboardInterrupt):
                pass
        raise
    finally:
        if touched:
            diagnostics("before-stop")
            try:
                stopped = compose("stop", ok=False).returncode == 0
                remaining = journal.command("Confirm project containers stopped", ["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=" + project], ok=False, private_stdout=True)
                if remaining.returncode == 0 and remaining.stdout.strip():
                    journal.command("Stop only this project's remaining command containers", ["docker", "stop", *remaining.stdout.decode().split()])
                    remaining = journal.command("Recheck project containers stopped", ["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=" + project], ok=False, private_stdout=True)
                journal.report["containers_stopped"] = stopped and remaining.returncode == 0 and not remaining.stdout.strip()
            except Exception:
                journal.report["containers_stopped"] = False
            diagnostics("after-stop")
        else:
            journal.report["containers_stopped"] = True
            for phase in ("before-stop", "after-stop"):
                (directory / f"{phase}-container-logs.log").write_text("No test containers were started.\n")
        if not journal.report["containers_stopped"]:
            journal.report["status"] = "FAIL"
            journal.report["failure_reason"] = journal.report["failure_reason"] or "Could not confirm test containers stopped"
        journal.save()
        journal.emit("Final status: " + journal.report["status"])
        journal.emit("Containers stopped: " + str(journal.report["containers_stopped"]))
        for name in ("execution.log", "result.json", "before-stop-container-logs.log", "after-stop-container-logs.log"):
            journal.emit("Absolute artifact path: " + str(directory / name))
        journal.emit("No Volume, backup, report, network or retained test container was deleted.")
        if journal.report["status"] != "PASS":
            raise CommandFailure(journal.report["failure_reason"] or "Test failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-isolated-tests", action="store_true", required=True)
    parser.add_argument("--image", required=True, help="Already-loaded backend image; never built or pulled here")
    parser.add_argument("--report-dir", help="New protected absolute report directory")
    parser.add_argument("--founder-username", default="verified-test-owner", help="Synthetic owner in the isolated database only")
    parser.add_argument("--expected-revision", help="Approved full Git SHA recorded in the image label")
    args = parser.parse_args()
    if not args.image or any(c.isspace() for c in args.image) or "=" in args.image:
        parser.error("Invalid image reference")
    if args.report_dir and not Path(args.report_dir).is_absolute():
        parser.error("Report directory must be absolute")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,50}", args.founder_username):
        parser.error("Founder test username must contain 3-50 letters, digits, underscores or hyphens")
    if args.expected_revision and not re.fullmatch(r"[0-9a-f]{40}", args.expected_revision):
        parser.error("Expected revision must be a full lowercase Git SHA")
    execute(args.image, args.report_dir, args.founder_username, args.expected_revision)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never print subprocess data, HTTP bodies, tokens or credential values.
        print("FAIL: test aborted; consult protected result.json and execution log.", file=sys.stderr)
        sys.exit(1)
