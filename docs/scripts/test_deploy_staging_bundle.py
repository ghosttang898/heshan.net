import hashlib
import importlib.util
import io
import json
import os
import stat
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("deploy-staging-bundle.py")
spec = importlib.util.spec_from_file_location("staging_bundle", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BundleSafety(unittest.TestCase):
    def test_public_asset_directories_survive_private_umask(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            bundle.mkdir()
            (bundle / "frontend/assets").mkdir(parents=True)
            (bundle / "frontend/assets/app.js").write_text("fixture")
            release = Path(directory) / "release"
            previous = os.umask(0o077)
            try:
                module.new_directory(release)
                module.copy_public_assets(bundle, release, ["frontend/assets/app.js"])
                for name in ("frontend", "frontend/assets"):
                    self.assertEqual(stat.S_IMODE((release / name).stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE(release.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((release / "frontend/assets/app.js").stat().st_mode), 0o644)
            finally:
                os.umask(previous)

    def test_directory_modes_survive_private_umask(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.umask(0o077)
            try:
                for mode in (0o700, 0o750):
                    path = Path(directory) / str(mode)
                    module.new_directory(path, mode)
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
            finally:
                os.umask(previous)

    def fixture_bundle(self, directory):
        names = {"backend-image.tar", "SOURCE_REVISION", "deploy/postgres-init.sh", "deploy/staging/compose.yml",
                 "deploy/staging/nginx.conf", "docs/scripts/staging.py", "docs/scripts/staging-http-smoke.py",
                 "docs/scripts/deploy-staging-bundle.py", "frontend/index.html", "frontend/release.json",
                 "tls/fullchain.pem", "tls/privkey.pem", "tls/rootCA.pem"}
        root = Path(directory).resolve()
        for name in names:
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic fixture, not a real key")
        (root / "SHA256SUMS").write_text("\n".join(hashlib.sha256((root / name).read_bytes()).hexdigest() + "  " + name for name in sorted(names)) + "\n")
        return root

    def test_complete_bundle_and_checksum_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture_bundle(directory)
            self.assertEqual(len(module.verified_files(root)), 13)
            (root / "frontend/index.html").write_text("changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                module.verified_files(root)

    def test_private_ca_path_traversal_and_duplicate_rejected(self):
        for name in ("tls/rootCA-key.pem", "../outside", "SOURCE_REVISION"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = self.fixture_bundle(directory)
                with (root / "SHA256SUMS").open("a") as output:
                    output.write("0" * 64 + "  " + name + "\n")
                with self.assertRaises(ValueError):
                    module.verified_files(root)

    def test_aliases_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture_bundle(directory)
            (root / "frontend/index.html").unlink()
            (root / "frontend/index.html").symlink_to(root / "SOURCE_REVISION")
            with self.assertRaisesRegex(ValueError, "aliased"):
                module.verified_files(root)

    def test_classic_image_architecture_and_sha_tag_guards(self):
        for architecture, revision, tag, success in (("amd64", "a" * 40, "image:" + "a" * 40, True),
                 ("arm64", "a" * 40, "image:" + "a" * 40, False),
                 ("amd64", "b" * 40, "image:" + "a" * 40, False),
                 ("amd64", "a" * 40, "image:pg-test", False)):
            with self.subTest(architecture=architecture, revision=revision, tag=tag), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "image.tar"
                config = json.dumps({"os": "linux", "architecture": architecture,
                    "config": {"Labels": {"org.opencontainers.image.revision": revision}}}).encode()
                with tarfile.open(path, "w") as archive:
                    for name, value in (("manifest.json", json.dumps([{"Config": "config.json", "RepoTags": [tag]}]).encode()), ("config.json", config)):
                        info = tarfile.TarInfo(name); info.size = len(value)
                        archive.addfile(info, io.BytesIO(value))
                if success:
                    self.assertEqual(module.archive_identities(path, "image:" + "a" * 40, "a" * 40), {"sha256:" + hashlib.sha256(config).hexdigest()})
                else:
                    with self.assertRaises(ValueError):
                        module.archive_identities(path, "image:" + "a" * 40, "a" * 40)

    def test_nonroot_exits_without_any_docker_call(self):
        with patch.object(module.os, "geteuid", return_value=501), patch("sys.argv", [str(SCRIPT), "--bundle", "/tmp/fixture", "--revision", "a" * 40]), patch.object(module.subprocess, "run") as run:
            with self.assertRaises(SystemExit): module.main()
            run.assert_not_called()

    def test_new_directory_never_overwrites_and_source_has_no_global_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new"; module.new_directory(path)
            with self.assertRaises(FileExistsError): module.new_directory(path)
        source = SCRIPT.read_text()
        for forbidden in ("prune", "--initialize-founder", "sudo -S", "usermod", '"rm"', '"down"'):
            self.assertNotIn(forbidden, source)
        self.assertIn('label=com.docker.compose.project=" + PROJECT', source)
        self.assertIn('Existing Staging volume found; first-install refused', source)
        self.assertIn('docker.compose("stop")', source)


if __name__ == "__main__":
    unittest.main()
