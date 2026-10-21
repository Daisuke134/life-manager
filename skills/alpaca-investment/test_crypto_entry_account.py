"""Account identity follows new sealed entries; legacy decisions stay unbound."""
import copy
from contextlib import ExitStack, redirect_stdout
from datetime import timedelta
from io import StringIO
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alpaca_cli as cli
import allocator
import crypto_ownership_proof as proofs
import crypto_performance as perf
import effect_store as store
import position_manager
from strategy_policy import candidate_cards
from test_crypto_activity_account import snapshot as activity_snapshot
from test_crypto_close import native_run
from test_etf_allocator import _snapshot, _candidate

ACCOUNT_A = 'synthetic-trading-account-A'
ACCOUNT_B = 'synthetic-trading-account-B'
START = '2026-01-01T04:00:00Z'


def seed(root, mode, *, bound=True, partial=False, pre_trade_readback=None):
    owner = 'alpaca-investment-' + mode
    card = candidate_cards()['alpaca-btc-5m-trend-400-v2' if bound else 'alpaca-btc-5m-trend-v1']
    decision = {'action': 'ENTER', 'mode': mode, 'owner_id': owner, 'strategy_id': card.strategy_id,
        'policy_card': card.to_mapping(), 'release_sha': 'a' * 40, 'observed_at': START}
    if bound:
        decision['native_trading_account_id'] = ACCOUNT_A
    if pre_trade_readback is not None:
        decision['pre_trade_account_readback'] = pre_trade_readback
    sealed = store.seal(root / 'receipts.jsonl', decision, {'asset_class': 'crypto', 'symbol': 'BTC/USDC',
        'side': 'buy', 'type': 'market', 'time_in_force': 'gtc', 'notional_usd': '10'})
    store.mark_started(root / 'receipts.jsonl', sealed)
    marker = {'status': 'entry_pending', 'symbol': 'BTCUSD', 'entry_effect_id': sealed['effect_id'],
        'entry_client_order_id': sealed['client_order_id'], 'entry_filled_qty': '0'}
    (root / 'live-owned-position.json').write_text(json.dumps(marker))
    broker = {'id': 'synthetic-entry', 'client_order_id': sealed['client_order_id'], 'symbol': 'BTCUSDC',
        'side': 'buy', 'type': 'market', 'time_in_force': 'gtc', 'status': 'canceled' if partial else 'filled',
        'filled_qty': '0.05', 'filled_avg_price': None if partial else '200',
        'submitted_at': START, 'filled_at': None if partial else '2026-01-01T04:00:01Z'}
    observation = {'mode': mode, 'paper': mode == 'paper', 'account': {'id': ACCOUNT_A, 'cash': '90', 'equity': '100'},
        'positions': [{'symbol': 'BTCUSDC', 'qty': '0.05', 'avg_entry_price': '200', 'unrealized_pl': '0'}],
        'clock': {'observed_at': '2026-01-01T04:00:02Z'}, 'activities_count': 0, 'open_and_closed_orders_count': 0}
    return marker, broker, observation, owner


def native_activity(mode, orders, *, account=ACCOUNT_A, end=None):
    fills = [{'id': 'fill-' + order['id'], 'activity_type': 'FILL', 'order_id': order['id'],
        'symbol': 'BTCUSDC', 'side': order['side'], 'qty': order['filled_qty'],
        'price': order['filled_avg_price'] or '200',
        'transaction_time': order['filled_at'] or '2026-01-01T04:00:01Z'} for order in orders]
    if end is None:
        end = (proofs.parse_instant(fills[-1]['transaction_time']) + timedelta(seconds=1)).isoformat()
    return activity_snapshot(account, mode=mode, start=orders[0]['submitted_at'], end=end, fills=fills)


def save_entry(root, marker, broker, observation, owner, mode, *, backfill=False, activity=None):
    ledger = root / 'receipts.jsonl'
    if backfill:
        store.reconcile_started(ledger, lambda _: copy.deepcopy(broker))
    native = native_run()
    with patch.dict(os.environ, {'LIFE_MANAGER_INVESTMENT_MODE': mode,
        'LIFE_MANAGER_INVESTMENT_OWNER_ID': owner}, clear=True), \
            patch.object(native, 'observe', side_effect=lambda **_: copy.deepcopy(observation)), \
            patch.object(native, 'read_crypto_activity_evidence', return_value=activity), \
            patch.object(cli, '_context', side_effect=AssertionError('provider forbidden')):
        return store.reconcile_started(ledger, lambda _: copy.deepcopy(broker), on_reconciled=lambda intent, order:
            native._reconcile_crypto_entry(intent, order, state=root,
                credentials_path=Path('unused'), cli_path=Path('unused')))


