#!/usr/bin/env python3
"""Build the Gig action queue from authenticated marketplace state plus delivery evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from delivery_cadence import delivery_decision, progress_payload
    from delivery_identity import stable_identity
except ModuleNotFoundError:  # direct import through the test loader
    import importlib.util
    _cadence_spec = importlib.util.spec_from_file_location(
        "delivery_cadence", Path(__file__).with_name("delivery_cadence.py")
    )
    if _cadence_spec is None or _cadence_spec.loader is None:
        raise
    _cadence = importlib.util.module_from_spec(_cadence_spec)
    _cadence_spec.loader.exec_module(_cadence)
    delivery_decision = _cadence.delivery_decision
    progress_payload = _cadence.progress_payload
    _identity_spec = importlib.util.spec_from_file_location(
        "delivery_identity", Path(__file__).with_name("delivery_identity.py")
    )
    if _identity_spec is None or _identity_spec.loader is None:
        raise
    _identity = importlib.util.module_from_spec(_identity_spec)
    _identity_spec.loader.exec_module(_identity)
    stable_identity = _identity.stable_identity


QUEUE_PRIORITY = {
    "overdue_or_today_paid_deliverable": 0,
    "buyer_feedback_or_revision": 1,
    "quote_needing_proposal": 2,
    "other_paid_work": 3,
    "nurture": 4,
    "listing_apply_learn": 5,
}
MARKETPLACE_ARTIFACT_MAX_BYTES = 190_000_000
# A5: strictly above every QUEUE_PRIORITY value, and deliberately NOT a new queue_class.
# Every consumer keys on the class string -- b2_queue_gate, paid_progress_finalize_gate,
# and above all the `case "$TOP_CLASS"` arm in gig_pass.sh:2318, which names the three paid
# classes. A fourth string would match no arm, so an order escalated by inventing one would
# reach the top of the queue and have nothing run on it at all. The class stays a value
# every consumer already knows; only the sort position moves.
FIRST_CONTACT_PRIORITY = -1


def first_contact_at_risk(item: dict[str, Any], now: datetime | None) -> bool:
    """Is the marketplace's own cancellation clock running on an order we never answered?

    Two orders were coupled on 2026-08-07: 買い手B sat at the top of the queue in a
    rebuild loop, and the pass hands PAID_WORK exactly one item, so 買い手A -- purchased
    22:38, auto-cancelling 8/9 23:00 unless a seller message existed -- could not be
    reached while it stayed second. The delivery date said 8/20 and nothing in the loop
    held the other clock, so the order looked comfortable right up until it would vanish.

    ★ Preempting a mid-revision order is the deliberate choice here. ★ It costs the
    revision buyer one pass (they are already talking to us, and the loop wakes hourly);
    not making first contact costs the entire order and its fee. The queue measured on the
    live 23:07 snapshot has three items, all buyer_feedback_or_revision, so this promotes
    one order past two -- it does not reorder a long tail.

    Both retraction paths are live-DOM facts, so nothing has to remember that we replied:
    coconala stops rendering the banner once any seller message exists (deadline becomes
    None), and our own capture independently reports seller_message_observed.
    """
    if item.get("seller_message_observed") is True:
        return False
    raw = str(item.get("contact_deadline") or "")
    if not raw:
        return False
    try:
        deadline = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if deadline.tzinfo is None or now is None:
        # An unanchored deadline cannot be compared, and a comparison we cannot make is
        # not permission to pin an order to the top of the queue forever.
        return False
    # Past its deadline the order is already cancelled or beyond saving; promoting it then
    # would starve live work on behalf of one that no longer exists.
    return deadline > now


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def normalized(value: Any) -> str:
    return re.sub(r"\W+", "", str(value or "").casefold())


def duplicate_order_quote(order: dict[str, Any], quote: dict[str, Any]) -> bool:
    order_request = str(order.get("request_id") or "")
    quote_request = str(quote.get("request_id") or "")
    if order_request and quote_request:
        return order_request == quote_request
    if normalized(order.get("buyer")) != normalized(quote.get("buyer")):
        return False
    order_title = normalized(order.get("title"))
    quote_title = normalized(quote.get("title"))
    return bool(order_title and quote_title and (order_title == quote_title or order_title in quote_title or quote_title in order_title))


def evidence_path(root: Path, item: dict[str, Any]) -> Path:
    return root / f"{stable_identity(item)}.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_active_paid_order(order: dict[str, Any]) -> bool:
    """Keep a live returned/revision order when the card status is ambiguous.

    Coconala's received-orders card can omit the paid label after a formal
    delivery is returned.  The authenticated talkroom and structured order
    fields are the safe fallback; free-form card text is never enough.

    C3a (2026-08-01): ``status`` is ``"paid" if "取引中" in card text else
    "unknown"``, so a paid order whose card does not render 取引中 arrives here.
    Both live-revision booleans are false for a quiet new order -- the buyer
    wrote a plain brief with no ACTIONABLE keyword and no attachment -- so such
    an order used to be dropped from the queue entirely, before routing even
    applied.  A persisted ``initial_request`` intake is the missing live fact:
    the collector read their brief off the authenticated talkroom and we have
    delivered nothing.  Every other guard still has to hold.
    """
    targeted = order.get("selection_stage") == "targeted"
    if order.get("selection_stage") == "preliminary" or order.get("targeted_readback_required") is True:
        return False
    if order.get("status") == "paid" and not targeted:
        return True
    if order.get("status") not in {"unknown", "paid"}:
        return False
    try:
        price = int(order.get("price_jpy"))
    except (TypeError, ValueError):
        return False
    live_revision = (
        order.get("buyer_feedback_pending_artifact") is True
        or order.get("buyer_reply_after_artifact_observed") is True
        or order.get("buyer_feedback_stage") in {"initial_request", "revision"}
        # A5: a buyer who paid and then wrote nothing at all trips none of the three above,
        # so an order whose card also fails to render 取引中 was dropped here -- before any
        # class, priority or clock could apply to it. The marketplace rendering its own
        # cancellation countdown at us is proof that a live paid transaction exists and
        # that it is our silence being counted; it is a live fact of the same kind as an
        # initial_request intake, and the quietest orders are exactly the ones this
        # deadline exists to kill.
        or bool(order.get("contact_deadline"))
    )
    live_paid_state = (
        order.get("talkroom_state") == "取引中"
        or (
            order.get("talkroom_state") == "納品確認待ち"
            and order.get("formal_delivery_observed") is True
        )
        or order.get("room_contract_kind") == "subscription"
    )
    # A buyer can explicitly hold formal delivery after the marketplace has already
    # rendered the room as completed.  That terminal-looking card is not proof that
    # the paid work is settled when the same live capture carries newer actionable
    # feedback: the buyer is asking us to replace the held artifact before the work
    # is complete.  Keep this narrow to the structured paid identity, an explicit
    # hold, and an unprocessed artifact/revision signal; ordinary completed rooms
    # remain excluded.
    held_feedback_reopened = (
        order.get("talkroom_state") == "取引完了"
        and order.get("buyer_formal_delivery_hold") is True
        and order.get("formal_delivery_observed") is not True
        and live_revision
    )
    return (
        price > 0
        and str(order.get("price_source") or "").startswith("structured")
        and bool(order.get("contract_id"))
        and bool(order.get("talkroom_id"))
        and (live_paid_state or held_feedback_reopened)
        and live_revision
    )


def ledger_confirms_delivery(
    item: dict[str, Any], package_sha256: str, projects_root: Path
) -> bool:
    """Has THIS package already been formally delivered, per the project ledger?

    Talkroom 90000004 (定期購入) was delivered and site-verified at 2026-08-06 05:33, and
    every later pass still re-queued it: the live check below only recognises the one-shot
    room's 納品確認待ち step, which a subscription room never shows. The ledger row written
    by the delivery browser after its own site readback is the durable fact.

    Bound to the artifact hash on purpose: a ledger row for v11 says nothing about the v12
    now sitting in the queue, so new versions of the same project still queue.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", package_sha256 or ""):
        return False
    try:
        identity = stable_identity(item)
    except ValueError:
        return False
    ledger = Path(projects_root).expanduser() / identity / "events.jsonl"
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(row, dict)
            and row.get("event") == "FORMAL_DELIVERY_CONFIRMED"
            and str(row.get("artifact_sha256") or "").lower() == package_sha256.lower()
        ):
            return True
    return False


