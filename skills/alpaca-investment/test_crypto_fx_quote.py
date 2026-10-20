"""A native quote reference never fabricates FX parity or a cash conversion."""
import copy
from decimal import Inexact,Rounded,localcontext
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import alpaca_cli as cli
import crypto_ownership_proof as proofs

ASOF='2026-01-01T12:00:30Z'
OBSERVED='2026-01-01T12:00:31Z'


def seal(frame):
    frame=copy.deepcopy(frame);frame.pop('source_receipt_id',None)
    frame['source_receipt_id']='alpaca-crypto-fx-quote:'+proofs._digest(frame)
    return frame


def fixture(mode='paper',*,asof=ASOF,quoted='2026-01-01T12:00:29Z',start='2026-01-01T12:00:00Z'):
    return seal({'schema_version':1,'kind':'crypto_fx_asof_quote','mode':mode,'paper':mode=='paper',
        'symbol':'USDC/USD','base_currency':'USDC','quote_currency':'USD','asof_at':asof,'observed_at':OBSERVED,
        'request':{'symbols':'USDC/USD','start':start,'end':asof,'sort':'desc','limit':1},
        'response':{'next_page_token':'older-quotes','quotes':{'USDC/USD':[{'t':quoted,'bp':'0.9995','ap':'1.00001'}]}}})


