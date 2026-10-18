"""Derived BTC cycle inventory; no submit path or capital-promotion authority."""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import json
import os
from math import ceil
from typing import Any

from crypto_ownership_proof import (_digest,_quantity_text,_sealed_entry_from_rows,entry_receipt_row,
    recorded_entry_proof_from_rows,recorded_no_fill_proof_from_rows,recorded_close_proof_from_rows,
    owned_quantity_state_from_rows,native_fee_debit_id,crypto_fx_quote_proof,_fx_instant,_execution_number,
    crypto_fill_activity_proof,validate_crypto_activity_snapshot,combine_crypto_activity_snapshots,execution_activity_identity,native_fee_row_facts,crypto_activity_page_progress,crypto_activity_paged_snapshot,validate_crypto_activity_page_chunk,ReconciliationPending)
from effect_store import _owned_rows
from paper_performance import _atomic_json,_operating_charge_key,_operating_cost_facts,_operating_cost_facts_match
from cost_inventory import read_expected_inventory,select_expected_inventory
from risk_policy import parse_instant
from paper_operating_costs import read_readback,select_components,remember_source_evidence,summarize as summarize_operating_costs
from crypto_statement_evidence import read_statement_readbacks,statement_inventory


def _scoped_plans(rows,mode,owner):
    return [r for r in rows if r.get('receipt_type')=='effect_intent' and r.get('status')=='planned'
        and isinstance(r.get('order'),dict) and r['order'].get('asset_class')=='crypto'
        and r.get('mode')==mode and r.get('owner_id')==owner]


def _summary(cycles):
    field='cashflow_after_observed_fees_and_scoped_operating_costs_usd'
    def reference_total(items):
        values=[c.get('fx_reference',{}).get(field) for c in items]
        return _reference_amount(sum((Fraction(int(v['numerator']),int(v['denominator'])) for v in values),Fraction())) if values and all(v is not None for v in values) else None
    groups={}
    for cycle in cycles:
        key=(cycle['strategy_id'],cycle['release_sha'])
        groups.setdefault(key,[]).append(cycle)
    reports=[]
    for (strategy,release),items in sorted(groups.items()):
        values=[c['execution_cashflow_usdc'] for c in items]
        reports.append({'strategy_id':strategy,'release_sha':release,'cycle_ids':[c['cycle_id'] for c in items],
            'completed_round_trips':sum(c['positive_sell_count']>0 for c in items),'execution_cashflow_usdc':_quantity_text(sum((Fraction(v) for v in values),Fraction()))
                if all(v is not None for v in values) else None,'net_pnl_usd':None,field:reference_total(items)})
    return {'closed_cycle_count':len(cycles),'completed_round_trips':sum(c['positive_sell_count']>0 for c in cycles) if len(reports)<=1 else None,
            'strategy_reports':reports,field:reference_total(cycles)}


def _fee_inventory(cycles,snapshots):
    # Existing FILL proof validates each snapshot's scope, content and paging.
    # CFEE IDs without an explicit order link are never joined by proximity.
    snapshots={raw['source_receipt_id']:raw for frame in snapshots.values()
        for raw in (frame['segments'] if frame['schema_version']==2 else [frame])}
    orders={o['provider_order_id']:(c['cycle_id'],o) for c in cycles for o in c['orders']}
    observed={};refs={};windows={}
    fill_ids={}
    for frame in snapshots.values():
        for fill in frame['fills']:
            facts=execution_activity_identity(fill)
            if fill['id'] in fill_ids and fill_ids[fill['id']]!=facts:
                raise ValueError('crypto_cycle_execution_conflict')
            fill_ids[fill['id']]=facts
    for frame in snapshots.values():
        begin=parse_instant(frame['request']['after']);end=parse_instant(frame['request']['until'])
        for order_id,(_,order) in orders.items():
            if order['quote_notional_usdc'] is None: continue
            expected=set(order['fill_activity_ids'])
            actual={f['id'] for f in frame['fills'] if f['order_id']==order_id}
            if actual-expected:
                raise ValueError('crypto_cycle_execution_conflict')
            if (expected and begin<=parse_instant(order['submitted_at'])
                    and end>parse_instant(order['execution_observed_until']) and actual!=expected):
                raise ValueError('crypto_cycle_execution_conflict')
    for frame in snapshots.values():
        for row in frame['fees']:
            key=row['id']
            if key in fill_ids or (key in observed and observed[key]!=row):
                raise ValueError('crypto_fee_evidence_conflict')
            observed[key]=row;refs.setdefault(key,set()).add(frame['source_receipt_id'])
            windows.setdefault(key,[]).append((parse_instant(frame['request']['after']),
                parse_instant(frame['request']['until'])))
    attributed=[];unattributed=[]
    for key,row in sorted(observed.items()):
        item={'fee_activity_id':key,'source_receipt_ids':sorted(refs[key])}
        order_id=row.get('order_id');reason=None
        if not isinstance(order_id,str) or not order_id.strip(): reason='order_id_missing'
        elif order_id not in orders: reason='order_outside_closed_cycles'
        else:
            cycle_id,order=orders[order_id]
            try:
                facts=native_fee_row_facts(row,side=order['side'],submitted_at=order['submitted_at'],windows=windows[key])
                if Fraction(order['filled_qty'])<=0: raise ValueError('fee_amount_invalid')
                attributed.append({**item,'cycle_id':cycle_id,'provider_order_id':order_id,
                    'asset':facts['asset'],'quantity':_quantity_text(facts['quantity'])})
            except ValueError as error: reason=str(error)
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


