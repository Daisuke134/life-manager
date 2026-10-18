"""One fixed window is proved only after both activity streams reach a short page."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import alpaca_cli as cli
import crypto_ownership_proof as proofs

START='2026-01-01T04:00:00Z'
END='2026-01-02T00:00:00Z'


def activity_rows(kind,count=401):
    if kind=='FILL':
        return [{'id':f'fill-{i:05}','activity_type':'FILL','order_id':'owned-buy','symbol':'BTCUSDC',
            'side':'buy','qty':'0.0001','price':'200','transaction_time':'2026-01-01T04:00:01Z'} for i in range(count)]
    return [{'id':f'fee-{i:05}','activity_type':'CFEE','symbol':'BTCUSD','qty':'-0.000001',
        'date':'2026-01-01','price':'200','net_amount':'0','status':'executed'} for i in range(count)]


def read_chunk(kind,token=None,mode='paper',rows=None,period_start=START,period_end=END):
    reader=getattr(cli,'read_crypto_activity_page_chunk',None)
    if reader is None: return None
    records=activity_rows(kind) if rows is None else rows
    def run(_path,args,_env):
        cursor=args[args.index('--page-token')+1] if '--page-token' in args else None
        start=next((i+1 for i,r in enumerate(records) if r['id']==cursor),0) if cursor else 0
        return copy.deepcopy(records[start:start+100])
    with patch.object(cli,'_context',return_value={}),patch.object(cli,'_run',side_effect=run):
        return reader(credentials_path=Path('unused'),cli_path=Path('unused'),mode=mode,
            period_start=period_start,period_end=period_end,activity_type=kind,page_token=token)


class CryptoActivityPageTests(unittest.TestCase):
    def chunks(self,mode='paper'):
        self.assertTrue(callable(getattr(cli,'read_crypto_activity_page_chunk',None)),
            'existing bounded activity transport needs resumable chunks')
        result=[]
        for kind in ('FILL','CFEE'):
            first=read_chunk(kind,mode=mode);result.append(first)
            result.append(read_chunk(kind,first['next_page_token'],mode))
        return result

    def test_chunk_preserves_four_full_pages_and_resumes_after_exact_last_id(self):
        chunks=self.chunks()
        self.assertEqual(len(chunks[0]['pages']),4)
        self.assertEqual(sum(len(p) for p in chunks[0]['pages']),400)
        self.assertEqual(chunks[0]['pagination'],'partial')
        self.assertEqual(chunks[0]['next_page_token'],'fill-00399')
        self.assertEqual(chunks[1]['request']['page_token'],'fill-00399')
        self.assertEqual(chunks[1]['pages'][0][0]['id'],'fill-00400')
        self.assertEqual(chunks[1]['pagination'],'exhausted')
        self.assertIsNone(chunks[1]['next_page_token'])

    def test_partial_chain_never_becomes_execution_proof(self):
        chunks=self.chunks()
        progress=proofs.crypto_activity_page_progress(chunks[:1],mode='paper')
        self.assertFalse(progress['complete'])
        self.assertEqual(progress['next_kind'],'FILL')
        self.assertEqual(progress['next_page_token'],'fill-00399')
        with self.assertRaisesRegex(proofs.ReconciliationPending,'crypto_activity_pagination_pending'):
            proofs.crypto_activity_paged_snapshot(chunks[:2],mode='paper')

    def test_complete_chain_supports_large_window_without_weakening_wire_limits(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode):
                chunks=self.chunks(mode)
                snapshot=proofs.crypto_activity_paged_snapshot(chunks,mode=mode)
                self.assertEqual(snapshot['kind'],'crypto_activity_paged_window')
                self.assertEqual(len(snapshot['fills']),401);self.assertEqual(len(snapshot['fees']),401)
                broker={'id':'owned-buy','client_order_id':'client','symbol':'BTCUSDC','side':'buy',
                    'type':'market','time_in_force':'gtc','status':'filled','filled_qty':'0.0401',
                    'filled_avg_price':'200','submitted_at':START,'filled_at':'2026-01-01T04:00:01Z'}
                facts=proofs.crypto_fill_activity_proof(snapshot,broker,mode=mode)
                self.assertEqual(facts['filled_qty'],'0.0401')
                self.assertEqual(len(facts['fill_activity_ids']),401)
                self.assertEqual(snapshot['fee_settlement_status'],'unknown')
                bad=copy.deepcopy(snapshot);bad['fills'][0]['qty']='9'
                bad['source_receipt_id']='alpaca-crypto-activity-pages:'+proofs._digest([
                    {k:v for k,v in bad.items() if k!='source_receipt_id'}])
                with self.assertRaisesRegex(ValueError,'owned_crypto_activities_invalid'):
                    proofs.validate_crypto_activity_snapshot(bad,mode=mode)

    def test_token_kind_window_mode_and_duplicate_chain_are_rejected(self):
        chunks=self.chunks()
        variants=[chunks[1:],chunks[:1]+chunks[2:],chunks[:1]+chunks[:1],chunks+[chunks[-1]]]
        wrong=copy.deepcopy(chunks);wrong[1]['request']['page_token']='wrong'
        wrong[1]['source_receipt_id']='alpaca-crypto-activity-chunk:'+proofs._digest([
            {k:v for k,v in wrong[1].items() if k!='source_receipt_id'}]);variants.append(wrong)
        for frames in variants:
            with self.subTest(length=len(frames)),self.assertRaisesRegex(ValueError,'owned_crypto_activity_pages_invalid'):
                proofs.crypto_activity_page_progress(frames,mode='paper')
        with self.assertRaisesRegex(ValueError,'owned_crypto_activity_pages_invalid'):
            proofs.crypto_activity_page_progress(chunks,mode='live')

    def test_invalid_chunk_context_never_opens_credentials(self):
        self.assertTrue(callable(getattr(cli,'read_crypto_activity_page_chunk',None)))
        for changes in ({'mode':'shadow'},{'activity_type':'DIV'},{'page_token':''},{'period_end':'invalid'}):
            args=dict(credentials_path=Path('unused'),cli_path=Path('unused'),mode='paper',
                period_start=START,period_end=END,activity_type='FILL',page_token=None);args.update(changes)
            with self.subTest(changes=changes),patch.object(cli,'_context') as context,self.assertRaises(ValueError):
                cli.read_crypto_activity_page_chunk(**args)
            context.assert_not_called()
