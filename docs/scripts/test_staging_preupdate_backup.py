from pathlib import Path
import os
import subprocess
import unittest

SCRIPT = Path(__file__).with_name("staging-preupdate-backup.sh")


class PreupdateBackupSafety(unittest.TestCase):
    def test_bash_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode, 0)

    def test_missing_approval_exits_before_docker(self):
        result = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("owner approval", result.stderr)

    @unittest.skipIf(os.geteuid() == 0, "Do not run an approved root operation in a local guard test")
    def test_nonroot_cannot_execute_backup(self):
        result = subprocess.run(["bash", str(SCRIPT), "--execute-backup"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)

    def test_no_lifecycle_restore_or_cleanup_commands(self):
        source = SCRIPT.read_text()
        for prohibited in ("compose up", "compose stop", "docker restart", "docker rm", "volume rm", "prune", "--initialize-founder", "init-env", "sudo -S"):
            self.assertNotIn(prohibited, source)
        self.assertIn("pg_restore --list", source)
        self.assertIn("BEGIN READ ONLY", source)
        self.assertIn("baseline-before.txt", source)
        self.assertIn("baseline-after.txt", source)
        self.assertIn("mv -n", source)
        self.assertIn("trap finish EXIT", source)


if __name__ == "__main__":
    unittest.main()
