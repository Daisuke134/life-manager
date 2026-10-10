#!/usr/bin/env python3
"""Generic buyer-visible delivery and inquiry cadence decisions.

This module contains only deterministic policy.  Marketplace adapters collect
DOM facts and the model/browser worker performs the actual send.  No buyer,
request number, title, or marketplace is embedded here.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MARKETPLACE_ARTIFACT_MAX_BYTES = 190_000_000
BUYER_FORMAL_DELIVERY_HOLD_BLOCKER = "buyer_explicit_formal_delivery_hold"

_PAID_WORK_EVIDENCE: Any = None
_PAID_WORK_EVIDENCE_LOADED = False

_DELIVERY_ATTEMPT: Any = None
_DELIVERY_ATTEMPT_LOADED = False


def _paid_work_evidence() -> Any:
    """The shared BLOCKED-record reader, loaded by path, or None.

    Loaded exactly the way paid_work_evidence loads ask_buyer, and for the same
    reason: this module is imported both as a plain sibling module and through a
    file loader with no package on sys.path, so a bare ``import`` works in only
    half the callers. None is NOT "no block" -- see ``_blocked_verdict``.
    """
    global _PAID_WORK_EVIDENCE, _PAID_WORK_EVIDENCE_LOADED
    if not _PAID_WORK_EVIDENCE_LOADED:
        _PAID_WORK_EVIDENCE_LOADED = True
        try:
            spec = importlib.util.spec_from_file_location(
                "paid_work_evidence", Path(__file__).with_name("paid_work_evidence.py")
            )
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                _PAID_WORK_EVIDENCE = module
        except (OSError, ImportError, SyntaxError, ValueError):
            _PAID_WORK_EVIDENCE = None
    return _PAID_WORK_EVIDENCE


def _blocked_verdict(item: dict[str, Any]) -> str:
    """``absent``/``stale``/``fresh``/``undeterminable`` for this item's project.

    One predicate, not a second one: the verdict comes from
    ``paid_work_evidence.blocked_evidence_verdict()``, so the gate below, the
    gate in gig_pass.sh, and the question that follows them can never disagree
    about what BLOCKED means.

    A missing ``project_root`` and an unloadable reader are both
    ``undeterminable`` -- we could not look, which is not the same as looking
    and finding nothing. ``delivery_queue.build`` threads the root in from the
    delivery manifest, so a real paid item always carries one.
    """
    module = _paid_work_evidence()
    if module is None:
        return "undeterminable"
    root = str(item.get("project_root") or "").strip()
    if not root:
        return "undeterminable"
    try:
        # No requirements path is passed on purpose: the record names the file the
        # builder rewrites with the current feedback every pass, so freshness is
        # measured against the buyer's own latest words -- the same question
        # gig_pass.sh's paid_work_fresh_blocked asks. A queue item may still be
        # carrying an older manifest's requirements path, and using it here would
        # read "stale" off a block that is live.
        return str(module.blocked_evidence_verdict(root)[0])
    except Exception:  # noqa: BLE001 -- a reader that raises has not looked either
        return "undeterminable"


def _artifact_ready(item: dict[str, Any]) -> bool:
    path = str(item.get("artifact_path") or "").strip()
    version = str(item.get("artifact_version") or "").strip()
    if not path or not version or version not in Path(path).name:
        return False
    artifact = Path(path)
    if not artifact.is_file():
        return False
    if artifact.stat().st_size > MARKETPLACE_ARTIFACT_MAX_BYTES and not _linked_asset_ready(item, artifact):
        return False
    if item.get("recipient_access_required") is True:
        try:
            if artifact.suffix.casefold() == ".zip" or zipfile.is_zipfile(artifact):
                return False
        except OSError:
            return False
    return True


def _linked_asset_ready(item: dict[str, Any], artifact: Path) -> bool:
    required = item.get("required_assets")
    produced = item.get("artifact_assets")
    if not isinstance(required, list) or not required or not isinstance(produced, list):
        return False
    counts: dict[str, int] = {}
    for row in produced:
        if not isinstance(row, dict) or row.get("type") != "linked_asset":
            continue
        try:
            if Path(str(row.get("path") or "")).resolve() != artifact.resolve():
                continue
        except OSError:
            continue
        asset_id = str(row.get("asset_id") or "")
        counts[asset_id] = counts.get(asset_id, 0) + 1
    return all(
        isinstance(row, dict)
        and row.get("kind") == "linked_asset"
        and isinstance(row.get("minimum_count"), int)
        and row["minimum_count"] > 0
        and counts.get(str(row.get("asset_id") or ""), 0) >= row["minimum_count"]
        for row in required
    )


def _hash_ready(item: dict[str, Any]) -> bool:
    digest = str(item.get("package_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    path = str(item.get("artifact_path") or "")
    if path and Path(path).is_file():
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        return actual == digest
    return False


def _acceptance_ready(item: dict[str, Any]) -> bool:
    status = str(item.get("acceptance_status") or "").upper()
    # A boolean emitted by a model or local ledger is not evidence.  The
    # acceptance report must be a real file in the request-scoped workspace.
    evidence_path = str(item.get("acceptance_evidence_path") or "")
    return status in {"PASS", "REVIEW_READY"} and bool(
        evidence_path and Path(evidence_path).is_file()
    )


def _delivery_attempt() -> Any:
    """The delivery-attempt ledger reader, loaded by path, or None.

    Same loader shape and same reason as ``_paid_work_evidence`` above: this
    module is imported as a sibling and through a path loader.
    """
    global _DELIVERY_ATTEMPT, _DELIVERY_ATTEMPT_LOADED
    if _DELIVERY_ATTEMPT_LOADED:
        return _DELIVERY_ATTEMPT
    _DELIVERY_ATTEMPT_LOADED = True
    try:
        spec = importlib.util.spec_from_file_location(
            "delivery_attempt", Path(__file__).with_name("delivery_attempt.py"),
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _DELIVERY_ATTEMPT = module
    except (AssertionError, ImportError, OSError):
        _DELIVERY_ATTEMPT = None
    return _DELIVERY_ATTEMPT


def _delivered_for_this_request(item: dict[str, Any], expected: str) -> bool:
    """Did a confirmed delivery already answer this exact buyer request?

    A recorded delivery is strictly stronger evidence than the mtime comparison
    below: the mtime test asks "was the file written after we last looked at the
    room", while this asks "did the buyer receive something built for this
    request".  Order 91000002 is what the difference costs -- the collector
    rewrote the requirements sidecar at 22:21 with a fresh ``observed_at`` while
    v5, built for that same request at 22:07, sat undelivered, so the artifact
    was retroactively older than the request it answered and the order was sent
    back to work_required.

    Deliberately narrow: it fires only for projects where THIS module's
    confirmed-delivery row exists (see ``confirmed_for_feedback``), so no
    pre-existing state is reinterpreted as delivered, and a genuinely new buyer
    message carries a new digest and does not match.
    """
    module = _delivery_attempt()
    root = str(item.get("project_root") or "").strip()
    if module is None or not root:
        return False
    try:
        state = json.loads((Path(root) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(state, dict):
        return False
    return bool(module.confirmed_for_feedback(state, expected))


def _buyer_feedback_processed(item: dict[str, Any]) -> bool:
    """Bind the built artifact to the exact live buyer-feedback revision."""
    expected = str(item.get("buyer_feedback_sha256") or "").strip()
    requirements_path = str(item.get("requirements_path") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        return False
    if _delivered_for_this_request(item, expected):
        return True
    if not requirements_path:
        return False
    try:
        payload = json.loads(Path(requirements_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or payload.get("feedback_sha256") != expected:
        return False
    # ``observed_at`` is when we last WROTE this file; the artifact has to
    # postdate when the BUYER last added to the request. The two were the same
    # field until 91000002 showed what the difference costs: a rewrite carrying
    # nothing new from the buyer (c4d73e52 changed the hashing rule) moved the
    # clock past a finished, accepted v5 and sent the order back to the builder
    # for nine hours. ``feedback_first_observed_at`` is derived from the
    # content-addressed accumulation, so it moves only when they speak --
    # coconala_queue_snapshot.request_first_observed_at has the derivation.
    # Absent on sidecars written before that field existed, and the fallback is
    # then exactly the old behaviour rather than a silently skipped check.
    observed_at = str(
        payload.get("feedback_first_observed_at") or payload.get("observed_at") or ""
    ).strip()
    if observed_at:
        try:
            observed = datetime.fromisoformat(observed_at)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            artifact = Path(str(item.get("artifact_path") or ""))
            if not artifact.is_file():
                return False
            artifact_stat = artifact.stat()
            if max(artifact_stat.st_mtime, artifact_stat.st_ctime) < observed.timestamp():
                return False
        except (OSError, ValueError):
            return False
    return True


def awaiting_buyer_decision(item: dict[str, Any]) -> bool:
    """Is an open question parked on the buyer's own decision?

    "The buyer owes us an answer" and "we owe the buyer work" are different
    states and only one of them is our backlog. Order 90000004 carries an
    ``open_buyer_decisions`` row -- the size of a button, waiting on the buyer's
    own executive -- and no artifact we could build answers it. Until the
    cadence could read this, it presented as unprocessed feedback.

    Read through ``project_root`` exactly the way ``_blocked_verdict`` reads the
    BLOCKED record, so no new plumbing is needed: ``delivery_queue.build``
    already threads that field onto the cadence item. Unreadable state fails to
    False, which is the safe direction here because every caller uses a True
    only to STOP acting.
    """
    root = str(item.get("project_root") or "").strip()
    if not root:
        return False
    try:
        state = json.loads((Path(root) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    rows = state.get("open_buyer_decisions") if isinstance(state, dict) else None
    if not isinstance(rows, list):
        return False
    return any(
        isinstance(row, dict)
        and str(row.get("status") or "") == "awaiting_buyer_executive_decision"
        for row in rows
    )


def delivered_on_the_buyers_own_system(item: dict[str, Any]) -> bool:
    """Was this order delivered by changing something the buyer already owns?

    Order 90000004 was delivered by editing the buyer's own WordPress page. The
    buyer sees v16 there; v17 sits on disk from the rebuild loop and was
    deliberately never sent. Nothing in the cadence knew that, so the moment the
    parked button decision resolves, ``awaiting_buyer_decision`` goes False, the
    branch below falls through to ``formal``, and the buyer receives an HTML file
    they never asked for -- against an order that was finished on their own site.

    A formal talkroom delivery is a different channel, not a stronger version of
    the same one. Once the work has landed on the customer's system, attaching a
    file is noise at best and a second, contradictory deliverable at worst.

    Read through ``project_root`` exactly as ``awaiting_buyer_decision`` does.
    Unreadable state fails to False: this value is only ever used to STOP a send,
    so the safe direction is to let the existing gates decide.
    """
    root = str(item.get("project_root") or "").strip()
    if not root:
        return False
    try:
        state = json.loads((Path(root) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(state, dict):
        return False
    return str(state.get("delivery_channel") or "").strip() == "live_system"


def delivery_decision(item: dict[str, Any]) -> dict[str, Any]:
    """Return ``formal`` only when all independent delivery gates pass.

    A progress message is always allowed when work exists or feedback was
    observed.  It explicitly keeps the formal-delivery checkbox off, so an
    incomplete artifact can be shown to the buyer without falsely closing a
    transaction.
    """
    # An explicit buyer hold is a hard stop even when every local artifact gate
    # passes. The fixed blocker is safe to persist and cannot echo buyer text.
    # Check it before subscription/finished branches so every room shape fails
    # closed while the buyer's instruction is active.
    if item.get("buyer_formal_delivery_hold") is True:
        feedback_open = (
            item.get("buyer_feedback_pending_artifact") is True
            or item.get("buyer_reply_after_artifact_observed") is True
        )
        replacement_ready = (
            feedback_open
            and _artifact_ready(item)
            and _acceptance_ready(item)
            and _hash_ready(item)
            and _buyer_feedback_processed(item)
        )
        # Formal delivery remains held, but once a freshly built and validated
        # artifact answers the newer feedback, the buyer-visible talkroom message
        # channel is allowed to carry it.  Before that point the honest state is
        # still internal work_required, so an old held package cannot be resent.
        if replacement_ready:
            return {
                "mode": "progress",
                "formal_delivery_checkbox": False,
                "buyer_visible": True,
                "blockers": [BUYER_FORMAL_DELIVERY_HOLD_BLOCKER],
            }
        return {
            "mode": "work_required",
            "formal_delivery_checkbox": False,
            "buyer_visible": False,
            "blockers": [BUYER_FORMAL_DELIVERY_HOLD_BLOCKER],
        }
    # B4 (spec section CC'): a subscription room (定期購入, A5's room_contract_kind) has no
    # 正式な納品 checkbox and no 納品確認待ち step -- it is an ongoing service relationship,
    # not a one-shot deliverable this queue tracks. The historical "33回の納品失敗" on 買い手C
    # (talkroom 90000004) was exactly a one-shot delivery routed at a room that structurally
    # cannot accept one: every attempt drove toward a checkbox/step-bar state the room never
    # renders and died. Today the cadence happens to land on "none" for that room through
    # unrelated branches (delivered_on_the_buyers_own_system, awaiting_buyer_decision) --
    # coincidence, not a guarantee, if either of those signals ever goes quiet. Real ongoing
    # work for a subscription room travels through B1's reply/message lane, never this one,
    # so every gate below is skipped unconditionally the instant the room is known to be a
    # subscription. "unknown" (field absent, or A5's own fail-closed default) is deliberately
    # NOT handled here -- it falls straight through to the existing gates, unchanged, exactly
    # as before this field existed.
    if item.get("room_contract_kind") == "subscription":
        return {
            "mode": "none",
            "formal_delivery_checkbox": False,
            "buyer_visible": False,
            "blockers": [],
        }
    if (
        item.get("formal_delivery_observed") is True
        and item.get("talkroom_state") == "納品確認待ち"
        and item.get("buyer_visible_artifact_observed") is True
        and item.get("buyer_feedback_pending_artifact") is False
        and (
            item.get("buyer_reply_after_artifact_observed") is False
            or (
                item.get("buyer_reply_after_artifact_observed") is True
                and item.get("buyer_feedback_answered_by_seller") is True
            )
        )
    ):
        # "We delivered and the buyer has not replied, or we answered their only
        # post-artifact feedback, so there is nothing to do."
        # Exactly right when what we delivered was the work. Order 91000002 is what
        # it looks like when it was not: a 1879-byte list of things we still needed
        # to confirm went out as a formal delivery, the order left the queue, and
        # the buyer's approval clock kept running on an empty deliverable.
        #
        # A standing BLOCKED record is the builder's own statement that it could not
        # produce the deliverable for the feedback that is open right now. That
        # diagnosis outranks the fact that something was sent.
        #
        # ★ The safety direction here is the OPPOSITE of the one in
        # paid_work_evidence.validate_paid_work(), and it is opposite AGAIN to
        # gig_pass.sh's paid_work_fresh_blocked(). Three call sites now read this one
        # verdict and must NOT be "simplified" into a shared boolean. ★
        #   - validate_paid_work: asked "may I ship?" -> undeterminable REFUSES.
        #   - paid_work_fresh_blocked: asked "may I skip building and answer instead?"
        #     -> undeterminable refuses too, i.e. it is treated as not-blocked.
        #   - here: asked "may I close this order out as finished?" -> undeterminable
        #     must keep the order OPEN, so fresh AND undeterminable both fall through.
        # Every one of them says "when we cannot see, do not act"; they produce
        # opposite booleans only because acting means something different in each.
        verdict = _blocked_verdict(item)
        if verdict in ("absent", "stale"):
            return {
                "mode": "none",
                "formal_delivery_checkbox": False,
                "buyer_visible": True,
                "blockers": [],
            }
        # Fresh or undeterminable: work remains. It is deliberately NOT routed into
        # the gates below -- for 91000002 they all pass (the stub has an artifact, an
        # acceptance record and a matching hash), so falling through would re-deliver
        # the same empty document as mode "formal". There is nothing to deliver while
        # the builder still says it cannot build, so this stays internal and the
        # blocked-order question path (ask_buyer_when_blocked) is what runs next.
        return {
            "mode": "work_required",
            "formal_delivery_checkbox": False,
            "buyer_visible": False,
            "blockers": [],
        }
    # ``formal_delivery_not_confirmed`` is the action to perform, not a
    # prerequisite.  Once the artifact/acceptance/hash/agreement gates pass,
    # the worker may submit it and the next collector observes the durable
    # 納品確認待ち state.
    blockers = [
        str(x) for x in (item.get("blockers") or [])
        if str(x) and str(x) != "formal_delivery_not_confirmed"
    ]
    if not _artifact_ready(item) and "missing_versioned_artifact" not in blockers:
        blockers.append("missing_versioned_artifact")
    if not _acceptance_ready(item) and "missing_acceptance_evidence" not in blockers:
        blockers.append("missing_acceptance_evidence")
    if not _hash_ready(item) and "missing_package_hash" not in blockers:
        blockers.append("missing_package_hash")
    # A complete artifact is ready for buyer review, not ready for transaction
    # completion.  Formal delivery is an irreversible marketplace transition and
    # requires the current buyer-side message to have been semantically judged as
    # explicit approval of the already submitted artifact.  A loose keyword flag
    # such as buyer_agreement_observed is deliberately insufficient.
    approval = item.get("formal_approval_evidence")
    latest_identity = item.get("latest_buyer_message_identity") or item.get("latest_message_identity")
    formal_approval_ready = (
        str(item.get("acceptance_status") or "").upper() == "PASS"
        and
        isinstance(approval, dict)
        and isinstance(latest_identity, dict)
        and approval == latest_identity
        and approval.get("side") == "buyer"
        and bool(str(approval.get("message_id") or "").strip())
        and bool(re.fullmatch(r"[0-9a-f]{64}", str(approval.get("content_sha256") or "")))
    )
    if not formal_approval_ready and "buyer_approval_required_for_formal" not in blockers:
        blockers.append("buyer_approval_required_for_formal")
    # Unprocessed buyer feedback still blocks formal: a fresh buyer message
    # after our artifact means the current artifact may not answer it, so the
    # builder must process the feedback first (progress), then formal-deliver.
    if (
        item.get("buyer_feedback_pending_artifact") is True
        or item.get("buyer_reply_after_artifact_observed") is True
    ) and not _buyer_feedback_processed(item) and "buyer_feedback_unprocessed" not in blockers:
        blockers.append("buyer_feedback_unprocessed")
    actionable_buyer_input = (
        item.get("buyer_feedback_pending_artifact") is True
        or item.get("buyer_reply_after_artifact_observed") is True
        or item.get("buyer_feedback_stage") == "initial_request"
    )
    artifact_missing = any(
        blocker in blockers
        for blocker in (
            "missing_versioned_artifact",
            "missing_acceptance_evidence",
            "missing_package_hash",
            "artifact_exceeds_marketplace_limit",
            "buyer_feedback_unprocessed",
        )
    )
    # A buyer message that requires work is not itself a buyer-visible result.
    # Keep it durable and let the builder resume on the next wake; never turn an
    # absent artifact into a promise that something will be sent later.
    #
    # P0-1: the "actionable buyer input" half was a loophole. With no open buyer
    # message and no artifact on disk, this fell through to ``progress`` and the
    # progress payload had nothing to attach, so the only thing it could say was
    # that something would follow later. A progress message is legitimate only
    # when a real artifact exists to show; without one the honest state is
    # work_required, which stays internal.
    # A question the buyer took away for their own decision is their move, not
    # our backlog, and it is not something to formally deliver against either.
    # Reached only when nothing is actually missing, so an order that still owes
    # work is never parked here -- and a fresh buyer message re-raises
    # ``buyer_feedback_unprocessed``, which puts ``artifact_missing`` back and
    # sends the order to work_required past this branch. It therefore cannot
    # freeze an order: only the buyer's own silence holds it.
    if not artifact_missing and awaiting_buyer_decision(item):
        return {
            "mode": "none",
            "formal_delivery_checkbox": False,
            "buyer_visible": True,
            "blockers": blockers,
            "awaiting_buyer_decision": True,
        }
    # The order was finished on the buyer's own system, so there is no file to
    # formally deliver -- the deliverable is already live where they can see it.
    # Placed after the parked-decision branch and before the mode choice below,
    # because the danger is precisely the fall-through: the moment a parked
    # decision resolves, the branch above stops firing and an artifact that was
    # never meant to be sent becomes a formal delivery.
    if not artifact_missing and delivered_on_the_buyers_own_system(item):
        return {
            "mode": "none",
            "formal_delivery_checkbox": False,
            "buyer_visible": True,
            "blockers": blockers,
            "delivered_on_live_system": True,
        }
    if artifact_missing and (actionable_buyer_input or not _artifact_ready(item)):
        mode = "work_required"
    else:
        mode = "formal" if not blockers else "progress"
    # A1's live-DOM signal, consumed for branching (B5 arriving inside B3): while a
    # prior formal delivery awaits the buyer (納品確認待ち), the formal checkbox is
    # DISABLED in the live room -- measured on 90000002, disabled=True on every
    # snapshot since 16:30 on 2026-08-08. A formal mode here is physically
    # impossible: the browser would upload, type, and then fail on an unclickable
    # box, leaving compose residue in the real form, once per pass. The revision
    # goes out as a progress message instead -- the channel the buyer answers
    # revisions through anyway -- and formal escalation stays reserved for rooms
    # whose checkbox is actually enabled. ``is True`` on both live fields so an
    # older snapshot without them keeps today's behaviour exactly.
    if (
        mode == "formal"
        and item.get("formal_delivery_control_disabled") is True
        and item.get("formal_delivery_observed") is True
        and item.get("talkroom_state") == "納品確認待ち"
    ):
        mode = "progress"
    return {
        "mode": mode,
        "formal_delivery_checkbox": mode == "formal",
        "buyer_visible": mode != "work_required",
        "blockers": blockers,
    }


def progress_payload(item: dict[str, Any]) -> dict[str, Any]:
    """Build a concise, buyer-visible progress update for the current pass.

    Buyer-facing text must read like a person wrote it. Internal blocker
    identifiers, ledger field names, and hashes never appear here — they stay
    in the evidence ledger (Dais ruling 2026-07-25 after
    "残課題: buyer_feedback_unprocessed" leaked to a real buyer).
    """
    decision = delivery_decision(item)
    version = str(item.get("artifact_version") or "未生成")
    delta = [str(x) for x in (item.get("acceptance_delta") or []) if str(x)]
    blockers = decision["blockers"]
    if delta:
        # Keep it scannable: lead with the update, list the changes plainly.
        changes = "\n".join(f"・{line}" for line in delta[:8])
        message = (
            f"お世話になっております。修正版 {version} をお送りします。\n"
            f"今回の主な変更点です。\n{changes}\n"
            "ご確認いただき、気になる点があれば遠慮なくお知らせください。"
        )
    elif _artifact_ready(item):
        # An artifact exists and is what gets attached, so the message describes
        # a send that is actually happening. It carries no promise about future
        # work: an empty change list only means we have no bullet points to add,
        # not that the deliverable is still coming.
        message = (
            f"お世話になっております。{version} をお送りします。"
            "ご確認いただき、気になる点があれば遠慮なくお知らせください。"
        )
    else:
        # P0-1: nothing to attach means nothing to say. The old branch here
        # shipped "まとまり次第あらためてお送りしますので、少しお待ちください" --
        # a contentless promise standing in for work that does not exist.
        # delivery_decision already routes this state to work_required; this is
        # the belt for any direct caller, and it is deliberately not
        # buyer-visible.
        return {
            "mode": "work_required",
            "formal_delivery_checkbox": False,
            "buyer_visible": False,
            "artifact_version": version,
            "acceptance_delta": delta,
            "blockers": blockers,
            "message": "",
        }
    # A progress payload is intentionally buyer-visible even when the formal
    # delivery gate is not met; the worker must attach only the artifact that
    # actually exists and must not tick the formal checkbox.
    return {
        "mode": "progress",
        "formal_delivery_checkbox": False,
        "buyer_visible": True,
        "artifact_version": version,
        "acceptance_delta": delta,
        "blockers": blockers,
        "message": message,
    }


def inquiries_from_dom(dom: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize open conversation cards into a generic reply queue.

    Buyer identity and raw message text are deliberately excluded.  The
    talkroom URL and bounded title are enough for the browser worker to reopen
    the conversation and compose a context-aware response from the live DOM.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in dom.get("cards", []):
        if not isinstance(card, dict):
            continue
        href = str(card.get("talkroom_url") or "")
        parsed = urlsplit(href)
        match = re.fullmatch(
            r"/(talkrooms|mypage/direct_message|smartphone/direct_messages)/([A-Za-z0-9_-]+)",
            parsed.path.rstrip("/"),
        )
        if not match:
            continue
        route, talkroom_id = match.groups()
        if route == "smartphone/direct_messages":
            route = "mypage/direct_message"
        if talkroom_id in seen:
            continue
        seen.add(talkroom_id)
        title = re.sub(r"\s+", " ", str(card.get("title") or "")).strip()[:200]
        last_side = str(card.get("last_message_side") or "").lower()
        reply_required = (
            last_side == "buyer"
            if last_side in {"buyer", "seller"}
            else bool(card.get("unread"))
        )
        rows.append({
            "talkroom_id": talkroom_id,
            "talkroom_url": f"https://coconala.com/{route}/{talkroom_id}",
            "title": title,
            "reply_required": reply_required,
            "next_action": "reply" if reply_required else "observe",
        })
    return rows


def inquiry_reply_instruction(row: dict[str, Any]) -> dict[str, Any]:
    """Return a generic bounded instruction for one live conversation."""
    return {
        "talkroom_id": str(row.get("talkroom_id") or ""),
        "talkroom_url": str(row.get("talkroom_url") or ""),
        "mode": "reply",
        "message": "ご連絡ありがとうございます。内容を確認し、対応可能な範囲・納期・次の確認事項を具体的にご案内します。",
    }


def validate_inquiry_evidence(evidence_dir: str | Path, expected_ids: list[str]) -> tuple[bool, list[str]]:
    """Validate machine-readable post-send proof for every reply action.

    The browser worker must write ``inquiry-actions.json``.  A model's JSON
    acknowledgement is not enough: each expected room needs a real screenshot,
    a canonical talkroom URL, and a bounded live-DOM observation captured
    after the send.
    """
    root = Path(evidence_dir)
    manifest = root / "inquiry-actions.json"
    try:
        rows = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, ["missing_inquiry_actions_manifest"]
    if not isinstance(rows, list):
        return False, ["inquiry_actions_manifest_not_array"]
    by_id = {str(row.get("talkroom_id")): row for row in rows if isinstance(row, dict)}
    errors: list[str] = []
    root_resolved = root.resolve()
    for room_id in expected_ids:
        row = by_id.get(str(room_id))
        if not row:
            errors.append(f"missing_inquiry_action:{room_id}")
            continue
        url = str(row.get("url") or "")
        if url != f"https://coconala.com/talkrooms/{room_id}":
            errors.append(f"invalid_inquiry_url:{room_id}")
        screenshot = Path(str(row.get("screenshot_path") or ""))
        try:
            screenshot.resolve().relative_to(root_resolved)
            screenshot_owned = True
        except ValueError:
            screenshot_owned = False
        if not screenshot_owned or not screenshot.is_file() or screenshot.stat().st_size == 0:
            errors.append(f"missing_inquiry_screenshot:{room_id}")
        live_dom_path = Path(str(row.get("live_dom_path") or ""))
        try:
            live_dom_path.resolve().relative_to(root_resolved)
            live_dom_owned = True
        except ValueError:
            live_dom_owned = False
        try:
            live_dom = json.loads(live_dom_path.read_text(encoding="utf-8")) if live_dom_owned else None
        except (OSError, json.JSONDecodeError):
            live_dom = None
        if not isinstance(live_dom, dict) or live_dom.get("url") != url or live_dom.get("reply_sent") is not True:
            errors.append(f"missing_post_send_live_dom:{room_id}")
        if row.get("sent") is not True:
            errors.append(f"reply_not_observed_sent:{room_id}")
    return not errors, errors


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-inquiry")
    validate.add_argument("--evidence-dir", required=True, type=Path)
    validate.add_argument("--expected-ids", required=True, type=Path)
    args = parser.parse_args()
    expected = json.loads(args.expected_ids.read_text(encoding="utf-8"))
    ok, errors = validate_inquiry_evidence(args.evidence_dir, [str(x) for x in expected])
    print(json.dumps({"ok": ok, "errors": errors}, ensure_ascii=False, separators=(",", ":")))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
