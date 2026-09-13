#!/usr/bin/env python3
"""One-shot, evidence-bound Coconala formal delivery over an owned CDP tab."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import websockets

import artifact_judge
import first_contact
import paid_work_evidence
import predelivery_score
import coconala_paid_progress_browser as progress
import coconala_queue_snapshot as collector
import project_ledger
from buyer_voice import check_style, normalize_for_match

# EV1 instrumentation; see artifact_judge for why the import itself must be able to fail.
try:
    from trajectory import record as record_trajectory
except Exception:  # noqa: BLE001 - instrumentation may never break its host
    def record_trajectory(**_kwargs: Any) -> None:  # type: ignore[misc]
        return None


# How much of our own message has to reappear in the room for a row to be ours.
#
# The head, not the tail: Coconala truncates long messages behind 「続きを読む」, and the
# sha256 that used to serve as this key sat at the very end -- the part most likely to be
# hidden. Kept short for the same reason; a longer needle re-exposes us to truncation.
#
# 40 whitespace-free characters of our opening is largely shared boilerplate, and that is
# deliberate rather than a weakness. Paired with the attachment-name condition, the
# identity asserted is "a row from us carrying this artifact" -- which is exactly the
# dedupe semantics the caller needs.
DELIVERY_MATCH_PREFIX = 40

# Beyond this, the quoted scope reads as a list wearing a sentence's clothes, so the line
# is dropped instead. Measured against the real 91000002 delta, whose three items render as
# 69 characters of quoted clauses jammed into one sentence -- the bullet report again.
SCOPE_MAX_CHARS = 60


def delivery_message(
    artifact_name: str, acceptance_delta: list[str], google_doc_link: str | None = None
) -> str:
    """What the buyer actually reads when we deliver.

    Replaces the template that produced the 2026-08-06 message to order 91000002: a
    「確認した内容は以下のとおりです」 header over ・bullets of our own internal acceptance
    notes, signed with a sha256. That is a build report, and the buyer correctly read it as
    a machine talking to itself.

    The delta still appears -- it is the honest answer to "what did I just get" -- but as
    a short quoted clause inside a sentence rather than a list. Quoting also makes this
    safe for arbitrary delta text: the items are written by the build agent in whatever
    shape it likes, and 「...」 keeps any of them grammatical.

    At most two items, and none at all when they are long. Three long clauses quoted into
    a single sentence is the bullet report with a different hat on, and no person writes
    that. A delivery with no scope line still works: the attachment names what arrived and
    the closing line invites the reply that would ask for more.

    ``google_doc_link`` is §EM' (2026-08-09): order 91000001 asked for delivery
    「グーグルドキュメントで」. The file attachment stays the source of truth (unchanged
    above); when the builder also published a Google Doc via
    scripts/google_docs_publisher.py, the link is appended so the buyer can open the
    format they actually asked for. None (the default, and every delivery before this
    one) reproduces today's message byte-for-byte.
    """
    items = [str(line).strip().rstrip("。.") for line in acceptance_delta if str(line).strip()]
    quoted = "".join(f"「{item}」" for item in items[:2])
    more = "ほか" if len(items) > 2 else ""
    scope = (
        f"今回対応したのは{quoted}{more}です。\n"
        if quoted and len(quoted) <= SCOPE_MAX_CHARS
        else ""
    )
    doc_line = f"\n\nGoogleドキュメント（閲覧・コメント可）: {google_doc_link}" if google_doc_link else ""
    return (
        "お世話になっております。\n"
        "ご依頼いただいた件が仕上がりましたので、お届けいたします。\n"
        f"{scope}"
        "\n"
        "添付のファイルをご確認ください。気になるところや直したい箇所がありましたら、"
        "このトークルームにそのままお書きいただければ、すぐに手を入れます。\n"
        "\n"
        f"添付: {artifact_name}"
        f"{doc_line}"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(args: argparse.Namespace) -> dict[str, Any]:
    project_id = str(args.project_id).strip()
    talkroom_id = str(args.talkroom_id).strip()
    if not re.fullmatch(r"[0-9]+", project_id) or not re.fullmatch(r"[0-9]+", talkroom_id):
        raise ValueError("numeric_identity_required")
    parsed = urlsplit(args.talkroom_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "coconala.com"
        or parsed.path.rstrip("/") != f"/talkrooms/{talkroom_id}"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("talkroom_url_not_canonical")
    project_root = args.project_root.expanduser().resolve()
    artifact = args.artifact.expanduser().resolve()
    acceptance = args.acceptance.expanduser().resolve()
    if not project_root.is_dir():
        raise ValueError("project_root_missing")
    for path, error in ((artifact, "artifact_outside_project"), (acceptance, "acceptance_outside_project")):
        try:
            path.relative_to(project_root)
        except ValueError as exc:
            raise ValueError(error) from exc
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"missing_or_empty:{path.name}")
    expected = str(args.artifact_sha256).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256_file(artifact) != expected:
        raise ValueError("artifact_sha256_mismatch")
    acceptance_data = json.loads(acceptance.read_text(encoding="utf-8"))
    if acceptance_data.get("status") != "PASS" or acceptance_data.get("package", {}).get("sha256") != expected:
        raise ValueError("acceptance_not_bound_to_artifact")
    message = str(args.message).strip()
    if not message or len(message) > 4000:
        raise ValueError("message_invalid")
    # The attachment name stays: it tells the buyer which file is theirs. The sha256 does
    # not -- it was never for them, and it is what made the message read as machine output.
    # It remains in the evidence JSON and the event_key, which is where it was always the
    # actual proof.
    binding = f"添付: {artifact.name}"
    if binding not in message:
        message = f"{message}\n\n{binding}"
    violations = check_style(message)
    if violations:
        raise ValueError(f"buyer_style_violation:{violations[0]}")
    return {
        "project_id": project_id,
        "talkroom_id": talkroom_id,
        "talkroom_url": f"https://coconala.com/talkrooms/{talkroom_id}",
        "project_root": project_root,
        "artifact": artifact,
        "acceptance": acceptance,
        "artifact_sha256": expected,
        "message": message,
        "event_key": f"coconala:formal:{project_id}:{expected}",
        "artifact_version": str(getattr(args, "artifact_version", "") or "manual"),
        "acceptance_delta": list(getattr(args, "acceptance_delta", []) or ["ご依頼内容に沿って成果物を完成しました"]),
    }


def validate_queue_contract(
    queue_path: Path, manifest_path: Path, project_root: Path, *, revision_after_formal: bool = False,
    read_only: bool = False,
) -> dict[str, Any]:
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not read_only and (queue.get("delivery_action") != "formal" or queue.get("formal_delivery_checkbox") is not True):
        raise ValueError("queue_not_formal")
    root = project_root.expanduser().resolve()
    if not read_only:
        if not (_formal_approval_ready(queue) or _account_owner_formal_ready(queue, root)):
            raise ValueError("formal_buyer_approval_evidence_required")
    # B4 (spec section CC'): a subscription room (room_contract_kind, A5) has no 正式な納品
    # checkbox and no 納品確認待ち step to submit through. delivery_cadence.delivery_decision
    # now refuses to ever emit mode="formal" for one, so a queue item carrying both
    # delivery_action="formal" and room_contract_kind="subscription" should never exist.
    # Defense-in-depth, same shape as the disabled-checkbox corroboration below: if a stale
    # queue file, a hand-edited fixture, or a future caller bypasses delivery_cadence, refuse
    # here rather than let the browser drive toward a checkbox this room never renders.
    if queue.get("room_contract_kind") == "subscription":
        raise ValueError("subscription_room_one_shot_refused")
    # Same double-confirmation shape as coconala_paid_progress_browser.validate_progress_contract:
    # the CLI flag alone is not trusted. The queue item -- rebuilt fresh from the live snapshot
    # every pass by gig_pass.sh's route_existing_revision_after_formal -- must independently
    # assert the same three facts, or a stale/hand-edited flag could reopen the checkbox guard
    # this module exists to keep closed.
    if revision_after_formal and not (
        queue.get("revision_after_formal") is True
        and queue.get("talkroom_state") == "納品確認待ち"
        and queue.get("formal_delivery_observed") is True
        # A1's live-DOM signal: during 納品確認待ち the checkbox is measured DISABLED
        # (90000002, every snapshot since 2026-08-08 16:30). A disabled checkbox makes a
        # formal send physically impossible, so a queue item carrying disabled=True must
        # not reach this browser at all -- delivery_cadence routes it to the progress
        # channel. Refusing here keeps the slow-failure mode structurally impossible.
        and queue.get("formal_delivery_control_disabled") is not True
    ):
        raise ValueError("revision_formal_state_not_observed")
    evidence = queue.get("delivery_evidence")
    if not isinstance(evidence, dict) or manifest.get("status") != "ok" or manifest.get("acceptance_status") != "PASS":
        raise ValueError("formal_manifest_not_accepted")
    if not root.is_dir() or Path(str(manifest.get("project_root") or "")).expanduser().resolve() != root:
        raise ValueError("formal_project_root_mismatch")
    for key in ("artifact_path", "artifact_version", "acceptance_evidence_path", "acceptance_status", "acceptance_delta", "package_sha256"):
        if evidence.get(key) != manifest.get(key):
            raise ValueError(f"formal_queue_manifest_mismatch:{key}")
    artifact = Path(str(manifest["artifact_path"])).expanduser().resolve()
    acceptance = Path(str(manifest["acceptance_evidence_path"])).expanduser().resolve()
    for path, error in ((artifact, "artifact_outside_project"), (acceptance, "acceptance_outside_project")):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(error) from exc
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"missing_or_empty:{path.name}")
    digest = str(manifest.get("package_sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or sha256_file(artifact) != digest:
        raise ValueError("artifact_sha256_mismatch")
    acceptance_data = json.loads(acceptance.read_text(encoding="utf-8"))
    if acceptance_data.get("status") != "PASS":
        raise ValueError("acceptance_status_not_pass")
    talkroom_id = str(queue.get("talkroom_id") or "").strip()
    # A direct service purchase has no 募集 and therefore no request_id at all: talkroom
    # 90000004 (¥2,500, status=paid) failed here on every pass from 2026-08-03 to 08-06,
    # before the browser even opened, because the contract only imagined the application
    # path. The identity of a direct purchase is its talkroom -- the same key the projects
    # directory already uses (~/gig/projects/90000004). Only ABSENT falls back; a malformed
    # request_id is corruption and still fails, because delivering under a corrupt identity
    # would dedupe against nothing.
    project_id = str(queue.get("request_id") or "").strip()
    if queue.get("request_id") in (None, ""):
        project_id = talkroom_id
    talkroom_url = str(queue.get("marketplace_url") or queue.get("talkroom_url") or "").strip()
    parsed = urlsplit(talkroom_url)
    if (
        not re.fullmatch(r"[0-9]+", project_id)
        or not re.fullmatch(r"[0-9]+", talkroom_id)
        or parsed.scheme != "https"
        or parsed.hostname != "coconala.com"
        or parsed.path.rstrip("/") != f"/talkrooms/{talkroom_id}"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("formal_queue_identity_invalid")
    delta = manifest.get("acceptance_delta")
    if not isinstance(delta, list) or not delta or not all(isinstance(x, str) and x.strip() for x in delta):
        raise ValueError("acceptance_delta_invalid")
    # Optional, additive, §EM': absent on every manifest before 2026-08-09 and on every
    # manifest that never called google_docs_publisher.py, so its absence must change
    # nothing. Present-but-malformed is refused rather than silently dropped or passed
    # through to a customer message unchecked.
    google_doc_link = manifest.get("google_doc_link")
    if google_doc_link is not None and not (
        isinstance(google_doc_link, str) and google_doc_link.startswith("https://docs.google.com/")
    ):
        raise ValueError("google_doc_link_invalid")
    linked_asset_delivery = _linked_asset_delivery(evidence)
    verified_remote_message = (
        manifest.get("remote_formal_delivery") is True
        and _account_owner_formal_ready(queue, root)
    )
    message = (
        str(manifest.get("customer_message") or "").strip()
        if linked_asset_delivery or verified_remote_message
        else delivery_message(artifact.name, delta, google_doc_link)
    )
    if not message:
        raise ValueError("message_invalid")
    violations = check_style(message)
    if violations:
        raise ValueError(f"buyer_style_violation:{violations[0]}")
    return {
        "project_id": project_id,
        "talkroom_id": talkroom_id,
        "talkroom_url": f"https://coconala.com/talkrooms/{talkroom_id}",
        "project_root": root,
        "artifact": artifact,
        "acceptance": acceptance,
        "artifact_sha256": digest,
        "artifact_version": str(manifest["artifact_version"]),
        "acceptance_delta": delta,
        "message": message,
        "event_key": f"coconala:formal:{project_id}:{digest}",
        "revision_after_formal": revision_after_formal,
        "linked_asset_delivery": linked_asset_delivery,
    }


def _formal_approval_ready(queue: dict[str, Any]) -> bool:
    approval = queue.get("formal_approval_evidence")
    latest_identity = queue.get("latest_buyer_message_identity") or queue.get("latest_message_identity")
    return bool(
        isinstance(approval, dict)
        and isinstance(latest_identity, dict)
        and approval == latest_identity
        and approval.get("side") == "buyer"
        and str(approval.get("message_id") or "").strip()
        and re.fullmatch(r"[0-9a-f]{64}", str(approval.get("content_sha256") or ""))
    )


def _account_owner_formal_ready(queue: dict[str, Any], root: Path) -> bool:
    """Accept one exact-cycle owner override without weakening ordinary delivery."""
    authorization = queue.get("account_owner_formal_authorization")
    if not isinstance(authorization, dict) or set(authorization) != {
        "authorized_by", "request_id", "buyer_feedback_sha256",
        "requirements_sha256", "policy_sha256",
    }:
        return False
    policy_path = root / "context" / "paid-file-operator-policy.json"
    try:
        if policy_path.is_symlink() or not policy_path.is_file():
            return False
        content = policy_path.read_bytes()
        policy = json.loads(content)
    except (OSError, ValueError, TypeError):
        return False
    return bool(
        authorization.get("authorized_by") == "account_owner"
        and authorization.get("request_id") == root.name
        and authorization.get("buyer_feedback_sha256") == queue.get("buyer_feedback_sha256")
        and authorization.get("requirements_sha256") == queue.get("requirements_sha256")
        and authorization.get("policy_sha256") == hashlib.sha256(content).hexdigest()
        and policy.get("version") == 1
        and policy.get("authorized_by") == "account_owner"
        and str(policy.get("request_id") or "") == root.name
        and policy.get("buyer_feedback_sha256") == authorization.get("buyer_feedback_sha256")
        and policy.get("requirements_sha256") == authorization.get("requirements_sha256")
        and policy.get("formal_delivery_after_remote") is True
    )


def _linked_asset_delivery(evidence: dict[str, Any]) -> bool:
    required = evidence.get("required_assets")
    produced = evidence.get("artifact_assets")
    if not isinstance(required, list) or not required or not isinstance(produced, list):
        return False
    counts: dict[str, int] = {}
    for row in produced:
        if isinstance(row, dict) and row.get("type") == "linked_asset":
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


def state_expression(artifact_name: str) -> str:
    encoded = json.dumps(artifact_name, ensure_ascii=False)
    return f'''(()=>{{
      const form=document.querySelector('.d-messageForm');
      const textarea=document.querySelector('textarea[placeholder="メッセージを入力"]');
      const formal=document.querySelector('.d-messageFormButtonArea_item-deliveryCheck input[type="checkbox"]');
      const send=[...(form?.querySelectorAll('button')||[])].filter(x=>(x.innerText||'').trim()==='送信').at(-1)||null;
      const selected=[...(form?.querySelectorAll('input[type=file]')||[])].flatMap(x=>[...(x.files||[])]).map(x=>x.name);
      const rendered=[...(form?.querySelectorAll('.d-partOfFilename')||[])].map(x=>(x.textContent||'').replace(/\\s+/g,''));
      const step=(document.querySelector('.d-talkroomStep_label-current')?.innerText||'').trim();
      const transactionState=step==='進行中'?'取引中':(step==='納品送付'?'納品確認待ち':(step==='取引完了'?'取引完了':'unknown'));
      // A 定期購入 room has no step bar and no 正式な納品 checkbox. Detected by its own UI
      // CONTROL (an anchor/button whose exact text is 定期購入を終了する), never by page text,
      // which a buyer message could echo.
      const subscription=[...document.querySelectorAll('a,button')].some(x=>(x.innerText||'').trim()==='定期購入を終了する');
      const messages=[...document.querySelectorAll('.d-talkroomMessage')].map(m=>{{
        const side=m.classList.contains('d-talkroomMessage-isOthers')?'buyer':(((m.innerText||'').trim().startsWith('自分'))?'seller':'system');
        const text=(m.querySelector('.d-normalMessage')?.innerText||'').trim();
        const attachments=[...m.querySelectorAll('.d-talkroomMessage_attachedFilesItem')].map(f=>(f.querySelector('.tooltip-content')?.innerText||f.querySelector('.d-attachedFileName')?.innerText||'').replace(/\\s+/g,' ').trim()).filter(Boolean);
        return {{side,text,attachments}};
      }});
      const sellers=messages.filter(x=>x.side==='seller');
      const buyers=messages.filter(x=>x.side==='buyer');
      return {{
        url:location.origin+location.pathname, transaction_state:transactionState,
        talkroom_step_label:step,
        talkroom_step_present:!!document.querySelector('.d-talkroomStep_label-current'),
        form_present:!!form, textarea_present:!!textarea, textarea_value:textarea?.value||'',
        formal_delivery_control_present:!!formal, formal_delivery_control_checked:formal?.checked===true,
        formal_delivery_control_disabled:formal?.disabled===true,
        form_has_artifact:selected.includes({encoded})||rendered.includes({encoded})||((form?.innerText||'')+(form?.innerHTML||'')).includes({encoded}),
        selected_file_names:selected, rendered_file_names:rendered,
        send_button_present:!!send, send_button_disabled:send?.disabled!==false,
        subscription_room:subscription,
        seller_messages:sellers, buyer_messages:buyers
      }};
    }})()'''


def matching_delivery(state: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any] | None:
    """Identify our own delivery among the seller rows the room shows.

    This is the single point that answers "is it in front of the buyer": post_send_verified
    and therefore the FORMAL_DELIVERY_CONFIRMED evidence, the send_performed/deduplicated
    pair that prevents a second delivery, and the seller_message_readback all resolve
    through it.

    It used to key on the sha256 printed at the end of the message. Taking the sha out of
    the buyer's text removes that key, so the text itself becomes the key: the attachment
    name (necessary -- it is the artifact identity dedupe needs) AND our exact opening
    (sufficient -- it binds the row to the message this run composed). Prefix rather than
    suffix because 「続きを読む」 truncates the end, never the beginning.
    """
    expected = normalize_for_match(contract["message"])[:DELIVERY_MATCH_PREFIX]
    if not expected:
        return None
    for row in reversed(state.get("seller_messages") or []):
        if (
            (contract.get("linked_asset_delivery") is True
             or contract["artifact"].name in (row.get("attachments") or []))
            and normalize_for_match(row.get("text")).startswith(expected)
        ):
            return row
    return None


def buyer_hold_ack_matches(state: dict[str, Any], contract: dict[str, Any]) -> bool:
    if matching_delivery(state, contract) is None:
        return False
    hold = state.get("buyer_formal_delivery_hold") is True
    if not hold:
        hold = collector.buyer_formal_delivery_directive(
            state.get("buyer_messages")
        ).get("buyer_formal_delivery_hold") is True
    return hold and state.get("transaction_state") == "取引完了" and state.get(
        "formal_delivery_control_disabled"
    ) is True


def sanitize_buyer_state(state: dict[str, Any]) -> dict[str, Any]:
    """Keep only the safe buyer directive; never persist or print raw buyer text."""
    raw = state.get("buyer_messages")
    safe = {key: value for key, value in state.items() if key != "buyer_messages"}
    if isinstance(raw, list):
        safe.update(collector.buyer_formal_delivery_directive(raw))
    elif safe.get("buyer_formal_delivery_hold") is True:
        safe["buyer_formal_delivery_hold_reason"] = "buyer_explicit_formal_delivery_hold"
    return safe


HELD_MANIFEST_NAME = "formal-delivery-held-evidence.json"
HELD_DOM_NAME = "formal-delivery-held-live-dom.json"
HELD_SCREENSHOT_NAME = "formal-delivery-held-screenshot.png"


def held_event_record(ledger: Path, package_sha: str) -> dict[str, Any] | None:
    try:
        rows = ledger.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in rows:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("event") != "formal_delivery_observed_held":
            continue
        nested = row.get("state") if isinstance(row.get("state"), dict) else row
        if str(nested.get("delivery_send_suppressed_package_sha256") or "").lower() == package_sha.lower() or str(row.get("delivery_send_suppressed_package_sha256") or "").lower() == package_sha.lower():
            return {"row": row, "state": nested}
    return None

def safe_held_manifest_path(raw_path: Any, current_manifest: Path) -> Path:
    """Accept only canonical gig evidence paths; otherwise use the caller's path."""
    try:
        candidate = Path(str(raw_path or "")).expanduser().resolve()
        if candidate.name != HELD_MANIFEST_NAME:
            return current_manifest
        canonical_root = artifact_judge.pass_evidence_root().expanduser().resolve()
        candidate.relative_to(canonical_root)
    except (OSError, RuntimeError, ValueError):
        return current_manifest
    return candidate


