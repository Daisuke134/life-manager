"""Read-only paid cost components; scoped subtotals never imply total cost coverage."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from decimal import Decimal, localcontext
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


def select_components(summary: dict, trips) -> dict:
    """Select one economic day without moving cumulative costs onto that day's P&L."""
    requested=[_binding(trip) for trip in trips]
    pairs={key for key in requested if key is not None}
    components = [row for row in summary.get("operating_cost_components", [])
                  if _binding(row) in pairs]
    coverages=[row for row in summary.get('operating_cost_scope_coverages',[]) if _binding(row) in pairs]
    component_gaps=[row for row in summary.get('operating_cost_component_gaps',[]) if _binding(row) in pairs]
    complete=not component_gaps and bool(requested) and len(pairs)==len(requested) and all(
        len([row for row in coverages if _binding(row)==key])==1
        and next(row for row in coverages if _binding(row)==key)['coverage_state']=='complete' for key in pairs)
    coverage_reason=None if complete else component_gaps[0]['reason'] if component_gaps else next((row.get('reason') for row in coverages if row.get('coverage_state')!='complete'),
        'cost_query_scope_missing' if summary.get('operating_cost_scope_coverages') else 'source_inventory_unverified')
    def subtotal(categories):
        amounts = [Decimal(row["amount_usd"]) for row in components if row["category"] in categories]
        if not amounts:
            return None
        with localcontext() as context:
            context.prec = max(len(format(amount, "f").replace(".", "")) for amount in amounts) + len(str(len(amounts))) + 1
            return format(sum(amounts, Decimal("0")), "f")
    return {
        "operating_costs_status": "partial" if components else "unknown",
        "operating_costs_reason": ("scoped_paid_components_only" if components
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


def read_readback(path: str | None) -> Any:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {"read_error": "operating_cost_readback_unavailable"}


def summarize(trips, payload, *, owner_id: str, observed_at: str, expected_inventory=None, mode="paper") -> dict:
    summary = {"operating_cost_components": [], "operating_costs_observed_at": None,
               "operating_costs_reason": "operating_cost_readback_missing"}
    if mode not in {"paper", "live"} or owner_id != f"alpaca-investment-{mode}":
        summary["operating_costs_reason"] = "operating_cost_scope_invalid"
        return select_components(summary, trips)
    if payload is None:
        return select_components(summary, trips)
    try:
        if not isinstance(payload, dict) or "read_error" in payload:
            raise ValueError("operating_cost_readback_unavailable")
        readback = payload["readback"]
        billing_at = readback["observed_at"]
        if _time(billing_at) > _time(observed_at):
            raise ValueError("operating_cost_readback_from_future")
        # Reuse the existing pure validator with its own billing query window.
        repo = str(Path(__file__).resolve().parents[2])
        if repo not in sys.path:
            sys.path.append(repo)
        from skills.cfo.adapters.actual_cost import adapt, validate_official_cost_queries, paid_charge_identity
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
                    or receipt["currency"] != "USD" or receipt["verification_state"] != "verified"
                    or f"actual-cost-{receipt['provider']}" not in covered):
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
                proof=_execution_time_proof(join,trip,receipt,account,observations)
                modern=expected_inventory is not None and join.get('join_type')=='paid_allocation' and 'execution_refs' in join
                if modern and (proof is not True or calendar and not inside):
                    reason=('operating_cost_calendar_time_mismatch' if calendar and not inside else
                        'operating_cost_execution_window_unverified' if proof is None else 'operating_cost_execution_time_mismatch')
                    component_gaps.append({'receipt_id':identity,'provider':provider,'owner_id':owner_id,'mode':mode,'paper':mode=='paper',
                        'order_ids':trip['order_ids'],'period_start':trip['period_start'],'period_end':_cost_end(trip),'reason':reason})
                    continue
                if calendar and not inside or proof is False or proof is None and not inside:continue
                component = receipt["components"][0]
                cost = {
                    "receipt_id": identity, "provider": provider, "currency": "USD",
                    "charge_identity": list(charge_identity),"billing_account_ref":account,
                    "attribution_basis":"verified_execution_window" if proof is True else "economic_interval_only",
                    "category": component["category"], "amount_usd": component["amount"],
                    "order_ids": trip["order_ids"], "period_start": trip["period_start"],
                    "period_end": _cost_end(trip), "occurred_at": receipt["occurred_at"],
                    "settled_at": receipt["settled_at"], "evidence_refs": receipt["evidence_refs"],
                }
                if charge_identity in accepted:
                    fields = ("category", "amount_usd", "order_ids", "period_start", "period_end")
                    if any(accepted[charge_identity][field] != cost[field] for field in fields):
                        charge_conflicts.add(charge_identity)
                else:
                    accepted[charge_identity] = cost
        summary['operating_cost_component_gaps']=component_gaps
        summary.update({"operating_cost_components": [accepted[key] for key in sorted(accepted)
                                                      if key not in charge_conflicts],
                        "operating_costs_observed_at": billing_at,
                        "operating_costs_reason": "no_scoped_paid_components"})
    except (KeyError, TypeError, ValueError, ArithmeticError, RecursionError) as error:
        summary["operating_costs_reason"] = (str(error) if isinstance(error, ValueError)
                                             and str(error).startswith("operating_cost_")
                                             else "operating_cost_readback_invalid")
    return select_components(summary, trips)
