import json
import os
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

    def test_main_context_accepts_actions_checkout_origin_without_git_suffix(self):
        from scripts import phase06_kernel_release as release
        from manager_core.digital_handoff import MAIN_REF, REPOSITORY, WORKFLOW
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, pages, runner_temp = root / 'source', root / 'pages', root / 'runner-temp'
            runner_temp.mkdir()
            def initialize(path, branch):
                path.mkdir(parents=True)
                subprocess.run(['git', '-C', str(path), 'init', '-q'], check=True)
                subprocess.run(['git', '-C', str(path), 'config', 'user.name', 'Origin fixture'], check=True)
                subprocess.run(['git', '-C', str(path), 'config', 'user.email', 'origin@example.invalid'], check=True)
                (path / 'fixture.txt').write_text('fixture')
                subprocess.run(['git', '-C', str(path), 'add', '.'], check=True)
                subprocess.run(['git', '-C', str(path), 'commit', '-qm', 'fixture'], check=True)
                subprocess.run(['git', '-C', str(path), 'branch', '-M', branch], check=True)
                subprocess.run(['git', '-C', str(path), 'remote', 'add', 'origin',
                                'https://github.com/Daisuke134/life-manager'], check=True)
            initialize(source, 'main')
            initialize(pages, 'gh-pages')
            source_sha = subprocess.check_output(
                ['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
            env = {
                'GITHUB_REPOSITORY': REPOSITORY,
                'GITHUB_REF': MAIN_REF,
                'GITHUB_WORKFLOW_REF': f'{REPOSITORY}/{WORKFLOW}@{MAIN_REF}',
                'GITHUB_WORKFLOW': cli.WORKFLOW_NAME,
                'GITHUB_EVENT_NAME': 'workflow_dispatch',
                'GITHUB_SHA': source_sha,
                'GITHUB_WORKFLOW_SHA': source_sha,
                'GITHUB_RUN_ID': '123',
                'GITHUB_RUN_ATTEMPT': '1',
                'RUNNER_ENVIRONMENT': 'github-hosted',
                'RUNNER_TEMP': str(runner_temp),
            }
            with patch.object(cli, 'SOURCE_ROOT', source), \
                 patch.object(release, 'ROOT', source / 'products' / 'manager'), \
                 patch.object(release, 'source_checkout_commit', return_value=source_sha), \
                 patch.dict('os.environ', env, clear=True):
                context = cli._check_main_context(pages)
            self.assertEqual(context['source_root'], source.resolve())
            self.assertEqual(context['pages_root'], pages.resolve())
            with patch.object(cli, 'SOURCE_ROOT', source), \
                 patch.object(release, 'source_checkout_commit', return_value=source_sha):
                preflight_code, preflight = cli.run_preflight(source)
            self.assertEqual(preflight_code, 0)
            self.assertEqual(preflight['status'], 'PREFLIGHT_READY')

            subprocess.run(['git', '-C', str(pages), 'remote', 'set-url', '--push', 'origin',
                            'https://github.com/Daisuke134/life-manager'], check=True)
            subprocess.run(['git', '-C', str(pages), 'remote', 'set-url', '--push', 'origin',
                            'https://github.com/Daisuke134/life-manager-evil.git'], check=True)
            with patch.object(cli, 'SOURCE_ROOT', source), \
                 patch.object(release, 'ROOT', source / 'products' / 'manager'), \
                 patch.object(release, 'source_checkout_commit', return_value=source_sha), \
                 patch.dict('os.environ', env, clear=True):
                with self.assertRaises(PermissionError):
                    cli._check_main_context(pages)
            subprocess.run(['git', '-C', str(pages), 'remote', 'set-url', '--push', 'origin',
                            'https://github.com/Daisuke134/life-manager'], check=True)

            subprocess.run(['git', '-C', str(source), 'remote', 'set-url', 'origin',
                            'https://github.com/Daisuke134/life-manager/'], check=True)
            with patch.object(cli, 'SOURCE_ROOT', source), \
                 patch.object(release, 'ROOT', source / 'products' / 'manager'), \
                 patch.object(release, 'source_checkout_commit', return_value=source_sha), \
                 patch.dict('os.environ', env, clear=True):
                with self.assertRaises(PermissionError):
                    cli._check_main_context(pages)
            with patch.object(cli, 'SOURCE_ROOT', source), \
                 patch.object(release, 'source_checkout_commit', return_value=source_sha):
                rejected_code, rejected = cli.run_preflight(source)
            self.assertEqual(rejected_code, 2)
            self.assertEqual(rejected['status'], 'PREFLIGHT_BLOCKED')

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
            self.assertEqual(first['positive_canary'], 'NOT_RUN')
            self.assertEqual(first['E16_ACCEPTANCE'], 'INCOMPLETE')
            self.assertEqual(first['authentication'], 'GATEWAY_ACKNOWLEDGED')
            self.assertEqual(second_code, 0)
            self.assertEqual(second['status'], 'NOT_DUE')
            self.assertEqual(second['writes'], 0)
            self.assertEqual(second['positive_canary'], 'NOT_RUN')
            self.assertEqual(second['E16_ACCEPTANCE'], 'INCOMPLETE')
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

    def test_run_once_exit_codes_distinguish_success_from_uncertain_or_stopped(self):
        cases = (
            ({'status': 'NO_ACTION', 'writes': 0}, 0),
            ({'status': 'NOT_DUE', 'writes': 0}, 0),
            ({'status': 'VERIFIED_PUBLIC_ARTIFACT_ONLY', 'writes': 1,
              'proof_level': 'P2', 'deployed': True, 'receipt_ref': 'a' * 40}, 0),
            ({'status': 'VERIFIED_PLATFORM_CONTRACT_P0', 'writes': 1,
              'proof_level': 'P0', 'receipt_ref': 'b' * 40}, 0),
            ({'status': 'UNKNOWN', 'writes': 0}, 2),
            ({'status': 'STOPPED_REGRESSION', 'writes': 0}, 2),
            ({'status': 'OWNER_BUSY', 'writes': 0}, 2),
            ({'status': 'VERIFIED_PUBLIC_ARTIFACT_ONLY', 'writes': 1,
              'proof_level': 'P0', 'deployed': False}, 2),
        )
        for report, expected_code in cases:
            with self.subTest(status=report['status'], proof=report.get('proof_level')):
                events = []
                class Checkpoint:
                    db = None
                    broken = False
                    def __init__(self, **kwargs): pass
                    def acquire(self, root):
                        Path(root).mkdir(mode=0o700)
                        self.db = Path(root) / 'cycle.sqlite'
                        self.db.write_bytes(b'restored')
                    def save(self): events.append('save')
                    def release(self): events.append('release')
                class Store:
                    def __init__(self, root): pass
                with tempfile.TemporaryDirectory() as tmp, \
                     patch.object(cli, '_check_main_context', return_value={
                         'run_id': '7', 'attempt': '1', 'source_sha': 'a' * 40,
                         'runner_temp': Path(tmp).resolve(), 'pages_root': Path(tmp) / 'pages'}), \
                     patch.object(cli, 'PrivateCheckpoint', Checkpoint), \
                     patch.object(cli, 'CycleStore', Store), \
                     patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: object()), \
                     patch.object(cli, 'run_owned_cycle', return_value=report):
                    code, summary = cli.run_once(Path(tmp) / 'fresh', Path(tmp) / 'pages')
                self.assertEqual(code, expected_code)
                self.assertEqual(events, ['save', 'release'])
                self.assertEqual(summary['status'], report['status'])
                self.assertEqual(summary['E16_ACCEPTANCE'], 'INCOMPLETE')
                self.assertEqual(summary['positive_canary'], 'NOT_RUN')
                if report['status'] == 'UNKNOWN':
                    self.assertIsNone(summary['writes'])
                if report['status'] == 'VERIFIED_PUBLIC_ARTIFACT_ONLY' and expected_code == 0:
                    self.assertEqual(summary['proof_level'], 'P2')
                    self.assertEqual(summary['receipt_sha'], 'a' * 40)

    def test_actual_workflow_shell_stops_after_real_cli_unknown(self):
        workflow_path = Path(__file__).resolve().parents[3] / '.github/workflows/manager-phase06-service.yml'
        lines = workflow_path.read_text().splitlines()
        start = lines.index('      - name: Restore, reconcile, and run one trusted main cycle')
        end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith('      - name: '))
        step = lines[start:end]
        self.assertIn('        shell: bash', step)
        run_at = step.index('        run: |')
        script_lines = []
        for line in step[run_at + 1:]:
            if line and not line.startswith('          '):
                break
            script_lines.append(line[10:] if line.startswith('          ') else '')
        script = '\n'.join(script_lines)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner_temp = root / 'runner-temp'
            runner_temp.mkdir()
            output = root / 'github-output'
            output.write_text('')
            env = {
                'PATH': os.environ['PATH'],
                'RUNNER_TEMP': str(runner_temp),
                'GITHUB_WORKSPACE': str(root),
                'GITHUB_OUTPUT': str(output),
            }
            done = subprocess.run(
                ['bash', '--noprofile', '--norc', '-e', '-o', 'pipefail', '-c', script],
                cwd=Path(__file__).resolve().parents[1], env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
            )
            self.assertEqual(done.returncode, 2, done.stderr)
            summary_path = runner_temp / 'manager-public-summary.json'
            self.assertTrue(summary_path.is_file())
            summary = json.loads(summary_path.read_text())
            self.assertEqual(summary['status'], 'UNKNOWN')
            self.assertIsNone(summary['writes'])
            self.assertEqual(output.read_text(), '')
            self.assertFalse((runner_temp / 'manager-owned-state').exists())


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

    def test_current_proof_export_uses_exact_checkpoint_packet_and_native_rows(self):
        from datetime import datetime, timedelta, timezone
        from manager_core.digital_handoff import (PUBLIC_BASE, REPOSITORY, SOURCE_REF,
            WORKFLOW, PublisherContext)
        from manager_core.learning import NativeTechnicalObservation
        from manager_core.owned_cycle import CycleStore
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from scripts import phase06_kernel_release as release
        from test_owned_public_collector import PublicCollectorTests
        with tempfile.TemporaryDirectory() as tmp:
            packet, fixture_journal, receipt, observed_at, target_url, urls = (
                PublicCollectorTests().prepare_v1_current_fixture(tmp))
            detail_url = f'https://api.github.com/repos/{REPOSITORY}/commits/{receipt}'
            parent = json.loads(urls[detail_url])['parents'][0]['sha']
            runner_temp = Path(tmp) / 'runner-temp'
            runner_temp.mkdir()
            store = CycleStore(runner_temp / 'private-state')
            publisher = PublisherContext(REPOSITORY, SOURCE_REF, WORKFLOW,
                                         packet['candidate']['source_commit'], '7')
            store.journal.reserve(packet, publisher, packet['baseline'], packet['candidate'],
                                  parent, datetime.fromisoformat(packet['created_at']))
            store.journal._present(packet['effect_key'], receipt)
            byte_count = sum(len(body) for url, body in urls.items()
                             if url.startswith(PUBLIC_BASE) and url != PUBLIC_BASE + 'manifest.json')
            receipt_url = f'https://github.com/{REPOSITORY}/commit/{receipt}'
            store.learning.record_native_technical_observation(NativeTechnicalObservation(
                packet['effect_key'], packet['candidate_sha256'], receipt,
                observed_at - timedelta(seconds=1), 'owned.pages.commit_occurrence',
                'commit_occurrence', 'VERIFIED', 'P1', 1, None, 'NOT_MEASURED',
                (receipt_url,)))
            store.learning.record_native_technical_observation(NativeTechnicalObservation(
                packet['effect_key'], packet['candidate_sha256'], receipt, observed_at,
                'owned.pages.served_bundle_bytes', 'byte', 'VERIFIED', 'P2', byte_count,
                None, 'NOT_MEASURED', (receipt_url, PUBLIC_BASE)))
            checkpoint = PrivateCheckpoint(run_id='7', run_attempt='1')
            checkpoint.db = store.db
            checkpoint.broken = False
            checkpoint.nonce = 'private-checkpoint-nonce-sentinel'
            checkpoint.revision = 1
            cycle_report = {
                'status': 'VERIFIED_PUBLIC_ARTIFACT_ONLY', 'proof_level': 'P2',
                'deployed': True, 'effect_key': packet['effect_key'],
                'receipt_ref': receipt, 'nonce': 'cycle-report-nonce-sentinel',
                'private_snapshot': 'cycle-report-private-snapshot-sentinel',
            }
            now = datetime.now(timezone.utc)

            def fake_prove(intent_path, pages_commit, output, proved_at, *, learner=None):
                self.assertEqual(json.loads(Path(intent_path).read_text()), packet)
                self.assertEqual(Path(intent_path).stat().st_mode & 0o777, 0o600)
                self.assertEqual(pages_commit, receipt)
                self.assertIs(learner, store.learning)
                proof_report = {
                    'status': 'VERIFIED_PUBLIC_ARTIFACT_ONLY',
                    'technical_proof': 'exact_public_artifact_bytes',
                    'human_outcome': 'NOT_MEASURED', 'effect_key': packet['effect_key'],
                    'source_commit': packet['candidate']['source_commit'],
                    'pages_commit': receipt, 'parent_pages_commit': parent,
                    'committed_at': observed_at.isoformat(), 'observed_at': proved_at.isoformat(),
                    'observation_decision': packet['decision'],
                    'reconciled_existing_occurrence': False,
                    'changed_pages': ['finance.html'], 'receipt_url': receipt_url,
                    'candidate_sha256': packet['candidate_sha256'],
                    'served_bundle_bytes': byte_count, 'candidate': packet['candidate'],
                }
                release.write_json(Path(output) / 'kernel-public-proof.json', proof_report)
                (Path(output) / 'proof-explorer.html').write_text(
                    release.render_explorer(proof_report, learner=learner))
                return proof_report

            with patch.object(release, 'prove', side_effect=fake_prove) as prove:
                exported = cli._export_current_kernel_proof(
                    checkpoint, store, cycle_report, runner_temp, now=now)
            self.assertTrue(exported)
            prove.assert_called_once()
            proof_dir = runner_temp / 'manager-kernel-proof'
            self.assertEqual({path.name for path in proof_dir.iterdir()},
                             {'kernel-public-proof.json', 'proof-explorer.html'})
            public_files = ''.join(path.read_text() for path in proof_dir.iterdir())
            self.assertNotIn('cycle-report-nonce-sentinel', public_files)
            self.assertNotIn('cycle-report-private-snapshot-sentinel', public_files)
            self.assertNotIn('private-checkpoint-nonce-sentinel', public_files)
            self.assertNotIn('provenance_refs', public_files)
            self.assertNotIn(packet['effect_key'], (proof_dir / 'proof-explorer.html').read_text())
            explorer = (proof_dir / 'proof-explorer.html').read_text()
            self.assertIn('owned.pages.commit_occurrence', explorer)
            self.assertIn('owned.pages.served_bundle_bytes', explorer)
            self.assertIn(f'{byte_count} byte', explorer)

    def test_current_proof_export_skips_untrusted_reports_and_cleans_failed_partial_output(self):
        from datetime import datetime, timedelta, timezone
        from manager_core.digital_handoff import PUBLIC_BASE, REPOSITORY, SOURCE_REF, WORKFLOW, PublisherContext
        from manager_core.learning import NativeTechnicalObservation
        from manager_core.owned_cycle import CycleStore
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from scripts import phase06_kernel_release as release
        from test_owned_public_collector import PublicCollectorTests
        with tempfile.TemporaryDirectory() as tmp:
            packet, fixture_journal, receipt, observed_at, target_url, urls = (
                PublicCollectorTests().prepare_v1_current_fixture(tmp))
            parent = json.loads(urls[
                f'https://api.github.com/repos/{REPOSITORY}/commits/{receipt}'])['parents'][0]['sha']
            runner_temp = Path(tmp) / 'runner-temp'
            runner_temp.mkdir()
            store = CycleStore(runner_temp / 'private-state')
            store.journal.reserve(packet, PublisherContext(REPOSITORY, SOURCE_REF, WORKFLOW,
                packet['candidate']['source_commit'], '7'), packet['baseline'], packet['candidate'],
                parent, datetime.fromisoformat(packet['created_at']))
            store.journal._present(packet['effect_key'], receipt)
            receipt_url = f'https://github.com/{REPOSITORY}/commit/{receipt}'
            store.learning.record_native_technical_observation(NativeTechnicalObservation(
                packet['effect_key'], packet['candidate_sha256'], receipt, observed_at,
                'owned.pages.commit_occurrence', 'commit_occurrence', 'VERIFIED', 'P1', 1,
                None, 'NOT_MEASURED', (receipt_url,)))
            byte_count = sum(len(body) for url, body in urls.items()
                             if url.startswith(PUBLIC_BASE) and url != PUBLIC_BASE + 'manifest.json')
            store.learning.record_native_technical_observation(NativeTechnicalObservation(
                packet['effect_key'], packet['candidate_sha256'], receipt, observed_at,
                'owned.pages.served_bundle_bytes', 'byte', 'VERIFIED', 'P2', byte_count,
                None, 'NOT_MEASURED', (receipt_url, PUBLIC_BASE)))
            checkpoint = PrivateCheckpoint(run_id='7', run_attempt='1')
            checkpoint.db = store.db
            checkpoint.broken = False
            checkpoint.revision = 1
            good_report = {'status': 'VERIFIED_PUBLIC_ARTIFACT_ONLY', 'proof_level': 'P2',
                           'deployed': True, 'effect_key': packet['effect_key'],
                           'receipt_ref': receipt}
            denied_reports = (
                dict(good_report, status='UNKNOWN'),
                dict(good_report, status='NO_ACTION'),
                dict(good_report, proof_level='P0', deployed=False),
            )
            with patch.object(release, 'prove') as prove:
                for denied in denied_reports:
                    self.assertFalse(cli._export_current_kernel_proof(
                        checkpoint, store, denied, runner_temp))
                    self.assertFalse((runner_temp / 'manager-kernel-proof').exists())
                p1_rows=[row for row in store.learning.native_technical_observations()
                         if row.proof_level=='P1']
                with patch.object(store.learning, 'native_technical_observations',
                                  return_value=p1_rows):
                    self.assertFalse(cli._export_current_kernel_proof(
                        checkpoint, store, good_report, runner_temp))
                prove.assert_not_called()

            rows_before = store.learning.native_technical_observations()
            delivery_before = store.journal.delivery_record(packet['effect_key'])
            def fail_after_first_file(intent_path, pages_commit, output, proved_at, *, learner=None):
                (Path(output) / 'kernel-public-proof.json').write_text('{"partial":true}')
                raise OSError('public proof read failed')
            with patch.object(release, 'prove', side_effect=fail_after_first_file) as prove:
                self.assertFalse(cli._export_current_kernel_proof(
                    checkpoint, store, good_report, runner_temp))
                prove.assert_called_once()
            self.assertFalse((runner_temp / 'manager-kernel-proof').exists())
            self.assertEqual(store.learning.native_technical_observations(), rows_before)
            self.assertEqual(store.journal.delivery_record(packet['effect_key']), delivery_before)

    def test_run_once_does_not_claim_positive_canary_when_proof_export_fails(self):
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
        report = {'status': 'VERIFIED_PUBLIC_ARTIFACT_ONLY', 'writes': 1,
                  'proof_level': 'P2', 'deployed': True, 'effect_key': 'a' * 64,
                  'receipt_ref': 'b' * 40}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(cli, '_check_main_context', return_value={'run_id': '7', 'attempt': '1',
                 'source_sha': 'c' * 40, 'runner_temp': Path(tmp).resolve(),
                 'pages_root': Path(tmp) / 'pages'}), \
             patch.object(cli, 'PrivateCheckpoint', Checkpoint), \
             patch.object(cli, 'CycleStore', Store), \
             patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: object()), \
             patch.object(cli, 'run_owned_cycle', return_value=report), \
             patch.object(cli, '_export_current_kernel_proof', return_value=False), \
             patch.object(cli, '_trusted_p2_observation', return_value=True):
            code, summary = cli.run_once(Path(tmp) / 'fresh', Path(tmp) / 'pages')
        self.assertEqual(code, 0)
        self.assertEqual(summary['positive_canary'], 'NOT_RUN')
        self.assertEqual(events, ['save', 'release'])

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
