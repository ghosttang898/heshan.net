"""Opt-in LOCAL fixture only: no VPS, real DB, account, DNS or production key."""
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get("RUN_STAGING_NGINX_TEST") == "1", "Explicit local Nginx fixture opt-in required")
class StagingNginxFixture(unittest.TestCase):
    def test_https_spa_headers_assets_and_api_boundary_as_nonroot(self):
        endpoint = os.environ.get("DOCKER_HOST", "")
        if os.environ.get("DOCKER_CONTEXT") or (endpoint and not endpoint.startswith("unix://")):
            self.fail("Local Docker endpoint only")
        directory = Path(tempfile.mkdtemp(prefix="heshan-staging-nginx-"))
        name = "heshan-staging-fixture-" + secrets.token_hex(6)
        image = name + ":local"
        self.addCleanup(lambda: subprocess.run(["docker", "rm", "-f", name], capture_output=True))
        def run(*args):
            result = subprocess.run(args, capture_output=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            return result.stdout
        # Only a generated throwaway certificate enters this local fixture image.
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost", "-keyout", str(directory / "privkey.pem"), "-out", str(directory / "fullchain.pem"))
        (directory / "privkey.pem").chmod(0o600)
        (directory / "nginx.conf").write_bytes((ROOT / "deploy/staging/nginx.conf").read_bytes())
        (directory / "index.html").write_text('<!doctype html><title>Staging TLS fixture</title><p>fixture</p>')
        (directory / "Dockerfile").write_text("FROM nginx:stable-alpine\nCOPY nginx.conf /etc/nginx/nginx.conf\n"
            "COPY --chown=101:101 --chmod=0640 privkey.pem /etc/nginx/tls/privkey.pem\n"
            "COPY fullchain.pem /etc/nginx/tls/fullchain.pem\nCOPY index.html /usr/share/nginx/html/index.html\n"
            'USER 101:101\nENTRYPOINT ["nginx", "-g", "daemon off;"]\n')
        run("docker", "build", "-t", image, str(directory))
        run("docker", "run", "-d", "--name", name, "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "64m", "--cpus", "0.1", "--pids-limit", "40", "--tmpfs", "/tmp:size=32m,mode=1777",
            "--add-host", "backend:127.0.0.1", "-p", "127.0.0.1::8443", image)
        port = run("docker", "port", name, "8443").decode().strip().rsplit(":", 1)[1]
        context = ssl.create_default_context(cafile=str(directory / "fullchain.pem"))
        origin = "https://localhost:" + port
        try:
            for attempt in range(30):
                try:
                    with urlopen(origin, context=context, timeout=3) as response:
                        index = response.read()
                    break
                except URLError:
                    time.sleep(0.5)
            else: self.fail("Nginx TLS fixture failed to become ready")
            for path in ("/", "/chat", "/find", "/posts/1", "/login", "/register", "/admin/administrators"):
                with urlopen(origin + path, context=context, timeout=5) as response:
                    self.assertEqual(response.read(), index)
                    self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                    self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                    self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
                    self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
                    self.assertIn("noindex", response.headers["X-Robots-Tag"])
                    self.assertEqual(response.headers["X-Heshan-Environment"], "staging")
                    self.assertIn("no-store", response.headers["Cache-Control"])
            for path, status in (("/api", 404), ("/api/health", 502), ("/assets/missing.js", 404), ("/.env", 404)):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(origin + path, context=context, timeout=5)
                self.assertEqual(caught.exception.code, status)
                self.assertNotEqual(caught.exception.read(), index)
            state = json.loads(run("docker", "inspect", "--format", "{{json .HostConfig.PortBindings}}", name))
            self.assertEqual(state["8443/tcp"][0]["HostIp"], "127.0.0.1")
            print("PASS: LOCAL Nginx/TLS/SPA fixture; NOT a staging deployment; retained at", directory)
        finally:
            (directory / "nginx.log").write_bytes(subprocess.run(["docker", "logs", name], capture_output=True).stderr)
            run("docker", "stop", name)


if __name__ == "__main__":
    unittest.main()
