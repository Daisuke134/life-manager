"""Native statement rows remain observations, never inferred CFEE or USD net."""
import copy
from contextlib import ExitStack, redirect_stdout
import hashlib
from io import StringIO
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
UI_ACCOUNT = '44444444-4444-4444-8444-444444444444'
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
        'source_path': f'/api/v1/accounts/{UI_ACCOUNT}/documents',
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

    def test_same_document_replay_and_missing_input_retain_each_row_once(self):
        # Rebuilding from only the current directory must not erase accepted history.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation, read = self.prepare(root)
            packet(root)
            with patch('subprocess.run', side_effect=pdf_process):
                first = self.write(root, observation, read)
                replay = self.write(root, observation, read)
            self.assertEqual(replay.get('fee_evidence', {}).get('statement_evidence', {}).get('observed_row_count'), 8)
            self.assertEqual(replay['fee_evidence']['statement_evidence'], first['fee_evidence']['statement_evidence'])
            documents = replay['statement_readbacks']
            projected = perf.build_crypto_performance([], mode='paper', owner_id='alpaca-investment-paper',
                statement_readbacks=documents + copy.deepcopy(documents))
            self.assertEqual(projected['fee_evidence']['statement_evidence']['observed_row_count'], 8)
            (root / 'statement-readbacks').rename(root / 'withheld-input')
            absent = self.write(root, observation, read)
            self.assertEqual(absent['fee_evidence']['statement_evidence'], first['fee_evidence']['statement_evidence'])
            self.assertEqual(absent['statement_input_status'], 'unavailable')

    def test_statement_is_retained_without_an_owned_cycle(self):
        # The historical not_applicable return must not discard account observations.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet(root)
            observation = {'mode': 'paper', 'paper': True, 'clock': {'observed_at': NOW}}
            with patch('subprocess.run', side_effect=pdf_process):
                report = self.write(root, observation, None)
            self.assertEqual(report.get('fee_evidence', {}).get('statement_evidence', {}).get('observed_row_count'), 8)
            self.assertEqual(report['cycles'], [])
            self.assertIsNone(report['net_pnl_usd'])
            self.assertFalse(report['capital_expansion_allowed'])

    def test_metadata_scope_and_unmapped_document_are_typed_unknown(self):
        # Trusting a mode/binding boolean or a foreign path would accept another account.
        variants = [
            {'measurement_mode': 'live'}, {'account_binding_verified': False},
            {'native_trading_account_id': ''},
            {'source_host': 'example.invalid'}, {'source_path': '/api/v1/accounts/foreign/documents'},
            {'native_account_get_request_id': ''}, {'native_account_get_date': 'invalid'},
            {'documents_request_id': ''},
            {'rows': [{'id': DOCUMENT, 'type': 'account_statement', 'date': '2026-01-01'}]},
            {'rows': [{'id': DOCUMENT, 'type': 'crypto_account_statement', 'date': '2026-02-30'}]},
        ]
        for changes in variants:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                observation, read = self.prepare(root)
                packet(root, metadata_changes=changes)
                with patch('subprocess.run', side_effect=pdf_process):
                    report = self.write(root, observation, read)
                self.assertEqual(report.get('reason'), 'crypto_statement_input_invalid')
                evidence = report['fee_evidence']['statement_evidence']
                self.assertEqual(evidence['status'], 'unknown')
                self.assertIsNone(evidence['observed_row_count'])
                self.assertIsNone(report['net_pnl_usd'])

    def test_private_input_checks_and_initial_hash_mismatch_are_typed_unknown(self):
        # Following links or accepting public files would bypass the private input boundary.
        for variant in ('metadata_mode', 'pdf_mode', 'directory_mode', 'symlink', 'hardlink', 'oversize', 'metadata_hash'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                observation, read = self.prepare(root)
                captured = packet(root)
                pdf = captured / f'{DOCUMENT}.pdf'
                if variant == 'metadata_mode': (captured / 'metadata.json').chmod(0o644)
                elif variant == 'pdf_mode': pdf.chmod(0o644)
                elif variant == 'directory_mode': captured.chmod(0o755)
                elif variant == 'symlink':
                    pdf.rename(root / 'external.pdf')
                    pdf.symlink_to(root / 'external.pdf')
                elif variant == 'hardlink': os.link(pdf, root / 'alias.pdf')
                elif variant == 'oversize':
                    with pdf.open('r+b') as handle: handle.truncate(8 * 1024 * 1024 + 1)
                elif variant == 'metadata_hash':
                    (captured / 'metadata.json').write_bytes((captured / 'metadata.json').read_bytes() + b' ')
                with patch('subprocess.run', side_effect=pdf_process):
                    report = self.write(root, observation, read)
                self.assertEqual(report.get('reason'), 'crypto_statement_input_invalid')
                self.assertEqual(report['fee_evidence']['statement_evidence']['status'], 'unknown')

    def test_known_pdf_metadata_and_extracted_row_changes_are_conflicts_without_row_loss(self):
        # A later read of one native document must not overwrite its accepted evidence.
        for variant in ('pdf', 'metadata', 'row'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                observation, read = self.prepare(root)
                captured = packet(root)
                with patch('subprocess.run', side_effect=pdf_process):
                    first = self.write(root, observation, read)
                original = first.get('fee_evidence', {}).get('statement_evidence')
                self.assertIsInstance(original, dict)
                if variant == 'pdf': (captured / f'{DOCUMENT}.pdf').write_bytes(PDF + b'changed')
                elif variant == 'metadata':
                    (captured / 'metadata.json').write_bytes((captured / 'metadata.json').read_bytes() + b' ')
                def changed(args, **kwargs):
                    kwargs['stdout'].write(TEXT.replace('-0.000015', '-0.000099').encode())
                    return subprocess.CompletedProcess(args, 0)
                with patch('subprocess.run', side_effect=changed if variant == 'row' else pdf_process):
                    report = self.write(root, observation, read)
                self.assertEqual(report.get('reason'), 'crypto_statement_evidence_conflict')
                evidence = report['fee_evidence']['statement_evidence']
                self.assertEqual(evidence['status'], 'conflict')
                self.assertEqual(evidence['observations'], original['observations'])
                self.assertEqual(report['known_statement_documents'], first['known_statement_documents'])
                saved = json.loads((root / 'performance-crypto-daily-2026-01-01.json').read_text())
                self.assertEqual(saved['fee_evidence']['statement_evidence']['observations'], original['observations'])

    def test_cache_projection_raw_rows_and_missing_known_document_are_conflicts(self):
        # A modified cache must not silently change or erase accepted source rows.
        for variant in ('projection', 'raw_row', 'missing_document', 'pdf_hash'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                observation, read = self.prepare(root)
                packet(root)
                with patch('subprocess.run', side_effect=pdf_process):
                    first = self.write(root, observation, read)
                self.assertIsInstance(first.get('fee_evidence', {}).get('statement_evidence'), dict)
                corrupt = copy.deepcopy(first)
                if variant == 'projection':
                    corrupt['fee_evidence']['statement_evidence']['observations'][0]['signed_qty_raw'] = '-1'
                elif variant == 'raw_row':
                    corrupt['statement_readbacks'][0]['fee_lines'][0]['raw_line'] = 'forged'
                elif variant == 'missing_document': corrupt['statement_readbacks'] = []
                elif variant == 'pdf_hash': corrupt['statement_readbacks'][0]['pdf_sha256'] = 'f' * 64
                (root / 'performance-crypto-latest.json').write_text(json.dumps(corrupt))
                report = self.write(root, observation, read)
                self.assertEqual(report.get('reason'), 'crypto_statement_evidence_conflict')
                self.assertEqual(report['fee_evidence']['statement_evidence']['status'], 'conflict')
                self.assertEqual(report['known_statement_documents'], first['known_statement_documents'])
                self.assertIsNone(report['net_pnl_usd'])

    def test_unreadable_fee_rows_and_missing_extractor_stay_typed_unknown_without_private_text(self):
        # Parser/tool failures cannot become an empty fee table or leak a process error.
        for variant in ('date', 'quantity', 'table', 'missing_tool', 'timeout'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                observation, read = self.prepare(root)
                packet(root)
                def broken(args, **kwargs):
                    if variant == 'missing_tool': raise FileNotFoundError('PRIVATE PROCESS DETAIL')
                    if variant == 'timeout': raise subprocess.TimeoutExpired(args, 10, stderr='PRIVATE PROCESS DETAIL')
                    text = TEXT.replace('01/01/2026', '02/30/2026') if variant == 'date' else (
                        TEXT.replace('-0.000015', 'NaN') if variant == 'quantity' else 'PRIVATE DOCUMENT BODY')
                    kwargs['stdout'].write(text.encode())
                    return subprocess.CompletedProcess(args, 0)
                with patch('subprocess.run', side_effect=broken):
                    report = self.write(root, observation, read)
                expected = 'crypto_statement_tool_unavailable' if variant == 'missing_tool' else (
                    'crypto_statement_extraction_failed' if variant == 'timeout' else 'crypto_statement_input_invalid')
                self.assertEqual(report.get('reason'), expected)
                self.assertEqual(report['fee_evidence']['statement_evidence']['status'], 'unknown')
                self.assertNotIn('PRIVATE', json.dumps(report))

    def test_real_main_preserves_statement_rows_through_the_real_writer_and_daily(self):
        # Omitting the caller's statement directory must not pass a writer-only test.
        from test_crypto_close import native_run
        from test_owned_policy import snapshot
        import alpaca_cli as cli
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                root = Path(directory)
                orders, activity, owned = cycle_fixture(root, mode)
                packet(root, mode)
                (root / 'live-owned-position.json').write_text(json.dumps(owned))
                native = native_run()
                observation = {'mode': mode, 'paper': mode == 'paper', 'clock': {'observed_at': NOW},
                    'account': {'cash': '0', 'equity': '100'},
                    'positions': [{'symbol': 'USDCUSD', 'qty': '100', 'unrealized_pl': '0'}],
                    'activities_count': 0, 'open_and_closed_orders_count': 0}
                raw, _ = snapshot(mode)
                raw.pop('crypto_history')
                raw['positions'] = 0
                stack.enter_context(patch.dict(os.environ, {'LIFE_MANAGER_INVESTMENT_MODE': mode,
                    'LIFE_MANAGER_INVESTMENT_DEPLOYMENT': 'local',
                    'LIFE_MANAGER_INVESTMENT_OWNER_ID': 'alpaca-investment-' + mode,
                    f'ALPACA_INVESTMENT_{mode.upper()}_STATE_DIR': str(root),
                    f'ALPACA_INVESTMENT_{mode.upper()}_CREDENTIALS_FILE': str(root / 'unused')}, clear=True))
                for name, value in (('observe', observation), ('read_allocator_snapshot', raw),
                    ('read_crypto_activity_evidence', activity), ('read_crypto_history', {}),
                    ('build_candidates', []), ('_review_status', {}),
                    ('read_campaign_snapshot', {'paper': True, 'unexpected_positions': [], 'fills': [], 'positions': [], 'options': []}),
                    ('deliver', {'message_id': 'synthetic-message'}), ('deliver_failure', {'status': 'delivered'})):
                    stack.enter_context(patch.object(native, name, return_value=value))
                stack.enter_context(patch.object(native, 'find_order_by_client_id', side_effect=lambda **kw:
                    next(o for o in orders if o['client_order_id'] == kw['client_order_id'])))
                stack.enter_context(patch.object(native, 'read_crypto_fx_evidence', side_effect=RuntimeError('offline fixture')))
                stack.enter_context(patch.object(cli, '_context', side_effect=AssertionError('provider forbidden')))
                stack.enter_context(patch('subprocess.run', side_effect=pdf_process))
                with redirect_stdout(StringIO()) as output:
                    code = native.main(wake_id='synthetic-statement-input')
                self.assertEqual(code, 0, output.getvalue())
                latest = json.loads((root / 'performance-crypto-latest.json').read_text())
                self.assertEqual(latest.get('fee_evidence', {}).get('statement_evidence', {}).get('observed_row_count'), 8)
                daily = json.loads((root / 'performance-crypto-daily-2026-01-01.json').read_text())
                self.assertEqual(daily['fee_evidence']['statement_evidence']['observed_row_count'], 8)
                self.assertNotIn('statement_readbacks', daily)
                self.assertIsNone(latest['net_pnl_usd'])
                self.assertFalse(latest['capital_expansion_allowed'])


if __name__ == '__main__':
    unittest.main()
