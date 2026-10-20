"""Read-only paid cost components; scoped subtotals never imply total cost coverage."""

from __future__ import annotations

import json
import os
from copy import deepcopy
import sys
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any


def _time(value):
    if not isinstance(value, str):
        raise ValueError("operating_cost_timestamp_invalid")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("operating_cost_timestamp_invalid")
    return result


def _cost_end(row):
    return row['closed_at'] if 'closed_at' in row else row['period_end']


def _binding(row):
    try:
        ids=row['order_ids']
        if not isinstance(ids,list) or not all(isinstance(value,str) and value for value in ids):return None
        return tuple(ids),_time(row['period_start']),_time(_cost_end(row))
    except (KeyError,TypeError,ValueError):return None


def _periods_overlap(left, right):
    return (left is not None and right is not None
        and left[1]<right[2] and right[1]<left[2])


def _execution_time_proof(join,trip,receipt,account,observations):
    if join.get('join_type')!='paid_allocation':return None
    proofs=[row for row in observations if row.get('inventory_verification')=='verified'
        and row.get('provider')==receipt['provider'] and row.get('billing_account_ref')==account
        and row.get('query_id')==join.get('query_id') and row.get('scope_id')==join.get('scope_id')
        and receipt['components'][0]['category'] in row.get('covered_categories',[]) and _binding(row)==_binding(trip)]
    if not proofs:return None
    refs={tuple(row[k] for k in ('execution_owner_id','run_id','occurrence_id')) for row in join.get('execution_refs',[])}
    occurred=_time(receipt['occurred_at'])
    return any(tuple(window[k] for k in ('execution_owner_id','run_id','occurrence_id')) in refs
        and receipt['components'][0]['category'] in window.get('covered_categories',[])
        and _time(window['started_at'])<=occurred<=_time(window['finished_at'])
        for proof in proofs for window in proof.get('execution_windows',[]))


def _has_service_period(line, join):
    return (any(key in row for row in (line,join) for key in ('service_period_start','service_period_end'))
        or join.get('attribution_basis')=='service_period')


def _service_period_proof(line, join, trip, receipt, account, observations):
    try:
        begin,end=_time(line['service_period_start']),_time(line['service_period_end'])
        return (begin<end and join.get('join_type')=='paid_allocation'
            and trip.get('scope_kind')=='owner_period' and trip.get('order_ids')==[]
            and _time(trip['period_start'])==begin and _time(_cost_end(trip))==end
            and join.get('attribution_basis')=='service_period'
            and _time(join['service_period_start'])==begin and _time(join['service_period_end'])==end
            and any(row.get('inventory_verification')=='verified' and row.get('settlement_state')=='paid_final'
                and row.get('query_id')==join.get('query_id') and row.get('scope_id')==join.get('scope_id')
                and _binding(row)==_binding(trip) and row.get('provider')==receipt['provider']
                and row.get('billing_account_ref')==account and line['category'] in row.get('covered_categories',[])
                and join.get('document_id') in row.get('document_ids',[]) for row in observations))
    except (KeyError,TypeError,ValueError):
        return False


def _calendar_contains(component, trip):
    try:
        return (trip.get('scope_kind')=='owner_period' and _binding(component)!=_binding(trip)
            and _time(trip['period_start'])<=_time(component['occurred_at'])<_time(_cost_end(trip)))
    except (KeyError,TypeError,ValueError):
        return False


def _calendar_gap_applies(gap, trip):
    if (gap.get('reason')=='operating_cost_service_period_partial_view'
            or gap.get('scope_kind')=='owner_period'):
        return False
    if _calendar_contains(gap,trip):
        return True
    parent,child=_binding(trip),_binding(gap)
    return (trip.get('scope_kind')=='owner_period' and parent!=child and _periods_overlap(child,parent))


def _calendar_covers(component, trip, observations):
    return (_calendar_contains(component,trip) and component.get('attribution_basis')=='verified_execution_window'
        and any(row.get('inventory_verification')=='verified' and row.get('settlement_state')=='paid_final'
            and _binding(row)==_binding(trip) and row.get('provider')==component.get('provider')
            and row.get('billing_account_ref')==component.get('billing_account_ref')
            and component.get('category') in row.get('covered_categories',[])
            and component.get('document_id') in row.get('document_ids',[]) for row in observations))


