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
    def run_backup(self, dump_failure=False, upload_failure=False, offsite=False,
                   checksum_failure=False, archive_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = root / '.env'; env.write_text('# isolated test file\n'); env.chmod(0o600)
            compose = root / 'compose.yml'; compose.write_text('# isolated test configuration\n')
            backup = root / 'backups'; backup.mkdir()
            old = backup / 'heshan-20000101T000000Z.dump'; old.write_text('old')
            os.utime(old, (time.time() - 9 * 86400, time.time() - 9 * 86400))
            unrelated = backup / 'other-file'; unrelated.write_text('keep')
            mocks = ('stat() { printf 600; }\nflock() { return 0; }\n'
                     + 'sha256sum() { if [[ $1 == -c ]]; then return '
                     + ('9' if checksum_failure else '0')
                     + '; fi; printf "fixture-hash  %s\\n" "$1"; }\n'
                     + 'docker() { case "$*" in *"pg_restore --list"*) '
                     + ('return 10' if archive_failure else 'printf mock-archive-list')
                     + ';; *" exec "*) '
                     + ('return 7' if dump_failure else 'printf mock-database-dump') + ';; '
                     + '*" run "*) printf "OFFSITE_CALLED\\n"; return ' + ('8' if upload_failure else '0') + ';; *) return 0;; esac; }\n'
                     + 'export BACKUP_OFFSITE=' + ('1' if offsite else '0') + '\n'
                     + 'export ENV_FILE=' + shlex.quote(str(env)) + '\n'
                     + 'export COMPOSE_FILE=' + shlex.quote(str(compose)) + '\n'
                     + 'export BACKUP_DIR=' + shlex.quote(str(backup)) + '\n')
            result = subprocess.run(['bash', '-c', mocks + SCRIPT], capture_output=True, text=True)
            return result, old.exists(), unrelated.read_text(), list(backup.glob('heshan-*.dump')), list(backup.glob('*.sha256'))

    def test_upload_success_does_not_authorize_unverified_old_backup_deletion(self):
        result, old, unrelated, dumps, checksums = self.run_backup(offsite=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(old)
        self.assertEqual(unrelated, 'keep')
        self.assertEqual(len(dumps), 2)
        self.assertEqual(len(checksums), 1)

    def test_offsite_failure_fails_job_and_preserves_local_retention(self):
        result, old, _, dumps, _ = self.run_backup(upload_failure=True, offsite=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old)
        self.assertEqual(len(dumps), 2)

    def test_dump_failure_does_not_prune_or_upload(self):
        result, old, _, dumps, _ = self.run_backup(dump_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old)
        self.assertEqual(len(dumps), 1)

    def test_local_default_never_calls_offsite_even_if_upload_would_fail(self):
        result, old, _, dumps, _ = self.run_backup(upload_failure=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('OFFSITE_CALLED', result.stdout)
        self.assertIn('offsite NOT RUN', result.stdout)
        self.assertTrue(old)
        self.assertEqual(len(dumps), 2)

    def test_checksum_failure_preserves_dump_and_never_uploads(self):
        result, old, _, dumps, _ = self.run_backup(checksum_failure=True, offsite=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old)
        self.assertEqual(len(dumps), 2)
        self.assertNotIn('OFFSITE_CALLED', result.stdout)

    def test_archive_failure_preserves_dump_and_never_reports_success(self):
        result, old, _, dumps, _ = self.run_backup(archive_failure=True, offsite=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old)
        self.assertEqual(len(dumps), 2)
        self.assertNotIn('OFFSITE_CALLED', result.stdout)
        self.assertNotIn('PASS:', result.stdout)


if __name__ == '__main__':
    unittest.main()
