import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_runner import command_for  # noqa: E402


TENANT = 'lm_11111111-1111-4111-8111-111111111111'


class MaritimeBrowserCommandTests(unittest.TestCase):
    def command(self, env):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            env = dict(env)
            tenant_id = env.get('LM_RUNTIME_TENANT_ID', TENANT)
            tenant_root = root / tenant_id
            tenant_root.mkdir(mode=0o700)
            if 'LM_MARITIME_BROWSER_RECEIPT' in env:
                source_root = Path('/data') / TENANT
                receipt = Path(env['LM_MARITIME_BROWSER_RECEIPT'])
                try:
                    relative = receipt.relative_to(source_root)
                    receipt = tenant_root / relative
                except ValueError:
                    receipt = root / receipt.relative_to('/data')
                receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                env['LM_MARITIME_BROWSER_RECEIPT'] = str(receipt)
            env['LIFE_MANAGER_STATE_HOME'] = str(tenant_root)
            args = argparse.Namespace(
                task_class='application-lane-agent', workdir=root,
                evidence_dir=root, image=[],
            )
            with patch.dict(os.environ, env, clear=True):
                return command_for(
                    'codex', '/fake/codex', {},
                    {'model': 'gpt-5.6-terra', 'effort': 'medium'},
                    args, 'Use the isolated live browser session.', {}, root / 'result.json',
                )

    def maritime_env(self, **extra):
        return {
            'LM_RUNTIME_HOST': 'maritime', 'LM_RUNTIME_TENANT_ID': TENANT,
            'LIFE_MANAGER_STATE_HOME': f'/data/{TENANT}',
            'LM_MARITIME_BROWSER_CDP_URL': 'http://127.0.0.1:9229',
            'LM_MARITIME_BROWSER_RECEIPT': f'/data/{TENANT}/receipts/cycle-1/browser-actions.jsonl',
            **extra,
        }

    def overrides(self, command):
        return [command[index + 1] for index, value in enumerate(command[:-1]) if value == '-c']

    def test_maritime_agent_gets_only_tenant_scoped_browser_mcp_and_no_shell(self):
        command = self.command(self.maritime_env(LM_CLOUD_MODEL_API_KEY='tenant-model-secret'))
        overrides = self.overrides(command)
        self.assertIn('mcp_servers.maritime_browser.required=true', overrides)
        self.assertIn('mcp_servers.maritime_browser.default_tools_approval_mode="approve"', overrides)
        enabled_tools = next(value.split('=', 1)[1] for value in overrides
                             if value.startswith('mcp_servers.maritime_browser.enabled_tools='))
        self.assertEqual(json.loads(enabled_tools), [
            'browser_observe', 'browser_navigate', 'browser_search',
        ])
        args_value = next(value.split('=', 1)[1] for value in overrides
                          if value.startswith('mcp_servers.maritime_browser.args='))
        mcp_args = json.loads(args_value)
        self.assertIn('--ignore-environment', mcp_args)
        self.assertIn('LM_RUNTIME_TENANT_ID=' + TENANT, mcp_args)
        self.assertIn('LM_MARITIME_BROWSER_CDP_URL=http://127.0.0.1:9229', mcp_args)
        self.assertIn('--tenant-root', mcp_args)
        self.assertTrue(any(value.endswith('/' + TENANT) for value in mcp_args))
        self.assertIn('--receipt-path', mcp_args)
        self.assertTrue(any(value.endswith('/receipts/cycle-1/browser-actions.jsonl') for value in mcp_args))
        self.assertIn('shell_tool', command)
        self.assertIn('unified_exec', command)
        self.assertNotIn('tenant-model-secret', json.dumps(command))

    def test_maritime_agent_fails_closed_if_session_or_receipt_is_missing(self):
        for missing in ['LM_MARITIME_BROWSER_CDP_URL', 'LM_MARITIME_BROWSER_RECEIPT']:
            env = self.maritime_env()
            del env[missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'maritime browser'):
                self.command(env)

    def test_maritime_agent_rejects_non_loopback_endpoint_and_foreign_receipt(self):
        for changes in [
            {'LM_MARITIME_BROWSER_CDP_URL': 'http://192.0.2.1:9229'},
            {'LM_MARITIME_BROWSER_RECEIPT': '/data/other/browser-actions.jsonl'},
        ]:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'maritime browser'):
                self.command(self.maritime_env(**changes))

    def test_non_maritime_agent_receives_no_browser_server(self):
        env = self.maritime_env()
        env['LM_RUNTIME_HOST'] = 'self-hosted'
        command = self.command(env)
        overrides = self.overrides(command)
        self.assertFalse(any('mcp_servers.maritime_browser.' in value for value in overrides))
        self.assertNotIn('shell_tool', command)


if __name__ == '__main__':
    unittest.main()
