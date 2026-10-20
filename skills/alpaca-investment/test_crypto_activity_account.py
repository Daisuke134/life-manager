"""Native account capture is bound to one env; old missing identity stays unknown."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alpaca_cli as cli
import crypto_ownership_proof as proofs
from test_crypto_activity_pages import activity_rows, START, END
from test_crypto_activity_evidence import FILL

MISSING = object()
ACCOUNT = 'synthetic-native-account-A'


def seal(body, prefix):
    body.pop('source_receipt_id', None)
    body['source_receipt_id'] = prefix + proofs._digest([body])
    return body


def snapshot(account=MISSING, *, mode='paper', start=START, end=END, fills=None):
    body = {'schema_version': 1, 'mode': mode, 'paper': mode == 'paper',
        'requested_period_start': start, 'requested_period_end': end,
        'request': {'after': start[:10] + 'T00:00:00Z', 'until': end, 'direction': 'asc', 'page_size': 100},
        'pagination': 'exhausted', 'fills': fills or [], 'fees': [],
        'fee_attribution_status': 'unknown', 'fee_settlement_status': 'unknown', 'net_realized_pnl_usd': None}
    if account is not MISSING:
        body['native_trading_account_id'] = account
    return seal(body, 'alpaca-crypto-activities:')


def chunk(kind, account=MISSING, *, mode='paper', resume=False, partial=False):
    records = activity_rows(kind)
    rows = records[:400] if partial else records[400:] if resume else []
    pages = [rows[i:i + 100] for i in range(0, len(rows), 100)] or [[]]
    token = records[399]['id'] if resume else None
    next_token = records[399]['id'] if partial else None
    body = {'schema_version': 1, 'kind': 'crypto_activity_page_chunk', 'mode': mode, 'paper': mode == 'paper',
        'requested_period_start': START, 'requested_period_end': END,
        'request': {'after': '2026-01-01T00:00:00Z', 'until': END, 'direction': 'asc', 'page_size': 100,
            'activity_type': kind, 'page_token': token}, 'pages': pages,
        'pagination': 'partial' if partial else 'exhausted', 'next_page_token': next_token}
    if account is not MISSING:
        body['native_trading_account_id'] = account
    return seal(body, 'alpaca-crypto-activity-chunk:')


class CryptoActivityAccountTests(unittest.TestCase):
    def capture(self, reader, *, mode='paper', account=None, records=None):
        env = {'synthetic-mode': mode}
        calls = []
        account = {'id': ACCOUNT} if account is None else account
        records = records or {kind: activity_rows(kind, 101) for kind in ('FILL', 'CFEE')}
        def run(path, args, selected_env):
            calls.append((copy.deepcopy(args), selected_env))
            if args[:2] == ['account', 'get']:
                return copy.deepcopy(account)
            kind = args[args.index('--activity-types') + 1]
            rows = records[kind]
            token = args[args.index('--page-token') + 1] if '--page-token' in args else None
            start = next((i + 1 for i, row in enumerate(rows) if row['id'] == token), 0) if token else 0
            return copy.deepcopy(rows[start:start + 100])
        kwargs = {'credentials_path': Path('unused'), 'cli_path': Path('unused'), 'mode': mode,
            'period_start': START, 'period_end': END}
        if reader is cli.read_crypto_activity_page_chunk:
            kwargs['activity_type'] = 'FILL'
        with patch.object(cli, '_context', return_value=env) as context, patch.object(cli, '_run', side_effect=run):
            value = reader(**kwargs)
            context.assert_called_once_with(Path('unused'), Path('unused'), mode=mode)
        return value, env, calls

    def test_both_capture_readers_bind_native_id_and_every_page_to_the_same_env(self):
        # A second context or an omitted GET breaks the native account/page binding.
        for mode in ('paper', 'live'):
            for reader in (cli.read_crypto_activity_evidence, cli.read_crypto_activity_page_chunk):
                with self.subTest(mode=mode, reader=reader.__name__):
                    value, env, calls = self.capture(reader, mode=mode)
                    self.assertEqual(value.get('native_trading_account_id'), ACCOUNT)
                    account_calls = [args for args, _ in calls if args[:2] == ['account', 'get']]
                    page_calls = [args for args, _ in calls if args[:3] == ['account', 'activity', 'list']]
                    self.assertEqual(len(account_calls), 1)
                    self.assertGreaterEqual(len(page_calls), 2)
                    self.assertTrue(all(selected is env for _, selected in calls))
                    tampered = copy.deepcopy(value)
                    tampered['native_trading_account_id'] = 'synthetic-native-account-B'
                    validator = (proofs.validate_crypto_activity_snapshot if reader is cli.read_crypto_activity_evidence
                        else proofs.validate_crypto_activity_page_chunk)
                    with self.assertRaises(ValueError):
                        validator(tampered, mode=mode)

    def test_missing_empty_or_wrong_type_account_get_id_never_becomes_a_capture(self):
        # Fresh capture requires a native GET id, never a configured or inferred account.
        for account in ({}, {'id': None}, {'id': ''}, {'id': '  '}, {'id': 7}, {'id': False}, {'id': []}, []):
            for reader in (cli.read_crypto_activity_evidence, cli.read_crypto_activity_page_chunk):
                with self.subTest(account=account, reader=reader.__name__):
                    with self.assertRaisesRegex(ValueError, 'crypto_activity_account_invalid'):
                        self.capture(reader, account=account)

    def test_same_account_resume_and_both_streams_keep_one_native_id(self):
        # Valid continuation must retain account scope through the paged envelope.
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode):
                chunks = [chunk('FILL', ACCOUNT, mode=mode, partial=True),
                    chunk('FILL', ACCOUNT, mode=mode, resume=True), chunk('CFEE', ACCOUNT, mode=mode)]
                progress = proofs.crypto_activity_page_progress(chunks, mode=mode)
                self.assertTrue(progress['complete'])
                self.assertEqual(progress.get('native_trading_account_id'), ACCOUNT)
                captured = proofs.crypto_activity_paged_snapshot(chunks, mode=mode)
                self.assertEqual(captured.get('native_trading_account_id'), ACCOUNT)
                self.assertEqual(len(captured['fills']), 401)
                proofs.validate_crypto_activity_snapshot(captured, mode=mode)

    def test_account_change_between_resume_chunks_or_fill_fee_streams_is_rejected(self):
        # A new context on resume must not merge another native account into one window.
        variants = [
            [chunk('FILL', ACCOUNT, partial=True), chunk('FILL', 'synthetic-native-account-B', resume=True)],
            [chunk('FILL', ACCOUNT), chunk('CFEE', 'synthetic-native-account-B')],
        ]
        for chunks in variants:
            with self.subTest(resume=len(chunks[0]['pages']) == 4):
                with self.assertRaisesRegex(ValueError, 'owned_crypto_activity_pages_invalid'):
                    proofs.crypto_activity_page_progress(chunks, mode='paper')

    def test_bundles_retain_same_account_and_reject_same_window_cross_account(self):
        # Content-valid envelopes from another account must not enter a bundle.
        first = snapshot(ACCOUNT)
        later = snapshot(ACCOUNT, start=END, end='2026-01-03T00:00:00Z')
        combined = proofs.combine_crypto_activity_snapshots([first, later], mode='paper')
        self.assertEqual(combined.get('native_trading_account_id'), ACCOUNT)
        proofs.validate_crypto_activity_snapshot(combined, mode='paper')
        with self.assertRaisesRegex(ValueError, 'owned_crypto_activities_invalid'):
            proofs.combine_crypto_activity_snapshots([first, snapshot('synthetic-native-account-B')], mode='paper')

    def test_legacy_and_mixed_evidence_stay_unknown_without_hiding_nested_conflicts(self):
        # Old missing scope remains readable; mixing it with new scope proves no account.
        old = snapshot(fills=[copy.deepcopy(FILL)])
        old_before = copy.deepcopy(old)
        broker = {'id': FILL['order_id'], 'client_order_id': 'synthetic-client', 'symbol': 'BTCUSDC',
            'side': 'buy', 'type': 'market', 'time_in_force': 'gtc', 'status': 'filled',
            'filled_qty': '0.02', 'filled_avg_price': '200', 'submitted_at': START,
            'filled_at': FILL['transaction_time']}
        facts = proofs.crypto_fill_activity_proof(old, broker, mode='paper')
        self.assertEqual(facts['filled_qty'], '0.02')
        self.assertEqual(old, old_before)
        self.assertNotIn('native_trading_account_id', old)
        mixed = proofs.combine_crypto_activity_snapshots([old, snapshot(ACCOUNT)], mode='paper')
        self.assertIsNone(mixed.get('native_trading_account_id'))
        paged = proofs.crypto_activity_paged_snapshot([chunk('FILL'), chunk('CFEE', ACCOUNT)], mode='paper')
        self.assertIsNone(paged.get('native_trading_account_id'))
        proofs.validate_crypto_activity_snapshot(paged, mode='paper')
        with self.assertRaisesRegex(ValueError, 'owned_crypto_activities_invalid'):
            proofs.combine_crypto_activity_snapshots([paged, snapshot('synthetic-native-account-B')], mode='paper')
        legacy_pages = proofs.crypto_activity_paged_snapshot([chunk('FILL'), chunk('CFEE')], mode='paper')
        self.assertNotIn('native_trading_account_id', legacy_pages)
        proofs.validate_crypto_activity_snapshot(legacy_pages, mode='paper')

    def test_explicit_invalid_native_id_is_not_accepted_as_legacy_missing_scope(self):
        # Legacy compatibility permits absence, not a signed but malformed new field.
        for value in (None, '', '  ', 7, False, []):
            for make, validator in ((lambda: snapshot(value), proofs.validate_crypto_activity_snapshot),
                (lambda: chunk('FILL', value), proofs.validate_crypto_activity_page_chunk)):
                with self.subTest(value=value, envelope=validator.__name__):
                    with self.assertRaises(ValueError):
                        validator(make(), mode='paper')


if __name__ == '__main__':
    unittest.main()
