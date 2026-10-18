"""Official activity arithmetic uses the actual bounded reader, never a fake fill."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import alpaca_cli as cli
import crypto_ownership_proof as proofs
from test_crypto_activity_evidence import FILL, FEE, START, END


def fixture(mode='live',side='buy'):
    fills=[{**FILL,'side':side},
           {**FILL,'id':'fill-2','side':side,'qty':'0.01','price':'203',
            'transaction_time':'2026-01-01T04:00:02Z'}]
    with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=[fills,[copy.deepcopy(FEE)]]):
        snapshot=cli.read_crypto_activity_evidence(credentials_path=Path('unused'),cli_path=Path('unused'),
            mode=mode,period_start=START,period_end=END)
    broker={'id':'official-entry','client_order_id':'sealed-client','symbol':'BTCUSDC','side':side,
        'status':'canceled','filled_qty':'0.03','filled_avg_price':None,'filled_at':None,
        'submitted_at':START,'type':'market','time_in_force':'gtc'}
    return snapshot,broker


def resign(snapshot):
    body={key:value for key,value in snapshot.items() if key!='source_receipt_id'}
    snapshot['source_receipt_id']='alpaca-crypto-activities:'+proofs._digest([body])


class CryptoFillProofTests(unittest.TestCase):
    def read(self,snapshot,broker,mode='live'):
        reader=getattr(proofs,'crypto_fill_activity_proof',None)
        self.assertTrue(callable(reader),'shared pure FILL proof reader is required')
        return reader(snapshot,broker,mode=mode)

    def test_nullable_terminal_fields_keep_native_activity_facts_without_mutating_order(self):
        for mode in ('paper','live'):
            for side in ('buy','sell'):
                with self.subTest(mode=mode,side=side):
                    snapshot,broker=fixture(mode,side);before=copy.deepcopy((snapshot,broker))
                    value=self.read(snapshot,broker,mode)
                    self.assertEqual(value['filled_qty'],'0.03')
                    self.assertEqual(value['weighted_avg_price_native'],'201')
                    self.assertEqual(value['first_execution_at'],'2026-01-01T04:00:01+00:00')
                    self.assertEqual(value['last_execution_at'],'2026-01-01T04:00:02+00:00')
                    self.assertEqual(value['provider_order_id'],broker['id'])
                    self.assertEqual(value['client_order_id'],broker['client_order_id'])
                    self.assertEqual(value['broker_status'],'canceled')
                    self.assertEqual(value['fill_activity_ids'],['fill-1','fill-2'])
                    self.assertEqual(value['quote_currency'],'USDC')
                    self.assertEqual(value['fee_attribution_status'],'unknown')
                    self.assertEqual(value['fee_settlement_status'],'unknown')
                    self.assertIsNone(value['net_realized_pnl_usd'])
                    self.assertEqual((snapshot,broker),before)

    def test_missing_or_short_fills_remain_pending(self):
        for count in (0,1):
            with self.subTest(count=count):
                snapshot,broker=fixture();snapshot['fills']=snapshot['fills'][:count];resign(snapshot)
                with self.assertRaises(proofs.ReconciliationPending): self.read(snapshot,broker)

    def test_overfilled_or_invalid_target_activity_is_rejected(self):
        variants=(('side','sell'),('symbol','ETHUSDC'),('qty','NaN'),('qty','0'),('qty','-1'),
                  ('qty','0.04'),('price','0'),('price','Infinity'),('transaction_time','2026-01-01T03:59:59Z'),
                  ('transaction_time','2026-01-02T04:00:01Z'),('transaction_time','invalid'))
        for key,value in variants:
            with self.subTest(key=key,value=value):
                snapshot,broker=fixture();snapshot['fills'][0][key]=value;resign(snapshot)
                with self.assertRaises(ValueError) as caught: self.read(snapshot,broker)
                self.assertNotIsInstance(caught.exception,proofs.ReconciliationPending)

    def test_known_order_average_and_filled_time_must_match_activity_facts(self):
        for key,value in (('filled_avg_price','202'),('filled_avg_price','NaN'),('filled_qty','NaN'),
                ('filled_qty','0'),('client_order_id',''),('symbol','ETHUSDC'),('side','foreign'),
                ('submitted_at','2026-01-01T04:00:02Z'),('type','limit'),('time_in_force','day')):
            with self.subTest(key=key,value=value):
                snapshot,broker=fixture();broker[key]=value
                with self.assertRaises(ValueError): self.read(snapshot,broker)
        for timestamp in ('2026-01-01T04:00:01Z','2026-01-02T04:00:01Z'):
            with self.subTest(timestamp=timestamp):
                snapshot,broker=fixture();broker.update(status='filled',filled_at=timestamp)
                with self.assertRaises(ValueError): self.read(snapshot,broker)
        snapshot,broker=fixture();broker.update(status='filled',filled_at='2026-01-01T04:00:02Z',filled_avg_price='201.0000001')
        self.assertEqual(self.read(snapshot,broker)['weighted_avg_price_native'],'201')

    def test_snapshot_digest_mode_window_pagination_and_unique_ids_are_required(self):
        mutations=(lambda s:s.update(mode='paper'),lambda s:s.update(paper=True),
            lambda s:s.update(schema_version=2),lambda s:s.update(pagination='partial'),
            lambda s:s['request'].update(until='2026-01-03T00:00:00Z'),
            lambda s:s['request'].update(after='2026-01-01T04:00:00Z'),
            lambda s:s.update(fee_settlement_status='complete'),
            lambda s:s['fills'][0].update(id=''),lambda s:s['fills'][0].update(order_id=None),
            lambda s:s['fills'][0].update(activity_type='CFEE'),
            lambda s:s['fees'][0].update(id=s['fills'][0]['id']),
            lambda s:s.update(fills=s['fills']*200))
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                snapshot,broker=fixture();mutate(snapshot);resign(snapshot)
                with self.assertRaises(ValueError): self.read(snapshot,broker)
        snapshot,broker=fixture();snapshot['fills'][0]['price']='999'
        with self.assertRaises(ValueError): self.read(snapshot,broker)

    def test_foreign_fills_and_unattributed_fees_are_retained_but_not_added_to_target(self):
        snapshot,broker=fixture()
        snapshot['fills'].append({**FILL,'id':'foreign-fill','order_id':'foreign-order','qty':'10'})
        resign(snapshot)
        value=self.read(snapshot,broker)
        self.assertEqual(value['filled_qty'],'0.03')
        self.assertEqual(value['fill_activity_ids'],['fill-1','fill-2'])
        self.assertNotIn('fees_usd',value)
        self.assertNotIn('inferred_fee',value)
        self.assertEqual(len(snapshot['fees']),1)


if __name__=='__main__': unittest.main()
