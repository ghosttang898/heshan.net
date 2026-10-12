#!/usr/bin/env python3
"""Opt-in synthetic Staging API acceptance. Credentials stay in memory."""
import argparse
import json
import secrets
import ssl
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-cert", required=True)
    parser.add_argument("--create-synthetic-staging-data", action="store_true")
    args = parser.parse_args()
    if not args.create_synthetic_staging_data:
        parser.error("Explicit synthetic Staging writes authorization required")
    origin = "https://localhost:18443"
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=args.ca_cert)), NoRedirects())
    checks = []
    artifacts = {}
    username = "stage-api-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(32)
    token = None

    def request(method, path, body=None, authenticated=False, expected=200, extra_headers=None):
        headers = {"Content-Type": "application/json", **(extra_headers or {})}
        if authenticated:
            headers["Authorization"] = "Bearer " + token
        req = Request(origin + path, headers=headers, method=method,
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            response = opener.open(req, timeout=20)
        except HTTPError as error:
            response = error
        if response.code != expected:
            raise AssertionError(f"Expected HTTP {expected}; received {response.code}")
        content = response.read()
        return response.headers, json.loads(content) if content else None

    def check(name, action):
        try:
            action()
            checks.append({"name": name, "status": "PASS"})
        except Exception as error:
            # Never print response bodies, request credentials or arbitrary exceptions.
            reason = str(error) if isinstance(error, AssertionError) else type(error).__name__
            checks.append({"name": name, "status": "FAIL", "reason": reason})

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    marker, _ = request("GET", "/api/health")
    require(marker.get("X-Heshan-Environment") == "staging", "Missing Staging marker; writes refused")

    def register():
        nonlocal token
        _, data = request("POST", "/api/auth/register", {"username": username, "password": password,
                          "displayName": "API acceptance fixture", "role": "SUPER_ADMIN"})
        require(data["role"] == "USER", "Registration role must be USER")
        token = data["token"]
        artifacts["username"] = username
    check("Registration defaults to USER despite supplied SUPER_ADMIN", register)
    if token is None:
        print(json.dumps({"checks": checks, "status": "FAIL"}, indent=2))
        return 1

    def login():
        nonlocal token
        _, data = request("POST", "/api/auth/login", {"username": username, "password": password})
        require(data["role"] == "USER", "Login role must be USER")
        token = data["token"]
    check("Login", login)
    check("Current identity", lambda: require(request("GET", "/api/auth/me", authenticated=True)[1]["username"] == username,
                                             "Identity mismatch"))
    check("Wrong password rejected", lambda: request("POST", "/api/auth/login",
          {"username": username, "password": secrets.token_urlsafe(32)}, expected=401))
    check("Unauthenticated identity rejected", lambda: request("GET", "/api/auth/me", expected=401))
    check("Re-login", login)
    for path in ("/api/admin/dashboard", "/api/admin/posts", "/api/admin/comments", "/api/admin/users", "/api/admin/administrators"):
        check("USER denied " + path, lambda path=path: request("GET", path, authenticated=True, expected=403))

    for kind in ("CHAT", "FIND_PERSON"):
        def publish(kind=kind):
            payload = {"title": "Staging API fixture " + kind + " " + username,
                       "content": "Synthetic acceptance data; not a real person or request.", "type": kind,
                       "ipCountry": "FORGED", "ipCity": "FORGED", "ipLocationStatus": "RESOLVED"}
            if kind == "FIND_PERSON":
                payload.update(nickname="Acceptance fixture", location="Synthetic Heshan", yearRange="2000-2001")
            _, data = request("POST", "/api/posts", payload, authenticated=True,
                              extra_headers={"X-Forwarded-For": "8.8.8.8"})
            artifacts[kind] = {"post_id": data["id"]}
            require(data["authorUsername"] == username, "Post author mismatch")
            require(data["ipCountry"] != "FORGED" and data["ipCity"] != "FORGED", "Client forged geolocation accepted")
            require(data["ipLocationStatus"] == "NON_PUBLIC", "Tunnel request or spoofed header incorrectly treated as public")
            _, stored = request("GET", f'/api/posts/{data["id"]}')
            for key in ("title", "content", "type", "nickname", "location", "yearRange"):
                if key in payload:
                    require(stored[key] == payload[key], "Stored post field mismatch: " + key)
            _, comment = request("POST", f'/api/posts/{data["id"]}/comments',
                                 {"content": "Synthetic API acceptance comment", "ipCountry": "FORGED"}, authenticated=True)
            artifacts[kind]["comment_id"] = comment["id"]
            require(comment["username"] == username, "Comment author mismatch")
            _, comments = request("GET", f'/api/posts/{data["id"]}/comments')
            require(any(row["id"] == comment["id"] and row["content"] == comment["content"] for row in comments),
                    "Saved comment not returned")
            forbidden = {"password", "passwordhash", "token", "ip", "ipaddress", "rawip", "clientip", "remoteaddress"}
            for row in (stored, *comments):
                require(not forbidden.intersection(key.lower() for key in row), "Sensitive public API fields found")
            artifacts[kind]["location_status"] = stored["ipLocationStatus"]
        check(kind + " publish/read/comment/author/location/privacy", publish)
    check("Public lists include both test posts", lambda: require(
          {record["post_id"] for kind, record in artifacts.items() if kind in {"CHAT", "FIND_PERSON"}}.issubset(
              {row["id"] for row in request("GET", "/api/posts")[1]}), "Created posts missing from list"))
    print(json.dumps({"status": "FAIL" if any(row["status"] == "FAIL" for row in checks) else "PASS",
                      "scope": "Synthetic API checks only; no DB SQL, UI logout, admin grants or restart claims",
                      "artifacts": artifacts, "checks": checks}, indent=2))
    return 1 if any(row["status"] == "FAIL" for row in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