def _reference_amount(value):
    return None if value is None else {'decimal':_quantity_text(value),
        'numerator':str(value.numerator),'denominator':str(value.denominator)}


def _operating_references(cycles,costs):
    for cycle in cycles:
        scoped=select_components(costs,[cycle]);ref=cycle['fx_reference']
        cashflow=ref['cashflow_after_observed_quote_fees_usd']
        model=scoped['model_cost_usd'];system=scoped['system_cost_usd']
        # BTC credited-side fees already reduce sellable quantity in the native proof.
        amount=(Fraction(int(cashflow['numerator']),int(cashflow['denominator']))-Fraction(model)-Fraction(system)
            if cashflow is not None and model is not None and system is not None
            and scoped['operating_cost_coverage']['coverage_state']=='complete' else None)
        ref.update(scoped_model_cost_usd=model,scoped_system_cost_usd=system,
            cashflow_after_observed_fees_and_scoped_operating_costs_usd=_reference_amount(amount))


def _fx_references(cycles,fees,readbacks,*,mode):
    if not isinstance(readbacks,dict):raise ValueError('crypto_fx_quote_invalid')
    quotes={};missing={};sources=set()
    for at,snapshot in readbacks.items():
        try:proof=crypto_fx_quote_proof(snapshot,mode=mode,asof_at=at)
        except ReconciliationPending:continue
        key=_fx_instant(at)
        facts=(Fraction(proof['bid_usd_per_usdc']),Fraction(proof['ask_usd_per_usdc']),_fx_instant(proof['quote_timestamp']))
        if key in quotes and quotes[key][0]!=facts:raise ValueError('crypto_fx_quote_conflict')
        quotes[key]=(facts,proof)
    for cycle in cycles:
        components=[];order_values={};cycle_missing=[]
        for order in cycle['orders']:
            total=Fraction();complete=order['quote_notional_usdc'] is not None
            for fill in order['execution_fills']:
                at=fill['transaction_time'];key=_fx_instant(at);quote=quotes.get(key)
                if quote is None:
                    missing.setdefault(key,{'asof_at':at,'mode':mode,'symbol':'USDC/USD'})
                    cycle_missing.append(fill['id']);complete=False;continue
                (bid,ask,_),proof=quote
                native=Fraction(_execution_number(fill['qty']))*Fraction(_execution_number(fill['price']));amount=native*(bid+ask)/2
                total+=amount;sources.add(proof['source_receipt_id'])
                components.append({'kind':'fill','provider_order_id':order['provider_order_id'],
                    'fill_activity_id':fill['id'],'transaction_time':at,'native_currency':'USDC',
                    'signed_native_amount':_quantity_text(-native if order['side']=='buy' else native),
                    'signed_usd_reference':_reference_amount(-amount if order['side']=='buy' else amount),
                    'fx_source_receipt_id':proof['source_receipt_id'],'fx_quote_timestamp':proof['quote_timestamp']})
            order_values[order['provider_order_id']]=total if complete else None
        cashflow=sum((-order_values[o['provider_order_id']] if o['side']=='buy' else order_values[o['provider_order_id']]
            for o in cycle['orders']),Fraction()) if all(v is not None for v in order_values.values()) else None
        totals={'BTC':[],'USDC':[]}
        for fee in fees:
            if fee['cycle_id']!=cycle['cycle_id']:continue
            order=next(o for o in cycle['orders'] if o['provider_order_id']==fee['provider_order_id'])
            gross=order_values[order['provider_order_id']]
            received=order['filled_qty'] if fee['asset']=='BTC' else order['quote_notional_usdc']
            amount=(Fraction(fee['quantity'])/Fraction(received)*gross
                if gross is not None and received is not None else None)
            totals[fee['asset']].append(amount)
            components.append({'kind':'fee_cost_basis','provider_order_id':fee['provider_order_id'],
                'fee_activity_id':fee['fee_activity_id'],'native_currency':fee['asset'],'native_quantity':fee['quantity'],
                'usd_reference':_reference_amount(amount),'fill_activity_ids':order['fill_activity_ids'],
                'fee_source_receipt_ids':fee['source_receipt_ids']})
        subtotal=lambda asset:sum(totals[asset],Fraction()) if totals[asset] and all(v is not None for v in totals[asset]) else None
        base=subtotal('BTC');quote=subtotal('USDC')
        cycle['fx_reference']={'valuation_basis':'asof_bbo_midpoint',
            'fee_basis':'credited_asset_weighted_execution_cost_basis','measurement_status':'reference_only',
            'cash_conversion_proven':False,'execution_cashflow_usd':_reference_amount(cashflow),
            'observed_base_fee_cost_basis_usd':_reference_amount(base),
            'observed_quote_fee_cost_basis_usd':_reference_amount(quote),
            'cashflow_after_observed_quote_fees_usd':_reference_amount(cashflow-quote if cashflow is not None and quote is not None else None),
            'components':components,'missing_fill_fx_ids':sorted(set(cycle_missing))}
    return [missing[key] for key in sorted(missing)],sources


