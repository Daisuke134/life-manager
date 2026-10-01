#!/usr/bin/env python3
"""Persist a verified fundraiser application dossier and its compact index row."""

from __future__ import annotations

import argparse
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
        return
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
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()

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

    if args.prepare:
        if not args.ledger or not args.applications_dir:
            fail("--prepare requires --ledger and --applications-dir for pre-submit deduplication")
        prior = read_rows(pathlib.Path(args.ledger)) + read_dossiers(pathlib.Path(args.applications_dir))
        if is_terminal_duplicate(data, identity_hash, prior):
            fail(f"duplicate terminal application: {identity_hash}")
        _advance_effect_marker("pre_effect", "effect_attempted", 1)
        if data.get("submitted_at") is not None or data.get("evidence") is not None:
            fail("prepare requires a pre-submit draft without submitted_at or evidence")
        data["application_digest"] = digest
        data["previewed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        replace_json(draft_path, data)
        print(json.dumps({"prepared": True, "application_digest": digest}))
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
    prior = read_rows(ledger) + read_dossiers(pathlib.Path(args.applications_dir))
    if is_terminal_duplicate(data, identity_hash, prior):
        fail(f"duplicate terminal application: {identity_hash}")
    _advance_effect_marker("effect_attempted", "post_effect_verified", 1)

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
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    encoded = (json.dumps(dossier, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=applications_dir, delete=False) as handle:
        handle.write(encoded)
        temp_path = pathlib.Path(handle.name)
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, dossier_path)
    dossier_sha = hashlib.sha256(encoded).hexdigest()

    ledger.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    row = {
        "run_id": args.run_id,
        "receipt_identity": identity,
        "receipt_identity_hash": identity_hash,
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
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.chmod(ledger, 0o600)
    print(json.dumps({"recorded": True, "receipt_identity_hash": identity_hash,
                      "application_record_path": str(dossier_path)}))


if __name__ == "__main__":
    main()
