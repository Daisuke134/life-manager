import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from test_application_loop_hol import _load_deployed_loop
from test_lancers_status import _load_status


class HttpStatusDiagnosticsTests(unittest.TestCase):
    def test_http_exception_propagates_only_status_through_application(self):
        for code, classification in [(500, 'lancers_http_error'), (403, 'lancers_provider_blocked')]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                loop = _load_deployed_loop()
                private = 'PRIVATE_SENTINEL'
                error = urllib.error.HTTPError('https://example.invalid/?token=' + private,
                                               code, private, {'Set-Cookie': private}, io.BytesIO(private.encode()))
                planner, submitter = Mock(), Mock()
                output = io.StringIO()
                with patch.object(loop.status.urllib.request, 'urlopen', side_effect=error):
                    result = loop.run_loop(
                        state_path=Path(directory) / 'state.json', evidence_root=Path(directory) / 'evidence',
                        discoverer=loop.status.run_discovery, planner=planner, submitter=submitter,
                        output_stream=output,
                    )
                self.assertFalse(result['ok'])
                self.assertFalse(result['submitted'])
                self.assertEqual(result['error'], classification)
                self.assertEqual(result['http_status'], code)
                self.assertEqual(json.loads(output.getvalue()), result)
                self.assertNotIn(private, output.getvalue())
                self.assertNotIn('example.invalid', output.getvalue())
                planner.assert_not_called()
                submitter.assert_not_called()

    def test_non_exception_http_failure_preserves_numeric_status(self):
        status = _load_status()
        response = Mock(status=503)
        response.geturl.return_value = 'https://www.lancers.jp/work/search'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(status.urllib.request, 'urlopen', return_value=response):
            result = status.run_discovery(query='test', limit=1, timeout=1)
        self.assertEqual(result['error'], 'lancers_http_error')
        self.assertEqual(result['http_status'], 503)
        response.read.assert_not_called()

    def test_response_without_status_does_not_invent_200(self):
        status = _load_status()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return 'https://www.lancers.jp/user/login'
        with patch.object(status.urllib.request, 'urlopen', return_value=Response()):
            result = status.run_discovery(query='test', limit=1, timeout=1)
        self.assertEqual(result['error'], 'lancers_provider_blocked')
        self.assertNotIn('http_status', result)

    def test_missing_status_and_non_http_failure_keep_old_envelope(self):
        status = _load_status()
        for error, classification in [
            (status.LancersProviderError('lancers_http_error'), 'lancers_http_error'),
            (urllib.error.URLError('PRIVATE_SENTINEL'), 'lancers_network_error'),
        ]:
            with self.subTest(classification=classification):
                with patch.object(status.urllib.request, 'urlopen', side_effect=error):
                    result = status.run_discovery(query='test', limit=1, timeout=1)
                self.assertEqual(result, {'ok': False, 'platform': 'lancers', 'source': 'public_html', 'error': classification})

    def test_application_omits_invalid_status_and_non_http_diagnostics(self):
        for error, code in [('lancers_http_error', None), ('lancers_http_error', True),
                            ('lancers_http_error', '500'), ('lancers_http_error', 999),
                            ('lancers_network_error', 500)]:
            with self.subTest(error=error, code=code), tempfile.TemporaryDirectory() as directory:
                loop = _load_deployed_loop()
                result = loop.run_loop(state_path=Path(directory) / 'state.json',
                    evidence_root=Path(directory) / 'evidence',
                    discoverer=lambda **kw: {'ok': False, 'error': error, 'http_status': code})
                self.assertEqual(result['error'], error)
                self.assertNotIn('http_status', result)
