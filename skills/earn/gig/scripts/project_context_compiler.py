#!/usr/bin/env python3
"""Compile one durable, request-scoped project context without raw-history stuffing.

Until 2026-08-07 this compiled *references*: paths, byte counts and hashes for everything
under ``source/``, ``requirements/``, ``delivery/`` and ``acceptance/``. It ran every
pass, wrote ``context/current.json`` and a receipts ledger, and ★nothing read either file
back★. Meanwhile ``artifact_judge.py`` read the entire talkroom ledger, so the judge saw
more of the order than the builder did -- the builder got a path string in its packet.

So the same compiler now carries content as well as references, from all four places a
requirement can be written:

| source | why it is here |
|---|---|
| ``source/posting/`` | what the buyer wrote before paying (91000002: 枚数 4枚) |
| ``source/proposal/`` | what the seller offered before the buyer purchased |
| ``source/dm/`` | the thread the material arrived in, plus its attachment index |
| ``requirements/live-buyer-reply.json`` | the current request AND everything accumulated |
| our own messages | on 2026-08-06 15:46 we promised this buyer a draft and forgot |

★Index and salient content travel; bodies stay as file references.★ ``read_these_first``
names the files, every section carries its own path, and the whole block is bounded to
``COMBINED_MAX_BYTES`` -- a builder that needs a full body reads the path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from private_data_boundary import (
    attachment_metadata, is_credential_attachment, redact_prompt_text,
)


# ★ Where the durable postings live is A8's decision, not a second one. ★
# ``artifact_judge.posting_store`` prefers ~/gig/postings over the project's own copy for
# the reason that matters here too: the project tree is the builder's rw sandbox and the
# store is not. Loaded by path so it resolves both when this file runs as a script (script
# dir on sys.path) and when a test loads it via spec_from_file_location (script dir absent).
# The fallback exists for the same reason the trajectory import below has one -- compiling
# context must never fail, and a failed compile isolates the whole paid lane.
try:
    _JUDGE_SPEC = importlib.util.spec_from_file_location(
        "gig_artifact_judge_posting_store",
        Path(__file__).resolve().parent / "artifact_judge.py",
    )
    _judge = importlib.util.module_from_spec(_JUDGE_SPEC)
    _JUDGE_SPEC.loader.exec_module(_judge)
    posting_store = _judge.posting_store
except Exception:  # noqa: BLE001 - see above; a missing judge must not take the lane down
    def posting_store() -> Path:  # type: ignore[misc]
        return Path(
            os.environ.get("GIG_POSTING_STORE") or (Path.home() / "gig" / "postings")
        ).expanduser()


# EV1 instrumentation. Degrades to silence; compiling context must never fail because the
# trajectory could not be written. See scripts/trajectory.py invariant 1.
try:
    from trajectory import record as record_trajectory
except Exception:  # noqa: BLE001 - instrumentation may never break its host
    def record_trajectory(**_kwargs: Any) -> None:  # type: ignore[misc]
        return None


SOURCE_DIRS = ("source", "requirements", "delivery", "acceptance")
# Budgets. The combined block is a digest, not a transcript: these are what a builder
# prompt can afford beside the rest of the paid-work instructions.
COMBINED_MAX_BYTES = 262144
POSTING_CHARS = 3000
CURRENT_REQUEST_CHARS = 1500
ACCUMULATED_ROWS = 16
ACCUMULATED_CHARS = 400
DM_MESSAGE_ROWS = 10
DM_MESSAGE_CHARS = 350
COMMITMENT_ROWS = 6
COMMITMENT_CHARS = 250
ATTACHMENT_ROWS = 12
ORDER_TITLE_CHARS = 200
STATE_FIELDS = (
    "request_id", "adapter", "buyer", "delivery_date", "talkroom_id",
    "source_contract_id", "queue_class", "talkroom_state", "work_state",
    "next_action", "current_version", "current_artifact_path",
    "current_package_sha256", "current_acceptance_status",
    "current_acceptance_delta", "buyer_visible", "formal_delivery_confirmed",
    "transaction_state", "handled_buyer_feedback_sha256",
)
QUEUE_FIELDS = (
    "request_id", "talkroom_id", "contract_id", "queue_class", "delivery_date",
    "talkroom_state", "buyer_feedback_sha256", "buyer_feedback_stage",
    "buyer_feedback_pending_artifact", "buyer_reply_after_artifact_observed",
    "buyer_visible_artifact_observed", "delivery_action", "blockers",
)


def _bytes_sha(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _is_runtime_interpreter_symlink(root: Path, path: Path, resolved: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    if (not path.is_symlink() or len(parts) != 6
            or parts[:2] != ("delivery", "runtime")
            or parts[3:5] != (".venv", "bin")):
        return False
    alias = parts[5]
    if not (alias in {"python", "python3", "𝜋thon"} or alias.startswith("python3.")):
        return False
    try:
        return (resolved.is_file() and resolved.name.startswith("python")
                and bool(resolved.stat().st_mode & 0o111))
    except OSError:
        return False


def _refs(root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    refs: list[dict[str, Any]] = []
    candidates = [root / "state.json", root / "events.jsonl"]
    for dirname in SOURCE_DIRS:
        directory = root / dirname
        if directory.is_dir():
            candidates.extend(path for path in directory.rglob("*") if path.is_file())
    for path in sorted(set(candidates)):
        if not path.is_file():
            continue
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError("source reference resolution failed") from error
        if not resolved.is_relative_to(root):
            if _is_runtime_interpreter_symlink(root, path, resolved):
                continue
            raise ValueError("source reference escapes project")
        if not resolved.is_file():
            continue
        size, sha = _bytes_sha(resolved)
        reference = {
            "path": str(path.relative_to(root)),
            "bytes": size,
            "sha256": sha,
        }
        if is_credential_attachment(root, path):
            reference.update(attachment_metadata(root, path))
        refs.append(reference)
    return refs


def _recent_events(path: Path, limit: int = 12) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        rows.append({key: row[key] for key in ("ts", "recorded_at", "event", "event_key") if key in row})
    return rows


def _clip(value: Any, limit: int) -> str:
    text = redact_prompt_text(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _posting_section(root: Path) -> dict[str, Any] | None:
    """What the buyer wrote before they paid."""
    directory = root / "source" / "posting"
    try:
        files = sorted(path for path in directory.glob("request-*.json") if path.is_file())
    except OSError:
        return None
    for path in files:
        document = _json(path)
        body = str(document.get("body") or "")
        if not body:
            continue
        return {
            "path": str(path),
            "url": document.get("url"),
            "title": _clip(document.get("title"), 200),
            "body_bytes": document.get("body_bytes"),
            "body": _clip(body, POSTING_CHARS),
        }
    return None


def _proposal_section(root: Path) -> dict[str, Any] | None:
    directory = root / "source" / "proposal"
    try:
        files = sorted(path for path in directory.glob("offer-*.json") if path.is_file())
    except OSError:
        return None
    for path in files:
        document = _json(path)
        body = str(document.get("body") or "")
        if body:
            return {
                "path": str(path),
                "url": document.get("url"),
                "title": _clip(document.get("title"), 200),
                "body_bytes": document.get("body_bytes"),
                "body": _clip(body, POSTING_CHARS),
            }
    return None


def _order_section(root: Path, queue: dict[str, Any] | None) -> dict[str, Any]:
    """★What was ordered★: the one string that says what to make, and where it came from.

    Order 91000001, 2026-08-07 23:36. The builder was shown 題材『パズルクエストX』 and
    納品はGoogleドキュメントで, and produced a general guide to the game. The words it was
    never shown are the order's own name -- 「ポケモン動画の企画・台本作成ができる方を募集します」
    -- the only place 企画 and 台本 exist anywhere on that order. Measured on that pass:
    ``grep -c 企画 PAID_WORK.prompt.txt`` returned 0. A 題材 and a file format are not a
    deliverable, and nothing in this compiler was carrying the difference.

    Precedence is ``artifact_judge.posting_text``'s, reused rather than re-decided: durable
    store first because it sits outside the builder's writable tree, project copy second.

    ★Neither exists for a direct offer, so a third source is required.★ B6 measured
    ``source/posting/`` in 1 of 9 live projects, and 91000001 arrived as ``offer:92000015`` --
    an order we never applied to, so nothing ever harvested a posting for it. The order
    label the marketplace collector already puts on the queue item is the only carrier in
    that case. It is third, not first, because it is a scraped label rather than the
    buyer's own document.

    ★Absence is recorded, never silent.★ When no source carries a title, ``looked_in`` names
    the concrete places that were checked, so "nobody ever wrote down what to build"
    (the honest state of 91000001 before A7 asks) cannot be confused with "the compiler
    dropped it".
    """
    queue = queue if isinstance(queue, dict) else {}
    request_id = str(queue.get("request_id") or root.name or "").strip()
    looked_in: list[str] = []
    title = ""
    origin = ""
    if request_id:
        store_path = posting_store() / f"request-{request_id}.json"
        looked_in.append(str(store_path))
        title = str(_json(store_path).get("title") or "").strip()
        if title:
            origin = "posting_store"
    if not title:
        pattern = root / "source" / "posting" / "request-*.json"
        looked_in.append(str(pattern))
        try:
            candidates = sorted(pattern.parent.glob(pattern.name))
        except OSError:
            candidates = []
        for path in candidates:
            title = str(_json(path).get("title") or "").strip()
            if title:
                origin = "project_posting"
                break
    if not title:
        looked_in.append("queue_item.title (marketplace order label)")
        title = str(queue.get("title") or "").strip()
        if title:
            origin = "order_label"
    section: dict[str, Any] = {
        "title": _clip(title, ORDER_TITLE_CHARS) or None,
        "title_source": origin or "none",
    }
    # The only scale signal that exists on the order. A ¥5,000 台本 and a ¥50,000 台本 are
    # different deliverables and nothing else in the packet says which one this is.
    price = queue.get("price_jpy")
    if isinstance(price, int) and not isinstance(price, bool):
        section["price_jpy"] = price
    contract_id = str(queue.get("contract_id") or queue.get("source_contract_id") or "").strip()
    if contract_id:
        section["contract_id"] = contract_id
    delivery_date = str(queue.get("delivery_date") or "").strip()
    if delivery_date:
        section["delivery_date"] = delivery_date
    if not title:
        section["looked_in"] = looked_in
    return section


def _dm_section(root: Path) -> dict[str, Any] | None:
    """The direct-message thread the material arrived in, plus its attachment index."""
    directory = root / "source" / "dm"
    try:
        files = sorted(path for path in directory.glob("thread-*-full.json") if path.is_file())
    except OSError:
        return None
    threads: list[dict[str, Any]] = []
    for path in files:
        document = _json(path)
        messages = document.get("messages")
        if not isinstance(messages, list) or not messages:
            continue
        rows = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            rows.append({
                "side": message.get("side"),
                "sent_at": message.get("sent_at"),
                "text": _clip(message.get("text"), DM_MESSAGE_CHARS),
                "attachments": [
                    str(item.get("filename") or "")
                    for item in message.get("attachments") or []
                    if isinstance(item, dict)
                ],
            })
        index = []
        for item in document.get("attachment_index") or []:
            if not isinstance(item, dict) or len(index) >= ATTACHMENT_ROWS:
                continue
            index.append({
                key: item.get(key)
                for key in ("filename", "bytes", "sha256", "path", "error")
                if item.get(key) is not None
            })
        threads.append({
            "path": str(path),
            "thread_id": document.get("thread_id"),
            "message_count": document.get("message_count"),
            "messages": rows,
            "attachment_index": index,
        })
    return {"threads": threads} if threads else None


def _requirements_section(root: Path) -> dict[str, Any] | None:
    """The current request, and everything the buyer has ever asked for.

    The second half is the point. ``persist_latest_paid_buyer_reply`` narrows the current
    request to what came after our last attachment -- correct for "what do I do now",
    catastrophic as "what did they ask for", which is how a stated fact stopped being a
    requirement after the first delivery.
    """
    path = root / "requirements" / "live-buyer-reply.json"
    payload = _json(path)
    if not payload:
        return None
    accumulated = []
    rows = payload.get("accumulated_requirements")
    if isinstance(rows, list):
        for row in rows[-ACCUMULATED_ROWS:]:
            if not isinstance(row, dict):
                continue
            accumulated.append({
                "sent_at": row.get("sent_at"),
                "text": _clip(row.get("text"), ACCUMULATED_CHARS),
                "attachments": row.get("attachments") or [],
            })
    return {
        "path": str(path),
        "buyer_feedback_stage": payload.get("buyer_feedback_stage"),
        "feedback_sha256": payload.get("feedback_sha256"),
        "current_request": _clip(payload.get("feedback_text"), CURRENT_REQUEST_CHARS),
        "everything_the_buyer_has_asked_for": accumulated,
    }


def _talkroom_section(root: Path) -> dict[str, Any] | None:
    path = root / "source" / "talkroom" / "messages.jsonl"
    rows = _jsonl_rows(path)
    if not rows:
        return None
    messages = []
    for row in rows:
        evidence = {
            key: row.get(key) for key in ("side", "sent_at", "message_id", "text", "attachments")
            if row.get(key) is not None
        }
        encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        messages.append({
            **evidence,
            "text": _clip(evidence.get("text"), DM_MESSAGE_CHARS),
            "source_fact_id": f"talkroom-message:sha256:{hashlib.sha256(encoded.encode()).hexdigest()}",
        })
    return {
        "path": str(path),
        "message_count": len(rows),
        "buyer_message_count": sum(1 for row in rows if row.get("side") == "buyer"),
        "seller_message_count": sum(1 for row in rows if row.get("side") == "seller"),
        "messages": messages,
    }


def _project_history(root: Path, references: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    """Hash-bound artifact lineage, external effects and the unresolved delta."""
    lineage = [
        reference for reference in references
        if str(reference.get("path") or "").startswith(("delivery/", "acceptance/"))
    ]
    effects = []
    for row in _jsonl_rows(root / "events.jsonl"):
        if row.get("event") == "economic_fact" and isinstance(row.get("fact"), dict):
            fact = row["fact"]
            capability = fact.get("capability_result") or {}
            effects.append({
                "fact_id": fact.get("fact_id"),
                "effect_key": fact.get("effect_key"),
                "kind": fact.get("kind"),
                "status": capability.get("status"),
                "source_fact_ids": capability.get("source_fact_ids") or [],
            })
    latest_acceptance = None
    acceptance_files = sorted(
        (path for path in (root / "acceptance").glob("acceptance-*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime_ns,
    )
    if acceptance_files:
        path = acceptance_files[-1]
        value = _json(path)
        latest_acceptance = {
            "path": str(path), "sha256": _bytes_sha(path)[1],
            "status": value.get("status"), "artifact_version": value.get("artifact_version"),
            "package_sha256": value.get("package_sha256"),
            "acceptance_delta": value.get("acceptance_delta"),
        }
    return {
        "artifact_lineage": lineage,
        "latest_acceptance": latest_acceptance,
        "effects": effects,
        "current_delta": {
            key: state.get(key) for key in (
                "next_action", "work_state", "current_version", "current_package_sha256",
                "current_acceptance_status", "current_acceptance_delta",
                "buyer_feedback_sha256", "handled_buyer_feedback_sha256",
            )
        },
    }


def _commitments(root: Path) -> list[dict[str, Any]]:
    """What we told this buyer we would do.

    Order 91000002, 2026-08-06 15:46: we promised a first draft within a day of purchase,
    and every later pass rebuilt its context without our own promise in it. Our messages
    are in the ledgers next to theirs; nothing was ever selecting them.
    """
    rows: list[dict[str, Any]] = []
    for row in _jsonl_rows(root / "source" / "talkroom" / "messages.jsonl"):
        if row.get("side") == "seller" and str(row.get("text") or "").strip():
            rows.append({"source": "talkroom", "sent_at": row.get("sent_at"), "text": row["text"]})
    directory = root / "source" / "dm"
    try:
        files = sorted(path for path in directory.glob("thread-*-full.json") if path.is_file())
    except OSError:
        files = []
    for path in files:
        for message in _json(path).get("messages") or []:
            if isinstance(message, dict) and message.get("side") == "seller" and str(message.get("text") or "").strip():
                rows.append({
                    "source": "dm", "sent_at": message.get("sent_at"), "text": message["text"],
                })
    rows.sort(key=lambda row: str(row.get("sent_at") or ""))
    return [
        {**row, "text": _clip(row["text"], COMMITMENT_CHARS)}
        for row in rows[-COMMITMENT_ROWS:]
    ]


def _buyer_attachments(root: Path, references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attachments already on disk, from the refs this compiler computes anyway.

    Materializing them to text is the ``skills/_shared/buyer-attachments`` skill's job and
    is not reimplemented here; when that skill has written an index beside the project it
    is named in ``read_these_first`` instead of being duplicated.
    """
    rows = []
    for reference in references:
        path = str(reference.get("path") or "")
        if path.startswith(("source/buyer-attachments/", "source/dm/attachments/")):
            row = {
                "path": str(root / path),
                "bytes": reference.get("bytes"),
                "sha256": reference.get("sha256"),
            }
            if reference.get("restricted") is True:
                row = {
                    key: reference.get(key)
                    for key in ("bytes", "sha256", "content_type", "purpose", "restricted")
                }
            rows.append(row)
    return rows[:ATTACHMENT_ROWS]


