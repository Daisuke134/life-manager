#!/usr/bin/env python3
"""Persist a verified fundraiser application dossier and its compact index row."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import stat
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit


TERMINAL = {"submitted_verified", "submit_unknown"}
TARGET_UNRESOLVED = {"pending", "effect_attempted", "submit_unknown"}
TARGET_HOLDING = TARGET_UNRESOLVED | {"submitted_verified"}
TARGET_STATUSES = TARGET_HOLDING | {"verified_pre_effect_failure"}
BLOCKED_LEGACY_TARGETS = {"deepscaleventures"}
TARGET_LEDGER_NAME = "target-intents.jsonl"
APPLICATION_FIELDS = (
    "organization", "program", "cohort_window", "account", "official_url",
    "contact", "question_answers", "attachments", "context_used",
    "context_version", "context_digest",
)
SAFE_OCCURRENCE = re.compile(r"fundraiser:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
MARKER_PHASES = {"pre_effect", "effect_attempted", "human_required", "post_effect_verified"}


def fail(message: str) -> None:
    raise SystemExit(f"record-application: {message}")


def required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{name} must be non-empty text")
    return value.strip()


def canonical_identity(data: dict) -> tuple[str, str]:
    parts = [
        required_text(data.get("organization"), "organization"),
        required_text(data.get("program"), "program"),
        required_text(data.get("cohort_window"), "cohort_window"),
        required_text(data.get("account"), "account"),
    ]
    identity = " | ".join(part.casefold() for part in parts)
    return identity, hashlib.sha256(identity.encode()).hexdigest()


def normalized_url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlsplit(value.strip().casefold())
    host = parsed.netloc.removeprefix("www.")
    return f"{host}{parsed.path.rstrip('/') or '/'}"


def date_markers(*values: object) -> set[str]:
    text = " ".join(str(value) for value in values if value).casefold()
    markers = set(re.findall(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b", text))
    months = {name.casefold(): index for index, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"), 1)}
    for month, day, year in re.findall(
            r"\b(" + "|".join(months) + r")\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b", text):
        markers.add(f"{year}-{months[month]:02d}-{int(day):02d}")
    return markers


def row_parts(row: dict) -> tuple[str, str, str, str]:
    structured = tuple(str(row.get(key) or "").strip() for key in
                       ("organization", "program", "cohort_window", "account"))
    if any(structured):
        return structured
    parts = [part.strip() for part in str(row.get("receipt_identity") or "").split("|")]
    return tuple((parts + [""] * 4)[:4])


def is_terminal_duplicate(data: dict, identity_hash: str, rows: list[dict]) -> bool:
    candidate_url = normalized_url(data.get("official_url"))
    candidate_dates = date_markers(data.get("organization"), data.get("program"),
                                   data.get("cohort_window"))
    for row in rows:
        if row.get("status") not in TERMINAL:
            continue
        if row.get("receipt_identity_hash") == identity_hash:
            return True
        organization, program, cohort, account = row_parts(row)
        prior_dates = date_markers(organization, program, cohort)
        if candidate_url and candidate_url == normalized_url(row.get("official_url")) \
                and candidate_dates & prior_dates:
            return True
        if tuple(str(data.get(key) or "").strip().casefold() for key in
                 ("organization", "program", "cohort_window", "account")) == tuple(
                    value.casefold() for value in (organization, program, cohort, account)):
            return True
    return False


def read_rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def read_dossiers(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for dossier in path.glob("*.json"):
        try:
            rows.append(json.loads(dossier.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return rows


def application_digest(data: dict) -> str:
    payload = {key: data.get(key) for key in APPLICATION_FIELDS}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def normalized_target_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def canonical_target_identity(data: dict) -> tuple[str, str]:
    application_identity, _ = canonical_identity(data)
    contact = data.get("contact")
    if not isinstance(contact, dict):
        fail("contact must be an object")
    method = required_text(contact.get("method"), "contact.method").casefold()
    destination = required_text(contact.get("destination"), "contact.destination")
    if method in {"email", "mail"}:
        destination = destination.casefold()
    else:
        destination = normalized_url(destination) or " ".join(destination.casefold().split())
    identity = f"{application_identity} | {method} | {destination}"
    return identity, hashlib.sha256(identity.encode()).hexdigest()


def target_hash_if_available(data: dict) -> str | None:
    if not isinstance(data, dict) or not isinstance(data.get("contact"), dict):
        return None
    required = ("organization", "program", "cohort_window", "account")
    if any(not isinstance(data.get(key), str) or not data[key].strip() for key in required):
        return None
    contact = data["contact"]
    if any(not isinstance(contact.get(key), str) or not contact[key].strip()
           for key in ("method", "destination")):
        return None
    return canonical_target_identity(data)[1]


def target_ledger_path(ledger: pathlib.Path) -> pathlib.Path:
    return ledger.parent / TARGET_LEDGER_NAME


def _read_target_rows(descriptor: int) -> list[dict]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks = []
    while True:
        chunk = os.read(descriptor, 64 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    try:
        text = b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError:
        fail("target intent ledger encoding is invalid")
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            fail("target intent ledger contains an invalid row")
        if (
            not isinstance(row, dict)
            or row.get("schema_version") != 1
            or row.get("status") not in TARGET_STATUSES
            or not isinstance(row.get("target_identity_hash"), str)
            or not isinstance(row.get("occurrence_id"), str)
            or not isinstance(row.get("application_digest"), str)
        ):
            fail("target intent ledger row shape is invalid")
        rows.append(row)
    return rows


def _with_target_ledger(path: pathlib.Path, callback):
    parent = path.parent
    if parent.is_symlink():
        fail("target intent directory must not be a symlink")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = parent.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        fail("target intent directory ownership is invalid")
    os.chmod(parent, 0o700)
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError:
        fail("target intent ledger is unavailable")
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            fail("target intent ledger ownership is invalid")
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        rows = _read_target_rows(descriptor)
        result = callback(descriptor, rows)
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return result
    finally:
        os.close(descriptor)


def _append_target_row(descriptor: int, row: dict) -> None:
    payload = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    os.lseek(descriptor, 0, os.SEEK_END)
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        view = view[written:]
    os.fsync(descriptor)


def _require_occurrence_resolved(
    rows: list[dict], occurrence_id: str, *, except_target_hash: str | None = None,
) -> None:
    latest_by_target: dict[str, dict] = {}
    for row in rows:
        if row["occurrence_id"] == occurrence_id:
            latest_by_target[row["target_identity_hash"]] = row
    for target_hash, row in latest_by_target.items():
        if target_hash != except_target_hash and row["status"] in TARGET_UNRESOLVED:
            fail(f"occurrence is held by unresolved target state {row['status']}")


def reserve_target(
    path: pathlib.Path, row: dict, prior: list[dict], organization: str,
) -> None:
    organization_key = normalized_target_name(organization)
    if organization_key in BLOCKED_LEGACY_TARGETS:
        fail("legacy unknown target is blocked")
    for old in prior:
        if old.get("status") in TERMINAL and (
            old.get("target_identity_hash") == row["target_identity_hash"]
            or target_hash_if_available(old) == row["target_identity_hash"]
        ):
            fail("target already has a terminal application receipt")

    def reserve(descriptor: int, rows: list[dict]) -> None:
        _require_occurrence_resolved(rows, row["occurrence_id"])
        previous = next((item for item in reversed(rows)
                         if item["target_identity_hash"] == row["target_identity_hash"]), None)
        if previous and previous["status"] in TARGET_HOLDING:
            fail(f"target is fenced by {previous['status']}")
        _append_target_row(descriptor, row)

    _with_target_ledger(path, reserve)


def finalize_target(path: pathlib.Path, row: dict, expected_status: str) -> None:
    def finalize(descriptor: int, rows: list[dict]) -> None:
        _require_occurrence_resolved(
            rows, row["occurrence_id"], except_target_hash=row["target_identity_hash"],
        )
        previous = next((item for item in reversed(rows)
                         if item["target_identity_hash"] == row["target_identity_hash"]), None)
        if (
            not previous
            or previous["status"] != expected_status
            or previous["occurrence_id"] != row["occurrence_id"]
            or previous["application_digest"] != row["application_digest"]
        ):
            fail(f"target {expected_status} intent does not match this occurrence and digest")
        _append_target_row(descriptor, row)

    _with_target_ledger(path, finalize)


def require_target_state(
    path: pathlib.Path, target_hash: str, occurrence_id: str, digest: str,
    expected_status: str,
) -> None:
    def check(_descriptor: int, rows: list[dict]) -> None:
        _require_occurrence_resolved(rows, occurrence_id, except_target_hash=target_hash)
        previous = next((item for item in reversed(rows)
                         if item["target_identity_hash"] == target_hash), None)
        if (
            not previous
            or previous["status"] != expected_status
            or previous["occurrence_id"] != occurrence_id
            or previous["application_digest"] != digest
        ):
            fail(f"target {expected_status} intent does not match this occurrence and digest")

    _with_target_ledger(path, check)


def append_receipt_row(path: pathlib.Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError:
        fail("application receipt ledger is unavailable")
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            fail("application receipt ledger ownership is invalid")
        os.fchmod(descriptor, 0o600)
        payload = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def replace_json(path: pathlib.Path, data: dict) -> None:
    encoded = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(encoded)
        temporary = pathlib.Path(handle.name)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _effect_marker_context() -> tuple[pathlib.Path, str] | None:
    path_value = os.environ.get("FUNDRAISER_EFFECT_MARKER")
    occurrence_id = os.environ.get("FUNDRAISER_OCCURRENCE_ID")
    if not path_value and not occurrence_id:
        return None
    if (not path_value or not occurrence_id
            or not SAFE_OCCURRENCE.fullmatch(occurrence_id)):
        fail("effect marker identity is invalid")
    return pathlib.Path(path_value), occurrence_id


def _read_effect_marker(path: pathlib.Path, occurrence_id: str) -> dict:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            fail("effect marker permissions are invalid")
        with os.fdopen(descriptor, "r", encoding="utf-8") as source:
            descriptor = -1
            marker = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        fail("effect marker is unavailable")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        not isinstance(marker, dict)
        or marker.get("schema_version") != 1
        or marker.get("owner_id") != "fundraiser"
        or marker.get("occurrence_id") != occurrence_id
        or marker.get("phase") not in MARKER_PHASES
        or marker.get("effect") not in {0, 1}
    ):
        fail("effect marker shape is invalid")
    return marker


def _advance_effect_marker(expected_phase: str, next_phase: str, effect: int) -> None:
    context = _effect_marker_context()
    if context is None:
        fail("effect marker is required")
    path, occurrence_id = context
    marker = _read_effect_marker(path, occurrence_id)
    if marker["phase"] != expected_phase:
        fail(f"effect marker phase is {marker['phase']}, expected {expected_phase}")
    marker.update({
        "phase": next_phase,
        "effect": effect,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    replace_json(path, marker)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", required=True)
    parser.add_argument("--ledger")
    parser.add_argument("--applications-dir")
    parser.add_argument("--run-id")
    parser.add_argument("--expected-context-version", required=True)
    parser.add_argument("--expected-context-digest", required=True)
    parser.add_argument("--occurrence", default=os.environ.get("FUNDRAISER_OCCURRENCE_ID"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--claim-effect", action="store_true")
    mode.add_argument("--terminal-status", choices=("submit_unknown", "verified_pre_effect_failure"))
    parser.add_argument("--status-evidence")
    args = parser.parse_args()

    occurrence_id = required_text(args.occurrence, "occurrence")
    if not SAFE_OCCURRENCE.fullmatch(occurrence_id):
        fail("occurrence identity is invalid")
    marker_context = _effect_marker_context()
    if marker_context is None or marker_context[1] != occurrence_id:
        fail("matching occurrence effect marker is required")
    marker_path = marker_context[0]
    marker = _read_effect_marker(marker_path, occurrence_id)

    draft_path = pathlib.Path(args.draft)
    data = json.loads(draft_path.read_text(encoding="utf-8"))
    identity, identity_hash = canonical_identity(data)
    official_url = required_text(data.get("official_url"), "official_url")
    contact = data.get("contact")
    if not isinstance(contact, dict):
        fail("contact must be an object")
    required_text(contact.get("method"), "contact.method")
    required_text(contact.get("destination"), "contact.destination")

    answers = data.get("question_answers")
    if not isinstance(answers, list) or not answers:
        fail("question_answers must contain every submitted field")
    for index, item in enumerate(answers):
        if not isinstance(item, dict):
            fail(f"question_answers[{index}] must be an object")
        required_text(item.get("question"), f"question_answers[{index}].question")
        if "answer" not in item or item["answer"] is None:
            fail(f"question_answers[{index}].answer is required")

    if not isinstance(data.get("context_used"), dict) or not data["context_used"]:
        fail("context_used must record the actual claims/sources used")

    context_version = required_text(data.get("context_version"), "context_version")
    context_digest = required_text(data.get("context_digest"), "context_digest")
    if context_version != args.expected_context_version:
        fail("context_version does not match the current canonical context")
    if context_digest != args.expected_context_digest:
        fail("context_digest does not match the current canonical context")
    digest = application_digest(data)
    _, target_hash = canonical_target_identity(data)

    if args.prepare:
        if not args.ledger or not args.applications_dir:
            fail("--prepare requires --ledger and --applications-dir for pre-submit deduplication")
        if not (
            (marker["phase"] == "pre_effect" and marker["effect"] == 0)
            or (marker["phase"] == "post_effect_verified" and marker["effect"] == 1)
        ):
            fail("prepare requires a clear occurrence after any prior verified target")
        prior = read_rows(pathlib.Path(args.ledger)) + read_dossiers(pathlib.Path(args.applications_dir))
        if is_terminal_duplicate(data, identity_hash, prior):
            fail(f"duplicate terminal application: {identity_hash}")
        if data.get("submitted_at") is not None or data.get("evidence") is not None:
            fail("prepare requires a pre-submit draft without submitted_at or evidence")
        target_row = {
            "schema_version": 1,
            "target_identity_hash": target_hash,
            "receipt_identity_hash": identity_hash,
            "occurrence_id": occurrence_id,
            "application_digest": digest,
            "status": "pending",
            "effect": 0,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        reserve_target(target_ledger_path(pathlib.Path(args.ledger)), target_row, prior,
                       required_text(data.get("organization"), "organization"))
        data["application_digest"] = digest
        data["previewed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        replace_json(draft_path, data)
        print(json.dumps({"prepared": True, "application_digest": digest}))
        return

    if args.claim_effect:
        for name in ("ledger", "applications_dir"):
            if not getattr(args, name):
                fail(f"--claim-effect requires --{name.replace('_', '-')}")
        if required_text(data.get("application_digest"), "application_digest") != digest:
            fail("application_digest does not match the prepared application")
        required_text(data.get("previewed_at"), "previewed_at")
        if not (
            (marker["phase"] == "pre_effect" and marker["effect"] == 0)
            or (marker["phase"] == "post_effect_verified" and marker["effect"] == 1)
        ):
            fail("effect claim requires the current target to follow a resolved target")
        target_path = target_ledger_path(pathlib.Path(args.ledger))
        require_target_state(target_path, target_hash, occurrence_id, digest, "pending")
        _advance_effect_marker(marker["phase"], "effect_attempted", 1)
        finalize_target(target_path, {
            "schema_version": 1,
            "target_identity_hash": target_hash,
            "receipt_identity_hash": identity_hash,
            "occurrence_id": occurrence_id,
            "application_digest": digest,
            "status": "effect_attempted",
            "effect": 1,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }, "pending")
        print(json.dumps({"effect_claimed": True, "application_digest": digest}))
        return

    if args.terminal_status:
        for name in ("ledger", "applications_dir", "run_id"):
            if not getattr(args, name):
                fail(f"--terminal-status requires --{name.replace('_', '-')}")
        if required_text(data.get("application_digest"), "application_digest") != digest:
            fail("application_digest does not match the prepared application")
        required_text(data.get("previewed_at"), "previewed_at")
        status_evidence = required_text(args.status_evidence, "status-evidence")
        if args.terminal_status == "submit_unknown":
            if marker["phase"] != "effect_attempted" or marker["effect"] != 1:
                fail("submit_unknown requires an attempted and unresolved occurrence")
            target_expected_status = "effect_attempted"
            effect = 1
        else:
            if not (
                (marker["phase"] == "pre_effect" and marker["effect"] == 0)
                or (marker["phase"] == "post_effect_verified" and marker["effect"] == 1)
            ):
                fail("verified_pre_effect_failure requires an unclaimed current target")
            target_expected_status = "pending"
            effect = 0
        target_row = {
            "schema_version": 1,
            "target_identity_hash": target_hash,
            "receipt_identity_hash": identity_hash,
            "occurrence_id": occurrence_id,
            "application_digest": digest,
            "status": args.terminal_status,
            "effect": effect,
            "evidence_ref": status_evidence,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        finalize_target(
            target_ledger_path(pathlib.Path(args.ledger)), target_row, target_expected_status,
        )
        receipt = {
            "run_id": args.run_id,
            "receipt_identity": identity,
            "receipt_identity_hash": identity_hash,
            "target_identity_hash": target_hash,
            "occurrence_id": occurrence_id,
            "organization": data["organization"],
            "program": data["program"],
            "cohort_window": data["cohort_window"],
            "official_url": official_url,
            "status": args.terminal_status,
            "effect": effect,
            "status_evidence": status_evidence,
            "utc_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "context_version": context_version,
            "context_digest": context_digest,
            "application_digest": digest,
        }
        append_receipt_row(pathlib.Path(args.ledger), receipt)
        print(json.dumps({"recorded": True, "status": args.terminal_status,
                          "receipt_identity_hash": identity_hash}))
        return

    for name in ("ledger", "applications_dir", "run_id"):
        if not getattr(args, name):
            fail(f"--{name.replace('_', '-')} is required when recording")
    if required_text(data.get("application_digest"), "application_digest") != digest:
        fail("application_digest does not match the prepared application")
    previewed_at = required_text(data.get("previewed_at"), "previewed_at")
    submitted_at = required_text(data.get("submitted_at"), "submitted_at")
    try:
        previewed_time = datetime.fromisoformat(previewed_at.replace("Z", "+00:00"))
        submitted_time = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
    except ValueError:
        fail("previewed_at and submitted_at must be ISO-8601")
    if submitted_time < previewed_time:
        fail("submitted_at must not precede previewed_at")

    evidence = data.get("evidence")
    if not isinstance(evidence, dict):
        fail("evidence must be an object")
    png = pathlib.Path(required_text(evidence.get("completion_png"), "evidence.completion_png"))
    if not png.is_absolute() or not png.is_file():
        fail("completion_png must be an existing absolute file")
    msgid = evidence.get("telegram_photo_message_id")
    if not isinstance(msgid, int) or msgid <= 0:
        fail("telegram_photo_message_id must be a positive integer")
    required_text(evidence.get("provider_readback"), "evidence.provider_readback")

    ledger = pathlib.Path(args.ledger)
    if marker["phase"] != "effect_attempted" or marker["effect"] != 1:
        fail("verified submission requires a claimed effect occurrence")
    require_target_state(
        target_ledger_path(ledger), target_hash, occurrence_id, digest, "effect_attempted",
    )
    prior = read_rows(ledger) + read_dossiers(pathlib.Path(args.applications_dir))
    if is_terminal_duplicate(data, identity_hash, prior):
        fail(f"duplicate terminal application: {identity_hash}")

    applications_dir = pathlib.Path(args.applications_dir)
    applications_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(applications_dir, 0o700)
    dossier_path = applications_dir / f"{identity_hash}.json"
    if dossier_path.exists():
        fail(f"dossier already exists: {dossier_path}")

    dossier = dict(data)
    dossier.update({
        "schema_version": 1,
        "run_id": args.run_id,
        "receipt_identity": identity,
        "receipt_identity_hash": identity_hash,
        "target_identity_hash": target_hash,
        "occurrence_id": occurrence_id,
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    encoded = (json.dumps(dossier, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=applications_dir, delete=False) as handle:
        handle.write(encoded)
        temp_path = pathlib.Path(handle.name)
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, dossier_path)
    dossier_sha = hashlib.sha256(encoded).hexdigest()

    finalize_target(target_ledger_path(ledger), {
        "schema_version": 1,
        "target_identity_hash": target_hash,
        "receipt_identity_hash": identity_hash,
        "occurrence_id": occurrence_id,
        "application_digest": digest,
        "status": "submitted_verified",
        "effect": 1,
        "evidence_ref": evidence["provider_readback"],
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }, "effect_attempted")
    _advance_effect_marker("effect_attempted", "post_effect_verified", 1)
    row = {
        "run_id": args.run_id,
        "receipt_identity": identity,
        "receipt_identity_hash": identity_hash,
        "target_identity_hash": target_hash,
        "occurrence_id": occurrence_id,
        "organization": data["organization"],
        "program": data["program"],
        "cohort_window": data["cohort_window"],
        "official_url": official_url,
        "status": "submitted_verified",
        "utc_timestamp": submitted_at,
        "context_version": context_version,
        "context_digest": context_digest,
        "application_digest": digest,
        "provider_readback": evidence["provider_readback"],
        "completion_png": str(png),
        "telegram_photo_message_id": msgid,
        "application_record_path": str(dossier_path),
        "application_record_sha256": dossier_sha,
    }
    append_receipt_row(ledger, row)
    print(json.dumps({"recorded": True, "receipt_identity_hash": identity_hash,
                      "application_record_path": str(dossier_path)}))


if __name__ == "__main__":
    main()
