"""Local-only Nginx tests. No VPS, DNS, production keys or database access."""
import http.client
import ipaddress
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'deploy/nginx-site-https.conf.example'
TRUST = ROOT / 'deploy/cloudflare-realip.conf.example'


class ProductionNginxTests(unittest.TestCase):
    def test_only_explicit_cloudflare_networks_are_trusted(self):
        networks = [ipaddress.ip_network(line.split()[1].rstrip(';'))
                    for line in TRUST.read_text().splitlines() if line.startswith('set_real_ip_from ')]
        self.assertEqual(len(networks), 22)
        self.assertTrue(all(network.prefixlen > 0 for network in networks))
        self.assertFalse(any(ipaddress.ip_address('8.8.8.8') in network for network in networks
                             if network.version == 4))

    def test_security_and_same_origin_contract(self):
        content = CONFIG.read_text()
        for expected in ['CF-Connecting-IP', 'proxy_set_header X-Forwarded-For $remote_addr;',
                         'proxy_set_header X-Forwarded-Proto https;', 'access_log off;',
                         "frame-ancestors 'none'", 'https://static.cloudflareinsights.com',
                         'ssl_protocols TLSv1.2 TLSv1.3;', 'proxy_hide_header Cache-Control;']:
            self.assertIn(expected, content)
        self.assertNotIn('preload', content)
        self.assertNotIn('noindex', content)

    def test_nginx_syntax_and_real_https_routes_locally(self):
        self.assertIsNotNone(shutil.which('docker'), 'Local Docker required; not a silent skip')
        with tempfile.TemporaryDirectory(prefix='heshan-nginx-test-') as directory:
            root = Path(directory)
            site = root / 'site'; site.mkdir()
            (site / 'index.html').write_text('MVP_TEST_INDEX')
            (site / 'assets').mkdir()
            (site / 'assets/app-test.js').write_text('console.log("fixture");')
            tls = root / 'tls'; tls.mkdir()
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                            '-subj', '/CN=heshan.net', '-keyout', str(tls / 'privkey.pem'),
                            '-out', str(tls / 'fullchain.pem')], check=True, capture_output=True)
            # Test-only echo proves an untrusted caller cannot forge CF-Connecting-IP.
            config = root / 'site.conf'
            config.write_text(CONFIG.read_text().replace('    location = /api {',
                '    location = /__test_ip { return 200 "$remote_addr"; }\n    location = /api {'))
            # Docker Desktop cannot reliably read macOS cloud-backed bind mounts.
            trust = root / 'cloudflare-realip.conf'
            trust.write_bytes(TRUST.read_bytes())
            name = 'heshan-local-nginx-' + uuid.uuid4().hex[:12]
            common = ['docker', 'run', '--memory', '64m', '--cpus', '0.25', '--pids-limit', '40',
                      '--read-only', '--security-opt', 'no-new-privileges:true',
                      '--tmpfs', '/var/cache/nginx', '--tmpfs', '/var/run', '--tmpfs', '/tmp',
                      '--tmpfs', '/var/log/nginx']
            for source, target in [(config, '/etc/nginx/conf.d/default.conf'),
                                   (trust, '/etc/nginx/heshan-cloudflare-realip.conf'),
                                   (tls, '/etc/heshan/tls'),
                                   (site, '/srv/heshan/frontend-current')]:
                common += ['--mount', f'type=bind,src={source},dst={target},readonly']
            syntax = subprocess.run(common + ['--rm', '--network', 'none', '--entrypoint', 'nginx',
                                     'nginx:stable-alpine', '-t'], capture_output=True, text=True)
            self.assertEqual(syntax.returncode, 0, syntax.stderr)
            started = False
            try:
                subprocess.run(common + ['--name', name, '-d', '-p', '127.0.0.1::443',
                                         '--entrypoint', 'nginx', 'nginx:stable-alpine',
                                         '-g', 'daemon off;'], check=True, capture_output=True)
                started = True
                data = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
                port = int(data['NetworkSettings']['Ports']['443/tcp'][0]['HostPort'])

                def request(path, extra=None):
                    connection = http.client.HTTPSConnection('127.0.0.1', port, timeout=5,
                        context=ssl._create_unverified_context())
                    connection.request('GET', path, headers={'Host': 'heshan.net', **(extra or {})})
                    response = connection.getresponse()
                    result = response.status, dict(response.getheaders()), response.read().decode()
                    connection.close()
                    return result

                for attempt in range(20):
                    try:
                        request('/'); break
                    except OSError:
                        if attempt == 19: raise
                        time.sleep(0.2)
                for path in ['/', '/chat', '/find', '/login', '/register', '/admin', '/posts/1']:
                    status, headers, body = request(path)
                    self.assertEqual(status, 200, path)
                    self.assertEqual(body, 'MVP_TEST_INDEX')
                    self.assertEqual(headers.get('Cache-Control'), 'no-store')
                    self.assertEqual(headers.get('X-Frame-Options'), 'DENY')
                status, headers, _ = request('/assets/app-test.js')
                self.assertEqual(status, 200)
                self.assertIn('immutable', headers['Cache-Control'])
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                for path in ['/assets/missing.js', '/.env', '/api']:
                    status, headers, _ = request(path)
                    self.assertEqual(status, 404)
                    self.assertEqual(headers['Cache-Control'], 'no-store')
                status, headers, _ = request('/api/health')
                self.assertEqual(status, 502)  # No application in this isolated fixture.
                self.assertEqual(headers['Cache-Control'], 'no-store')
                _, _, peer = request('/__test_ip', {'CF-Connecting-IP': '8.8.8.8',
                                                    'X-Forwarded-For': '8.8.8.8'})
                self.assertNotEqual(peer, '8.8.8.8')
            finally:
                if started:
                    subprocess.run(['docker', 'stop', '--time', '5', name], check=True, capture_output=True)
                    subprocess.run(['docker', 'rm', name], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
