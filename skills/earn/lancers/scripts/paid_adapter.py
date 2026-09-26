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


def _quality_digest(contract: Mapping[str, Any], body: str) -> str:
    value: dict[str, Any] = {
        "buyer_context": contract.get("buyer_context"),
        "body": body.strip(),
    }
    if "artifact_content" in contract:
        value["artifact_content"] = contract.get("artifact_content")
    return _digest(value)


def _load_work_sync():
    path = HERE / "work_sync.py"
    spec = importlib.util.spec_from_file_location("lancers_paid_work_sync", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("lancers_paid_inventory_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_shared(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name}_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_REPLY_COMPOSER = _load_shared(
    "lancers_paid_reply_composer",
    HERE.parents[2] / "_shared/marketplace-core/scripts/reply_composer.py",
)
_REPLY_GROUNDING = _load_shared(
    "lancers_paid_reply_grounding",
    HERE.parents[2] / "_shared/marketplace-core/scripts/reply_grounding.py",
)

DEFAULT_CANDIDATE_PROFILE = Path.home() / ".config/anicca/job-search/profile.json"
DEFAULT_PROVIDER_PROFILE = Path.home() / ".config/anicca/crowdworks/public-profile.json"
_SAFE_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{1,127}\Z")


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
        if candidate.get("source_kind") == "project_acceptance":
            return self._read_acceptance_detail(candidate)
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

    def _read_acceptance_detail(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        project_id = candidate.get("provider_id")
        proposal_id = candidate.get("proposal_id")
        if (not isinstance(project_id, str) or re.fullmatch(r"[0-9]+", project_id) is None
                or not isinstance(proposal_id, str) or not proposal_id):
            raise RuntimeError("lancers_paid_acceptance_candidate_invalid")
        self._open()
        work_sync = self._work_sync()
        verified = work_sync._read_proposal_terms(self.page, proposal_id, expected_project=project_id)
        order = work_sync._read_order_terms(self.page, project_id)
        if order is not None:
            return {
                "provider_state": "awaiting_acceptance",
                "project_id": project_id, "proposal_id": proposal_id,
                "verified_price": verified["price"],
                "verified_delivery_due_on": verified["delivery_due_on"],
                "order_amount": order["amount"],
                "order_tax_basis": order["tax_basis"],
                "order_delivery_due_on": order["max_due_on"],
                "order_milestone_count": order["milestone_count"],
                "accept_form_action": order["action"],
                "accept_fields": dict(order["fields"]),
            }
        if work_sync._read_acceptance_confirmed(self.page, project_id):
            return {"provider_state": "accepted_confirmed",
                    "project_id": project_id, "proposal_id": proposal_id}
        return {"provider_state": "acceptance_state_unknown",
                "project_id": project_id, "proposal_id": proposal_id}

    def accept_order(self, intent: Mapping[str, Any], detail: Mapping[str, Any]) -> None:
        project_id = detail.get("project_id")
        action = detail.get("accept_form_action")
        fields = detail.get("accept_fields")
        if (not isinstance(project_id, str) or re.fullmatch(r"[0-9]+", project_id) is None
                or action != f"/project/approval/finish_yes/{project_id}"
                or not isinstance(fields, Mapping) or not fields):
            raise RuntimeError("lancers_paid_acceptance_context_invalid")
        self._open()
        value = self.page.evaluate(
            """async ({path, fields}) => { const form = new FormData();
            for (const key in fields) form.append(key, fields[key]);
            const response = await fetch(path, {method:'POST', credentials:'same-origin', body:form});
            return {status: response.status}; }""",
            {"path": f"https://www.lancers.jp{action}", "fields": dict(fields)},
        )
        if not isinstance(value, Mapping) or value.get("status") not in {200, 201, 302}:
            raise RuntimeError("lancers_paid_acceptance_submission_uncertain")

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

    def _accept_readback(self, detail: Mapping[str, Any]) -> dict[str, Any]:
        project_id = detail.get("project_id")
        if not isinstance(project_id, str) or not project_id:
            return {"verified": False, "authoritative_absent": False}
        self._open()
        work_sync = self._work_sync()
        order = work_sync._read_order_terms(self.page, project_id)
        if order is not None:
            return {"verified": False, "authoritative_absent": False}
        if work_sync._read_acceptance_confirmed(self.page, project_id):
            return {"verified": True, "provider_receipt_id": f"lancers-project-approval-{project_id}",
                    "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        return {"verified": False, "authoritative_absent": False}

    def readback(self, intent: Mapping[str, Any], detail: Mapping[str, Any]) -> dict[str, Any]:
        if intent.get("action") == "accept":
            return self._accept_readback(detail)
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

    def read_inventory(self) -> Mapping[str, Any]:
        """Paid inventory through this provider's single owned page (reused for details)."""
        self._open()
        return self._work_sync().read_paid_inventory(state_path=self.state_path, page=self.page)

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
                 provider: Any | None = None,
                 state_path: Path = DEFAULT_STATE,
                 candidate_profile: Path = DEFAULT_CANDIDATE_PROFILE,
                 provider_profile: Path = DEFAULT_PROVIDER_PROFILE):
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("lancers_account_id_invalid")
        self.account_id = account_id.strip()
        self.inventory_reader = inventory_reader
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        self.provider = provider
        self.state_path = Path(state_path).expanduser().resolve()
        self.candidate_profile = Path(candidate_profile).expanduser().resolve()
        self.provider_profile = Path(provider_profile).expanduser().resolve()
        self._contexts: dict[str, dict[str, Any]] = {}

    def _compose_answer(self, contract: Mapping[str, Any]) -> str | None:
        buyer_context = contract.get("buyer_context")
        if not isinstance(buyer_context, str) or not buyer_context.strip():
            return None
        try:
            grounding = _REPLY_GROUNDING.build_reply_grounding(
                candidate_profile_path=self.candidate_profile,
                provider_profile_path=self.provider_profile,
            )
            body = _REPLY_COMPOSER.compose(
                {
                    "board": {"title": contract.get("title", "")},
                    "grounding": grounding,
                    "conversation": [{"role": "buyer", "body": buyer_context}],
                    "action_contract": {
                        "kind": "contract_answer",
                        "question": (
                            "契約済みのLancers依頼について、買い手の依頼内容を実際に満たす"
                            "回答・成果を作成してください。未実施の作業を完了と主張せず、"
                            "外部連絡先へ誘導せず、依頼本文に必要な内容だけを返してください。"
                        ),
                        "allowed_choices": [],
                    },
                    "provider_rules": {"outside_contact_before_approval": "forbidden"},
                },
                state_root=self.state_path.parent / "paid-compose",
                task_label="lancers-paid-answer",
            )
        except Exception:
            return None
        return body.strip() if isinstance(body, str) and body.strip() else None

    def _quality_check(self, contract: Mapping[str, Any], body: str) -> str | None:
        buyer_context = contract.get("buyer_context")
        if (not isinstance(buyer_context, str) or not buyer_context.strip()
                or not isinstance(body, str) or not body.strip()):
            return None
        source = "買い手の依頼:\n" + buyer_context + "\n\n送信予定の回答:\n" + body
        try:
            grounding = _REPLY_GROUNDING.build_reply_grounding(
                candidate_profile_path=self.candidate_profile,
                provider_profile_path=self.provider_profile,
            )
            value = _REPLY_COMPOSER.compose(
                {
                    "board": {"title": contract.get("title", "")},
                    "grounding": grounding,
                    "conversation": [{"role": "buyer", "body": source}],
                    "action_contract": {
                        "kind": "required_form_field",
                        "question": (
                            "この回答が依頼の全必須要件を満たし、未実施の作業を"
                            "完了と偽っていないか判定してください。"
                        ),
                        "allowed_choices": [
                            "quality_ok", "quality_needs_rework", "buyer_input_required",
                        ],
                    },
                    "provider_rules": {"outside_contact_before_approval": "forbidden"},
                },
                state_root=self.state_path.parent / "paid-compose",
                task_label="lancers-paid-quality",
            )
        except Exception:
            return None
        return value.strip() if isinstance(value, str) else None

    def _inventory(self) -> list[dict[str, Any]]:
        snapshot = self.inventory_reader()
        if (not isinstance(snapshot, Mapping) or snapshot.get("ok") is not True
                or snapshot.get("source_complete") is not True
                or not isinstance(snapshot.get("contract_candidates"), list)):
            error = RuntimeError("lancers_paid_inventory_unavailable")
            reason = snapshot.get("error") if isinstance(snapshot, Mapping) else None
            if isinstance(reason, str) and _SAFE_ERROR_CODE.fullmatch(reason):
                code = f"lancers_paid_inventory_{reason}"
                if len(code) <= 127:
                    error.paid_error_code = code
            raise error
        observed_at = self.clock()
        rows = []
        contexts: dict[str, dict[str, Any]] = {}
        for candidate in snapshot["contract_candidates"]:
            if not isinstance(candidate, Mapping):
                raise RuntimeError("lancers_paid_inventory_unavailable")
            kind = candidate.get("source_kind")
            provider_id = candidate.get("provider_id")
            funding = candidate.get("funding_status")
            if (kind not in {"project", "monthly", "storefront", "project_acceptance"}
                    or not isinstance(provider_id, str) or not provider_id):
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
                or action not in {"answer", "formal_delivery", "accept"}
                or not isinstance(payload, Mapping)):
            raise RuntimeError("lancers_paid_effect_unsupported")
        detail = self._current_detail(work_id)
        if action == "accept":
            if detail.get("provider_state") != "awaiting_acceptance":
                raise RuntimeError("lancers_paid_context_changed")
            if (payload.get("project_id") != detail.get("project_id")
                    or payload.get("order_amount") != detail.get("order_amount")
                    or payload.get("order_delivery_due_on") != detail.get("order_delivery_due_on")):
                raise RuntimeError("lancers_paid_context_changed")
            sender = getattr(self.provider, "accept_order", None)
            if not callable(sender):
                raise RuntimeError("lancers_paid_accept_effect_unavailable")
            sender(dict(intent), detail)
            return
        if detail.get("provider_state") != "funded":
            raise RuntimeError("lancers_paid_context_changed")
        event_id = payload.get("buyer_event_id")
        if not isinstance(event_id, str) or event_id != detail.get("buyer_event_id"):
            raise RuntimeError("lancers_paid_context_changed")
        body = payload.get("body") if action == "answer" else payload.get("answer_body")
        if (payload.get("correct_work_verified") is not True
                or payload.get("quality_verdict") != "quality_ok"
                or not isinstance(body, str) or not body.strip()
                or not isinstance(payload.get("quality_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", payload["quality_sha256"])
                or payload["quality_sha256"] != _quality_digest(detail, body)):
            raise RuntimeError("lancers_paid_answer_quality_unverified")
        if action == "answer":
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


def _amount_status(verified: Mapping[str, Any], order: Mapping[str, Any],
                    tax_basis: Any) -> tuple[str, list[str]]:
    """Compare a verified-proposal amount to an order amount, kind and value together.

    Never treats an ambiguous text (per-unit/recurring/range wording, or more than one
    amount) as a plain number, and never assumes a tax basis it did not read on the page.
    """
    if verified.get("kind") == "unparsed" or order.get("kind") == "unparsed":
        return "unparsed", []
    if verified.get("kind") != order.get("kind"):
        return "mismatch", [f"amount kind mismatch: order={order.get('kind')} verified_proposal={verified.get('kind')}"]
    v_amount, o_amount = verified.get("amount_jpy"), order.get("amount_jpy")
    if not isinstance(v_amount, int) or not isinstance(o_amount, int):
        return "unparsed", []
    if not isinstance(tax_basis, Mapping) or tax_basis.get("basis") not in {"inclusive", "exclusive"}:
        return "tax_unknown", []
    if tax_basis["basis"] == "exclusive":
        expected = v_amount
    else:
        rate = tax_basis.get("rate_percent")
        if not isinstance(rate, int):
            return "tax_unknown", []
        expected = round(v_amount * (100 + rate) / 100)
    if o_amount != expected:
        return "mismatch", [f"amount mismatch: order={o_amount} ({tax_basis['basis']}) verified_proposal={v_amount}"]
    return "match", []


def _decide_acceptance(contract: Mapping[str, Any]) -> dict[str, Any]:
    project_id = contract.get("project_id")
    proposal_id = contract.get("proposal_id")
    verified_price = contract.get("verified_price")
    verified_due = contract.get("verified_delivery_due_on")
    order_amount = contract.get("order_amount")
    order_tax_basis = contract.get("order_tax_basis")
    order_due = contract.get("order_delivery_due_on")
    milestone_count = contract.get("order_milestone_count")
    required = (project_id, proposal_id, verified_price, verified_due, order_amount, order_due, milestone_count)
    if any(value is None for value in required) or not isinstance(verified_price, Mapping) or not isinstance(order_amount, Mapping):
        return {"action": "wait", "reason": "acceptance_terms_unavailable",
                "remaining_work": ["read official order and verified proposal terms"]}
    status, amount_diffs = _amount_status(verified_price, order_amount, order_tax_basis)
    if status == "unparsed":
        return {"action": "wait", "reason": "acceptance_terms_unparsed",
                "remaining_work": ["re-read an unambiguous fixed amount for the proposal and the order"]}
    if status == "tax_unknown":
        return {"action": "wait", "reason": "acceptance_tax_basis_unknown",
                "remaining_work": ["read the official 税込/税抜 label and tax rate on the order page"]}
    diffs = list(amount_diffs)
    if order_due != verified_due:
        diffs.append(f"deadline mismatch: order={order_due} verified_proposal={verified_due}")
    if milestone_count != 1:
        diffs.append(f"order has {milestone_count} milestone(s), verified proposal covers one deliverable")
    if diffs:
        return {"action": "wait", "reason": "acceptance_terms_mismatch", "remaining_work": diffs}
    return {"action": "accept", "payload": {
        "project_id": project_id, "proposal_id": proposal_id,
        "order_amount": dict(order_amount), "order_delivery_due_on": order_due,
    }}


def decide(row: Mapping[str, Any], *,
           answer_selector: Callable[[Mapping[str, Any]], str | None] | None = None,
           quality_selector: Callable[[Mapping[str, Any], str], str | None] | None = None) -> dict[str, Any]:
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
    if provider_state == "awaiting_acceptance":
        return _decide_acceptance(contract)
    if provider_state == "accepted_confirmed":
        return {"action": "noop", "classification": "completed"}
    if provider_state == "acceptance_state_unknown":
        return {"action": "wait", "reason": "acceptance_state_unknown",
                "remaining_work": ["reconfirm official acceptance/working state for this project"]}
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
    context = row.get("context")
    previous_intent = context.get("previous_intent") if isinstance(context, Mapping) else None
    if (isinstance(previous_intent, Mapping)
            and context.get("previous_effect_verified") is True
            and previous_intent.get("action") == "answer"):
        return {
            "action": "wait",
            "reason": "formal_delivery_surface_unverified",
            "remaining_work": [
                "verify the official Lancers completion/delivery surface before any second effect",
            ],
        }
    body = contract.get("prepared_answer")
    if (not isinstance(body, str) or not body.strip()) and callable(answer_selector):
        body = answer_selector(contract)
    if isinstance(body, str) and body.strip() and not isinstance(contract.get("prepared_answer"), str):
        quality = quality_selector(contract, body.strip()) if callable(quality_selector) else None
        if quality != "quality_ok":
            return {
                "action": "wait", "reason": "work_quality_required",
                "remaining_work": ["produce and independently verify the contract-specific work"],
            }
        return {"action": "answer", "payload": {
            "body": body.strip(), "buyer_event_id": buyer_event_id.strip(),
            "correct_work_verified": True, "quality_verdict": quality,
            "quality_sha256": _quality_digest(contract, body),
        }}
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
    parser.add_argument("--candidate-profile", type=Path, default=DEFAULT_CANDIDATE_PROFILE)
    parser.add_argument("--provider-profile", type=Path, default=DEFAULT_PROVIDER_PROFILE)
    args = parser.parse_args(argv)
    provider = _LiveLancersProvider(state_path=args.state_path.expanduser().resolve())
    adapter = LancersPaidAdapter(
        account_id=args.account_id,
        inventory_reader=provider.read_inventory,
        provider=provider,
        state_path=args.state_path.expanduser().resolve(),
        candidate_profile=args.candidate_profile.expanduser().resolve(),
        provider_profile=args.provider_profile.expanduser().resolve(),
    )
    return adapter, lambda row: decide(
        row, answer_selector=adapter._compose_answer,
        quality_selector=adapter._quality_check,
    )


__all__ = ["LancersPaidAdapter", "build", "decide"]
