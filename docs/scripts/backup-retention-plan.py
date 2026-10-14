#!/usr/bin/env python3
"""Read-only 7-day local retention planner. Never delete files or contact storage."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Optional

DAY = 86400
NAME = re.compile(r"daily-(\d{8}T\d{6}Z)-[0-9a-f]{16}\.dump")


@dataclass(frozen=True)
class Backup:
    name: str
    created: float
    sha256: str
    size: int
    receipt: Optional[dict] = None


def readback_matches(chunks, expected_sha256, expected_size):
    """Use a full decrypted stream, never an ETag or a size-only comparison."""
    digest = hashlib.sha256()
    size = 0
    for chunk in chunks:
        size += len(chunk)
        digest.update(chunk)
    return size == expected_size and digest.hexdigest() == expected_sha256


def plan(records, now, remote_id):
    if not remote_id or any(not NAME.fullmatch(item.name) or not re.fullmatch(r"[0-9a-f]{64}", item.sha256)
                            or item.size <= 0 or item.created > now for item in records):
        raise ValueError("Invalid inventory, clock or approved remote identity")
    if len({item.name for item in records}) != len(records):
        raise ValueError("Duplicate backup identity")
    newest = max(records, key=lambda item: (item.created, item.name), default=None)
    decisions = []
    for item in sorted(records, key=lambda item: (item.created, item.name)):
        reason = "within_7_days"
        eligible = False
        proof = item.receipt or {}
        if item == newest:
            reason = "always_keep_newest_complete_local_backup"
        elif now - item.created >= 7 * DAY:
            valid = (proof.get("status") == "DECRYPTED_READBACK_SHA256_VERIFIED"
                     and proof.get("sha256") == item.sha256 and proof.get("size") == item.size
                     and proof.get("remote_id") == remote_id and proof.get("object_name") == item.name
                     and proof.get("sidecar_verified") is True
                     and type(proof.get("verified_at")) in (int, float)
                     and type(proof.get("uploaded_at")) in (int, float))
            if not valid:
                reason = "missing_or_mismatched_offsite_proof"
            elif not item.created <= proof["uploaded_at"] <= proof["verified_at"] <= now:
                reason = "invalid_receipt_clock"
            elif now - proof["verified_at"] > DAY:
                reason = "remote_readback_must_be_repeated_within_24_hours"
            elif proof["uploaded_at"] + 30 * DAY <= now + DAY:
                reason = "remote_copy_expiring_within_24_hours_or_already_expired"
            else:
                eligible, reason = True, "candidate_only_after_new_owner_approved_cleanup"
        decisions.append({"name": item.name, "eligible_candidate": eligible, "reason": reason})
    return {"mode": "PLAN_ONLY", "deletion_executed": False, "local_days": 7,
            "offsite_days": 30, "decisions": decisions}


def private_regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
        raise ValueError("Unsafe backup/checksum/receipt file")
    return path


def inventory(directory):
    info = directory.lstat()
    if not directory.is_absolute() or directory.resolve() != directory or not stat.S_ISDIR(info.st_mode) \
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Absolute private non-aliased directory required")
    records = []
    for file in directory.iterdir():
        match = NAME.fullmatch(file.name)
        if not match:
            continue  # Historical, partial and unrelated files are never managed.
        private_regular(file)
        size = file.stat().st_size
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        sha = digest.hexdigest()
        sidecar = private_regular(Path(str(file) + ".sha256"))
        if sidecar.read_text().strip() != sha + "  " + file.name:
            raise ValueError("Checksum mismatch; no retention plan authorized")
        receipt_path = Path(str(file) + ".receipt.json")
        receipt = json.loads(private_regular(receipt_path).read_text()) if receipt_path.exists() else None
        if receipt is not None and not isinstance(receipt, dict):
            raise ValueError("Invalid offsite receipt")
        created = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
        records.append(Backup(file.name, created, sha, size, receipt))
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--remote-id", required=True, help="Nonsecret approved storage-account/bucket/prefix identifier")
    args = parser.parse_args()
    print(json.dumps(plan(inventory(args.directory), time.time(), args.remote_id), indent=2))
