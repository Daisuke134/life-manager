"""One finite, read-mostly .si domain-flip pass with fenced provider writes."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterator


SKILL_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILL_DIR.parents[1]
DEFAULT_STATE_ROOT = Path.home() / ".local/state/life-manager/domain-flip"
AGENT_RUNNER = REPO_ROOT / "runtime/agent-runner/agent_runner.py"
REVIEW_SCHEMA = SKILL_DIR / "candidate-review.schema.json"
_REQUIRED_EVENT_FIELDS = {
    "candidate_id", "run_id", "owner_id", "occurrence_id", "release_sha",
    "loaded_argv", "loaded_env", "phase", "command", "exit_code", "effect",
    "readback", "provider_receipt_id", "evidence_refs", "error_class",
    "retryable", "next_action",
}
_SENSITIVE_KEY_PARTS = (
    "email", "phone", "address", "password", "secret", "token", "api_key",
    "registrant", "person", "credential", "account_name",
)
_EMAIL_VALUE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SECRET_VALUE = re.compile(
    r"(?i)(?:\bbearer\s+[A-Z0-9._~-]{8,}|\b(?:api[-_]?key|access[-_]?token|password|secret|cookie)\s*[:=]\s*\S+|\beyJ[A-Z0-9_-]{12,}\.[A-Z0-9_-]{8,})"
)
_EVIDENCE_SECRET_QUERY = re.compile(r"(?i)[?&](?:api[-_]?key|access[-_]?token|token|password|secret)=")
_ADDRESS_VALUE = re.compile(
    r"(?i)\b\d{1,6}\s+(?:(?:north|south|east|west|n|s|e|w)\.?\s+)?"
    r"(?:[A-Z0-9][A-Z0-9.'-]*\s+){1,4}"
    r"(?:street|st\.?|road|rd\.?|avenue|ave\.?|boulevard|blvd\.?|lane|ln\.?|drive|dr\.?|court|ct\.?|apartment|apt\.?|suite)\b"
)
_JAPANESE_ADDRESS_VALUE = re.compile(
    r"(?:北海道|東京都|(?:京都|大阪)府|[\u4e00-\u9fff]{2,3}県)?"
    r"[\u4e00-\u9fff\u3040-\u30ff々ヶー]{1,30}(?:市|区|町|村)"
    r"[\u4e00-\u9fff\u3040-\u30ff々ヶー]{1,30}"
    r"\d{1,4}(?:丁目|番地?|号|(?:-\d{1,4}){1,2}|条(?:東|西)?\d{0,4}丁目)"
)
_JAPANESE_POSTAL_CODE_VALUE = re.compile(r"(?:(?:〒\s*)|(?:郵便番号\s*:?\s*))?\d{3}-?\d{4}(?!\d)")
_PHONE_VALUE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_ALLOWED_ENV_KEYS = {"LIFE_MANAGER_LOOP_ID", "LIFE_MANAGER_RELEASE_SHA"}
_SAFE_READBACK_KEYS = {
    "provider", "domain", "id", "status", "available", "currency", "listed", "holder_type",
    "readback_verified", "provider_receipt_id", "owner_handle_fingerprint",
    "contact_fingerprint", "mail_verified",
    "activation_date", "expiration_date", "renewal_date", "registration_cost_eur",
    "renewal_cost_eur", "final_charge_eur", "maximum_loss_eur", "min_price_eur",
    "minimum_accepted_price_eur", "registration_amount", "renewal_amount",
    "model_cost_eur", "infra_cost_eur",
    "fx_verified", "fx_basis_receipt_id",
    "price", "category_ids", "total", "evidence_refs", "fx_evidence_refs", "page", "totalPages",
    "totalElements", "complete",
}
_NAME_LEFT = ("neon", "neuro", "holo", "astro", "cyber", "quant", "plasma", "vector", "nexus", "synth")
_NAME_RIGHT = ("orbit", "signal", "forge", "logic", "matrix", "flux", "circuit", "grid", "core", "wave")
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))
import core


def _private_dir(path: Path) -> Path:
    path = Path(path).expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("state_directory_unsafe")
    info = path.stat()
    if info.st_uid != os.getuid():
        raise ValueError("state_directory_unsafe")
    os.chmod(path, 0o700)
    return path


@contextlib.contextmanager
def _owner_lock(state_root: Path) -> Iterator[None]:
    root = _private_dir(state_root)
    path = root / ".owner.lock"
    if path.is_symlink():
        raise ValueError("state_lock_unsafe")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _has_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                return True
            if not _has_sensitive_key(nested):
                continue
            return True
    elif isinstance(value, list):
        return any(_has_sensitive_key(item) for item in value)
    return False


def _has_sensitive_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_EMAIL_VALUE.search(value) or _SECRET_VALUE.search(value)
                    or re.search(r"(?i)https?://[^/\s:@]+:[^/\s@]+@", value))
    if isinstance(value, dict):
        return any(_has_sensitive_value(key) or _has_sensitive_value(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_has_sensitive_value(item) for item in value)
    return False


def _has_private_contact_text(value: Any) -> bool:
    normalized = unicodedata.normalize("NFKC", value)
    return bool(_EMAIL_VALUE.search(normalized) or _PHONE_VALUE.search(normalized)
                or _ADDRESS_VALUE.search(normalized) or _JAPANESE_ADDRESS_VALUE.search(normalized)
                or _JAPANESE_POSTAL_CODE_VALUE.search(normalized))


def _valid_evidence_ref(value: Any) -> bool:
    if not isinstance(value, str) or not 0 < len(value) <= 512:
        return False
    if _has_sensitive_value(value) or _has_private_contact_text(value) or _EVIDENCE_SECRET_QUERY.search(value):
        return False
    return re.match(r"^[a-z][a-z0-9+.-]*://[^\s]+$", value) is not None


def _valid_context(context: Any) -> bool:
    if not isinstance(context, dict):
        return False
    if (context.get("owner_id") != "domain-flip"
            or not isinstance(context.get("run_id"), str)
            or not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", context["run_id"])
            or context.get("occurrence_id") != f"domain-flip:{context['run_id']}"
            or not isinstance(context.get("release_sha"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", context["release_sha"])):
        return False
    argv = context.get("loaded_argv")
    env = context.get("loaded_env")
    if (not isinstance(argv, list) or not all(isinstance(item, str) for item in argv)
            or not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())):
        return False
    if (set(env) - _ALLOWED_ENV_KEYS
            or env.get("LIFE_MANAGER_LOOP_ID", "domain-flip") != "domain-flip"
            or ("LIFE_MANAGER_RELEASE_SHA" in env and env["LIFE_MANAGER_RELEASE_SHA"] != context["release_sha"])):
        return False
    if not argv or Path(argv[0]).name != "run.py":
        return False
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument.startswith("--candidate="):
            if not re.fullmatch(r"--candidate=[a-z0-9-]{1,63}\.si", argument):
                return False
        elif argument == "--candidate":
            index += 1
            if index >= len(argv) or not re.fullmatch(r"[a-z0-9-]{1,63}\.si", argv[index]):
                return False
        elif re.fullmatch(r"--state-root-sha256=[0-9a-f]{64}", argument):
            pass
        else:
            return False
        index += 1
    return True


def _valid_decimal_amount(value: Any) -> bool:
    try:
        amount = Decimal(str(value))
    except Exception:
        return False
    return amount.is_finite() and amount >= 0


def _valid_quote_amounts(quote: Any) -> bool:
    if not isinstance(quote, dict):
        return False
    for field in ("registration_amount", "renewal_amount"):
        if field in quote and not _valid_decimal_amount(quote[field]):
            return False
    allowed_currencies = {"EUR", "USD", "GBP"}
    if "currency" in quote and quote["currency"] not in allowed_currencies:
        return False
    payloads = quote.get("readback_payloads")
    if "readback_payloads" in quote:
        if not isinstance(payloads, dict):
            return False
        for operation in ("create", "renew"):
            row = payloads.get(operation)
            price = row.get("price") if isinstance(row, dict) else None
            if (not isinstance(row, dict)
                    or type(row.get("code")) is not int or row["code"] != 0
                    or any(row.get(flag) is not None and type(row.get(flag)) is not bool
                           for flag in ("is_premium", "is_promotion"))
                    or not isinstance(price, dict)
                    or price.get("currency") not in allowed_currencies
                    or "amount" not in price
                    or not _valid_decimal_amount(price["amount"])):
                return False
    return True


def _valid_readback(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or _has_sensitive_key(value) or _has_sensitive_value(value):
        return False
    if any(key not in _SAFE_READBACK_KEYS for key in value):
        return False
    for key, item in value.items():
        if key == "provider":
            if item not in {"openprovider", "sedo", "euipo", "register-si", "bank", "agent-runner"}:
                return False
        elif key == "status":
            if not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item):
                return False
            if item.casefold() not in {"free", "active", "act", "pre", "registered", "listed",
                                      "not-listed", "not-found", "complete", "submitted", "pending"}:
                return False
        elif key == "domain":
            if not isinstance(item, str) or not re.fullmatch(r"[a-z0-9-]{1,63}\.si", item):
                return False
        elif key == "holder_type":
            if item not in {"natural_person", "legal_entity"}:
                return False
        elif key in {"id", "provider_receipt_id", "fx_basis_receipt_id"}:
            if item is None and key in {"provider_receipt_id", "fx_basis_receipt_id"}:
                continue
            if not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", item):
                return False
        elif key in {"owner_handle_fingerprint", "contact_fingerprint"}:
            if not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item):
                return False
        elif key == "currency":
            if item not in {"EUR", "USD", "GBP"}:
                return False
        elif key in {"available", "listed", "readback_verified", "fx_verified", "complete", "mail_verified"}:
            if type(item) is not bool:
                return False
        elif key in {"activation_date", "expiration_date", "renewal_date"}:
            if not isinstance(item, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item):
                return False
        elif key in {"total", "page", "totalPages", "totalElements"}:
            if type(item) is not int or item < 0:
                return False
        elif key in {"evidence_refs", "fx_evidence_refs"}:
            if not isinstance(item, list) or not all(_valid_evidence_ref(ref) for ref in item):
                return False
        elif key == "category_ids":
            if not isinstance(item, list) or not all(isinstance(value, str) and value.isdigit() for value in item):
                return False
        elif key in {"registration_amount", "renewal_amount", "registration_cost_eur",
                     "renewal_cost_eur", "final_charge_eur",
                     "maximum_loss_eur", "min_price_eur", "minimum_accepted_price_eur",
                     "model_cost_eur", "infra_cost_eur", "price"}:
            if not _valid_decimal_amount(item):
                return False
    return True


def _validate_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict) or not _REQUIRED_EVENT_FIELDS.issubset(event):
        raise ValueError("event_fields_missing")
    if set(event) != _REQUIRED_EVENT_FIELDS:
        raise ValueError("event_fields_unexpected")
    if (not isinstance(event["candidate_id"], str)
            or not re.fullmatch(r"[a-z0-9-]{1,63}\.si", event["candidate_id"])
            or _has_sensitive_value(event)
            or not _valid_context({key: event[key] for key in (
                "run_id", "owner_id", "occurrence_id", "release_sha", "loaded_argv", "loaded_env")})
            or not isinstance(event["phase"], str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", event["phase"])
            or not isinstance(event["command"], str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", event["command"])
            or (event["exit_code"] is not None and type(event["exit_code"]) is not int)
            or event["effect"] not in {"none", "pending", "submitted", "verified", "effect_unknown"}
            or not _valid_readback(event["readback"])
            or (event["provider_receipt_id"] is not None and
                (not isinstance(event["provider_receipt_id"], str)
                 or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", event["provider_receipt_id"])))
            or not isinstance(event["evidence_refs"], list)
            or not all(_valid_evidence_ref(ref) for ref in event["evidence_refs"])
            or (event["error_class"] is not None and
                (not isinstance(event["error_class"], str)
                 or not re.fullmatch(r"[A-Za-z0-9:_-]{1,80}", event["error_class"])) )
            or type(event["retryable"]) is not bool
            or not isinstance(event["next_action"], str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,80}", event["next_action"])):
        raise ValueError("event_invalid_or_contains_private_data")
    return event


def append_event(state_dir: Path, event: dict[str, Any]) -> Path:
    """Validate and fsync one privacy-filtered JSONL occurrence event."""
    _validate_event(event)
    root = _private_dir(Path(state_dir))
    path = root / "events.jsonl"
    if path.is_symlink():
        raise ValueError("event_store_unsafe")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        line = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        view = memoryview(line)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    return path


def read_events(state_root: Path) -> list[dict[str, Any]]:
    root = Path(state_root).expanduser()
    path = root / "events.jsonl"
    if not path.exists():
        return []
    if path.is_symlink():
        raise ValueError("event_store_unsafe")
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("event_store_unsafe")
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError("event_store_corrupt") from None
        records.append(_validate_event(event))
    return records


def _event(
    state_root: Path,
    context: dict[str, Any],
    domain: str,
    *,
    phase: str,
    command: str,
    effect: str,
    readback: dict[str, Any] | None = None,
    provider_receipt_id: str | None = None,
    evidence_refs: list[str] | None = None,
    error_class: str | None = None,
    exit_code: int | None = 0,
    retryable: bool = False,
    next_action: str = "continue_pass",
) -> None:
    append_event(state_root, {
        "candidate_id": domain,
        **context,
        "phase": phase,
        "command": command,
        "exit_code": exit_code,
        "effect": effect,
        "readback": readback,
        "provider_receipt_id": provider_receipt_id,
        "evidence_refs": list(evidence_refs or []),
        "error_class": error_class,
        "retryable": retryable,
        "next_action": next_action,
    })


def _safe_error_class(error: BaseException, fallback: str) -> str:
    value = getattr(error, "code", None)
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9:_-]{1,80}", value) else fallback


def _domain(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9-]{1,63}\.si", value):
        raise ValueError("candidate_domain_invalid")
    label = value[:-3]
    if label.startswith("-") or label.endswith("-"):
        raise ValueError("candidate_domain_invalid")
    return value


def generate_candidate_name(run_id: str) -> str:
    """Rotate era-inspired, generic sci-fi word blends without repeating a fixed list."""
    digest = hashlib.sha256(run_id.encode("utf-8")).digest()
    left = _NAME_LEFT[digest[0] % len(_NAME_LEFT)]
    right = _NAME_RIGHT[digest[1] % len(_NAME_RIGHT)]
    if left == right:
        right = _NAME_RIGHT[(digest[1] + 1) % len(_NAME_RIGHT)]
    return f"{left}{right}.si"


def _history_state(events: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    domain_state: dict[str, str] = {}
    reservations: dict[str, Decimal] = {}
    acquisitions = 0
    invalid_reservation = False
    for event in events:
        domain = event["candidate_id"]
        if event["command"] == "register" and event["phase"] == "registration-dispatch" and event["run_id"] == run_id:
            acquisitions += 1
        if event["command"] == "register" and event["phase"] == "registration-dispatch":
            if event["effect"] in {"pending", "effect_unknown", "submitted", "verified"}:
                readback = event.get("readback") or {}
                amount = readback.get("maximum_loss_eur") if isinstance(readback, dict) else None
                if amount is None:
                    if domain not in reservations:
                        invalid_reservation = True
                else:
                    try:
                        reservation = Decimal(str(amount))
                        if not reservation.is_finite() or reservation < 0:
                            raise ValueError("reservation_invalid")
                        reservations[domain] = reservation
                    except Exception:
                        invalid_reservation = True
            elif event["effect"] == "none":
                reservations.pop(domain, None)
        elif event["phase"] in {"registration-rejected", "registration-reconcile-no-effect"}:
            reservations.pop(domain, None)
        if event["phase"] in {"registration-dispatch", "listing-dispatch", "registration-readback", "listing-readback"} and event["effect"] in {"pending", "effect_unknown"}:
            domain_state[domain] = "unknown"
        elif event["phase"] == "registration-rejected":
            domain_state[domain] = "rejected"
        elif event["phase"] == "registration-reconcile-no-effect":
            domain_state[domain] = "rejected"
        elif event["command"] in {"register", "get_domain", "list_domains", "sedo_insert", "sedo_status"} and event["effect"] in {"submitted", "verified"}:
            domain_state[domain] = "held"
    held = {domain for domain, state in domain_state.items() if state in {"unknown", "held"}}
    unknown = {domain for domain, state in domain_state.items() if state == "unknown"}
    committed_loss = None if invalid_reservation else sum(reservations.values(), Decimal("0.00"))
    return {
        "active_holdings": len(held),
        "active_domains": sorted(held),
        "acquisitions_this_pass": acquisitions,
        "effect_unknown_domains": sorted(unknown),
        "committed_loss_eur": None if committed_loss is None else format(committed_loss, "f"),
    }


def _private_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError("private_input_unsafe")
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("private_input_unsafe")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("private_input_invalid") from None


def _private_runner_json(path: Path, evidence_root: Path) -> Any | None:
    path = Path(path)
    root = _private_dir(Path(evidence_root))
    if path.is_symlink() or not path.is_file():
        raise ValueError("runner_result_unsafe")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError("runner_result_unowned") from None
    info = path.stat()
    if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
        raise ValueError("runner_result_unsafe")
    os.chmod(path, 0o600)
    return _private_json(path)


def _write_private_json(path: Path, value: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        payload = (json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":")) + "\n").encode()
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(fd)
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    os.replace(temp, path)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _safe_quote(quote: dict[str, Any]) -> dict[str, Any]:
    if not _valid_quote_amounts(quote):
        raise ValueError("provider_quote_amount_invalid")
    fields = {
        "domain", "provider", "available", "currency", "registration_cost_eur",
        "renewal_cost_eur", "registration_amount", "renewal_amount", "final_charge_eur",
        "readback_verified", "provider_receipt_id",
        "evidence_refs", "fx_verified", "fx_basis_receipt_id", "fx_evidence_refs",
    }
    return {key: _json_ready(value) for key, value in quote.items() if key in fields}


def _save_provider_readback(evidence_dir: Path, domain: str, kind: str, value: dict[str, Any]) -> str:
    safe: dict[str, Any] = {"domain": domain, "provider": "openprovider", "readback_verified": True}
    if kind == "availability":
        payload = value.get("readback_payload")
        if isinstance(payload, dict):
            result = payload.get("result")
            safe_result = {}
            if isinstance(result, dict):
                if result.get("domain") == domain:
                    safe_result["domain"] = domain
                if result.get("status") in {"free", "active"}:
                    safe_result["status"] = result["status"]
                for key in ("is_premium", "is_promotion"):
                    if type(result.get(key)) is bool:
                        safe_result[key] = result[key]
            safe["readback_payload"] = {
                "result": safe_result,
            }
        if type(value.get("available")) is bool:
            safe["available"] = value["available"]
        if value.get("status") in {"free", "active"}:
            safe["status"] = value["status"]
        filename = "openprovider-availability.json"
    elif kind == "quote":
        if not _valid_quote_amounts(value):
            raise ValueError("provider_readback_amount_invalid")
        payloads = value.get("readback_payloads")
        safe_payloads = {}
        if isinstance(payloads, dict):
            for operation in ("create", "renew"):
                row = payloads.get(operation)
                if isinstance(row, dict):
                    price = row.get("price")
                    safe_payloads[operation] = {"code": row["code"]}
                    for key in ("is_premium", "is_promotion"):
                        if type(row.get(key)) is bool:
                            safe_payloads[operation][key] = row[key]
                    if isinstance(price, dict):
                        safe_payloads[operation]["price"] = {
                            key: price[key] for key in ("currency", "amount") if key in price
                        }
        safe["readback_payloads"] = safe_payloads
        safe.update({key: _json_ready(value[key]) for key in (
            "currency", "registration_amount", "renewal_amount", "registration_cost_eur",
            "renewal_cost_eur", "final_charge_eur", "fx_verified", "fx_basis_receipt_id",
        ) if key in value})
        filename = "openprovider-price-readbacks.json"
    else:
        raise ValueError("provider_readback_kind_invalid")
    if _has_sensitive_key(safe) or _has_sensitive_value(safe):
        raise ValueError("provider_readback_private_data")
    _write_private_json(evidence_dir / filename, safe)
    return f"domain-flip://evidence/{evidence_dir.parent.name}/{domain[:-3]}/{filename}"


def _safe_rights(rights: dict[str, Any]) -> dict[str, Any]:
    records = rights.get("records")
    if not isinstance(records, list):
        return {}
    safe_records = []
    for row in records:
        if not isinstance(row, dict):
            return {}
        allowed = {"word_mark", "office", "status", "classes", "official_record_url"}
        if set(row) - allowed:
            return {}
        if (not isinstance(row.get("word_mark"), str) or not row["word_mark"].strip()
                or not isinstance(row.get("office"), str)
                or not isinstance(row.get("status"), str)
                or not isinstance(row.get("classes"), list)
                or not all(isinstance(item, str) and item.isdigit() for item in row["classes"])
                or not _valid_evidence_ref(row.get("official_record_url"))
                or _has_sensitive_value(row) or _has_private_contact_text(row["word_mark"])):
            return {}
        safe_records.append({key: row[key] for key in allowed if key in row})
    refs = rights.get("evidence_refs")
    if not isinstance(refs, list) or not refs or not all(_valid_evidence_ref(ref) for ref in refs):
        return {}
    if (rights.get("status") != "complete" or rights.get("source") != "euipo"
            or type(rights.get("total_elements")) is not int
            or rights["total_elements"] != len(safe_records)):
        return {}
    return {
        "status": rights.get("status"),
        "source": rights.get("source"),
        "total_elements": rights.get("total_elements"),
        "records": safe_records,
        "evidence_refs": refs,
    }


def _safe_market(market: dict[str, Any]) -> dict[str, Any]:
    fields = {"status", "evidence_refs", "observations"}
    result = {key: market[key] for key in fields if key in market}
    refs = result.get("evidence_refs")
    if (result.get("status") != "reported" or not isinstance(refs, list)
            or not refs or not all(_valid_evidence_ref(ref) for ref in refs)):
        return {"status": "unavailable", "evidence_refs": []}
    observations = result.get("observations")
    if isinstance(observations, list):
        safe_observations = []
        for row in observations[:20]:
            if not isinstance(row, dict) or _has_sensitive_key(row) or _has_sensitive_value(row):
                continue
            clean = {key: row[key] for key in ("domain", "price_eur", "currency", "sale_date", "source_ref") if key in row}
            if (not isinstance(clean.get("domain"), str)
                    or not re.fullmatch(r"[a-z0-9-]{1,63}\.[a-z0-9-]{2,20}", clean["domain"])
                    or not isinstance(clean.get("source_ref"), str)
                    or not _valid_evidence_ref(clean["source_ref"])):
                continue
            try:
                price = Decimal(str(clean.get("price_eur")))
            except Exception:
                continue
            if not price.is_finite() or price <= 0 or clean.get("currency") != "EUR":
                continue
            clean["price_eur"] = str(price)
            safe_observations.append(clean)
        result["observations"] = safe_observations
    return _json_ready(result)


def _safe_fees(fees: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "sedo_fee_rate", "tax_eur", "payout_fee_eur", "fx_fee_eur",
        "measured_model_cost_eur", "measured_infra_cost_eur", "evidence_refs",
        "readback_verified", "readback_at", "direct_marketplace_fee_rate",
        "sedomls_fee_rate", "domain_category", "source_sha256", "minimum_sale_price_eur",
        "cost_readback_verified", "cost_readback_at", "cost_evidence_refs",
    }
    if (fees.get("readback_verified") is not True
            or not isinstance(fees.get("evidence_refs"), list)
            or not fees["evidence_refs"]
            or not all(_valid_evidence_ref(ref) for ref in fees["evidence_refs"])
            or fees.get("cost_readback_verified") is not True
            or not isinstance(fees.get("cost_evidence_refs"), list)
            or not fees["cost_evidence_refs"]
            or not all(_valid_evidence_ref(ref) for ref in fees["cost_evidence_refs"])):
        return {"readback_verified": False, "evidence_refs": []}
    result = {key: fees[key] for key in fields if key in fees}
    for key in ("sedo_fee_rate", "direct_marketplace_fee_rate", "sedomls_fee_rate",
                "minimum_sale_price_eur",
                "tax_eur", "payout_fee_eur", "fx_fee_eur",
                "measured_model_cost_eur", "measured_infra_cost_eur"):
        try:
            amount = Decimal(str(result[key]))
        except Exception:
            return {"readback_verified": False, "evidence_refs": []}
        if not amount.is_finite() or amount < 0:
            return {"readback_verified": False, "evidence_refs": []}
        result[key] = str(amount)
    if (Decimal(result["sedo_fee_rate"]) > 1
            or result.get("domain_category") != "I"
            or not isinstance(result.get("source_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", result["source_sha256"])):
        return {"readback_verified": False, "evidence_refs": []}
    return _json_ready(result)


def _listing_terms_match(domain: str, expected_price: Any, expected_min: Any,
                         status_readback: Any, domain_rows: Any) -> tuple[bool, dict[str, Any]]:
    if (not isinstance(status_readback, dict) or status_readback.get("domain") != domain
            or status_readback.get("provider") != "sedo"
            or status_readback.get("listed") is not True
            or status_readback.get("readback_verified") is not True
            or not isinstance(domain_rows, list) or len(domain_rows) != 1
            or not isinstance(domain_rows[0], dict)):
        return False, {}
    row = domain_rows[0]
    if (row.get("domain") != domain or row.get("provider") != "sedo"
            or row.get("listed") is not True or row.get("readback_verified") is not True
            or row.get("fixed_price") is not False or row.get("currency") != "EUR"
            or status_readback.get("currency") != "EUR"):
        return False, {}
    try:
        price = Decimal(str(row["price"]))
        minimum = Decimal(str(row["min_price"]))
        status_price = Decimal(str(status_readback["price"]))
        expected = Decimal(str(expected_price))
        expected_minimum = Decimal(str(expected_min))
    except Exception:
        return False, {}
    if (not all(value.is_finite() for value in (price, minimum, status_price, expected, expected_minimum))
            or price != expected or minimum != expected_minimum or status_price != price):
        return False, {}
    safe = {
        "domain": domain,
        "listed": True,
        "status": "listed",
        "price": format(price, "f"),
        "min_price_eur": format(minimum, "f"),
        "currency": "EUR",
        "provider": "sedo",
        "provider_receipt_id": status_readback.get("provider_receipt_id"),
        "readback_verified": True,
    }
    return True, safe


def _validate_review(review: Any, domain: str, allowed_refs: set[str]) -> dict[str, Any] | None:
    if not isinstance(review, dict):
        return None
    required = {
        "action", "selected_domain", "listing_price_eur", "minimum_accepted_price_eur",
        "rights_risk", "reason", "evidence_refs",
    }
    if set(review) != required or _has_sensitive_key(review) or _has_sensitive_value(review):
        return None
    if (not isinstance(review["action"], str) or review["action"] not in {"register", "skip"}
            or review["selected_domain"] != domain
            or not isinstance(review["rights_risk"], str)
            or review["rights_risk"] not in {"clear", "possible_conflict", "unverified"}
            or not isinstance(review["reason"], str) or not review["reason"].strip()
            or len(review["reason"]) > 500
            or _has_private_contact_text(review["reason"])
            or not isinstance(review["evidence_refs"], list)
            or not review["evidence_refs"]
            or not all(isinstance(ref, str) for ref in review["evidence_refs"])
            or len(review["evidence_refs"]) != len(set(review["evidence_refs"]))
            or not all(_valid_evidence_ref(ref) and len(ref) <= 512 for ref in review["evidence_refs"])
            or not all(isinstance(ref, str) and ref in allowed_refs for ref in review["evidence_refs"])):
        return None
    for field in ("listing_price_eur", "minimum_accepted_price_eur"):
        if (not isinstance(review[field], str)
                or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", review[field])):
            return None
        try:
            amount = Decimal(review[field])
        except Exception:
            return None
        if not amount.is_finite() or amount <= 0:
            return None
    if Decimal(review["listing_price_eur"]) < Decimal(review["minimum_accepted_price_eur"]):
        return None
    return review


def _run_agent_review(packet: dict[str, Any], evidence_dir: Path) -> dict[str, Any]:
    prompt = {
        "instruction": (
            "Review this original sci-fi-era .si domain candidate for a conservative resale listing. "
            "Use only the supplied evidence refs. Return exactly the required JSON schema. "
            "Choose skip when evidence is incomplete or rights risk is not clear. "
            "This read-only reviewer cannot authorize registration or override deterministic policy."
        ),
        "candidate_packet": packet,
    }
    with tempfile.TemporaryDirectory(prefix=".candidate-review-", dir=evidence_dir) as scratch:
        runner_dir = Path(scratch)
        completed = subprocess.run(
            [
                sys.executable, str(AGENT_RUNNER), "--task-class", "diagnostic-agent",
                "--prompt-stdin", "--schema", str(REVIEW_SCHEMA),
                "--evidence-dir", str(runner_dir), "--task-label", "domain-flip-candidate-review",
                "--loop", "domain-flip", "--workdir", str(REPO_ROOT),
                "--timeout-seconds", "300", "--read-only",
            ],
            input=json.dumps(prompt, sort_keys=True, separators=(",", ":")),
            capture_output=True,
            text=True,
            timeout=330,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("reviewer_failed")
        summary_path = runner_dir / "summary.json"
        if not summary_path.is_file() or summary_path.is_symlink():
            raise RuntimeError("reviewer_result_missing")
        summary = _private_json(summary_path)
        result_path = Path(str(summary.get("result_path") or "")).resolve()
        try:
            result_path.relative_to(runner_dir.resolve())
        except ValueError:
            raise RuntimeError("reviewer_result_unowned") from None
        review = _private_runner_json(result_path, runner_dir)
        if not isinstance(review, dict):
            raise RuntimeError("reviewer_result_invalid")
        return review


def _preflight_credentials(client: Any) -> str | None:
    if client is None:
        return "provider_credentials_missing"
    loader = getattr(client, "_load_credentials", None)
    if not callable(loader):
        return None
    try:
        loader()
    except Exception as error:
        return str(getattr(error, "code", "provider_preflight_failed"))
    return None


def _append_simple(state_root: Path, context: dict[str, Any], domain: str, *, reason: str,
                   next_action: str, refs: list[str] | None = None,
                   status: str = "scout_only") -> dict[str, Any]:
    _event(state_root, context, domain, phase="scout", command="run_once", effect="none",
           evidence_refs=refs, error_class=reason, next_action=next_action)
    return {"status": status, "domain": domain, "reason_codes": [reason]}


def _valid_business_funding(funding: Any) -> bool:
    if (not isinstance(funding, dict)
            or funding.get("source_type") != "business_dedicated"
            or funding.get("source_owner_id") != "domain-flip"
            or funding.get("source_verified") is not True
            or funding.get("currency") != "EUR"
            or funding.get("automatic_refill_enabled") is not False
            or funding.get("balance_readback_verified") is not True
            or not isinstance(funding.get("balance_provider_receipt_id"), str)
            or not funding.get("balance_provider_receipt_id")
            or not isinstance(funding.get("funding_receipt_id"), str)
            or not funding.get("funding_receipt_id")
            or type(funding.get("top_up_count")) is not int
            or funding["top_up_count"] < 0 or funding["top_up_count"] > 1):
        return False
    try:
        cap = Decimal(str(funding["lifetime_cap_eur"]))
        funded = Decimal(str(funding["owner_funded_total_eur"]))
        remaining = Decimal(str(funding["remaining_eur"]))
        timestamp = datetime.fromisoformat(str(funding["balance_readback_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError, ArithmeticError):
        return False
    now = datetime.now(timezone.utc)
    if (timestamp.tzinfo is None or not all(value.is_finite() for value in (cap, funded, remaining))
            or min(cap, funded, remaining) < 0 or cap > core.INITIAL_CAP_EUR
            or funded > cap or remaining > funded):
        return False
    age = now - timestamp.astimezone(timezone.utc)
    return timedelta(minutes=-5) <= age <= timedelta(hours=24)


def _valid_fee_evidence(fees: Any) -> bool:
    if (not isinstance(fees, dict) or fees.get("readback_verified") is not True
            or not isinstance(fees.get("evidence_refs"), list)
            or not any(ref.startswith("https://sedo.com/") for ref in fees["evidence_refs"]
                       if isinstance(ref, str))
            or fees.get("cost_readback_verified") is not True
            or not isinstance(fees.get("cost_evidence_refs"), list)
            or not fees["cost_evidence_refs"]
            or not all(_valid_evidence_ref(ref) for ref in fees["cost_evidence_refs"])):
        return False
    try:
        timestamp = datetime.fromisoformat(str(fees["readback_at"]).replace("Z", "+00:00"))
        cost_timestamp = datetime.fromisoformat(str(fees["cost_readback_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError):
        return False
    if timestamp.tzinfo is None or cost_timestamp.tzinfo is None:
        return False
    now = datetime.now(timezone.utc)
    age = now - timestamp.astimezone(timezone.utc)
    cost_age = now - cost_timestamp.astimezone(timezone.utc)
    return (timedelta(minutes=-5) <= age <= timedelta(hours=24)
            and timedelta(minutes=-5) <= cost_age <= timedelta(hours=24))


def _readback(value: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    return _json_ready({key: value[key] for key in fields if key in value})


def _valid_whois_publication_scope(registrant: dict[str, Any]) -> bool:
    refs = registrant.get("whois_policy_evidence_refs")
    official_ref = "https://www.register.si/splosni-pogoji/#pravila_whois"
    return (
        registrant.get("holder_type") == "natural_person"
        and registrant.get("whois_public_fields") == ["email"]
        and registrant.get("whois_optional_fields_opted_in") == []
        and registrant.get("whois_policy_verified") is True
        and isinstance(refs, list)
        and official_ref in refs
        and all(_valid_evidence_ref(ref) for ref in refs)
    )


def _registrant_contact_matches(registrant: dict[str, Any], readback: Any) -> bool:
    return (
        isinstance(readback, dict)
        and readback.get("provider") == "openprovider"
        and readback.get("readback_verified") is True
        and readback.get("email_verified") is True
        and readback.get("holder_type") == registrant.get("holder_type")
        and readback.get("owner_handle_fingerprint") == registrant.get("owner_handle_fingerprint")
        and readback.get("contact_fingerprint") == registrant.get("contact_fingerprint")
        and readback.get("email_fingerprint") == registrant.get("whois_email_fingerprint")
        and all(
            isinstance(registrant.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", registrant[key])
            for key in ("owner_handle_fingerprint", "contact_fingerprint", "whois_email_fingerprint")
        )
    )


def _run_once(
    *,
    state_root: Path,
    context: dict[str, Any],
    funding: dict[str, Any] | None,
    registrant: dict[str, Any] | None,
    registrar: Any,
    sedo: Any,
    rights_searcher: Any,
    candidate_names: list[str] | None,
    market_evidence: dict[str, Any] | None,
    fee_evidence: dict[str, Any] | None,
    reviewer: Callable[..., dict[str, Any]] | None,
) -> dict[str, Any]:
    if not _valid_context(context):
        raise ValueError("occurrence_context_invalid")
    root = _private_dir(Path(state_root))
    names = candidate_names or [generate_candidate_name(context["run_id"])]
    if not isinstance(names, list) or not names or len(names) != 1:
        raise ValueError("candidate_batch_invalid")
    names = list(dict.fromkeys(_domain(name) for name in names))
    history = read_events(root)
    portfolio = _history_state(history, context["run_id"])
    if portfolio["committed_loss_eur"] is None:
        return _append_simple(root, context, names[0], reason="cap_reservation_evidence_missing",
                              next_action="reconcile_registration_state")
    existing_unknown = set(portfolio["effect_unknown_domains"])
    for domain in names:
        if domain in existing_unknown:
            return _append_simple(root, context, domain, reason="effect_unknown",
                                  next_action="official_readback", status="effect_unknown")
        if domain in portfolio["active_domains"]:
            return _append_simple(root, context, domain, reason="domain_already_held",
                                  next_action="manage_existing_holding")

    missing = _preflight_credentials(registrar) or _preflight_credentials(sedo)
    if missing:
        return _append_simple(root, context, names[0], reason=missing,
                              next_action="configure_provider_credentials")
    if rights_searcher is None:
        return _append_simple(root, context, names[0], reason="rights_evidence_missing",
                              next_action="authorized_euipo_subscription")

    # Candidate names are local blends; the rights service receives only the public label.
    # Each pass reviews at most one name and can register at most one domain.
    for domain in names:
        label = domain[:-3]
        _private_dir(root / "evidence")
        _private_dir(root / "evidence" / context["run_id"])
        evidence_dir = root / "evidence" / context["run_id"] / label
        _private_dir(evidence_dir)
        try:
            rights = rights_searcher.search_wordmark(label)
        except Exception:
            return _append_simple(root, context, domain, reason="rights_evidence_missing",
                                  next_action="inspect_rights_search")
        rights = _safe_rights(rights) if isinstance(rights, dict) else {}
        if (rights.get("status") != "complete" or rights.get("source") != "euipo"
                or not rights.get("evidence_refs")):
            return _append_simple(root, context, domain, reason="rights_evidence_missing",
                                  next_action="authorized_euipo_subscription")
        _write_private_json(evidence_dir / "rights.json", rights)
        records = rights.get("records")
        total = rights.get("total_elements")
        if not isinstance(records, list) or type(total) is not int or total != len(records):
            return _append_simple(root, context, domain, reason="rights_evidence_missing",
                                  next_action="complete_official_readback")
        if records or total != 0:
            return _append_simple(root, context, domain, reason="rights_review_required",
                                  next_action="skip_candidate",
                                  refs=rights.get("evidence_refs", []))
        _event(root, context, domain, phase="rights-readback", command="euipo_search",
               effect="verified", readback={"provider": "euipo", "status": "complete",
               "totalElements": total, "complete": True},
               evidence_refs=rights["evidence_refs"], next_action="registrar_readback")
        try:
            availability = registrar.check_domain(domain)
            quote = registrar.quote_create(domain, funding_fx_basis=(funding or {}).get("fx_basis"))
            if isinstance(quote, dict):
                _safe_quote(quote)
            if isinstance(availability, dict):
                availability = dict(availability)
                local_ref = _save_provider_readback(evidence_dir, domain, "availability", availability)
                refs = availability.get("evidence_refs", [])
                availability["evidence_refs"] = [*refs, local_ref] if isinstance(refs, list) else [local_ref]
            if isinstance(quote, dict):
                quote = dict(quote)
                local_ref = _save_provider_readback(evidence_dir, domain, "quote", quote)
                refs = quote.get("evidence_refs", [])
                quote["evidence_refs"] = [*refs, local_ref] if isinstance(refs, list) else [local_ref]
                if quote.get("available") is None:
                    quote["available"] = availability.get("available") if isinstance(availability, dict) else None
                elif isinstance(availability, dict) and quote["available"] != availability.get("available"):
                    return _append_simple(root, context, domain, reason="registrar_readback_conflict",
                                          next_action="official_registrar_readback")
        except Exception as error:
            return _append_simple(root, context, domain, reason="registrar_read_failed",
                                  next_action="inspect_registrar_readback")
        if (not isinstance(availability, dict) or availability.get("readback_verified") is not True
                or availability.get("available") is not True
                or not isinstance(availability.get("evidence_refs"), list)
                or not availability["evidence_refs"]
                or not all(_valid_evidence_ref(ref) for ref in availability["evidence_refs"])):
            return _append_simple(root, context, domain, reason="registrar_availability_unverified",
                                  next_action="registrar_readback",
                                  refs=availability.get("evidence_refs", []) if isinstance(availability, dict) else None)
        if (not isinstance(quote, dict) or quote.get("readback_verified") is not True
                or quote.get("available") is not True or quote.get("domain") != domain
                or not isinstance(quote.get("evidence_refs"), list) or not quote["evidence_refs"]
                or not all(_valid_evidence_ref(ref) for ref in quote["evidence_refs"])):
            return _append_simple(root, context, domain, reason="registrar_quote_unverified",
                                  next_action="fresh_price_readback",
                                  refs=quote.get("evidence_refs", []) if isinstance(quote, dict) else None)

        availability_safe = _readback(availability, {
            "provider", "domain", "available", "readback_verified", "provider_receipt_id", "evidence_refs",
        })
        quote_safe = _safe_quote(quote)
        _event(root, context, domain, phase="availability-readback", command="check_domain",
               effect="verified", readback=availability_safe,
               provider_receipt_id=availability_safe.get("provider_receipt_id"),
               evidence_refs=availability.get("evidence_refs", []), next_action="quote_readback")
        _event(root, context, domain, phase="quote-readback", command="quote_create",
               effect="verified", readback=quote_safe,
               provider_receipt_id=quote_safe.get("provider_receipt_id"),
               evidence_refs=quote.get("evidence_refs", []), next_action="purchase_policy")

        rights_refs = rights.get("evidence_refs", [])
        availability_refs = availability.get("evidence_refs", [])
        quote_refs = quote.get("evidence_refs", [])
        market = market_evidence if isinstance(market_evidence, dict) else {}
        fees = fee_evidence if isinstance(fee_evidence, dict) else {}
        market_safe = _safe_market(market)
        fees_safe = _safe_fees(fees)
        market_refs = market_safe.get("evidence_refs", [])
        fee_refs = fees_safe.get("evidence_refs", [])
        fee_cost_refs = fees_safe.get("cost_evidence_refs", [])
        allowed_refs = {
            ref for refs in (rights_refs, availability_refs, quote_refs, market_refs, fee_refs, fee_cost_refs)
            if isinstance(refs, list) for ref in refs if _valid_evidence_ref(ref)
        }
        if not _valid_business_funding(funding):
            return _append_simple(root, context, domain, reason="business_funding_unverified",
                                  next_action="verified_business_balance",
                                  refs=sorted(allowed_refs))
        if (not isinstance(registrant, dict) or registrant.get("legal_holder_verified") is not True
                or registrant.get("whois_email_functional") is not True
                or registrant.get("whois_email_receiving_verified") is not True
                or not isinstance(registrant.get("owner_handle"), str)
                or not isinstance(registrant.get("owner_handle_fingerprint"), str)
                or not isinstance(registrant.get("contact_fingerprint"), str)
                or not isinstance(registrant.get("whois_email_fingerprint"), str)):
            return _append_simple(root, context, domain, reason="registrant_unverified",
                                  next_action="verified_private_registrant")
        if not _valid_whois_publication_scope(registrant):
            return _append_simple(root, context, domain, reason="whois_publication_unverified",
                                  next_action="approved_whois_scope")
        if (market_safe.get("status") != "reported"
                or not isinstance(market_refs, list) or not market_refs
                or not _valid_fee_evidence(fees_safe)):
            return _append_simple(root, context, domain, reason="market_or_fee_evidence_missing",
                                  next_action="complete_market_and_fee_evidence",
                                  refs=sorted(allowed_refs))

        rights_for_policy = {
            "status": "clear", "sources": ["euipo"], "evidence_refs": rights_refs,
        }
        packet = {
            "candidate": {"domain": domain, "style": "original 1970s–1990s science-fiction futurism"},
            "rights": rights,
            "registrar_availability": availability_safe,
            "registrar_quote": quote_safe,
            "market_evidence": market_safe,
            "sale_fee_evidence": fees_safe,
        }
        _write_private_json(evidence_dir / "fee-readback.json", fees_safe)
        try:
            review_raw = reviewer(packet) if reviewer is not None else _run_agent_review(packet, evidence_dir)
        except Exception as error:
            code = str(getattr(error, "code", "reviewer_failed"))
            return _append_simple(root, context, domain, reason="reviewer_failed",
                                  next_action="inspect_reviewer_result", refs=sorted(allowed_refs))
        review = _validate_review(review_raw, domain, allowed_refs)
        if review is None:
            return _append_simple(root, context, domain, reason="review_invalid",
                                  next_action="review_again_read_only", refs=sorted(allowed_refs))
        _write_private_json(evidence_dir / "candidate-packet.json", packet)
        _write_private_json(evidence_dir / "review.json", review)
        if review["action"] != "register":
            return _append_simple(root, context, domain, reason="model_skipped_candidate",
                                  next_action="next_daily_candidate", refs=review["evidence_refs"])
        if review["rights_risk"] != "clear":
            return _append_simple(root, context, domain, reason="rights_review_required",
                                  next_action="skip_candidate", refs=review["evidence_refs"])

        try:
            registrant_readback = registrar.get_customer(registrant["owner_handle"])
        except Exception:
            return _append_simple(root, context, domain, reason="registrant_contact_readback_missing",
                                  next_action="official_contact_readback", refs=sorted(allowed_refs))
        if not _registrant_contact_matches(registrant, registrant_readback):
            return _append_simple(root, context, domain, reason="registrant_contact_readback_mismatch",
                                  next_action="review_current_registrant", refs=sorted(allowed_refs))
        contact_event_readback = {
            "provider": "openprovider",
            "readback_verified": True,
            "holder_type": registrant_readback["holder_type"],
            "owner_handle_fingerprint": registrant_readback["owner_handle_fingerprint"],
            "contact_fingerprint": registrant_readback["contact_fingerprint"],
            "mail_verified": True,
        }
        contact_filename = "openprovider-contact-readback.json"
        _write_private_json(evidence_dir / contact_filename, contact_event_readback)
        contact_ref = f"domain-flip://evidence/{context['run_id']}/{label}/{contact_filename}"
        allowed_refs.add(contact_ref)
        _event(root, context, domain, phase="registrant-readback", command="get_customer",
               effect="verified", readback=contact_event_readback, evidence_refs=[contact_ref],
               next_action="purchase_policy")

        candidate = {
            "domain": domain,
            "minimum_accepted_price_eur": review["minimum_accepted_price_eur"],
        }
        evidence = {
            "registrant": registrant,
            "registrant_readback": registrant_readback,
            "rights": rights_for_policy,
            "market": market_safe,
            "fees": fees_safe,
        }
        decision = core.evaluate_purchase(candidate, quote, funding, portfolio, evidence)
        if not decision["eligible"]:
            reason_codes = list(decision["reason_codes"])
            _event(root, context, domain, phase="purchase-policy", command="evaluate_purchase",
                   effect="none", evidence_refs=sorted(allowed_refs),
                   error_class=reason_codes[0] if reason_codes else "purchase_ineligible",
                   next_action="scout_next_pass")
            return {"status": "no_purchase", "domain": domain,
                    "reason_codes": reason_codes, "policy": _json_ready(decision)}

        # Persist a fence before the provider call. A crash after dispatch cannot trigger a blind replay.
        _event(root, context, domain, phase="registration-dispatch", command="register",
               effect="pending", readback={
                   "owner_handle_fingerprint": registrant["owner_handle_fingerprint"],
                   "contact_fingerprint": registrant["contact_fingerprint"],
                   "registration_cost_eur": str(quote["registration_cost_eur"]),
                   "renewal_cost_eur": str(quote["renewal_cost_eur"]),
                   "model_cost_eur": str(fees["measured_model_cost_eur"]),
                   "infra_cost_eur": str(fees["measured_infra_cost_eur"]),
                   "maximum_loss_eur": str(decision["maximum_loss_eur"]),
               },
               evidence_refs=sorted(allowed_refs), exit_code=None,
               next_action="official_readback")
        idempotency_key = hashlib.sha256(
            f"domain-flip:{context['occurrence_id']}:{domain}".encode("utf-8")
        ).hexdigest()
        try:
            registration = registrar.register(domain, registrant["owner_handle"], idempotency_key)
        except Exception as error:
            code = _safe_error_class(error, "registration_response_unknown")
            _event(root, context, domain, phase="registration-dispatch", command="register",
                   effect="effect_unknown", evidence_refs=sorted(allowed_refs), error_class=code,
                   exit_code=None, next_action="official_readback")
            return {"status": "effect_unknown", "domain": domain, "reason_codes": ["effect_unknown"]}
        if not isinstance(registration, dict) or not registration.get("domain_id"):
            _event(root, context, domain, phase="registration-dispatch", command="register",
                   effect="effect_unknown", evidence_refs=sorted(allowed_refs),
                   error_class="registration_receipt_missing", exit_code=None,
                   next_action="official_readback")
            return {"status": "effect_unknown", "domain": domain, "reason_codes": ["effect_unknown"]}
        domain_id = str(registration["domain_id"])
        receipt_id = registration.get("provider_receipt_id")
        if (not domain_id.isdigit() or registration.get("provider") != "openprovider"
                or registration.get("domain") != domain or receipt_id != domain_id):
            _event(root, context, domain, phase="registration-dispatch", command="register",
                   effect="effect_unknown",
                   provider_receipt_id=receipt_id if isinstance(receipt_id, str) else None,
                   evidence_refs=sorted(allowed_refs), error_class="registration_receipt_mismatch",
                   exit_code=None, next_action="official_readback")
            return {"status": "effect_unknown", "domain": domain,
                    "reason_codes": ["registration_receipt_mismatch"]}
        _event(root, context, domain, phase="registration-submitted", command="register",
               effect="submitted", provider_receipt_id=receipt_id if isinstance(receipt_id, str) else None,
               evidence_refs=sorted(allowed_refs), next_action="official_readback")
        try:
            owner_readback = registrar.get_domain(domain_id)
        except Exception as error:
            _event(root, context, domain, phase="registration-readback", command="get_domain",
                   effect="effect_unknown", provider_receipt_id=receipt_id if isinstance(receipt_id, str) else None,
                   evidence_refs=sorted(allowed_refs), error_class=str(getattr(error, "code", "provider_read_failed")),
                   exit_code=None, next_action="official_readback")
            return {"status": "effect_unknown", "domain": domain, "reason_codes": ["registration_readback_missing"]}
        owner_safe = _readback(owner_readback, {
            "id", "domain", "status", "provider", "provider_receipt_id",
            "readback_verified", "owner_handle_fingerprint", "activation_date", "expiration_date", "renewal_date",
        }) if isinstance(owner_readback, dict) else {}
        active_status = str(owner_safe.get("status", "")).casefold() in {"act", "active", "registered"}
        resource_matches = (
            owner_safe.get("provider") == "openprovider"
            and owner_safe.get("id") == domain_id
            and owner_safe.get("provider_receipt_id") == domain_id
        )
        owner_matches = owner_safe.get("owner_handle_fingerprint") == registrant["owner_handle_fingerprint"]
        if (owner_safe.get("domain") != domain or owner_safe.get("readback_verified") is not True
                or not resource_matches or not active_status or not owner_matches):
            _event(root, context, domain, phase="registration-readback", command="get_domain",
                   effect="effect_unknown",
                   readback=owner_safe or None,
                   provider_receipt_id=owner_safe.get("provider_receipt_id") if isinstance(owner_safe.get("provider_receipt_id"), str) else None,
                   evidence_refs=sorted(allowed_refs),
                   error_class="registration_readback_mismatch",
                   exit_code=None,
                   next_action="registration_owner_readback")
            return {"status": "registration_pending", "domain": domain,
                    "reason_codes": ["registered_owner_readback_required"]}
        _event(root, context, domain, phase="registration-readback", command="get_domain",
               effect="verified", readback=owner_safe,
               provider_receipt_id=owner_safe.get("provider_receipt_id") if isinstance(owner_safe.get("provider_receipt_id"), str) else None,
               evidence_refs=sorted(allowed_refs), next_action="sedo_listing")

        _event(root, context, domain, phase="listing-dispatch", command="sedo_insert",
               effect="pending", readback={
                   "domain": domain,
                   "price": review["listing_price_eur"],
                   "minimum_accepted_price_eur": review["minimum_accepted_price_eur"],
                   "currency": "EUR",
               }, evidence_refs=sorted(allowed_refs), exit_code=None,
               next_action="official_sedo_readback")
        try:
            listing_submit = sedo.insert_for_sale(
                domain,
                Decimal(review["listing_price_eur"]),
                Decimal(review["minimum_accepted_price_eur"]),
            )
        except Exception as error:
            code = str(getattr(error, "code", "effect_unknown"))
            _event(root, context, domain, phase="listing-dispatch", command="sedo_insert",
                   effect="effect_unknown", evidence_refs=sorted(allowed_refs), error_class=code,
                   exit_code=None, next_action="official_sedo_readback")
            return {"status": "effect_unknown", "domain": domain,
                    "reason_codes": ["listing_effect_unknown"]}
        listing_receipt = listing_submit.get("provider_receipt_id") if isinstance(listing_submit, dict) else None
        _event(root, context, domain, phase="listing-submitted", command="sedo_insert",
               effect="submitted", provider_receipt_id=listing_receipt if isinstance(listing_receipt, str) else None,
               evidence_refs=sorted(allowed_refs), next_action="official_sedo_readback")
        try:
            listing_readback = sedo.domain_status(domain)
            listing_rows = sedo.domain_list([domain])
        except Exception as error:
            code = _safe_error_class(error, "provider_read_failed")
            _event(root, context, domain, phase="listing-readback", command="sedo_status",
                   effect="effect_unknown", provider_receipt_id=listing_receipt if isinstance(listing_receipt, str) else None,
                   evidence_refs=sorted(allowed_refs), error_class=code,
                   exit_code=None, next_action="official_sedo_readback")
            return {"status": "listing_pending", "domain": domain,
                    "reason_codes": ["listing_readback_missing"]}
        listed, listing_safe = _listing_terms_match(
            domain, review["listing_price_eur"], review["minimum_accepted_price_eur"],
            listing_readback, listing_rows,
        )
        status_public = ({key: listing_readback[key] for key in (
            "domain", "listed", "status", "price", "currency", "provider",
            "provider_receipt_id", "readback_verified",
        ) if key in listing_readback} if isinstance(listing_readback, dict) else {})
        rows_public = [{key: row[key] for key in (
            "domain", "listed", "price", "min_price", "fixed_price", "currency",
            "provider", "readback_verified",
        ) if key in row} for row in listing_rows if isinstance(row, dict)] if isinstance(listing_rows, list) else []
        _write_private_json(evidence_dir / "sedo-listing-readbacks.json", {
            "domain_status": status_public,
            "domain_list": rows_public,
        })
        listing_refs = sorted({*allowed_refs, f"domain-flip://evidence/{context['run_id']}/{label}/sedo-listing-readbacks.json"})
        _event(root, context, domain, phase="listing-readback", command="sedo_status",
               effect="verified" if listing_safe else "effect_unknown",
               readback=listing_safe or None,
               provider_receipt_id=listing_safe.get("provider_receipt_id") if isinstance(listing_safe.get("provider_receipt_id"), str) else None,
               evidence_refs=listing_refs,
               error_class=None if listing_safe else "listing_terms_mismatch",
               exit_code=0 if listing_safe else None,
               next_action="await_buyer_settlement" if listed else "official_sedo_readback")
        return {"status": "listed" if listed else "listing_pending", "domain": domain,
                "reason_codes": [] if listed else ["listing_not_confirmed"]}
    return _append_simple(root, context, names[0], reason="candidate_batch_exhausted",
                          next_action="next_daily_candidate")


def run_once(
    *,
    state_root: Path = DEFAULT_STATE_ROOT,
    context: dict[str, Any],
    funding: dict[str, Any] | None = None,
    registrant: dict[str, Any] | None = None,
    registrar: Any = None,
    sedo: Any = None,
    rights_searcher: Any = None,
    candidate_names: list[str] | None = None,
    market_evidence: dict[str, Any] | None = None,
    fee_evidence: dict[str, Any] | None = None,
    reviewer: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    with _owner_lock(Path(state_root)):
        return _run_once(
            state_root=Path(state_root), context=context, funding=funding, registrant=registrant,
            registrar=registrar, sedo=sedo, rights_searcher=rights_searcher,
            candidate_names=candidate_names, market_evidence=market_evidence,
            fee_evidence=fee_evidence, reviewer=reviewer,
        )


def _main_context(args: Any = None) -> dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    release_sha = os.environ.get("LIFE_MANAGER_RELEASE_SHA")
    if not isinstance(release_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        try:
            release_sha = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True, timeout=5,
            ).stdout.strip()
        except Exception:
            raise ValueError("release_sha_missing") from None
    safe_env = {
        key: os.environ[key] for key in ("LIFE_MANAGER_LOOP_ID", "LIFE_MANAGER_RELEASE_SHA")
        if key in os.environ
    }
    safe_argv = ["skills/domain-flip/run.py"]
    if args is not None:
        for domain in args.candidate_names or []:
            safe_argv.append(f"--candidate={domain}")
        state_root = Path(args.state_root).expanduser().resolve()
        if state_root != DEFAULT_STATE_ROOT.resolve():
            digest = hashlib.sha256(str(state_root).encode("utf-8")).hexdigest()
            safe_argv.append(f"--state-root-sha256={digest}")
    return {
        "run_id": run_id,
        "owner_id": "domain-flip",
        "occurrence_id": f"domain-flip:{run_id}",
        "release_sha": release_sha,
        "loaded_argv": safe_argv,
        "loaded_env": safe_env,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--candidate", action="append", dest="candidate_names")
    args = parser.parse_args()
    sys.path.insert(0, str(SKILL_DIR))
    import openprovider
    import rights_search
    import sedo

    root = Path(args.state_root).expanduser()
    try:
        funding = _private_json(root / "funding.json")
        registrant = _private_json(root / "registrant.json")
        market = _private_json(root / "market.json")
        fee_costs = _private_json(root / "fees.json")
        sedo_client = sedo.SedoClient()
        try:
            fee_schedule = sedo_client.fee_schedule()
        except Exception:
            fee_schedule = None
        fees = ({**(fee_costs if isinstance(fee_costs, dict) else {}), **fee_schedule}
                if isinstance(fee_schedule, dict)
                else {"readback_verified": False, "evidence_refs": []})
        result = run_once(
            state_root=root,
            context=_main_context(args),
            funding=funding,
            registrant=registrant,
            registrar=openprovider.OpenProviderClient(),
            sedo=sedo_client,
            rights_searcher=rights_search.EUIPORightsSearch(),
            candidate_names=args.candidate_names,
            market_evidence=market,
            fee_evidence=fees,
        )
    except Exception as error:
        result = {"status": "failed", "reason_codes": [str(getattr(error, "code", "owner_pass_failed"))]}
    print(json.dumps(_json_ready(result), sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") not in {"failed", "effect_unknown"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
