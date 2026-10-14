"""Synthetic local TLS-install checks, never reads the VPS private key."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('install-origin-certificate.sh')


class OriginCertificateInstallTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(['bash', '-n', str(SCRIPT)], check=True)

    def test_scope_and_order(self):
        source = SCRIPT.read_text()
        for forbidden in ['systemctl start', 'systemctl reload', 'systemctl enable',
                          'docker compose', 'cat "$key"', 'openssl genpkey']:
            self.assertNotIn(forbidden, source)
        self.assertIn('existing target, no overwrite', source)
        self.assertLess(source.index('certificate/key/CSR mismatch'), source.index('install -m 0600'))
        self.assertIn('nginx -t -c /etc/heshan/nginx-validation.conf', source)

    def test_public_key_comparison_accepts_match_and_rejects_other_key(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'key.pem'
            other = Path(directory) / 'other.pem'
            cert = Path(directory) / 'cert.pem'
            for target in [key, other]:
                subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                                '-out', str(target)], check=True, capture_output=True)
            subprocess.run(['openssl', 'req', '-x509', '-new', '-key', str(key), '-days', '1',
                            '-subj', '/CN=heshan.net', '-out', str(cert)], check=True, capture_output=True)
            public = subprocess.check_output(['openssl', 'x509', '-in', str(cert), '-pubkey', '-noout'])
            cert_der = subprocess.check_output(['openssl', 'pkey', '-pubin', '-outform', 'DER'], input=public)
            fingerprint = hashlib.sha256(cert_der).digest()
            def key_fingerprint(path):
                return hashlib.sha256(subprocess.check_output(
                    ['openssl', 'pkey', '-in', str(path), '-pubout', '-outform', 'DER'])).digest()
            self.assertEqual(fingerprint, key_fingerprint(key))
            self.assertNotEqual(fingerprint, key_fingerprint(other))


if __name__ == '__main__':
    unittest.main()
