"""Local backup control-flow tests with mocked Docker; no databases contacted."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import unittest

SCRIPT = Path(__file__).with_name('backup-postgresql.sh').read_text()


class BackupTests(unittest.TestCase):
    def run_backup(self, dump_failure=False, upload_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = root / '.env'; env.write_text('# isolated test file\n'); env.chmod(0o600)
            compose = root / 'compose.yml'; compose.write_text('# isolated test configuration\n')
            backup = root / 'backups'; backup.mkdir()
            old = backup / 'heshan-20000101T000000Z.dump'; old.write_text('old')
            os.utime(old, (time.time() - 9 * 86400, time.time() - 9 * 86400))
            unrelated = backup / 'other-file'; unrelated.write_text('keep')
            mocks = ('stat() { printf 600; }\nflock() { return 0; }\n'
                     + 'sha256sum() { printf "fixture-hash  %s\\n" "$1"; }\n'
                     + 'docker() { case "$*" in *" exec "*) '
                     + ('return 7' if dump_failure else 'printf mock-database-dump') + ';; '
                     + '*" run "*) return ' + ('8' if upload_failure else '0') + ';; *) return 0;; esac; }\n'
                     + 'export ENV_FILE=' + shlex.quote(str(env)) + '\n'
                     + 'export COMPOSE_FILE=' + shlex.quote(str(compose)) + '\n'
                     + 'export BACKUP_DIR=' + shlex.quote(str(backup)) + '\n')
            result = subprocess.run(['bash', '-c', mocks + SCRIPT], capture_output=True, text=True)
            return result, old.exists(), unrelated.read_text(), list(backup.glob('heshan-*.dump')), list(backup.glob('*.sha256'))

    def test_success_uploads_before_pruning_and_keeps_unrelated_files(self):
        result, old, unrelated, dumps, checksums = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(old)
        self.assertEqual(unrelated, 'keep')
        self.assertEqual(len(dumps), 1)
        self.assertEqual(len(checksums), 1)

    def test_offsite_failure_fails_job_and_preserves_local_retention(self):
        result, old, _, dumps, _ = self.run_backup(upload_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old)
        self.assertEqual(len(dumps), 2)

    def test_dump_failure_does_not_prune_or_upload(self):
        result, old, _, dumps, _ = self.run_backup(dump_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old)
        self.assertEqual(len(dumps), 1)


if __name__ == '__main__':
    unittest.main()