def project_held_manifest(
    payload: dict[str, Any], contract: dict[str, Any], package_sha: str,
    manifest_path: Path,
) -> dict[str, Any]:
    """Project both old and rebuilt manifests onto the secret-free result contract."""
    safe: dict[str, Any] = {
        "event_key": f"coconala:formal_hold:{contract['project_id']}:{contract['talkroom_id']}:{package_sha}",
        "event": "formal_delivery_observed_held", "status": "observed",
        "project_id": contract["project_id"], "talkroom_id": contract["talkroom_id"],
        "terminal_state": "site_observed_buyer_hold", "artifact_sha256": package_sha,
        "transaction_state": "取引完了",
    }
    recorded_at = payload.get("recorded_at")
    if isinstance(recorded_at, str):
        safe["recorded_at"] = recorded_at
    for key, basename in (("dom_path", HELD_DOM_NAME), ("screenshot_path", HELD_SCREENSHOT_NAME)):
        if isinstance(payload.get(key), str):
            safe[key] = str(manifest_path.with_name(basename))
    for key in ("dom_sha256", "screenshot_sha256"):
        value = payload.get(key)
        if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value.lower()):
            safe[key] = value.lower()
    if "formal_delivery_held_evidence_path" in payload:
        safe["formal_delivery_held_evidence_path"] = str(manifest_path)
    return safe


