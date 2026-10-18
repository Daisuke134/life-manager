"""Statement order context never manufactures CFEE identity or financial authority."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alpaca_cli as cli
import crypto_ownership_proof as proofs
import crypto_performance as perf
import crypto_statement_evidence as statements
import effect_store as store
import test_crypto_entry_account as entry_fixture
import test_crypto_performance as performance_fixture
import test_crypto_statement_evidence as statement_fixture
from test_crypto_activity_account import snapshot, seal
from test_crypto_operating_costs import billing
from test_crypto_performance import cycle_fixture
from test_crypto_statement_origin import ANCHORS, OTHER_ACCOUNT, native_readback, origin_packet


ACCOUNT = statement_fixture.ACCOUNT
DOCUMENT = statement_fixture.DOCUMENT
OBSERVED = '2026-01-03T06:00:00Z'
OWNER = 'alpaca-investment-live'
PAIRS = [(4, 'buy-0', 'buy-fill-0'), (5, 'sell-0-0', 'sell-fill-0-0')]
NEXT_PAIRS = [(6, 'buy-72', 'buy-fill-72'), (7, 'sell-72-0', 'sell-fill-72-0')]


def activity(fills, fees, *, mode, start, end):
    begin = proofs.parse_instant(start[:10] + 'T00:00:00Z')
    finish = proofs.parse_instant(end)
    selected_fills = [row for row in fills if begin <= proofs.parse_instant(row['transaction_time']) <= finish]
    selected_fees = [row for row in fees if begin <= proofs.parse_instant(row['created_at']) <= finish]
    frame = snapshot(ACCOUNT, mode=mode, start=start, end=end, fills=copy.deepcopy(selected_fills))
    frame['fees'] = copy.deepcopy(selected_fees)
    return seal(frame, 'alpaca-crypto-activities:')


class CryptoStatementOrderContextTests(unittest.TestCase):
    def setUp(self):
        self.forbidden_calls = []

    def forbidden(self, **kwargs):
        self.forbidden_calls.append(kwargs)
        raise AssertionError('provider access is forbidden in statement context tests')

    def prepare(self, root, *, case='valid', mode='live', two_days=False):
        fills = []
        fees = []
        if case == 'open':
            # Explicit account avoids the pre-existing helper's captured default argument.
            with patch.object(entry_fixture, 'ACCOUNT_A', ACCOUNT):
                marker, buy, observation, owner = entry_fixture.seed(root, mode)
                entry_fixture.save_entry(root, marker, buy, observation, owner, mode)
            fills = entry_fixture.native_activity(mode, [buy], account=ACCOUNT, end=OBSERVED)['fills']
            fees = [{'id': 'canonical-open-fee', 'activity_type': 'CFEE', 'order_id': buy['id'],
                'symbol': 'BTCUSD', 'qty': '-0.00005', 'date': '2026-01-01',
                'created_at': buy['filled_at'], 'net_amount': '0', 'status': 'executed'}]
            text = statement_fixture.TEXT.replace('buy-0', buy['id'])
        else:
            for index in ((0, 72) if two_days else (0,)):
                with patch.object(performance_fixture, 'NOW', OBSERVED):
                    orders, frame, _ = cycle_fixture(root, mode, index=index, zero=case == 'zero_sell',
                        native_account_id=None if case == 'legacy_account' else ACCOUNT)
                fills.extend(frame['fills'])
                sell = orders[-1]
                fees.append({'id': f'canonical-quote-fee-{index}', 'activity_type': 'CFEE', 'order_id': sell['id'],
                    'symbol': 'USDCUSD', 'qty': '-0.01', 'date': sell['submitted_at'][:10],
                    'created_at': sell['filled_at'], 'net_amount': '0', 'status': 'executed'})
            text = statement_fixture.TEXT
            if two_days:
                text = text.replace('synthetic-3', 'buy-72').replace('synthetic-4', 'sell-72-0')
        if case == 'missing_fill':
            fills = []
        elif case == 'wrong_order':
            text = text.replace('buy-0', 'foreign-buy').replace('sell-0-0', 'foreign-sell')
        elif case == 'wrong_asset':
            text = text.replace('buy-0          BTCUSD', 'buy-0          USDCUSD')
            text = text.replace('sell-0-0       USDCUSD', 'sell-0-0       BTCUSD')
        elif case in ('zero_qty', 'positive_qty'):
            sign = '' if case == 'zero_qty' else '+'
            text = text.replace('-0.000015', '0' if not sign else '+0.000015')
            text = text.replace('-0.012345', '0' if not sign else '+0.012345')
        elif case == 'zero_sell':
            text = text.replace('buy-0', 'foreign-buy')
        rows = store._rows(root / 'receipts.jsonl')
        start = next(row['decision']['observed_at'] for row in rows if row.get('receipt_type') == 'decision')
        frame = activity(fills, fees, mode=mode, start=start, end=OBSERVED)
        def reader(**kwargs):
            return activity(fills, fees, mode=mode, start=kwargs['period_start'], end=kwargs['period_end'])
        return rows, frame, reader, text

    def write(self, root, reader, text, *, mode='live', billing_path=None):
        env = {'PATH': os.environ.get('PATH', os.defpath)}
        if billing_path is not None:
            env['LM_CFO_ACTUAL_COST_READBACK'] = str(billing_path)
        observation = {'mode': mode, 'paper': mode == 'paper', 'clock': {'observed_at': OBSERVED}}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(cli, '_context', side_effect=AssertionError('provider forbidden')), \
                patch.object(statement_fixture, 'TEXT', text), \
                patch('subprocess.run', side_effect=statement_fixture.pdf_process):
            result = perf.write_crypto_performance(root, observation, mode=mode,
                owner_id='alpaca-investment-' + mode, activity_reader=reader,
                activity_page_reader=self.forbidden)
        self.assertEqual(self.forbidden_calls, [])
        self.assertIsNone(result['net_pnl_usd'])
        self.assertFalse(result['capital_expansion_allowed'])
        self.assertEqual(json.loads((root / 'performance-crypto-latest.json').read_text()), result)
        return result

    def add_packet(self, root, *, case='valid', capture=1, mode='live'):
        if case == 'unverified_origin' or mode == 'paper':
            return statement_fixture.packet(root, mode)
        proof = native_readback(capture)
        changes = None
        if case == 'foreign_account':
            proof['native_account_get']['id'] = proof['margin']['id'] = OTHER_ACCOUNT
            changes = {'native_trading_account_id': OTHER_ACCOUNT}
        return origin_packet(root, proof, mode=mode, metadata_changes=changes)

    def assert_financial_unchanged(self, result, baseline):
        for field in ('cycles', 'strategy_reports', 'completed_round_trips', 'execution_cashflow_usdc',
            'net_pnl_usd', 'gross_strategy_pnl_usd', 'fees_usd', 'model_cost_usd', 'system_cost_usd',
            'capital_expansion_allowed'):
            self.assertEqual(result.get(field), baseline.get(field), field)
        omitted = {'statement_evidence', 'statement_order_candidates'}
        self.assertEqual({k: v for k, v in result['fee_evidence'].items() if k not in omitted},
            {k: v for k, v in baseline['fee_evidence'].items() if k not in omitted})

    def assert_raw_unchanged(self, result):
        evidence = result['fee_evidence']['statement_evidence']
        self.assertEqual(evidence, statements.statement_inventory(result['statement_readbacks'], mode=result['mode']))
        self.assertEqual(evidence['observed_row_count'], 8)
        self.assertEqual(len(evidence['observations']), 8)
        for row in evidence['observations']:
            self.assertEqual(row['attribution_status'], 'unattributed')
            self.assertEqual(row['current_account_scope_status'], 'unknown')
            self.assertIn('fee_identity_unproved', row['reasons'])
            self.assertEqual(row['net_amount_raw'], '$ --')
            self.assertIsNone(row['net_amount_usd'])
            self.assertNotIn('fee_activity_id', row)
            self.assertNotIn('created_at', row)

    def expected(self, result, pairs):
        document = result['fee_evidence']['statement_evidence']['documents'][0]
        refs = sorted(ref['source_receipt_id'] for ref in document['capture_refs']
            if ref.get('official_pdf_origin', {}).get('status') == 'verified')
        expected = []
        for line, order, fill in pairs:
            cycle = next(cycle for cycle in result['cycles'] if order in cycle['order_ids'])
            self.assertEqual(cycle['native_trading_account_id'], ACCOUNT)
            self.assertEqual(cycle['owner_id'], OWNER)
            self.assertEqual(cycle['mode'], 'live')
            self.assertEqual(cycle['strategy_id'], 'alpaca-btc-5m-trend-400-v2')
            self.assertEqual(cycle['release_sha'], 'a' * 40)
            expected.append({'document_id': DOCUMENT, 'document_fingerprint': document['document_fingerprint'],
                'source_line_number': line, 'provider_order_id': order, 'cycle_id': cycle['cycle_id'],
                'fill_activity_ids': [fill], 'verified_capture_receipt_ids': refs, 'relation': 'order_context_only'})
        return sorted(expected, key=lambda item: item['source_line_number'])

    def assert_candidates(self, result, pairs):
        candidates = result['fee_evidence'].get('statement_order_candidates', [])
        self.assertEqual(sorted(candidates, key=lambda item: item['source_line_number']), self.expected(result, pairs))
        keys = [(item['document_id'], item['source_line_number'], item['cycle_id']) for item in candidates]
        self.assertEqual(len(keys), len(set(keys)))

    def test_verified_buy_and_sell_context_does_not_change_raw_or_canonical_fees(self):
        # Omitting the context consumer loses both links despite valid sealed account/order/FILL proof.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows, frame, reader, text = self.prepare(root)
            baseline = self.write(root, reader, text)
            self.add_packet(root)
            report = self.write(root, reader, text)
            self.assert_financial_unchanged(report, baseline)
            self.assert_raw_unchanged(report)
            self.assertEqual(report['fee_evidence']['observed_fee_count'], 1)
            self.assertEqual(report['fee_evidence']['observed_fee_activity_ids'], ['canonical-quote-fee-0'])
            self.assertEqual(report['cycles'][0]['observed_quote_fee_subtotal_usdc'], '0.01')
            self.assertEqual(report['cycles'][0]['cashflow_after_observed_quote_fees_usdc'], '0.49')
            # PDF qty differs from CFEE qty, and its BUY has no CFEE; these remain order-only links.
            self.assert_candidates(report, PAIRS)

    def test_distinct_statement_lines_for_one_order_remain_distinct_without_another_fee(self):
        # Capture replay deduplication must not collapse two native lines sharing all order values.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, reader, text = self.prepare(root)
            baseline = self.write(root, reader, text)
            lines = text.split('\n')
            lines[5] = lines[3]
            text = '\n'.join(lines)
            self.add_packet(root)
            report = self.write(root, reader, text)
            self.assert_financial_unchanged(report, baseline)
            self.assert_raw_unchanged(report)
            self.assertEqual(report['fee_evidence']['observed_fee_count'], 1)
            self.assertEqual(report['cycles'][0]['observed_quote_fee_subtotal_usdc'], '0.01')
            self.assert_candidates(report, PAIRS + [(6, 'buy-0', 'buy-fill-0')])

    def test_missing_or_ineligible_context_never_creates_candidates(self):
        # Each contrast keeps readable raw rows and the existing native fee authority.
        cases = ('legacy_account', 'unverified_origin', 'foreign_account', 'wrong_order',
            'wrong_asset', 'zero_qty', 'positive_qty', 'open', 'missing_fill', 'zero_sell', 'paper_legacy')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                mode = 'paper' if case == 'paper_legacy' else 'live'
                _, _, reader, text = self.prepare(root, case=case, mode=mode)
                baseline = self.write(root, reader, text, mode=mode)
                self.add_packet(root, case=case, mode=mode)
                report = self.write(root, reader, text, mode=mode)
                self.assert_financial_unchanged(report, baseline)
                self.assert_raw_unchanged(report)
                evidence = report['fee_evidence']['statement_evidence']
                first_rows = evidence['observations'][:2]
                if case == 'legacy_account':
                    self.assertNotIn('native_trading_account_id', report['cycles'][0])
                if case in ('unverified_origin', 'paper_legacy'):
                    self.assertTrue(all('official_pdf_origin' not in ref
                        for ref in evidence['documents'][0]['capture_refs']))
                if case == 'foreign_account':
                    document = evidence['documents'][0]
                    self.assertEqual(document['capture_trading_account_id'], OTHER_ACCOUNT)
                    self.assertEqual(document['capture_refs'][0]['official_pdf_origin']['status'], 'verified')
                if case == 'wrong_order':
                    self.assertEqual([row['order_id'] for row in first_rows], ['foreign-buy', 'foreign-sell'])
                if case == 'wrong_asset':
                    self.assertEqual([row['symbol'] for row in first_rows], ['USDCUSD', 'BTCUSD'])
                if case == 'zero_qty':
                    self.assertEqual([row['signed_qty_raw'] for row in first_rows], ['0', '0'])
                if case == 'positive_qty':
                    self.assertEqual([row['signed_qty_raw'] for row in first_rows], ['+0.000015', '+0.012345'])
                if case == 'missing_fill':
                    self.assertEqual(report['cycles'][0]['native_execution_status'], 'partial')
                if case == 'open':
                    self.assertEqual(report['cycles'], [])
                    self.assertEqual(len(report['open_entries']), 1)
                if case == 'zero_sell':
                    zero = next(order for order in report['cycles'][0]['orders'] if order['provider_order_id'] == 'sell-0-0')
                    self.assertEqual(zero['filled_qty'], '0')
                    self.assertEqual(zero['fill_activity_ids'], [])
                self.assertEqual(report['fee_evidence'].get('statement_order_candidates', []), [])

    def test_fresh_capture_replay_and_input_missing_rebuild_candidates_without_duplication(self):
        # Cached candidate claims are disposable; valid retained sources must recreate the same links.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, reader, text = self.prepare(root)
            baseline = self.write(root, reader, text)
            self.add_packet(root, case='unverified_origin')
            self.write(root, reader, text)
            self.add_packet(root, capture=1)
            self.write(root, reader, text)
            self.add_packet(root, capture=2)
            fresh = self.write(root, reader, text)
            changed = copy.deepcopy(fresh)
            changed['fee_evidence']['statement_order_candidates'] = [{'provider_order_id': 'forged-order',
                'cycle_id': 'forged-cycle', 'relation': 'fee_attributed'}]
            (root / 'performance-crypto-latest.json').write_text(json.dumps(changed))
            replay = self.write(root, self.forbidden, text)
            shutil.rmtree(root / 'statement-readbacks')
            missing = self.write(root, self.forbidden, text)
            for wake, report in (('fresh', fresh), ('replay', replay), ('missing', missing)):
                with self.subTest(wake=wake):
                    self.assert_financial_unchanged(report, baseline)
                    self.assert_raw_unchanged(report)
                    self.assertEqual(len(report['statement_readbacks']), 3)
                    self.assertEqual(len(report['known_statement_documents']), 1)
                    refs = report['fee_evidence']['statement_evidence']['documents'][0]['capture_refs']
                    self.assertEqual(len(refs), 3)
                    self.assertEqual(sum('official_pdf_origin' in ref for ref in refs), 2)
                    self.assert_candidates(report, PAIRS)
            self.assertEqual(missing['statement_input_status'], 'unavailable')

    def test_daily_candidates_follow_each_of_two_closed_cycle_days(self):
        # Copying every latest candidate to every daily report leaks another day's cycle context.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, reader, text = self.prepare(root, two_days=True)
            baseline = self.write(root, reader, text)
            days = ('2026-01-01', '2026-01-02')
            old_daily = {day: json.loads((root / f'performance-crypto-daily-{day}.json').read_text()) for day in days}
            self.add_packet(root)
            report = self.write(root, reader, text)
            self.assertEqual(report['fee_evidence']['observed_fee_count'], 2)
            views = [('latest', report, baseline, PAIRS + NEXT_PAIRS)] + [
                (day, json.loads((root / f'performance-crypto-daily-{day}.json').read_text()), old_daily[day], pairs)
                for day, pairs in zip(days, (PAIRS, NEXT_PAIRS))]
            for scope, result, previous, pairs in views:
                with self.subTest(scope=scope):
                    self.assert_financial_unchanged(result, previous)
                    if scope == 'latest':
                        self.assert_raw_unchanged(result)
                    else:
                        self.assertNotIn('statement_readbacks', result)
                        self.assertEqual(result['fee_evidence']['statement_evidence'], report['fee_evidence']['statement_evidence'])
                        self.assertEqual(result['fee_evidence']['attributed_native_fees'][0]['quantity'], '0.01')
                    self.assert_candidates(result, pairs)

    def test_invalid_input_preserves_raw_and_financial_anchors_without_reusing_cached_candidates(self):
        # A reporting failure retains prior evidence but cannot reuse an unvalidated candidate list.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows, frame, reader, text = self.prepare(root)
            built = perf.build_crypto_performance(rows, mode='live', owner_id=OWNER,
                activity_readbacks={row['order_id']: frame for row in frame['fills']})
            billing_path = root / 'billing.json'
            billing_path.write_text(json.dumps(billing(built['cycles'][0], 'live')))
            captured = self.add_packet(root)
            first = self.write(root, reader, text, billing_path=billing_path)
            self.assertEqual(len(first['known_operating_cost_components']), 4)
            self.assertEqual(first['known_fee_activity_ids'], ['canonical-quote-fee-0'])
            daily_path = root / 'performance-crypto-daily-2026-01-01.json'
            old_daily = json.loads(daily_path.read_text())
            changed = copy.deepcopy(first)
            changed['fee_evidence']['statement_order_candidates'] = [{'provider_order_id': 'forged-order'}]
            (root / 'performance-crypto-latest.json').write_text(json.dumps(changed))
            (captured / f'{DOCUMENT}.pdf').write_bytes(statement_fixture.PDF + b'changed')
            report = self.write(root, self.forbidden, text)
            self.assertEqual(report.get('reason'), 'crypto_statement_evidence_conflict')
            for anchor in ANCHORS:
                self.assertEqual(report[anchor], first[anchor], anchor)
            evidence = report['fee_evidence']['statement_evidence']
            self.assertEqual(evidence['observed_row_count'], 8)
            self.assertEqual(evidence['documents'], first['fee_evidence']['statement_evidence']['documents'])
            self.assertEqual(evidence['observations'], first['fee_evidence']['statement_evidence']['observations'])
            self.assertIn(report['fee_evidence'].get('statement_order_candidates'), (None, []))
            self.assertEqual(json.loads(daily_path.read_text()), old_daily)

    def test_without_documents_both_modes_keep_the_old_optional_field_shape(self):
        # The fixture's None default preserves old decisions and reports without statement inputs.
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                rows, frame, reader, text = self.prepare(root, case='legacy_account', mode=mode)
                decision = next(row['decision'] for row in rows if row.get('receipt_type') == 'decision')
                self.assertNotIn('native_trading_account_id', decision)
                self.assertNotIn('id', next(row['strategy_receipt']['account_readback']['account'] for row in rows
                    if row.get('receipt_type') == 'outcome' and row.get('strategy_receipt')))
                before = perf.build_crypto_performance(rows, mode=mode, owner_id='alpaca-investment-' + mode,
                    activity_readbacks={row['order_id']: frame for row in frame['fills']})
                report = self.write(root, reader, text, mode=mode)
                self.assert_financial_unchanged(report, before)
                self.assertNotIn('statement_order_candidates', report['fee_evidence'])


    def test_project_failure_retains_activity_evidence_and_recovers_without_provider_reads(self):
        # A bad sealed ledger cannot erase the captured inputs needed after its repair.
        retained = ('activity_readbacks', 'order_activity_refs', 'fee_activity_refs')
        for field, value in (('release_sha', 'b' * 40), ('native_trading_account_id', OTHER_ACCOUNT)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, reader, text = self.prepare(root)
                self.add_packet(root)
                first = self.write(root, reader, text)
                self.assert_candidates(first, PAIRS)
                for key in retained:
                    self.assertTrue(first[key], key)
                ledger = root / 'receipts.jsonl'
                original = ledger.read_bytes()
                changed = [json.loads(line) for line in original.decode().splitlines() if line.strip()]
                decision = next(row['decision'] for row in changed if row.get('receipt_type') == 'decision')
                decision[field] = value
                ledger.write_text(''.join(json.dumps(row) + '\n' for row in changed))
                daily = root / 'performance-crypto-daily-2026-01-01.json'
                old_daily = daily.read_bytes()
                failed = self.write(root, self.forbidden, text)
                self.assertEqual(failed['failed_phase'], 'project')
                self.assertEqual(failed['measurement_status'], 'partial')
                self.assert_raw_unchanged(failed)
                self.assertIn(failed['fee_evidence'].get('statement_order_candidates'), (None, []))
                self.assertEqual(daily.read_bytes(), old_daily)
                for key in ANCHORS:
                    if key not in retained:
                        self.assertEqual(failed[key], first[key], key)
                self.assertEqual({key: failed[key] for key in retained},
                    {key: first[key] for key in retained})
                ledger.write_bytes(original)
                recovered = self.write(root, self.forbidden, text)
                self.assertEqual(recovered['reason'], 'crypto_costs_or_fx_unknown')
                self.assert_financial_unchanged(recovered, first)
                self.assert_raw_unchanged(recovered)
                self.assert_candidates(recovered, PAIRS)
                for key in ANCHORS:
                    self.assertEqual(recovered[key], first[key], key)

    def test_wrong_cache_owner_or_mode_keeps_early_rejection_of_activity_references(self):
        # Retaining project inputs does not authorize an invalid cache from another scope.
        for field, value in (('owner_id', 'alpaca-investment-paper'), ('mode', 'paper')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, reader, text = self.prepare(root)
                self.add_packet(root)
                first = self.write(root, reader, text)
                changed = copy.deepcopy(first)
                changed[field] = value
                (root / 'performance-crypto-latest.json').write_text(json.dumps(changed))
                failed = self.write(root, self.forbidden, text)
                self.assertEqual(failed['failed_phase'], 'cache')
                self.assertEqual(failed['reason'], 'crypto_performance_activity_cache_invalid')
                self.assertEqual(failed['activity_readbacks'], {})
                self.assertEqual(failed['order_activity_refs'], {})
                self.assertEqual(failed['fee_activity_refs'], [])
                self.assertIn(failed['fee_evidence'].get('statement_order_candidates'), (None, []))


if __name__ == '__main__':
    unittest.main()
