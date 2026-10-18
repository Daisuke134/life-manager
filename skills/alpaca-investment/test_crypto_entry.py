"""Acquisition proof uses actual sealed-policy and provider/account fixtures."""
import copy
import json
import os
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import effect_store as store
import crypto_ownership_proof as proofs
import alpaca_cli
from strategy_policy import candidate_cards
from test_crypto_close import native_run


def entry_fixture(root,mode='live',*,owned_qty='0.05'):
    owner=f'alpaca-investment-{mode}'
    card=candidate_cards()['alpaca-btc-5m-trend-400-v2']
    decision={'action':'ENTER','mode':mode,'owner_id':owner,'strategy_id':card.strategy_id,
              'policy_card':card.to_mapping(),'release_sha':'a'*40,'observed_at':'2026-01-01T04:00:00Z'}
    order={'asset_class':'crypto','symbol':'BTC/USDC','side':'buy','type':'market',
           'time_in_force':'gtc','notional_usd':'10'}
    sealed=store.seal(root/'receipts.jsonl',decision,order);store.mark_started(root/'receipts.jsonl',sealed)
    marker={'status':'entry_pending','symbol':'BTCUSD','entry_effect_id':sealed['effect_id'],
            'entry_client_order_id':sealed['client_order_id'],'entry_filled_qty':'0'}
    (root/'live-owned-position.json').write_text(json.dumps(marker))
    broker={'id':'official-entry','client_order_id':sealed['client_order_id'],'status':'filled',
            'symbol':'BTCUSDC','side':'buy','type':'market','time_in_force':'gtc','filled_qty':'0.05',
            'filled_avg_price':'200','submitted_at':'2026-01-01T04:00:00Z','filled_at':'2026-01-01T04:00:01Z'}
    observation={'mode':mode,'paper':mode=='paper','account':{'cash':'0','equity':'100'},
        'positions':[{'symbol':'USDCUSD','qty':'90','unrealized_pl':'0'},
                     {'symbol':'BTCUSDC','qty':owned_qty,'avg_entry_price':'200','unrealized_pl':'0'}],
        'clock':{'observed_at':'2026-01-01T04:00:02Z'},'activities_count':0,'open_and_closed_orders_count':0}
    return marker,broker,observation,owner