def close_cycle(root, marker, broker, observation, owner, mode, *, closing_account=ACCOUNT_A, terminal=False):
    rows = store._rows(root / 'receipts.jsonl')
    acquired = proofs.recorded_entry_proof_from_rows(rows, marker, broker, observation, mode=mode, owner_id=owner)
    owned = {**marker, 'status': 'open', 'entry_filled_qty': '0.05', 'owned_qty': '0.05'}
    parent = proofs._owned_policy(proofs.owned_entry_decision_from_rows(rows, owned, mode=mode, owner_id=owner), owned, mode=mode)
    closed = proofs.parse_instant(parent['entry_timestamp']) + timedelta(minutes=15)
    stamp = lambda seconds: (closed + timedelta(seconds=seconds)).isoformat()
    decision = {'action': 'EXIT', 'mode': mode, 'owner_id': owner, 'strategy_id': parent['card'].strategy_id,
        'release_sha': parent['release_sha'], 'observed_at': stamp(0), 'position_qty': '0.05',
        **{key: parent[key] for key in ('entry_effect_id', 'entry_client_order_id', 'entry_provider_order_id',
            'entry_price', 'entry_timestamp')}}
    sealed = store.seal(root / 'receipts.jsonl', decision, {'asset_class': 'crypto', 'symbol': 'BTC/USDC',
        'side': 'sell', 'type': 'market', 'time_in_force': 'gtc', 'qty': '0.05'})
    store.mark_started(root / 'receipts.jsonl', sealed)
    owned.update(status='closing', close_effect_id=sealed['effect_id'], close_client_order_id=sealed['client_order_id'])
    sell = {'id': 'synthetic-exit', 'client_order_id': sealed['client_order_id'], 'symbol': 'BTCUSDC',
        'side': 'sell', 'type': 'market', 'time_in_force': 'gtc', 'status': 'canceled' if terminal else 'filled', 'qty': '0.05',
        'filled_qty': '0.05', 'filled_avg_price': '210', 'submitted_at': stamp(0), 'filled_at': stamp(1)}
    flat = {**copy.deepcopy(observation), 'positions': [], 'clock': {'observed_at': stamp(2)}}
    flat['account']['id'] = closing_account
    frame = native_activity(mode, [broker, sell], end=stamp(2))
    store.reconcile_started(root / 'receipts.jsonl', lambda _: sell, on_reconciled=lambda *_:
        proofs.sell_remainder_proof_from_rows(store._rows(root / 'receipts.jsonl'), owned, sell, flat,
            mode=mode, owner_id=owner, activity_readback=frame) if terminal else
        proofs.close_fill_proof_from_rows(store._rows(root / 'receipts.jsonl'), owned, sell, flat, mode=mode, owner_id=owner))
    return frame, acquired


def closed_reuse_fixture(root, mode, path, *, bound):
    marker, buy, observation, owner = seed(root, mode, bound=bound)
    save_entry(root, marker, buy, observation, owner, mode)
    owned = {**marker, 'status': 'open', 'entry_filled_qty': '0.05', 'owned_qty': '0.05'}
    if path == 'closed_fee_only':
        current = {**copy.deepcopy(observation), 'positions': []}
        frame = native_activity(mode, [buy], end=current['clock']['observed_at'])
        frame['fees'] = [{'id': 'synthetic-saved-fee-close', 'activity_type': 'CFEE', 'order_id': buy['id'],
            'symbol': 'BTCUSD', 'qty': '-0.05', 'date': '2026-01-01',
            'created_at': current['clock']['observed_at'], 'net_amount': '0', 'status': 'executed'}]
        frame['source_receipt_id'] = 'alpaca-crypto-activities:' + proofs._digest([
            {key: value for key, value in frame.items() if key != 'source_receipt_id'}])
        store.record_native_fee_debit(root / 'receipts.jsonl', owned, current,
            activity_readback=frame, mode=mode, owner_id=owner)
        quantity = proofs.owned_quantity_state_from_rows(store._rows(root / 'receipts.jsonl'), owned,
            mode=mode, owner_id=owner)
        owned.update(status='closed', owned_qty='0', close_reason='native_fee_debit',
            fee_close_id=proofs.native_fee_debit_id(quantity['last_fee_debit']))
        broker = buy
    else:
        close_cycle(root, marker, buy, observation, owner, mode, terminal=path != 'closed_filled_sell')
        rows = store._rows(root / 'receipts.jsonl')
        plan = next(row for row in rows if row.get('receipt_type') == 'effect_intent'
            and row.get('status') == 'planned' and row.get('order', {}).get('side') == 'sell')
        saved = proofs._sell_receipt_row(rows, plan['effect_id'])
        broker = saved['broker']
        current = copy.deepcopy(saved['strategy_receipt']['account_readback'])
        owned.update(status='closing' if path == 'closing_terminal_sell' else 'closed',
            close_effect_id=plan['effect_id'], close_client_order_id=plan['client_order_id'])
    (root / 'live-owned-position.json').write_text(json.dumps(owned))
    return owned, broker, current, owner


