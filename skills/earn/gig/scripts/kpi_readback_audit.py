#!/usr/bin/env python3
"""Audit local KPI truth against authenticated Coconala readback artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from kpi_reconciler import reconcile_state, verified_application_identities
from storefront_direct import _storefront_paths


APPLIED_URL = "https://coconala.com/mypage/job_matching/applied/offers"
HASH_KEYS = {
    "storefront_readback", "storefront_contract", "apply_readback", "applied.jsonl",
    "settlement_projection",
}
ULID = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")
SHA256 = re.compile(r"[0-9a-f]{64}")


class AuditError(ValueError):
    pass


def _storefront_contract_path() -> Path:
    return _storefront_paths()["scorecard"]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _reject_constant(value: str) -> None:
    raise ValueError(value)


def _time(value: Any) -> dt.datetime:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return dt.datetime.fromtimestamp(value, dt.timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise AuditError("timestamp is invalid") from exc
    if not isinstance(value, str) or not value.strip():
        raise AuditError("timestamp is unavailable")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditError("timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise AuditError("timestamp must include timezone")
    return parsed


def _request_id(value: Any) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise AuditError("request identity is invalid")
    if not (value.isdigit() or ULID.fullmatch(value)):
        raise AuditError("request identity is invalid")
    return value


def _fresh(value: Any, audit_time: dt.datetime, max_age_seconds: int, name: str) -> None:
    observed = _time(value)
    lag = (audit_time - observed).total_seconds()
    if lag < 0:
        raise AuditError(f"{name} readback is future-observed")
    if lag > max_age_seconds:
        raise AuditError(f"{name} readback is stale")


def _storefront_sales(
    readback: dict[str, Any], audit_time: dt.datetime, expected_ids: set[str],
    max_age_seconds: int,
) -> int:
    if not isinstance(readback, dict) or not isinstance(readback.get("services"), list):
        raise AuditError("storefront readback is malformed")
    _fresh(readback.get("observed_at"), audit_time, max_age_seconds, "storefront")
    services = readback["services"]
    digest = hashlib.sha256(_canonical(services)).hexdigest()
    if readback.get("content_sha256") != digest:
        raise AuditError("storefront content hash mismatch")
    if type(readback.get("service_count")) is not int or readback["service_count"] != len(services):
        raise AuditError("storefront service count mismatch")
    ids: set[str] = set()
    live = 0
    total = 0
    for service in services:
        if not isinstance(service, dict):
            raise AuditError("storefront service is malformed")
        service_id = str(service.get("service_id") or "")
        if not service_id.isdigit() or service_id in ids:
            raise AuditError("storefront service identity is invalid")
        ids.add(service_id)
        count = service.get("sales_count")
        if type(count) is not int or count < 0:
            raise AuditError("storefront sales count unavailable")
        total += count
        live += service.get("state") == "公開中"
    if not ids or ids != expected_ids:
        raise AuditError("storefront inventory coverage mismatch")
    if type(readback.get("live_listings_count")) is not int or readback["live_listings_count"] != live:
        raise AuditError("storefront live listing count mismatch")
    return total


def _official_apply_ids(
    readback: dict[str, Any], audit_time: dt.datetime, max_age_seconds: int,
) -> set[str]:
    if not isinstance(readback, dict):
        raise AuditError("apply readback is malformed")
    if readback.get("source") != "code_owned_cdp_readback":
        raise AuditError("apply readback source is invalid")
    if readback.get("observed") is not True or readback.get("not_found") is not False:
        raise AuditError("apply readback was not observed")
    _fresh(readback.get("observed_at"), audit_time, max_age_seconds, "apply")
    if not isinstance(readback.get("pass_id"), str) or not readback["pass_id"].strip():
        raise AuditError("apply readback pass identity is unavailable")
    if type(readback.get("pages_walked")) is not int or readback["pages_walked"] < 1:
        raise AuditError("apply readback page coverage is unavailable")
    if type(readback.get("cards_seen")) is not int or readback["cards_seen"] < 1:
        raise AuditError("apply readback page coverage is unavailable")
    if type(readback.get("has_next_page")) is not bool:
        raise AuditError("apply readback page coverage is unavailable")
    urls = readback.get("urls")
    if readback.get("url") != APPLIED_URL or not isinstance(urls, list) or APPLIED_URL not in urls:
        raise AuditError("apply readback URL is invalid")
    raw_ids = readback.get("request_ids")
    if not isinstance(raw_ids, list):
        raise AuditError("apply request identities are unavailable")
    request_ids = [_request_id(value) for value in raw_ids]
    if len(request_ids) != len(set(request_ids)):
        raise AuditError("apply request identities are duplicated")
    expected_raw = readback.get("expected_request_ids")
    absent_raw = readback.get("applied_page_absent_request_ids")
    if not isinstance(expected_raw, list) or not expected_raw:
        raise AuditError("apply sample coverage is unavailable")
    expected = {_request_id(value) for value in expected_raw}
    if (
        not isinstance(absent_raw, list) or absent_raw
        or readback.get("missing_count") != 0
        or readback.get("unresolved_count") != 0
        or not expected.issubset(set(request_ids))
    ):
        raise AuditError("apply readback reports unresolved identities")
    return set(request_ids)


def _local_verified_ids(rows: Iterable[dict[str, Any]]) -> tuple[set[str], set[str]]:
    try:
        verified, conflicts = verified_application_identities(rows)
    except ValueError as exc:
        raise AuditError("local application proof is malformed") from exc
    return set(verified), conflicts


def _local_storefront_count(events: Iterable[dict[str, Any]]) -> int:
    receipts: set[str] = set()
    count = 0
    for event in events:
        if not isinstance(event, dict):
            raise AuditError("settlement event is malformed")
        if event.get("event_name") != "settled":
            continue
        identity = event.get("identity")
        receipt = identity.get("payment_receipt_id") if isinstance(identity, dict) else None
        if not isinstance(receipt, str) or not receipt or receipt in receipts:
            raise AuditError("settlement receipt identity is invalid")
        receipts.add(receipt)
        count += event.get("acquisition_lane") == "storefront"
    return count


def audit_rows(
    storefront_readback: dict[str, Any],
    apply_readback: dict[str, Any],
    applications: Iterable[dict[str, Any]],
    settlement_events: Iterable[dict[str, Any]],
    *,
    observed_at: str,
    input_hashes: dict[str, str],
    expected_storefront_ids: set[str],
    max_age_seconds: int = 3600,
) -> dict[str, Any]:
    audit_time = _time(observed_at)
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise AuditError("audit freshness bound is invalid")
    if set(input_hashes) != HASH_KEYS or any(
        not isinstance(value, str) or not SHA256.fullmatch(value)
        for value in input_hashes.values()
    ):
        raise AuditError("audit input hashes are invalid")
    official_sales = _storefront_sales(
        storefront_readback, audit_time, expected_storefront_ids, max_age_seconds
    )
    local_sales = _local_storefront_count(settlement_events)
    official_apply = _official_apply_ids(apply_readback, audit_time, max_age_seconds)
    local_apply, local_conflicts = _local_verified_ids(applications)
    missing = sorted(
        (official_apply - local_apply) | (official_apply & local_conflicts),
        key=lambda value: (not value.isdigit(), value),
    )
    storefront_status = "match" if official_sales == local_sales else "mismatch"
    apply_status = "match" if not missing else "mismatch"
    audit_id = "coconala:kpi-readback:" + hashlib.sha256(_canonical(input_hashes)).hexdigest()
    return {
        "schema_version": 1,
        "audit_id": audit_id,
        "observed_at": audit_time.isoformat(timespec="seconds"),
        "status": "match" if storefront_status == apply_status == "match" else "mismatch",
        "checks": {
            "storefront_sales": {
                "status": storefront_status,
                "official_count": official_sales,
                "local_count": local_sales,
                "delta": official_sales - local_sales,
            },
            "apply_sample": {
                "status": apply_status,
                "coverage": "official_sample_only",
                "official_sample_count": len(official_apply),
                "local_verified_count": len(local_apply),
                "matched_count": len(official_apply) - len(missing),
                "missing_local_ids": missing,
            },
        },
        "inputs": dict(sorted(input_hashes.items())),
    }


def append_receipt(path: Path, report: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        try:
            existing = [
                json.loads(line, parse_constant=_reject_constant)
                for line in handle if line.strip()
            ]
        except (json.JSONDecodeError, ValueError) as exc:
            raise AuditError("audit receipt ledger is malformed") from exc
        for row in existing:
            if row.get("audit_id") != report.get("audit_id"):
                continue
            existing_semantics = {key: value for key, value in row.items() if key != "observed_at"}
            report_semantics = {
                key: value for key, value in report.items() if key != "observed_at"
            }
            if _canonical(existing_semantics) != _canonical(report_semantics):
                raise AuditError("conflicting audit receipt")
            return False
        handle.seek(0, os.SEEK_END)
        handle.write(_canonical(report).decode() + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)
    return True


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        content = path.read_bytes()
        value = json.loads(content, parse_constant=_reject_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AuditError(f"unreadable {path.name}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"unreadable {path.name}")
    return value, content


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        content = path.read_bytes() if path.exists() else b""
        rows = [
            json.loads(line, parse_constant=_reject_constant)
            for line in content.decode().splitlines() if line.strip()
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AuditError(f"unreadable {path.name}") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise AuditError(f"unreadable {path.name}")
    return rows, content


def audit_state(
    state_dir: Path, storefront_path: Path, apply_path: Path, *, observed_at: str,
    storefront_contract_path: Path | None = None, max_age_seconds: int = 3600,
) -> dict[str, Any]:
    storefront_contract_path = storefront_contract_path or _storefront_contract_path()
    storefront, storefront_content = _read_json(storefront_path)
    apply, apply_content = _read_json(apply_path)
    applications, applications_content = _read_jsonl(state_dir / "applied.jsonl")
    contract, contract_content = _read_json(storefront_contract_path)
    contract_services = contract.get("services")
    if not isinstance(contract_services, list):
        raise AuditError("storefront contract is malformed")
    expected_ids = {
        str(row.get("service_id") or "") for row in contract_services if isinstance(row, dict)
    }
    if len(expected_ids) != len(contract_services) or not all(value.isdigit() for value in expected_ids):
        raise AuditError("storefront contract is malformed")
    settlement = reconcile_state(state_dir)
    event_hash = hashlib.sha256(_canonical(settlement["events"])).hexdigest()
    return audit_rows(
        storefront, apply, applications, settlement["events"], observed_at=observed_at,
        input_hashes={
            "storefront_readback": hashlib.sha256(storefront_content).hexdigest(),
            "storefront_contract": hashlib.sha256(contract_content).hexdigest(),
            "apply_readback": hashlib.sha256(apply_content).hexdigest(),
            "applied.jsonl": hashlib.sha256(applications_content).hexdigest(),
            "settlement_projection": event_hash,
        }, expected_storefront_ids=expected_ids, max_age_seconds=max_age_seconds,
    )


def unreadable_receipt(
    *, state_dir: Path, storefront_path: Path, apply_path: Path,
    storefront_contract_path: Path, observed_at: str, reason: str,
) -> dict[str, Any]:
    sources = {
        "storefront_readback": storefront_path,
        "storefront_contract": storefront_contract_path,
        "apply_readback": apply_path,
        "applied.jsonl": state_dir / "applied.jsonl",
        "earnings.jsonl": state_dir / "earnings.jsonl",
        "identity_chain.jsonl": state_dir / "identity_chain.jsonl",
    }
    hashes: dict[str, str] = {}
    for name, path in sources.items():
        try:
            content = path.read_bytes()
        except OSError:
            content = f"missing:{path}".encode()
        hashes[name] = hashlib.sha256(content).hexdigest()
    identity = {"inputs": hashes, "reason": reason}
    return {
        "schema_version": 1,
        "audit_id": "coconala:kpi-readback-unreadable:" + hashlib.sha256(
            _canonical(identity)
        ).hexdigest(),
        "observed_at": _time(observed_at).isoformat(timespec="seconds"),
        "status": "unreadable",
        "checks": {"official_readback": {"status": "unreadable", "reason": reason}},
        "inputs": hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--storefront-readback", type=Path, required=True)
    parser.add_argument("--apply-readback", type=Path, required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--storefront-contract", type=Path, default=_storefront_contract_path())
    parser.add_argument("--max-age-seconds", type=int, default=3600)
    parser.add_argument("--audit-log", type=Path)
    args = parser.parse_args()
    try:
        report = audit_state(
            args.state_dir, args.storefront_readback, args.apply_readback,
            observed_at=args.observed_at, storefront_contract_path=args.storefront_contract,
            max_age_seconds=args.max_age_seconds,
        )
        appended = append_receipt(
            args.audit_log or args.state_dir / "kpi-readback-audit.jsonl", report
        )
    except ValueError as exc:
        report = unreadable_receipt(
            state_dir=args.state_dir,
            storefront_path=args.storefront_readback,
            apply_path=args.apply_readback,
            storefront_contract_path=args.storefront_contract,
            observed_at=args.observed_at,
            reason=str(exc),
        )
        appended = append_receipt(
            args.audit_log or args.state_dir / "kpi-readback-audit.jsonl", report
        )
        output = dict(report)
        output["receipt_appended"] = appended
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 2
    output = dict(report)
    output["receipt_appended"] = appended
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if report["status"] == "match" else 1


if __name__ == "__main__":
    raise SystemExit(main())