def select_components(summary: dict, trips) -> dict:
    """Select one economic day without moving cumulative costs onto that day's P&L."""
    requested=[_binding(trip) for trip in trips]
    pairs={key for key in requested if key is not None}
    observations=summary.get("operating_cost_query_observations", [])
    components = [row for row in summary.get("operating_cost_components", [])
                  if _binding(row) in pairs or any(_calendar_covers(row,trip,observations) for trip in trips)]
    coverages=[row for row in summary.get('operating_cost_scope_coverages',[]) if _binding(row) in pairs]
    component_gaps=[row for row in summary.get('operating_cost_component_gaps',[])
        if _binding(row) in pairs or any(_calendar_gap_applies(row,trip) for trip in trips)]
    component_gaps.extend(row for row in summary.get('operating_cost_scope_coverages',[])
        if row.get('coverage_state')!='complete' and row not in component_gaps and any(_calendar_gap_applies(row,trip) for trip in trips))
    for component in components:
        if (component.get('attribution_basis') not in {'verified_execution_window','verified_service_period'}
                and any(_binding(row)==_binding(component) and row.get('coverage_state')=='complete' for row in coverages)
                and not any(g.get('receipt_id')==component['receipt_id'] and _binding(g)==_binding(component) for g in component_gaps)):
            component_gaps.append({**{k:component[k] for k in ('receipt_id','provider','order_ids','period_start','period_end')},
                'reason':'operating_cost_paid_attribution_unverified'})
    complete=not component_gaps and bool(requested) and len(pairs)==len(requested) and all(
        len([row for row in coverages if _binding(row)==key])==1
        and next(row for row in coverages if _binding(row)==key)['coverage_state']=='complete' for key in pairs)
    coverage_reason=None if complete else component_gaps[0]['reason'] if component_gaps else next((row.get('reason') for row in coverages if row.get('coverage_state')!='complete'),
        'cost_query_scope_missing' if summary.get('operating_cost_scope_coverages') else 'source_inventory_unverified')
    def subtotal(categories):
        amounts = [Decimal(row["amount_usd"]) for row in components if row["category"] in categories]
        if not amounts:
            return None
        with localcontext(Context()) as context:
            context.prec = max(max(1,amount.adjusted()+1) for amount in amounts) + max(max(0,-amount.as_tuple().exponent) for amount in amounts) + len(str(len(amounts))) + 1
            return format(sum(amounts, Decimal("0")), "f")
    return {
        "model_cost_usd":(subtotal({'model_cost'}) or '0') if complete else None,
        "system_cost_usd":(subtotal({'tool_cost','browser_cost','infra_cost'}) or '0') if complete else None,
        "operating_costs_status": "complete" if complete else "partial" if components else "unknown",
        "operating_costs_reason": ("confirmed_scoped_costs" if complete else "scoped_paid_components_only" if components
                                   else "no_scoped_paid_components_for_day" if summary.get("operating_cost_components")
                                   else summary.get("operating_costs_reason", "no_scoped_paid_components")),
        "operating_costs_observed_at": summary.get("operating_costs_observed_at"),
        "operating_cost_query_observations": [row for row in summary.get("operating_cost_query_observations", [])
                                              if _binding(row) in pairs],
        "operating_cost_query_rejections":[row for row in summary.get('operating_cost_query_rejections',[]) if _binding(row) in pairs],
        "operating_cost_component_gaps":component_gaps,
        "operating_cost_scope_coverages":coverages,
        "operating_cost_coverage": {"coverage_state": "complete" if complete else "gap", "reason": coverage_reason},
        "operating_cost_components": components,
        "operating_cost_source_receipt_ids": [row["receipt_id"] for row in components],
        "verified_model_cost_subtotal_usd": subtotal({"model_cost"}),
        "verified_system_cost_subtotal_usd": subtotal({"tool_cost", "browser_cost", "infra_cost"}),
    }


