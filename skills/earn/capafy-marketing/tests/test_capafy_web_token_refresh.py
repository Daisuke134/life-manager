import base64
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('refresh', Path(__file__).resolve().parents[1] / 'scripts' / 'capafy_web_token_refresh.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def jwt(lifetime, remaining=None):
    now = int(time.time())
    exp = now + (lifetime if remaining is None else remaining)
    claims = {'iat': exp - lifetime, 'exp': exp}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    return 'header.' + payload + '.signature'


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'credentials.json'
        self.saved_path = m.CREDENTIALS
        m.CREDENTIALS = self.path
        self.addCleanup(setattr, m, 'CREDENTIALS', self.saved_path)
        self.save(jwt(86400))

    def save(self, token):
        self.path.write_text(json.dumps({'credentials': [
            {'service': 'capafy-publisher', 'email': 'owner@example.test', 'web_token': token},
            {'service': 'other', 'marker': 'preserve'}]}))

    def test_short_lifetimes_never_request_otp(self):
        for lifetime in [86400, 7 * 86400]:
            self.save(jwt(lifetime))
            with patch.object(m, '_probe', return_value='valid'), patch.object(m, '_post') as login:
                self.assertEqual(m.main(), 0)
                login.assert_not_called()

    def test_unknown_expiry_valid_token_reused(self):
        for token in ['opaque', 'bad.%%%.jwt', 'header.e30.signature']:
            self.save(token)
            with patch.object(m, '_probe', return_value='valid'), patch.object(m, '_post') as login:
                self.assertEqual(m.main(), 0)
                login.assert_not_called()

    def test_unknown_validation_never_logs_in(self):
        self.save(jwt(86400, -1))
        with patch.object(m, '_probe', return_value='unknown'), patch.object(m, '_post') as login:
            self.assertEqual(m.main(), 1)
            login.assert_not_called()

    def test_confirmed_auth_failure_one_attempt_then_cooldown(self):
        with patch.object(m, '_probe', return_value='auth_failed'), patch.object(m, '_post', side_effect=RuntimeError) as login:
            with self.assertRaises(RuntimeError):
                m.main()
            self.assertEqual(m.main(), 1)
            self.assertEqual(login.call_count, 1)

    def test_near_expiry_refresh_and_merge(self):
        old = jwt(86400, 20)
        new = jwt(86400)
        self.save(old)
        def post(path, body):
            if path == '/auth/login':
                doc = json.loads(self.path.read_text())
                doc['credentials'][1]['marker'] = 'edited-during-otp'
                self.path.write_text(json.dumps(doc))
                return {'challengeId': 'dummy'}
            return {'token': new}
        with patch.object(m, '_probe', return_value='valid'), patch.object(m, '_latest_otp', return_value='000000'), patch.object(m, '_post', side_effect=post):
            self.assertEqual(m.main(), 0)
            self.assertEqual(m.main(), 0)
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['credentials'][0]['web_token'], new)
        self.assertEqual(saved['credentials'][1]['marker'], 'edited-during-otp')
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertEqual(list(self.path.parent.glob('credentials.json.*')), [])

    def test_parallel_caller_no_challenge(self):
        with m._lock(self.path.with_name('capafy-web-refresh.lock')):
            with patch.object(m, '_post') as login:
                self.assertEqual(m.main(), 0)
                login.assert_not_called()

    def test_failed_save_cools_down(self):
        self.save(jwt(86400, -1))
        with patch.object(m, '_probe', return_value='valid'), patch.object(m, '_latest_otp', return_value='000000'), patch.object(m, '_post', side_effect=[{'challengeId': 'dummy'}, {'token': jwt(86400)}]):
            real_save = m._atomic_json
            def save(path, doc):
                if path == self.path:
                    raise OSError('simulated')
                real_save(path, doc)
            with patch.object(m, '_atomic_json', side_effect=save):
                with self.assertRaises(OSError):
                    m.main()
            self.assertEqual(m.main(), 1)

    def test_probe_only_401_is_auth_failure(self):
        import urllib.error
        for status, expected in [(401, 'auth_failed'), (403, 'unknown'), (500, 'unknown')]:
            with patch.object(m.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('test', status, 'test', {}, None)):
                self.assertEqual(m._probe('secret'), expected)

    def test_probe_network_error_unknown(self):
        with patch.object(m.urllib.request, 'urlopen', side_effect=OSError):
            self.assertEqual(m._probe('secret'), 'unknown')

    def test_secret_not_in_receipt(self):
        from io import StringIO
        output = StringIO()
        secret = jwt(86400)
        self.save(secret)
        with patch.object(m, '_probe', return_value='valid'), patch('sys.stdout', output):
            self.assertEqual(m.main(), 0)
        self.assertNotIn(secret, output.getvalue())
        self.assertNotIn('owner@example', output.getvalue())

    def test_atomic_failure_keeps_original(self):
        before = self.path.read_bytes()
        with patch.object(m.os, 'replace', side_effect=OSError):
            with self.assertRaises(OSError):
                m._atomic_json(self.path, {'changed': True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('credentials.json.*')), [])

    def test_window_bounded_by_lifetime(self):
        self.assertEqual(m._refresh_window(jwt(100)), 10)
        self.assertEqual(m._refresh_window(jwt(86400)), 300)


if __name__ == '__main__':
    unittest.main()
