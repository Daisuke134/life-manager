import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/substack-publish/verify-preview.py'


def load_module():
    spec = importlib.util.spec_from_file_location('verify_preview', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, {'SUBSTACK_PUBLICATION': 'writer-test.substack.com'}):
        spec.loader.exec_module(module)
    return module


class VerifyPreviewTests(unittest.TestCase):
    def test_owned_preview_and_cleanup_on_pass_or_image_failure(self):
        for sizes, expected in [([[728, 440]], 0), ([[728, 1000]], 1), ([], 1)]:
            with self.subTest(sizes=sizes), tempfile.TemporaryDirectory() as temp:
                module = load_module()
                calls = []
                def evaluate(target, expression):
                    self.assertEqual(target, 'owned-tab')
                    if 'document.body.innerText' in expression:
                        return 'article text ' * 40
                    if "querySelectorAll('img')" in expression:
                        return sizes
                    return True
                cdp = SimpleNamespace(
                    new_target=mock.Mock(return_value='owned-tab'),
                    close_target=mock.Mock(),
                    evaluate=evaluate,
                    navigate=mock.Mock(),
                    screenshot=mock.Mock(),
                    _browser_call=lambda method, params: calls.append((method, params)),
                    _page=mock.Mock(return_value=SimpleNamespace(close=mock.Mock())),
                    _rpc=mock.Mock(),
                )
                lease = SimpleNamespace(
                    acquire=mock.Mock(return_value={'ok': True, 'context_id': 'owned-context', 'token': 'lease-token', 'generation': 1}),
                    release=mock.Mock(),
                )
                with (
                    mock.patch.dict(sys.modules, {'cdp': cdp, 'cdp_context_lease': lease}),
                    mock.patch.dict(os.environ, {'SUBSTACK_SESSION_COOKIE': 'session=test', 'CDP': 'http://[::1]:9222', 'LIFE_MANAGER_BROWSER_LEASE_IDENTITY': 'interactive:dais'}),
                    mock.patch.object(module, 'W', temp),
                    mock.patch.object(module.time, 'sleep'),
                    mock.patch.object(module, 'sync_playwright', create=True, side_effect=AssertionError('browser-wide attachment forbidden')),
                ):
                    if sizes:
                        self.assertEqual(module.verify_once('123', 950), expected)
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'images were not measured'):
                            module.verify_once('123', 950)
                self.assertEqual(calls[0][0], 'Storage.setCookies')
                self.assertEqual(calls[0][1]['browserContextId'], 'owned-context')
                cdp.close_target.assert_called_once()
                lease.release.assert_called_once()
                self.assertEqual(lease.release.call_args.kwargs, {'token': 'lease-token', 'generation': 1})

    def test_busy_guard_defers_without_opening_a_page(self):
        module = load_module()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(module, 'subprocess', create=True) as process,
            mock.patch.object(module, 'verify_once') as verify,
        ):
            process.run.return_value.returncode = 75
            self.assertEqual(module.main(['123', '950']), 75)
        verify.assert_not_called()
        self.assertIn('with-browser.sh', ' '.join(process.run.call_args.args[0]))
        self.assertEqual(process.run.call_args.kwargs['env']['BROWSER_WAIT_SECONDS'], '0')


if __name__ == '__main__':
    unittest.main()
