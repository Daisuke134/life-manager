"""Derived BTC cycle inventory; no submit path or capital-promotion authority."""
from __future__ import annotations

from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import json
from typing import Any

from crypto_ownership_proof import (_digest,_quantity_text,_sealed_entry_from_rows,entry_receipt_row,
    recorded_entry_proof_from_rows,recorded_no_fill_proof_from_rows,recorded_close_proof_from_rows,
    crypto_fill_activity_proof,validate_crypto_activity_snapshot,ReconciliationPending)
from effect_store import _owned_rows
from paper_performance import _atomic_json
from risk_policy import parse_instant


def _scoped_plans(rows,mode,owner):
    return [r for r in rows if r.get('receipt_type')=='effect_intent' and r.get('status')=='planned'
        and isinstance(r.get('order'),dict) and r['order'].get('asset_class')=='crypto'
        and r.get('mode')==mode and r.get('owner_id')==owner]


def _summary(cycles):
    groups={}
    for cycle in cycles:
        key=(cycle['strategy_id'],cycle['release_sha'])
        groups.setdefault(key,[]).append(cycle)
    reports=[]
    for (strategy,release),items in sorted(groups.items()):
        values=[c['execution_cashflow_usdc'] for c in items]
        reports.append({'strategy_id':strategy,'release_sha':release,'cycle_ids':[c['cycle_id'] for c in items],
            'completed_round_trips':len(items),'execution_cashflow_usdc':_quantity_text(sum((Fraction(v) for v in values),Fraction()))
                if all(v is not None for v in values) else None,'net_pnl_usd':None})
    return {'closed_cycle_count':len(cycles),'completed_round_trips':len(cycles) if len(reports)<=1 else None,
            'strategy_reports':reports}


def _fee_inventory(cycles,snapshots):
    # Existing FILL proof validates each snapshot's scope, content and paging.
    # CFEE IDs without an explicit order link are never joined by proximity.
    orders={o['provider_order_id']:(c['cycle_id'],o) for c in cycles for o in c['orders']}
    observed={};refs={};windows={}
    fill_ids={f['id'] for frame in snapshots.values() for f in frame['fills']}
    for frame in snapshots.values():
        for row in frame['fees']:
            key=row['id']
            if key in fill_ids or (key in observed and observed[key]!=row):
                raise ValueError('crypto_fee_evidence_conflict')
            observed[key]=row;refs.setdefault(key,set()).add(frame['source_receipt_id'])
            windows.setdefault(key,[]).append((parse_instant(frame['request']['after']).date(),
                parse_instant(frame['request']['until']).astimezone(timezone.utc).date()))
    attributed=[];unattributed=[]
    for key,row in sorted(observed.items()):
        item={'fee_activity_id':key,'source_receipt_ids':sorted(refs[key])}
        order_id=row.get('order_id');reason=None
        if not isinstance(order_id,str) or not order_id.strip(): reason='order_id_missing'
        elif order_id not in orders: reason='order_outside_closed_cycles'
        elif row.get('status')!='executed': reason='fee_not_executed'
        else:
            cycle_id,order=orders[order_id]
            asset='BTC' if order['side']=='buy' else 'USDC'
            symbol=row.get('symbol')
            if symbol not in {asset,asset+'USD',asset+'/USD'}: reason='received_asset_unproved'
            else:
                try:
                    qty=Decimal(str(row['qty']));net=Decimal(str(row['net_amount']))
                    if (not qty.is_finite() or qty>=0 or len(qty.as_tuple().digits)>100
                            or abs(qty.as_tuple().exponent)>100 or not net.is_finite() or net!=0
                            or Fraction(order['filled_qty'])<=0): raise ValueError
                except (ValueError,KeyError,ArithmeticError): reason='fee_amount_invalid'
                if reason is None:
                    try:
                        day=date.fromisoformat(row['date'])
                        if (day.isoformat()!=row['date'] or day<parse_instant(order['submitted_at']).astimezone(timezone.utc).date()
                                or not all(begin<=day<=end for begin,end in windows[key])): raise ValueError
                    except (ValueError,KeyError,TypeError): reason='fee_date_invalid'
                if reason is None:
                    attributed.append({**item,'cycle_id':cycle_id,'provider_order_id':order_id,
                        'asset':asset,'quantity':_quantity_text(-Fraction(qty))})
        if reason: unattributed.append({**item,'reason':reason})
    totals={}
    for item in attributed:
        key=item['provider_order_id'];totals[key]=totals.get(key,Fraction())+Fraction(item['quantity'])
    valid=[]
    for item in attributed:
        order=orders[item['provider_order_id']][1]
        received=order['filled_qty'] if order['side']=='buy' else order['quote_notional_usdc']
        reason='fee_execution_missing' if received is None else (
            'fee_amount_invalid' if totals[item['provider_order_id']]>Fraction(received) else None)
        if reason:
            unattributed.append({'fee_activity_id':item['fee_activity_id'],
                'source_receipt_ids':item['source_receipt_ids'],'reason':reason})
        else: valid.append(item)
    return {'observation_scope':'account_activity_windows','observed_fee_count':len(observed),'observed_fee_activity_ids':sorted(observed),
        'attribution_cycle_ids':[c['cycle_id'] for c in cycles],'attributed_native_fees':valid,
        'unattributed_fees':unattributed,'fee_settlement_status':'unknown',
        'fee_completeness_status':'unknown','next_action':'read_late_fee_postings_and_reconcile_unattributed_evidence'}