def remember_source_evidence(known, summary, *, owner_id, mode):
    """Keep recorded scope evidence; never use it to authorize current money."""
    field='known_operating_cost_source_evidence'
    def ids(values, required=False):
        return (isinstance(values,list) and (bool(values) or not required)
            and all(isinstance(value,str) and value for value in values) and len(values)==len(set(values)))
    def validate(record):
        try:
            scope=record['scope'];queries=record['queries'];binding=_binding(scope)
            if (record.get('kind')!='historical_source_coverage' or record.get('current_cost_authority') is not False
                    or binding is None or not binding[1]<binding[2]<=_time(record['observed_at'])
                    or scope.get('owner_id')!=owner_id or scope.get('mode')!=mode or scope.get('paper') is not (mode=='paper')
                    or scope.get('scope_kind') not in {'order_pair','owner_period'}
                    or bool(binding[0]) != (scope.get('scope_kind')=='order_pair') or not ids(scope.get('order_ids'))
                    or scope.get('coverage_state')!='complete' or not ids(scope.get('evidence_refs'),True)
                    or not ids(scope.get('source_receipt_ids'),True) or not isinstance(queries,list) or not queries):
                raise ValueError
            categories=set()
            for query in queries:
                if (query.get('inventory_verification')!='verified' or _binding(query)!=binding
                        or query.get('settlement_state') not in {'paid_final','no_charge_final'}
                        or not isinstance(query.get('provider'),str) or not query['provider']
                        or not isinstance(query.get('billing_account_ref'),str) or not query['billing_account_ref']
                        or not ids(query.get('covered_categories'),True) or not ids(query.get('evidence_refs'),True)
                        or not ids(query.get('document_ids')) or _time(query['observed_at'])>_time(record['observed_at'])):
                    raise ValueError
                if (not isinstance(query.get('query_id'),str) or not query['query_id']
                        or not isinstance(scope.get('scope_id'),str) or not scope['scope_id']
                        or query.get('scope_id')!=scope['scope_id'] or query.get('scope_kind')!=scope['scope_kind']
                        or not _time(query['window_start'])<=binding[1]<binding[2]<=_time(query['window_end'])
                            <=_time(query['finalized_through'])<=_time(query['observed_at'])
                        or (query['settlement_state']=='no_charge_final') != (query['document_ids']==[])
                        or not isinstance(query.get('execution_windows'),list) or not query['execution_windows']):
                    raise ValueError
                for window in query['execution_windows']:
                    if (not isinstance(window,dict) or any(not isinstance(window.get(key),str) or not window[key]
                            for key in ('execution_owner_id','run_id','occurrence_id'))
                            or not _time(window['started_at'])<=_time(window['finished_at'])
                            or not ids(window.get('covered_categories'),True)
                            or not set(window['covered_categories'])<=set(query['covered_categories'])):
                        raise ValueError
                categories.update(query['covered_categories'])
            if categories!={'model_cost','tool_cost','browser_cost','infra_cost'}:raise ValueError
        except (KeyError,TypeError,AttributeError,ValueError) as error:
            raise ValueError('operating_cost_source_history_invalid') from error
    if mode not in {'paper','live'} or owner_id!='alpaca-investment-'+mode:
        raise ValueError('operating_cost_source_history_invalid')
    current=summary.get(field,[])
    if not isinstance(known,list) or not isinstance(current,list):raise ValueError('operating_cost_source_history_invalid')
    result=[]
    for record in [*known,*current]:
        validate(record)
        if record not in result:result.append(deepcopy(record))
    for scope in summary.get('operating_cost_scope_coverages',[]):
        if scope.get('coverage_state')!='complete':continue
        queries=[query for query in summary.get('operating_cost_query_observations',[])
            if query.get('inventory_verification')=='verified' and _binding(query)==_binding(scope)]
        if not queries:continue
        record={'kind':'historical_source_coverage','current_cost_authority':False,
            'scope':scope,'queries':queries,'observed_at':summary.get('operating_costs_observed_at')}
        validate(record)
        if record not in result:result.append(deepcopy(record))
    return result


def read_readback(path: str | None) -> Any:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {"read_error": "operating_cost_readback_unavailable"}


