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


def select_components(summary: dict, trips) -> dict:
    """Select one economic day without moving cumulative costs onto that day's P&L."""
    pairs = {tuple(trip["order_ids"]) for trip in trips}
    components = [row for row in summary.get("operating_cost_components", [])
                  if tuple(row["order_ids"]) in pairs]
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


def summarize(trips, payload, *, owner_id: str, observed_at: str) -> dict:
    summary = {"operating_cost_components": [], "operating_costs_observed_at": None,
               "operating_costs_reason": "operating_cost_readback_missing"}
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
        from skills.cfo.adapters.actual_cost import adapt
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
                    invoice_id = doc.get("invoice_id")
                    charge_kind, charge_document = (("invoice", invoice_id)
                        if isinstance(invoice_id, str) and invoice_id else (kind, document_id))
                    charge_identity = (doc.get("provider"), charge_kind, charge_document,
                                       line.get("line_item_id"), allocation.get("allocation_id"))
                    value = (doc.get("provider"), kind, document_id, line, allocation, charge_identity)
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
            provider, kind, document_id, line, allocation, charge_identity = raw[identity]
            key = (provider, allocation.get("job_id"))
            join = jobs.get(key)
            if key in job_conflicts or not isinstance(join, dict):
                continue
            if (join.get("document_type") != kind or join.get("document_id") != document_id
                    or join.get("line_item_id") != line.get("line_item_id")
                    or join.get("allocation_id") != allocation.get("allocation_id")
                    or join.get("owner_id") != owner_id or join.get("mode") != "paper"
                    or join.get("paper") is not True or join.get("product_loop_id") != "investment"
                    or join.get("status") not in {"completed", "settled", "paid"}):
                continue
            for trip in trips:
                if (join.get("order_ids") != trip["order_ids"]
                        or not trip.get("period_start")
                        or _time(join.get("period_start")) != _time(trip["period_start"])
                        or _time(join.get("period_end")) != _time(trip["closed_at"])
                        or not isinstance(join.get("source_receipt_ids"), list)
                        or not set(trip["source_receipt_ids"]) <= set(join["source_receipt_ids"])
                        or not _time(trip["period_start"]) <= _time(receipt["occurred_at"]) <= _time(trip["closed_at"])):
                    continue
                component = receipt["components"][0]
                cost = {
                    "receipt_id": identity, "provider": provider, "currency": "USD",
                    "charge_identity": list(charge_identity),
                    "category": component["category"], "amount_usd": component["amount"],
                    "order_ids": trip["order_ids"], "period_start": trip["period_start"],
                    "period_end": trip["closed_at"], "occurred_at": receipt["occurred_at"],
                    "settled_at": receipt["settled_at"], "evidence_refs": receipt["evidence_refs"],
                }
                if charge_identity in accepted:
                    fields = ("category", "amount_usd", "order_ids", "period_start", "period_end")
                    if any(accepted[charge_identity][field] != cost[field] for field in fields):
                        charge_conflicts.add(charge_identity)
                else:
                    accepted[charge_identity] = cost
        summary.update({"operating_cost_components": [accepted[key] for key in sorted(accepted)
                                                      if key not in charge_conflicts],
                        "operating_costs_observed_at": billing_at,
                        "operating_costs_reason": "no_scoped_paid_components"})
    except (KeyError, TypeError, ValueError, ArithmeticError, RecursionError) as error:
        summary["operating_costs_reason"] = (str(error) if isinstance(error, ValueError)
                                             and str(error).startswith("operating_cost_")
                                             else "operating_cost_readback_invalid")
    return select_components(summary, trips)
