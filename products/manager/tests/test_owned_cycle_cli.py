from contextlib import contextmanager
from decimal import Decimal
import json
import sqlite3
from time import monotonic
from types import SimpleNamespace
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_owned_digital_cycle as cli


class OwnedCycleCLITests(unittest.TestCase):
    def test_shadow_settings_are_inert_and_preserve_unconfigured_money(self):
        from manager_core import ampersand_api
        env = {'MANAGER_CATALOG_SHADOW_ENABLED': 'true',
               'GITHUB_EVENT_NAME': 'workflow_dispatch', 'AMPERSAND_API_KEY': 'hak_abcdefgh',
               'MANAGER_AMPERSAND_MAX_TOTAL_USD': '0.050000',
               'MANAGER_AMPERSAND_MAX_CALL_USD': '0.030000'}
        with patch.object(ampersand_api, 'make_client', return_value=object()) as factory:
            settings = cli._catalog_shadow_settings(env, started_monotonic=12.5)
            self.assertEqual(settings.deadline_monotonic, 132.5)
            self.assertEqual((settings.cap_usd, settings.upper_usd), (Decimal('.05'), Decimal('.03')))
            self.assertEqual(factory.call_count, 0)
            settings.client_factory()
            factory.assert_called_once_with('hak_abcdefgh', timeout=30)
        for name in ('MANAGER_AMPERSAND_MAX_TOTAL_USD', 'MANAGER_AMPERSAND_MAX_CALL_USD'):
            for value in (None, '', ' ', 'bad', 'NaN', 'Infinity', '-Infinity', '0', '-1',
                          '100.000001', '0.0000001', '1e9999999999999999999'):
                with self.subTest(name=name, value=value):
                    changed = dict(env)
                    if value is None:
                        changed.pop(name)
                    else:
                        changed[name] = value
                    settings = cli._catalog_shadow_settings(changed, started_monotonic=1)
                    self.assertIsNotNone(settings)
                    self.assertEqual(settings.deadline_monotonic, 121)
                    self.assertEqual((settings.client_factory, settings.cap_usd, settings.upper_usd),
                                     (None, None, None))
        for changes in ({'MANAGER_AMPERSAND_MAX_CALL_USD': '.06'},
                        {'AMPERSAND_API_KEY': 'hak_abcdefgh '}, {'AMPERSAND_API_KEY': ''},
                        {'AMPERSAND_API_KEY': 'bad'}):
            with self.subTest(changes=changes):
                settings = cli._catalog_shadow_settings(env | changes, started_monotonic=1)
                self.assertEqual((settings.client_factory, settings.cap_usd, settings.upper_usd),
                                 (None, None, None))

    def test_shadow_disabled_schedule_control_and_preflight_are_inert(self):
        from manager_core import ampersand_api, owned_provider_shadow as shadow
        enabled = {'MANAGER_CATALOG_SHADOW_ENABLED': 'true',
                   'GITHUB_EVENT_NAME': 'workflow_dispatch',
                   'MANAGER_AMPERSAND_MAX_TOTAL_USD': 'NaN',
                   'MANAGER_AMPERSAND_MAX_CALL_USD': 'malformed'}
        for flag in (None, 'false', 'TRUE', 'unknown', ''):
            env = dict(enabled)
            if flag is None:
                env.pop('MANAGER_CATALOG_SHADOW_ENABLED')
            else:
                env['MANAGER_CATALOG_SHADOW_ENABLED'] = flag
            with self.subTest(flag=flag):
                self.assertIsNone(cli._catalog_shadow_settings(env, started_monotonic=1))
        self.assertIsNone(cli._catalog_shadow_settings(enabled | {'GITHUB_EVENT_NAME': 'schedule'},
                                                      started_monotonic=1))
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict('os.environ', enabled, clear=True), \
             patch.object(cli, '_catalog_shadow_settings', side_effect=AssertionError('parsed')), \
             patch.object(ampersand_api, 'make_client', side_effect=AssertionError('client')), \
             patch.object(shadow, 'compare_prepared_catalog_shadow', side_effect=AssertionError('compare')), \
             patch.object(cli, '_check_main_context', side_effect=PermissionError('fixture context')):
            for control in ('stop', 'rollback', 'resume'):
                code, summary = cli.run_control(control, Path(tmp)/control, Path(tmp)/'pages')
                self.assertEqual(code, 2)
                self.assertIsNone(summary['catalog_shadow'])
            for command in ([], ['preflight']):
                with patch('builtins.print') as output:
                    cli.main(command)
                self.assertIsNone(json.loads(output.call_args.args[0])['catalog_shadow'])

        for event, flag in (('schedule', 'true'), ('workflow_dispatch', 'false')):
            with self.subTest(event=event, flag=flag), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self._shadow_cli_context(root, env_changes={
                        'GITHUB_EVENT_NAME': event, 'MANAGER_CATALOG_SHADOW_ENABLED': flag}) as fixture, \
                     patch.object(shadow, 'compare_prepared_catalog_shadow', side_effect=AssertionError('compare')):
                    code, summary = cli.run_once(root/'run', root/'pages')
                    self.assertEqual(code, 0)
                    self.assertIsNone(summary['catalog_shadow'])
                    self.assertEqual(fixture[3].call_count, 0)
                    self.assertEqual(fixture[4].create_count, 0)
                    self.assertEqual(fixture[5], [])
        for control in ('stop', 'rollback', 'resume'):
            with self.subTest(control=control), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self._shadow_cli_context(root, env_changes={
                        'MANAGER_AMPERSAND_MAX_TOTAL_USD': 'NaN'}) as fixture, \
                     patch.object(cli, '_catalog_shadow_settings', side_effect=AssertionError('parsed')), \
                     patch.object(shadow, 'compare_prepared_catalog_shadow', side_effect=AssertionError('compare')):
                    code, summary = cli.run_control(control, root/'run', root/'pages')
                    self.assertEqual(code, 0)
                    self.assertIsNone(summary['catalog_shadow'])
                    self.assertEqual(fixture[3].call_count, 0)
                    self.assertEqual(fixture[4].create_count, 0)
                    self.assertIsNone(fixture[2].value['owner'])

    @contextmanager
    def _shadow_cli_context(self, root, *, status='NO_ACTION', env_changes=None):
        from manager_core import ampersand_api, owned_catalog_planner as planner, owned_cycle
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from manager_core.owned_cycle import CycleStore
        from test_owned_checkpoint import MemoryGateway
        from test_owned_platform_host import github_environment
        from test_owned_provider_shadow import OwnedProviderShadowTests, client_for
        prepared, _, now = OwnedProviderShadowTests().prepared_fixture(root/'catalog')
        gateway = MemoryGateway(CycleStore(root/'seed').db.read_bytes())
        client, sessions = client_for()
        closed = []
        client.close = lambda: closed.append(True)
        env = github_environment(GITHUB_SHA='c'*40, GITHUB_WORKFLOW_SHA='c'*40,
            MANAGER_CATALOG_SHADOW_ENABLED='true', AMPERSAND_API_KEY='hak_abcdefgh',
            MANAGER_AMPERSAND_MAX_TOTAL_USD='.05', MANAGER_AMPERSAND_MAX_CALL_USD='.03')
        env.update(env_changes or {})
        context = {'run_id': '123', 'attempt': '1', 'source_sha': 'c'*40,
                   'runner_temp': root, 'pages_root': root/'pages'}
        report = {'status': status, 'writes': 0, 'reason': 'FIXTURE_PUBLISHER_RESULT'}
        # Keep the checkpoint, host, helper, cycle and recovery gates real;
        # substitute publisher dispatch to avoid any external write.
        with patch.object(cli, '_check_main_context', return_value=context), \
             patch.object(PrivateCheckpoint.__init__, '__defaults__', (gateway,)), \
             patch('scripts.phase06_kernel_release.source_checkout_commit', return_value='c'*40), \
             patch.object(planner, 'plan_catalog_change', return_value=prepared) as selector, \
             patch.object(owned_cycle, '_dispatch_owned_locked', return_value=report), \
             patch.object(ampersand_api, 'make_client', return_value=client) as factory, \
             patch.dict('os.environ', env, clear=True):
            yield prepared, now, gateway, factory, sessions, closed, selector

    def test_saved_shadow_replays_without_send_configuration(self):
        from manager_core import owned_provider_shadow as shadow
        from manager_core.owned_checkpoint import PrivateCheckpoint
        for saved_kind in ('ack', 'intent', 'absent'):
            with self.subTest(saved_kind=saved_kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self._shadow_cli_context(root, env_changes={
                        'AMPERSAND_API_KEY': '', 'MANAGER_AMPERSAND_MAX_TOTAL_USD': 'NaN',
                        'MANAGER_AMPERSAND_MAX_CALL_USD': ''}) as fixture:
                    prepared, now, gateway, factory, sessions, closed, selector = fixture
                    if saved_kind != 'absent':
                        from test_owned_provider_shadow import client_for
                        initial_client, initial_sessions = client_for()
                        cp = PrivateCheckpoint(gateway, run_id='123', run_attempt='1')
                        cp.acquire(root/'initial')
                        original = shadow.compare_prepared_catalog_shadow(cp, prepared,
                            now=now, run_id='99', enabled=True, client_factory=lambda: initial_client,
                            cap_usd=Decimal('.05'), upper_usd=Decimal('.03'),
                            deadline_monotonic=monotonic()+120)
                        self.assertEqual(initial_sessions.create_count, 1)
                        if saved_kind == 'intent':
                            with sqlite3.connect(cp.db) as db:
                                db.execute('DELETE FROM catalog_shadow_results')
                        cp.save()
                        cp.release()
                    with patch.object(shadow.CheckpointedProvider, '__init__', side_effect=AssertionError('provider')):
                        code, summary = cli.run_once(root/'run', root/'pages')
                    self.assertEqual(code, 0)
                    public = summary['catalog_shadow']
                    expected = {'ack': ('COMPARED_P0', 'MODEL_RESPONSE_PARSED'),
                                'intent': ('UNKNOWN', 'PRIOR_INTENT_RECONCILIATION_REQUIRED'),
                                'absent': ('SKIPPED', 'PROVIDER_NOT_CONFIGURED')}[saved_kind]
                    self.assertEqual((public['status'], public['reason']), expected)
                    if saved_kind == 'ack':
                        self.assertEqual(public['run_id'], '99')
                        self.assertEqual(public['compared_at'], original['compared_at'])
                    self.assertEqual(factory.call_count, 0)
                    self.assertEqual(sessions.create_count, 0)
                    self.assertEqual(closed, [])
                    self.assertEqual(selector.call_count, 1)
                    self.assertIsNone(gateway.value['owner'])

    def test_public_shadow_projection_is_nested_exact_and_single_pass(self):
        from manager_core import owned_provider_shadow as shadow
        raw = shadow._record('COMPARED_P0', 'MODEL_RESPONSE_PARSED', '99',
            compared_at='2026-10-23T00:00:00+00:00', operation_id='catalog_shadow_'+'a'*64,
            context_sha256='b'*64, baseline_digest='c'*64, candidate_digest='d'*64,
            baseline={'no_action': {'decision': 'PASS'}, 'rules': {'decision': 'PROPOSE'}},
            model_status='MODEL_ADVICE_P0', model_advice={'decision': 'PROPOSE', 'reason': 'PRIVATE_ADVICE'},
            model_comparison={'no_action_same_decision': False, 'rules_same_decision': True},
            provider={'session_id': 'PRIVATE_PROVIDER'}, raw_response='PRIVATE_RAW',
            api_key='PRIVATE_KEY', path='/PRIVATE_PATH')
        report = {'status': 'NO_ACTION', 'writes': 0, 'reason': 'FIXTURE_RESULT'}
        ordinary = cli.public_summary(report, source_sha='e'*40)
        with patch.object(shadow, 'public_catalog_shadow_summary', wraps=shadow.public_catalog_shadow_summary) as project:
            summary = cli.public_summary(report, source_sha='e'*40, catalog_shadow=raw)
        self.assertEqual(project.call_count, 1)
        self.assertIs(project.call_args.args[0], raw)
        self.assertIsNone(ordinary['catalog_shadow'])
        self.assertEqual({k: v for k, v in summary.items() if k != 'catalog_shadow'},
                         {k: v for k, v in ordinary.items() if k != 'catalog_shadow'})
        public = summary['catalog_shadow']
        self.assertEqual(set(public), {'schema', 'status', 'reason', 'run_id', 'compared_at',
            'operation_id', 'context_sha256', 'baseline_digest', 'candidate_digest',
            'baseline_decisions', 'model_status', 'model_decision', 'model_comparison',
            'proof_level', 'authorized_execution', 'causal_support', 'human_outcome',
            'action_writes', 'settled_cost_usd'})
        self.assertEqual(public['run_id'], '99')
        self.assertEqual(public['proof_level'], 'P0')
        self.assertIs(public['authorized_execution'], False)
        self.assertIs(public['causal_support'], False)
        self.assertEqual(public['human_outcome'], 'NOT_MEASURED')
        self.assertEqual(public['action_writes'], 0)
        self.assertIsNone(public['settled_cost_usd'])
        self.assertNotIn('PRIVATE_', json.dumps(summary))

    def test_shadow_result_survives_cycle_unknown_but_not_checkpoint_failure(self):
        from contextlib import ExitStack
        from manager_core import owned_provider_shadow as shadow
        from manager_core.owned_checkpoint import PrivateCheckpoint
        for failure in (None, 'save', 'release', 'helper', 'selector'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with self._shadow_cli_context(root, status='UNKNOWN') as fixture, ExitStack() as stack:
                    _, _, gateway, factory, sessions, closed, selector = fixture
                    if failure == 'save':
                        original_cycle = cli.run_owned_cycle
                        def finish_then_fail(*args, **kwargs):
                            report = original_cycle(*args, **kwargs)
                            stack.enter_context(patch.object(PrivateCheckpoint, 'save',
                                side_effect=cli.CheckpointUnavailable('save fence')))
                            return report
                        stack.enter_context(patch.object(cli, 'run_owned_cycle', side_effect=finish_then_fail))
                    elif failure == 'release':
                        stack.enter_context(patch.object(PrivateCheckpoint, 'release',
                            side_effect=cli.CheckpointUnavailable('release fence')))
                    elif failure == 'helper':
                        stack.enter_context(patch.object(shadow, 'compare_prepared_catalog_shadow',
                            side_effect=cli.CheckpointUnavailable('helper fence')))
                    elif failure == 'selector':
                        selector.side_effect = RuntimeError('selector failed')
                    code, summary = cli.run_once(root/'run', root/'pages')
                    self.assertEqual(code, 2)
                    self.assertEqual(summary['status'], 'UNKNOWN')
                    self.assertIsNone(summary['writes'])
                    self.assertEqual(summary['authentication'], 'GATEWAY_ACKNOWLEDGED')
                    if failure is None:
                        self.assertEqual(summary['catalog_shadow']['status'], 'COMPARED_P0')
                        self.assertIsNone(gateway.value['owner'])
                        self.assertEqual(gateway.calls[-2:], ['checkpoint', 'release'])
                    else:
                        self.assertIsNone(summary['catalog_shadow'])
                        if failure == 'selector':
                            self.assertEqual(summary['reason'], 'SELECTOR_UNAVAILABLE')
                            self.assertEqual(gateway.calls[-2:], ['checkpoint', 'release'])
                        else:
                            self.assertNotIn('release', gateway.calls)
                            self.assertIsNotNone(gateway.value['owner'])
                    self.assertEqual(factory.call_count, 0 if failure in ('helper', 'selector') else 1)
                    self.assertEqual(sessions.create_count, 0 if failure in ('helper', 'selector') else 1)
                    self.assertEqual(closed, [] if failure in ('helper', 'selector') else [True])

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
        parse_settings = cli._catalog_shadow_settings
        def settings(env, *, started_monotonic):
            events.append(('settings', started_monotonic))
            return parse_settings(env, started_monotonic=started_monotonic)
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
            _catalog_shadow_result = None
            def __init__(self, *args, **kwargs): events.append(('host', args, kwargs))
        cycle_report = {'status': 'NO_ACTION', 'reason': 'NO_ELIGIBLE_BOUNDED_IMPROVEMENT', 'writes': 0}
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'fresh'
            with patch.object(cli, 'monotonic', side_effect=lambda: (events.append(('clock',)), 12.5)[1]), \
                 patch.dict('os.environ', {'MANAGER_CATALOG_SHADOW_ENABLED': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch'}, clear=True), \
                 patch.object(cli, '_catalog_shadow_settings', side_effect=settings), \
                 patch.object(cli, '_check_main_context', side_effect=lambda *_: (events.append(('context',)), {'run_id': '7', 'attempt': '1', 'source_sha': 'a' * 40, 'runner_temp': Path(tmp).resolve(), 'pages_root': Path(tmp) / 'pages'})[1]), \
                 patch.object(cli, 'PrivateCheckpoint', Checkpoint), patch.object(cli, 'CycleStore', Store), \
                 patch.object(cli, 'GitHubActionsCycleHost', Host), \
                 patch.object(cli, 'run_owned_cycle', side_effect=lambda *a, **k: (events.append(('cycle',)), cycle_report)[1]):
                code, summary = cli.run_once(state, Path(tmp) / 'pages')
            self.assertEqual(code, 0)
            self.assertEqual(summary['positive_canary'], 'NOT_RUN')
            self.assertEqual(summary['authentication'], 'GATEWAY_ACKNOWLEDGED')
            names = [event[0] for event in events]
            self.assertLess(names.index('clock'), names.index('context'))
            self.assertLess(names.index('settings'), names.index('acquire'))
            self.assertIn(('settings', 12.5), events)
            host_event = next(event for event in events if event[0] == 'host')
            self.assertEqual(host_event[2]['catalog_shadow'].deadline_monotonic, 132.5)
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
                     patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: SimpleNamespace(_catalog_shadow_result=None)), \
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
             patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: SimpleNamespace(_catalog_shadow_result=None)), \
             patch.object(cli, 'run_owned_cycle', return_value={'status': 'NO_ACTION', 'writes': 0}):
            code, summary = cli.run_once(Path(tmp) / 'fresh', Path(tmp) / 'pages')
        self.assertEqual(code, 2)
        self.assertEqual(summary['status'], 'UNKNOWN')
        self.assertIsNone(summary['writes'])
        self.assertNotIn('release', events)

    def test_not_due_saved_v2_current_delivery_exports_real_proof_read_only(self):
        from datetime import datetime, timedelta, timezone
        from manager_core.digital_handoff import (MAIN_REF, PUBLIC_BASE, REPOSITORY, WORKFLOW,
            PublisherContext, plan_release)
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from manager_core.owned_cycle import CycleStore, _cycle_result
        from manager_core.owned_platform_host import GitHubActionsCycleHost
        from scripts import phase06_kernel_release as release
        from test_candidate_verification import setup
        from test_owned_effect_recovery import GitOccurrenceFixture

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline_dir, candidate_dir, _ = setup(root)
            baseline = json.loads((baseline_dir / 'manifest.json').read_text())
            candidate = json.loads((candidate_dir / 'manifest.json').read_text())
            created = datetime.now(timezone.utc) - timedelta(seconds=10)
            packet = plan_release(baseline, candidate, created,
                                  schema='manager.digital-handoff.v2')
            git = GitOccurrenceFixture(root / 'public-git', baseline_dir, candidate_dir, packet)
            store = CycleStore(root / 'runner-temp' / 'private-state')
            publisher = PublisherContext(REPOSITORY, MAIN_REF, WORKFLOW,
                candidate['source_commit'], '123', workflow_commit=candidate['source_commit'])
            store.journal.reserve(packet, publisher, baseline, candidate, git.parent, created)
            receipt = git.send(git.parent)
            occurrence = git.evidence(receipt)
            store.journal._present(packet['effect_key'], receipt)
            store.journal.save_delivery(packet['effect_key'], {
                'status': 'VERIFIED', 'effect_key': packet['effect_key'],
                'receipt_ref': receipt, 'candidate_sha256': packet['candidate_sha256'],
                'observed_at': datetime.now(timezone.utc).isoformat(),
                'proof_ref': PUBLIC_BASE, 'proof_level': 'P2',
                'reason': 'EXACT_DEPLOYED_CANDIDATE', 'human_outcome': 'NOT_MEASURED'})

            target_url = f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/gh-pages'
            list_url = (f'https://api.github.com/repos/{REPOSITORY}/commits'
                        '?sha=gh-pages&per_page=100&page=1')
            runs_url = (f'https://api.github.com/repos/{REPOSITORY}/actions/workflows/307239134/runs'
                        '?branch=gh-pages&per_page=100')
            detail_url = f'https://api.github.com/repos/{REPOSITORY}/commits/{receipt}'
            urls = {
                target_url: json.dumps({'ref': 'refs/heads/gh-pages',
                    'object': {'type': 'commit', 'sha': receipt}}).encode(),
                list_url: json.dumps([{'sha': receipt, 'commit': {
                    'message': occurrence.receipt['commit']['message']}}]).encode(),
                detail_url: json.dumps(occurrence.receipt).encode(),
                runs_url: json.dumps({'workflow_runs': [{
                    'workflow_id': 307239134, 'path': '.github/workflows/pages.yml',
                    'event': 'workflow_dispatch', 'head_branch': 'gh-pages',
                    'head_repository': {'full_name': REPOSITORY}, 'head_sha': receipt,
                    'status': 'completed', 'conclusion': 'success',
                    'created_at': occurrence.receipt['commit']['committer']['date']}]}).encode(),
                PUBLIC_BASE + 'manifest.json': json.dumps(candidate).encode(),
            }
            for commit, bodies in ((receipt, occurrence.committed_bodies),
                                   (git.parent, occurrence.parent_bodies)):
                for name, raw in bodies.items():
                    urls[f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/manager-support/{name}'] = raw
            urls.update({PUBLIC_BASE + name: raw for name, raw in occurrence.committed_bodies.items()
                         if name != 'manifest.json'})

            def public_get(url):
                self.assertIn(url, urls, 'current proof used an unexpected public URL')
                return urls[url]

            checkpoint = PrivateCheckpoint(run_id='123', run_attempt='1')
            checkpoint.db = store.db
            checkpoint.owner = '123:1:private-owner'
            checkpoint.nonce = 'private-owner'
            checkpoint.revision = 1
            checkpoint.broken = False
            host = GitHubActionsCycleHost(checkpoint, root, None)
            no_op = dict(_cycle_result('NOT_DUE'),
                         nonce='no-op-private-nonce-sentinel',
                         private_snapshot='no-op-private-snapshot-sentinel')
            with patch.object(release, 'public_get', side_effect=public_get):
                current_report = cli._select_current_noop_proof(store, host, no_op)
                self.assertIsNotNone(current_report)
                self.assertEqual(current_report['status'], 'VERIFIED_PUBLIC_ARTIFACT_ONLY')
                self.assertEqual(current_report['proof_level'], 'P2')
                self.assertEqual(current_report['receipt_ref'], receipt)
                self.assertEqual(no_op['proof_level'], 'P0')
                self.assertEqual(no_op['writes'], 0)
                exported = cli._export_current_kernel_proof(
                    checkpoint, store, current_report, root / 'runner-temp')
            self.assertTrue(exported)
            proof_dir = root / 'runner-temp' / 'manager-kernel-proof'
            self.assertEqual({path.name for path in proof_dir.iterdir()},
                             {'kernel-public-proof.json', 'proof-explorer.html'})
            proof = json.loads((proof_dir / 'kernel-public-proof.json').read_text())
            self.assertEqual(proof['pages_commit'], receipt)
            self.assertEqual(proof['status'], 'VERIFIED_PUBLIC_ARTIFACT_ONLY')
            self.assertEqual(proof['human_outcome'], 'NOT_MEASURED')
            html = (proof_dir / 'proof-explorer.html').read_text()
            self.assertIn('owned.pages.commit_occurrence', html)
            self.assertIn('owned.pages.served_bundle_bytes', html)
            self.assertNotIn(packet['effect_key'], html)
            public_files = ''.join(path.read_text() for path in proof_dir.iterdir())
            self.assertNotIn('no-op-private-nonce-sentinel', public_files)
            self.assertNotIn('no-op-private-snapshot-sentinel', public_files)
            self.assertNotIn('provenance_refs', public_files)
            self.assertEqual(git.git('rev-list', '--count', 'HEAD'), '2')

            for untrusted in (
                    dict(current_report, status='UNKNOWN', proof_level='P0'),
                    dict(current_report, proof_level='P0'),
                    dict(current_report, receipt_ref='f' * 40),
                    dict(current_report, candidate_sha256='e' * 64)):
                current = {'kind': 'candidate', 'effect_key': packet['effect_key'],
                           'receipt_ref': receipt, 'evidence': untrusted}
                with patch.object(host, 'observe_current_delivery', return_value=current):
                    self.assertIsNone(cli._select_current_noop_proof(store, host, no_op))
            with patch.object(host, 'observe_current_delivery', return_value={
                    'kind': 'rollback', 'effect_key': packet['effect_key'],
                    'receipt_ref': receipt, 'evidence': current_report}):
                self.assertIsNone(cli._select_current_noop_proof(store, host, no_op))

    def test_not_due_run_once_saves_selected_current_proof_without_canary_upgrade(self):
        events = []
        selected = {'status': 'VERIFIED_PUBLIC_ARTIFACT_ONLY', 'proof_level': 'P2',
                    'deployed': True, 'effect_key': 'a' * 64, 'receipt_ref': 'b' * 40}
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
        class Host:
            _catalog_shadow_result = None
            def __init__(self, *args, **kwargs): pass
        from manager_core.owned_cycle import _cycle_result
        report = _cycle_result('NOT_DUE')
        def select(*args):
            events.append('select_current')
            return selected
        def export(checkpoint, store, proof_report, runner_temp):
            events.append(('export', proof_report))
            return True
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(cli, '_check_main_context', return_value={'run_id': '7', 'attempt': '1',
                 'source_sha': 'c' * 40, 'runner_temp': Path(tmp).resolve(),
                 'pages_root': Path(tmp) / 'pages'}), \
             patch.object(cli, 'PrivateCheckpoint', Checkpoint), \
             patch.object(cli, 'CycleStore', Store), \
             patch.object(cli, 'GitHubActionsCycleHost', Host), \
             patch.object(cli, 'run_owned_cycle', return_value=report), \
             patch.object(cli, '_select_current_noop_proof', side_effect=select), \
             patch.object(cli, '_export_current_kernel_proof', side_effect=export):
            code, summary = cli.run_once(Path(tmp) / 'fresh', Path(tmp) / 'pages')
        self.assertEqual(code, 0)
        self.assertEqual(summary['status'], 'NOT_DUE')
        self.assertEqual(summary['proof_level'], 'P0')
        self.assertEqual(summary['writes'], 0)
        self.assertEqual(summary['positive_canary'], 'NOT_RUN')
        self.assertTrue(summary['current_proof_exported'])
        self.assertEqual(summary['current_proof_receipt_sha'], 'b' * 40)
        self.assertEqual(events, ['select_current', 'save', ('export', selected), 'release'])

        events.clear()
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(cli, '_check_main_context', return_value={'run_id': '7', 'attempt': '1',
                 'source_sha': 'c' * 40, 'runner_temp': Path(tmp).resolve(),
                 'pages_root': Path(tmp) / 'pages'}), \
             patch.object(cli, 'PrivateCheckpoint', Checkpoint), \
             patch.object(cli, 'CycleStore', Store), \
             patch.object(cli, 'GitHubActionsCycleHost', Host), \
             patch.object(cli, 'run_owned_cycle', return_value=report), \
             patch.object(cli, '_select_current_noop_proof', side_effect=select), \
             patch.object(cli, '_export_current_kernel_proof', return_value=False):
            code, failed = cli.run_once(Path(tmp) / 'fresh', Path(tmp) / 'pages')
        self.assertEqual(code, 0)
        self.assertFalse(failed['current_proof_exported'])
        self.assertIsNone(failed['current_proof_receipt_sha'])
        self.assertEqual(failed['positive_canary'], 'NOT_RUN')
        self.assertEqual(failed['writes'], 0)

    def test_current_v1_seed_is_never_selected_for_noop_proof(self):
        from datetime import datetime
        from manager_core.digital_handoff import (REPOSITORY, SOURCE_REF, WORKFLOW,
            PublisherContext)
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from manager_core.owned_cycle import CycleStore, _cycle_result
        from manager_core.owned_platform_host import GitHubActionsCycleHost
        from test_owned_public_collector import PublicCollectorTests

        with tempfile.TemporaryDirectory() as tmp:
            packet, source_journal, receipt, _, _, _ = (
                PublicCollectorTests().prepare_v1_current_fixture(tmp))
            original = source_journal.record(packet['effect_key'])
            root = Path(tmp) / 'runner-temp'
            store = CycleStore(root / 'private-state')
            publisher = PublisherContext(REPOSITORY, SOURCE_REF, WORKFLOW,
                packet['candidate']['source_commit'], '123')
            store.journal.reserve(packet, publisher, packet['baseline'], packet['candidate'],
                original.expected_parent, datetime.fromisoformat(packet['created_at']))
            store.journal._present(packet['effect_key'], receipt)
            checkpoint = PrivateCheckpoint(run_id='123', run_attempt='1')
            checkpoint.db = store.db
            host = GitHubActionsCycleHost(checkpoint, root, None)
            evidence = {'status': 'VERIFIED', 'proof_level': 'P2',
                        'effect_key': packet['effect_key'], 'receipt_ref': receipt,
                        'candidate_sha256': packet['candidate_sha256'],
                        'reason': 'EXACT_DEPLOYED_CANDIDATE'}
            current = {'kind': 'candidate', 'effect_key': packet['effect_key'],
                       'receipt_ref': receipt, 'evidence': evidence}
            with patch.object(host, 'observe_current_delivery', return_value=current):
                self.assertIsNone(cli._select_current_noop_proof(
                    store, host, _cycle_result('NOT_DUE')))

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
             patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: SimpleNamespace(_catalog_shadow_result=None)), \
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
             patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: SimpleNamespace(_catalog_shadow_result=None)), \
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
             patch.object(cli, 'GitHubActionsCycleHost', lambda *a, **k: SimpleNamespace(_catalog_shadow_result=None)), \
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
