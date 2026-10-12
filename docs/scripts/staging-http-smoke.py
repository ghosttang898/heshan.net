#!/usr/bin/env python3
"""Explicit HTTPS staging smoke tests. Synthetic writes require a separate flag."""
import argparse
import json
import secrets
import ssl
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler


def validate_origin(value):
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
        raise ValueError("Use an explicit HTTPS staging origin")
    if url.hostname not in {"localhost", "127.0.0.1", "::1"} and not url.hostname.startswith("staging-") and not url.hostname.endswith(".pages.dev"):
        raise ValueError("Only loopback, staging-* or Pages preview origins are allowed")
    return value


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        # Never forward JWTs across origins or accidentally hit production.
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--ca-cert", help="Trusted local CA; never disable certificate verification")
    parser.add_argument("--exercise-test-user", action="store_true", help="Explicitly create synthetic USER/post/comment in staging")
    args = parser.parse_args()
    origin = validate_origin(args.origin)
    context = ssl.create_default_context()
    if args.ca_cert:
        context.load_verify_locations(args.ca_cert)
    opener = build_opener(HTTPSHandler(context=context), NoRedirects())
    checks = []

    def request(method, path, body=None, token=None, expected=200):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(origin + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
        try:
            response = opener.open(request, timeout=20)
        except HTTPError as error:
            response = error
        if response.code != expected:
            raise ValueError(f"{method} {path}: expected {expected}, got {response.code}; no response body logged")
        content = response.read()
        checks.append({"name": method + " " + path, "status": "PASS"})
        return response.headers, content

    try:
        headers, index = request("GET", "/")
        if headers.get("X-Heshan-Environment") != "staging":
            raise ValueError("Staging environment marker required before any synthetic writes")
        for header, expected in (("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
                                 ("Referrer-Policy", "no-referrer")):
            if headers.get(header) != expected:
                raise ValueError("Missing security header: " + header)
        if "frame-ancestors 'none'" not in headers.get("Content-Security-Policy", ""):
            raise ValueError("Missing frame-ancestors CSP")
        if "noindex" not in headers.get("X-Robots-Tag", ""):
            raise ValueError("Staging must discourage indexing")
        for path in ("/chat", "/find", "/posts/1", "/login", "/register", "/admin/administrators"):
            route_headers, content = request("GET", path)
            if "text/html" not in route_headers.get("Content-Type", "") or content != index:
                raise ValueError("SPA route did not return the same index")
        _, health = request("GET", "/api/health")
        if json.loads(health).get("status") != "ok":
            raise ValueError("Unexpected API health response")
        request("GET", "/api/auth/me", expected=401)
        if args.exercise_test_user:
            username = "stage-" + secrets.token_hex(6)
            password = secrets.token_hex(24)
            _, registered = request("POST", "/api/auth/register", {"username": username, "displayName": "Staging fixture",
                                     "password": password, "role": "SUPER_ADMIN"})
            if json.loads(registered)["role"] != "USER":
                raise ValueError("Registration must default to USER")
            _, logged_in = request("POST", "/api/auth/login", {"username": username, "password": password})
            token = json.loads(logged_in)["token"]
            request("GET", "/api/auth/me", token=token)
            request("GET", "/api/admin/dashboard", token=token, expected=403)
            _, created = request("POST", "/api/posts", {"title": "Staging smoke fixture", "content": "Synthetic staging post", "type": "CHAT"}, token)
            post_id = json.loads(created)["id"]
            request("POST", f"/api/posts/{post_id}/comments", {"content": "Synthetic staging reply"}, token)
            request("GET", f"/api/posts/{post_id}/comments", token=token)
        print(json.dumps({"status": "PASS", "scope": "HTTPS/SPA/USER smoke only; no ADMIN/founder/restore claims", "checks": checks}, indent=2))
    except Exception:
        print(json.dumps({"status": "FAIL", "checks": checks, "reason": "HTTPS/HTTP/header/assertion failure; no tokens or response bodies printed"}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
