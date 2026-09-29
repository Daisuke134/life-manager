#!/usr/bin/env python3
"""Mercor boundary for the shared marketplace Paid kernel."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlparse


def _load_paid_handoff_builder():
    path = Path(__file__).resolve().parents[3] / "_shared/marketplace-core/scripts/paid_handoff.py"
    spec = importlib.util.spec_from_file_location("mercor_shared_paid_handoff", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("mercor_paid_handoff_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PAID_HANDOFF = _load_paid_handoff_builder()

ACTIVE_STATES = frozenset({"selected", "contracted", "authorized_work", "work_submitted", "needs_human", "provider_review_required"})
TERMINAL_STATES = frozenset({"accepted", "paid_settled", "bank_matched", "revenue_recorded", "rejected"})

class MercorPaidWait(RuntimeError):
    def __init__(self, reason: str, remaining_work: list[str]):
        super().__init__(reason); self.paid_wait_reason = reason; self.paid_remaining_work = remaining_work

def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip(): raise RuntimeError("mercor_paid_inventory_unavailable")
    try: parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError: raise RuntimeError("mercor_paid_inventory_unavailable") from None
    if parsed.tzinfo is None: raise RuntimeError("mercor_paid_inventory_unavailable")
    return parsed.astimezone(timezone.utc)

def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    try: lines = path.read_text(encoding="utf-8").splitlines()
    except OSError: raise RuntimeError("mercor_paid_inventory_unavailable") from None
    for line in lines:
        try: value = json.loads(line)
        except ValueError: raise RuntimeError("mercor_paid_inventory_unavailable") from None
        required = ("work_id", "event_id", "state", "evidence_ref", "observed_at")
        if not isinstance(value, Mapping) or any(not isinstance(value.get(field), str) or not value[field].strip() for field in required):
            raise RuntimeError("mercor_paid_inventory_unavailable")
        if value["state"] not in ACTIVE_STATES | TERMINAL_STATES: raise RuntimeError("mercor_paid_inventory_unavailable")
        _timestamp(value["observed_at"])
        evidence = urlparse(value["evidence_ref"])
        if evidence.scheme != "https" or evidence.hostname != "work.mercor.com":
            raise MercorPaidWait(
                "official_work_receipt_required",
                ["observe this work item on work.mercor.com and persist its identity-bound official URL"],
            )
        rows.append(dict(value))
    return rows

def _official_contracts(path: Path, *, max_age_seconds: int = 900) -> list[dict[str, Any]]:
    if not path.is_file():
        raise MercorPaidWait("official_work_inventory_unavailable", ["resume the shared Mercor Reply observer and obtain its official contract snapshot"])
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): raise RuntimeError("mercor_paid_inventory_unavailable") from None
    contracts = value.get("contracts") if isinstance(value, Mapping) else None
    observed_at = value.get("observed_at") if isinstance(value, Mapping) else None
    if value.get("version") != 1 or not isinstance(contracts, list):
        raise RuntimeError("mercor_paid_inventory_unavailable")
    observed = _timestamp(observed_at)
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    if age < -300 or age > max_age_seconds:
        raise MercorPaidWait("official_work_inventory_stale", ["wait for the shared Mercor Reply observer to refresh its official contract snapshot"])
    rows = []
    states = {"active":"contracted", "contracted":"contracted", "selected":"selected"}
    for contract in contracts:
        if not isinstance(contract, Mapping): raise RuntimeError("mercor_paid_inventory_unavailable")
        work_id = contract.get("jobId") or contract.get("contractId") or contract.get("id")
        if not isinstance(work_id, str) or not work_id.strip(): raise RuntimeError("mercor_paid_inventory_unavailable")
        status = str(contract.get("status") or "").strip().casefold()
        state = states.get(status, "provider_review_required")
        payload = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        rows.append({"work_id":work_id.strip(), "event_id":hashlib.sha256(payload.encode()).hexdigest(),
                     "state":state, "evidence_ref":"https://work.mercor.com/home?tab=contracts",
                     "observed_at":observed_at.strip(), "official_contract":dict(contract)})
    return rows

class MercorPaidAdapter:
    def __init__(self, *, account_id: str, official_snapshot: Path, work_events: Path):
        if not isinstance(account_id, str) or not account_id.strip(): raise ValueError("mercor_account_id_invalid")
        self.account_id = account_id.strip(); self.official_snapshot = official_snapshot.expanduser().resolve(); self.work_events = work_events.expanduser().resolve(); self._contexts = {}
    def _inventory(self) -> list[dict[str, Any]]:
        latest, histories = {}, {}
        for row in _official_contracts(self.official_snapshot) + _rows(self.work_events):
            work_id = row["work_id"].strip(); histories.setdefault(work_id, []).append(row)
            if work_id not in latest or _timestamp(row["observed_at"]) >= _timestamp(latest[work_id]["observed_at"]): latest[work_id] = row
        self._contexts = {key: {"events": value, "latest": latest[key]} for key, value in histories.items()}
        return [{"provider":"mercor", "account_id":self.account_id, "work_id":work_id,
                 "latest_event_id":row["event_id"], "provider_state":row["state"], "observed_at":row["observed_at"]}
                for work_id, row in latest.items() if row["state"] in ACTIVE_STATES]
    def observe_active(self): return self._inventory()
    def observe_one(self, work_id: str):
        matches = [row for row in self._inventory() if row["work_id"] == work_id]
        if len(matches) != 1: raise RuntimeError("mercor_paid_work_unavailable")
        return matches[0]
    def context(self, work_id: str):
        if work_id not in self._contexts: self._inventory()
        try: return dict(self._contexts[work_id])
        except KeyError: raise RuntimeError("mercor_paid_work_unavailable") from None

    def paid_handoff(self, work_id: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
        """Map an explicit official Mercor funded handoff to the shared contract.

        The current Mercor observer exposes contract identity and status, but not
        enough payment/task detail to safely infer a Paid mutation.  A future
        official observer may therefore attach a normalized ``paid_handoff``
        object to the contract snapshot.  Every required field is mandatory;
        this boundary never derives funding, price, scope, or artifact terms
        from a title, email, or an ``active`` status.
        """
        if not isinstance(work_id, str) or not work_id.strip() or not isinstance(context, Mapping):
            raise RuntimeError("mercor_paid_handoff_unavailable")
        latest = context.get("latest")
        official = latest.get("official_contract") if isinstance(latest, Mapping) else None
        paid = official.get("paid_handoff") if isinstance(official, Mapping) else None
        if not isinstance(official, Mapping) or not isinstance(paid, Mapping):
            raise RuntimeError("mercor_paid_handoff_unavailable")
        if not isinstance(latest, Mapping) or latest.get("work_id") != work_id.strip():
            raise RuntimeError("mercor_paid_handoff_unavailable")

        def _identifier(name: str) -> str:
            value = paid.get(name)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError("mercor_paid_handoff_unavailable")
            return value.strip()

        contract_id = _identifier("contract_external_id")
        funding_id = _identifier("funding_external_id")
        thread_id = _identifier("thread_external_id")
        terms_sha256 = _identifier("terms_sha256")
        scope_sha256 = _identifier("scope_sha256")
        artifact_requirement_sha256 = _identifier("artifact_requirement_sha256")
        observed_at = _identifier("observed_at")
        if paid.get("status") != "funded" or type(paid.get("price_minor")) is not int or paid["price_minor"] < 1:
            raise RuntimeError("mercor_paid_handoff_unavailable")
        currency = paid.get("currency")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise RuntimeError("mercor_paid_handoff_unavailable")
        try:
            return _PAID_HANDOFF.build_paid_handoff(
                platform="mercor",
                application_external_id=f"application:{work_id.strip()}",
                work_external_id=work_id.strip(),
                contract_external_id=contract_id,
                funding_external_id=funding_id,
                thread_external_id=thread_id,
                terms_sha256=terms_sha256,
                scope_sha256=scope_sha256,
                artifact_requirement_sha256=artifact_requirement_sha256,
                price_minor=paid["price_minor"],
                currency=currency,
                observed_at=observed_at,
            )
        except _PAID_HANDOFF.PaidHandoffMappingError as error:
            raise RuntimeError("mercor_paid_handoff_unavailable") from error

    def mutate(self, intent): raise RuntimeError("mercor_human_submission_required")
    def readback(self, intent): return {"verified":False, "authoritative_absent":False}

def decide(row: Mapping[str, Any]) -> dict[str, Any]:
    state = row.get("provider_state")
    if state == "work_submitted": return {"action":"noop", "classification":"awaiting_buyer"}
    if state == "needs_human": return {"action":"wait", "reason":"mercor_human_action_required", "remaining_work":["complete the identity-bound task and resume this exact work item"]}
    if state in {"selected", "contracted"}: return {"action":"wait", "reason":"mercor_work_authorization_required", "remaining_work":["read the official contract and record explicit AI work authorization"]}
    if state == "authorized_work": return {"action":"wait", "reason":"mercor_human_submission_required", "remaining_work":["prepare the artifact and obtain the required human submission receipt"]}
    if state == "provider_review_required": return {"action":"wait", "reason":"mercor_contract_state_review_required", "remaining_work":["read the official contract state and classify the exact next work or payment action"]}
    raise RuntimeError("mercor_paid_state_unavailable")

def build(argv: list[str]):
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--account-id",required=True); parser.add_argument("--official-snapshot",required=True,type=Path); parser.add_argument("--work-events",required=True,type=Path); args=parser.parse_args(argv)
    return MercorPaidAdapter(account_id=args.account_id,official_snapshot=args.official_snapshot,work_events=args.work_events), decide

__all__=["MercorPaidAdapter","MercorPaidWait","build","decide"]