def held_event_matches(ledger: Path, package_sha256: str) -> bool:
    try:
        rows = ledger.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in rows:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("event") != "formal_delivery_observed_held":
            continue
        nested = row.get("state") if isinstance(row.get("state"), dict) else row
        if str(nested.get("delivery_send_suppressed_package_sha256") or "").lower() == package_sha256.lower() or str(row.get("delivery_send_suppressed_package_sha256") or "").lower() == package_sha256.lower():
            return True
    return False


def held_package_suppression(item: dict[str, Any], evidence: dict[str, Any], package_sha256: str) -> bool:
    """Suppress only the package observed in the terminal buyer-hold recovery."""
    if not (
        item.get("buyer_formal_delivery_hold") is True
        and item.get("talkroom_state") == "取引完了"
        and item.get("formal_delivery_control_disabled") is True
        and re.fullmatch(r"[0-9a-f]{64}", package_sha256 or "")
    ):
        return False
    root_value = str(evidence.get("project_root") or item.get("project_root") or "").strip()
    if not root_value:
        return False
    root = Path(root_value).expanduser()
    try:
        state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    state_match = (
        isinstance(state, dict)
        and state.get("terminal_state") == "site_observed_buyer_hold"
        and str(state.get("delivery_send_suppressed_package_sha256") or "").lower()
        == package_sha256.lower()
    )
    # The hold is package-scoped.  A later buyer feedback digest reopens the work
    # even though the old package remains terminally suppressed; otherwise the
    # queue would keep returning ``none`` and never let the builder produce the
    # requested replacement.
    current_feedback = str(item.get("buyer_feedback_sha256") or "").strip().lower()
    handled_feedback = str(state.get("handled_buyer_feedback_sha256") or "").strip().lower()
    if current_feedback and current_feedback != handled_feedback:
        return False
    return state_match or held_event_matches(root / "events.jsonl", package_sha256)


