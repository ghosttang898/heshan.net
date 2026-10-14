from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("retention_policy", ROOT / "backup-retention-plan.py")
policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policy
spec.loader.exec_module(policy)
NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc).timestamp()
REMOTE = "approved-b2-account/staging-prefix"


def backup(days, proof=True):
    created = NOW - days * policy.DAY
    stamp = datetime.fromtimestamp(created, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = "daily-" + stamp + "-0123456789abcdef.dump"
    receipt = {"status": "DECRYPTED_READBACK_SHA256_VERIFIED", "sha256": "a" * 64, "size": 10,
               "remote_id": REMOTE, "object_name": name, "sidecar_verified": True,
               "uploaded_at": created, "verified_at": NOW} if proof else None
    return policy.Backup(name, created, "a" * 64, 10, receipt)


class RetentionTest(unittest.TestCase):
    def decisions(self, *records):
        return policy.plan(records, NOW, REMOTE)["decisions"]

    def test_seven_days_and_newest_copy_protected(self):
        result = self.decisions(backup(8), backup(6), backup(0))
        self.assertEqual([item["eligible_candidate"] for item in result], [True, False, False])
        self.assertFalse(policy.plan([backup(20)], NOW, REMOTE)["decisions"][0]["eligible_candidate"])

    def test_unuploaded_sole_copy_is_never_eligible(self):
        self.assertFalse(self.decisions(backup(20, False), backup(0))[0]["eligible_candidate"])

    def test_mismatched_proof_never_authorizes_cleanup(self):
        for field, value in (("sha256", "b" * 64), ("size", 11), ("remote_id", "different"),
                             ("object_name", "other.dump"), ("sidecar_verified", False), ("status", "UPLOADED_ONLY")):
            old = backup(8)
            receipt = {**old.receipt, field: value}
            with self.subTest(field=field):
                self.assertFalse(self.decisions(replace(old, receipt=receipt), backup(0))[0]["eligible_candidate"])

    def test_stale_or_expiring_remote_proof_is_protected(self):
        old = backup(8)
        stale = replace(old, receipt={**old.receipt, "verified_at": NOW - 2 * policy.DAY})
        self.assertFalse(self.decisions(stale, backup(0))[0]["eligible_candidate"])
        self.assertFalse(self.decisions(backup(29), backup(0))[0]["eligible_candidate"])
        self.assertFalse(self.decisions(backup(31), backup(0))[0]["eligible_candidate"])

    def test_invalid_clocks_are_protected(self):
        old = backup(8)
        for uploaded, verified in ((NOW + 1, NOW), (old.created - 1, NOW), (NOW, NOW + 1)):
            changed = replace(old, receipt={**old.receipt, "uploaded_at": uploaded, "verified_at": verified})
            self.assertFalse(self.decisions(changed, backup(0))[0]["eligible_candidate"])
        with self.assertRaises(ValueError):
            policy.plan([replace(old, created=NOW + 1)], NOW, REMOTE)

    def test_duplicate_backup_identity_fails(self):
        with self.assertRaises(ValueError):
            self.decisions(backup(8), backup(8))

    def test_full_decrypted_readback_hash_and_length(self):
        expected = hashlib.sha256(b"complete").hexdigest()
        self.assertTrue(policy.readback_matches([b"com", b"plete"], expected, 8))
        self.assertFalse(policy.readback_matches([b"com"], expected, 8))
        self.assertFalse(policy.readback_matches([b"different"], expected, 9))

    def test_empty_plan_has_no_deletion(self):
        self.assertEqual(policy.plan([], NOW, REMOTE)["decisions"], [])
        self.assertFalse(policy.plan([], NOW, REMOTE)["deletion_executed"])

    def test_inventory_keeps_historical_files_and_is_readonly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            historical = root / "preupdate-20261013.dump"
            historical.write_bytes(b"untouched")
            managed = root / backup(8).name
            managed.write_bytes(b"fixture")
            managed.chmod(0o600)
            sha = hashlib.sha256(b"fixture").hexdigest()
            sidecar = Path(str(managed) + ".sha256")
            sidecar.write_text(sha + "  " + managed.name + "\n")
            sidecar.chmod(0o600)
            before = set(root.iterdir())
            items = policy.inventory(root)
            self.assertEqual(len(items), 1)
            policy.plan(items, NOW, REMOTE)
            self.assertEqual(set(root.iterdir()), before)
            self.assertEqual(historical.read_bytes(), b"untouched")

    def test_unsafe_permissions_symlinks_hardlinks_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "file"
            file.write_bytes(b"fixture")
            file.chmod(0o644)
            with self.assertRaises(ValueError):
                policy.private_regular(file)
            file.chmod(0o600)
            linked = root / "linked"
            linked.symlink_to(file)
            with self.assertRaises(ValueError):
                policy.private_regular(linked)
            os.link(file, root / "hardlinked")
            with self.assertRaises(ValueError):
                policy.private_regular(file)


if __name__ == "__main__":
    unittest.main()
