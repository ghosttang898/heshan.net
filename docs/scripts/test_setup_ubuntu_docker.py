"""Local isolated checks; never execute the installer or system commands."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).with_name('setup-ubuntu-docker.sh').read_text()
SWAP_CODE, SSH_CODE, MERGE_CODE = re.findall(r"<<'PY'\n(.*?)\nPY", SCRIPT, re.S)
ROLLBACK = SCRIPT[SCRIPT.index('rollback_on_exit() {'):SCRIPT.index('trap rollback_on_exit EXIT')]


class SetupSafetyTests(unittest.TestCase):
    def create_swap(self, path, size=4096):
        with patch.object(sys, 'argv', ['create', str(path), str(size)]):
            exec(compile(SWAP_CODE, 'swap-create', 'exec'), {})

    def test_swap_creation_is_exclusive_and_repeat_preserves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'swap'
            self.create_swap(path)
            self.assertEqual(path.read_bytes(), bytes(4096))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_bytes(b'existing content')
            with self.assertRaises(SystemExit):
                self.create_swap(path)
            self.assertEqual(path.read_bytes(), b'existing content')

    def test_swap_creation_rejects_symlink_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            target.write_bytes(b'keep')
            link = Path(directory) / 'swap'
            link.symlink_to(target)
            with self.assertRaises(SystemExit):
                self.create_swap(link)
            self.assertEqual(target.read_bytes(), b'keep')
            self.assertTrue(link.is_symlink())

    def test_swap_write_failure_preserves_partial_file_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'swap'
            write = os.write
            calls = 0

            def fail_after_partial_write(fd, data):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return write(fd, data[:7])
                raise OSError('simulated disk full')

            with patch.object(os, 'write', side_effect=fail_after_partial_write), self.assertRaises(SystemExit):
                self.create_swap(path)
            self.assertEqual(path.stat().st_size, 7)
            before = path.read_bytes()
            with self.assertRaises(SystemExit):
                self.create_swap(path)
            self.assertEqual(path.read_bytes(), before)

    def test_swap_handles_short_writes_and_sync_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            write = os.write
            path = Path(directory) / 'swap'
            with patch.object(os, 'write', side_effect=lambda fd, data: write(fd, data[:127])):
                self.create_swap(path)
            self.assertEqual(path.read_bytes(), bytes(4096))
            failed = Path(directory) / 'failed'
            with patch.object(os, 'fsync', side_effect=OSError('simulated sync failure')), self.assertRaises(SystemExit):
                self.create_swap(failed)
            self.assertTrue(failed.exists())

    def test_swap_checks_precede_install_and_old_dd_flag_is_gone(self):
        self.assertNotIn('oflag=excl', SCRIPT)
        self.assertLess(SCRIPT.index('        validate_swap_file'), SCRIPT.index('\napt-get update'))
        self.assertIn('if [[ $swap_was_present == false ]]; then', SCRIPT)

    def test_incomplete_swap_preflight_rejects_without_modification(self):
        validator = SCRIPT[SCRIPT.index('validate_swap_file() {'):SCRIPT.index('[[ $# == 0 ]]')]
        for metadata, signature, valid in [('7:0:600', 'swap', False),
                                           ('4096:0:600', '', False),
                                           ('4096:1000:600', 'swap', False),
                                           ('4096:0:644', 'swap', False),
                                           ('4096:0:600', 'swap', True)]:
            with self.subTest(metadata=metadata, signature=signature), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'swap'
                path.write_text('preserve incomplete content')
                command = ('set -euo pipefail\ndie() { exit 19; }\n'
                           + validator + '\n'
                           + 'swap=' + shlex.quote(str(path)) + '\nswap_bytes=4096\n'
                           + 'stat() { printf "%s" ' + shlex.quote(metadata) + '; }\n'
                           + 'blkid() { printf "%s" ' + shlex.quote(signature) + '; }\n'
                           + 'validate_swap_file\n')
                result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0 if valid else 19)
                self.assertEqual(path.read_text(), 'preserve incomplete content')

    def merge(self, original):
        output = []
        with patch.object(Path, 'exists', return_value=original is not None), \
                patch.object(Path, 'read_text', return_value=json.dumps(original)), \
                patch.object(Path, 'write_text', side_effect=output.append), \
                patch.object(sys, 'argv', ['merge', '/unused/output']):
            exec(compile(MERGE_CODE, 'config-merge', 'exec'), {})
        return json.loads(output[0])

    def test_merge_preserves_settings_and_is_repeatable(self):
        original = {'debug': False, 'log-opts': {'labels': 'site'}}
        result = self.merge(original)
        self.assertFalse(result['debug'])
        self.assertEqual(result['log-opts']['labels'], 'site')
        self.assertEqual(result['log-opts']['max-size'], '10m')
        self.assertEqual(result['log-opts']['max-file'], '3')
        self.assertEqual(self.merge(result), result)
        self.assertEqual(self.merge(None)['log-driver'], 'json-file')

    def test_custom_or_invalid_configuration_is_rejected(self):
        for original in [[], {'hosts': ['tcp://0.0.0.0:2375']},
                         {'log-driver': 'local'}, {'log-opts': []},
                         {'log-opts': {'max-size': '50m'}},
                         {'log-opts': {'max-file': '5'}}]:
            with self.subTest(original=original), self.assertRaises(SystemExit):
                self.merge(original)

    def test_connection_addresses_and_ports(self):
        for args, valid in [(['8.8.8.8', '12345', '165.232.156.104', '22'], True),
                            (['2001:db8::1', '12345', '2001:db8::2', '22'], True),
                            (['not-an-ip', '12345', '8.8.8.8', '22'], False),
                            (['8.8.8.8', '0', '8.8.4.4', '22'], False),
                            (['8.8.8.8', '12345', '8.8.4.4', '65536'], False)]:
            with self.subTest(args=args), patch.object(sys, 'argv', ['check', *args]):
                if valid:
                    exec(compile(SSH_CODE, 'ssh-check', 'exec'), {})
                else:
                    with self.assertRaises(SystemExit):
                        exec(compile(SSH_CODE, 'ssh-check', 'exec'), {})

    def test_missing_or_malformed_connection_stops(self):
        check = SCRIPT[SCRIPT.index('connection=${SSH_CONNECTION:-}'):SCRIPT.index('python3 - "$client"')]
        for value in ['', '8.8.8.8', '8.8.8.8 12345 8.8.4.4 22 extra',
                      '8.8.8.8 12345 8.8.4.4 22\nextra']:
            with self.subTest(value=value):
                result = subprocess.run(['bash', '-c', 'set -euo pipefail\ndie() { exit 17; }\n'
                                         + 'SSH_CONNECTION=' + shlex.quote(value) + '\n' + check],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 17)

    def test_rollback_restores_removes_or_preserves_external_change(self):
        for original_exists, externally_changed in [(True, False), (False, False),
                                                    (True, True), (False, True)]:
            with self.subTest(original=original_exists, external=externally_changed), \
                    tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                current = root / 'current.json'
                current.write_text('external' if externally_changed else 'generated')
                (root / 'daemon.json').write_text('generated')
                if original_exists:
                    (root / 'daemon.json.before').write_text('original')
                code = ROLLBACK.replace('/etc/docker/daemon.json', str(current))
                command = ('set -euo pipefail\n' + code + '\n'
                           + 'systemctl() { return 0; }\n'
                           + 'work=' + shlex.quote(directory) + '\n'
                           + 'rollback_pending=true\n'
                           + 'daemon_existed=' + str(original_exists).lower() + '\n'
                           + 'trap rollback_on_exit EXIT\nexit 23\n')
                result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
                self.assertEqual(result.returncode, 23)
                if externally_changed:
                    self.assertEqual(current.read_text(), 'external')
                elif original_exists:
                    self.assertEqual(current.read_text(), 'original')
                else:
                    self.assertFalse(current.exists())

    def test_swap_creation_failure_triggers_daemon_rollback(self):
        creator = SCRIPT[SCRIPT.index('create_swap_file() {'):SCRIPT.index('validate_swap_file() {')]
        for existed in [True, False]:
            with self.subTest(original=existed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                current = root / 'current.json'
                current.write_text('generated')
                (root / 'daemon.json').write_text('generated')
                if existed:
                    (root / 'daemon.json.before').write_text('original')
                swap = root / 'swap'
                swap.write_text('keep existing Swap file')
                command = ('set -euo pipefail\n'
                           + ROLLBACK.replace('/etc/docker/daemon.json', str(current)) + '\n'
                           + creator + '\nsystemctl() { return 0; }\n'
                           + 'work=' + shlex.quote(directory) + '\nrollback_pending=true\n'
                           + 'daemon_existed=' + str(existed).lower() + '\n'
                           + 'trap rollback_on_exit EXIT\n'
                           + 'create_swap_file ' + shlex.quote(str(swap)) + ' 4096\n')
                result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(swap.read_text(), 'keep existing Swap file')
                if existed:
                    self.assertEqual(current.read_text(), 'original')
                else:
                    self.assertFalse(current.exists())

    def test_security_checks_precede_installation(self):
        first_install = SCRIPT.index('\napt-get update')
        self.assertLess(SCRIPT.index('root_effective='), first_install)
        self.assertLess(SCRIPT.index("pubkeyauthentication yes'"), first_install)

    def test_ubuntu_swap_capacity_formats_and_header_page(self):
        helpers = SCRIPT[SCRIPT.index('swap_capacity_bytes() {'):SCRIPT.index('create_swap_file() {')]
        # Observed Ubuntu 24.04 output. swapon's explicit SIZE column removes
        # the heading and other columns; the installer must request that form.
        observed = ('NAME             TYPE       SIZE   USED PRIO\n'
                    '/swapfile-heshan file 1073737728 274432   -2\n')
        size_column = observed.splitlines()[1].split()[2] + '\n'
        cases = [(size_column, 4096, True), ('', 4096, False),
                 ('536866816\n', 4096, False), ('1073733632\n', 4096, False),
                 ('1073676288\n', 65536, True),
                 ('1073737728\n1073737728\n', 4096, True),
                 ('1024M\n', 4096, False), (observed, 4096, False)]
        for output, page_size, valid in cases:
            with self.subTest(output=output, page_size=page_size):
                command = ('set -euo pipefail\ndie() { exit 21; }\n'
                           + helpers + '\n'
                           + 'swapon() { [[ "$*" == "--show=SIZE --bytes --noheadings --raw" ]] || return 22; '
                           + 'printf "%s" ' + shlex.quote(output) + '; }\n'
                           + 'swap_min_usable_bytes=$((1073741824 - ' + str(page_size) + '))\n'
                           + 'verify_swap_capacity\n')
                result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
                if valid:
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0)
        proc_row = '/swapfile-heshan file 1048572 268 -2'
        self.assertEqual(int(proc_row.split()[2]) * 1024, int(size_column))
        self.assertNotIn('--output SIZE', helpers)

    def test_active_swap_preflight_uses_same_header_aware_threshold(self):
        self.assertIn('active_swap=$(swap_capacity_bytes)', SCRIPT)
        self.assertIn('active_swap < swap_min_usable_bytes', SCRIPT)
        self.assertNotIn("awk 'NR>1 {total += $3 * 1024}", SCRIPT)


if __name__ == '__main__':
    unittest.main()
