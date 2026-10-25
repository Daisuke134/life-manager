import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).with_name('browser_mcp.py')
SPEC = importlib.util.spec_from_file_location('maritime_browser_mcp', MODULE)
browser_mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser_mcp)
TENANT = 'lm_11111111-1111-4111-8111-111111111111'


class Locator:
    def __init__(self, *, value=None, count=1, attributes=None, form=None, press_error=None):
        self.value = value
        self.count_value = count
        self.attributes = attributes or {}
        self.form = form or {
            'method': 'GET', 'action': 'https://capafy.ai/search', 'target': '_self',
            'inputName': 'q', 'fieldNames': ['q'],
        }
        self.press_error = press_error
        self.filled = None
        self.pressed = None

    def count(self):
        return self.count_value

    @property
    def first(self):
        return self

    def get_attribute(self, name):
        return self.attributes.get(name)

    def evaluate(self, _expression):
        return self.form

    def fill(self, value, timeout=None):
        self.filled = value

    def press(self, key, timeout=None):
        if self.press_error:
            raise self.press_error
        self.pressed = key


class FakePage:
    def __init__(self):
        self.url = 'https://capafy.ai/market'
        self.goto_calls = []
        self.locators = {}
        self.screenshot_calls = 0
        self.title_calls = 0
        self.body_reads = 0
        self.body_url_after_read = None
        self.closed = False
        self.context = FakeContext([self])
        self.body_text = (
            'Top seller hello@example.com, code 123456; verification code 1234; '
            'one-time passcode 87654321; code is 4321; 4321 is your code; '
            'Bearer secret-token-abcdefghijkl; api_key=demo; '
            'token=opaque-secret; session_id=session-secret; csrf=csrf-secret; '
            'authToken=auth-secret; Authorization: Basic dXNlcjpwYXNzd29yZA==; '
            '"Authorization": "Basic cHJveHk6c2VjcmV0=="; '
            'Proxy-Authorization: Digest digest-secret-value; sk-live-abcdefghijklmnop; '
            'eyJabcdefghijk.abcdefghijklmnop.abcdefghijklmnop'
        )

    def title(self):
        self.title_calls += 1
        return 'Capafy market'

    def locator(self, selector):
        return type('Body', (), {'inner_text': lambda _self, **_kwargs: self._read_body()})()

    def _read_body(self):
        self.body_reads += 1
        body = self.body_text
        if self.body_url_after_read is not None:
            self.url = self.body_url_after_read
        return body

    def screenshot(self, **kwargs):
        self.screenshot_calls += 1
        return b'png-fixture'

    def get_by_role(self, role, name=None, exact=None):
        return self.locators.setdefault((role, name), Locator())

    def goto(self, url, **kwargs):
        self.goto_calls.append(url)
        self.url = url

    def close(self):
        self.closed = True


class FakeCDP:
    def __init__(self):
        self.calls = []

    def send(self, name, params=None):
        self.calls.append((name, params))


class FakeContext:
    def __init__(self, pages):
        self.pages = pages
        self.routes = []
        self.handlers = {}
        self.init_scripts = []
        self.cdp_sessions = []
        for page in pages:
            page.context = self

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def on(self, event, handler):
        self.handlers[event] = handler

    def new_cdp_session(self, _page):
        session = FakeCDP()
        self.cdp_sessions.append(session)
        return session


class BrowserMcpTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.tenant_root = self.root / TENANT
        self.receipt_parent = self.tenant_root / 'receipts' / 'cycle-1'
        self.receipt_parent.mkdir(parents=True, mode=0o700)
        self.tenant_root.chmod(0o700)
        (self.tenant_root / 'receipts').chmod(0o700)
        self.receipt_parent.chmod(0o700)
        self.receipt = self.receipt_parent / 'browser-actions.jsonl'
        self.page = FakePage()
        self.session = browser_mcp.BrowserMcpSession(
            page=self.page, tenant_id=TENANT,
            tenant_root=self.tenant_root, receipt_path=self.receipt,
        )

    def test_lists_only_observe_navigate_click_and_search_tools(self):
        tools = self.session.list_tools()['tools']
        self.assertEqual([tool['name'] for tool in tools], [
            'browser_observe', 'browser_navigate', 'browser_search',
        ])
        self.assertTrue(all('inputSchema' in tool for tool in tools))

    def test_observe_returns_redacted_text_without_forwarding_unredacted_screenshots(self):
        result = self.session.call('browser_observe', {})
        self.assertEqual(result['content'][0]['type'], 'text')
        self.assertIn('https://capafy.ai', result['content'][0]['text'])
        self.assertIn('[email redacted]', result['content'][0]['text'])
        self.assertIn('[code redacted]', result['content'][0]['text'])
        for secret in ('123456', '1234', '87654321', '4321', 'secret-token-abcdefghijkl',
                       'demo', 'opaque-secret', 'session-secret',
                       'csrf-secret', 'auth-secret', 'dXNlcjpwYXNzd29yZA==',
                       'cHJveHk6c2VjcmV0==',
                       'digest-secret-value', 'sk-live-abcdefghijklmnop',
                       'eyJabcdefghijk.abcdefghijklmnop.abcdefghijklmnop'):
            self.assertNotIn(secret, result['content'][0]['text'])
        self.assertEqual(len(result['content']), 1)
        self.assertEqual(self.page.screenshot_calls, 0)

    def test_observe_rejects_private_capafy_page_before_reading_page_data(self):
        self.page.url = 'https://capafy.ai/account'
        with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'navigation_blocked'):
            self.session.call('browser_observe', {})
        self.assertEqual(self.page.title_calls, 0)
        self.assertEqual(self.page.body_reads, 0)

    def test_observe_allows_only_public_capafy_routes_before_reading_page_data(self):
        for path in ('/earnings', '/dashboard', '/account/settings', '/marketplace/sales'):
            with self.subTest(path=path):
                self.page.url = 'https://capafy.ai' + path
                self.page.title_calls = 0
                self.page.body_reads = 0
                with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'navigation_blocked'):
                    self.session.call('browser_observe', {})
                self.assertEqual(self.page.title_calls, 0)
                self.assertEqual(self.page.body_reads, 0)

    def test_observe_discards_body_if_page_changes_to_private_route_during_read(self):
        self.page.body_url_after_read = 'https://capafy.ai/account'
        with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'navigation_blocked'):
            self.session.call('browser_observe', {})
        self.assertEqual(self.page.body_reads, 1)
        self.assertNotIn('Top seller', self.receipt.read_text())

    def test_navigation_is_https_and_allowlisted_and_routes_block_foreign_hosts(self):
        for url in ['http://capafy.ai', 'https://example.com',
                    'https://user:secret@capafy.ai', 'https://capafy.ai:444',
                    'https://capafy.ai/publish', 'https://capafy.ai/%70ublish',
                    'https://capafy.ai/%2570ublish',
                    'https://capafy.ai/search?action=publish',
                    'https://capafy.ai/search?%61ction=%2570ublish',
                    'https://capafy.ai/logout', 'https://capafy.ai/account/settings',
                    'https://api.capafy.ai/agent/agents', 'https://capafy.ai/unreviewed-route',
                    'https://capafy.ai/search?email=hello%40example.com',
                    'https://capafy.ai/search?token=secret-token-value',
                    'https://capafy.ai/search?session_id=session-secret',
                    'https://capafy.ai/search?csrf=csrf-secret',
                    'https://capafy.ai/search?authToken=auth-secret',
                    'https://capafy.ai/search?code=1234']:
            with self.subTest(url=url), self.assertRaisesRegex(browser_mcp.BrowserToolError, 'navigation_blocked'):
                self.session.call('browser_navigate', {'url': url})
        self.assertEqual(self.page.goto_calls, [])
        self.session.call('browser_navigate', {'url': 'https://capafy.ai/developer/doc/4.2'})
        self.assertEqual(self.page.goto_calls, ['https://capafy.ai/developer/doc/4.2'])
        route_handler = self.page.context.routes[0][1]
        route = type('Route', (), {'request': type('Request', (), {
                                       'url': 'https://attacker.invalid/', 'method': 'GET'})(),
                                   'abort': lambda self: setattr(self, 'aborted', True),
                                   'continue_': lambda self: setattr(self, 'continued', True)})()
        route_handler(route)
        self.assertTrue(route.aborted)

    def test_route_aborts_provider_write_methods_even_on_allowlisted_hosts(self):
        route_handler = self.page.context.routes[0][1]
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            route = type('Route', (), {
                'request': type('Request', (), {'url': 'https://publisher.capafy.ai/api/search', 'method': method})(),
                'abort': lambda self: setattr(self, 'aborted', True),
                'continue_': lambda self: setattr(self, 'continued', True),
            })()
            route_handler(route)
            self.assertTrue(route.aborted, method)
            self.assertFalse(getattr(route, 'continued', False), method)

        route = type('Route', (), {
            'request': type('Request', (), {'url': 'https://publisher.capafy.ai/publish', 'method': 'GET'})(),
            'abort': lambda self: setattr(self, 'aborted', True),
            'continue_': lambda self: setattr(self, 'continued', True),
        })()
        route_handler(route)
        self.assertTrue(route.aborted)

    def test_generic_executable_click_tool_is_not_exposed(self):
        with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'tool_not_allowed'):
            self.session.call('browser_click', {'role': 'button', 'name': 'Search'})

    def test_context_route_and_service_worker_bypass_cover_all_pages(self):
        self.assertEqual(self.page.context.routes[0][0], '**/*')
        self.assertIn('serviceWorker', self.page.context.init_scripts[0])
        self.assertEqual(self.page.context.cdp_sessions[0].calls, [
            ('Network.enable', None),
            ('Network.setBypassServiceWorker', {'bypass': True}),
        ])

    def test_popup_page_is_guarded_closed_and_fences_the_session(self):
        popup = FakePage()
        self.page.context.handlers['page'](popup)
        self.assertTrue(popup.closed)
        self.assertEqual(len(self.page.context.cdp_sessions), 2)
        with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'context_unavailable'):
            self.session.call('browser_observe', {})

    def test_search_uses_only_searchbox_and_does_not_persist_query(self):
        search = Locator()
        self.page.locators[('searchbox', None)] = search
        result = self.session.call('browser_search', {'query': 'popular writing workflow'})
        self.assertEqual(search.filled, 'popular writing workflow')
        self.assertEqual(search.pressed, 'Enter')
        self.assertEqual(result['content'][0]['type'], 'text')
        line = json.loads(self.receipt.read_text().splitlines()[0])
        self.assertEqual(line['tool'], 'browser_search')
        rows = [json.loads(row) for row in self.receipt.read_text().splitlines()]
        self.assertEqual([row['outcome'] for row in rows], ['started', 'searched'])
        self.assertEqual(rows[0]['actionId'], rows[1]['actionId'])
        self.assertNotIn('query', line)
        self.assertNotIn('popular writing workflow', self.receipt.read_text())

    def test_search_refuses_post_or_cross_origin_forms_before_filling(self):
        for form in [
            {'method': 'POST', 'action': 'https://capafy.ai/publish'},
            {'method': 'GET', 'action': 'https://attacker.invalid/search'},
            {'method': 'GET', 'action': 'https://capafy.ai/market?mode=redeem',
             'target': '_self', 'inputName': 'q', 'fieldNames': ['q', 'mode']},
            {'method': 'GET', 'action': 'https://capafy.ai/search',
             'target': '_blank', 'inputName': 'q', 'fieldNames': ['q']},
        ]:
            search = Locator(form=form)
            self.page.locators[('searchbox', None)] = search
            with self.subTest(form=form), self.assertRaisesRegex(browser_mcp.BrowserToolError, 'search_blocked'):
                self.session.call('browser_search', {'query': 'public results'})
            self.assertIsNone(search.filled)

    def test_search_refuses_credential_like_queries_before_filling(self):
        for query in ('token=opaque-secret', 'session_id=session-secret',
                      'csrf=csrf-secret', 'authToken=auth-secret'):
            search = Locator()
            self.page.locators[('searchbox', None)] = search
            with self.subTest(query=query), self.assertRaisesRegex(
                    browser_mcp.BrowserToolError, 'search_query_invalid'):
                self.session.call('browser_search', {'query': query})
            self.assertIsNone(search.filled)
            self.assertIsNone(search.pressed)

    def test_search_failure_after_dispatch_is_recorded_as_effect_unknown(self):
        search = Locator(press_error=TimeoutError('simulated timeout'))
        self.page.locators[('searchbox', None)] = search
        with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'search_effect_unknown'):
            self.session.call('browser_search', {'query': 'public results'})
        row = json.loads(self.receipt.read_text().strip().splitlines()[-1])
        self.assertEqual(row['outcome'], 'effect_unknown')
        before = self.receipt.read_text()
        with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'effect_unknown_fence'):
            self.session.call('browser_observe', {})
        self.assertEqual(self.receipt.read_text(), before)

    def test_receipt_start_failure_prevents_search_dispatch(self):
        search = Locator()
        self.page.locators[('searchbox', None)] = search
        with patch.object(self.session, '_record', side_effect=browser_mcp.BrowserToolError(
                'browser_receipt_write_failed', record=False)):
            with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'receipt_write_failed'):
                self.session.call('browser_search', {'query': 'public results'})
        self.assertIsNone(search.filled)
        self.assertIsNone(search.pressed)

    def test_started_receipt_fsync_failure_prevents_browser_dispatch(self):
        search = Locator()
        self.page.locators[('searchbox', None)] = search
        with patch.object(browser_mcp.os, 'fsync', side_effect=OSError('simulated fsync failure')):
            with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'receipt_write_failed'):
                self.session.call('browser_search', {'query': 'public results'})
        self.assertIsNone(search.filled)
        self.assertIsNone(search.pressed)

    def test_terminal_receipt_fsync_failure_is_persisted_as_unknown(self):
        search = Locator()
        self.page.locators[('searchbox', None)] = search
        fsync_calls = 0

        def fsync(fd):
            nonlocal fsync_calls
            fsync_calls += 1
            if fsync_calls == 3:
                raise OSError('simulated terminal fsync failure')
            return None

        with patch.object(browser_mcp.os, 'fsync', side_effect=fsync):
            with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'effect_unknown_receipt_unavailable'):
                self.session.call('browser_search', {'query': 'public results'})
        rows = [json.loads(line) for line in self.receipt.read_text().splitlines()]
        self.assertEqual([row['outcome'] for row in rows], ['started', 'searched', 'effect_unknown'])
        self.assertEqual(len({row['actionId'] for row in rows}), 1)
        self.assertEqual(search.pressed, 'Enter')

    def test_post_dispatch_receipt_failure_is_unknown_without_contradictory_block_row(self):
        search = Locator()
        self.page.locators[('searchbox', None)] = search
        original_record = self.session._record

        def fail_success_receipt(tool, outcome, action_id):
            if outcome == 'searched':
                raise browser_mcp.BrowserToolError('browser_receipt_write_failed', record=False)
            original_record(tool, outcome, action_id)

        with patch.object(self.session, '_record', side_effect=fail_success_receipt):
            with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'effect_unknown_receipt_unavailable'):
                self.session.call('browser_search', {'query': 'public results'})
        self.assertEqual(search.pressed, 'Enter')
        rows = [json.loads(line) for line in self.receipt.read_text().splitlines()]
        self.assertEqual([row['outcome'] for row in rows], ['started', 'effect_unknown'])
        self.assertEqual(len({row['actionId'] for row in rows}), 1)
        self.assertEqual(rows[0]['actionId'], browser_mcp.uuid.UUID(rows[0]['actionId']).hex)
        self.assertEqual(self.receipt.stat().st_mode & 0o777, 0o600)

    def test_receipt_path_cannot_escape_or_follow_a_symlink(self):
        outside = self.root / 'outside'
        outside.mkdir(mode=0o700)
        with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'receipt_path_invalid'):
            browser_mcp.BrowserMcpSession(
                page=self.page, tenant_id=TENANT, tenant_root=self.tenant_root,
                receipt_path=outside / 'actions.jsonl',
            )
        link = self.tenant_root / 'receipts' / 'link'
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'receipt_path_invalid'):
            browser_mcp.BrowserMcpSession(
                page=self.page, tenant_id=TENANT, tenant_root=self.tenant_root,
                receipt_path=link / 'actions.jsonl',
            )

    def test_browser_tool_budget_stops_further_observation(self):
        self.session.calls = browser_mcp.MAX_TOOL_CALLS
        with self.assertRaisesRegex(browser_mcp.BrowserToolError, 'browser_action_budget_exhausted'):
            self.session.call('browser_observe', {})

    def test_stdio_handshake_and_tool_call_follow_mcp_json_rpc(self):
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'browser_observe', 'arguments': {}}},
        ]
        stdin = '\n'.join(json.dumps(row) for row in requests) + '\n'
        with patch('sys.stdin') as input_stream, patch('sys.stdout') as output_stream:
            input_stream.__iter__.return_value = iter(stdin.splitlines())
            browser_mcp.run_stdio(self.session)
            output = ''.join(call.args[0] for call in output_stream.write.call_args_list)
        messages = [json.loads(line) for line in output.splitlines() if line.strip()]
        self.assertEqual(messages[0]['result']['serverInfo']['name'], 'life-manager-maritime-browser')
        self.assertEqual(messages[1]['result']['tools'][0]['name'], 'browser_observe')
        self.assertEqual(messages[2]['result']['content'][0]['type'], 'text')
        self.assertEqual(len(messages[2]['result']['content']), 1)


if __name__ == '__main__':
    unittest.main()
