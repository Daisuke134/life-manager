import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import shutil
import tempfile
import types
import unittest

MODULE = Path(__file__).parents[1] / 'scripts/cloud_cycle.py'
TENANT = 'lm_11111111-1111-4111-8111-111111111111'


class CloudCycleTest(unittest.TestCase):
    def test_cycle_owns_tenant_browser_and_passes_only_its_loopback_endpoint(self):
        self.env.update(CAPAFY_CHROMIUM='/parent/browser', CLOAKBROWSER_BINARY_PATH='/parent/browser',
                        CAPAFY_BROWSER_PROFILE='/parent/profile',
                        LM_MARITIME_BROWSER_CDP_URL='http://attacker.invalid:9999')
        result = self.run_cycle()
        self.assertEqual(result['status'], 'completed')
        child = self.calls[0][1]['env']
        self.assertEqual(child['LM_MARITIME_BROWSER_CDP_URL'], 'http://127.0.0.1:9229')
        self.assertEqual(self.browser_sessions[0]['tenant_id'], TENANT)
        self.assertEqual(self.browser_sessions[0]['data_root'], self.root)
        self.assertEqual(self.browser_sessions[0]['profile'], self.home / 'browser' / 'profile')
        for key in ['CAPAFY_CHROMIUM', 'CLOAKBROWSER_BINARY_PATH', 'CAPAFY_BROWSER_PROFILE']:
            self.assertNotIn(key, child)
        self.assertTrue(self.browser_sessions[0]['closed'])

    def test_browser_start_failure_defers_before_runner_and_is_replay_safe(self):
        class BrokenBrowserSession:
            def __init__(self, **_kwargs):
                pass

            def __enter__(self):
                raise self.module.BrowserSessionError('browser_session_startup_failed')

            def __exit__(self, *_args):
                return False

        BrokenBrowserSession.module = self.module
        self.module.BrowserSession = BrokenBrowserSession
        result = self.run_cycle()
        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(result['errorClass'], 'browser_session_startup_failed')
        self.assertEqual(self.run_cycle(), result)
        self.assertEqual(self.calls, [])

    def test_linux_browser_owner_uses_existing_binary_headlessly(self):
        import os
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            browser = root / 'browser'
            browser.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            browser.chmod(0o700)
            uname = root / 'uname'
            uname.write_text('#!/bin/sh\necho Linux\n')
            uname.chmod(0o700)
            script = MODULE.parent / 'browser-owner'
            env = {'PATH': str(root) + ':/usr/bin:/bin', 'HOME': str(root),
                   'CAPAFY_BROWSER_PORT_OWNED': '1', 'CAPAFY_CHROMIUM': str(browser)}
            result = subprocess.run(['bash', str(script)], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--headless=new', result.stdout.splitlines())
            self.assertIn('--disable-dev-shm-usage', result.stdout.splitlines())
            self.assertNotIn('--no-sandbox', result.stdout.splitlines())

    def test_macos_browser_owner_runs_under_bash32_with_no_platform_args(self):
        """2026-10-24: 'platform_args[@]: unbound variable' kept the Capafy console browser down on macOS bash 3.2."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            browser = root / 'browser'
            browser.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            browser.chmod(0o700)
            uname = root / 'uname'
            uname.write_text('#!/bin/sh\necho Darwin\n')
            uname.chmod(0o700)
            script = MODULE.parent / 'browser-owner'
            env = {'PATH': str(root) + ':/usr/bin:/bin', 'HOME': str(root),
                   'CAPAFY_BROWSER_PORT_OWNED': '1', 'CAPAFY_CHROMIUM': str(browser)}
            result = subprocess.run(['/bin/bash', str(script)], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('--headless=new', result.stdout.splitlines())
            self.assertIn('--no-first-run', result.stdout.splitlines())

    def setUp(self):
        self.assertTrue(MODULE.exists(), 'cloud_cycle.py must implement the tenant adapter')
        spec = importlib.util.spec_from_file_location('cloud_cycle', MODULE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / TENANT
        self.work = self.home / 'build'
        self.work.mkdir(parents=True)
        self.config = self.home / 'runner.json'
        self.config.write_text('{}')
        self.env = {'LM_RUNTIME_HOST': 'maritime', 'LM_RUNTIME_TENANT_ID': TENANT,
                    'LIFE_MANAGER_STATE_HOME': str(self.home),
                    'LIFE_MANAGER_BUILD_WORKSPACE': str(self.work),
                    'AGENT_RUNNER_CONFIG': str(self.config), 'LM_RELEASE_SHA': 'a' * 40}
        self.calls = []
        self.browser_sessions = []
        module = self.module
        browser_sessions = self.browser_sessions

        class FakeBrowserSession:
            def __init__(self, *, tenant_id, data_root, release_root, **_kwargs):
                self.cdp_url = 'http://127.0.0.1:9229'
                self.record = {'tenant_id': tenant_id, 'data_root': Path(data_root),
                               'release_root': Path(release_root),
                               'profile': Path(data_root) / tenant_id / 'browser' / 'profile',
                               'closed': False}
                browser_sessions.append(self.record)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.record['closed'] = True
                return False

        module.BrowserSession = FakeBrowserSession

    def runner(self, command, **options):
        self.calls.append((command, options))
        artifact = Path(command[command.index('--workdir') + 1]) / 'original-product.md'
        artifact.write_text('Original skill and listing prepared for this tenant.')
        receipt = Path(options['env']['LM_MARITIME_BROWSER_RECEIPT'])
        receipt.write_text('\n'.join(json.dumps(row) for row in [
            {'at': '2026-10-20T00:00:00Z', 'actionId': 'a' * 32, 'tool': 'browser_navigate',
             'outcome': 'started', 'origin': 'https://capafy.ai'},
            {'at': '2026-10-20T00:00:01Z', 'actionId': 'a' * 32, 'tool': 'browser_navigate',
             'outcome': 'opened', 'origin': 'https://capafy.ai'},
        ]) + '\n')
        receipt.chmod(0o600)
        return types.SimpleNamespace(returncode=0, stdout=json.dumps({'status': 'success', 'evidence': [str(artifact)]}), stderr='')

    def run_cycle(self, runner=None, occurrence='cycle-1'):
        return self.module.run_cycle(TENANT, occurrence, '2026-10-20', env=self.env,
                                     data_root=self.root, runner=runner or self.runner)

    def test_cycle_calls_existing_factory_once_and_scopes_workspace(self):
        result = self.run_cycle()
        again = self.run_cycle()
        self.assertEqual(result, again)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(self.calls), 1)
        command, opts = self.calls[0]
        self.assertTrue(command[1].endswith('/skills/earn/marketing-engine/run_agent.sh'))
        occurrence_work = self.work / 'occurrences' / 'cycle-1'
        self.assertEqual(command[command.index('--workdir') + 1], str(occurrence_work))
        self.assertEqual(opts['cwd'], str(occurrence_work))
        self.assertEqual(opts['env']['HOME'], str(self.home / 'home'))
        self.assertEqual(opts['env']['AGENT_RUNNER_CONFIG'], str(self.config))
        self.assertEqual(opts['env']['AGENT_RUNNER_WORKDIR'], str(occurrence_work))
        self.assertEqual(opts['env']['LIFE_MANAGER_BUILD_WORKSPACE'], str(self.work))
        self.assertIn('No authorized Publisher identity is connected', opts['input'])
        self.assertIn('maritime_browser MCP tools', opts['input'])
        self.assertNotIn('Reuse the existing Capafy factory', opts['input'])
        self.assertNotIn('goal', command)
        self.assertEqual(result['providerReceiptRefs'], [])
        self.assertEqual(len(result['artifactRefs']), 1)

    def test_success_receipt_closes_started_browser_action(self):
        result = self.run_cycle()
        action_receipt = self.home / 'receipts/cycle-1/browser-actions.jsonl'
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(self.module._browser_action_effect_unknown(action_receipt, os.geteuid()))

    def test_unclosed_browser_action_stays_unknown_even_if_runner_reports_success(self):
        def interrupted_after_dispatch(command, **options):
            self.calls.append((command, options))
            artifact = Path(command[command.index('--workdir') + 1]) / 'draft.md'
            artifact.write_text('draft')
            receipt = Path(options['env']['LM_MARITIME_BROWSER_RECEIPT'])
            receipt.write_text(json.dumps({
                'at': '2026-10-20T00:00:00Z', 'actionId': 'b' * 32,
                'tool': 'browser_search', 'outcome': 'started', 'origin': 'https://capafy.ai',
            }) + '\n')
            receipt.chmod(0o600)
            return types.SimpleNamespace(returncode=0,
                stdout=json.dumps({'status': 'success', 'evidence': [str(artifact)]}), stderr='')

        result = self.run_cycle(interrupted_after_dispatch)
        self.assertEqual(result['status'], 'effect_unknown')
        self.assertEqual(result['errorClass'], 'browser_effect_unknown')
        self.assertEqual(self.run_cycle(interrupted_after_dispatch), result)
        self.assertEqual(len(self.calls), 1)

    def test_cloud_output_schema_requires_literal_owned_file_paths(self):
        def checked(command, **options):
            schema = json.loads(Path(command[command.index('--schema') + 1]).read_text())
            pattern = schema['properties']['evidence']['items']['pattern']
            artifact = str(Path(command[command.index('--workdir') + 1]) / '商品と掲載原稿.md')
            self.assertIsNotNone(re.search(pattern, artifact))
            self.assertIsNotNone(re.search(pattern, 'file://' + artifact))
            self.assertIsNone(re.search(pattern, 'Created original offline product: ' + artifact))
            self.assertIsNone(re.search(pattern, '/other-tenant/build/product.md'))
            return self.runner(command, **options)
        self.assertEqual(self.run_cycle(checked)['status'], 'completed')

    def test_unconfigured_cloud_route_does_not_use_local_profiles(self):
        del self.env['AGENT_RUNNER_CONFIG']
        result = self.run_cycle()
        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(result['errorClass'], 'cloud_model_config_missing')
        self.assertEqual(self.calls, [])

    def test_foreign_binding_is_rejected_before_model_execution(self):
        self.env['LM_CAPAFY_BINDING_JSON'] = json.dumps({'tenantId': 'lm_22222222-2222-4222-8222-222222222222', 'provider': 'capafy', 'subjectId': 'seller-2'})
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.run_cycle()
        self.assertEqual(self.calls, [])

    def test_workspace_escape_is_rejected_before_execution(self):
        self.env['LIFE_MANAGER_BUILD_WORKSPACE'] = str(self.root / 'other-user')
        with self.assertRaisesRegex(ValueError, 'workspace'):
            self.run_cycle()
        self.assertEqual(self.calls, [])

    def test_receipt_symlink_cannot_write_to_another_tenant(self):
        foreign = self.root / 'foreign-receipts'
        foreign.mkdir()
        (self.home / 'receipts').symlink_to(foreign, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'receipt'):
            self.run_cycle()
        self.assertEqual(list(foreign.iterdir()), [])
        self.assertEqual(self.calls, [])

    def test_tenant_root_symlink_cannot_alias_another_user(self):
        foreign = self.root / 'lm_22222222-2222-4222-8222-222222222222'
        (foreign / 'build').mkdir(parents=True)
        (foreign / 'runner.json').write_text('{}')
        shutil.rmtree(self.home)
        self.home.symlink_to(foreign, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'tenant'):
            self.run_cycle()
        self.assertEqual(self.calls, [])

    def test_provider_reference_must_be_metadata_not_a_secret_object(self):
        self.env['LM_CAPAFY_BINDING_JSON'] = json.dumps({'tenantId': TENANT, 'provider': 'capafy', 'subjectId': 'seller-a', 'credentialRef': {'secret': 'fixture'}})
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.run_cycle()
        self.assertEqual(self.calls, [])

    def test_timeout_is_unknown_and_replay_does_not_dispatch(self):
        def timeout(command, **options):
            self.calls.append((command, options))
            raise subprocess.TimeoutExpired(command, options['timeout'])
        result = self.run_cycle(timeout)
        self.assertEqual(result['status'], 'effect_unknown')
        self.assertEqual(self.run_cycle()['status'], 'effect_unknown')
        self.assertEqual(len(self.calls), 1)

    def test_child_directories_cannot_alias_another_tenant(self):
        foreign = self.root / 'other-tenant'
        foreign.mkdir()
        for directory in ['home', 'agent-codex', 'claude', 'evidence', 'state', 'runtime', 'tmp', 'agent-ledgers']:
            with self.subTest(directory=directory):
                link = self.home / directory
                if link.exists():
                    shutil.rmtree(link)
                self.calls.clear()
                link.symlink_to(foreign, target_is_directory=True)
                try:
                    with self.assertRaisesRegex(ValueError, 'child_path'):
                        self.run_cycle(occurrence='escape-' + directory)
                    self.assertEqual(self.calls, [])
                    self.assertEqual(list(foreign.iterdir()), [])
                finally:
                    link.unlink()

    def test_child_environment_excludes_parent_secrets_and_rebinds_ledgers(self):
        self.env.update(FOUNDER_SECRET='fixture-private', SUPABASE_SERVICE_ROLE_KEY='fixture-db',
                        ANICCA_USAGE_LEDGER='/parent/usage.jsonl',
                        ANICCA_TOKEN_BUDGET_LEDGER='/parent/budget.jsonl',
                        LM_CLOUD_MODEL_API_KEY='fixture-tenant-model')
        self.run_cycle()
        child = self.calls[0][1]['env']
        self.assertNotIn('FOUNDER_SECRET', child)
        self.assertNotIn('SUPABASE_SERVICE_ROLE_KEY', child)
        self.assertEqual(child['LM_CLOUD_MODEL_API_KEY'], 'fixture-tenant-model')
        for key in ['ANICCA_USAGE_LEDGER', 'ANICCA_TOKEN_BUDGET_LEDGER', 'TMPDIR']:
            self.assertTrue(Path(child[key]).is_relative_to(self.home), key)

    def test_cached_receipt_rejects_extra_fields_and_unowned_artifacts(self):
        self.run_cycle()
        receipt = self.home / 'receipts/cycle-1/cycle.json'
        original = json.loads(receipt.read_text())
        for change in [{'rawSecret': 'fixture-secret'},
                       {'artifactRefs': ['artifact://../../other/private.txt']},
                       {'providerReceiptRefs': ['unverified-receipt']},
                       {'status': 'invented-status'}]:
            with self.subTest(change=change):
                saved = json.loads(json.dumps(original))
                saved['result'].update(change)
                receipt.write_text(json.dumps(saved))
                result = self.run_cycle()
                self.assertEqual(result['status'], 'effect_unknown')
                self.assertNotIn('fixture-secret', json.dumps(result))
                self.assertEqual(result['artifactRefs'], [])
        self.assertEqual(len(self.calls), 1)

    def test_success_without_owned_artifact_is_not_completed(self):
        def unproven(command, **options):
            return types.SimpleNamespace(returncode=0, stdout=json.dumps({'status': 'success', 'evidence': ['/etc/passwd']}), stderr='')
        self.assertNotEqual(self.run_cycle(unproven)['status'], 'completed')


    def test_no_op_with_owned_draft_artifacts_records_completed_offline_work(self):
        def no_op_with_draft(command, **options):
            self.calls.append((command, options))
            artifact = Path(command[command.index('--workdir') + 1]) / 'offline-draft.md'
            artifact.write_text('Original draft; not published.')
            return types.SimpleNamespace(returncode=0,
                stdout=json.dumps({'status': 'no_op', 'evidence': [str(artifact)]}), stderr='')

        result = self.run_cycle(no_op_with_draft)
        self.assertEqual(result['status'], 'completed')
        self.assertIsNone(result['errorClass'])
        self.assertEqual(result['artifactRefs'], ['artifact://occurrences/cycle-1/offline-draft.md'])
        self.assertIsNone(result['providerSnapshotRef'])
        self.assertEqual(result['providerReceiptRefs'], [])
        self.assertIsNone(result['nextEligibleAt'])
        self.assertEqual(self.run_cycle()['artifactRefs'], result['artifactRefs'])
        self.assertEqual(len(self.calls), 1)

    def test_no_op_with_stale_owned_artifacts_remains_deferred(self):
        artifact = self.work / 'prior-draft.md'
        artifact.write_text('Draft from an earlier cycle.')

        def no_work(command, **options):
            self.calls.append((command, options))
            return types.SimpleNamespace(returncode=0,
                stdout=json.dumps({'status': 'no_op', 'evidence': [str(artifact)]}), stderr='')

        result = self.run_cycle(no_work)
        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(result['errorClass'], 'no_work')
        self.assertEqual(result['artifactRefs'], [])
        self.assertEqual(len(self.calls), 1)

    def test_no_op_does_not_reuse_a_preexisting_occurrence_directory(self):
        occurrence_parent = self.work / 'occurrences'
        occurrence_parent.mkdir(mode=0o700)
        occurrence_work = occurrence_parent / 'cycle-1'
        occurrence_work.mkdir(mode=0o700)
        old_artifact = occurrence_work / 'old-draft.md'
        old_artifact.write_text('Draft from an earlier unreceipted cycle.')

        result = self.run_cycle()

        self.assertEqual(result['status'], 'effect_unknown')
        self.assertEqual(result['errorClass'], 'occurrence_workspace_preexisting')
        self.assertEqual(result['artifactRefs'], [])
        self.assertEqual(self.calls, [])
        self.assertEqual(old_artifact.read_text(), 'Draft from an earlier unreceipted cycle.')

    def test_no_op_rejects_a_symlinked_occurrence_parent(self):
        foreign = self.root / 'foreign-occurrences'
        foreign.mkdir()
        (self.work / 'occurrences').symlink_to(foreign, target_is_directory=True)

        result = self.run_cycle()

        self.assertEqual(result['status'], 'effect_unknown')
        self.assertEqual(result['errorClass'], 'occurrence_workspace_unavailable')
        self.assertEqual(result['artifactRefs'], [])
        self.assertEqual(self.calls, [])
        self.assertEqual(list(foreign.iterdir()), [])

    def test_no_op_does_not_accept_symlink_or_hard_link_artifacts(self):
        import os

        def linked_artifacts(command, **options):
            occurrence_work = Path(command[command.index('--workdir') + 1])
            occurrence_work.mkdir(parents=True, exist_ok=True)
            source = self.work / 'shared-draft.md'
            source.write_text('Shared file outside occurrence output.')
            symlink = occurrence_work / 'symlink.md'
            symlink.symlink_to(source)
            hardlink = occurrence_work / 'hardlink.md'
            os.link(source, hardlink)
            non_file = occurrence_work / 'directory'
            non_file.mkdir()
            self.calls.append((command, options))
            return types.SimpleNamespace(returncode=0,
                stdout=json.dumps({'status': 'no_op', 'evidence': [str(symlink), str(hardlink), str(non_file)]}), stderr='')

        result = self.run_cycle(linked_artifacts)

        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(result['errorClass'], 'no_work')
        self.assertEqual(result['artifactRefs'], [])

    def test_no_op_without_owned_artifacts_remains_deferred(self):
        def no_work(command, **options):
            self.calls.append((command, options))
            return types.SimpleNamespace(returncode=0,
                stdout=json.dumps({'status': 'no_op', 'evidence': []}), stderr='')

        result = self.run_cycle(no_work)
        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(result['errorClass'], 'no_work')
        self.assertEqual(result['artifactRefs'], [])
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