class CryptoEntryTests(unittest.TestCase):
    def proof(self,root,marker,broker,observation,mode):
        reader=getattr(proofs,'entry_fill_proof_from_rows',None)
        self.assertTrue(callable(reader),'shared acquisition proof reader is required')
        return reader(store._rows(root/'receipts.jsonl'),marker,broker,observation,
                      mode=mode,owner_id=f'alpaca-investment-{mode}')

    def test_acquisition_proof_records_native_fill_and_observed_quantity_without_inventing_fees(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);marker,broker,observation,owner=entry_fixture(root,mode,owned_qty='0.049875')
                before=(root/'receipts.jsonl').read_bytes()
                proof=self.proof(root,marker,broker,observation,mode)
                self.assertEqual(proof['receipt']['kind'],'owned_crypto_entry')
                self.assertEqual(proof['receipt']['owner_id'],owner)
                self.assertEqual(proof['receipt']['account_owned_qty'],'0.049875')
                self.assertEqual(proof['receipt']['entry_filled_qty'],'0.05')
                self.assertEqual(proof['receipt']['quote_currency'],'USDC')
                self.assertIsNone(proof['receipt']['net_realized_pnl_usd'])
                self.assertNotIn('inferred_fee',proof['receipt'])
                self.assertEqual((root/'receipts.jsonl').read_bytes(),before)

    def test_filled_buy_without_account_receipt_remains_in_the_common_fence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);marker,broker,observation,_=entry_fixture(root)
            store.reconcile_started(root/'receipts.jsonl',lambda _:broker)
            self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),1)
            self.assertEqual(store.effect_state(root/'receipts.jsonl',marker['entry_effect_id']),'started')

    def test_duplicate_planned_after_completed_entry_cannot_hide_invalid_proof(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);marker,broker,observation,owner=entry_fixture(root,mode)
                ledger=root/'receipts.jsonl'
                proof=self.proof(root,marker,broker,observation,mode)
                store.reconcile_started(ledger,lambda _:broker,on_reconciled=lambda *_:proof)
                self.assertEqual(store.unresolved_intent_count(ledger),0)
                rows=store._rows(ledger)
                rows.append(copy.deepcopy(next(row for row in rows
                    if row.get('receipt_type')=='effect_intent' and row.get('status')=='planned')))
                ledger.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                with self.assertRaises(ValueError):
                    proofs.recorded_entry_proof_from_rows(rows,marker,broker,observation,
                        mode=mode,owner_id=owner)
                self.assertEqual(store.unresolved_intent_count(ledger),1)
                self.assertEqual(store.effect_state(ledger,marker['entry_effect_id']),'started')

    def test_invalid_fill_identity_quantity_time_or_account_cannot_complete_entry(self):
        variants=(('broker','id',''),('broker','client_order_id','foreign'),('broker','filled_qty',None),
            ('broker','filled_qty','NaN'),('broker','filled_qty','0'),('broker','filled_avg_price',None),
            ('broker','filled_at',None),('broker','filled_at','2026-01-01T04:01:00Z'),
            ('broker','side','sell'),('observation','mode','paper'),('observation','paper',True),
            ('observation','positions',[{'symbol':'BTCUSD','qty':'0.06'}]))
        for section,key,value in variants:
            with self.subTest(section=section,key=key),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);marker,broker,observation,_=entry_fixture(root)
                {'broker':broker,'observation':observation}[section][key]=value
                with self.assertRaises(ValueError): self.proof(root,marker,broker,observation,'live')

    def main_flow(self,mode,*,lag=False,backfill=False):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);marker,broker,observation,owner=entry_fixture(root,mode)
            if backfill: store.reconcile_started(root/'receipts.jsonl',lambda _:copy.deepcopy(broker))
            if lag: observation['positions']=observation['positions'][:1]
            raw={'account':observation['account'],'clock':{'timestamp':'2026-01-01T04:00:02Z'},
                 'risk':{'allocated_capital_usd':'10'},'positions':0 if lag else 1,'open_orders':0,
                 'crypto':[],'option_quotes':[]}
            native=native_run()
            stack.enter_context(patch.dict(os.environ,{'LIFE_MANAGER_INVESTMENT_MODE':mode,
                'LIFE_MANAGER_INVESTMENT_DEPLOYMENT':'local','LIFE_MANAGER_INVESTMENT_OWNER_ID':owner,
                f'ALPACA_INVESTMENT_{mode.upper()}_STATE_DIR':str(root),
                f'ALPACA_INVESTMENT_{mode.upper()}_CREDENTIALS_FILE':str(root/'unused')},clear=True))
            stack.enter_context(patch.object(native,'observe',side_effect=lambda **_:copy.deepcopy(observation)))
            stack.enter_context(patch.object(native,'read_allocator_snapshot',side_effect=lambda **_:copy.deepcopy(raw)))
            stack.enter_context(patch.object(native,'find_order_by_client_id',return_value=broker))
            for name,value in (('read_crypto_history',{}),('build_candidates',[]),('_review_status',{}),
                    ('read_campaign_snapshot',{'paper':True,'unexpected_positions':['BTCUSD'] if not lag else [],
                                             'fills':[],'positions':[],'options':[]}),
                    ('deliver',{'message_id':'fixture'}),('deliver_failure',{'status':'delivered'}),('_retry_allowed',False)):
                stack.enter_context(patch.object(native,name,return_value=value))
            submit=stack.enter_context(patch.object(native,'submit_order',side_effect=AssertionError('duplicate entry')))
            stack.enter_context(patch.object(alpaca_cli,'_context',side_effect=AssertionError('provider forbidden')))
            stack.enter_context(patch.object(alpaca_cli,'_run',side_effect=AssertionError('provider forbidden')))
            with redirect_stdout(StringIO()) as output: code=native.main(wake_id='entry-account-fixture')
            result=json.loads(output.getvalue().splitlines()[-1]);self.assertEqual(code,0,result)
            if lag:
                self.assertEqual(result['reconciliation']['unresolved'],1)
                self.assertEqual(result['reconciliation']['deferred'],1)
                self.assertEqual(store.unresolved_intent_count(root/'receipts.jsonl'),1)
                self.assertEqual(json.loads((root/'live-owned-position.json').read_text()),marker)
                observation['positions'].append({'symbol':'BTCUSDC','qty':'0.05','unrealized_pl':'0','avg_entry_price':'200'})
                raw['positions']=1
                with redirect_stdout(StringIO()) as output: code=native.main(wake_id='entry-account-recovered')
                self.assertEqual(code,0,output.getvalue())
            opened=json.loads((root/'live-owned-position.json').read_text())
            self.assertEqual(opened['status'],'open');self.assertEqual(opened['owned_qty'],'0.05')
            outcomes=[r for r in store._rows(root/'receipts.jsonl') if r.get('receipt_type')=='outcome']
            self.assertEqual(outcomes[-1]['strategy_receipt']['receipt']['kind'],'owned_crypto_entry')
            before=(root/'receipts.jsonl').read_bytes()
            store.reconcile_started(root/'receipts.jsonl',lambda _:self.fail('completed acquisition query'),
                                    on_reconciled=lambda *_:self.fail('completed acquisition callback'))
            self.assertEqual((root/'receipts.jsonl').read_bytes(),before)
            submit.assert_not_called()

    def test_real_main_records_entry_before_opening_ownership(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode): self.main_flow(mode)

    def test_lag_keeps_entry_pending_and_recovers_without_another_order(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode): self.main_flow(mode,lag=True)

    def test_existing_filled_buy_gets_its_missing_account_receipt(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode): self.main_flow(mode,backfill=True)


if __name__=='__main__': unittest.main()