def recover_buyer_hold_ack(
    contract: dict[str, Any], state: dict[str, Any], screenshot: bytes,
    evidence_dir: Path, ledger: Path,
) -> dict[str, Any]:
    """Persist only a verified, read-only buyer-hold observation."""
    state = sanitize_buyer_state(state)
    if not buyer_hold_ack_matches(state, contract):
        raise ValueError("buyer_hold_ack_preconditions_failed")
    artifact = Path(contract["artifact"]).expanduser().resolve()
    package_sha = str(contract.get("artifact_sha256") or "").lower()
    if not artifact.is_file() or sha256_file(artifact) != package_sha:
        raise ValueError("buyer_hold_ack_artifact_hash_mismatch")
    ledger = Path(ledger).expanduser().resolve()
    state_path = ledger.parent / "state.json"
    try:
        current = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("buyer_hold_ack_project_state_missing") from exc
    if not isinstance(current, dict):
        raise ValueError("buyer_hold_ack_project_state_invalid")
    evidence_dir = Path(evidence_dir).expanduser().resolve()
    event_key = f"coconala:formal_hold:{contract['project_id']}:{contract['talkroom_id']}:{package_sha}"
    manifest_path = evidence_dir / HELD_MANIFEST_NAME
    held_event = held_event_record(ledger, package_sha)
    if held_event is not None:
        historical_path_value = held_event["state"].get("formal_delivery_held_evidence_path") or held_event["row"].get("formal_delivery_held_evidence_path")
        if isinstance(historical_path_value, str) and not Path(historical_path_value).expanduser().is_absolute():
            historical_path_value = str(ledger.parent / historical_path_value)
        historical_manifest = safe_held_manifest_path(historical_path_value, manifest_path)
    elif current.get("terminal_state") == "site_observed_buyer_hold" and current.get(
        "delivery_send_suppressed_package_sha256"
    ) == package_sha and manifest_path.is_file():
        historical_manifest = manifest_path
    else:
        historical_manifest = None
    if historical_manifest is not None:
        needs_write = False
        try:
            existing = json.loads(historical_manifest.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                raise ValueError("held_manifest_not_object")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            if held_event is None:
                raise
            state = held_event["state"] if isinstance(held_event["state"], dict) else {}
            existing = {"formal_delivery_held_evidence_path": str(historical_manifest)}
            existing.update({target: state[source] for source, target in (
                ("formal_delivery_held_dom_sha256", "dom_sha256"),
                ("formal_delivery_held_screenshot_sha256", "screenshot_sha256"),
            ) if isinstance(state.get(source), str)})
            needs_write = True
        projected = project_held_manifest(existing, contract, package_sha, historical_manifest)
        if projected != existing:
            needs_write = True
        if needs_write:
            collector.atomic_json(historical_manifest, projected)
        return {**projected, "deduplicated": True}
    now = datetime.now(timezone.utc).isoformat()
    dom_path = evidence_dir / "formal-delivery-held-live-dom.json"
    screenshot_path = evidence_dir / "formal-delivery-held-screenshot.png"
    dom = {k: state[k] for k in (
        "url", "transaction_state", "buyer_formal_delivery_hold",
        "buyer_formal_delivery_hold_reason", "formal_delivery_control_disabled", "seller_messages",
    ) if k in state}
    dom.update({"artifact_filename": artifact.name, "artifact_sha256": package_sha, "captured_at": now})
    collector.atomic_json(dom_path, dom)
    collector.secure_write_bytes(screenshot_path, screenshot)
    dom_sha, screenshot_sha = sha256_file(dom_path), sha256_file(screenshot_path)
    event = {
        "event_key": event_key, "event": "formal_delivery_observed_held", "recorded_at": now,
        "project_id": contract["project_id"], "talkroom_id": contract["talkroom_id"],
        "terminal_state": "site_observed_buyer_hold", "artifact_sha256": package_sha,
        "dom_path": str(dom_path), "dom_sha256": dom_sha,
        "screenshot_path": str(screenshot_path),
        "screenshot_sha256": screenshot_sha, "transaction_state": "取引完了",
    }
    collector.atomic_json(manifest_path, {**event, "status": "observed", "transaction_state": "取引完了"})
    patch = {
        "terminal_state": "site_observed_buyer_hold", "formal_delivery_observed_held": True,
        "buyer_formal_delivery_hold": True,
        "buyer_formal_delivery_hold_reason": "buyer_explicit_formal_delivery_hold",
        "delivery_send_suppressed_package_sha256": package_sha,
        "formal_delivery_held_evidence_path": str(manifest_path),
        "formal_delivery_held_dom_sha256": dom_sha,
        "formal_delivery_held_screenshot_sha256": screenshot_sha,
    }
    project_ledger.append(ledger.parent, patch, "formal_delivery_observed_held")
    return {**event, "status": "observed", "dom_path": str(dom_path), "deduplicated": False}


# Talkroom 90000004 (¥2,500, paid 07-31) is a 定期購入: no step bar, no 正式な納品 checkbox,
# no 納品確認待ち -- the deliverable goes out as an attached message and the cycle completes
# on the close date. The browser modelled only the one-shot room, so readiness demanded a
# step-bar state this room never shows (measured 2026-08-06 05:01:
# transaction_state="unknown", formal_delivery_control_present=false, form_present=true)
# and every attempt since 08-03 died before delivering anything.

def talkroom_ready(state: dict[str, Any], talkroom_url: str) -> bool:
    if state.get("url") != talkroom_url:
        return False
    if state.get("subscription_room") is True:
        return bool(state.get("form_present")) and bool(state.get("textarea_present"))
    return state.get("transaction_state") in ("取引中", "納品確認待ち", "取引完了")


def delivery_mode(state: dict[str, Any]) -> str:
    return "subscription_message" if state.get("subscription_room") is True else "formal_checkbox"


def formal_delivery_blocked_on_pending_confirmation(
    mode: str, state: dict[str, Any], *, revision_after_formal: bool = False
) -> bool:
    """True when a PRIOR formal delivery in this room is still awaiting the buyer's
    confirmation -- Coconala refuses to let the checkbox be re-checked while one is pending.

    Measured on talkroom 90000002: formal-delivery-evidence.json already records a
    SUCCESSFUL formal_checkbox send on 2026-08-06 that left the room in 納品確認待ち. Every
    attempt since then still read formal_delivery_control_checked=false initially (the
    sibling formal_checkbox_not_initially_off guard below does not fire) and only failed
    later, at the post-click readback -- because the click itself is a no-op the site
    silently refuses. That is not a transport fault; it is the marketplace's own state
    machine saying "one delivery is already on the table". Attempting the checkbox here
    would not fail on our forms, it would fail on theirs, six more times.

    ``revision_after_formal`` lifts the block. Measured again on the SAME talkroom
    2026-08-07/08: the buyer did not confirm that first delivery -- they replied with a
    revision request (5 attached photos) while transaction_state stayed 納品確認待ち, exactly
    as gig_pass.sh:1314-1316 already documents ("A new accepted revision remains a formal
    delivery even when the transaction is already in 納品確認待ち. The live UI still exposes
    the formal checkbox"). Eight straight attempts died here anyway, because this guard
    could not tell "buyer silent" from "buyer replied with feedback we have not answered
    yet" -- both read as the identical transaction_state. The caller (validate_queue_contract)
    only sets the flag after it independently confirms the queue item carries
    revision_after_formal=True, so a caller that cannot prove freshness gets the old,
    fail-closed block.

    Scoped to formal_checkbox rooms only, same as formal_checkbox_not_initially_off: a
    subscription room has no checkbox and no 納品確認待ち step to collide with.

    ★ The live DOM outranks the flag. ★ Opus review 2026-08-08: during 納品確認待ち the
    checkbox is measured DISABLED (90000002, every snapshot since 16:30), so even a fully
    corroborated revision_after_formal cannot click it -- proceeding would upload, type,
    and then die on the unclickable box, leaving compose residue in the real form once per
    pass. formal_delivery_control_disabled=True therefore blocks unconditionally, before
    any upload; a revision against a disabled checkbox belongs on the progress channel
    (delivery_cadence routes it there).
    """
    if mode != "formal_checkbox":
        return False
    if state.get("formal_delivery_control_disabled") is True:
        return True
    return state.get("transaction_state") == "納品確認待ち" and not revision_after_formal


def post_send_verified(state: dict[str, Any], contract: dict[str, Any]) -> bool:
    """Site-side proof that this delivery is in front of the buyer.

    Both room types require our own message visible in the room with the artifact attached
    and our exact opening in the text. The one-shot room additionally reaches 納品確認待ち; a
    subscription room has no such step, so demanding it would fail every successful
    delivery.
    """
    if matching_delivery(state, contract) is None:
        return False
    if state.get("subscription_room") is True:
        return True
    return state.get("transaction_state") in ("納品確認待ち", "取引完了")


async def trusted_click(session: progress.CdpSession, selector: str) -> None:
    point = await session.evaluate(f'''(()=>{{const x=document.querySelector({json.dumps(selector)});if(!x)return null;x.scrollIntoView({{block:'center'}});const r=x.getBoundingClientRect();return {{x:r.left+r.width/2,y:r.top+r.height/2}};}})()''')
    if not isinstance(point, dict):
        raise RuntimeError(f"click_target_missing:{selector}")
    for event_type in ("mouseMoved", "mousePressed", "mouseReleased"):
        params: dict[str, Any] = {"type": event_type, "x": point["x"], "y": point["y"]}
        if event_type != "mouseMoved":
            params.update({"button": "left", "clickCount": 1})
        await session.call("Input.dispatchMouseEvent", params)


async def trusted_click_send(session: progress.CdpSession) -> None:
    point = await session.evaluate('''(()=>{const form=document.querySelector('.d-messageForm');const x=[...(form?.querySelectorAll('button')||[])].filter(b=>(b.innerText||'').trim()==='送信'&&!b.disabled).at(-1)||null;if(!x)return null;x.scrollIntoView({block:'center'});const r=x.getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2};})()''')
    if not isinstance(point, dict):
        raise RuntimeError("formal_send_button_missing")
    for event_type in ("mouseMoved", "mousePressed", "mouseReleased"):
        params: dict[str, Any] = {"type": event_type, "x": point["x"], "y": point["y"]}
        if event_type != "mouseMoved":
            params.update({"button": "left", "clickCount": 1})
        await session.call("Input.dispatchMouseEvent", params)


async def confirm_formal_modal_if_present(session: progress.CdpSession) -> dict[str, Any]:
    await asyncio.sleep(1)
    diagnostic = await session.evaluate('''(()=>{const visible=x=>{const r=x.getBoundingClientRect();const s=getComputedStyle(x);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const dialogs=[...document.querySelectorAll('[role=dialog],.modal,.d-modal')].filter(visible);const buttons=[...document.querySelectorAll('button')].filter(visible).map(x=>(x.innerText||'').trim()).filter(Boolean);return{dialogs:dialogs.map(x=>(x.innerText||'').trim().slice(0,1000)),buttons};})()''')
    labels = diagnostic.get("buttons") if isinstance(diagnostic, dict) else []
    allowed = [label for label in ("納品する", "納品として送信", "送信する") if label in labels]
    if not allowed:
        return diagnostic if isinstance(diagnostic, dict) else {"dialogs": [], "buttons": []}
    if len(allowed) != 1:
        raise RuntimeError(f"formal_confirmation_ambiguous:{json.dumps(diagnostic, ensure_ascii=False)}")
    label = allowed[0]
    point = await session.evaluate(f'''(()=>{{const visible=x=>{{const r=x.getBoundingClientRect();const s=getComputedStyle(x);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'}};const xs=[...document.querySelectorAll('button')].filter(x=>visible(x)&&(x.innerText||'').trim()==={json.dumps(label, ensure_ascii=False)}&&!x.disabled);const x=xs.at(-1)||null;if(!x)return null;const r=x.getBoundingClientRect();return{{x:r.left+r.width/2,y:r.top+r.height/2}};}})()''')
    if not isinstance(point, dict):
        raise RuntimeError("formal_confirmation_button_missing")
    for event_type in ("mouseMoved", "mousePressed", "mouseReleased"):
        params: dict[str, Any] = {"type": event_type, "x": point["x"], "y": point["y"]}
        if event_type != "mouseMoved":
            params.update({"button": "left", "clickCount": 1})
        await session.call("Input.dispatchMouseEvent", params)
    return {**diagnostic, "confirmation_clicked": label}


async def close_formal_explanation(session: progress.CdpSession) -> None:
    point = await session.evaluate('''(()=>{const visible=x=>{const r=x.getBoundingClientRect();const s=getComputedStyle(x);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const dialog=[...document.querySelectorAll('[role=dialog],.modal,.d-modal')].find(x=>visible(x)&&(x.innerText||'').includes('正式な納品について'));if(!dialog)return false;const xs=[...dialog.querySelectorAll('button')].filter(x=>visible(x)&&(x.innerText||'').trim()==='閉じる'&&!x.disabled);if(xs.length!==1)return null;const r=xs[0].getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2};})()''')
    if point is False:
        return
    if not isinstance(point, dict):
        raise RuntimeError("formal_explanation_close_not_unique")
    for event_type in ("mouseMoved", "mousePressed", "mouseReleased"):
        params: dict[str, Any] = {"type": event_type, "x": point["x"], "y": point["y"]}
        if event_type != "mouseMoved":
            params.update({"button": "left", "clickCount": 1})
        await session.call("Input.dispatchMouseEvent", params)
    await asyncio.sleep(0.5)


async def execute(ws_url: str, contract: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any], bytes, bool]:
    expression = state_expression(contract["artifact"].name)
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=10, max_size=64 * 1024 * 1024) as ws:
        session = progress.CdpSession(ws, ws_url, contract["talkroom_url"])
        await session.call("Page.enable")
        await session.call("DOM.enable")
        initial = await progress._wait_for_state(
            session, expression,
            lambda s: talkroom_ready(s, contract["talkroom_url"]),
            args.page_timeout, "formal_talkroom_not_ready")
        mode = delivery_mode(initial)
        existing = matching_delivery(initial, contract)
        if existing is not None:
            # The marketplace readback is authoritative.  A process can die after the
            # buyer-visible send but before the local confirmation ledger is appended;
            # retrying that exact delivery would duplicate it.
            verified, sent = initial, False
        else:
            if mode == "formal_checkbox" and initial.get("formal_delivery_control_checked") is not False:
                raise RuntimeError("formal_checkbox_not_initially_off")
            if formal_delivery_blocked_on_pending_confirmation(
                mode, initial, revision_after_formal=contract.get("revision_after_formal") is True
            ):
                raise RuntimeError("awaiting_buyer_confirmation")
            linked = contract.get("linked_asset_delivery") is True
            if not linked:
                await progress._upload(session, contract["artifact"])
                await progress._wait_for_state(session, expression, lambda s: s.get("form_has_artifact") is True and s.get("formal_delivery_control_checked") is False, args.upload_timeout, "formal_upload_not_ready")
            await progress._fill_message(session, contract["message"])
            await progress._wait_for_state(session, expression, lambda s: (linked or s.get("form_has_artifact") is True) and s.get("textarea_value") == contract["message"] and s.get("send_button_disabled") is False, args.send_timeout, "formal_message_not_ready")
            if mode == "formal_checkbox":
                await trusted_click(session, '.d-messageFormButtonArea_item-deliveryCheck input[type="checkbox"]')
                await progress._wait_for_state(session, expression, lambda s: s.get("formal_delivery_control_checked") is True and (linked or s.get("form_has_artifact") is True) and s.get("textarea_value") == contract["message"], args.send_timeout, "formal_checkbox_readback_failed")
                await close_formal_explanation(session)
                await progress._wait_for_state(session, expression, lambda s: s.get("formal_delivery_control_checked") is True and (linked or s.get("form_has_artifact") is True) and s.get("textarea_value") == contract["message"] and s.get("send_button_disabled") is False, args.send_timeout, "formal_after_explanation_not_ready")
            await trusted_click_send(session)
            modal = await confirm_formal_modal_if_present(session) if mode == "formal_checkbox" else {}
            sent = True
            try:
                verified = await progress._wait_for_state(
                    session, expression,
                    lambda s: post_send_verified(s, contract),
                    args.post_timeout, "formal_post_send_readback_failed")
            except RuntimeError as exc:
                raise RuntimeError(f"{exc};submit_diagnostic={json.dumps(modal, ensure_ascii=False)}") from exc
        screenshot = await session.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        return verified, base64.b64decode(screenshot["data"]), sent


