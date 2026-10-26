import importlib.util
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from urllib.error import URLError
from unittest.mock import patch


MODULE = Path(__file__).with_name('browser_session.py')
SPEC = importlib.util.spec_from_file_location('maritime_browser_session', MODULE)
browser_session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser_session)
TENANT = 'lm_11111111-1111-4111-8111-111111111111'


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return json.dumps(self.payload).encode()


class FakeProcess:
    def __init__(self, command, **kwargs):
        self.pid = 4242
        self.command = command
        self.kwargs = kwargs
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode


class BrowserSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / TENANT
        self.home.mkdir(mode=0o700)
        self.binary = self.root / 'chromium'
        self.binary.write_text('#!/bin/sh\nexit 0\n')
        self.binary.chmod(0o700)
        self.calls = []
        self.responses = []
        self.browser_uuid = '12345678-1234-1234-1234-123456789abc'
        self.owner_receipt_changes = {}

        def popen(command, **kwargs):
            process = FakeProcess(command, **kwargs)
            self.calls.append(process)
            state_dir = Path(command[command.index('--state-dir') + 1])
            receipt = {
                'owner': command[command.index('--owner') + 1],
                'pid': process.pid,
                'supervisor_pid': process.pid,
                'browser_root_pid': 4343,
                'listener_pid': 4343,
                'browser_uuid': self.browser_uuid,
                'port': 9229,
                'profile_name': 'profile',
            }
            receipt.update(self.owner_receipt_changes)
            path = state_dir / '9229.json'
            path.write_text(json.dumps(receipt))
            path.chmod(0o600)
            return process

        def urlopen(url, timeout=None):
            if not self.responses:
                raise URLError('not ready')
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return FakeResponse(response)

        self.popen = popen
        self.urlopen = urlopen

    def session(self, tenant_id=TENANT, **kwargs):
        options = dict(
            tenant_id=tenant_id,
            data_root=self.root,
            release_root=Path(__file__).parents[3],
            chromium_binary=self.binary,
            popen_impl=self.popen,
            urlopen_impl=self.urlopen,
            sleep_impl=lambda _seconds: None,
            startup_timeout_seconds=0.1,
        )
        options.update(kwargs)
        return browser_session.MaritimeBrowserSession(**options)

    def test_session_uses_private_tenant_profile_loopback_cdp_and_cleans_up(self):
        self.responses.append({'webSocketDebuggerUrl':
                               f'ws://127.0.0.1:9229/devtools/browser/{self.browser_uuid}'})
        session = self.session()
        with session as active:
            self.assertEqual(active.cdp_url, 'http://127.0.0.1:9229')
            self.assertEqual(active.profile_dir, self.home / 'browser' / 'profile')
            self.assertEqual(active.profile_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(active.profile_dir.stat().st_uid, os.geteuid())
        self.assertEqual(len(self.calls), 1)
        process = self.calls[0]
        self.assertIn('--remote-debugging-address=127.0.0.1', process.command)
        self.assertIn('--remote-debugging-port=9229', process.command)
        self.assertIn('--user-data-dir=' + str(self.home / 'browser' / 'profile'), process.command)
        self.assertEqual(process.kwargs['env'], {'PATH': '/usr/bin:/bin', 'HOME': str(self.home / 'home')})
        self.assertTrue(process.terminated)

    def test_foreign_port_owner_exit_fails_closed_without_attaching_to_it(self):
        def rejected_owner(command, **kwargs):
            process = FakeProcess(command, **kwargs)
            process.returncode = 75
            self.calls.append(process)
            return process

        with self.assertRaisesRegex(browser_session.BrowserSessionError, 'browser_session_startup_failed'):
            self.session(popen_impl=rejected_owner).__enter__()
        self.assertEqual(len(self.calls), 1)
        self.assertIn('browser_port_owner.py', self.calls[0].command[2])

    def test_browser_owner_forwards_session_stop_to_an_exact_adopted_profile(self):
        from runtime.host import browser_port_owner as owner

        with tempfile.TemporaryDirectory() as raw:
            args = type('Args', (), {
                'state_dir': Path(raw) / 'state', 'profile': '/profiles/owned',
                'port': 9224, 'owner': 'maritime-owned', 'terminate_adopted_on_exit': True,
                'command': ['--', '/usr/bin/true'],
            })()
            handlers = {}

            def fake_signal(signum, handler):
                previous = handlers.get(signum, lambda *_args: None)
                handlers[signum] = handler
                return previous

            def fake_wait(pid, port, poll_interval=10):
                self.assertEqual((pid, port, poll_interval), (4242, 9224, 0.1))
                handlers[owner.signal.SIGTERM](owner.signal.SIGTERM, None)
                return 75

            with (
                patch.object(owner, '_port_answers', return_value=True),
                patch.object(owner, '_live_profile_owner', return_value=4242),
                patch.object(owner, '_browser_uuid', return_value='browser-generation'),
                patch.object(owner, '_wait_for_adopted_browser', side_effect=fake_wait),
                patch.object(owner, '_forward_process_group_signal') as forward,
                patch.object(owner.signal, 'signal', side_effect=fake_signal),
                patch.object(owner.subprocess, 'Popen') as popen,
            ):
                self.assertEqual(owner.run(args), 75)
            forward.assert_called_once_with(4242, owner.signal.SIGTERM)
            popen.assert_not_called()

    def test_two_tenants_receive_distinct_cookie_profiles_and_owner_state(self):
        other = 'lm_22222222-2222-4222-8222-222222222222'
        (self.root / other).mkdir(mode=0o700)
        first, second = self.session(), self.session(other)
        first._prepare_paths()
        second._prepare_paths()
        self.assertNotEqual(first.profile_dir, second.profile_dir)
        self.assertNotEqual(first.profile_dir / 'Default' / 'Cookies', second.profile_dir / 'Default' / 'Cookies')
        self.assertNotEqual(first.state_dir, second.state_dir)
        self.assertNotEqual(first.owner_id, second.owner_id)
        self.assertEqual(first.profile_dir, self.home / 'browser' / 'profile')
        self.assertEqual(second.profile_dir, self.root / other / 'browser' / 'profile')

    def test_tenant_session_rejects_a_foreign_tenants_cdp_owner_receipt(self):
        other = 'lm_22222222-2222-4222-8222-222222222222'
        (self.root / other).mkdir(mode=0o700)
        first, second = self.session(), self.session(other)
        first._prepare_paths()
        second._prepare_paths()
        receipt = {
            'owner': first.owner_id,
            'pid': 4242,
            'supervisor_pid': 4242,
            'browser_root_pid': 4343,
            'listener_pid': 4343,
            'browser_uuid': self.browser_uuid,
            'port': 9229,
            'profile_name': 'profile',
        }
        foreign_receipt = second.state_dir / '9229.json'
        foreign_receipt.write_text(json.dumps(receipt))
        foreign_receipt.chmod(0o600)
        self.assertIsNone(second._read_owner_receipt())

    def test_session_rejects_invalid_tenant_and_symlinked_profile(self):
        with self.assertRaisesRegex(browser_session.BrowserSessionError, 'tenant'):
            self.session('../other').__enter__()
        foreign = self.root / 'foreign'
        foreign.mkdir(mode=0o700)
        browser_dir = self.home / 'browser'
        browser_dir.mkdir(mode=0o700)
        (browser_dir / 'profile').symlink_to(foreign, target_is_directory=True)
        with self.assertRaisesRegex(browser_session.BrowserSessionError, 'profile'):
            self.session().__enter__()
        self.assertEqual(list(foreign.iterdir()), [])
        self.assertEqual(self.calls, [])

    def test_session_allows_only_packaged_chromium_symlink(self):
        cloak_root = self.root / 'cloakbrowser'
        cloak_root.mkdir(mode=0o700)
        target = cloak_root / 'chrome'
        target.write_text('#!/bin/sh\nexit 0\n')
        target.chmod(0o700)
        link = self.root / 'lm-cloud-chromium'
        link.symlink_to(target)
        with patch.object(browser_session, 'CHROMIUM_PATH', link):
            session = self.session(chromium_binary=link, cloakbrowser_root=cloak_root)
            session._prepare_paths()
        self.assertEqual(session.chromium_binary, link)

    def test_session_rejects_chromium_symlink_outside_packaged_directory(self):
        foreign = self.root / 'foreign-chromium'
        foreign.write_text('#!/bin/sh\nexit 0\n')
        foreign.chmod(0o700)
        link = self.root / 'lm-cloud-chromium'
        link.symlink_to(foreign)
        with patch.object(browser_session, 'CHROMIUM_PATH', link):
            session = self.session(chromium_binary=link, cloakbrowser_root=self.root / 'cloakbrowser')
            with self.assertRaisesRegex(browser_session.BrowserSessionError, 'browser_binary_unavailable'):
                session._prepare_paths()

    def test_session_fails_closed_when_cdp_is_not_ready(self):
        session = self.session()
        with self.assertRaisesRegex(browser_session.BrowserSessionError, 'browser_session_startup_failed'):
            session.__enter__()
        self.assertTrue(self.calls[0].terminated)

    def test_shutdown_timeout_keeps_supervisor_handle_for_cleanup_retry(self):
        session = self.session()

        class StuckProcess:
            pid = 43210

            def __init__(self):
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired('browser owner', timeout)

        process = StuckProcess()
        session.process = process
        with self.assertRaisesRegex(browser_session.BrowserSessionError, 'shutdown_failed'):
            session._stop()
        self.assertTrue(process.terminated)
        self.assertIs(session.process, process)

    def test_shutdown_nonzero_owner_exit_is_not_reported_as_clean(self):
        session = self.session()
        process = FakeProcess([])
        process.returncode = 1
        session.process = process
        with self.assertRaisesRegex(browser_session.BrowserSessionError, 'shutdown_failed'):
            session._stop()
        self.assertIs(session.process, process)

    def test_cdp_must_report_the_exact_loopback_endpoint(self):
        self.responses.append({'webSocketDebuggerUrl':
                               'ws://192.0.2.99:9229/devtools/browser/12345678-1234-1234-1234-123456789abc'})
        with self.assertRaisesRegex(browser_session.BrowserSessionError, 'browser_session_startup_failed'):
            self.session().__enter__()
        self.assertTrue(self.calls[0].terminated)

    def test_cdp_rejects_listener_not_owned_by_this_supervisor(self):
        self.owner_receipt_changes = {'supervisor_pid': 9999}
        self.responses.append({'webSocketDebuggerUrl':
                               f'ws://127.0.0.1:9229/devtools/browser/{self.browser_uuid}'})
        with self.assertRaisesRegex(browser_session.BrowserSessionError, 'browser_session_startup_failed'):
            self.session().__enter__()
        self.assertTrue(self.calls[0].terminated)

    def test_cdp_rejects_browser_uuid_different_from_private_owner_receipt(self):
        self.owner_receipt_changes = {'browser_uuid': '87654321-4321-4321-4321-cba987654321'}
        self.responses.append({'webSocketDebuggerUrl':
                               f'ws://127.0.0.1:9229/devtools/browser/{self.browser_uuid}'})
        with self.assertRaisesRegex(browser_session.BrowserSessionError, 'browser_session_startup_failed'):
            self.session().__enter__()
        self.assertTrue(self.calls[0].terminated)

    def test_cdp_healthcheck_bypasses_the_managed_egress_proxy(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                payload = json.dumps({'webSocketDebuggerUrl':
                                      'ws://127.0.0.1:9229/devtools/browser/12345678-1234-1234-1234-123456789abc'})
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(payload.encode())

            def log_message(self, *_args):
                return

        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(thread.join, 2)
        url = f'http://127.0.0.1:{server.server_port}'
        proxy_env = {
            'HTTP_PROXY': 'http://127.0.0.1:1', 'http_proxy': 'http://127.0.0.1:1',
            'ALL_PROXY': 'http://127.0.0.1:1', 'all_proxy': 'http://127.0.0.1:1',
            'NO_PROXY': '', 'no_proxy': '',
        }
        session = browser_session.MaritimeBrowserSession(
            tenant_id=TENANT, data_root=self.root, release_root=Path(__file__).parents[3],
            chromium_binary=self.binary,
        )
        session._prepare_paths()
        session.process = FakeProcess([])
        receipt = {
            'owner': 'maritime-' + TENANT[3:], 'pid': 4242, 'supervisor_pid': 4242,
            'browser_root_pid': 4343, 'listener_pid': 4343,
            'browser_uuid': '12345678-1234-1234-1234-123456789abc',
            'port': 9229, 'profile_name': 'profile',
        }
        owner_path = session.state_dir / '9229.json'
        owner_path.write_text(json.dumps(receipt))
        owner_path.chmod(0o600)
        import urllib.request
        with patch.dict(os.environ, proxy_env), patch.object(browser_session, 'CDP_URL', url), \
                patch.object(urllib.request, '_opener', None):
            self.assertTrue(session._cdp_ready())


if __name__ == '__main__':
    unittest.main()
