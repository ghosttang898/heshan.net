import base64
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("create_key", Path(__file__).with_name("create-b2-staging-key.py"))
key = importlib.util.module_from_spec(spec)
spec.loader.exec_module(key)


def result():
    return {**key.new_key_payload("fixture-account"), "applicationKeyId": "fixtureID",
            "applicationKey": "FAKE_NEW_SECRET", "expirationTimestamp": int(datetime.now(timezone.utc).timestamp() * 1000) + key.DURATION * 1000}


class KeyTest(unittest.TestCase):
    def test_payload_has_only_four_permissions_and_one_bucket(self):
        payload = key.new_key_payload("fixture-account")
        self.assertEqual(payload["capabilities"], ["listBuckets", "listFiles", "readFiles", "writeFiles"])
        self.assertEqual(payload["bucketIds"], [key.BUCKET_ID])
        self.assertEqual(payload["namePrefix"], "staging/")
        self.assertEqual(payload["validDurationInSeconds"], 2592000)
        self.assertNotIn("deleteFiles", json.dumps(payload))

    def test_unexpected_api_endpoints_fail(self):
        for url in ("http://api001.backblazeb2.com", "https://api001.backblazeb2.com.evil.test",
                    "https://user@api001.backblazeb2.com", "https://api001.backblazeb2.com:443",
                    "https://api001.backblazeb2.com/path", "https://api001.backblazeb2.com?query=x"):
            with self.subTest(url=url), self.assertRaises(key.SafeError):
                key.api_base(url)
        self.assertEqual(key.api_base("https://api005.backblazeb2.com"), "https://api005.backblazeb2.com")

    def test_http_or_delete_operation_never_reaches_network(self):
        with patch.object(key.urllib.request, "build_opener") as network:
            for url in ("http://api005.backblazeb2.com/b2api/v4/b2_create_key",
                        "https://api005.backblazeb2.com/b2api/v4/b2_delete_key"):
                with self.assertRaises(key.SafeError):
                    key.request_json(url, "FAKE")
            network.assert_not_called()

    def test_redirect_is_refused(self):
        with self.assertRaises(key.SafeError):
            key.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test")

    def test_readonly_parent_checks_bucket_identity_before_creation(self):
        auth = {"accountId": "fixture-account", "authorizationToken": "FAKE_TOKEN", "apiInfo": {"storageApi": {
            "apiUrl": "https://api005.backblazeb2.com", "allowed": {"capabilities": ["writeKeys", "listBuckets"]}}}}
        bucket = {"accountId": "fixture-account", "bucketId": key.BUCKET_ID, "bucketName": key.BUCKET_NAME, "bucketType": "allPrivate"}
        api = Mock(side_effect=[auth, {"buckets": [bucket]}])
        self.assertEqual(key.authorize_and_check("fixtureID", "FAKE_ADMIN", api)[2], "fixture-account")
        self.assertEqual(api.call_count, 2)
        self.assertNotIn("b2_create_key", str(api.call_args_list))
        self.assertEqual(api.call_args.args[2]["bucketId"], key.BUCKET_ID)
        for field, changed in (("bucketType", "allPublic"), ("bucketName", "production"), ("accountId", "other"), ("bucketId", "other")):
            bad = {**bucket, field: changed}
            with self.subTest(field=field), self.assertRaises(key.SafeError):
                key.authorize_and_check("fixtureID", "FAKE_ADMIN", Mock(side_effect=[auth, {"buckets": [bad]}]))

    def test_parent_without_write_keys_fails_before_bucket_request(self):
        api = Mock(return_value={"apiInfo": {"storageApi": {"allowed": {"capabilities": ["readFiles"]}}}})
        with self.assertRaises(key.SafeError):
            key.authorize_and_check("fixtureID", "FAKE_ADMIN", api)
        self.assertEqual(api.call_count, 1)

    def test_excess_capabilities_wrong_scope_and_permanent_key_rejected(self):
        key.validate_new_key(result(), "fixture-account")
        for field, changed in (("capabilities", key.CAPS + ["deleteFiles"]), ("bucketIds", []),
                               ("namePrefix", ""), ("accountId", "other"), ("expirationTimestamp", None)):
            with self.subTest(field=field), self.assertRaises(key.SafeError):
                key.validate_new_key({**result(), field: changed}, "fixture-account")

    def test_actual_child_authorization_scope_checked(self):
        created = result()
        auth = {"accountId": created["accountId"], "applicationKeyExpirationTimestamp": created["expirationTimestamp"],
                "apiInfo": {"storageApi": {"allowed": {"capabilities": key.CAPS, "namePrefix": "staging/", "buckets": [{"id": key.BUCKET_ID}]}}}}
        key.verify_key_authorization(created, Mock(return_value=auth))
        bad = deepcopy(auth)
        bad["apiInfo"]["storageApi"]["allowed"]["capabilities"] = key.CAPS + ["deleteFiles"]
        with self.assertRaises(key.SafeError):
            key.verify_key_authorization(created, Mock(return_value=bad))

    def test_result_file_private_and_only_new_credential_whitelisted(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            path, fd = key.reserve_output(home)
            try:
                key.save_result(fd, {**result(), "authorizationToken": "FAKE_ADMIN_TOKEN", "adminSecret": "FAKE_ADMIN"}, True)
            finally:
                os.close(fd)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertIn("FAKE_NEW_SECRET", path.read_text())
            self.assertNotIn("FAKE_ADMIN", path.read_text())
            another, other_fd = key.reserve_output(home)
            os.close(other_fd)
            self.assertNotEqual(path, another)

    def test_unsafe_or_symlink_config_directory_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            (home / ".config").mkdir()
            target = home / ".config/heshan-backup"
            target.mkdir(mode=0o755)
            with self.assertRaises(key.SafeError):
                key.reserve_output(home)

    def test_http_error_body_is_not_exposed(self):
        opener = Mock()
        opener.open.side_effect = key.urllib.error.HTTPError(key.AUTH_URL, 401, "FAKE_SECRET", {}, None)
        with patch.object(key.urllib.request, "build_opener", return_value=opener), self.assertRaises(key.SafeError) as failure:
            key.request_json(key.AUTH_URL, "Basic " + base64.b64encode(b"fixture:FAKE_SECRET").decode())
        self.assertNotIn("FAKE_SECRET", str(failure.exception))


if __name__ == "__main__":
    unittest.main()
