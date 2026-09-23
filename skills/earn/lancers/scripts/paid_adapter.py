#!/usr/bin/env python3
"""Thin Lancers boundary for the shared marketplace Paid kernel."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote


HERE = Path(__file__).resolve().parent
DEFAULT_STATE = Path.home() / ".local/state/anicca/lancers/application.json"


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_work_sync():
    path = HERE / "work_sync.py"
    spec = importlib.util.spec_from_file_location("lancers_paid_work_sync", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("lancers_paid_inventory_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _LiveLancersProvider:
    """Provider-grounded detail/message boundary for funded Lancers work."""

    def __init__(self, *, state_path: Path):
        self.state_path = Path(state_path).expanduser().resolve()
        self.browser = None
        self.page = None
        self._lock = None
        self._posted: dict[str, str] = {}

    def _open(self) -> None:
        if self.page is not None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _load_work_sync().application_tick.account_lock(
            self.state_path.with_name("paid-account.json")
        )
        self._lock.__enter__()
        work_sync = _load_work_sync()
        try:
            self.browser, self.page = work_sync.application_tick._open_owned_page()
            if not work_sync.application_tick._production_account_ready(self.page):
                raise RuntimeError("lancers_paid_account_unavailable")
        except Exception:
            self.close()
            raise

    def _work_sync(self):
        return _load_work_sync()

    def _goto_detail(self, detail_path: str) -> str:
        if not isinstance(detail_path, str) or not detail_path.startswith("/"):
            raise RuntimeError("lancers_paid_detail_path_invalid")
        self._open()
        work_sync = self._work_sync()
        self.page.goto(
            f"https://www.lancers.jp{detail_path}",
            wait_until="domcontentloaded", timeout=20_000,
        )
        parsed = work_sync.urlsplit(str(self.page.url))
        if parsed.netloc != "www.lancers.jp" or parsed.path != detail_path:
            raise RuntimeError("lancers_paid_detail_readback_unavailable")
        return str(self.page.locator("body").inner_text()).strip()

    def _board_for(self, candidate: Mapping[str, Any]) -> tuple[str | None, list[Mapping[str, Any]]]:
        work_sync = self._work_sync()
        private: list[Any] = []
        snapshot = work_sync._snapshot(
            lambda path: work_sync._fetch(self.page, path), set(), private,
        )
        provider_id = str(candidate.get("provider_id") or "")
        for board in snapshot.get("boards", []):
            refs = board.get("source_refs") if isinstance(board, Mapping) else None
            if not isinstance(refs, list):
                continue
            if any(isinstance(ref, Mapping)
                   and ref.get("source_kind") in {"job", "storefront_contract"}
                   and str(ref.get("provider_id")) == provider_id
                   for ref in refs):
                return str(board.get("board_id")), [
                    dict(item) for item in private
                    if isinstance(item, (list, tuple)) and len(item) == 3
                    and str(item[0].get("id")) == str(board.get("board_id"))
                ]
        return None, []

    @staticmethod
    def _funded(body: str) -> bool:
        compact = " ".join(body.split())
        return ("仮払い済み" in compact or "仮払いが完了" in compact
                or "エスクロー済み" in compact)

    def read_detail(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        detail_path = candidate.get("detail_path")
        body = self._goto_detail(detail_path)
        board_id, private = self._board_for(candidate)
        messages: list[Mapping[str, Any]] = []
        if board_id:
            messages = self._work_sync()._message_rows(
                lambda path: self._work_sync()._fetch(self.page, path), board_id,
            )
        buyer = [row for row in messages
                 if isinstance(row.get("send_user"), Mapping)
                 and row["send_user"].get("is_client") is True]
        latest = max(buyer, key=lambda row: int(str(row.get("id")))) if buyer else None
        return {
            "provider_state": "funded" if self._funded(body) else "requires_detail_readback",
            "detail_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "board_id": board_id,
            "buyer_event_id": str(latest.get("id")) if latest else None,
            "buyer_context": "\n\n".join(str(row.get("description") or "").strip()
                                             for row in buyer[-20:]),
            "formal_delivery_required": True,
        }

    def send_message(self, intent: Mapping[str, Any], detail: Mapping[str, Any]) -> None:
        board_id = detail.get("board_id")
        payload = intent.get("payload") if isinstance(intent, Mapping) else None
        body = payload.get("body") if isinstance(payload, Mapping) else None
        if not isinstance(board_id, str) or not board_id or not isinstance(body, str) or not body.strip():
            raise RuntimeError("lancers_paid_message_context_invalid")
        self._open()
        value = self.page.evaluate(
            """async ({path, body}) => { const form = new FormData();
            form.append('description', body); form.append('rich_description', body);
            const response = await fetch(path, {method:'POST', credentials:'same-origin', body:form});
            const text = await response.text(); let parsed = {}; try { parsed = JSON.parse(text); } catch (_) {}
            return {status: response.status, body: parsed}; }""",
            {"path": f"/v1/message_api/boards/{quote(board_id, safe='')}/messages",
             "body": body.strip()},
        )
        if not isinstance(value, Mapping) or value.get("status") not in {200, 201}:
            raise RuntimeError("lancers_paid_message_submission_uncertain")
        response = value.get("body")
        if isinstance(response, Mapping) and isinstance(response.get("data"), Mapping):
            response = response["data"]
        message_id = response.get("id") if isinstance(response, Mapping) else None
        if not isinstance(message_id, (str, int)) or not str(message_id).strip():
            raise RuntimeError("lancers_paid_message_submission_uncertain")
        self._posted[str(intent.get("effect_key"))] = str(message_id)

    def readback(self, intent: Mapping[str, Any], detail: Mapping[str, Any]) -> dict[str, Any]:
        if intent.get("action") != "answer":
            return {"verified": False, "authoritative_absent": False}
        board_id = detail.get("board_id")
        payload = intent.get("payload")
        body = payload.get("body") if isinstance(payload, Mapping) else None
        if not isinstance(board_id, str) or not isinstance(body, str):
            return {"verified": False, "authoritative_absent": False}
        self._open()
        rows = self._work_sync()._message_rows(
            lambda path: self._work_sync()._fetch(self.page, path), board_id,
        )
        expected = self._posted.get(str(intent.get("effect_key")))
        for row in rows:
            sender = row.get("send_user")
            if (isinstance(sender, Mapping) and sender.get("is_client") is False
                    and str(row.get("description") or "").strip() == body.strip()
                    and (expected is None or str(row.get("id")) == expected)):
                return {"verified": True, "provider_receipt_id": str(row["id"]),
                        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        return {"verified": False, "authoritative_absent": True}

    def close(self) -> None:
        work_sync = self._work_sync()
        if self.page is not None:
            try:
                work_sync._cleanup(self.page, self.browser)
            except Exception:
                pass
        self.page = self.browser = None
        if self._lock is not None:
            lock, self._lock = self._lock, None
            lock.__exit__(None, None, None)


class LancersPaidAdapter:
    def __init__(self, *, account_id: str, inventory_reader: Callable[[], Mapping[str, Any]],
                 clock: Callable[[], str] | None = None,
                 provider: Any | None = None):
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("lancers_account_id_invalid")
        self.account_id = account_id.strip()
        self.inventory_reader = inventory_reader
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        self.provider = provider
        self._contexts: dict[str, dict[str, Any]] = {}

    def _inventory(self) -> list[dict[str, Any]]:
        snapshot = self.inventory_reader()
        if (not isinstance(snapshot, Mapping) or snapshot.get("ok") is not True
                or snapshot.get("source_complete") is not True
                or not isinstance(snapshot.get("contract_candidates"), list)):
            raise RuntimeError("lancers_paid_inventory_unavailable")
        observed_at = self.clock()
        rows = []
        contexts: dict[str, dict[str, Any]] = {}
        for candidate in snapshot["contract_candidates"]:
            if not isinstance(candidate, Mapping):
                raise RuntimeError("lancers_paid_inventory_unavailable")
            kind = candidate.get("source_kind")
            provider_id = candidate.get("provider_id")
            funding = candidate.get("funding_status")
            if kind not in {"project", "monthly", "storefront"} or not isinstance(provider_id, str) or not provider_id:
                raise RuntimeError("lancers_paid_inventory_unavailable")
            if not isinstance(funding, str) or not funding:
                raise RuntimeError("lancers_paid_inventory_unavailable")
            work_id = f"{kind}:{provider_id}"
            event = _digest({"contract": candidate, "boards": snapshot.get("boards", [])})
            rows.append({
                "provider": "lancers", "account_id": self.account_id, "work_id": work_id,
                "latest_event_id": event, "provider_state": funding, "observed_at": observed_at,
            })
            contexts[work_id] = {
                "contract": dict(candidate),
                "boards": list(snapshot.get("boards", [])),
                "finance": dict(snapshot.get("finance", {})),
            }
        self._contexts = contexts
        return rows

    def observe_active(self) -> list[dict[str, Any]]:
        return self._inventory()

    def observe_one(self, work_id: str) -> dict[str, Any]:
        matches = [row for row in self._inventory() if row["work_id"] == work_id]
        if len(matches) != 1:
            raise RuntimeError("lancers_paid_work_unavailable")
        return matches[0]

    def context(self, work_id: str) -> dict[str, Any]:
        if work_id not in self._contexts:
            self._inventory()
        try:
            context = dict(self._contexts[work_id])
        except KeyError:
            raise RuntimeError("lancers_paid_work_unavailable") from None
        if self.provider is not None:
            detail = self.provider.read_detail(dict(context["contract"]))
            if not isinstance(detail, Mapping):
                raise RuntimeError("lancers_paid_contract_detail_invalid")
            context["contract"] = {**context["contract"], **dict(detail)}
            self._contexts[work_id] = context
        return context

    @staticmethod
    def _detail(context: Mapping[str, Any]) -> Mapping[str, Any]:
        contract = context.get("contract")
        if not isinstance(contract, Mapping):
            raise RuntimeError("lancers_paid_contract_detail_invalid")
        return contract

    def _current_detail(self, work_id: str) -> Mapping[str, Any]:
        return self._detail(self.context(work_id))

    def mutate(self, intent: dict[str, Any]) -> None:
        if self.provider is None:
            raise RuntimeError("lancers_paid_provider_unavailable")
        if not isinstance(intent, Mapping):
            raise RuntimeError("lancers_paid_intent_invalid")
        work_id = intent.get("work_id")
        action = intent.get("action")
        payload = intent.get("payload")
        if (not isinstance(work_id, str) or not work_id.strip()
                or action not in {"answer", "formal_delivery"}
                or not isinstance(payload, Mapping)):
            raise RuntimeError("lancers_paid_effect_unsupported")
        detail = self._current_detail(work_id)
        if detail.get("provider_state") != "funded":
            raise RuntimeError("lancers_paid_context_changed")
        event_id = payload.get("buyer_event_id")
        if not isinstance(event_id, str) or event_id != detail.get("buyer_event_id"):
            raise RuntimeError("lancers_paid_context_changed")
        if (payload.get("correct_work_verified") is not True
                or payload.get("quality_verdict") != "quality_ok"
                or not isinstance(payload.get("quality_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", payload["quality_sha256"])):
            raise RuntimeError("lancers_paid_answer_quality_unverified")
        if action == "answer":
            body = payload.get("body")
            if not isinstance(body, str) or not body.strip():
                raise RuntimeError("lancers_paid_answer_invalid")
            sender = getattr(self.provider, "send_message", None)
            if not callable(sender):
                raise RuntimeError("lancers_paid_message_effect_unavailable")
            sender(dict(intent), detail)
            return
        sender = getattr(self.provider, "submit_delivery", None)
        if not callable(sender):
            raise RuntimeError("lancers_paid_delivery_effect_unavailable")
        sender(dict(intent), detail)

    def readback(self, intent: dict[str, Any]) -> dict[str, Any]:
        work_id = intent.get("work_id") if isinstance(intent, Mapping) else None
        if not isinstance(work_id, str) or not work_id.strip():
            return {"verified": False, "authoritative_absent": False}
        active = self._inventory()
        if not any(row["work_id"] == work_id for row in active):
            return {"verified": False, "authoritative_absent": True}
        if self.provider is None:
            return {"verified": False, "authoritative_absent": False}
        detail = self._current_detail(work_id)
        readback = getattr(self.provider, "readback", None)
        if not callable(readback):
            return {"verified": False, "authoritative_absent": False}
        value = readback(dict(intent), detail)
        if not isinstance(value, Mapping):
            return {"verified": False, "authoritative_absent": False}
        return dict(value)


def decide(row: Mapping[str, Any]) -> dict[str, Any]:
    context = row.get("context")
    contract = context.get("contract") if isinstance(context, Mapping) else None
    if not isinstance(contract, Mapping):
        if row.get("provider_state") == "requires_detail_readback":
            return {
                "action": "wait",
                "reason": "official_contract_detail_required",
                "remaining_work": ["read funded contract terms and complete buyer context"],
            }
        raise RuntimeError("lancers_paid_context_unavailable")
    provider_state = contract.get("provider_state")
    if provider_state == "delivered":
        return {"action": "noop", "classification": "completed"}
    if provider_state != "funded":
        return {
            "action": "wait",
            "reason": "official_contract_detail_required",
            "remaining_work": ["read funded contract terms and complete buyer context"],
        }
    buyer_event_id = contract.get("buyer_event_id")
    if not isinstance(buyer_event_id, str) or not buyer_event_id.strip():
        return {"action": "wait", "reason": "buyer_event_required",
                "remaining_work": ["read and persist the latest buyer message"]}
    body = contract.get("prepared_answer")
    if (not isinstance(body, str) or not body.strip()
            or contract.get("correct_work_verified") is not True
            or contract.get("quality_verdict") != "quality_ok"
            or not isinstance(contract.get("quality_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", contract["quality_sha256"])):
        return {"action": "wait", "reason": "work_quality_required",
                "remaining_work": ["produce and independently verify the contract-specific work"]}
    return {"action": "answer", "payload": {
        "body": body.strip(), "buyer_event_id": buyer_event_id.strip(),
        "correct_work_verified": True, "quality_verdict": "quality_ok",
        "quality_sha256": contract["quality_sha256"],
    }}


def build(argv: list[str]):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args(argv)
    work_sync = _load_work_sync()
    reader = lambda: work_sync.read_paid_inventory(
        state_path=args.state_path.expanduser().resolve()
    )
    return LancersPaidAdapter(
        account_id=args.account_id,
        inventory_reader=reader,
        provider=_LiveLancersProvider(state_path=args.state_path.expanduser().resolve()),
    ), decide


__all__ = ["LancersPaidAdapter", "build", "decide"]
