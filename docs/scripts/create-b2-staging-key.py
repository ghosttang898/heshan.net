#!/usr/bin/env python3
"""Mac-only explicit B2 key creation. Default is offline preview, not execution."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings

BUCKET_ID = "321b7358da54367ead16001a"
BUCKET_NAME = "heshan-staging-backups-001"
PREFIX = "staging/"
CAPS = ["listBuckets", "listFiles", "readFiles", "writeFiles"]
DURATION = 30 * 86400
AUTH_URL = "https://api.backblazeb2.com/b2api/v4/b2_authorize_account"


class SafeError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise SafeError(message)


def api_base(value):
    require(isinstance(value, str), "Missing API endpoint")
    parsed = urllib.parse.urlsplit(value)
    require(parsed.scheme == "https" and parsed.netloc == parsed.hostname
            and re.fullmatch(r"api\d*\.backblazeb2\.com", parsed.hostname or "")
            and parsed.path in ("", "/") and not parsed.query and not parsed.fragment,
            "Unexpected API endpoint; no credentials forwarded")
    return value.rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SafeError("Redirect refused; no credentials forwarded")


def request_json(url, authorization, payload=None):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == "https", "HTTPS required; no credentials sent")
    api_base("https://" + parsed.netloc)
    require(parsed.path in ("/b2api/v4/b2_authorize_account", "/b2api/v4/b2_list_buckets", "/b2api/v4/b2_create_key")
            and not parsed.query and not parsed.fragment, "Unapproved API operation")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": authorization, "Content-Type": "application/json"},
        method="POST" if payload is not None else "GET")
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, "API response too large")
        result = json.loads(raw)
        require(isinstance(result, dict), "Invalid API response")
        return result
    except urllib.error.HTTPError as error:
        raise SafeError("B2 HTTP " + str(error.code) + "; body withheld; no automatic retry") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SafeError("Network/TLS failure; no automatic retry") from None
    except (ValueError, UnicodeError):
        raise SafeError("Invalid API JSON; response withheld") from None


def new_key_payload(account_id):
    return {"accountId": account_id, "keyName": "heshan-staging-backup",
            "bucketIds": [BUCKET_ID], "namePrefix": PREFIX,
            "capabilities": list(CAPS), "validDurationInSeconds": DURATION}


def authorize_and_check(admin_id, admin_secret, api=request_json):
    require(bool(re.fullmatch(r"[A-Za-z0-9]+", admin_id)) and bool(admin_secret)
            and ":" not in admin_id, "Invalid management credential format")
    basic = "Basic " + base64.b64encode((admin_id + ":" + admin_secret).encode()).decode()
    auth = api(AUTH_URL, basic)
    storage = auth.get("apiInfo", {}).get("storageApi", {})
    caps = storage.get("allowed", {}).get("capabilities", [])
    require("writeKeys" in caps and "listBuckets" in caps, "Management credential requires writeKeys and listBuckets")
    require(isinstance(auth.get("accountId"), str) and auth["accountId"]
            and isinstance(auth.get("authorizationToken"), str) and auth["authorizationToken"], "Invalid authorization response")
    base = api_base(storage.get("apiUrl"))
    token = auth["authorizationToken"]
    buckets = api(base + "/b2api/v4/b2_list_buckets", token,
                  {"accountId": auth["accountId"], "bucketId": BUCKET_ID}).get("buckets", [])
    require(len(buckets) == 1 and buckets[0].get("bucketId") == BUCKET_ID
            and buckets[0].get("bucketName") == BUCKET_NAME and buckets[0].get("bucketType") == "allPrivate"
            and buckets[0].get("accountId") == auth["accountId"], "Expected private Staging bucket/account mismatch")
    return base, token, auth["accountId"]


def validate_new_key(result, account_id):
    require(result.get("accountId") == account_id and result.get("keyName") == "heshan-staging-backup"
            and result.get("bucketIds") == [BUCKET_ID] and result.get("namePrefix") == PREFIX,
            "Returned account/bucket/prefix differs; revoke this NEW key manually")
    require(isinstance(result.get("capabilities"), list) and sorted(result["capabilities"]) == sorted(CAPS),
            "Returned permissions differ; do not use this NEW key")
    require(isinstance(result.get("applicationKeyId"), str) and result["applicationKeyId"]
            and isinstance(result.get("applicationKey"), str) and result["applicationKey"], "Missing new key material")
    expiration = result.get("expirationTimestamp")
    now = datetime.now(timezone.utc).timestamp() * 1000
    require(type(expiration) is int and now < expiration <= now + (DURATION + 300) * 1000,
            "Unexpected expiration; do not use this NEW key")


def verify_key_authorization(result, api=request_json):
    basic = "Basic " + base64.b64encode((result["applicationKeyId"] + ":" + result["applicationKey"]).encode()).decode()
    auth = api(AUTH_URL, basic)
    allowed = auth.get("apiInfo", {}).get("storageApi", {}).get("allowed", {})
    buckets = allowed.get("buckets", [])
    require(auth.get("accountId") == result["accountId"] and sorted(allowed.get("capabilities", [])) == sorted(CAPS)
            and allowed.get("namePrefix") == PREFIX and len(buckets) == 1 and buckets[0].get("id") == BUCKET_ID
            and auth.get("applicationKeyExpirationTimestamp") == result["expirationTimestamp"],
            "Actual new-key authorization scope differs; do not use it")


def reserve_output(home):
    require(home.is_absolute() and home.resolve() == home, "Non-aliased home path required")
    config = home / ".config"
    config.mkdir(mode=0o700, exist_ok=True)
    info = config.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not config.is_symlink()
            and not (info.st_mode & 0o022), "Unsafe config parent")
    directory = config / "heshan-backup"
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700 and directory.resolve() == directory, "Private directory must be owned by you, mode 0700")
    name = "b2-staging-" + secrets.token_hex(8) + ".backup-credentials.json"
    folder = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
    finally:
        os.close(folder)
    return directory / name, fd


def save_result(fd, result, verified):
    # Whitelist only NEW key material; never serialize management credentials/tokens.
    safe = {key: result.get(key) for key in ("accountId", "keyName", "applicationKeyId", "applicationKey",
            "capabilities", "bucketIds", "namePrefix", "expirationTimestamp")}
    safe["scope_verification"] = "PASS" if verified else "FAIL_DO_NOT_USE"
    data = json.dumps(safe, indent=2).encode() + b"\n"
    with os.fdopen(os.dup(fd), "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-create", action="store_true")
    args = parser.parse_args()
    preview = {"mode": "CREATE_ONE_KEY" if args.execute_create else "OFFLINE_PREVIEW",
               "bucket": BUCKET_NAME, **new_key_payload("ACCOUNT_FROM_HIDDEN_LOGIN")}
    print(json.dumps(preview, indent=2))
    if not args.execute_create:
        return 0
    require(sys.platform == "darwin" and sys.stdin.isatty() and sys.stdout.isatty(), "Run interactively on your Mac, without sudo/piping")
    require(os.geteuid() != 0, "Do not run with sudo")
    expected = "CREATE " + BUCKET_NAME + " " + PREFIX
    require(input("Type exactly: " + expected + "\n> ") == expected, "Cancelled; no API call")
    warnings.simplefilter("error", getpass.GetPassWarning)
    admin_id = getpass.getpass("Management key ID (hidden): ").strip()
    admin_secret = getpass.getpass("Management application key (hidden; NOT login password): ").strip()
    base, token, account_id = authorize_and_check(admin_id, admin_secret)
    admin_id = admin_secret = ""
    path, fd = reserve_output(Path.home())
    print("Private result file: " + str(path), flush=True)
    attempted = False
    try:
        attempted = True
        result = request_json(base + "/b2api/v4/b2_create_key", token, new_key_payload(account_id))
        token = ""
        try:
            validate_new_key(result, account_id)
            verify_key_authorization(result)
        except Exception:
            save_result(fd, result, False)
            raise
        save_result(fd, result, True)
        print("PASS: one restricted 30-day backup key saved privately. No secrets printed.")
        print("No files uploaded/deleted, no VPS or scheduler changes. Do not paste the private file.")
        return 0
    except Exception:
        if attempted:
            print("Create request may have reached B2. Do NOT retry automatically. Inspect Application Keys; revoke only the newly created key if unusable.", file=sys.stderr)
        raise
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        print("STOP: " + (str(error) if isinstance(error, SafeError) else type(error).__name__) + "; credentials/response withheld", file=sys.stderr)
        raise SystemExit(1)