class CryptoFxQuoteTests(unittest.TestCase):
    def proof(self,frame,mode='paper',asof=ASOF):
        reader=getattr(proofs,'crypto_fx_quote_proof',None)
        self.assertTrue(callable(reader),'FX needs the same bounded pure evidence contract')
        return reader(frame,mode=mode,asof_at=asof)

    def test_paper_and_live_reader_preserve_a_single_asof_candidate_and_an_older_cursor(self):
        for mode in ('paper','live'):
            with self.subTest(mode=mode):
                reader=getattr(cli,'read_crypto_fx_evidence',None)
                self.assertTrue(callable(reader),'reuse the pinned quotes transport for FX')
                response=fixture(mode)['response'];old=copy.deepcopy(response)
                with patch.object(cli,'_context',return_value={}) as context,patch.object(cli,'_run',return_value=response) as run:
                    frame=reader(credentials_path=Path('unused'),cli_path=Path('unused'),mode=mode,
                        asof_at=ASOF,observed_at=OBSERVED)
                self.assertEqual(context.call_args.kwargs['mode'],mode)
                args=run.call_args.args[1]
                self.assertEqual(args[:5],['data','crypto','quotes','--symbols','USDC/USD'])
                self.assertEqual(args[args.index('--sort')+1],'desc');self.assertEqual(args[args.index('--limit')+1],'1')
                self.assertEqual(frame['response']['next_page_token'],'older-quotes')
                result=self.proof(frame,mode)
                self.assertEqual(result['bid_usd_per_usdc'],'0.9995');self.assertEqual(result['ask_usd_per_usdc'],'1.00001')
                self.assertEqual(result['age_seconds'],'1');self.assertEqual(result['selection'],'latest_at_or_before')
                self.assertFalse(result['cash_conversion_proven']);self.assertEqual(response,old)

    def test_missing_or_stale_quote_stays_pending_without_a_rate_of_one(self):
        empty=fixture();empty['response']['quotes']={}
        with self.assertRaisesRegex(proofs.ReconciliationPending,'crypto_fx_quote_missing'):self.proof(seal(empty))
        stale=fixture(quoted='2026-01-01T11:59:59Z')
        with self.assertRaisesRegex(proofs.ReconciliationPending,'crypto_fx_quote_stale'):self.proof(stale)

    def test_mode_currency_request_hash_shape_price_and_future_changes_are_rejected(self):
        frames=[]
        for change in ({'mode':'live'},{'paper':False},{'schema_version':True},{'base_currency':'USD'},
                       {'symbol':'USD/USDC'},{'observed_at':'2026-01-01T12:00:29Z'}):
            frame=fixture();frame.update(change);frames.append(seal(frame))
        for key,value in (('start','2026-01-01T11:59:00Z'),('end',OBSERVED),('sort','asc'),('limit',True),('symbols','BTC/USD')):
            frame=fixture();frame['request'][key]=value;frames.append(seal(frame))
        for change in ({'bp':'0'},{'bp':'NaN'},{'ap':'0.99'},{'ap':'1e1000000'},{'t':'2026-01-01T12:00:30.000000001Z'}):
            frame=fixture();frame['response']['quotes']['USDC/USD'][0].update(change);frames.append(seal(frame))
        frame=fixture();frame['response']['quotes']['USDC/USD']*=2;frames.append(seal(frame))
        frame=fixture();frame['response']['quotes']['BTC/USD']=frame['response']['quotes'].pop('USDC/USD');frames.append(seal(frame))
        frame=fixture();frame['response'].pop('next_page_token');frames.append(seal(frame))
        frame=fixture();frame['response']['quotes']['USDC/USD'][0]['bp']='0.8';frames.append(frame)
        for i,frame in enumerate(frames):
            with self.subTest(case=i),self.assertRaisesRegex(ValueError,'crypto_fx_quote_invalid'):self.proof(frame)

    def test_nanosecond_asof_and_exact_thirty_second_boundary_do_not_round(self):
        asof='2026-01-01T12:00:30.000000001Z'
        start='2026-01-01T12:00:00.000000001Z'
        exact=fixture(asof=asof,quoted='2026-01-01T12:00:00.000000001Z',start=start)
        self.assertEqual(self.proof(exact,asof=asof)['age_seconds'],'30')
        future=fixture(asof=asof,quoted='2026-01-01T12:00:30.000000002Z',start=start)
        with self.assertRaisesRegex(ValueError,'crypto_fx_quote_invalid'):self.proof(future,asof=asof)
        stale=fixture(asof=asof,quoted='2026-01-01T12:00:00Z',start=start)
        with self.assertRaisesRegex(proofs.ReconciliationPending,'crypto_fx_quote_stale'):self.proof(stale,asof=asof)
        offset=fixture(asof='2026-01-01T21:00:30+09:00')
        self.assertEqual(self.proof(offset,asof=ASOF)['age_seconds'],'1')

    def test_invalid_input_never_loads_credentials_or_dispatches_a_query(self):
        reader=getattr(cli,'read_crypto_fx_evidence',None);self.assertTrue(callable(reader))
        with patch.object(cli,'_context',side_effect=AssertionError('context forbidden')):
            for mode,asof,observed in (('shadow',ASOF,OBSERVED),('paper','bad',OBSERVED),('paper',OBSERVED,ASOF)):
                with self.subTest(mode=mode,asof=asof),self.assertRaises(ValueError):
                    reader(credentials_path=Path('unused'),cli_path=Path('unused'),mode=mode,asof_at=asof,observed_at=observed)

    def test_exact_prices_survive_ambient_precision_and_traps(self):
        frame=fixture();frame['response']['quotes']['USDC/USD'][0].update(
            bp='0.999999999999999999999999999999',ap='1.000000000000000000000000000001')
        frame=seal(frame)
        with localcontext() as context:
            context.prec=8;context.traps[Inexact]=True;context.traps[Rounded]=True
            result=self.proof(frame)
            self.assertEqual(result['bid_usd_per_usdc'],'0.999999999999999999999999999999')
            self.assertEqual(result['ask_usd_per_usdc'],'1.000000000000000000000000000001')

    def test_request_subtraction_preserves_nanoseconds_and_exact_window_width(self):
        reader=getattr(cli,'read_crypto_fx_evidence',None);self.assertTrue(callable(reader))
        cases=[('2026-01-01T12:00:30.123456789Z','2026-01-01T12:00:00.123456789Z'),
               ('2026-01-01T21:00:30.000000001+09:00','2026-01-01T12:00:00.000000001Z'),
               ('2026-01-01T12:00:30Z','2026-01-01T12:00:00Z')]
        for asof,start in cases:
            with self.subTest(asof=asof),patch.object(cli,'_context',return_value={}),\
                 patch.object(cli,'_run',return_value=fixture(asof=asof,start=start)['response']) as run:
                frame=reader(credentials_path=Path('unused'),cli_path=Path('unused'),mode='paper',
                    asof_at=asof,observed_at=OBSERVED)
                self.assertEqual(frame['request']['start'],start)
                args=run.call_args.args[1];self.assertEqual(args[args.index('--start')+1],start)
                self.assertEqual(self.proof(fixture(asof=asof,start=start),asof=asof)['bid_usd_per_usdc'],'0.9995')