DEFAULT_PROJECTS_ROOT = Path("~/gig/projects")


OPEN_ORDERS_ROUTE = "https://coconala.com/mypage/received_orders/open"
LIVE_SNAPSHOT_SOURCES = {
    "authenticated_coconala_default_context_dom",
    "authenticated_coconala_hidden_default_context_dom",
}


def build_preliminary(snapshot: dict[str, Any], today: date) -> dict[str, Any]:
    """Build a selection-only queue from a fully covered orders-only snapshot."""
    if not isinstance(snapshot, dict):
        raise ValueError("preliminary snapshot must be an object")
    if (
        snapshot.get("source") not in LIVE_SNAPSHOT_SOURCES
        or snapshot.get("read_only") is not True
        or snapshot.get("collector_mode") != "orders-only"
        or snapshot.get("observed_sources") != ["orders"]
        or snapshot.get("open_orders_list_observed") is not True
    ):
        raise ValueError("preliminary queue requires covered authenticated orders-only snapshot")
    orders = snapshot.get("orders")
    receipt = snapshot.get("source_receipt")
    if not isinstance(orders, list) or not isinstance(receipt, dict):
        raise ValueError("preliminary queue requires orders and source_receipt")
    receipt_contract = {"source": "orders", "requested_route": OPEN_ORDERS_ROUTE,
                        "final_route": OPEN_ORDERS_ROUTE, "login_redirect": False,
                        "coverage_complete": True}
    if (
        any(receipt.get(key) != expected for key, expected in receipt_contract.items())
        or type(receipt.get("cards_count")) is not int
        or receipt.get("cards_count") != len(orders)
        or receipt.get("empty_state_present") is not (len(orders) == 0)
    ):
        raise ValueError("preliminary queue requires a complete orders source receipt")

    items: list[dict[str, Any]] = []
    for index, source in enumerate(orders):
        if not isinstance(source, dict):
            raise ValueError(f"preliminary order row {index} is malformed")
        talkroom_id = source.get("talkroom_id")
        if (
            not isinstance(talkroom_id, str) or not re.fullmatch(r"[0-9]+", talkroom_id)
            or source.get("contract_id") != f"talkroom:{talkroom_id}"
            or source.get("marketplace_url") != f"https://coconala.com/talkrooms/{talkroom_id}"
            or source.get("status") not in {"unknown", "paid"}
        ):
            raise ValueError(f"preliminary order row {index} has invalid identity or status")
        item = dict(source)
        queue_class = "overdue_or_today_paid_deliverable" if str(
            item.get("delivery_date") or "9999-12-31"
        ) <= today.isoformat() else "other_paid_work"
        item.update({
            "snapshot_captured_at": snapshot.get("captured_at"),
            "queue_class": queue_class,
            "priority": QUEUE_PRIORITY[queue_class],
            "selection_stage": "preliminary",
            "targeted_readback_required": True,
            "delivery_ready": False,
            "delivery_action": "none",
            "blockers": ["targeted_talkroom_readback_required"],
        })
        items.append(item)
    items.sort(key=lambda item: (
        str(item.get("delivery_date") or "9999-12-31"),
        -int(item.get("price_jpy") or 0),
        stable_identity(item),
    ))
    return {
        "version": 1,
        "captured_at": snapshot.get("captured_at"),
        "today": today.isoformat(),
        "source": snapshot.get("source"),
        "selection_stage": "preliminary",
        "items": items,
    }


