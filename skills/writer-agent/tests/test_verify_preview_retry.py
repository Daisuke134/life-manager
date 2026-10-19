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


def fake_browser(evaluate):
    """An ephemeral headless CloakBrowser context: launch_context -> ctx -> one page."""
    page = SimpleNamespace(
        evaluate=evaluate,
        goto=mock.Mock(),
        mouse=SimpleNamespace(click=mock.Mock()),
        screenshot=mock.Mock(),
    )
    ctx = SimpleNamespace(add_cookies=mock.Mock(), new_page=mock.Mock(return_value=page), close=mock.Mock())
    cloak = SimpleNamespace(launch_context=mock.Mock(return_value=ctx))
    return cloak, ctx, page


class VerifyPreviewTests(unittest.TestCase):
    def test_ephemeral_preview_closes_context_on_pass_or_image_failure(self):
        for sizes, expected, visible in [([[728, 440]], 0, True), ([[728, 1000]], 1, True), ([], 1, True), ([[728, 440]], 0, False)]:
            with self.subTest(sizes=sizes, visible=visible), tempfile.TemporaryDirectory() as temp:
                module = load_module()

                def evaluate(expression):
                    if 'document.body.innerText' in expression:
                        return 'article text ' * 40
                    if 'preview-iframe' in expression:
                        return {'ok': visible, 'sizes': sizes}
                    if 'getBoundingClientRect' in expression:
                        return {'x': 10, 'y': 20}
                    return True

                cloak, ctx, page = fake_browser(evaluate)
                with (
                    mock.patch.dict(sys.modules, {'cloakbrowser': cloak}),
                    mock.patch.dict(os.environ, {'SUBSTACK_SESSION_COOKIE': 'session=test; other=2'}, clear=True),
                    mock.patch.object(module, 'W', temp),
                    mock.patch.object(module.time, 'sleep'),
                ):
                    if not visible:
                        with self.assertRaisesRegex(RuntimeError, 'preview unavailable'):
                            module.verify_once('123', 950)
                    elif sizes:
                        self.assertEqual(module.verify_once('123', 950), expected)
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'images were not measured'):
                            module.verify_once('123', 950)
                kwargs = cloak.launch_context.call_args.kwargs
                self.assertIs(kwargs['headless'], True)
                self.assertEqual(kwargs['viewport'], {'width': 1000, 'height': 1500})
                self.assertNotIn('cdp_url', kwargs)
                cookies = ctx.add_cookies.call_args.args[0]
                self.assertEqual([(c['name'], c['value'], c['domain']) for c in cookies],
                                 [('session', 'test', '.substack.com'), ('other', '2', '.substack.com')])
                page.goto.assert_called_once()
                self.assertEqual(page.goto.call_args.args[0], 'https://writer-test.substack.com/publish/post/123')
                ctx.close.assert_called_once()

    def test_missing_cookie_never_launches_a_browser(self):
        module = load_module()
        cloak, _, _ = fake_browser(lambda expression: True)
        with mock.patch.dict(sys.modules, {'cloakbrowser': cloak}), mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'SUBSTACK_SESSION_COOKIE is required'):
                module.verify_once('123', 950)
        cloak.launch_context.assert_not_called()

    def test_free_audience_preview_does_not_require_paid_subscriber_view(self):
        module = load_module()
        expressions = []

        def evaluate(expression):
            expressions.append(expression)
            if 'document.body.innerText' in expression:
                return 'article text ' * 40
            if 'preview-iframe' in expression:
                return {'ok': True, 'sizes': [[728, 440]]}
            if 'getBoundingClientRect' in expression:
                return {'x': 10, 'y': 20}
            return True

        cloak, ctx, page = fake_browser(evaluate)
        with tempfile.TemporaryDirectory() as temp, (
            mock.patch.dict(sys.modules, {'cloakbrowser': cloak})
        ), mock.patch.dict(os.environ, {'SUBSTACK_SESSION_COOKIE': 'session=test'}), (
            mock.patch.object(module, 'W', temp)
        ), mock.patch.object(module.time, 'sleep'):
            self.assertEqual(module.verify_once('123', 950, 'everyone'), 0)
        self.assertFalse(any('preview-sub-paid' in item or 'paid subscriber' in item for item in expressions))
        page.mouse.click.assert_not_called()
        ctx.close.assert_called_once()

    def test_main_passes_audience_and_rejects_unknown_audience(self):
        module = load_module()
        with mock.patch.object(module, 'verify_once', return_value=0) as verify:
            self.assertEqual(module.main(['123', '950', 'everyone']), 0)
            verify.assert_called_once_with('123', 950, 'everyone')
            self.assertEqual(module.main(['123', '950', 'founding']), 2)

    def test_main_runs_in_process_without_a_shared_browser_lease(self):
        module = load_module()
        self.assertFalse(hasattr(module, 'subprocess'))
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(module, 'verify_once', return_value=0) as verify:
            self.assertEqual(module.main(['123', '950']), 0)
        verify.assert_called_once_with('123', 950, 'only_paid')

    def test_browser_failure_is_temporary_and_fail_closed(self):
        module = load_module()

        class PlaywrightError(Exception):
            pass

        with mock.patch.object(module, 'verify_once', side_effect=PlaywrightError('Target closed')):
            self.assertEqual(module.main(['123', '950']), 75)


if __name__ == '__main__':
    unittest.main()
