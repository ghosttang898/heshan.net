"""Execute the logging script locally with mocked Docker/systemd and temp paths."""
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('configure-docker-logging.sh').read_text()


class DockerLoggingTests(unittest.TestCase):
    def run_script(self, original=None, running=False, restart_failure=False,
                   validation_failure=False, driver='json-file', flags='', second_run=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docker_dir = root / 'docker'
            docker_dir.mkdir()
            config = docker_dir / 'daemon.json'
            if original is not None:
                config.write_text(json.dumps(original))
                config.chmod(0o600)
            before = config.read_bytes() if config.exists() else None
            script = SCRIPT.replace('[[ $EUID == 0 ]]', '[[ 1 == 1 ]]')
            script = script.replace('/etc/docker', str(docker_dir))
            script = script.replace('/var/tmp', str(root))
            script = script.replace('/run/lock/heshan-docker-setup.lock', str(root / 'lock'))
            log = root / 'operations'
            failed = root / 'failed-once'
            mocks = ('export SUDO_USER=tester\n'
                     + 'flock() { return 0; }\n'
                     + 'systemctl() { printf "%s\\n" "$*" >> ' + shlex.quote(str(log)) + '; '
                     + 'if [[ $1 == show ]]; then printf "%s" ' + shlex.quote(flags) + '; fi; '
                     + ('if [[ $1 == restart && ! -e ' + shlex.quote(str(failed))
                        + ' ]]; then touch ' + shlex.quote(str(failed)) + '; return 1; fi; ' if restart_failure else '')
                     + 'return 0; }\n'
                     + 'docker() { case $3 in version) return 0;; '
                     + 'info) printf "%s" ' + shlex.quote(driver) + ';; '
                     + 'ps) ' + ('printf container-id' if running else ':') + ';; '
                     + '*) return 99;; esac; }\n'
                     + 'dockerd() { return ' + ('1' if validation_failure else '0') + '; }\n')
            command = mocks + script
            result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
            first_operations = log.read_text() if log.exists() else ''
            if second_run and result.returncode == 0:
                log.write_text('')
                result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
            operations = log.read_text() if log.exists() else ''
            after = config.read_bytes() if config.exists() else None
            backups = list(root.glob('heshan-docker-logging.*/daemon.json.before'))
            return result, before, after, operations, first_operations, [p.read_bytes() for p in backups], config.stat().st_mode & 0o777 if config.exists() else None

    def test_missing_config_created(self):
        result, _, after, operations, _, _, mode = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(after), {'log-driver': 'json-file', 'log-opts': {'max-size': '10m', 'max-file': '3'}})
        self.assertIn('restart docker', operations)
        self.assertEqual(mode, 0o644)

    def test_custom_settings_backed_up_and_preserved(self):
        original = {'debug': False, 'log-opts': {'labels': 'site'}, 'dns': ['1.1.1.1']}
        result, before, after, _, _, backups, mode = self.run_script(original)
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(after)
        self.assertFalse(config['debug'])
        self.assertEqual(config['dns'], original['dns'])
        self.assertEqual(config['log-opts']['labels'], 'site')
        self.assertIn(before, backups)
        self.assertEqual(mode, 0o600)

    def test_conflicts_leave_config_unchanged(self):
        for original in [[], {'log-driver': 'local'}, {'log-opts': []},
                         {'log-opts': {'max-file': 3}}, {'log-opts': {'max-size': '50m'}}]:
            with self.subTest(original=original):
                result, before, after, operations, _, _, _ = self.run_script(original)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(after, before)
                self.assertNotIn('restart docker', operations)

    def test_running_containers_prevent_changes(self):
        result, before, after, operations, _, _, _ = self.run_script({'debug': False}, running=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(after, before)
        self.assertNotIn('restart docker', operations)

    def test_validation_failure_prevents_changes(self):
        result, before, after, operations, _, _, _ = self.run_script(validation_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(after, before)
        self.assertNotIn('restart docker', operations)

    def test_restart_failure_rolls_back_existing_or_new_file(self):
        for original in [None, {'debug': False}]:
            with self.subTest(original=original):
                result, before, after, operations, _, _, _ = self.run_script(original, restart_failure=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(after, before)
                self.assertEqual(operations.count('restart docker'), 2)

    def test_repeat_run_does_not_restart_or_rewrite(self):
        result, _, after, operations, first, _, _ = self.run_script(second_run=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('restart docker', first)
        self.assertNotIn('restart docker', operations)
        self.assertEqual(json.loads(after)['log-opts']['max-file'], '3')

    def test_matching_config_is_not_rewritten_even_with_containers(self):
        original = {'debug': False, 'log-driver': 'json-file',
                    'log-opts': {'max-size': '10m', 'max-file': '3'}}
        result, before, after, operations, _, _, _ = self.run_script(original, running=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(after, before)
        self.assertNotIn('restart docker', operations)

    def test_custom_runtime_driver_or_startup_flags_are_rejected(self):
        for options in [{'driver': 'local'}, {'flags': '--config-file /custom.json'}, {'flags': '--log-opt max-file=8'}]:
            with self.subTest(options=options):
                result, before, after, operations, _, _, _ = self.run_script(**options)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(after, before)
                self.assertNotIn('restart docker', operations)


if __name__ == '__main__':
    unittest.main()