def build_crypto_performance(rows,*,mode,owner_id,activity_readbacks=None,fee_activity_readbacks=None):
    if mode not in {'paper','live'} or owner_id!=f'alpaca-investment-{mode}' or not isinstance(rows,list):
        raise ValueError('crypto_performance_scope_invalid')
    if any(not isinstance(r,dict) for r in rows):
        raise ValueError('crypto_performance_ledger_invalid')
    extra=activity_readbacks if activity_readbacks is not None else {}
    if not isinstance(extra,dict) or any(not isinstance(k,str) or not k for k in extra):
        raise ValueError('crypto_performance_activity_cache_invalid')
    plans=_scoped_plans(rows,mode,owner_id)
    entries=[r for r in plans if r['order'].get('side')=='buy']
    sells=[r for r in plans if r['order'].get('side')=='sell']
    cycles=[];opened=[];pending=[];no_fill=[];matched_sells=set();missing={};sources=set()
    providers={};fill_ids={};last_flat=None;fee_snapshots={};periods=[]
    for frame in (fee_activity_readbacks or []):
        validate_crypto_activity_snapshot(frame,mode=mode)
        fee_snapshots[frame['source_receipt_id']]=frame
    def consume(provider,effect):
        if provider in providers and providers[provider]!=effect:
            raise ValueError('crypto_cycle_evidence_reused')
        providers[provider]=effect
    for entry in entries:
        effect=entry.get('effect_id')
        marker={'status':'entry_pending','symbol':'BTCUSD','entry_effect_id':effect,
                'entry_client_order_id':entry.get('client_order_id'),'entry_filled_qty':'0'}
        sealed=_sealed_entry_from_rows(rows,marker,mode=mode,owner_id=owner_id)
        periods.append(sealed['decision']['observed_at'])
        saved=[r for r in rows if r.get('receipt_type')=='outcome' and r.get('effect_id')==effect
               and r.get('strategy_receipt') is not None]
        if not saved:
            pending.append({'entry_effect_id':effect,'reason':'owned_entry_receipt_missing'});continue
        row=entry_receipt_row(rows,effect);wrapper=row['strategy_receipt'];kind=wrapper['receipt']['kind']
        if kind=='owned_crypto_no_fill':
            recorded_no_fill_proof_from_rows(rows,{**marker,'status':'closed'},row['broker'],wrapper['account_readback'],mode=mode,owner_id=owner_id)
            consume(row['broker']['id'],effect)
            no_fill.append(effect);continue
        acquisition=recorded_entry_proof_from_rows(rows,marker,row['broker'],wrapper['account_readback'],mode=mode,owner_id=owner_id)
        receipt=acquisition['receipt'];owned_qty=receipt['account_owned_qty']
        if last_flat is not None and parse_instant(row['broker']['submitted_at'])<last_flat:
            raise ValueError('crypto_cycle_overlap')
        marker.update(status='closing',entry_filled_qty=receipt['entry_filled_qty'],owned_qty=owned_qty)
        orders=[(effect,row['broker'],acquisition)]
        consume(row['broker']['id'],effect)
        for fill_id in receipt.get('entry_execution',{}).get('fill_activity_ids',[]):
            if fill_id in fill_ids and fill_ids[fill_id]!=row['broker']['id']:
                raise ValueError('crypto_cycle_evidence_reused')
            fill_ids[fill_id]=row['broker']['id']
        legs=[];incomplete=False;closed=None
        for intent in sells:
            ds=[r['decision'] for r in rows if r.get('receipt_type')=='decision' and r.get('decision_id')==intent.get('decision_id')]
            if len(ds)!=1: raise ValueError('crypto_cycle_decision_invalid')
            if ds[0].get('entry_effect_id')!=effect: continue
            matched_sells.add(intent['effect_id'])
            if closed is not None: raise ValueError('crypto_cycle_after_close')
            if Decimal(str(intent['order'].get('qty')))!=Decimal(owned_qty):
                raise ValueError('crypto_cycle_quantity_invalid')
            marker.update(close_effect_id=intent['effect_id'],close_client_order_id=intent['client_order_id'],owned_qty=owned_qty)
            outs=[r for r in rows if r.get('receipt_type')=='outcome' and r.get('effect_id')==intent['effect_id']
                  and r.get('strategy_receipt') is not None]
            if not outs:
                pending.append({'entry_effect_id':effect,'close_effect_id':intent['effect_id'],'reason':'owned_close_receipt_missing'})
                incomplete=True;break
            leg=outs[-1]
            verified=recorded_close_proof_from_rows(rows,marker,leg['broker'],leg['strategy_receipt']['account_readback'],mode=mode,owner_id=owner_id)
            consume(leg['broker']['id'],intent['effect_id'])
            remainder=verified['receipt'].get('remaining_owned_qty','0')
            orders.append((intent['effect_id'],leg['broker'],verified));legs.append(verified['receipt'])
            owned_qty=remainder
            if Decimal(remainder)==0:
                closed=verified
        if incomplete: continue
        if closed is None:
            opened.append({'entry_effect_id':effect,'recorded_owned_qty':owned_qty});continue
        last_flat=parse_instant(closed['account_readback']['clock']['observed_at'])
        executions=[];cashflow=Fraction();complete=True
        for order_effect,broker,proof in orders:
            native=extra[broker['id']] if broker['id'] in extra else proof.get('activity_readback')
            facts=None
            if native is not None:
                try: facts=crypto_fill_activity_proof(native,broker,mode=mode,allow_zero=broker['side']=='sell')
                except ReconciliationPending: facts=None
                fee_snapshots[native['source_receipt_id']]=native
                known=proof['receipt'].get('entry_execution') or proof['receipt'].get('sell_execution')
                if facts is not None and known:
                    left={k:v for k,v in facts.items() if k!='source_receipt_id'}
                    right={k:v for k,v in known.items() if k!='source_receipt_id'}
                    if left!=right: raise ValueError('crypto_cycle_execution_conflict')
            if facts is None:
                complete=False;missing[broker['id']]=broker['submitted_at'];amount=None;ids=[]
            else:
                ids=facts['fill_activity_ids']
                for fill_id in ids:
                    if fill_id in fill_ids and fill_ids[fill_id]!=broker['id']:
                        raise ValueError('crypto_cycle_evidence_reused')
                    fill_ids[fill_id]=broker['id']
                amount=Fraction() if facts['filled_qty']=='0' else Fraction(facts['filled_qty'])*Fraction(
                    int(facts['weighted_avg_price_numerator']),int(facts['weighted_avg_price_denominator']))
                cashflow+=(-amount if broker['side']=='buy' else amount)
                sources.add(facts['source_receipt_id']);sources.update(ids)
            sources.add(broker['id'])
            executions.append({'effect_id':order_effect,'provider_order_id':broker['id'],'client_order_id':broker['client_order_id'],
                'side':broker['side'],'submitted_at':broker['submitted_at'],'filled_qty':broker['filled_qty'],'quote_notional_usdc':_quantity_text(amount) if amount is not None else None,
                'fill_activity_ids':ids})
        cycles.append({'cycle_id':_digest({'mode':mode,'owner_id':owner_id,'entry_effect_id':effect}),
            'owner_id':owner_id,'mode':mode,'strategy_id':receipt['strategy_id'],'release_sha':receipt['release_sha'],
            'entry_effect_id':effect,'period_start':sealed['decision']['observed_at'],
            'period_end':closed['account_readback']['clock']['observed_at'],'closed_at':closed['receipt']['exit_timestamp'],
            'entry_filled_qty':receipt['entry_filled_qty'],'entry_account_owned_qty':receipt['account_owned_qty'],
            'order_ids':[b['id'] for _,b,_ in orders],'orders':executions,
            'positive_sell_count':sum(Decimal(b['filled_qty'])>0 for _,b,_ in orders[1:]),
            'native_execution_status':'complete' if complete else 'partial','execution_cashflow_usdc':_quantity_text(cashflow) if complete else None,
            'net_pnl_usd':None})
    orphan=[r['effect_id'] for r in sells if r['effect_id'] not in matched_sells]
    unscoped=[r.get('effect_id') for r in rows if r.get('receipt_type')=='effect_intent' and r.get('status')=='planned'
        and isinstance(r.get('order'),dict) and r['order'].get('asset_class')=='crypto' and r.get('mode')==mode and r.get('owner_id')!=owner_id]
    return {'schema_version':1,'report_scope':'owned_crypto_cycles','owner_id':owner_id,'mode':mode,'paper':mode=='paper',
        'measurement_status':'partial','reason':'crypto_costs_or_fx_unknown','capital_expansion_allowed':False,
        'cycle_coverage_status':'partial' if pending or orphan or unscoped else 'complete',
        'net_pnl_usd':None,'gross_strategy_pnl_usd':None,'fees_usd':None,'slippage_usd':None,'model_cost_usd':None,'system_cost_usd':None,
        'cycles':cycles,'open_entries':opened,'pending_entries':pending,'no_fill_entry_effect_ids':no_fill,
        'unmatched_sell_effect_ids':orphan,'unscoped_effect_ids':unscoped,'missing_activity_order_ids':sorted(missing),
        'activity_requests':[{'order_id':key,'submitted_at':value} for key,value in sorted(missing.items())],
        'fee_period_start':min(periods,key=parse_instant) if periods else None,
        'source_receipt_ids':sorted(sources),'fee_evidence':_fee_inventory(cycles,fee_snapshots),**_summary(cycles)}