def _encoded_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _fit(body: dict[str, Any]) -> dict[str, Any]:
    """Shrink the digest until it fits, and say what was dropped.

    Order matters: the newest material is worth more than the oldest, and a body we drop
    is still one ``read_these_first`` path away.
    """
    dropped: list[str] = []

    def trim_dm_messages() -> None:
        for thread in (body.get("dm") or {}).get("threads", []):
            thread["messages"] = thread["messages"][-4:]

    def trim_accumulated() -> None:
        requirements = body.get("requirements")
        if isinstance(requirements, dict):
            requirements["everything_the_buyer_has_asked_for"] = (
                requirements.get("everything_the_buyer_has_asked_for") or []
            )[-6:]

    def trim_posting() -> None:
        posting = body.get("posting")
        if isinstance(posting, dict):
            posting["body"] = _clip(posting.get("body"), 800)

    def trim_commitments() -> None:
        body["our_commitments"] = (body.get("our_commitments") or [])[-2:]

    trims = (
        ("dm_messages", trim_dm_messages),
        ("accumulated_requirements", trim_accumulated),
        ("posting_body", trim_posting),
        ("commitments", trim_commitments),
    )
    for name, trim in trims:
        if _encoded_bytes(body) <= COMBINED_MAX_BYTES:
            break
        trim()
        dropped.append(name)
    if _encoded_bytes(body) > COMBINED_MAX_BYTES:
        # Last resort. This block is carried inside a hard-bounded packet, and a packet
        # that refuses to build fails the whole paid lane -- so an over-budget digest
        # collapses to the paths and the current request rather than taking the lane
        # down. Everything dropped is still one open() away, which is the point of
        # read_these_first.
        current = (body.get("requirements") or {}).get("current_request")
        restricted = [
            row for row in body.get("buyer_attachments", [])
            if isinstance(row, dict) and row.get("restricted") is True
        ]
        body = {
            "version": body["version"],
            # ★ Survives the collapse. ★ What was ordered is the last thing worth dropping:
            # a builder left with the current message and no order name is exactly the
            # 91000001 state, and it is ~120 bytes.
            "order": body.get("order", {}),
            "sources_present": body.get("sources_present", []),
            "read_these_first": body.get("read_these_first", [])[:24],
            "requirements": {"current_request": _clip(current, CURRENT_REQUEST_CHARS)},
        }
        if restricted:
            body["buyer_attachments"] = restricted
        dropped.append("collapsed_to_paths")
    body["bytes"] = _encoded_bytes(body)
    if dropped:
        body["truncated"] = dropped
    return body