def read_owner_period_costs(state, *, observed_at, owner_id, mode, previous=None, economic_scopes=()):
    """Read the last completed UTC day's operating costs without a trade or write."""
    result={'schema_version':1,'report_scope':'owner_period_operating_costs','owner_id':owner_id,
        'mode':mode,'paper':mode=='paper','observed_at':observed_at,'period_timezone':'UTC',
        'model_cost_usd':None,'system_cost_usd':None,'net_pnl_usd':None,'capital_expansion_allowed':False}
    known=[];paid_anchors=[]
    try:
        if mode not in {'paper','live'} or owner_id!='alpaca-investment-'+mode:
            raise ValueError('owner_period_costs_scope_invalid')
        from paper_performance import _operating_identity_keys,_operating_cost_facts,_operating_cost_facts_match
        end=_time(observed_at).astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
        scope={'scope_kind':'owner_period','owner_id':owner_id,'mode':mode,'paper':mode=='paper',
            'order_ids':[],'period_start':(end-timedelta(days=1)).isoformat(),'period_end':end.isoformat(),
            'source_receipt_ids':[]}
        result.update(period_start=scope['period_start'],period_end=scope['period_end'])
        if previous is not None:
            if not isinstance(previous,dict) or 'read_error' in previous:raise ValueError('owner_period_costs_history_unavailable')
            if previous.get('owner_id')!=owner_id or previous.get('mode')!=mode or previous.get('paper') is not (mode=='paper'):
                raise ValueError('owner_period_costs_scope_invalid')
            known=remember_source_evidence([],previous,owner_id=owner_id,mode=mode)
            paid_anchors=deepcopy(previous.get('known_operating_cost_components',previous.get('operating_cost_components',[])))
            if not isinstance(paid_anchors,list):raise ValueError('owner_period_costs_history_invalid')
            for anchor in paid_anchors:
                _operating_identity_keys(anchor);_operating_cost_facts(anchor);_time(anchor['occurred_at'])
        scopes=[]
        for economic in economic_scopes:
            if (isinstance(economic,dict) and economic.get('scope_kind','order_pair')=='order_pair'
                    and economic.get('owner_id')==owner_id and economic.get('mode')==mode
                    and economic.get('paper',mode=='paper') is (mode=='paper') and _binding(economic) is not None
                    and not any(_binding(economic)==_binding(row) for row in scopes)):
                scopes.append(deepcopy(economic))
        from cost_inventory import read_expected_inventory
        inventory=read_expected_inventory(state,[*scopes,scope],owner_id=owner_id,observed_at=observed_at)
        matching=[row for row in inventory.get('scopes',[]) if _binding(row)==_binding(scope)
            and row.get('owner_id')==owner_id and row.get('mode')==mode]
        if len(matching)==1:scope={**scope,'source_receipt_ids':list(matching[0]['source_receipt_ids'])}
        result.update(cost_scope=scope,source_receipt_ids=scope['source_receipt_ids'],expected_cost_inventory=inventory)
        payload=read_readback(os.environ.get('LM_CFO_ACTUAL_COST_READBACK') or os.environ.get('LM_CFO_ACTUAL_COST'))
        summary=summarize([*scopes,scope],payload,owner_id=owner_id,mode=mode,observed_at=observed_at,expected_inventory=inventory)
        known=remember_source_evidence(known,summary,owner_id=owner_id,mode=mode)
        current=select_components(summary,[scope])
        old_anchors=deepcopy(paid_anchors);conflicts=[]
        def matches(row,anchor):
            return (_operating_cost_facts_match(_operating_cost_facts(row),_operating_cost_facts(anchor))
                and _time(row['occurred_at'])==_time(anchor['occurred_at']))
        for row in current['operating_cost_components']:
            keys=_operating_identity_keys(row)
            hits=[index for index,anchor in enumerate(paid_anchors) if keys&_operating_identity_keys(anchor)]
            if any(not matches(row,paid_anchors[index]) for index in hits):
                conflicts.extend(paid_anchors[index] for index in hits)
                continue
            for index in hits:keys|=_operating_identity_keys(paid_anchors[index])
            anchored={**deepcopy(row),'identity_aliases':[list(key) for key in sorted(keys)]}
            at=min(hits) if hits else len(paid_anchors)
            paid_anchors=[anchor for index,anchor in enumerate(paid_anchors) if index not in hits]
            paid_anchors.insert(at,anchored)
        for anchor in old_anchors:
            if 'service_period_start' in anchor or 'service_period_end' in anchor:
                relevant=_time(anchor['service_period_start'])<end and end-timedelta(days=1)<_time(anchor['service_period_end'])
            else:relevant=_binding(anchor)==_binding(scope) or end-timedelta(days=1)<=_time(anchor['occurred_at'])<end
            if relevant and not any(_operating_identity_keys(row)&_operating_identity_keys(anchor) and matches(row,anchor)
                    for row in current['operating_cost_components']):conflicts.append(anchor)
        if conflicts:
            gaps=[{'receipt_id':anchor['receipt_id'],'provider':anchor['provider'],'order_ids':scope['order_ids'],
                'period_start':scope['period_start'],'period_end':scope['period_end'],'reason':'owner_period_paid_history_missing'}
                for anchor in conflicts]
            blocked=set().union(*(_operating_identity_keys(anchor) for anchor in conflicts))
            current=select_components({**summary,'operating_cost_component_gaps':summary.get('operating_cost_component_gaps',[])+gaps,
                'operating_cost_components':[row for row in summary['operating_cost_components']
                    if not blocked&_operating_identity_keys(row)]},[scope])
            current['operating_costs_reason']='owner_period_paid_history_missing'
        return {**result,**current,'known_operating_cost_source_evidence':known,'known_operating_cost_components':paid_anchors}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,ArithmeticError) as error:
        return {**result,'operating_costs_status':'unknown','operating_costs_reason':'owner_period_costs_unavailable',
            'operating_cost_coverage':{'coverage_state':'gap','reason':'owner_period_costs_unavailable'},
            'error_class':type(error).__name__,'known_operating_cost_source_evidence':known,'known_operating_cost_components':paid_anchors}


