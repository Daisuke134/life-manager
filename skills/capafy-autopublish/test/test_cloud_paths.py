"""Host boundaries of the existing Capafy entries; providers are local fixtures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class CloudPathsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / 'release'
        self.home = self.base / 'owner-home'
        self.state = self.base / 'tenant-a'
        self.workspace = self.state / 'build'
        self.home.mkdir()
        self.workspace.mkdir(parents=True)
        for relative in ['skills/self/capafy-loop/capafy-loop-daily.sh',
                         'skills/capafy-autopublish/scripts/daily_loop.sh']:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.env = {'PATH': os.environ['PATH'], 'HOME': str(self.home),
                    'LM_RUNTIME_HOST': 'maritime', 'LM_RUNTIME_TENANT_ID': 'tenant-a',
                    'LIFE_MANAGER_OCCURRENCE_ID': 'occurrence-1', 'LM_RUNTIME_DATE_KEY': '2026-10-20',
                    'LIFE_MANAGER_REPO': str(self.repo), 'LIFE_MANAGER_STATE_HOME': str(self.state),
                    'CAPAFY_STATE_DIR': str(self.state / 'publisher'),
                    'LIFE_MANAGER_BUILD_WORKSPACE': str(self.workspace),
                    'CAPAFY_CATALOG_DIR': str(self.workspace / 'catalog')}
        self.marker = self.home / 'private-env-read'
        for env_file in [self.home / '.local/state/life-manager/.env', self.state / '.env']:
            env_file.parent.mkdir(parents=True, exist_ok=True)
            env_file.write_text('printf bad > "$HOME/private-env-read"\n')

    def run_entry(self, relative, env=None):
        return subprocess.run(['bash', str(self.repo / relative)], cwd=self.repo,
                              env=env or self.env, capture_output=True, text=True, timeout=5)

    def fixture_drainer(self):
        scripts = self.repo / 'skills/capafy-autopublish/scripts'
        key = scripts / 'key_health_gate.sh'
        key.write_text('#!/usr/bin/env bash\necho HOST_KEY_OK\n')
        key.chmod(0o755)
        (scripts / 'reconcile_ledger.py').write_text('pass\n')
        (scripts / 'inventory_status.py').write_text('print(\'VERDICT=DRAINED\\n{}\')\n')
        (scripts / 'candidate_backlog.py').write_text('import sys\nsys.stdin.read()\n')

    def test_cloud_state_and_notifications_are_tenant_scoped(self):
        adapter = self.repo / 'skills/capafy-autopublish/scripts/cloud_cycle.py'
        adapter.write_text('import json,os,sys\nprint(json.dumps({"argv":sys.argv[1:],'
                           '"state":os.environ["LIFE_MANAGER_STATE_HOME"]}))\n')
        result = self.run_entry('skills/self/capafy-loop/capafy-loop-daily.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt['argv'], ['--tenant', 'tenant-a', '--occurrence', 'occurrence-1', '--date', '2026-10-20'])
        self.assertEqual(receipt['state'], str(self.state))
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.home / '.local/state/life-manager/logs').exists())
        self.assertFalse((self.base / 'tenant-b').exists())
        self.assertFalse((self.repo / '.git').exists())

    def test_cloud_drainer_uses_explicit_state_without_loading_dotenv(self):
        self.fixture_drainer()
        result = self.run_entry('skills/capafy-autopublish/scripts/daily_loop.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.state / 'publisher/.capafy-healthy-pass').exists())
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.home / '.local/state/life-manager/state').exists())

    def test_local_drainer_keeps_existing_dotenv_and_default_state(self):
        self.fixture_drainer()
        env = {key: self.env[key] for key in ('PATH', 'HOME', 'LIFE_MANAGER_REPO')}
        result = self.run_entry('skills/capafy-autopublish/scripts/daily_loop.sh', env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())
        self.assertTrue((self.home / '.local/state/life-manager/state/capafy-autopublish/.capafy-healthy-pass').exists())

    def test_cloud_drainer_rejects_missing_state_before_home_fallback(self):
        self.fixture_drainer()
        env = dict(self.env)
        del env['LIFE_MANAGER_STATE_HOME']
        result = self.run_entry('skills/capafy-autopublish/scripts/daily_loop.sh', env)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((self.home / '.local/state/life-manager/state').exists())
        self.assertFalse(self.marker.exists())


if __name__ == '__main__':
    unittest.main()
