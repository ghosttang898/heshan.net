"""Local synthetic CSR verification only; no production key or server access."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('prepare-origin-csr.sh')


class OriginCsrTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(['bash', '-n', str(SCRIPT)], check=True)

    def test_scope_and_private_key_not_printed(self):
        source = SCRIPT.read_text()
        self.assertIn('chmod 0600 /etc/heshan/tls/privkey.pem', source)
        self.assertIn('cat /etc/heshan/tls/origin.csr', source)
        self.assertNotIn('cat /etc/heshan/tls/privkey.pem', source)
        self.assertNotIn('systemctl start', source)
        self.assertNotIn('docker compose', source)
        self.assertNotIn('curl', source)
        self.assertIn('existing TLS material', source)
        self.assertIn('mkdir -m 0700 /etc/heshan/tls/.csr-preparation-lock', source)

    def test_synthetic_csr_has_both_hostnames_and_matches_key(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'key.pem'
            csr = Path(directory) / 'origin.csr'
            subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                            '-out', str(key)], check=True, capture_output=True)
            subprocess.run(['openssl', 'req', '-new', '-sha256', '-key', str(key), '-subj', '/CN=heshan.net',
                            '-addext', 'subjectAltName=DNS:heshan.net,DNS:www.heshan.net',
                            '-out', str(csr)], check=True, capture_output=True)
            subprocess.run(['openssl', 'req', '-in', str(csr), '-verify', '-noout'], check=True, capture_output=True)
            text = subprocess.check_output(['openssl', 'req', '-in', str(csr), '-text', '-noout'], text=True)
            self.assertIn('DNS:heshan.net, DNS:www.heshan.net', text)
            public = subprocess.check_output(['openssl', 'req', '-in', str(csr), '-pubkey', '-noout'])
            self.assertEqual(public, subprocess.check_output(['openssl', 'pkey', '-in', str(key), '-pubout']))


if __name__ == '__main__':
    unittest.main()