async def read_only_capture(ws_url: str, contract: dict[str, Any], timeout: float) -> tuple[dict[str, Any], bytes]:
    expression = state_expression(contract["artifact"].name)
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=10, max_size=64 * 1024 * 1024) as ws:
        session = progress.CdpSession(ws, ws_url, contract["talkroom_url"])
        await session.call("Page.enable")
        state = await progress._wait_for_state(
            session, expression, lambda s: s.get("url") == contract["talkroom_url"],
            timeout, "formal_readback_not_ready")
        shot = await session.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        return state, base64.b64decode(shot["data"])


async def read_only(ws_url: str, contract: dict[str, Any], timeout: float) -> dict[str, Any]:
    state, _ = await read_only_capture(ws_url, contract, timeout)
    return sanitize_buyer_state(state)


def persist(contract: dict[str, Any], verified: dict[str, Any], screenshot: bytes, sent: bool, evidence_dir: Path, ledger: Path) -> dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat()
    collector.secure_directory(evidence_dir)
    screenshot_path = (evidence_dir / "formal-delivery-screenshot.png").resolve()
    dom_path = (evidence_dir / "formal-delivery-live-dom.json").resolve()
    manifest_path = (evidence_dir / "formal-delivery-evidence.json").resolve()
    collector.secure_write_bytes(screenshot_path, screenshot)
    matched = matching_delivery(verified, contract)
    if not post_send_verified(verified, contract):
        raise RuntimeError("formal_authoritative_readback_missing")
    mode = delivery_mode(verified)
    row = {
        "event_key": contract["event_key"], "formal_effect_key": contract["event_key"],
        "event": "FORMAL_DELIVERY_CONFIRMED",
        "captured_at": captured_at, "project_id": contract["project_id"], "talkroom_id": contract["talkroom_id"],
        "artifact_path": str(contract["artifact"]), "artifact_bytes": contract["artifact"].stat().st_size,
        "artifact_sha256": contract["artifact_sha256"], "acceptance_path": str(contract["acceptance"]),
        "send_performed": sent, "deduplicated": not sent, "transaction_state": verified["transaction_state"],
        "delivery_mode": mode,
        "formal_delivery_control_checked_before_send": mode == "formal_checkbox",
        "seller_attachment_readback": None if contract.get("linked_asset_delivery") is True else contract["artifact"].name,
        "linked_asset_delivery": contract.get("linked_asset_delivery") is True,
        "seller_message_readback": str(matched.get("text") or ""),
        "screenshot_path": str(screenshot_path), "dom_path": str(dom_path)
    }
    collector.atomic_json(dom_path, {"url": contract["talkroom_url"], **verified})
    collector.atomic_json(manifest_path, row)
    queue_screenshot_path = (evidence_dir / "paid-queue-screenshot.png").resolve()
    queue_dom_path = (evidence_dir / "paid-queue-live-dom.json").resolve()
    queue_manifest_path = (evidence_dir / "paid-queue-evidence.json").resolve()
    collector.secure_write_bytes(queue_screenshot_path, screenshot)
    queue_live = {
        "url": contract["talkroom_url"],
        "sent": True,
        "mode": "formal",
        "send_performed": sent,
        "deduplicated": not sent,
        "transaction_state": verified["transaction_state"],
        "delivery_mode": mode,
        "formal_delivery_control_checked": False,
        "formal_delivery_control_disabled": verified.get("formal_delivery_control_disabled") is True,
        # True was hardcoded here while a 定期購入 room has no checkbox at all -- the
        # evidence gate downstream trusts this field, so it must state the room's truth.
        "formal_delivery_control_checked_before_send": mode == "formal_checkbox",
        "latest_seller_attachment": None if contract.get("linked_asset_delivery") is True else {
            "filename": contract["artifact"].name,
            "size_bytes": contract["artifact"].stat().st_size,
            "message": str(matched.get("text") or ""),
        },
        "latest_seller_message": str(matched.get("text") or ""),
        "linked_asset_delivery": contract.get("linked_asset_delivery") is True,
        "formal_effect_key": contract["event_key"],
    }
    queue_outer = {
        "sent": True,
        "mode": "formal",
        "send_performed": sent,
        "deduplicated": not sent,
        "formal_delivery_checkbox": True,
        "captured_at": captured_at,
        "talkroom_id": contract["talkroom_id"],
        "artifact_basename": contract["artifact"].name,
        "artifact_version": contract["artifact_version"],
        "package_sha256": contract["artifact_sha256"],
        "acceptance_delta": contract["acceptance_delta"],
        "screenshot_path": str(queue_screenshot_path),
        "live_dom_path": str(queue_dom_path),
        "formal_effect_key": contract["event_key"],
        "linked_asset_delivery": contract.get("linked_asset_delivery") is True,
    }
    collector.atomic_json(queue_dom_path, queue_live)
    collector.atomic_json(queue_manifest_path, queue_outer)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []
    if not any(json.loads(line).get("event_key") == contract["event_key"] for line in existing if line.strip()):
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
    return row