def summarize(trips, payload, *, owner_id: str, observed_at: str, expected_inventory=None, mode="paper") -> dict:
    requested=list(trips)
    trips=list(requested)
    summary = {"operating_cost_components": [], "operating_costs_observed_at": None,
               "operating_costs_reason": "operating_cost_readback_missing"}
    if mode not in {"paper", "live"} or owner_id != f"alpaca-investment-{mode}":
        summary["operating_costs_reason"] = "operating_cost_scope_invalid"
        return select_components(summary, requested)
    if payload is None:
        return select_components(summary, requested)
    try:
        if not isinstance(payload, dict) or "read_error" in payload:
            raise ValueError("operating_cost_readback_unavailable")
        readback = payload["readback"]
        # Calendar views verify child scopes independently; money keeps its original binding.
        if any(trip.get('scope_kind')=='owner_period' for trip in requested):
            for scope in readback.get('cost_scopes',[]):
                if (isinstance(scope,dict) and scope.get('scope_kind','order_pair')=='order_pair'
                        and scope.get('owner_id')==owner_id and scope.get('mode')==mode
                        and scope.get('paper') is (mode=='paper') and _binding(scope) is not None
                        and not any(_binding(scope)==_binding(trip) for trip in trips)):
                    trips.append(scope)
        billing_at = readback["observed_at"]
        if _time(billing_at) > _time(observed_at):
            raise ValueError("operating_cost_readback_from_future")
        # Reuse the existing pure validator with its own billing query window.
        repo = str(Path(__file__).resolve().parents[2])
        if repo not in sys.path:
            sys.path.append(repo)
        from skills.cfo.adapters.actual_cost import adapt, validate_official_cost_queries, paid_charge_identity, MAX_B0_AMOUNT_SIGNIFICANT_DIGITS
        with localcontext(Context(prec=MAX_B0_AMOUNT_SIGNIFICANT_DIGITS)):
            records = adapt(payload, snapshot_at=billing_at,
                            trailing_start=readback["trailing"]["window_start"])
        covered = {row["source_id"] for row in records
                   if row["record_type"] == "coverage" and row["product_loop_id"] == "investment"
                   and row["projection"] == "historical" and row["coverage_state"] == "complete"}
        raw = {}
        conflicts = set()
        documents = next((payload[key] for key in ("documents", "invoices", "paid_receipts")
                          if key in payload), [])
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            kind = doc.get("document_type")
            document_id = doc.get("invoice_id") if kind == "invoice" else doc.get("receipt_id")
            for line in doc.get("line_items", []):
                if not isinstance(line, dict):
                    raise ValueError("operating_cost_readback_invalid")
                for allocation in line.get("allocations", []):
                    if not isinstance(allocation, dict):
                        raise ValueError("operating_cost_readback_invalid")
                    receipt_id = (f"{doc.get('provider')}:actual-cost:{kind}:{document_id}:"
                                  f"line:{line.get('line_item_id')}:allocation:{allocation.get('allocation_id')}")
                    charge_identity=paid_charge_identity(doc,line,allocation)
                    if charge_identity is None:raise ValueError("operating_cost_readback_invalid")
                    account=doc.get('billing_account_ref')
                    account=account if isinstance(account,str) and account.strip() else None
                    value = (doc.get("provider"), kind, document_id, line, allocation, charge_identity, account)
                    if receipt_id in raw and raw[receipt_id] != value:
                        conflicts.add(receipt_id)
                    raw[receipt_id] = value
        jobs = {}
        job_conflicts = set()
        for join in payload.get("job_joins", []):
            if not isinstance(join, dict):
                continue
            key = (join.get("provider"), join.get("job_id"))
            if key in jobs and jobs[key] != join:
                job_conflicts.add(key)
            jobs[key] = join
        observations = [];scope_coverages=[];query_rejections=[]
        scopes = readback.get("cost_scopes", [])
        for scope in scopes if isinstance(scopes, list) else []:
            if not isinstance(scope, dict):
                continue
            for trip in trips:
                try:
                    matches = (scope.get("owner_id") == owner_id and scope.get("mode") == mode
                        and scope.get("paper") is (mode == "paper") and scope.get("order_ids") == trip["order_ids"]
                        and _time(scope.get("period_start")) == _time(trip["period_start"])
                        and _time(scope.get("period_end")) == _time(_cost_end(trip))
                        and isinstance(scope.get("source_receipt_ids"), list)
                        and set(trip["source_receipt_ids"]) <= set(scope["source_receipt_ids"]))
                except (KeyError, TypeError, ValueError):
                    matches = False
                if matches:
                    with localcontext(Context(prec=MAX_B0_AMOUNT_SIGNIFICANT_DIGITS)):
                        query_result = validate_official_cost_queries(payload, snapshot_at=observed_at,
                            paid_records=records, scope=scope, expected_inventory=expected_inventory)
                    observations.extend(query_result["observations"])
                    context={key:scope.get(key) for key in ('scope_id','owner_id','mode','paper','order_ids','period_start','period_end')}
                    query_rejections.extend({**context,**rejection} for rejection in query_result['rejections'])
                    verified=query_result.get('scope_coverages',[])
                    if verified:scope_coverages.extend(verified)
                    else:scope_coverages.append({**scope,'scope_kind':scope.get('scope_kind','order_pair'),
                        'coverage_state':'gap','reason':query_result['reason'],'evidence_refs':[]})
        summary["operating_cost_query_observations"] = observations
        summary["operating_cost_scope_coverages"] = scope_coverages
        summary["operating_cost_query_rejections"] = query_rejections
        component_gaps=[]
        accepted = {}
        charge_conflicts = set()
        for receipt in records:
            if (receipt["record_type"] != "receipt" or receipt["product_loop_id"] != "investment"
                    or receipt["currency"] != "USD" or receipt["verification_state"] != "verified"):
                continue
            identity = receipt["receipt_id"]
            if identity in conflicts or identity not in raw:
                continue
            provider, kind, document_id, line, allocation, charge_identity, account = raw[identity]
            key = (provider, allocation.get("job_id"))
            join = jobs.get(key)
            if key in job_conflicts or not isinstance(join, dict):
                continue
            if (join.get("document_type") != kind or join.get("document_id") != document_id
                    or join.get("line_item_id") != line.get("line_item_id")
                    or join.get("allocation_id") != allocation.get("allocation_id")
                    or join.get("owner_id") != owner_id or join.get("mode") != mode
                    or join.get("paper") is not (mode == "paper") or join.get("product_loop_id") != "investment"
                    or join.get("status") not in {"completed", "settled", "paid"}):
                continue
            for trip in trips:
                if (join.get("order_ids") != trip["order_ids"]
                        or not trip.get("period_start")
                        or _time(join.get("period_start")) != _time(trip["period_start"])
                        or _time(join.get("period_end")) != _time(_cost_end(trip))
                        or not isinstance(join.get("source_receipt_ids"), list)
                        or not set(trip["source_receipt_ids"]) <= set(join["source_receipt_ids"])):
                    continue
                occurred=_time(receipt['occurred_at']);begin=_time(trip['period_start']);finish=_time(_cost_end(trip))
                calendar=trip.get('scope_kind','order_pair')=='owner_period'
                inside=begin<=occurred<finish if calendar else begin<=occurred<=finish
                service=_has_service_period(line,join)
                proof=(_service_period_proof(line,join,trip,receipt,account,observations) if service
                    else _execution_time_proof(join,trip,receipt,account,observations))
                modern=service or expected_inventory is not None and join.get('join_type')=='paid_allocation' and 'execution_refs' in join
                if modern and (proof is not True or calendar and not inside and not service):
                    reason=('operating_cost_service_period_unverified' if service else 'operating_cost_calendar_time_mismatch' if calendar and not inside else
                        'operating_cost_execution_window_unverified' if proof is None else 'operating_cost_execution_time_mismatch')
                    component_gaps.append({'receipt_id':identity,'provider':provider,'owner_id':owner_id,'mode':mode,'paper':mode=='paper',
                        'order_ids':trip['order_ids'],'period_start':trip['period_start'],'period_end':_cost_end(trip),'reason':reason})
                    continue
                if f"actual-cost-{provider}" not in covered and proof is not True:continue
                if calendar and not inside and not service or proof is False or proof is None and not inside:continue
                component = receipt["components"][0]
                cost = {
                    "receipt_id": identity, "provider": provider, "currency": "USD", "document_id": document_id,
                    "charge_identity": list(charge_identity),"billing_account_ref":account,
                    "attribution_basis":"verified_service_period" if service else "verified_execution_window" if proof is True else "economic_interval_only",
                    "category": component["category"], "amount_usd": component["amount"],
                    "order_ids": trip["order_ids"], "period_start": trip["period_start"],
                    "period_end": _cost_end(trip), "occurred_at": receipt["occurred_at"],
                    "settled_at": receipt["settled_at"], "evidence_refs": receipt["evidence_refs"],
                }
                if service:
                    cost.update(service_period_start=line['service_period_start'],service_period_end=line['service_period_end'])
                if charge_identity in accepted:
                    fields = ("category", "amount_usd", "order_ids", "period_start", "period_end")
                    if any(accepted[charge_identity][field] != cost[field] for field in fields):
                        charge_conflicts.add(charge_identity)
                else:
                    accepted[charge_identity] = cost
        def claims_owned(join,value):
            provider,kind,doc_id,line,allocation,charge,account=value
            return (isinstance(join,dict) and join.get('join_type')!='scope_query' and join.get('provider')==provider
                and join.get('document_type')==kind and join.get('document_id')==doc_id
                and join.get('line_item_id')==line.get('line_item_id') and join.get('allocation_id')==allocation.get('allocation_id')
                and join.get('job_id')==allocation.get('job_id') and join.get('product_loop_id')=='investment'
                and join.get('owner_id')==owner_id and join.get('mode')==mode and join.get('paper') is (mode=='paper'))
        def claims_current(join,trip,value):
            return claims_owned(join,value) and _binding(join)==_binding(trip)
        for trip in trips:
            binding=_binding(trip)
            proofs=[row for row in observations if row.get('inventory_verification')=='verified'
                and row.get('settlement_state') in {'paid_final','no_charge_final'} and _binding(row)==binding]
            for receipt in records:
                if (receipt.get('record_type')!='receipt' or receipt.get('product_loop_id')!='investment'
                        or receipt.get('verification_state')!='verified' or receipt.get('currency')!='USD'):
                    continue
                identity=receipt['receipt_id'];value=raw.get(identity)
                if value is None:continue
                provider,kind,document_id,line,allocation,charge,account=value
                claimed=any(claims_current(join,trip,value) for join in payload.get('job_joins',[]))
                relevant=any(row.get('provider')==provider and line.get('category') in row.get('covered_categories',[])
                    and (account is None or claimed or row.get('billing_account_ref')==account and document_id in row.get('document_ids',[])) for row in proofs)
                if not relevant:continue
                known=accepted.get(charge)
                resolved=(charge not in charge_conflicts and known is not None
                    and known.get('attribution_basis') in {'verified_execution_window','verified_service_period'})
                if (resolved and known.get('attribution_basis')!='verified_service_period'
                        and trip.get('scope_kind','order_pair')=='owner_period' and _binding(known)!=binding
                        and _time(trip['period_start'])<=_time(receipt['occurred_at'])<_time(_cost_end(trip))
                        and not _calendar_covers(known,trip,observations)):resolved=False
                if resolved:continue
                if any(g.get('receipt_id')==identity and _binding(g)==binding for g in component_gaps):continue
                reason='operating_cost_paid_charge_conflict' if charge in charge_conflicts else 'operating_cost_paid_allocation_unattributed'
                component_gaps.append({'receipt_id':identity,'provider':provider,'owner_id':owner_id,'mode':mode,'paper':mode=='paper',
                    'order_ids':trip['order_ids'],'period_start':trip['period_start'],'period_end':_cost_end(trip),'reason':reason})
        verified_ids={r.get('receipt_id') for r in records if r.get('record_type')=='receipt' and r.get('verification_state')=='verified'}
        for trip in trips:
            proofs=[row for row in observations if row.get('inventory_verification')=='verified' and _binding(row)==_binding(trip)]
            for identity,value in raw.items():
                if identity in verified_ids:continue
                provider,kind,document_id,line,allocation,charge,account=value
                if allocation.get('product_loop_id')!='investment' or not any(claims_current(join,trip,value) for join in payload.get('job_joins',[])):continue
                if not any(row.get('provider')==provider and line.get('category') in row.get('covered_categories',[])
                        and (account is None or row.get('billing_account_ref')==account) for row in proofs):continue
                component_gaps.append({'document_type':kind,'document_id':document_id,'line_item_id':line.get('line_item_id'),
                    'allocation_id':allocation.get('allocation_id'),'provider':provider,'owner_id':owner_id,'mode':mode,'paper':mode=='paper',
                    'order_ids':trip['order_ids'],'period_start':trip['period_start'],'period_end':_cost_end(trip),
                    'reason':'operating_cost_claimed_allocation_unverified'})
        for trip in requested:
            for identity,value in raw.items():
                provider,kind,document_id,line,allocation,charge,account=value
                owned=[join for join in payload.get('job_joins',[]) if claims_owned(join,value)]
                if not owned:continue
                service=any(_has_service_period(line,join) for join in owned)
                if service:
                    try:
                        begin,end=_time(line['service_period_start']),_time(line['service_period_end'])
                        relevant=not begin<end or begin<_time(_cost_end(trip)) and _time(trip['period_start'])<end
                    except (KeyError,TypeError,ValueError):
                        relevant=True
                else:
                    parent=_binding(trip)
                    relevant=trip.get('scope_kind')=='owner_period' and parent is not None and any(
                        _periods_overlap(_binding(join),parent)
                        for join in owned)
                known=accepted.get(charge)
                confirmed=(charge not in charge_conflicts and known is not None
                    and known.get('attribution_basis')=='verified_service_period')
                if not relevant or (confirmed and _binding(known)==_binding(trip)):continue
                if (not service and charge not in charge_conflicts and known is not None
                        and known.get('attribution_basis')=='verified_execution_window'
                        and (_binding(known)==_binding(trip) or not _calendar_contains(known,trip)
                            or _calendar_covers(known,trip,observations))):continue
                gap={'provider':provider,'document_type':kind,'document_id':document_id,
                    'line_item_id':line.get('line_item_id'),'allocation_id':allocation.get('allocation_id'),
                    'order_ids':trip['order_ids'],'period_start':trip['period_start'],'period_end':_cost_end(trip),
                    'reason':('operating_cost_service_period_partial_view' if confirmed else 'operating_cost_service_period_unverified')
                        if service else 'operating_cost_paid_allocation_unattributed'}
                if identity in verified_ids:gap['receipt_id']=identity
                if not any(_binding(g)==_binding(gap) and g.get('document_id')==document_id
                        and g.get('allocation_id')==allocation.get('allocation_id') for g in component_gaps):component_gaps.append(gap)
            for charge,component in accepted.items():
                if (component.get('attribution_basis')!='verified_service_period'
                        and _calendar_contains(component,trip) and (charge in charge_conflicts
                        or not _calendar_covers(component,trip,observations))):
                    component_gaps.append({'receipt_id':component['receipt_id'],'provider':component['provider'],
                        'order_ids':trip['order_ids'],'period_start':trip['period_start'],'period_end':_cost_end(trip),
                        'reason':'operating_cost_calendar_source_unverified'})
        summary['operating_cost_component_gaps']=component_gaps
        summary.update({"operating_cost_components": [accepted[key] for key in sorted(accepted)
                                                      if key not in charge_conflicts],
                        "operating_costs_observed_at": billing_at,
                        "operating_costs_reason": "no_scoped_paid_components"})
    except (KeyError, TypeError, ValueError, ArithmeticError, RecursionError) as error:
        summary["operating_costs_reason"] = (str(error) if isinstance(error, ValueError)
                                             and str(error).startswith("operating_cost_")
                                             else "operating_cost_readback_invalid")
    return select_components(summary, requested)