def delivery_gate(
    item: dict[str, Any],
    evidence_root: Path,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
) -> tuple[dict[str, Any], list[str]]:
    path = evidence_path(evidence_root, item)
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(evidence, dict):
            evidence = {}
    except (OSError, json.JSONDecodeError):
        evidence = {}
    blockers: list[str] = []
    artifact_value = evidence.get("artifact_path")
    artifact = Path(os.path.expanduser(str(artifact_value))) if artifact_value else None
    version = str(evidence.get("artifact_version") or "")
    if not artifact or not artifact.is_file() or not version or version not in artifact.name:
        blockers.append("missing_versioned_artifact")
    elif artifact.stat().st_size > MARKETPLACE_ARTIFACT_MAX_BYTES and not _linked_asset_ready(evidence, artifact):
        blockers.append("artifact_exceeds_marketplace_limit")
    acceptance_value = evidence.get("acceptance_evidence_path")
    acceptance = Path(os.path.expanduser(str(acceptance_value))) if acceptance_value else None
    if evidence.get("acceptance_status") not in {"PASS", "REVIEW_READY"} or not acceptance or not acceptance.is_file():
        blockers.append("missing_acceptance_evidence")
    package_hash = str(evidence.get("package_sha256") or "")
    if not artifact or not artifact.is_file() or not re.fullmatch(r"[0-9a-f]{64}", package_hash) or sha256_file(artifact) != package_hash:
        blockers.append("missing_package_hash")
    suppressed = not blockers and held_package_suppression(item, evidence, package_hash)
    snapshot_time = item.get("snapshot_captured_at")
    live_formal = (
        item.get("formal_delivery_observed") is True
        and item.get("buyer_visible_artifact_observed") is True
        and item.get("talkroom_state") == "納品確認待ち"
        and bool(snapshot_time)
        and item.get("talkroom_observed_at") == snapshot_time
        and bool(re.fullmatch(r"[0-9a-f]{64}", str(item.get("talkroom_evidence_sha256") or "")))
        and bool(re.fullmatch(r"[0-9a-f]{64}", str(item.get("talkroom_screenshot_sha256") or "")))
    )
    if suppressed:
        return {"path": str(path), "present": path.is_file(), **evidence, "resend_suppressed": True, "delivery_send_suppressed_package_sha256": package_hash}, []
    if not live_formal and not ledger_confirms_delivery(item, package_hash, projects_root):
        blockers.append("formal_delivery_not_confirmed")
    return {"path": str(path), "present": path.is_file(), **evidence}, blockers


