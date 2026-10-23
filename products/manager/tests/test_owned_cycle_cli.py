import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_owned_digital_cycle as cli


class OwnedCycleCLITests(unittest.TestCase):
    def test_preflight_is_read_only_and_reports_auth_not_proven(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'state'
            with patch('scripts.phase06_kernel_release.source_checkout_commit', return_value='a' * 40), \
                 patch.object(cli, 'CycleStore', side_effect=AssertionError('preflight created a store')), \
                 patch.object(cli, 'PrivateCheckpoint', side_effect=AssertionError('preflight acquired a lease')):
                code, summary = cli.run_preflight(cli.SOURCE_ROOT, state)
            self.assertEqual(code, 0)
            self.assertEqual(summary['authentication'], 'NOT_PROVEN')
            self.assertFalse(state.exists())

    def test_run_once_restores_before_store_and_calls_one_cycle(self):
        events = []
        class Checkpoint:
            db = None
            broken = False
            def __init__(self, **kwargs): events.append(('checkpoint', kwargs))
            def acquire(self, root):
                events.append(('acquire', Path(root)))
                Path(root).mkdir(mode=0o700)
                self.db = Path(root) / 'cycle.sqlite'
                self.db.write_bytes(b'restored')
            def save(self): events.append(('save',)); return {'revision': 2, 'sha256': 'b' * 64}
            def release(self): events.append(('release',))
        class Store:
            def __init__(self, root):
                events.append(('store', Path(root)))
                self.root = Path(root)
        class Host:
            def __init__(self, *args, **kwargs): events.append(('host', args, kwargs))
        cycle_report = {'status': 'NO_ACTION', 'reason': 'NO_ELIGIBLE_BOUNDED_IMPROVEMENT', 'writes': 0}
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'fresh'
            with patch.object(cli, '_check_main_context', return_value={'run_id': '7', 'attempt': '1', 'source_sha': 'a' * 40, 'runner_temp': Path(tmp).resolve(), 'pages_root': Path(tmp) / 'pages'}), \
                 patch.object(cli, 'PrivateCheckpoint', Checkpoint), patch.object(cli, 'CycleStore', Store), \
                 patch.object(cli, 'GitHubActionsCycleHost', Host), \
                 patch.object(cli, 'run_owned_cycle', side_effect=lambda *a, **k: (events.append(('cycle',)), cycle_report)[1]):
                code, summary = cli.run_once(state, Path(tmp) / 'pages')
            self.assertEqual(code, 0)
            self.assertEqual(summary['positive_canary'], 'NOT_RUN')
            self.assertEqual(summary['authentication'], 'GATEWAY_ACKNOWLEDGED')
            names = [event[0] for event in events]
            self.assertLess(names.index('acquire'), names.index('store'))
            self.assertLess(names.index('store'), names.index('host'))
            self.assertLess(names.index('host'), names.index('cycle'))
            self.assertEqual(names.count('cycle'), 1)
            self.assertIn('save', names)
            self.assertIn('release', names)

    def test_composed_real_checkpoint_host_and_cycle_restore_no_action_then_not_due(self):
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from manager_core.owned_cycle import CycleStore
        from test_owned_checkpoint import MemoryGateway
        from manager_core import owned_catalog_planner as planner
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = CycleStore(root / 'seed')
            gateway = MemoryGateway(seed.db.read_bytes())
            source_sha = subprocess.check_output(['git', '-C', str(cli.SOURCE_ROOT), 'rev-parse', 'HEAD'], text=True).strip()
            pages = root / 'pages'
            (pages / 'manager-support').mkdir(parents=True)
            from manager_core.digital_environment import build_site
            catalog_path = Path(__file__).resolve().parents[1] / 'public_goods/service/catalog.json'
            bundle = root / 'bundle'
            build_site(json.loads(catalog_path.read_text()), bundle, source_sha)
            for name in ('index.html', 'finance.html', 'mental.html', 'physical.html', 'control.html', 'proof.html', 'manifest.json'):
                shutil.copyfile(bundle / name, pages / 'manager-support' / name)
            subprocess.run(['git', '-C', str(pages), 'init', '-q'], check=True)
            subprocess.run(['git', '-C', str(pages), 'config', 'user.name', 'P0 Fixture'], check=True)
            subprocess.run(['git', '-C', str(pages), 'config', 'user.email', 'fixture@example.invalid'], check=True)
            subprocess.run(['git', '-C', str(pages), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(pages), 'commit', '-qm', 'fixture baseline'], check=True)
            subprocess.run(['git', '-C', str(pages), 'branch', '-M', 'gh-pages'], check=True)
            subprocess.run(['git', '-C', str(pages), 'remote', 'add', 'origin', 'https://github.com/Daisuke134/life-manager.git'], check=True)
            env = {
                'GITHUB_REPOSITORY': 'Daisuke134/life-manager',
                'GITHUB_REF': 'refs/heads/main',
                'GITHUB_WORKFLOW_REF': 'Daisuke134/life-manager/.github/workflows/manager-phase06-service.yml@refs/heads/main',
                'GITHUB_WORKFLOW': 'Manager Phase06 Digital Environment',
                'GITHUB_EVENT_NAME': 'workflow_dispatch',
                'GITHUB_SHA': source_sha,
                'GITHUB_WORKFLOW_SHA': source_sha,
                'GITHUB_RUN_ID': '123',
                'GITHUB_RUN_ATTEMPT': '1',
                'RUNNER_ENVIRONMENT': 'github-hosted',
                'RUNNER_TEMP': str(root),
                'MANAGER_RELEASE_ENABLED': 'true',
                'GH_TOKEN': 'P0-only-token-sentinel',
            }
            with patch.object(PrivateCheckpoint.__init__, '__defaults__', (gateway,)), \
                 patch.object(planner, 'plan_catalog_change', return_value=None) as selector, \
                 patch.dict('os.environ', env, clear=True):
                first_code, first = cli.run_once(root / 'first', pages)
                second_code, second = cli.run_once(root / 'second', pages)
                def missing_gateway(_payload):
                    raise OSError('remote private state missing')
                with patch.object(PrivateCheckpoint.__init__, '__defaults__', (missing_gateway,)), \
                     patch.object(cli, 'CycleStore', side_effect=AssertionError('missing remote state created a blank store')):
                    missing_code, missing = cli.run_once(root / 'missing', pages)
            self.assertEqual(first_code, 0)
            self.assertEqual(first['status'], 'NO_ACTION')
            self.assertEqual(first['writes'], 0)
            self.assertEqual(first['authentication'], 'GATEWAY_ACKNOWLEDGED')
            self.assertEqual(second_code, 2)
            self.assertEqual(second['status'], 'NOT_DUE')
            self.assertEqual(second['writes'], 0)
            self.assertEqual(selector.call_count, 1)
            self.assertEqual(gateway.calls, ['acquire', 'checkpoint', 'release', 'acquire', 'checkpoint', 'release'])
            self.assertEqual(missing_code, 2)
            self.assertEqual(missing['status'], 'UNKNOWN')
            self.assertEqual(missing['authentication'], 'NOT_PROVEN')
            self.assertIsNone(missing['writes'])
            self.assertFalse((root / 'missing').exists())
            self.assertIsNone(gateway.value['owner'])
            self.assertTrue((root / 'first/cycle.sqlite').is_file())
            self.assertTrue((root / 'second/cycle.sqlite').is_file())


    def test_checkpoint_failure_never_releases_or_claims_zero_writes(self):
        events = []
        class Checkpoint:
            db = None
            broken = False
            def __init__(self, **kwargs): pass
            def acquire(self, root):
                Path(root).mkdir(mode=0o700)
                self.db = Path(root) / 'cycle.sqlite'; self.db.write_bytes(b'x')
            def save(self): self.broken = True; raise cli.CheckpointUnavailable('uncertain private state')
            def release(self): events.append('release')
        class Store:
            def __init__(self, root): pass
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(cli, '_check_main_context', return_value={'run_id': '7', 'attempt': '1', 'source_sha': 'a' * 40, 'runner_temp': Path(tmp).resolve(), 'pages_root': Path(tmp) / 'pages'}), \
             patch.object(cli, 'PrivateCheckpoint', Checkpoint), patch.object(cli, 'CycleStore', Store), \
             patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: object()), \
             patch.object(cli, 'run_owned_cycle', return_value={'status': 'NO_ACTION', 'writes': 0}):
            code, summary = cli.run_once(Path(tmp) / 'fresh', Path(tmp) / 'pages')
        self.assertEqual(code, 2)
        self.assertEqual(summary['status'], 'UNKNOWN')
        self.assertIsNone(summary['writes'])
        self.assertNotIn('release', events)

    def test_public_summary_is_allowlisted(self):
        summary = cli.public_summary({'status': 'NO_ACTION', 'reason': 'NO_ELIGIBLE_BOUNDED_IMPROVEMENT', 'writes': 0,
                                      'private_snapshot': 'secret', 'nonce': 'secret'})
        self.assertNotIn('nonce', summary)
        self.assertNotIn('private_snapshot', summary)
        self.assertEqual(summary['E16_ACCEPTANCE'], 'INCOMPLETE')
        self.assertEqual(summary['positive_canary'], 'NOT_RUN')

    def test_selector_unknown_persists_session_but_never_claims_zero_writes(self):
        events = []
        class Checkpoint:
            db = None
            broken = False
            def __init__(self, **kwargs): pass
            def acquire(self, root):
                Path(root).mkdir(mode=0o700)
                self.db = Path(root) / 'cycle.sqlite'; self.db.write_bytes(b'restored')
            def save(self): events.append('save')
            def release(self): events.append('release')
        class Store:
            def __init__(self, root): pass
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(cli, '_check_main_context', return_value={'run_id': '7', 'attempt': '1', 'source_sha': 'a' * 40, 'runner_temp': Path(tmp).resolve(), 'pages_root': Path(tmp) / 'pages'}), \
             patch.object(cli, 'PrivateCheckpoint', Checkpoint), patch.object(cli, 'CycleStore', Store), \
             patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: object()), \
             patch.object(cli, 'run_owned_cycle', side_effect=cli.CatalogSelectionUnavailable('selector unavailable')):
            code, summary = cli.run_once(Path(tmp) / 'fresh', Path(tmp) / 'pages')
        self.assertEqual(code, 2)
        self.assertEqual(summary['status'], 'UNKNOWN')
        self.assertEqual(summary['reason'], 'SELECTOR_UNAVAILABLE')
        self.assertIsNone(summary['writes'])
        self.assertEqual(events, ['save', 'release'])

    def test_main_environment_claim_is_rejected_before_private_session(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict('os.environ', {'GITHUB_REPOSITORY': 'Daisuke134/life-manager',
                                      'GITHUB_REF': 'refs/heads/main',
                                      'GITHUB_EVENT_NAME': 'workflow_dispatch'}, clear=True), \
             patch.object(cli, 'PrivateCheckpoint', side_effect=AssertionError('lease requested before context validation')):
            code, summary = cli.run_once(Path(tmp) / 'fresh', Path(tmp) / 'pages')
        self.assertEqual(code, 2)
        self.assertEqual(summary['status'], 'UNKNOWN')
        self.assertEqual(summary['authentication'], 'NOT_PROVEN')
        self.assertIsNone(summary['writes'])

    def test_unknown_occurrence_is_checkpointed_and_released_only_after_ack(self):
        events = []
        class Checkpoint:
            db = None
            broken = False
            def __init__(self, **kwargs): pass
            def acquire(self, root):
                Path(root).mkdir(mode=0o700)
                self.db = Path(root) / 'cycle.sqlite'; self.db.write_bytes(b'restored')
            def save(self): events.append('save')
            def release(self): events.append('release')
        class Store:
            def __init__(self, root): pass
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(cli, '_check_main_context', return_value={'run_id': '7', 'attempt': '1', 'source_sha': 'a' * 40, 'runner_temp': Path(tmp).resolve(), 'pages_root': Path(tmp) / 'pages'}), \
             patch.object(cli, 'PrivateCheckpoint', Checkpoint), patch.object(cli, 'CycleStore', Store), \
             patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: object()), \
             patch.object(cli, 'run_owned_cycle', return_value={'status': 'UNKNOWN', 'reason': 'DELIVERY_UNCONFIRMED', 'writes': 0}):
            code, summary = cli.run_once(Path(tmp) / 'fresh', Path(tmp) / 'pages')
        self.assertEqual(code, 2)
        self.assertEqual(events, ['save', 'release'])
        self.assertEqual(summary['status'], 'UNKNOWN')
        self.assertEqual(summary['authentication'], 'GATEWAY_ACKNOWLEDGED')
        self.assertIsNone(summary['writes'])


    def test_default_cli_arguments_are_read_only_preflight(self):
        with patch.object(cli, 'run_preflight', return_value=(0, {'status': 'PREFLIGHT_READY', 'authentication': 'NOT_PROVEN'})) as preflight, \
             patch('builtins.print'):
            self.assertEqual(cli.main(['--state-store', '/tmp/does-not-exist']), 0)
        preflight.assert_called_once()



if __name__ == '__main__':
    unittest.main()