class CryptoEntryAccountTests(unittest.TestCase):
    def test_native_account_id_survives_both_real_account_get_projections(self):
        # Returning whole fake GET objects would hide the production jq projection loss.
        for mode in ('paper', 'live'):
            for reader in ('observe', 'allocator'):
                with self.subTest(mode=mode, reader=reader), tempfile.TemporaryDirectory() as directory:
                    account = {'id': ACCOUNT_A, 'cash': '100', 'equity': '100', 'last_equity': '100', 'status': 'ACTIVE'}
                    clock = {'timestamp': START, 'observed_at': START, 'is_open': True}
                    remaining = iter([clock, [], 0, 0, {'price': '100', 'timestamp': START}, 0] if reader == 'observe'
                        else [clock, [], *([] if mode == 'paper' else [[]]), [], [], 0,
                            {'price': '100', 'timestamp': START}, [], {'tradable': False}, {}, []])
                    def run(_path, args, _env):
                        if args[:2] == ['account', 'get']:
                            result = copy.deepcopy(account)
                            if not re.search(r'(?:\{|,)\s*id\s*(?::|,|\})', args[args.index('--jq') + 1]):
                                result.pop('id')
                            return result
                        return copy.deepcopy(next(remaining))
                    with patch.dict(os.environ, {'LIFE_MANAGER_INVESTMENT_MODE': mode,
                        'ALPACA_ACCOUNT_ID': ACCOUNT_B}, clear=True), patch.object(cli, '_context', return_value={}), \
                            patch.object(cli, '_run', side_effect=run):
                        value = (cli.observe(credentials_path=Path('unused'), cli_path=Path('unused')) if reader == 'observe'
                            else cli.read_allocator_snapshot(credentials_path=Path('unused'), cli_path=Path('unused'),
                                risk_day_path=Path(directory) / 'risk-day.json'))
                    self.assertEqual(value['account'].get('id'), ACCOUNT_A)

    def entry_main(self, root, mode, *, fresh_account=ACCOUNT_A, filled=False, pre_trade_readback=None, flow_readback=None, flow_requests=None):
        native = native_run()
        raw = _snapshot(mode)
        raw['account']['id'] = ACCOUNT_A
        candidate = {**_candidate('BTC/USDC'), 'asset_class': 'crypto', 'candidate_ref': 'crypto://BTC/USDC'}
        card = candidate_cards()['alpaca-btc-5m-trend-400-v2']
        (root / 'selected-strategy.json').write_text(json.dumps({'selection': 'selected', 'report_id': 'synthetic-report',
            'strategy_id': card.strategy_id, 'release_sha': 'a' * 40, 'card': card.to_mapping(),
            'expires_at': '2099-01-01T00:00:00Z'}))
        reads = []
        provider_order = {}
        def allocator_read(**kwargs):
            if flow_requests is not None:
                flow_requests.append({'has_sink':'flow_sink' in kwargs,'read_index':len(reads)})
            if kwargs.get('flow_sink') is not None and flow_readback is not None:
                kwargs['flow_sink'].append(copy.deepcopy(flow_readback))
            value = copy.deepcopy(raw)
            if reads:
                value['account']['id'] = fresh_account
            reads.append(value)
            return value
        def observe(**_):
            value = {'mode': mode, 'paper': mode == 'paper', 'account': {**raw['account'],
                'id': fresh_account if len(reads) > 1 else ACCOUNT_A}, 'positions': [],
                'clock': {'observed_at': raw['clock']['timestamp']}, 'activities_count': 0, 'open_and_closed_orders_count': 0}
            if len(reads) > 1 and not provider_order and pre_trade_readback is not None:
                value = copy.deepcopy(pre_trade_readback)
            if provider_order and filled:
                value['positions'] = [{'symbol': 'BTCUSDC', 'qty': '0.05', 'unrealized_pl': '0'}]
                value['clock']['observed_at'] = (proofs.parse_instant(raw['clock']['timestamp']) + timedelta(seconds=2)).isoformat()
            return value
        def submit(**kwargs):
            provider_order.update(id='synthetic-main-entry', client_order_id=kwargs['client_order_id'],
                symbol='BTCUSDC', side='buy', type='market', time_in_force='gtc',
                status='filled' if filled else 'new', filled_qty='0.05' if filled else '0',
                filled_avg_price='200' if filled else None, submitted_at=raw['clock']['timestamp'],
                filled_at=(proofs.parse_instant(raw['clock']['timestamp']) + timedelta(seconds=1)).isoformat() if filled else None)
            return {'status': 'accepted'}
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'LIFE_MANAGER_INVESTMENT_MODE': mode,
                'LIFE_MANAGER_INVESTMENT_DEPLOYMENT': 'local', 'LIFE_MANAGER_INVESTMENT_OWNER_ID': 'alpaca-investment-' + mode,
                'LIFE_MANAGER_RUN_ID': f'synthetic-entry-{mode}',
                'LIFE_MANAGER_OCCURRENCE_ID': f'alpaca-investment-{mode}:synthetic-entry-{mode}',
                'LIFE_MANAGER_RELEASE_SHA': 'b' * 40,
                f'ALPACA_INVESTMENT_{mode.upper()}_STATE_DIR': str(root),
                f'ALPACA_INVESTMENT_{mode.upper()}_CREDENTIALS_FILE': str(root / 'unused')}, clear=True))
            stack.enter_context(patch.object(native, 'observe', side_effect=observe))
            stack.enter_context(patch.object(native, 'read_allocator_snapshot', side_effect=allocator_read))
            stack.enter_context(patch.object(allocator, 'evaluate', return_value={'action': 'ENTER',
                'strategy_id': card.strategy_id, 'signal_inputs': {}, 'reason': 'synthetic-entry', 'expected_cost_usd': '0.02'}))
            for name, value in (('build_candidates', [candidate]), ('read_crypto_history', {}), ('_review_status', {}),
                ('read_campaign_snapshot', {'paper': True, 'unexpected_positions': [], 'fills': [], 'positions': [], 'options': []}),
                ('deliver', {'message_id': 'synthetic-message'}), ('deliver_failure', {'status': 'delivered'}),
                ('record_source_inventory', {'coverage_state': 'gap', 'reason': 'synthetic-fixture', 'appended': False}),
                ('_retry_allowed', False)):
                stack.enter_context(patch.object(native, name, return_value=value))
            stack.enter_context(patch.object(native, 'submit_order', side_effect=submit))
            stack.enter_context(patch.object(native, 'find_order_by_client_id', side_effect=lambda **_: copy.deepcopy(provider_order)))
            stack.enter_context(patch.object(cli, '_context', side_effect=AssertionError('provider forbidden')))
            with redirect_stdout(StringIO()) as output:
                code = native.main(wake_id='synthetic-bound-entry')
        return code, store._rows(root / 'receipts.jsonl'), output.getvalue()

    def test_real_main_seals_the_native_initial_account_on_new_entry(self):
        # A field stored only in a later readback never binds the original intent.
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                code, rows, output = self.entry_main(root, mode, filled=True)
                self.assertEqual(code, 0, output)
                self.assertNotIn(ACCOUNT_A, output)
                decisions = [row['decision'] for row in rows if row.get('receipt_type') == 'decision' and row['decision'].get('action') == 'ENTER']
                self.assertEqual(len(decisions), 1)
                self.assertEqual(decisions[0].get('native_trading_account_id'), ACCOUNT_A)
                marker = json.loads((root / 'live-owned-position.json').read_text())
                saved = proofs.entry_receipt_row(rows, marker['entry_effect_id'])
                wrapper = saved['strategy_receipt']
                canonical = proofs.recorded_entry_proof_from_rows(rows, marker, saved['broker'],
                    wrapper['account_readback'], mode=mode, owner_id='alpaca-investment-' + mode)
                self.assertEqual(canonical['receipt'].get('native_trading_account_id'), ACCOUNT_A)
                frame, _ = close_cycle(root, marker, saved['broker'], wrapper['account_readback'],
                    'alpaca-investment-' + mode, mode)
                report = perf.build_crypto_performance(store._rows(root / 'receipts.jsonl'), mode=mode,
                    owner_id='alpaca-investment-' + mode,
                    activity_readbacks={row['order_id']: frame for row in frame['fills']})
                self.assertEqual(report['cycles'][0].get('native_trading_account_id'), ACCOUNT_A)

    def test_real_main_rejects_initial_a_to_fresh_b_before_sealing_or_submission(self):
        # Same cash/qty/clock cannot authorize a new intent on a different account.
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                code, rows, output = self.entry_main(Path(directory), mode, fresh_account=ACCOUNT_B)
                self.assertEqual(code, 78, output)
                self.assertFalse(any(row.get('receipt_type') == 'effect_intent' for row in rows))

    def test_saved_normal_and_filled_without_strategy_receipts_bind_account_a(self):
        # Both existing writer inputs must produce an account-bound canonical receipt.
        for mode in ('paper', 'live'):
            for backfill in (False, True):
                with self.subTest(mode=mode, backfill=backfill), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    marker, broker, observation, owner = seed(root, mode)
                    save_entry(root, marker, broker, observation, owner, mode, backfill=backfill)
                    saved = proofs.entry_receipt_row(store._rows(root / 'receipts.jsonl'), marker['entry_effect_id'])
                    actual = proofs.recorded_entry_proof_from_rows(store._rows(root / 'receipts.jsonl'), marker,
                        broker, observation, mode=mode, owner_id=owner)
                    self.assertEqual(actual['receipt'], saved['strategy_receipt']['receipt'])
                    self.assertEqual(actual['receipt'].get('native_trading_account_id'), ACCOUNT_A)

    def test_recorded_reader_rejects_current_b_and_tampered_saved_b_with_identical_financial_facts(self):
        # Saving A in a decision alone cannot protect a reader that ignores account identity.
        for mode in ('paper', 'live'):
            for swap in ('current', 'saved'):
                with self.subTest(mode=mode, swap=swap), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    marker, broker, observation, owner = seed(root, mode)
                    save_entry(root, marker, broker, observation, owner, mode)
                    rows = store._rows(root / 'receipts.jsonl')
                    current = copy.deepcopy(observation)
                    if swap == 'current':
                        current['account']['id'] = ACCOUNT_B
                    else:
                        proofs.entry_receipt_row(rows, marker['entry_effect_id'])['strategy_receipt']['account_readback']['account']['id'] = ACCOUNT_B
                    with self.assertRaises(ValueError):
                        proofs.recorded_entry_proof_from_rows(rows, marker, broker, current, mode=mode, owner_id=owner)

    def test_terminal_entry_matches_new_sealed_account_and_rejects_foreign_activity(self):
        # A content-valid activity response from B cannot complete A's partial entry.
        for mode in ('paper', 'live'):
            for account in (ACCOUNT_A, ACCOUNT_B):
                with self.subTest(mode=mode, account=account), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    marker, broker, observation, owner = seed(root, mode, partial=True)
                    frame = native_activity(mode, [broker], account=account, end=observation['clock']['observed_at'])
                    def read():
                        return proofs.entry_fill_proof_from_rows(store._rows(root / 'receipts.jsonl'), marker, broker,
                            observation, mode=mode, owner_id=owner, activity_readback=frame)
                    if account == ACCOUNT_B:
                        with self.assertRaises(ValueError):
                            read()
                    else:
                        self.assertEqual(read()['receipt'].get('native_trading_account_id'), ACCOUNT_A)

    def test_closed_cycle_retains_bound_account_and_rejects_foreign_activity(self):
        # The real cycle builder must consume the sealed/recorded binding, not infer it.
        for mode in ('paper', 'live'):
            for foreign in (False, True):
                with self.subTest(mode=mode, foreign=foreign), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    marker, broker, observation, owner = seed(root, mode)
                    save_entry(root, marker, broker, observation, owner, mode)
                    frame, _ = close_cycle(root, marker, broker, observation, owner, mode)
                    if foreign:
                        frame['native_trading_account_id'] = ACCOUNT_B
                        frame['source_receipt_id'] = 'alpaca-crypto-activities:' + proofs._digest([
                            {key: value for key, value in frame.items() if key != 'source_receipt_id'}])
                    def build():
                        return perf.build_crypto_performance(store._rows(root / 'receipts.jsonl'), mode=mode,
                            owner_id=owner, activity_readbacks={row['order_id']: frame for row in frame['fills']})
                    if foreign:
                        with self.assertRaises(ValueError):
                            build()
                    else:
                        report = build()
                        self.assertEqual(report['cycles'][0].get('native_trading_account_id'), ACCOUNT_A)
                        self.assertIsNone(report['net_pnl_usd'])
                        self.assertFalse(report['capital_expansion_allowed'])

    def test_legacy_v1_proof_and_exit_remain_unbound_despite_new_current_and_activity_ids(self):
        # A later native id must neither repair old attribution nor block old ownership.
        for mode in ('paper', 'live'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                marker, broker, observation, owner = seed(root, mode, bound=False)
                save_entry(root, marker, broker, observation, owner, mode)
                current = copy.deepcopy(observation)
                current['account']['id'] = ACCOUNT_B
                actual = proofs.recorded_entry_proof_from_rows(store._rows(root / 'receipts.jsonl'), marker,
                    broker, current, mode=mode, owner_id=owner)
                self.assertIsNone(actual['receipt'].get('native_trading_account_id'))
                owned = {**marker, 'status': 'open', 'entry_filled_qty': '0.05', 'owned_qty': '0.05'}
                with patch.dict(os.environ, {'LIFE_MANAGER_INVESTMENT_OWNER_ID': owner}, clear=True):
                    policy = position_manager.load_owned_policy(root, owned, mode=mode)
                self.assertEqual(policy['card'].strategy_id, 'alpaca-btc-5m-trend-v1')
                self.assertIsNone(policy.get('native_trading_account_id'))
                frame, _ = close_cycle(root, marker, broker, observation, owner, mode)
                report = perf.build_crypto_performance(store._rows(root / 'receipts.jsonl'), mode=mode, owner_id=owner,
                    activity_readbacks={row['order_id']: frame for row in frame['fills']})
                self.assertEqual(report['closed_cycle_count'], 1)
                self.assertIsNone(report['cycles'][0].get('native_trading_account_id'))
                decision = next(row['decision'] for row in store._rows(root / 'receipts.jsonl')
                    if row.get('receipt_type') == 'decision' and row['decision'].get('action') == 'ENTER')
                self.assertNotIn('native_trading_account_id', decision)
                self.assertIsNone(report['net_pnl_usd'])

    def test_terminal_sell_closure_checks_the_new_bound_account(self):
        # Terminal activity proof must not bypass the account check of a filled close.
        for mode in ('paper', 'live'):
            for account in (ACCOUNT_A, ACCOUNT_B):
                with self.subTest(mode=mode, account=account), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    marker, broker, observation, owner = seed(root, mode)
                    save_entry(root, marker, broker, observation, owner, mode)
                    def close():
                        return close_cycle(root, marker, broker, observation, owner, mode,
                            closing_account=account, terminal=True)
                    if account == ACCOUNT_B:
                        with self.assertRaises(ValueError): close()
                    else:
                        frame, _ = close()
                        report = perf.build_crypto_performance(store._rows(root / 'receipts.jsonl'), mode=mode,
                            owner_id=owner, activity_readbacks={row['order_id']: frame for row in frame['fills']})
                        self.assertEqual(report['cycles'][0]['native_trading_account_id'], ACCOUNT_A)

    def test_fee_only_closure_checks_current_and_activity_account(self):
        # A fee reducing the last owned quantity to zero still belongs to the same account.
        for mode in ('paper', 'live'):
            for current, activity in ((ACCOUNT_A, ACCOUNT_A), (ACCOUNT_B, ACCOUNT_A), (ACCOUNT_A, ACCOUNT_B)):
                with self.subTest(mode=mode, current=current, activity=activity), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    marker, broker, observation, owner = seed(root, mode)
                    save_entry(root, marker, broker, observation, owner, mode)
                    owned = {**marker, 'status': 'open', 'entry_filled_qty': '0.05', 'owned_qty': '0.05'}
                    flat = {**copy.deepcopy(observation), 'positions': []}
                    flat['account']['id'] = current
                    frame = native_activity(mode, [broker], account=activity, end=flat['clock']['observed_at'])
                    frame['fees'] = [{'id': 'synthetic-fee-close', 'activity_type': 'CFEE', 'order_id': broker['id'],
                        'symbol': 'BTCUSD', 'qty': '-0.05', 'date': '2026-01-01',
                        'created_at': flat['clock']['observed_at'], 'net_amount': '0', 'status': 'executed'}]
                    frame['source_receipt_id'] = 'alpaca-crypto-activities:' + proofs._digest([
                        {key: value for key, value in frame.items() if key != 'source_receipt_id'}])
                    def read():
                        return proofs.native_fee_debit_proof_from_rows(store._rows(root / 'receipts.jsonl'), owned,
                            flat, activity_readback=frame, mode=mode, owner_id=owner)
                    if current != ACCOUNT_A or activity != ACCOUNT_A:
                        with self.assertRaises(ValueError): read()
                    else:
                        self.assertEqual(read()['receipt']['remaining_owned_qty'], '0')

    def test_no_fill_account_receipt_checks_new_binding(self):
        # A failed new entry cannot close against an unrelated flat account.
        for mode in ('paper', 'live'):
            for account in (ACCOUNT_A, ACCOUNT_B):
                with self.subTest(mode=mode, account=account), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    marker, broker, observation, owner = seed(root, mode)
                    broker.update(status='canceled', filled_qty='0', filled_avg_price=None, filled_at=None)
                    observation['positions'] = []
                    observation['account']['id'] = account
                    store.reconcile_started(root / 'receipts.jsonl', lambda _: broker)
                    def read():
                        return proofs.no_fill_entry_proof_from_rows(store._rows(root / 'receipts.jsonl'), marker,
                            broker, observation, mode=mode, owner_id=owner)
                    if account == ACCOUNT_B:
                        with self.assertRaises(ValueError): read()
                    else:
                        self.assertEqual(read()['receipt']['kind'], 'owned_crypto_no_fill')

    def test_no_fill_outcome_carries_execution_identity_from_intent(self):
        env = {'LIFE_MANAGER_INVESTMENT_MODE': 'live', 'LIFE_MANAGER_INVESTMENT_DEPLOYMENT': 'local',
            'LIFE_MANAGER_INVESTMENT_OWNER_ID': 'alpaca-investment-live', 'LIFE_MANAGER_RUN_ID': 'no-fill-run',
            'LIFE_MANAGER_OCCURRENCE_ID': 'alpaca-investment-live:no-fill-run',
            'LIFE_MANAGER_RELEASE_SHA': 'b' * 40}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env, clear=True):
            root = Path(directory)
            marker, broker, observation, owner = seed(root, 'live')
            broker.update(status='canceled', filled_qty='0', filled_avg_price=None, filled_at=None)
            observation['positions'] = []
            ledger = root / 'receipts.jsonl'
            rows = store._rows(ledger)
            planned = next(row for row in rows if row.get('receipt_type') == 'effect_intent'
                and row.get('status') == 'planned' and row.get('effect_id') == marker['entry_effect_id'])
            expected_submission = {**planned['execution_identity'], 'runtime_release_sha': 'c' * 40,
                'run_id': 'no-fill-submit-run', 'occurrence_id': f'{owner}:no-fill-submit-run'}
            for row in rows:
                if row.get('receipt_type') == 'effect_intent' and row.get('status') == 'started':
                    row['submission_identity'] = expected_submission
            ledger.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))
            store.reconcile_started(root / 'receipts.jsonl', lambda _: broker)
            proof = store.record_no_fill_account_receipt(root / 'receipts.jsonl', marker, broker,
                observation, owner_id=owner, mode='live')
            rows = store._rows(root / 'receipts.jsonl')
            intent = next(row for row in rows if row.get('receipt_type') == 'effect_intent'
                and row.get('status') == 'planned' and row.get('effect_id') == marker['entry_effect_id'])
            outcome = next(row for row in rows if row.get('receipt_type') == 'outcome'
                and row.get('effect_id') == marker['entry_effect_id'] and row.get('strategy_receipt') == proof)
            self.assertEqual(outcome['execution_identity'], intent['execution_identity'])
            self.assertEqual(outcome['submission_identity'], expected_submission)

    def test_legacy_no_fill_outcome_does_not_invent_execution_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker, broker, observation, owner = seed(root, 'paper')
            broker.update(status='canceled', filled_qty='0', filled_avg_price=None, filled_at=None)
            observation['positions'] = []
            store.reconcile_started(root / 'receipts.jsonl', lambda _: broker)
            ledger = root / 'receipts.jsonl'
            rows = store._rows(ledger)
            for row in rows:
                row.pop('execution_identity', None)
            ledger.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))
            store.record_no_fill_account_receipt(ledger, marker, broker, observation,
                owner_id=owner, mode='paper')
            outcome = next(row for row in store._rows(ledger) if row.get('receipt_type') == 'outcome'
                and row.get('effect_id') == marker['entry_effect_id'] and row.get('strategy_receipt') is not None)
            self.assertIsNone(outcome.get('execution_identity'))

    def test_open_new_bound_owner_rejects_foreign_current_account_before_reuse(self):
        # The open-owner path reads historical A; its fresh quantity check must bind A too.
        for mode in ('paper', 'live'):
            for account in (ACCOUNT_A, ACCOUNT_B):
                with self.subTest(mode=mode, account=account), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    marker, broker, observation, owner = seed(root, mode)
                    save_entry(root, marker, broker, observation, owner, mode)
                    owned = {**marker, 'status': 'open', 'entry_filled_qty': '0.05', 'owned_qty': '0.05'}
                    (root / 'live-owned-position.json').write_text(json.dumps(owned))
                    current = copy.deepcopy(observation)
                    current['account']['id'] = account
                    native = native_run()
                    with patch.dict(os.environ, {'LIFE_MANAGER_INVESTMENT_MODE': mode,
                        'LIFE_MANAGER_INVESTMENT_OWNER_ID': owner}, clear=True), \
                            patch.object(native, 'find_order_by_client_id', return_value=broker), \
                            patch.object(cli, '_context', side_effect=AssertionError('provider forbidden')):
                        def read():
                            return native._sync_live_ownership(root, Path('unused'), Path('unused'), current,
                                reconcile_fees=False)
                        if account == ACCOUNT_B:
                            with self.assertRaises(ValueError): read()
                        else:
                            self.assertEqual(read()['owned_qty'], '0.05')

    def test_saved_close_reuse_checks_current_account_on_all_paths_and_preserves_legacy(self):
        # Validating saved A proves no fresh B; every close replay must bind current scope.
        missing = object()
        paths = ('closing_terminal_sell', 'closed_filled_sell', 'closed_terminal_sell', 'closed_fee_only')
        variants = (('A', ACCOUNT_A), ('B', ACCOUNT_B), ('missing', missing),
            ('null', None), ('bool', True), ('integer', 7))
        for bound in (True, False):
            for mode in ('paper', 'live'):
                for path in paths:
                    for label, account in variants if bound else (('B', ACCOUNT_B),):
                        with self.subTest(bound=bound, mode=mode, path=path, current=label), tempfile.TemporaryDirectory() as directory:
                            root = Path(directory)
                            owned, broker, current, owner = closed_reuse_fixture(root, mode, path, bound=bound)
                            if account is missing:
                                current['account'].pop('id')
                            else:
                                current['account']['id'] = account
                            marker = root / 'live-owned-position.json'
                            marker_before = marker.read_bytes()
                            ledger_before = (root / 'receipts.jsonl').read_bytes()
                            native = native_run()
                            rejected = False
                            with patch.dict(os.environ, {'LIFE_MANAGER_INVESTMENT_MODE': mode,
                                'LIFE_MANAGER_INVESTMENT_OWNER_ID': owner}, clear=True), \
                                    patch.object(native, 'find_order_by_client_id', return_value=broker), \
                                    patch.object(cli, '_context', side_effect=AssertionError('provider forbidden')):
                                try:
                                    result = native._sync_live_ownership(root, Path('unused'), Path('unused'), current,
                                        reconcile_fees=False)
                                except ValueError:
                                    rejected = True
                            self.assertEqual((root / 'receipts.jsonl').read_bytes(), ledger_before)
                            if bound and label != 'A':
                                self.assertEqual(marker.read_bytes(), marker_before, 'foreign current account must not rewrite the marker')
                                self.assertTrue(rejected, 'new-bound close must reject a different or missing current account')
                            else:
                                self.assertFalse(rejected)
                                self.assertEqual(result, {**owned, 'status': 'closed'})
                                self.assertEqual(json.loads(marker.read_text()), {**owned, 'status': 'closed'})
                                if not bound:
                                    decision = next(row['decision'] for row in store._rows(root / 'receipts.jsonl')
                                        if row.get('receipt_type') == 'decision' and row['decision'].get('action') == 'ENTER')
                                    self.assertNotIn('native_trading_account_id', decision)


if __name__ == '__main__':
    unittest.main()
