"""Pre-BUY raw quote balances are sealed inputs, never profit authority."""
import copy
from pathlib import Path
import tempfile
import unittest

from test_crypto_entry_account import (ACCOUNT_A, ACCOUNT_B, START,
    seed)
import test_crypto_entry_account as fixtures
import crypto_ownership_proof as proofs
import effect_store as store
from test_etf_allocator import NOW


def observation(mode, stamp=START, positions=None):
    return {'mode':mode,'paper':mode=='paper',
        'account':{'id':ACCOUNT_A,'cash':'11.11','equity':'22.22'},
        'clock':{'observed_at':stamp},
        'positions':positions if positions is not None else [
            {'symbol':'USDCUSD','qty':'66.123456789012345678901234567890',
             'market_value':'65.99','side':'long'}],
        'activities_count':7,'open_and_closed_orders_count':3}


def malformed(value):
    variants=[]
    for name, path, item in (
        ('account',('account','id'),ACCOUNT_B),('mode',('mode',),'wrong'),
        ('paper',('paper',),None),('stale',('clock','observed_at'),'2025-12-31T00:00:00Z'),
        ('cash',('account','cash'),'NaN'),('equity',('account','equity'),'Infinity'),
        ('qty',('positions',0,'qty'),'NaN'),('negative',('positions',0,'qty'),'-1'),
        ('symbol',('positions',0,'symbol'),'BTCUSDC'),
        ('duplicate',('positions',),value['positions']*2),('shape',('positions',),{})):
        raw=copy.deepcopy(value);target=raw
        for key in path[:-1]:target=target[key]
        target[path[-1]]=item;variants.append((name,raw))
    return variants


class QuoteBaselineTests(unittest.TestCase):
    def test_real_main_seals_fresh_pre_submit_raw_and_not_post_buy_or_initial(self):
        for mode in ('paper','live'):
            for empty in (False,True):
                with self.subTest(mode=mode,empty=empty),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);raw=observation(mode,NOW,[] if empty else None)
                    before=copy.deepcopy(raw)
                    code,rows,output=fixtures.CryptoEntryAccountTests().entry_main(root,mode,
                        filled=True,pre_trade_readback=raw)
                    self.assertEqual(code,0,output)
                    decision=next(row['decision'] for row in rows if row.get('receipt_type')=='decision'
                        and row['decision'].get('action')=='ENTER')
                    self.assertEqual(decision.get('pre_trade_account_readback'),before)
                    self.assertEqual(raw,before)
                    saved=next(row['strategy_receipt'] for row in rows if row.get('strategy_receipt'))
                    self.assertNotEqual(saved['account_readback']['positions'],before['positions'])
                    self.assertNotIn(ACCOUNT_A,output)
                    self.assertNotIn('66.123456789012345678901234567890',output)
                    self.assertIsNone(saved['receipt']['net_realized_pnl_usd'])

    def test_real_main_rejects_bad_raw_before_seal_or_submit(self):
        for mode in ('paper','live'):
            for name,raw in malformed(observation(mode,NOW)):
                with self.subTest(mode=mode,case=name),tempfile.TemporaryDirectory() as directory:
                    code,rows,_=fixtures.CryptoEntryAccountTests().entry_main(Path(directory),mode,
                        pre_trade_readback=raw)
                    self.assertNotEqual(code,0)
                    self.assertFalse(any(row.get('receipt_type')=='effect_intent' for row in rows))
                    self.assertFalse(any(row.get('receipt_type')=='outcome' for row in rows))

    def test_shared_entry_consumer_revalidates_raw_and_submission_time(self):
        for mode in ('paper','live'):
            good=observation(mode)
            later=observation(mode,'2026-01-01T04:00:01Z')
            for name,raw in [('valid',good),('absent',None),('after_submit',later),*malformed(good)]:
                with self.subTest(mode=mode,case=name),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory)
                    marker,broker,after,owner=seed(root,mode,pre_trade_readback=raw)
                    rows=store._rows(root/'receipts.jsonl');before=copy.deepcopy(rows)
                    def read():
                        return proofs.entry_fill_proof_from_rows(rows,marker,broker,after,
                            mode=mode,owner_id=owner)
                    if name in ('valid','absent'):
                        result=read()
                        self.assertEqual(result['account_readback'],after)
                        self.assertIsNone(result['receipt']['net_realized_pnl_usd'])
                        if name=='absent':
                            self.assertNotIn('pre_trade_account_readback',rows[0]['decision'])
                    else:
                        with self.assertRaises(ValueError):read()
                    self.assertEqual(rows,before)


if __name__=='__main__':
    unittest.main()
