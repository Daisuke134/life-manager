import importlib.util
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import types
import unittest

MODULE = Path(__file__).parents[1] / 'scripts/cloud_cycle.py'
TENANT = 'lm_11111111-1111-4111-8111-111111111111'


class CloudCycleTest(unittest.TestCase):
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

    def runner(self, command, **options):
        self.calls.append((command, options))
        artifact = self.work / 'original-product.md'
        artifact.write_text('Original skill and listing prepared for this tenant.')
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
        self.assertEqual(command[command.index('--workdir') + 1], str(self.work))
        self.assertEqual(opts['cwd'], str(self.work))
        self.assertEqual(opts['env']['HOME'], str(self.home / 'home'))
        self.assertEqual(opts['env']['AGENT_RUNNER_CONFIG'], str(self.config))
        self.assertIn('No provider account is connected', opts['input'])
        self.assertNotIn('goal', command)
        self.assertEqual(result['providerReceiptRefs'], [])
        self.assertEqual(len(result['artifactRefs']), 1)

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
        for directory in ['home', 'codex', 'claude', 'evidence', 'state', 'runtime', 'tmp', 'ledgers']:
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


if __name__ == '__main__':
    unittest.main()
