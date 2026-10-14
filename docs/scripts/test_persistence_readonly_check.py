import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("persistence_check", ROOT / "persistence-readonly-check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class ReadOnlyCheckTest(unittest.TestCase):
    def test_sql_is_explicit_readonly(self):
        self.assertTrue(check.SQL.startswith("BEGIN READ ONLY;"))
        self.assertTrue(check.SQL.endswith("COMMIT;\n"))
        for word in ("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP", "TRUNCATE"):
            self.assertNotIn(word, check.SQL)

    def test_inspection_does_not_read_container_environment(self):
        self.assertNotIn(".Env", check.FORMAT)
        self.assertNotIn(".Config.Healthcheck", check.FORMAT)
        self.assertIn(".Mounts", check.FORMAT)
        self.assertIn(".HostConfig.RestartPolicy", check.FORMAT)

    def test_command_environment_is_local_socket(self):
        with patch.object(check.subprocess, "run", return_value=Mock(returncode=0, stdout=b"ok")) as run:
            self.assertEqual(check.run(["docker", "inspect", "fixture"]), b"ok")
            self.assertEqual(run.call_args.kwargs["env"]["DOCKER_HOST"], "unix:///var/run/docker.sock")
            self.assertNotIn("DOCKER_CONTEXT", run.call_args.kwargs["env"])

    def test_errors_do_not_echo_sensitive_output(self):
        with patch.object(check.subprocess, "run", return_value=Mock(returncode=1, stderr=b"SECRET", stdout=b"SECRET")):
            with self.assertRaises(ValueError) as failure:
                check.run(["docker", "inspect", "fixture"])
            self.assertNotIn("SECRET", str(failure.exception))

    def test_script_contains_no_restart_restore_or_delete_command(self):
        source = (ROOT / "persistence-readonly-check.py").read_text()
        for command in ('["docker", "restart"', '["docker", "stop"', '["docker", "start"',
                        '["docker", "rm"', '"prune"', '"pg_dump"'):
            self.assertNotIn(command, source)
        self.assertIn('"pg_restore", "--list"', source)
        self.assertNotIn(".write_text(", source)
        self.assertNotIn("mktemp", source)


if __name__ == "__main__":
    unittest.main()