def _linked_asset_ready(evidence: dict[str, Any], artifact: Path) -> bool:
    required = evidence.get("required_assets")
    produced = evidence.get("artifact_assets")
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


def build(snapshot: dict[str, Any], evidence_root: Path, today: date) -> dict[str, Any]:
    # A5: the contact clock is stated to the minute, so `today` is too coarse to compare
    # against it. The snapshot's own capture time is the honest "now" -- it is the instant
    # the banner was read, and the production path already refuses a snapshot older than
    # --max-age-seconds, so it cannot drift far from wall clock.
    try:
        observed_now = datetime.fromisoformat(str(snapshot.get("captured_at") or ""))
    except ValueError:
        observed_now = None
    if observed_now is not None and observed_now.tzinfo is None:
        observed_now = None
    quotes = [q for q in snapshot.get("quotes", []) if q.get("status") == "proposal_required"]
    paid = []
    for source in snapshot.get("orders", []):
        if not is_active_paid_order(source):
            continue
        item = dict(source)
        # Normalize the ambiguous card state before priority/cadence logic so
        # downstream workers cannot mistake a returned paid order for a quote.
        item["status"] = "paid"
        paid.append(item)
    # A stale proposal may remain visible during the quote -> purchased
    # transition. Paid is authoritative; remove only the stale quote.
    quotes = [quote for quote in quotes if not any(duplicate_order_quote(order, quote) for order in paid)]
    items: list[dict[str, Any]] = []
    for source in paid:
        item = dict(source)
        item["snapshot_captured_at"] = snapshot.get("captured_at")
        due = None
        try:
            due = date.fromisoformat(str(item.get("delivery_date")))
        except (TypeError, ValueError):
            pass
        # C3a (2026-08-01): this class is the ONLY one that reaches the builder.
        # run_paid_work has a single call site, gig_pass.sh:1671, gated on
        # TOP_CLASS = buyer_feedback_or_revision; the other two paid classes skip
        # the builder and go straight to assess_paid_queue. A quiet new order
        # ("よろしくお願いします。以下の内容でお願いします") trips none of the three
        # booleans below -- ACTIONABLE does not match and there is no attachment,
        # so latest_actionable stays -1 and `-1 > -1` is false -- and would never
        # get an artifact built at all. An initial_request intake means the
        # collector holds their brief and we have delivered nothing: that is
        # unfinished paid work waiting on us, which is what this class means.
        # This is a re-classification into an existing class, never a new class
        # string: every consumer that keys on the value (b2_queue_gate,
        # QUEUE_PRIORITY, paid_progress_finalize_gate, the gig_pass case arm)
        # keeps seeing a value it already knows.
        if (
            item.get("buyer_feedback_pending_artifact")
            or item.get("buyer_reply_after_artifact_observed")
            or item.get("revision_requested")
            or item.get("buyer_feedback_stage") in {"initial_request", "revision"}
        ):
            queue_class = "buyer_feedback_or_revision"
        elif due and due <= today:
            queue_class = "overdue_or_today_paid_deliverable"
        else:
            queue_class = "other_paid_work"
        delivery_evidence, blockers = delivery_gate(item, evidence_root)
        # Live talkroom facts are authoritative.  Local evidence may supply
        # only artifact/acceptance facts; it must never forge buyer consent,
        # formal state, visibility, timestamps, or live hashes.
        cadence_item = dict(item)
        for key in (
            # project_root is the builder's own workspace, recorded in the manifest it
            # writes. delivery_decision needs it to see a standing BLOCKED record before
            # it closes a formally-delivered order out as finished; without it the
            # cadence cannot tell an empty delivery from a real one.
            "project_root",
            "requirements_path", "artifact_path", "artifact_version", "acceptance_evidence_path",
            "acceptance_status", "package_sha256", "acceptance_delta", "recipient_access_required",
        ):
            if key in delivery_evidence:
                cadence_item[key] = delivery_evidence[key]
        cadence_item["blockers"] = blockers
        suppressed = delivery_evidence.get("resend_suppressed") is True
        cadence = {"mode": "none", "formal_delivery_checkbox": False, "buyer_visible": False, "blockers": []} if suppressed else delivery_decision(cadence_item)
        at_risk = first_contact_at_risk(item, observed_now)
        item.update({
            "queue_class": queue_class,
            "first_contact_at_risk": at_risk,
            "priority": FIRST_CONTACT_PRIORITY if at_risk else QUEUE_PRIORITY[queue_class],
            "delivery_evidence": delivery_evidence,
            "blockers": blockers,
            "delivery_ready": not blockers,
            # Missing work remains internal and durable. Buyer-visible progress
            # exists only when a real artifact has crossed the evidence gates.
            "delivery_action": cadence["mode"],
            "formal_delivery_checkbox": cadence["formal_delivery_checkbox"],
            "progress_payload": progress_payload(cadence_item) if cadence["mode"] == "progress" else None,
            "resend_suppressed": suppressed,
            "delivery_send_suppressed_package_sha256": delivery_evidence.get("delivery_send_suppressed_package_sha256") if suppressed else None,
        })
        items.append(item)
    for source in quotes:
        item = dict(source)
        item.update({
            "queue_class": "quote_needing_proposal",
            "priority": QUEUE_PRIORITY["quote_needing_proposal"],
            "blockers": [],
            "delivery_ready": False,
        })
        items.append(item)
    items.sort(key=lambda item: (
        item["priority"],
        # Among orders about to be cancelled, the nearest cancellation wins -- delivery_date
        # is the wrong clock for exactly the items promoted by the wrong-clock defect.
        str(item.get("contact_deadline") or "") if item.get("first_contact_at_risk") else "",
        item.get("delivery_date") or item.get("proposal_due") or "9999-12-31",
        -int(item.get("price_jpy") or 0),
        str(item.get("contract_id") or ""),
    ))
    return {
        "version": 1,
        "captured_at": snapshot.get("captured_at"),
        "today": today.isoformat(),
        "source": snapshot.get("source", "fixture_or_normalized_snapshot"),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--snapshot", required=True, type=Path)
    build_parser.add_argument("--delivery-evidence-dir", required=True, type=Path)
    build_parser.add_argument("--today", default=date.today().isoformat())
    build_parser.add_argument("--output", required=True, type=Path)
    build_parser.add_argument("--require-live-source", action="store_true")
    build_parser.add_argument("--max-age-seconds", type=int, default=300)
    preliminary_parser = subparsers.add_parser("preliminary")
    preliminary_parser.add_argument("--snapshot", required=True, type=Path)
    preliminary_parser.add_argument("--today", default=date.today().isoformat())
    preliminary_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if args.command == "preliminary":
            result = build_preliminary(snapshot, date.fromisoformat(args.today))
        else:
            if args.require_live_source:
                if snapshot.get("source") not in LIVE_SNAPSHOT_SOURCES or snapshot.get("read_only") is not True:
                    raise ValueError("production queue requires a read-only authenticated live DOM snapshot")
                captured = datetime.fromisoformat(str(snapshot.get("captured_at") or ""))
                if captured.tzinfo is None:
                    raise ValueError("live DOM snapshot timestamp lacks timezone")
                age = (datetime.now(timezone.utc) - captured.astimezone(timezone.utc)).total_seconds()
                if age < -30 or age > args.max_age_seconds:
                    raise ValueError(f"live DOM snapshot is stale (age_seconds={age:.0f})")
            result = build(snapshot, args.delivery_evidence_dir, date.fromisoformat(args.today))
        atomic_json(args.output, result)
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "success", "items": len(result["items"]), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