def record_intent(contract: dict[str, Any], ledger: Path) -> None:
    intent_key = f"{contract['event_key']}:intent"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []
    if any(json.loads(line).get("event_key") == intent_key for line in existing if line.strip()):
        return
    row = {
        "event_key": intent_key,
        "event": "FORMAL_DELIVERY_INTENT",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "project_id": contract["project_id"],
        "talkroom_id": contract["talkroom_id"],
        "artifact_path": str(contract["artifact"]),
        "artifact_bytes": contract["artifact"].stat().st_size,
        "artifact_sha256": contract["artifact_sha256"],
        "acceptance_path": str(contract["acceptance"]),
        "next_effect": "upload_then_formal_checkbox_then_send"
    }
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()


def formal_event_confirmed(contract: dict[str, Any], ledger: Path) -> bool:
    if not ledger.is_file():
        return False
    try:
        rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        return False
    return any(
        row.get("event_key") == contract["event_key"]
        and row.get("event") == "FORMAL_DELIVERY_CONFIRMED"
        for row in rows if isinstance(row, dict)
    )


# The judge can refuse for two different reasons, and they need opposite answers. A refusal
# the buyer can resolve is a question we have not asked yet; a refusal about the artifact is
# ours to fix. artifact_judge raises the same exception type for both, so the split happens
# here. Nothing new is invented for the asking: record_judge_refusal writes the BLOCKED
# record the ask lane already reads, which is the whole redirect.
ROUTED_TO_ASK_EXIT = 7

