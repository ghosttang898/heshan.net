"""Parse Compose with synthetic secrets only; never start production services."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ProductionComposeTests(unittest.TestCase):
    def test_isolated_production_model(self):
        environment = {key: value for key, value in os.environ.items() if not key.startswith('COMPOSE_')}
        environment.update(POSTGRES_DB='heshan_production', POSTGRES_USER='heshan_prod_app',
                           POSTGRES_PASSWORD='synthetic-local-test-password',
                           POSTGRES_ADMIN_PASSWORD='synthetic-local-admin-password',
                           APP_JWT_SECRET='synthetic-local-test-secret',
                           APP_CORS_ALLOWED_ORIGINS='https://heshan.net,https://www.heshan.net',
                           BACKEND_IMAGE='heshan-backend:a67f2bf4ad1765abd48c00856c3e9cd9a94efb9a',
                           BACKUP_REMOTE='', BACKUP_DIR='/var/backups/heshan',
                           RCLONE_CONFIG='/etc/heshan/rclone.conf')
        model = json.loads(subprocess.check_output(['docker', 'compose', '--project-name', 'heshan',
            '--env-file', '/dev/null', '-f', str(ROOT / 'deploy/compose.yml'), 'config', '--format', 'json'],
            env=environment))
        self.assertEqual(model['name'], 'heshan')
        self.assertEqual(model['volumes']['postgres_data']['name'], 'heshan_postgres_data')
        services = model['services']
        for name, memory in [('db', 402653184), ('backend', 805306368), ('proxy', 67108864)]:
            self.assertEqual(services[name]['pull_policy'], 'never', name)
            self.assertEqual(int(services[name]['mem_limit']), memory, name)
            self.assertEqual(services[name]['restart'], 'unless-stopped', name)
        for name in ['db', 'backend']:
            self.assertFalse(services[name].get('ports'), name)
        self.assertEqual(services['proxy']['ports'][0]['host_ip'], '127.0.0.1')
        self.assertEqual(str(services['proxy']['ports'][0]['published']), '8080')
        self.assertEqual(services['db']['environment']['POSTGRES_DB'], 'heshan_production')
        self.assertEqual(services['backend']['environment']['SPRING_PROFILES_ACTIVE'], 'prod')
        self.assertTrue(model['networks']['database']['internal'])
        self.assertTrue(services['backend']['read_only'])
        self.assertEqual(services['backend']['cap_drop'], ['ALL'])
        self.assertTrue(model['networks']['application']['ipam']['config'][0]['subnet'] == '172.30.10.0/24')
        self.assertEqual(services['db']['volumes'][0]['source'], 'postgres_data')


if __name__ == '__main__':
    unittest.main()
