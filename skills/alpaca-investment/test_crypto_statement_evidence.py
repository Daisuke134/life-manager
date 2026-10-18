"""Native statement rows remain observations, never inferred CFEE or USD net."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crypto_performance as perf
from test_crypto_performance import NOW, activity_fixture, cycle_fixture


ACCOUNT = '11111111-1111-4111-8111-111111111111'
DOCUMENT = '22222222-2222-4222-8222-222222222222'
PDF = b'%PDF-1.4\nsynthetic crypto statement\n'
TEXT = '''Synthetic crypto statement
Fees
Trade Date   Order ID       Symbol   Qty          Net Amt
01/01/2026   buy-0          BTCUSD   -0.000015    $ --
01/01/2026   sell-0-0       USDCUSD  -0.012345    $ --
01/01/2026   synthetic-3    BTCUSD   -0.000025    $ --
01/01/2026   synthetic-4    USDCUSD  -0.023456    $ --
01/01/2026   synthetic-5    BTCUSD   -0.000035    $ --
01/01/2026   synthetic-6    USDCUSD  -0.034567    $ --
01/01/2026   synthetic-7    BTCUSD   -0.000045    $ --
01/01/2026   synthetic-8    USDCUSD  -0.045678    $ --

Transaction
'''


def packet(root, mode='paper', *, metadata_changes=None, pdf=PDF):
    metadata = {
        'source_host': 'app.alpaca.markets',
        'source_path': f'/api/v1/accounts/{ACCOUNT}/documents',
        'measurement_mode': mode,
        'account_binding_verified': True,
        'native_trading_account_id': ACCOUNT,
        'native_account_get_request_id': 'synthetic-account-request',
        'native_account_get_date': 'Thu, 01 Jan 2026 06:00:00 GMT',
        'documents_request_id': 'synthetic-documents-request',
        'rows': [
            {'id': 'synthetic-application', 'type': 'account_application', 'sub_type': '',
             'date': '2026-01-01', 'name': 'Synthetic application'},
            {'id': DOCUMENT, 'type': 'crypto_account_statement', 'sub_type': '',
             'date': '2026-01-01', 'name': 'Synthetic crypto statement'},
        ],
    }
    metadata.update(metadata_changes or {})
    raw = (json.dumps(metadata, indent=2) + '\n').encode()
    directory = root / 'statement-readbacks' / hashlib.sha256(raw).hexdigest()
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    directory.parent.chmod(0o700)
    (directory / 'metadata.json').write_bytes(raw)
    (directory / 'metadata.json').chmod(0o600)
    (directory / f'{DOCUMENT}.pdf').write_bytes(pdf)
    (directory / f'{DOCUMENT}.pdf').chmod(0o600)
    return directory


def pdf_process(args, **kwargs):
    kwargs['stdout'].write(TEXT.encode())
    return subprocess.CompletedProcess(args, 0)


class CryptoStatementEvidenceTests(unittest.TestCase):
    def prepare(self, root, mode='paper'):
        orders, frame, owned = cycle_fixture(root, mode)
        observation = {'mode': mode, 'paper': mode == 'paper', 'clock': {'observed_at': NOW}}
        def read(**kwargs):
            return activity_fixture(frame, mode=mode, start=kwargs['period_start'], end=kwargs['period_end'])
        return observation, read

    def write(self, root, observation, reader):
        with patch.dict(os.environ, {}, clear=True):
            return perf.write_crypto_performance(root, observation, mode=observation['mode'],
                owner_id='alpaca-investment-' + observation['mode'], activity_reader=reader)

    def test_writer_keeps_eight_native_rows_in_cache_and_daily_without_attributing_them(self):
        # Dropping the optional input from the writer or builder must lose these rows.
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                observation, read = self.prepare(root, mode)
                packet(root, mode)
                with patch('subprocess.run', side_effect=pdf_process):
                    report = self.write(root, observation, read)
                evidence = report.get('fee_evidence', {}).get('statement_evidence')
                self.assertIsInstance(evidence, dict, 'native statement input must reach the existing writer')
                self.assertEqual(evidence['status'], 'recorded')
                self.assertEqual(evidence['observed_row_count'], 8)
                self.assertEqual(len(evidence['observations']), 8)
                row = evidence['observations'][0]
                self.assertEqual(row['trade_date_raw'], '01/01/2026')
                self.assertEqual(row['order_id'], 'buy-0')
                self.assertEqual(row['symbol'], 'BTCUSD')
                self.assertEqual(row['signed_qty_raw'], '-0.000015')
                self.assertEqual(row['net_amount_raw'], '$ --')
                self.assertIsNone(row['net_amount_usd'])
                self.assertEqual(row['source_line_number'], 4)
                self.assertEqual(row['attribution_status'], 'unattributed')
                self.assertIn('account_scope_unknown', row['reasons'])
                self.assertNotIn('created_at', row)
                self.assertNotIn('fee_activity_id', row)
                self.assertEqual(report['fee_evidence']['observed_fee_count'], 0)
                self.assertEqual(report['fee_evidence']['attributed_native_fees'], [])
                self.assertEqual(report['cycles'][0]['execution_cashflow_usdc'], '0.5')
                self.assertIsNone(report['net_pnl_usd'])
                self.assertFalse(report['capital_expansion_allowed'])
                for name in ('performance-crypto-latest.json', 'performance-crypto-daily-2026-01-01.json'):
                    saved = json.loads((root / name).read_text())
                    self.assertEqual(saved['fee_evidence']['statement_evidence'], evidence)

    def test_absent_statement_is_unavailable_instead_of_zero_fee_or_complete(self):
        # An empty optional input must not become an asserted zero or complete period.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation, read = self.prepare(root)
            report = self.write(root, observation, read)
            evidence = report.get('fee_evidence', {}).get('statement_evidence')
            self.assertIsInstance(evidence, dict, 'missing native statement input needs a typed state')
            self.assertEqual(evidence['status'], 'unavailable')
            self.assertIsNone(evidence['observed_row_count'])
            self.assertEqual(evidence['completeness_status'], 'unknown')
            self.assertIsNone(report['fees_usd'])
            self.assertIsNone(report['net_pnl_usd'])


if __name__ == '__main__':
    unittest.main()