# formal_delivery_blocked_on_pending_confirmation (9652a0e3) makes execute() raise this before
# any upload or click when a prior formal delivery on the same room is still awaiting the
# buyer's confirmation. Coconala's own state machine is declining a duplicate send, not our
# transport breaking -- so like ROUTED_TO_ASK_EXIT it needs its own process exit, or
# gig_pass.sh has no way to tell the two apart and keeps blaming the browser.
AWAITING_BUYER_CONFIRMATION_EXIT = 8

# Contract validation raised before any browser action -- not a delivery attempt. Shared
# meaning with coconala_paid_progress_browser.CONTRACT_INVALID_EXIT; gig_pass.sh maps this
# to a failure reason that skips attempt recording. Every unrecognised exit still counts.
CONTRACT_INVALID_EXIT = 9


def route_judge_refusal(refusal: BaseException, project_root: Any, queue_item: dict) -> dict:
    """Turn a buyer-answerable refusal into the BLOCKED record the ask lane reads.

    Re-raises anything the buyer cannot answer, so every other refusal keeps today's
    fail-closed behaviour exactly.
    """
    if not artifact_judge.should_ask_the_buyer(refusal):
        raise refusal
    brief = first_contact.order_brief(project_root, queue_item)
    return first_contact.record_judge_refusal(brief, project_root, str(refusal))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-item", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--talkroom-id")
    parser.add_argument("--talkroom-url")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--artifact-sha256")
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--message")
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--default-tab-helper", required=True, type=Path)
    parser.add_argument("--page-timeout", type=float, default=30)
    parser.add_argument("--upload-timeout", type=float, default=120)
    parser.add_argument("--send-timeout", type=float, default=120)
    parser.add_argument("--post-timeout", type=float, default=120)
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--revision-after-formal", action="store_true")
    args = parser.parse_args()
    queue_mode = args.queue_item is not None or args.manifest is not None
    if queue_mode:
        if args.queue_item is None or args.manifest is None:
            raise SystemExit("--queue-item and --manifest are required together")
        try:
            contract = validate_queue_contract(
                args.queue_item, args.manifest, args.project_root,
                revision_after_formal=args.revision_after_formal,
                read_only=args.read_only,
            )
        except ValueError as invalid:
            # Same fairness rule as the progress browser (see CONTRACT_INVALID_EXIT
            # there): a contract rejected before any browser action is not a delivery
            # attempt and must not consume the order's retry budget.
            print(json.dumps({"ok": False, "contract_invalid": str(invalid)},
                             ensure_ascii=False, separators=(",", ":")))
            return CONTRACT_INVALID_EXIT
    else:
        required = (args.project_id, args.talkroom_id, args.talkroom_url, args.artifact, args.artifact_sha256, args.acceptance, args.message)
        if any(value is None for value in required):
            raise SystemExit("manual mode requires project/talkroom/artifact/acceptance/message arguments")
        contract = validate(args)
    if args.read_only:
        with collector.DefaultTab(args.default_tab_helper, contract["talkroom_url"]) as tab:
            state, screenshot = asyncio.run(read_only_capture(tab.ws, contract, args.page_timeout))
        state = sanitize_buyer_state(state)
        result: dict[str, Any] = {"ok": True, "read_only": True, "state": state, "buyer_hold_ack": False}
        if buyer_hold_ack_matches(state, contract):
            result["evidence"] = recover_buyer_hold_ack(
                contract, state, screenshot, args.evidence_dir.resolve(), args.ledger.resolve()
            )
            result["buyer_hold_ack"] = True
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    # ── The last question before the buyer sees it ────────────────────────────────
    #
    # Placed here, not in validate_queue_contract, and not upstream in the promotion
    # transaction. This line is the last thing between the artifact and the buyer for BOTH
    # room types: the one-shot room and the 定期購入 subscription room (talkroom 90000004)
    # diverge inside execute(), downstream of here, so one gate covers both.
    #
    # After --read-only on purpose. Observing a room sends nothing, and an observation pass
    # that could not reach a model must not stop reporting what the room says.
    # Before record_intent on purpose: an artifact we are about to refuse must not first be
    # written into the delivery ledger as an intent.
    #
    # ★ Fails CLOSED. ★ Raises with the same two error ids as validate_paid_work, so a
    # refusal reads the same whether it happened at promotion or at the send.
    trajectory_context = {
        "stage": "PAID_QUEUE_DELIVERY",
        "lane": "delivery",
        "resource_key": f"talkroom:{contract['talkroom_id']}",
        "artifact_sha256": contract["artifact_sha256"],
    }
    # Parsed before the try, not inside it. validate_queue_contract already read both files,
    # so a decode error here is not a judge refusal -- and JSONDecodeError is a ValueError,
    # which would otherwise land in a handler that says it only handles refusals.
    requirements_path = (
        json.loads(args.manifest.read_text(encoding="utf-8")).get("requirements_path")
        if queue_mode else None
    )
    queue_item = (
        json.loads(args.queue_item.read_text(encoding="utf-8"))
        if args.queue_item is not None else {}
    )
    try:
        artifact_judge.refuse_unless_deliverable(
            contract["project_root"],
            contract["artifact"],
            requirements_path,
            trajectory_context=trajectory_context,
        )
        # E1 (26-gig-loop §CC' 段E): the binary judge above only answers "is this the
        # ordered thing at all". This scores how well it matches and blocks only a
        # confidently bad score -- see predelivery_score.py for the fail-open direction.
        # Same try/except as the judge on purpose: a score-low refusal is not askable
        # (predelivery_score.ERROR_PREDELIVERY_SCORE_LOW is not in ASK_THE_BUYER_ERRORS),
        # so route_judge_refusal re-raises it and this delivery attempt fails closed,
        # exactly like an about_the_deal or not_the_order verdict does today.
        predelivery_score.score_predelivery(
            contract["project_root"], contract["artifact"], requirements_path,
        )
    except ValueError as refusal:
        routed = route_judge_refusal(refusal, contract["project_root"], queue_item)
        # Written is not the same as readable, and both have to hold before anything claims a
        # question is queued. write_blocked_record swallows OSError and reports False; and
        # order_brief fills feedback_sha256 best-effort, so a record whose digest does not
        # match the requirements file it points at grades undeterminable, and the ask lane
        # sends nothing on that. Either way the redirect did not happen, so keep today's
        # crash rather than a green pass that stalls the order forever.
        # ``fresh`` and nothing else, matching ask_buyer_pass.build's fail direction.
        verdict = paid_work_evidence.blocked_evidence_verdict(contract["project_root"])[0]
        if not routed.get("blocked_record_written") or verdict != paid_work_evidence.BLOCK_FRESH:
            raise refusal
        # Not ok: nothing was delivered. The pass must not read this as a send.
        print(json.dumps({"ok": False, "routed_to_ask": {**routed, "blocked_verdict": verdict}},
                         ensure_ascii=False, separators=(",", ":")))
        return ROUTED_TO_ASK_EXIT
    ledger = args.ledger.resolve()
    contract["formal_event_confirmed"] = formal_event_confirmed(contract, ledger)
    record_intent(contract, ledger)
    try:
        with collector.DefaultTab(args.default_tab_helper, contract["talkroom_url"]) as tab:
            verified, screenshot, sent = asyncio.run(execute(tab.ws, contract, args))
    except RuntimeError as exc:
        # Only the pending-confirmation guard gets its own exit; every other RuntimeError
        # out of execute() is a real transport fault and must keep today's fail-closed
        # traceback rather than be reinterpreted as a marketplace decline.
        if str(exc) != "awaiting_buyer_confirmation":
            raise
        print(json.dumps({"ok": False, "awaiting_buyer_confirmation": True},
                          ensure_ascii=False, separators=(",", ":")))
        return AWAITING_BUYER_CONFIRMATION_EXIT
    # EV1: the delivery half of spec §4.2 no_delivery_without_gate. Written AFTER execute()
    # returns, so `deliver` means the browser really ran, and `ok` means it verified a send
    # -- an attempt that raised never reaches this line and never claims to have delivered.
    record_trajectory(
        action="deliver", result="ok" if sent else "refused",
        stage=trajectory_context["stage"], lane=trajectory_context["lane"],
        resource_key=trajectory_context["resource_key"],
        artifact_sha256=trajectory_context["artifact_sha256"],
    )
    row = persist(contract, verified, screenshot, sent, args.evidence_dir.resolve(), ledger)
    print(json.dumps({"ok": True, "evidence": row}, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
