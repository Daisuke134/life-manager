#!/usr/bin/env python3
"""Durable, monotonic intent fence for one marketplace application request.

The fence owns only bookkeeping. It never judges eligibility and it never talks to
the browser. A prepared intent means an uncertain click may already have happened,
so all later entries must reconcile the exact request ID and must not click again.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Iterator

from provider_adapter import EffectIntent
from provider_authorization import AuthorizationDecision, AuthorizationState


VERSION = 4
PREVIOUS_RETAINER_VERSION = 3
PREVIOUS_VERSION = 2
LEGACY_VERSION = 1
PREPARED = "prepared"
CONFIRMED = "confirmed"
# `RETIRED_ABSENT` is not a submission result.  It means a PREPARED intent was
# independently reconciled as absent and its old immutable record was archived
# before another *fresh* attempt may be prepared for the request.
RETIRED_ABSENT = "retired_absent"
_STATES = frozenset({PREPARED, CONFIRMED, RETIRED_ABSENT})
PRE_EFFECT = "pre_effect"
IRREVERSIBLE_ATTEMPT_STARTED = "irreversible_attempt_started"
_EFFECT_PHASES = frozenset({PRE_EFFECT, IRREVERSIBLE_ATTEMPT_STARTED})
_LEGACY_FIELDS = frozenset({
    "version", "state", "request_id", "snapshot_sha256", "proposal_sha256",
    "price_jpy", "deliver_date", "lease_fence", "cas",
})
_FIELDS_V2 = _LEGACY_FIELDS | {"effect_phase"}
_RETAINER_TERMS_FIELDS = frozenset({
    "work_frequency", "weekly_hours_min", "weekly_hours_max",
})
_FIELDS_V3 = _FIELDS_V2 | {"retainer_terms", "retainer_terms_sha256"}
_FIELDS = _FIELDS_V3 | {"screening_answers", "screening_answers_sha256"}
_SCREENING_ANSWER_FIELDS = frozenset({"question", "answer"})
_LEASE_FIELDS = frozenset({"task", "token", "generation"})
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_32 = re.compile(r"^[0-9a-f]{32}$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_RETAINER_ULID = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_RETAINER_FREQUENCIES = frozenset({
    "WEEK_ONE", "WEEK_TWO", "WEEK_THREE", "WEEK_FOUR", "WEEK_FIVE",
    "BIWEEKLY", "MONTH_ONE",
})
_AUTONOMOUS_AUTHORIZATION_STATES = frozenset({
    AuthorizationState.APPROVED_API,
    AuthorizationState.APPROVED_BROWSER,
})


class IntentFenceError(ValueError):
    """A malformed or non-monotonic durable intent is unsafe to act on."""


def proposal_sha256(proposal_text: str) -> str:
    return hashlib.sha256(proposal_text.encode("utf-8")).hexdigest()


def authorized_provider_intent(
    *,
    provider: str,
    account_key: str,
    resource_id: str,
    action: str,
    payload_hash: str,
    authorization: AuthorizationDecision,
) -> EffectIntent:
    """Build one logical provider effect only from current autonomous approval."""
    if (
        not isinstance(authorization, AuthorizationDecision)
        or authorization.state not in _AUTONOMOUS_AUTHORIZATION_STATES
        or authorization.receipt_hash is None
        or not _HEX_64.fullmatch(authorization.receipt_hash)
    ):
        raise IntentFenceError("authorization_not_approved")
    canonical = json.dumps(
        [provider, account_key, resource_id, action, payload_hash],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    effect_key = "provider-effect:v1:" + hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return EffectIntent(
        provider=provider,
        account_key=account_key,
        resource_id=resource_id,
        action=action,
        payload_hash=payload_hash,
        authorization_hash=authorization.receipt_hash,
        effect_key=effect_key,
    )


def build_cas(
    request_id: str,
    snapshot_sha256: str,
    proposal_hash: str,
    price_jpy: int,
    deliver_date: str,
    retainer_terms_sha256: str | None = None,
    screening_answers_sha256: str | None = None,
) -> str:
    base = f"{request_id}:{snapshot_sha256}:{proposal_hash}:{price_jpy}:{deliver_date}"
    if retainer_terms_sha256 is not None:
        base = f"{base}:{retainer_terms_sha256}"
    return base if screening_answers_sha256 is None else f"{base}:{screening_answers_sha256}"


def default_root() -> Path:
    return Path.home() / "gig" / "application-intents"


def _request_id(value: object) -> str:
    result = str(value).strip()
    if not (result.isdigit() or _RETAINER_ULID.fullmatch(result)):
        raise IntentFenceError("request_id_invalid")
    return result


def _sha256(value: object, field: str) -> str:
    result = str(value)
    if not _HEX_64.fullmatch(result):
        raise IntentFenceError(f"{field}_must_be_sha256")
    return result


def _price(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise IntentFenceError("price_jpy_must_be_positive_integer")
    return value


def _date(value: object) -> str:
    result = str(value).strip()
    if not _DATE.fullmatch(result):
        raise IntentFenceError("deliver_date_must_be_yyyy_mm_dd")
    return result


def _retainer_terms(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _RETAINER_TERMS_FIELDS:
        raise IntentFenceError("retainer_terms_fields_invalid")
    frequency = value["work_frequency"]
    minimum = value["weekly_hours_min"]
    maximum = value["weekly_hours_max"]
    if frequency not in _RETAINER_FREQUENCIES:
        raise IntentFenceError("retainer_work_frequency_invalid")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
        raise IntentFenceError("retainer_weekly_hours_min_invalid")
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum < minimum
    ):
        raise IntentFenceError("retainer_weekly_hours_max_invalid")
    return {
        "work_frequency": frequency,
        "weekly_hours_min": minimum,
        "weekly_hours_max": maximum,
    }


def _screening_answers(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 20:
        raise IntentFenceError("screening_answers_invalid")
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != _SCREENING_ANSWER_FIELDS:
            raise IntentFenceError("screening_answer_fields_invalid")
        question = item["question"]
        answer = item["answer"]
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            raise IntentFenceError("screening_answer_question_invalid")
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 5000:
            raise IntentFenceError("screening_answer_value_invalid")
        result.append({"question": question.strip(), "answer": answer.strip()})
    if len({item["question"] for item in result}) != len(result):
        raise IntentFenceError("screening_answers_duplicate")
    return result


def _lease_fence(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _LEASE_FIELDS:
        raise IntentFenceError("lease_fence_fields_invalid")
    task = value["task"]
    token = value["token"]
    generation = value["generation"]
    if not isinstance(task, str) or not task:
        raise IntentFenceError("lease_fence_task_invalid")
    if not isinstance(token, str) or not _HEX_32.fullmatch(token):
        raise IntentFenceError("lease_fence_token_invalid")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise IntentFenceError("lease_fence_generation_invalid")
    return {"task": task, "token": token, "generation": generation}


def intent_payload(
    *,
    request_id: object,
    snapshot_sha256: object,
    proposal_text: object,
    price_jpy: object,
    deliver_date: object,
    lease_fence: object,
    retainer_terms: object | None = None,
    screening_answers: object | None = None,
    state: str = PREPARED,
    effect_phase: str = PRE_EFFECT,
) -> dict[str, object]:
    """Construct an exact CAS-bound prepared payload, without writing it."""
    request = _request_id(request_id)
    snapshot = _sha256(snapshot_sha256, "snapshot_sha256")
    proposal = str(proposal_text)
    if not proposal.strip():
        raise IntentFenceError("proposal_text_required")
    price = _price(price_jpy)
    date = _date(deliver_date)
    fence = _lease_fence(lease_fence)
    if state not in _STATES:
        raise IntentFenceError("state_invalid")
    if effect_phase not in _EFFECT_PHASES:
        raise IntentFenceError("effect_phase_invalid")
    proposal_hash = proposal_sha256(proposal)
    is_retainer = _RETAINER_ULID.fullmatch(request) is not None
    if is_retainer and retainer_terms is None:
        raise IntentFenceError("retainer_terms_required")
    if not is_retainer and retainer_terms is not None:
        raise IntentFenceError("retainer_terms_for_single_forbidden")
    if is_retainer and screening_answers is None:
        raise IntentFenceError("screening_answers_required")
    if not is_retainer and screening_answers is not None:
        raise IntentFenceError("screening_answers_for_single_forbidden")
    base = {
        "version": VERSION,
        "state": state,
        "effect_phase": effect_phase,
        "request_id": request,
        "snapshot_sha256": snapshot,
        "proposal_sha256": proposal_hash,
        "price_jpy": price,
        "deliver_date": date,
        "lease_fence": fence,
    }
    if not is_retainer:
        # Preserve the existing single-offer shape and CAS exactly, including
        # replay of already-durable version-2 intents.
        return {
            **base,
            "version": PREVIOUS_VERSION,
            "cas": build_cas(request, snapshot, proposal_hash, price, date),
        }
    terms = _retainer_terms(retainer_terms)
    terms_hash = hashlib.sha256(
        json.dumps(terms, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    answers = _screening_answers(screening_answers)
    answers_hash = hashlib.sha256(
        json.dumps(answers, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        **base,
        "retainer_terms": terms,
        "retainer_terms_sha256": terms_hash,
        "screening_answers": answers,
        "screening_answers_sha256": answers_hash,
        "cas": build_cas(request, snapshot, proposal_hash, price, date, terms_hash, answers_hash),
    }


def validate_intent(value: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["intent_must_be_object"]
    version = value.get("version")
    expected_fields = (
        _LEGACY_FIELDS if version == LEGACY_VERSION
        else _FIELDS_V2 if version == PREVIOUS_VERSION
        else _FIELDS_V3 if version == PREVIOUS_RETAINER_VERSION
        else _FIELDS
    )
    actual = set(value)
    missing = sorted(expected_fields - actual)
    additional = sorted(actual - expected_fields)
    if missing:
        errors.append("intent_missing:" + ",".join(missing))
    if additional:
        errors.append("intent_additional:" + ",".join(additional))
    if errors:
        return errors
    if version not in {LEGACY_VERSION, PREVIOUS_VERSION, PREVIOUS_RETAINER_VERSION, VERSION}:
        errors.append("intent_version_invalid")
    if value["state"] not in _STATES:
        errors.append("intent_state_invalid")
    if version in {PREVIOUS_VERSION, PREVIOUS_RETAINER_VERSION, VERSION} and value["effect_phase"] not in _EFFECT_PHASES:
        errors.append("intent_effect_phase_invalid")
    try:
        request = _request_id(value["request_id"])
        is_retainer = _RETAINER_ULID.fullmatch(request) is not None
        if is_retainer and version not in {PREVIOUS_RETAINER_VERSION, VERSION}:
            errors.append("retainer_intent_version_invalid")
        if not is_retainer and version in {PREVIOUS_RETAINER_VERSION, VERSION}:
            errors.append("single_intent_version_invalid")
        snapshot = _sha256(value["snapshot_sha256"], "snapshot_sha256")
        proposal = _sha256(value["proposal_sha256"], "proposal_sha256")
        price = _price(value["price_jpy"])
        date = _date(value["deliver_date"])
        _lease_fence(value["lease_fence"])
        terms_hash = None
        answers_hash = None
        if version in {PREVIOUS_RETAINER_VERSION, VERSION}:
            terms = _retainer_terms(value["retainer_terms"])
            terms_hash = str(value["retainer_terms_sha256"])
            calculated_terms_hash = hashlib.sha256(
                json.dumps(terms, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if terms_hash != calculated_terms_hash:
                errors.append("retainer_terms_sha256_mismatch")
        if version == VERSION:
            answers = _screening_answers(value["screening_answers"])
            answers_hash = str(value["screening_answers_sha256"])
            calculated_answers_hash = hashlib.sha256(
                json.dumps(answers, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if answers_hash != calculated_answers_hash:
                errors.append("screening_answers_sha256_mismatch")
        if value["cas"] != build_cas(request, snapshot, proposal, price, date, terms_hash, answers_hash):
            errors.append("intent_cas_mismatch")
    except IntentFenceError as error:
        errors.append(str(error))
    return errors


def is_pre_effect(intent: dict[str, object]) -> bool:
    """Only versioned intents can prove that no irreversible attempt started."""
    return (
        intent.get("version") in {PREVIOUS_VERSION, PREVIOUS_RETAINER_VERSION, VERSION}
        and intent.get("state") == PREPARED
        and intent.get("effect_phase") == PRE_EFFECT
    )


def _durable_replace(path: Path, payload: dict[str, object]) -> None:
    """File and parent-directory fsync make prepared survive process loss."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(8)}")
    data = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class IntentStore:
    """Per-request durable intent state plus immutable absent-recovery archives."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()

    def intent_path(self, request_id: object) -> Path:
        return self.root / f"{_request_id(request_id)}.json"

    def _lock_path(self, request_id: object) -> Path:
        return self.root / f".{_request_id(request_id)}.lock"

    def _recovery_path(self, request_id: object, cas: object) -> Path:
        request = _request_id(request_id)
        digest = hashlib.sha256(str(cas).encode("utf-8")).hexdigest()
        return self.root / "recovery-history" / request / f"{digest}.json"

    @contextlib.contextmanager
    def locked(self, request_id: object) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._lock_path(request_id).open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_locked(self, request_id: object) -> dict[str, object] | None:
        path = self.intent_path(request_id)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise IntentFenceError("intent_read_invalid") from error
        errors = validate_intent(value)
        if errors:
            raise IntentFenceError(";".join(errors))
        assert isinstance(value, dict)
        if value["request_id"] != _request_id(request_id):
            raise IntentFenceError("intent_request_id_path_mismatch")
        return value

    def read(self, request_id: object) -> dict[str, object] | None:
        with self.locked(request_id):
            return self._read_locked(request_id)

    def prepare(self, **kwargs: object) -> dict[str, object]:
        candidate = intent_payload(**kwargs)
        request_id = candidate["request_id"]
        with self.locked(request_id):
            existing = self._read_locked(request_id)
            if existing is None or existing["state"] == RETIRED_ABSENT:
                _durable_replace(self.intent_path(request_id), candidate)
                return {
                    "intent": candidate,
                    "created": True,
                    "reconcile_only": False,
                    "cas_match": True,
                }
            # Prepared and confirmed are both terminal for click permission. The caller
            # must read official exact-ID history, regardless of the offered CAS value.
            return {
                "intent": existing,
                "created": False,
                "reconcile_only": True,
                "cas_match": existing["cas"] == candidate["cas"],
            }

    def retire_prepared_locked(
        self, request_id: object, *, expected_cas: object, reason: str | None = None
    ) -> dict[str, object]:
        """Archive a reconciled-absent PREPARED intent while the caller holds its lock.

        This does not grant a click. A caller-supplied reason must prove submit had not started.
        """
        existing = self._read_locked(request_id)
        if existing is None:
            raise IntentFenceError("retire_requires_prepared_intent")
        if existing["cas"] != str(expected_cas):
            raise IntentFenceError("retire_cas_mismatch")
        if existing["state"] != PREPARED:
            raise IntentFenceError("retire_state_invalid")
        archive_reason = (
            "official_exact_id_absent_and_fresh_form_observed"
            if reason is None else reason
        )
        if not isinstance(archive_reason, str) or not archive_reason.strip():
            raise IntentFenceError("retire_reason_invalid")
        archive = {
            "version": VERSION,
            "event": "prepared_reconciled_absent",
            "reason": archive_reason,
            "intent": existing,
        }
        _durable_replace(self._recovery_path(request_id, existing["cas"]), archive)
        retired = {**existing, "state": RETIRED_ABSENT}
        _durable_replace(self.intent_path(request_id), retired)
        return retired

    def mark_irreversible_attempt_started_locked(
        self, request_id: object, *, expected_cas: object
    ) -> dict[str, object]:
        """Durably close retry permission immediately before the submit click."""
        existing = self._read_locked(request_id)
        if existing is None:
            raise IntentFenceError("effect_start_requires_prepared_intent")
        if existing["cas"] != str(expected_cas):
            raise IntentFenceError("effect_start_cas_mismatch")
        if existing["state"] != PREPARED:
            raise IntentFenceError("effect_start_state_invalid")
        if not is_pre_effect(existing):
            raise IntentFenceError("effect_start_phase_invalid")
        started = {**existing, "effect_phase": IRREVERSIBLE_ATTEMPT_STARTED}
        _durable_replace(self.intent_path(request_id), started)
        return started

    def confirm(self, request_id: object, *, expected_cas: object) -> dict[str, object]:
        with self.locked(request_id):
            existing = self._read_locked(request_id)
            if existing is None:
                raise IntentFenceError("confirm_requires_prepared_intent")
            if existing["cas"] != str(expected_cas):
                raise IntentFenceError("confirm_cas_mismatch")
            if existing["state"] == CONFIRMED:
                return existing
            if existing["state"] != PREPARED:
                raise IntentFenceError("confirm_state_invalid")
            confirmed = {**existing, "state": CONFIRMED}
            _durable_replace(self.intent_path(request_id), confirmed)
            return confirmed


def _json_output(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--root", type=Path, default=default_root())
    prepare.add_argument("--request-id", required=True)
    prepare.add_argument("--snapshot-sha256", required=True)
    prepare.add_argument("--proposal-text", required=True)
    prepare.add_argument("--price-jpy", type=int, required=True)
    prepare.add_argument("--deliver-date", required=True)
    prepare.add_argument("--lease-fence-json", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("--root", type=Path, default=default_root())
    status.add_argument("--request-id", required=True)
    confirm = subparsers.add_parser("confirm")
    confirm.add_argument("--root", type=Path, default=default_root())
    confirm.add_argument("--request-id", required=True)
    confirm.add_argument("--expected-cas", required=True)
    args = parser.parse_args(argv)
    try:
        store = IntentStore(args.root)
        if args.command == "prepare":
            result = store.prepare(
                request_id=args.request_id,
                snapshot_sha256=args.snapshot_sha256,
                proposal_text=args.proposal_text,
                price_jpy=args.price_jpy,
                deliver_date=args.deliver_date,
                lease_fence=json.loads(args.lease_fence_json),
            )
            _json_output({
                "ok": True,
                "state": result["intent"]["state"],
                "created": result["created"],
                "reconcile_only": result["reconcile_only"],
                "cas_match": result["cas_match"],
            })
            return 0
        if args.command == "status":
            _json_output({"ok": True, "intent": store.read(args.request_id)})
            return 0
        intent = store.confirm(args.request_id, expected_cas=args.expected_cas)
        _json_output({"ok": True, "state": intent["state"], "cas": intent["cas"]})
        return 0
    except (IntentFenceError, OSError, ValueError, json.JSONDecodeError) as error:
        _json_output({"ok": False, "error": str(error)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