def _read_activity(**kwargs):
    raise ValueError('crypto_performance_activity_reader_missing')


def write_crypto_performance(state_dir,observation,*,mode,owner_id,activity_reader=None):
    if mode not in {'paper','live'} or owner_id!=f'alpaca-investment-{mode}':
        raise ValueError('crypto_performance_scope_invalid')
    state=Path(state_dir);latest=state/'performance-crypto-latest.json';phase='ledger'
    frames={};refs={};fee_refs=[];fee_checked=None;known_fees=set();known_entries=set();known_cycles=set()
    try:
        phase='cache'
        if latest.exists():
            old=json.loads(latest.read_text())
            if old.get('mode')!=mode or old.get('owner_id')!=owner_id or old.get('report_scope')!='owned_crypto_cycles':
                raise ValueError('crypto_performance_activity_cache_invalid')
            frames=old.get('activity_readbacks',{});refs=old.get('order_activity_refs',{})
            fee_checked=old.get('fee_checked_at')
            for key,target in (('known_entry_effect_ids',known_entries),('known_closed_cycle_ids',known_cycles),('known_fee_activity_ids',known_fees)):
                values=old.get(key,[])
                if not isinstance(values,list) or any(not isinstance(v,str) or not v for v in values):
                    raise ValueError('crypto_performance_activity_cache_invalid')
                target.update(values)
            for cycle in old.get('cycles',[]):
                known_entries.add(cycle['entry_effect_id']);known_cycles.add(cycle['cycle_id'])
            for entry in [*old.get('open_entries',[]),*old.get('pending_entries',[])]:
                known_entries.add(entry['entry_effect_id'])
            known_entries.update(old.get('no_fill_entry_effect_ids',[]))
            known_fees.update(old.get('fee_evidence',{}).get('observed_fee_activity_ids',[]))
            if not isinstance(frames,dict) or not isinstance(refs,dict):
                raise ValueError('crypto_performance_activity_cache_invalid')
            fee_refs=old.get('fee_activity_refs',list(refs.values()))
            if (not isinstance(fee_refs,list)
                    or any(not isinstance(ref,str) or ref not in frames for ref in [*refs.values(),*fee_refs])):
                raise ValueError('crypto_performance_activity_cache_invalid')
        phase='ledger'
        rows=_owned_rows(state/'receipts.jsonl')
        plans=_scoped_plans(rows,mode,owner_id)
        phase='history'
        if not plans:
            if latest.exists(): raise ValueError('crypto_performance_history_missing')
            return {'status':'not_applicable'}
        current_entries={r['effect_id'] for r in plans if r['order'].get('side')=='buy'}
        if not known_entries <= current_entries:
            raise ValueError('crypto_performance_history_missing')
        known_entries.update(current_entries)
        extra={key:frames[ref] for key,ref in refs.items()}
        phase='project'
        result=build_crypto_performance(rows,mode=mode,owner_id=owner_id,activity_readbacks=extra,
            fee_activity_readbacks=[frames[ref] for ref in fee_refs])
        phase='history'
        current_cycles={c['cycle_id'] for c in result['cycles']}
        if not known_cycles <= current_cycles:
            raise ValueError('crypto_performance_history_missing')
        known_cycles.update(current_cycles)
        phase='observation'
        if observation.get('mode')!=mode or observation.get('paper') is not (mode=='paper'):
            raise ValueError('crypto_performance_observation_mode_invalid')
        observed=observation['clock']['observed_at'];now=parse_instant(observed)
        if any(parse_instant(c['period_end'])>now for c in result['cycles']):
            raise ValueError('crypto_performance_time_invalid')
        if ((fee_checked is not None and parse_instant(fee_checked)>now)
                or any(validate_crypto_activity_snapshot(frames[ref],mode=mode)[1]>now for ref in fee_refs)):
            raise ValueError('crypto_performance_time_invalid')
        reader=activity_reader or _read_activity
        did_read=False
        if result['activity_requests']:
            phase='activity_readback'
            start=min(result['activity_requests'],key=lambda r:parse_instant(r['submitted_at']))['submitted_at']
            end=min(now,parse_instant(start)+timedelta(days=90)).isoformat().replace('+00:00','Z')
            incoming=reader(mode=mode,period_start=start,period_end=end)
            begin,finish=validate_crypto_activity_snapshot(incoming,mode=mode)
            if begin!=parse_instant(start) or finish!=parse_instant(end):
                raise ValueError('crypto_fee_readback_window_invalid')
            eligible=[r['order_id'] for r in result['activity_requests'] if parse_instant(r['submitted_at'])<=finish]
            trial={**extra,**{key:incoming for key in eligible}}
            refreshed=build_crypto_performance(rows,mode=mode,owner_id=owner_id,activity_readbacks=trial,
                fee_activity_readbacks=[*[frames[ref] for ref in fee_refs],incoming])
            ref=incoming['source_receipt_id'];frames[ref]=incoming
            for key in eligible: refs[key]=ref
            if ref not in fee_refs: fee_refs.append(ref)
            result=refreshed;extra=trial;fee_checked=observed;did_read=True
        through=parse_instant(result['fee_period_start']) if result['fee_period_start'] else now
        windows=sorted((parse_instant(frames[ref]['request']['after']),parse_instant(frames[ref]['request']['until'])) for ref in fee_refs)
        for begin,finish in windows:
            if begin<=through: through=max(through,finish)
        if (not did_read and through<now and through.astimezone(timezone.utc).date()<now.astimezone(timezone.utc).date()
                and fee_checked!=observed):
            phase='activity_readback'
            start=through.isoformat().replace('+00:00','Z')
            end=min(now,through+timedelta(days=90)).isoformat().replace('+00:00','Z')
            incoming=reader(mode=mode,period_start=start,period_end=end)
            begin,finish=validate_crypto_activity_snapshot(incoming,mode=mode)
            if begin!=through or finish!=parse_instant(end):
                raise ValueError('crypto_fee_readback_window_invalid')
            refreshed=build_crypto_performance(rows,mode=mode,owner_id=owner_id,activity_readbacks=extra,
                fee_activity_readbacks=[*[frames[ref] for ref in fee_refs],incoming])
            ref=incoming['source_receipt_id'];frames[ref]=incoming
            if ref not in fee_refs: fee_refs.append(ref)
            result=refreshed;through=finish;fee_checked=observed
        phase='history'
        current_fees=set(result['fee_evidence']['observed_fee_activity_ids'])
        if not known_fees<=current_fees: raise ValueError('crypto_performance_fee_history_missing')
        known_fees.update(current_fees)
        result['fee_readback_through']=through.isoformat().replace('+00:00','Z')
        phase='write'
        observed=observation['clock']['observed_at'];day=parse_instant(observed).astimezone(timezone.utc).date().isoformat()
        payload={**result,'observed_at':observed,'performance_day':day,'activity_readbacks':frames,'order_activity_refs':refs,
                 'known_entry_effect_ids':sorted(known_entries),'known_closed_cycle_ids':sorted(known_cycles),
                 'known_fee_activity_ids':sorted(known_fees),'fee_activity_refs':fee_refs,'fee_checked_at':fee_checked}
        _atomic_json(latest,payload)
        for closed_day in sorted({parse_instant(c['closed_at']).astimezone(timezone.utc).date().isoformat() for c in result['cycles']}):
            cycles=[c for c in result['cycles'] if parse_instant(c['closed_at']).astimezone(timezone.utc).date().isoformat()==closed_day]
            ids={c['cycle_id'] for c in cycles}
            fee_evidence={**result['fee_evidence'],'attribution_cycle_ids':sorted(ids),
                'attributed_native_fees':[f for f in result['fee_evidence']['attributed_native_fees'] if f['cycle_id'] in ids]}
            daily={**payload,'generated_as_of':observed,'cycles':cycles,'fee_evidence':fee_evidence,**_summary(cycles),'performance_day':closed_day,
                   'observed_at':max(c['closed_at'] for c in cycles),'report_scope':'owned_crypto_cycles_daily'}
            _atomic_json(state/f'performance-crypto-daily-{closed_day}.json',daily)
        return payload
    except Exception as error:
        # Reporting failure is visible and non-numeric; it never permits a trade
        # or suppresses the owner report and its existing financial fences.
        reason=str(error) if isinstance(error,ValueError) and str(error).startswith(('crypto_','owned_')) else 'crypto_performance_unavailable'
        result={'schema_version':1,'owner_id':owner_id,'mode':mode,'paper':mode=='paper','report_scope':'owned_crypto_cycles',
            'measurement_status':'partial','reason':reason,'error_class':type(error).__name__,'failed_phase':phase,
            'completed_round_trips':None,'net_pnl_usd':None,'capital_expansion_allowed':False,
            'activity_readbacks':frames if phase in {'ledger','history','observation','activity_readback','write'} else {},
            'order_activity_refs':refs if phase in {'ledger','history','observation','activity_readback','write'} else {},
            'known_entry_effect_ids':sorted(known_entries),'known_closed_cycle_ids':sorted(known_cycles),
            'known_fee_activity_ids':sorted(known_fees),
            'fee_activity_refs':fee_refs if phase in {'ledger','history','observation','activity_readback','write'} else [],
            'fee_checked_at':fee_checked,
            'next_action':'reconcile_cycle_proof_and_official_fill_readback'}
        _atomic_json(latest,result)
        return result