def build_crypto_performance(rows,*,mode,owner_id,activity_readbacks=None,fee_activity_readbacks=None,fx_readbacks=None,operating_cost_readback=None,observed_at=None,expected_inventory=None,statement_readbacks=None):
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
            cutoff=next(i for i,r in enumerate(rows) if r is intent)
            before=owned_quantity_state_from_rows(rows,marker,mode=mode,owner_id=owner_id,upto_index=cutoff)
            owned_qty=before['owned_qty']
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
        quantity=owned_quantity_state_from_rows(rows,marker,mode=mode,owner_id=owner_id)
        fee_events=[r for r in rows if r.get('receipt_type')=='native_fee_debit' and r.get('entry_effect_id')==effect]
        for event in fee_events:
            frame=event['strategy_receipt']['activity_readback']
            fee_snapshots[frame['source_receipt_id']]=frame;sources.add(frame['source_receipt_id'])
        if closed is not None:
            close_account=closed['account_readback'];closed_at=closed['receipt']['exit_timestamp'];closure_kind='sell'
            closing_fee=closed['receipt'].get('native_fee_debit')
            if closing_fee:
                closure_kind='sell_and_native_fee' if Decimal(closed['receipt']['exit_filled_qty'])>0 else 'native_fee_debit'
                closed_at=closing_fee['observed_at']
        elif quantity['owned_qty']=='0' and quantity['last_fee_debit'] is not None:
            fee=quantity['last_fee_debit']
            matches=[r for r in fee_events if r.get('fee_debit_id')==native_fee_debit_id(fee)]
            if len(matches)!=1:raise ValueError('crypto_cycle_flat_proof_missing')
            close_account=matches[0]['strategy_receipt']['account_readback']
            closed_at=fee['observed_at'];closure_kind='native_fee_debit'
        else:
            opened.append({'entry_effect_id':effect,'recorded_owned_qty':quantity['owned_qty'],
                'post_acquisition_fee_debited_qty':quantity['debited_qty']});continue
        last_flat=parse_instant(close_account['clock']['observed_at'])
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
                complete=False;missing[broker['id']]={'submitted_at':broker['submitted_at'],
                    'readback_start':native['requested_period_end'] if native is not None else broker['submitted_at']};amount=None;ids=[]
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
            requested=next(plan['order'] for plan in plans if plan['effect_id']==order_effect)
            executions.append({'effect_id':order_effect,'provider_order_id':broker['id'],'client_order_id':broker['client_order_id'],
                'requested_notional_usd':requested.get('notional_usd'),'execution_quote_currency':'USDC',
                'side':broker['side'],'submitted_at':broker['submitted_at'],'filled_qty':broker['filled_qty'],'quote_notional_usdc':_quantity_text(amount) if amount is not None else None,
                'execution_fills':[{k:f[k] for k in ('id','qty','price','transaction_time')} for f in native['fills'] if f['id'] in ids] if facts is not None else [],
                'fill_activity_ids':ids,'execution_observed_until':native['request']['until'] if facts is not None else None})
        cycles.append({'cycle_id':_digest({'mode':mode,'owner_id':owner_id,'entry_effect_id':effect}),
            'owner_id':owner_id,'mode':mode,'strategy_id':receipt['strategy_id'],'release_sha':receipt['release_sha'],
            'entry_effect_id':effect,'period_start':sealed['decision']['observed_at'],
            'period_end':close_account['clock']['observed_at'],'closed_at':closed_at,'closure_kind':closure_kind,
            'post_acquisition_fee_debited_qty':quantity['debited_qty'],
            'entry_filled_qty':receipt['entry_filled_qty'],'entry_account_owned_qty':receipt['account_owned_qty'],
            'order_ids':[b['id'] for _,b,_ in orders],'orders':executions,
            'source_receipt_ids':sorted({b['id'] for _,b,_ in orders}|{key for order in executions for key in order['fill_activity_ids']}),
            'positive_sell_count':sum(Decimal(b['filled_qty'])>0 for _,b,_ in orders[1:]),
            'native_execution_status':'complete' if complete else 'partial','execution_cashflow_usdc':_quantity_text(cashflow) if complete else None,
            'net_pnl_usd':None})
    orphan=[r['effect_id'] for r in sells if r['effect_id'] not in matched_sells]
    unscoped=[r.get('effect_id') for r in rows if r.get('receipt_type')=='effect_intent' and r.get('status')=='planned'
        and isinstance(r.get('order'),dict) and r['order'].get('asset_class')=='crypto' and r.get('mode')==mode and r.get('owner_id')!=owner_id]
    fee_inventory=_fee_inventory(cycles,fee_snapshots)
    fee_inventory['statement_evidence']=statement_inventory(statement_readbacks if statement_readbacks is not None else [],mode=mode)
    quote_fees={}
    for fee in fee_inventory['attributed_native_fees']:
        if fee['asset']=='USDC':quote_fees.setdefault(fee['cycle_id'],[]).append(fee)
    for cycle in cycles:
        observed=quote_fees.get(cycle['cycle_id'],[])
        subtotal=sum((Fraction(f['quantity']) for f in observed),Fraction()) if observed else None
        cycle['observed_quote_fee_subtotal_usdc']=_quantity_text(subtotal) if subtotal is not None else None
        cashflow=cycle['execution_cashflow_usdc']
        cycle['cashflow_after_observed_quote_fees_usdc']=(_quantity_text(Fraction(cashflow)-subtotal)
            if cashflow is not None and subtotal is not None else None)
        cycle['quote_fee_activity_ids']=sorted(f['fee_activity_id'] for f in observed)
        cycle['quote_fee_coverage_status']='partial' if observed else 'unknown'
    fx_requests,fx_sources=_fx_references(cycles,fee_inventory['attributed_native_fees'],fx_readbacks if fx_readbacks is not None else {},mode=mode)
    sources.update(fx_sources)
    costs=summarize_operating_costs(cycles,operating_cost_readback,owner_id=owner_id,mode=mode,observed_at=observed_at,expected_inventory=expected_inventory)
    _operating_references(cycles,costs)
    return {**costs,'expected_cost_inventory':expected_inventory,'schema_version':1,'report_scope':'owned_crypto_cycles','owner_id':owner_id,'mode':mode,'paper':mode=='paper',
        'measurement_status':'partial','reason':'crypto_costs_or_fx_unknown','capital_expansion_allowed':False,
        'cycle_coverage_status':'partial' if pending or orphan or unscoped else 'complete',
        'net_pnl_usd':None,'gross_strategy_pnl_usd':None,'fees_usd':None,'slippage_usd':None,'model_cost_usd':costs.get('model_cost_usd'),'system_cost_usd':costs.get('system_cost_usd'),
        'cycles':cycles,'open_entries':opened,'pending_entries':pending,'no_fill_entry_effect_ids':no_fill,
        'unmatched_sell_effect_ids':orphan,'unscoped_effect_ids':unscoped,'missing_activity_order_ids':sorted(missing),
        'fx_requests':fx_requests,'activity_requests':[{'order_id':key,**value} for key,value in sorted(missing.items())],
        'fee_period_start':min(periods,key=parse_instant) if periods else None,
        'source_receipt_ids':sorted(sources),'fee_evidence':fee_inventory,**_summary(cycles)}