def combined_context(
    root: Path, references: list[dict[str, Any]], queue: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One block holding all four sources, bounded, with the paths to the full bodies.

    ``order`` is deliberately not one of the four and is not listed in ``sources_present``:
    it is the identity of the thing being built, assembled from whichever source has it,
    and it is the one field that must survive every trim.
    """
    root = Path(root)
    body: dict[str, Any] = {"version": 1, "order": _order_section(root, queue)}
    posting = _posting_section(root)
    if posting is not None:
        body["posting"] = posting
    proposal = _proposal_section(root)
    if proposal is not None:
        body["proposal"] = proposal
    dm_thread = _dm_section(root)
    if dm_thread is not None:
        body["dm"] = dm_thread
    requirements = _requirements_section(root)
    if requirements is not None:
        body["requirements"] = requirements
    talkroom = _talkroom_section(root)
    if talkroom is not None:
        body["talkroom"] = talkroom
    commitments = _commitments(root)
    if commitments:
        body["our_commitments"] = commitments
    attachments = _buyer_attachments(root, references)
    if attachments:
        body["buyer_attachments"] = attachments
    body["project_history"] = _project_history(root, references, state or {})
    body["buyer_trust_context"] = {
        "instruction": "Interpret buyer emotion and trust only from the cited message source_fact_ids.",
        "evidence": [
            {"source_fact_id": row["source_fact_id"], "sent_at": row.get("sent_at"), "text": row.get("text")}
            for row in (talkroom or {}).get("messages", []) if row.get("side") == "buyer"
        ],
    }
    body["read_these_first"] = [
        str(section["path"])
        for section in (posting, proposal, requirements, talkroom)
        if isinstance(section, dict) and section.get("path")
    ] + [
        str(thread["path"]) for thread in (dm_thread or {}).get("threads", [])
    ] + [row["path"] for row in attachments if isinstance(row.get("path"), str)]
    body["sources_present"] = sorted(
        key for key in ("posting", "proposal", "dm", "requirements", "talkroom", "our_commitments")
        if key in body
    )
    return _fit(body)


def compile_context(root: Path, queue: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    state = _json(root / "state.json")
    request_id = str(state.get("request_id") or queue.get("request_id") or "").strip()
    talkroom_id = str(state.get("talkroom_id") or queue.get("talkroom_id") or "").strip()
    if not request_id or not talkroom_id:
        raise ValueError("project_context_identity_missing")
    references = _refs(root)
    body: dict[str, Any] = {
        "version": 1,
        "thread_id": f"coconala:{request_id}:{talkroom_id}",
        "project_root": str(root),
        "identity": {"request_id": request_id, "talkroom_id": talkroom_id},
        "current_state": {key: state[key] for key in STATE_FIELDS if key in state},
        "current_queue": {key: queue[key] for key in QUEUE_FIELDS if key in queue},
        "recent_events": _recent_events(root / "events.jsonl"),
        "source_refs": references,
        "combined_context": combined_context(root, references, queue, state),
    }
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body["project_context_sha256"] = hashlib.sha256(encoded).hexdigest()
    return body


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def append_context_read_receipt(
    root: Path, compiled: dict[str, Any], queue: dict[str, Any]
) -> dict[str, Any]:
    live_path = Path(str(queue.get("talkroom_evidence_file") or "")).expanduser().resolve()
    if not live_path.is_file():
        raise ValueError("live_talkroom_evidence_missing")
    live_bytes, live_sha = _bytes_sha(live_path)
    sources = [
        *compiled["source_refs"],
        {"path": str(live_path), "bytes": live_bytes, "sha256": live_sha, "source": "live_talkroom_dom"},
    ]
    identity = compiled.get("identity") or {}
    request_id = str(identity.get("request_id") or "")
    talkroom_id = str(identity.get("talkroom_id") or "")
    grouped: dict[str, list[dict[str, Any]]] = {}
    live_proof: dict[str, Any] | None = None
    for source in sources:
        if not isinstance(source, dict):
            continue
        key = source_resource_key(
            source.get("path") or "", request_id, talkroom_id, source=source,
        )
        if key is None:
            continue
        proof = {
            field: source[field]
            for field in ("path", "bytes", "sha256", "source")
            if source.get(field) is not None
        }
        grouped.setdefault(key, []).append(proof)
        if source.get("source") == "live_talkroom_dom":
            live_proof = proof
    source_reads = []
    for key in sorted(grouped):
        proofs = sorted(
            grouped[key],
            key=lambda value: (
                str(value.get("path") or ""),
                int(value.get("bytes") or 0),
                str(value.get("sha256") or ""),
            ),
        )
        encoded = json.dumps(
            proofs, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        source_reads.append({
            "resource_key": key,
            "source_count": len(proofs),
            "bytes": sum(int(value.get("bytes") or 0) for value in proofs),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        })
    body = {
        "version": 1,
        "thread_id": compiled["thread_id"],
        "project_context_sha256": compiled["project_context_sha256"],
        "input_event_id": str(queue.get("buyer_feedback_sha256") or ""),
        "observed_at": str(queue.get("talkroom_observed_at") or ""),
        "source_count": len(compiled["source_refs"]),
        "sources_read_count": len(sources),
        "sources_read": source_reads,
        "live_talkroom": live_proof,
    }
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    receipt = {**body, "receipt_sha256": hashlib.sha256(encoded).hexdigest()}
    ledger = root.resolve() / "context" / "context-read-receipts.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    try:
        existing = ledger.read_text(encoding="utf-8")
    except OSError:
        pass
    if receipt["receipt_sha256"] not in existing:
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return receipt


def source_resource_key(
    path: str,
    request_id: str,
    talkroom_id: str,
    *,
    source: dict[str, Any] | None = None,
) -> str | None:
    """Classify one read source into the EV1 resource-key vocabulary (spec §4.1).

    ★ Paths arrive in both forms. ★ ``_refs`` records them relative to the project root
    ("source/posting/request-91000002.json") while ``append_context_read_receipt`` appends
    the live DOM capture as an absolute path, so the leading slash is normalised before
    matching. Matching on "/source/posting/" alone silently filed every relative source
    under project state, which makes spec §4.2 ``sources_read_before_work`` unsatisfiable
    even on a pass that really did read the posting and the DM.

    ``dm:`` is the fourth resource kind, beyond the three the spec enumerates: B1 reads
    four distinct sources and the check has to tell a DM read from a talkroom read.
    """
    text = str(path or "")
    if not text.startswith("/"):
        text = "/" + text
    if "/source/posting/" in text:
        return f"posting:{request_id}" if request_id else None
    if "/source/dm/" in text:
        return f"dm:{request_id}" if request_id else None
    if (isinstance(source, dict) and source.get("source") == "live_talkroom_dom") \
            or "/source/talkroom/" in text or "talkroom-" in Path(text).name:
        return f"talkroom:{talkroom_id}" if talkroom_id else None
    return f"project:{request_id}" if request_id else None


def record_source_reads(compiled: dict[str, Any], receipt: dict[str, Any]) -> None:
    """One EV1 `read` line per resource this compile actually hashed.

    ★ Driven by the receipt, not by intent. ★ ``sources_read`` now has one deterministic
    aggregate per resource whose files were hashed, so a line here means that resource
    existed and was read -- exactly the fact spec §4.2 ``sources_read_before_work`` needs,
    without emitting one trajectory event for every historical file.
    """
    identity = compiled.get("identity") or {}
    request_id = str(identity.get("request_id") or "")
    talkroom_id = str(identity.get("talkroom_id") or "")
    for source in receipt.get("sources_read") or []:
        if not isinstance(source, dict):
            continue
        key = str(source.get("resource_key") or "").strip()
        if not key:
            key = source_resource_key(source.get("path") or "", request_id, talkroom_id)
        if key is None:
            continue
        digest = str(source.get("sha256") or "").lower()
        record_trajectory(
            stage="PAID_WORK", lane="delivery", resource_key=key, action="read",
            result="ok", artifact_sha256=digest if len(digest) == 64 else None,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--queue-item", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence-output", type=Path)
    parser.add_argument("--receipt-evidence-output", type=Path)
    args = parser.parse_args()
    queue = _json(args.queue_item)
    if not queue:
        raise SystemExit("project context queue item must be an object")
    compiled = compile_context(args.project_root, queue)
    atomic_json(args.output, compiled)
    if args.evidence_output is not None:
        atomic_json(args.evidence_output, compiled)
    receipt = append_context_read_receipt(args.project_root, compiled, queue)
    if args.receipt_evidence_output is not None:
        atomic_json(args.receipt_evidence_output, receipt)
    record_source_reads(compiled, receipt)
    print(json.dumps({
        "ok": True,
        "thread_id": compiled["thread_id"],
        "project_context_sha256": compiled["project_context_sha256"],
        "source_count": len(compiled["source_refs"]),
        "combined_sources": compiled["combined_context"]["sources_present"],
        # Surfaced so a pass log shows "none" the moment an order arrives with nothing
        # naming what to build, instead of that fact living only inside the packet.
        "order_title_source": compiled["combined_context"].get("order", {}).get("title_source"),
        "combined_context_bytes": compiled["combined_context"]["bytes"],
        "context_read_receipt_sha256": receipt["receipt_sha256"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
