import base64
import importlib.util
import io
from contextlib import redirect_stdout
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / 'scripts/capafy_hourly_reconcile.py'
BINDING = {'tenantId': 'lm_11111111-1111-4111-8111-111111111111', 'provider': 'capafy', 'subjectId': 'seller-a'}


def token(subject='seller-a'):
    payload = base64.urlsafe_b64encode(json.dumps({'sub': subject, 'exp': 4102444800}).encode()).decode().rstrip('=')
    return 'fixture.' + payload + '.signature'


class OwnedSnapshotTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('reconcile', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.sales = {'code': 0, 'data': {'startDate': '2026-10-20', 'endDate': '2026-10-20',
            'granularity': 'daily', 'totalRevenue': 3.98,
            'data': [{'date': '2026-10-20', 'revenue': 3.98, 'refundAmount': 0}]}}
        self.get = patch.object(self.module, '_get', return_value={'code': 0, 'data': {'userId': 'seller-a'}})
        self.post = patch.object(self.module, '_post', side_effect=lambda *args: self.sales)
        self.get.start()
        self.post.start()
        self.addCleanup(self.get.stop)
        self.addCleanup(self.post.stop)

    def read(self, **kwargs):
        return self.module.read_owned_sales_snapshot(BINDING, '2026-10-20', '2026-10-20',
            access_token='fixture-publisher-token', web_token=kwargs.get('web_token', token()),
            observed_at='2026-10-20T12:00:00Z')

    def test_cli_reads_credentials_from_stdin_and_prints_only_snapshot(self):
        incoming = {'binding': BINDING, 'periodStart': '2026-10-20', 'periodEnd': '2026-10-20',
                    'accessToken': 'fixture-publisher-token', 'webToken': token()}
        output = io.StringIO()
        with patch.object(self.module.sys, 'stdin', io.StringIO(json.dumps(incoming))), redirect_stdout(output):
            code = self.module.main(['--tenant-snapshot', '--observed-at', '2026-10-20T12:00:00Z'])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())['complete'])
        self.assertNotIn('fixture-publisher-token', output.getvalue())
        self.assertNotIn('signature', output.getvalue())

    def test_owner_bound_official_daily_rows_have_sanitized_evidence(self):
        snapshot = self.read()
        self.assertTrue(snapshot['complete'])
        self.assertEqual(snapshot['tenantId'], BINDING['tenantId'])
        self.assertEqual(snapshot['rows'], [{'date': '2026-10-20', 'revenue': '3.98', 'refundAmount': '0.00'}])
        self.assertRegex(snapshot['evidenceRefs'][0], r'^capafy://readback/[0-9a-f]{64}$')
        self.assertNotIn('fixture-publisher-token', json.dumps(snapshot))
        self.assertNotIn('signature', json.dumps(snapshot))

    def test_cli_failure_does_not_print_credentials_or_fabricate_zero(self):
        incoming = {'binding': BINDING, 'periodStart': '2026-10-20', 'periodEnd': '2026-10-20',
                    'accessToken': 'fixture-publisher-token', 'webToken': token('seller-b')}
        output = io.StringIO()
        with patch.object(self.module.sys, 'stdin', io.StringIO(json.dumps(incoming))), redirect_stdout(output):
            code = self.module.main(['--tenant-snapshot', '--observed-at', '2026-10-20T12:00:00Z'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue()), {'complete': False, 'errorClass': 'capafy_snapshot_unconfirmed'})

    def test_foreign_web_token_cannot_be_combined_with_publisher_account(self):
        with self.assertRaisesRegex(ValueError, 'owner_mismatch'):
            self.read(web_token=token('seller-b'))

    def test_failed_or_incomplete_sales_never_produces_verified_zero(self):
        for change in [{'_error': 'fixture-secret'}, {'code': 401}, {'code': 0, 'data': {'data': []}}]:
            with self.subTest(change=change):
                self.sales = change
                with self.assertRaisesRegex(ValueError, 'snapshot'):
                    self.read()

    def test_profile_and_sales_require_explicit_integer_success_code(self):
        for code in [None, False, True, '0', 0.0]:
            with self.subTest(code=code, endpoint='profile'):
                payload = {'data': {'userId': 'seller-a'}}
                if code is not None:
                    payload['code'] = code
                with patch.object(self.module, '_get', return_value=payload):
                    with self.assertRaisesRegex(ValueError, 'snapshot'):
                        self.read()
            with self.subTest(code=code, endpoint='sales'):
                original = self.sales.copy()
                self.sales.pop('code', None)
                if code is not None:
                    self.sales['code'] = code
                try:
                    with self.assertRaisesRegex(ValueError, 'snapshot'):
                        self.read()
                finally:
                    self.sales = original

    def test_daily_coverage_total_and_amounts_are_verified(self):
        for change in [{'totalRevenue': 5}, {'startDate': '2026-10-19'}, {'data': []},
                       {'data': [{'date': '2026-10-20', 'revenue': None, 'refundAmount': 0}]},
                       {'data': [{'date': '2026-10-20', 'revenue': 3.98, 'refundAmount': -1}]}]:
            with self.subTest(change=change):
                original = self.sales['data'].copy()
                self.sales['data'].update(change)
                try:
                    with self.assertRaisesRegex(ValueError, 'snapshot'):
                        self.read()
                finally:
                    self.sales['data'] = original


if __name__ == '__main__':
    unittest.main()