def _read_activity(**kwargs):
    raise ValueError('crypto_performance_activity_reader_missing')


def write_crypto_performance(state_dir,observation,*,mode,owner_id,activity_reader=None,activity_page_reader=None,fx_reader=None,statement_readback_dir=None):
    if mode not in {'paper','live'} or owner_id!=f'alpaca-investment-{mode}':
        raise ValueError('crypto_performance_scope_invalid')
    state=Path(state_dir);latest=state/'performance-crypto-latest.json';phase='ledger'
    frames={};refs={};fee_refs=[];fee_checked=None;known_fees=set();known_entries=set();known_cycles=set()
    window_days=90;limit_window=None;query={};page_chunks=[];page_checked=None
    fx_frames={};fx_attempts={};fx_errors=[];billing_cache=None;known_cost_components=[];source_evidence=[]
    statement_docs=[];known_statements={};statement_input_status='unavailable'
    statement_evidence=statement_inventory([],mode=mode);saved_statement_evidence=None;saved_fee_evidence={}
    try:
        phase='cache'
        if latest.exists():
            old=json.loads(latest.read_text())
            statement_docs=old.get('statement_readbacks',[])
            known_statements=old.get('known_statement_documents',{})
            saved_fee_evidence=old.get('fee_evidence',{})
            saved_statement_evidence=saved_fee_evidence.get('statement_evidence') if isinstance(saved_fee_evidence,dict) else None
            if isinstance(saved_statement_evidence,dict):statement_evidence=saved_statement_evidence
            phase='cache'
            if old.get('mode')!=mode or old.get('owner_id')!=owner_id or old.get('report_scope')!='owned_crypto_cycles':
                raise ValueError('crypto_performance_activity_cache_invalid')
            frames=old.get('activity_readbacks',{});refs=old.get('order_activity_refs',{})
            fee_checked=old.get('fee_checked_at')
            fx_frames=old.get('fx_quote_readbacks',{});fx_attempts=old.get('fx_attempted_at',{})
            billing_cache=old.get('operating_cost_readback')
            known_cost_components=old.get('known_operating_cost_components',old.get('operating_cost_components',[]))
            source_evidence=old.get('known_operating_cost_source_evidence',[])
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
            known_fees.update(saved_fee_evidence.get('observed_fee_activity_ids',[]) if isinstance(saved_fee_evidence,dict) else [])
            if not isinstance(frames,dict) or not isinstance(refs,dict):
                raise ValueError('crypto_performance_activity_cache_invalid')
            fee_refs=old.get('fee_activity_refs',list(refs.values()))
            if (not isinstance(fee_refs,list)
                    or any(not isinstance(ref,str) or ref not in frames for ref in [*refs.values(),*fee_refs])):
                raise ValueError('crypto_performance_activity_cache_invalid')
            candidate=old.get('activity_window_days',90)
            if type(candidate) is not int or not 1<=candidate<=90:
                raise ValueError('crypto_performance_activity_cache_invalid')
            window_days=candidate
            candidate=old.get('activity_limit_window')
            if candidate is not None:
                if not isinstance(candidate,dict): raise ValueError('crypto_performance_activity_cache_invalid')
                try:
                    begin,end=(parse_instant(candidate[k]) for k in ('after','until'))
                    if (begin!=begin.astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
                            or not begin<end<=begin+timedelta(days=1)): raise ValueError
                except (ValueError,TypeError,KeyError):
                    raise ValueError('crypto_performance_activity_cache_invalid')
                limit_window=candidate
            phase='activity_page_cache'
            page_chunks=old.get('activity_page_chunks',[]);page_checked=old.get('activity_page_checked_at')
            crypto_activity_page_progress(page_chunks,mode=mode)
            if page_chunks and (limit_window is None
                    or parse_instant(page_chunks[0]['requested_period_start'])!=parse_instant(limit_window['after'])
                    or parse_instant(page_chunks[0]['requested_period_end'])!=parse_instant(limit_window['until'])):
                raise ValueError('crypto_performance_activity_cache_invalid')
            phase='operating_costs'
            try:source_evidence=remember_source_evidence(source_evidence,old,owner_id=owner_id,mode=mode)
            except ValueError as error:raise ValueError('crypto_operating_cost_source_history_invalid') from error
        phase='statement_cache'
        rebuilt=statement_inventory(statement_docs,mode=mode)
        statement_evidence=rebuilt
        anchors={d['document_id']:d['document_fingerprint'] for d in statement_docs}
        if (not isinstance(saved_fee_evidence,dict)
                or (saved_statement_evidence is not None and not isinstance(saved_statement_evidence,dict))):
            raise ValueError('crypto_statement_evidence_conflict')
        if not isinstance(known_statements,dict) or known_statements!=anchors:
            raise ValueError('crypto_statement_evidence_conflict')
        fields=('documents','observations','observed_row_count','completeness_status','observation_scope')
        if saved_statement_evidence is not None and any(saved_statement_evidence.get(k)!=rebuilt[k] for k in fields):
            raise ValueError('crypto_statement_evidence_conflict')
        if statement_docs and saved_statement_evidence is None:
            raise ValueError('crypto_statement_evidence_conflict')
        phase='statement_readback'
        incoming_statements=read_statement_readbacks(
            statement_readback_dir if statement_readback_dir is not None else state/'statement-readbacks',mode=mode,
            known_metadata_hashes={d['metadata_sha256'] for d in statement_docs})
        statement_input_status='available' if incoming_statements else 'unavailable'
        merged={d['source_receipt_id']:d for d in statement_docs}
        for document in incoming_statements:
            key=document['document_id'];fingerprint=document['document_fingerprint']
            if key in known_statements and known_statements[key]!=fingerprint:
                raise ValueError('crypto_statement_evidence_conflict')
            merged[document['source_receipt_id']]=document
        candidate=list(merged.values())
        statement_evidence=statement_inventory(candidate,mode=mode)
        statement_docs=candidate
        known_statements={d['document_id']:d['document_fingerprint'] for d in statement_docs}
        phase='ledger'
        rows=_owned_rows(state/'receipts.jsonl')
        plans=_scoped_plans(rows,mode,owner_id)
        phase='history'
        if not plans and not statement_docs:
            if latest.exists(): raise ValueError('crypto_performance_history_missing')
            return {'status':'not_applicable'}
        current_entries={r['effect_id'] for r in plans if r['order'].get('side')=='buy'}
        if not known_entries <= current_entries:
            raise ValueError('crypto_performance_history_missing')
        known_entries.update(current_entries)
        extra={key:frames[ref] for key,ref in refs.items()}
        phase='project'
        result=build_crypto_performance(rows,mode=mode,owner_id=owner_id,activity_readbacks=extra,
            fee_activity_readbacks=[frames[ref] for ref in fee_refs],statement_readbacks=statement_docs)
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
        if ((page_checked is not None and parse_instant(page_checked)>now)
                or (limit_window is not None and parse_instant(limit_window['until'])>now)):
            raise ValueError('crypto_performance_time_invalid')
        reader=activity_reader or _read_activity
        def read_window(start):
            requested=parse_instant(start)
            after=requested.astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
            end=min(now,after+timedelta(days=window_days)).isoformat().replace('+00:00','Z')
            query.update(period_start=start,after=after.isoformat().replace('+00:00','Z'),until=end)
            if (limit_window is not None and after==parse_instant(limit_window['after'])
                    and parse_instant(end)>=parse_instant(limit_window['until'])):
                raise ValueError('crypto_activity_single_day_limit')
            incoming=reader(mode=mode,period_start=start,period_end=end)
            begin,finish=validate_crypto_activity_snapshot(incoming,mode=mode)
            if begin!=requested or finish!=parse_instant(end):
                raise ValueError('crypto_fee_readback_window_invalid')
            return incoming,finish
        did_read=False
        if limit_window is not None and activity_page_reader is not None:
            phase='activity_page_readback'
            progress=crypto_activity_page_progress(page_chunks,mode=mode)
            if not progress['complete']:
                if page_checked is not None and parse_instant(page_checked)==now:
                    raise ReconciliationPending('crypto_activity_pagination_pending')
                chunk=activity_page_reader(mode=mode,period_start=limit_window['after'],period_end=limit_window['until'],
                    activity_type=progress['next_kind'],page_token=progress['next_page_token'])
                begin,finish,*_=validate_crypto_activity_page_chunk(chunk,mode=mode)
                if begin!=parse_instant(limit_window['after']) or finish!=parse_instant(limit_window['until']):
                    raise ValueError('crypto_fee_readback_window_invalid')
                candidate=page_chunks+[chunk]
                progress=crypto_activity_page_progress(candidate,mode=mode)
                page_chunks=candidate;page_checked=observed
                if not progress['complete']: raise ReconciliationPending('crypto_activity_pagination_pending')
            incoming=crypto_activity_paged_snapshot(page_chunks,mode=mode)
            finish=parse_instant(incoming['requested_period_end'])
            eligible=[r['order_id'] for r in result['activity_requests'] if parse_instant(r['readback_start'])<=finish]
            trial={**extra,**{key:combine_crypto_activity_snapshots([extra[key],incoming],mode=mode)
                if key in extra else incoming for key in eligible}}
            refreshed=build_crypto_performance(rows,mode=mode,owner_id=owner_id,activity_readbacks=trial,
                fee_activity_readbacks=[*[frames[ref] for ref in fee_refs],incoming],statement_readbacks=statement_docs)
            ref=incoming['source_receipt_id'];frames[ref]=incoming
            for key in eligible:
                projected=trial[key];projected_ref=projected['source_receipt_id']
                frames[projected_ref]=projected;refs[key]=projected_ref
            if ref not in fee_refs: fee_refs.append(ref)
            result=refreshed;extra=trial;fee_checked=observed;did_read=True;limit_window=None;page_chunks=[]
        if not did_read and result['activity_requests'] and any(parse_instant(r['readback_start'])<now for r in result['activity_requests']):
            phase='activity_readback'
            start=min(result['activity_requests'],key=lambda r:parse_instant(r['readback_start']))['readback_start']
            incoming,finish=read_window(start)
            eligible=[r['order_id'] for r in result['activity_requests'] if parse_instant(r['readback_start'])<=finish]
            trial={**extra,**{key:combine_crypto_activity_snapshots([extra[key],incoming],mode=mode)
                if key in extra else incoming for key in eligible}}
            refreshed=build_crypto_performance(rows,mode=mode,owner_id=owner_id,activity_readbacks=trial,
                fee_activity_readbacks=[*[frames[ref] for ref in fee_refs],incoming],statement_readbacks=statement_docs)
            ref=incoming['source_receipt_id'];frames[ref]=incoming
            for key in eligible:
                projected=trial[key];projected_ref=projected['source_receipt_id']
                frames[projected_ref]=projected;refs[key]=projected_ref
            if ref not in fee_refs: fee_refs.append(ref)
            result=refreshed;extra=trial;fee_checked=observed;did_read=True
        through=parse_instant(result['fee_period_start']) if result['fee_period_start'] else now
        windows=sorted((parse_instant(frames[ref]['request']['after']),parse_instant(frames[ref]['request']['until'])) for ref in fee_refs)
        for begin,finish in windows:
            if begin<=through: through=max(through,finish)
        if (not did_read and through<now and through.astimezone(timezone.utc).date()<now.astimezone(timezone.utc).date()
                and (fee_checked is None or parse_instant(fee_checked)!=now)):
            phase='activity_readback'
            start=through.isoformat().replace('+00:00','Z')
            incoming,finish=read_window(start)
            refreshed=build_crypto_performance(rows,mode=mode,owner_id=owner_id,activity_readbacks=extra,
                fee_activity_readbacks=[*[frames[ref] for ref in fee_refs],incoming],statement_readbacks=statement_docs)
            ref=incoming['source_receipt_id'];frames[ref]=incoming
            if ref not in fee_refs: fee_refs.append(ref)
            result=refreshed;through=finish;fee_checked=observed
        phase='history'
        current_fees=set(result['fee_evidence']['observed_fee_activity_ids'])
        if not known_fees<=current_fees: raise ValueError('crypto_performance_fee_history_missing')
        known_fees.update(current_fees)
        result['fee_readback_through']=through.isoformat().replace('+00:00','Z')
        phase='fx_reference'
        if not isinstance(fx_frames,dict) or not isinstance(fx_attempts,dict):
            raise ValueError('crypto_fx_cache_invalid')
        for at,checked in fx_attempts.items():_fx_instant(at);_fx_instant(checked)
        if any(_fx_instant(frame['observed_at'])>_fx_instant(observed) for frame in fx_frames.values()):
            raise ValueError('crypto_fx_cache_invalid')
        if any(_fx_instant(checked)>_fx_instant(observed) for checked in fx_attempts.values()):
            raise ValueError('crypto_fx_cache_invalid')
        requests,_=_fx_references(result['cycles'],result['fee_evidence']['attributed_native_fees'],fx_frames,mode=mode)
        attempted={_fx_instant(at):_fx_instant(checked) for at,checked in fx_attempts.items()}
        eligible=[r for r in requests if attempted.get(_fx_instant(r['asof_at']))!=_fx_instant(observed)]
        for request in eligible[:2] if fx_reader is not None else []:
            at=request['asof_at'];fx_attempts[at]=observed
            try:
                incoming=fx_reader(mode=mode,asof_at=at,observed_at=observed)
                crypto_fx_quote_proof(incoming,mode=mode,asof_at=at)
                if _fx_instant(incoming['observed_at'])!=_fx_instant(observed):raise ValueError('crypto_fx_quote_invalid')
                fx_frames[at]=incoming
            except Exception as error:
                fx_errors.append({'asof_at':at,'mode':mode,'error_class':type(error).__name__,
                    'reason':'crypto_fx_readback_unavailable','retryable':True,'next_action':'retry_on_next_observation'})
        result['fx_requests'],fx_sources=_fx_references(result['cycles'],result['fee_evidence']['attributed_native_fees'],fx_frames,mode=mode)
        result['source_receipt_ids']=sorted(set(result['source_receipt_ids'])|fx_sources)
        phase='operating_costs'
        cost_scopes=[{**{k:cycle[k] for k in ('owner_id','mode','order_ids','period_start','closed_at','source_receipt_ids')},'paper':mode=='paper'} for cycle in result['cycles']]
        expected_inventory=read_expected_inventory(state,cost_scopes,owner_id=owner_id,observed_at=observed) if plans else None
        result['expected_cost_inventory']=expected_inventory
        incoming=read_readback(os.environ.get('LM_CFO_ACTUAL_COST_READBACK') or os.environ.get('LM_CFO_ACTUAL_COST')) if plans else None
        old_costs=summarize_operating_costs(result['cycles'],billing_cache,owner_id=owner_id,mode=mode,observed_at=observed,expected_inventory=expected_inventory)
        selected=incoming if incoming is not None else billing_cache
        costs=summarize_operating_costs(result['cycles'],selected,owner_id=owner_id,mode=mode,observed_at=observed,expected_inventory=expected_inventory)
        source_evidence=remember_source_evidence(source_evidence,costs,owner_id=owner_id,mode=mode)
        def charges(components):
            if not isinstance(components,list):raise ValueError('crypto_operating_cost_cache_invalid')
            facts={}
            for c in components:
                key=_operating_charge_key(c)
                value=_operating_cost_facts(c)
                if key in facts and facts[key]!=value:raise ValueError('crypto_operating_cost_cache_invalid')
                facts[key]=value
            return facts
        anchored=charges(known_cost_components)
        previous=charges(old_costs['operating_cost_components']);current=charges(costs['operating_cost_components'])
        accepts=(current==anchored if incoming is None else all(_operating_cost_facts_match(current.get(key),value) for key,value in anchored.items()))
        if accepts:
            billing_cache=selected;known_cost_components=costs['operating_cost_components']
        elif previous==anchored:
            costs={**old_costs,'operating_costs_reason':'crypto_operating_cost_history_missing',
                'next_cost_action':'reconcile_paid_cost_history_without_dropping_known_components'}
        else:
            costs={**summarize_operating_costs(result['cycles'],None,owner_id=owner_id,mode=mode,observed_at=observed),
                'operating_costs_reason':'crypto_operating_cost_cache_invalid',
                'next_cost_action':'restore_official_billing_evidence_matching_known_charge_anchors'}
        result.update(costs)
        _operating_references(result['cycles'],costs)
        result.update(_summary(result['cycles']))
        phase='write'
        observed=observation['clock']['observed_at'];day=parse_instant(observed).astimezone(timezone.utc).date().isoformat()
        payload={**result,'statement_readbacks':statement_docs,'known_statement_documents':known_statements,
                 'statement_input_status':statement_input_status,
                 'known_operating_cost_components':known_cost_components,'known_operating_cost_source_evidence':source_evidence,'operating_cost_readback':billing_cache,'fx_quote_readbacks':fx_frames,'fx_attempted_at':fx_attempts,'fx_readback_errors':fx_errors,'observed_at':observed,'performance_day':day,'activity_readbacks':frames,'order_activity_refs':refs,
                 'known_entry_effect_ids':sorted(known_entries),'known_closed_cycle_ids':sorted(known_cycles),
                 'known_fee_activity_ids':sorted(known_fees),'fee_activity_refs':fee_refs,'fee_checked_at':fee_checked,
                 'activity_window_days':window_days,'activity_limit_window':limit_window,
                 'activity_page_chunks':page_chunks,'activity_page_checked_at':page_checked}
        _atomic_json(latest,payload)
        for closed_day in sorted({parse_instant(c['closed_at']).astimezone(timezone.utc).date().isoformat() for c in result['cycles']}):
            cycles=[c for c in result['cycles'] if parse_instant(c['closed_at']).astimezone(timezone.utc).date().isoformat()==closed_day]
            ids={c['cycle_id'] for c in cycles}
            fee_evidence={**result['fee_evidence'],'attribution_cycle_ids':sorted(ids),
                'attributed_native_fees':[f for f in result['fee_evidence']['attributed_native_fees'] if f['cycle_id'] in ids]}
            daily={**{k:v for k,v in payload.items() if k!='statement_readbacks'},**select_components(result,cycles),'expected_cost_inventory':select_expected_inventory(expected_inventory,cycles),'generated_as_of':observed,'cycles':cycles,'fee_evidence':fee_evidence,**_summary(cycles),'performance_day':closed_day,
                   'observed_at':max(c['closed_at'] for c in cycles),'report_scope':'owned_crypto_cycles_daily'}
            _atomic_json(state/f'performance-crypto-daily-{closed_day}.json',daily)
        return payload
    except Exception as error:
        # Reporting failure is visible and non-numeric; it never permits a trade
        # or suppresses the owner report and its existing financial fences.
        reason=str(error) if isinstance(error,ValueError) and str(error).startswith(('crypto_','owned_')) else 'crypto_performance_unavailable'
        next_action='reconcile_cycle_proof_and_official_fill_readback'
        if reason=='crypto_activity_limit_exceeded' and phase=='activity_readback' and query:
            span=ceil((parse_instant(query['until'])-parse_instant(query['after']))/timedelta(days=1))
            window_days=max(1,span//2)
            if span<=1: limit_window={key:query[key] for key in ('after','until')}
            next_action='inspect_single_day_activity_pagination' if span<=1 else 'retry_activity_readback_with_smaller_window'
        elif reason=='crypto_activity_single_day_limit': next_action='inspect_single_day_activity_pagination'
        elif reason=='crypto_activity_pagination_pending': next_action='continue_activity_pages_from_saved_token'
        if reason.startswith('crypto_statement_'):
            statement_evidence={**statement_evidence,'status':'conflict' if reason=='crypto_statement_evidence_conflict' else 'unknown',
                'reason':reason}
            next_action='reconcile_native_statement_capture_without_replacing_known_document_evidence'
        result={'schema_version':1,'owner_id':owner_id,'mode':mode,'paper':mode=='paper','report_scope':'owned_crypto_cycles',
            'measurement_status':'partial','reason':reason,'error_class':type(error).__name__,'failed_phase':phase,
            'operating_cost_source_history_status':'invalid' if reason=='crypto_operating_cost_source_history_invalid' else 'recorded_only',
            'completed_round_trips':None,'net_pnl_usd':None,'capital_expansion_allowed':False,
            'statement_readbacks':statement_docs,'known_statement_documents':known_statements,
            'statement_input_status':statement_input_status,'fee_evidence':{'statement_evidence':statement_evidence},
            'activity_readbacks':frames if phase in {'ledger','history','observation','activity_readback','write','activity_page_readback','activity_page_cache','fx_reference','operating_costs','statement_cache','statement_readback'} else {},
            'order_activity_refs':refs if phase in {'ledger','history','observation','activity_readback','write','activity_page_readback','activity_page_cache','fx_reference','operating_costs','statement_cache','statement_readback'} else {},
            'known_entry_effect_ids':sorted(known_entries),'known_closed_cycle_ids':sorted(known_cycles),
            'known_fee_activity_ids':sorted(known_fees),
            'fee_activity_refs':fee_refs if phase in {'ledger','history','observation','activity_readback','write','activity_page_readback','activity_page_cache','fx_reference','operating_costs','statement_cache','statement_readback'} else [],
            'fee_checked_at':fee_checked,
            'known_operating_cost_components':known_cost_components,'known_operating_cost_source_evidence':source_evidence,'operating_cost_readback':billing_cache,
            'fx_quote_readbacks':fx_frames,'fx_attempted_at':fx_attempts,'fx_readback_errors':fx_errors,
            'activity_window_days':window_days,'activity_limit_window':limit_window,'activity_query':query,
            'activity_page_chunks':page_chunks,'activity_page_checked_at':page_checked,
            'retryable':next_action!='inspect_single_day_activity_pagination','next_action':next_action}
        _atomic_json(latest,result)
        return result
