"""Provision a release-pinned strategy only from complete validation reports."""

from __future__ import annotations

import argparse
import json
import importlib.util
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strategy_cards import StrategyCard, is_valid_release_sha, validate_strategy_card
from strategy_validation import select_strategy


_ALPACA = Path(__file__).resolve().parents[3] / "skills" / "alpaca-investment"
if str(_ALPACA) not in sys.path:
    sys.path.append(str(_ALPACA))
from control import control_fence
# The core has another effect_store module with a different receipt schema.
_effect_spec = importlib.util.spec_from_file_location("alpaca_selection_effect_store", _ALPACA / "effect_store.py")
_effects = importlib.util.module_from_spec(_effect_spec)
_effect_spec.loader.exec_module(_effects)
from crypto_ownership_proof import recorded_close_proof_from_rows, recorded_no_fill_proof_from_rows, recorded_fee_flat_state_from_rows
from etf_ownership import (_read_open, _close_provider_order, _closed_account_readback,
                           _number, ETF_OWNER_IDS, ETF_STRATEGY_ID)


class SelectionProvisionError(ValueError):
    """The deployment cannot safely create or retain a selected strategy."""


_KNOWN_HOLD_ERRORS = frozenset({
    "owned_close_evidence_unknown",
    "owned_policy_identity_unknown",
    "no_strategy_selected",
})


def _atomic_write(path: Path, payload: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def _read_reports(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SelectionProvisionError("validation_reports_invalid") from error

    if isinstance(value, list):
        reports = value
    elif isinstance(value, dict) and isinstance(value.get("reports"), list):
        reports = value["reports"]
    else:
        raise SelectionProvisionError("validation_reports_invalid")
    if any(not isinstance(report, dict) for report in reports):
        raise SelectionProvisionError("validation_reports_invalid")
    return reports


def _existing_selected_shape_is_valid(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("selection") != "selected":
        return False
    if not isinstance(value.get("report_id"), str) or not value["report_id"].strip():
        return False
    if not isinstance(value.get("strategy_id"), str) or not value["strategy_id"].strip():
        return False
    if not is_valid_release_sha(value.get("release_sha")):
        return False
    card_payload = value.get("card")
    if not isinstance(card_payload, dict):
        return False
    try:
        card = StrategyCard.from_mapping(card_payload)
    except (TypeError, ValueError):
        return False
    return card.strategy_id == value["strategy_id"] and not validate_strategy_card(card)


def _existing_selection_expiry_status(value: dict[str, Any]) -> str:
    expires_at = value.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at.strip():
        return "invalid"
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return "invalid"
    if expires.tzinfo is None:
        return "invalid"
    if expires <= datetime.now(timezone.utc):
        return "expired"
    return "future"


def _existing_selection_is_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("selection") == "no_strategy":
        return value.get("strategy_id") == "NO_STRATEGY"
    return _existing_selected_shape_is_valid(value) and _existing_selection_expiry_status(value) == "future"


def _existing_selection_is_expired(value: Any) -> bool:
    return (
        _existing_selected_shape_is_valid(value)
        and _existing_selection_expiry_status(value) == "expired"
    )


def _selection_payload(
    selection: dict[str, Any],
    source_reports: list[dict[str, Any]],
    runtime_release_sha: str | None = None,
) -> dict[str, Any]:
    if selection.get("selection") != "selected":
        raise SelectionProvisionError("no_strategy_selected")
    report_id = selection.get("report_id")
    reports = selection.get("reports")
    if not isinstance(report_id, str) or not isinstance(reports, list):
        raise SelectionProvisionError("selected_strategy_invalid")
    selected = next(
        (row for row in reports
         if isinstance(row, dict) and row.get("report_id") == report_id and row.get("accepted") is True),
        None,
    )
    if selected is None:
        raise SelectionProvisionError("selected_strategy_invalid")
    source = next(
        (report for report in source_reports if report.get("report_id") == report_id),
        None,
    )
    if source is None:
        raise SelectionProvisionError("selected_strategy_invalid")
    if runtime_release_sha is not None and not is_valid_release_sha(runtime_release_sha):
        raise SelectionProvisionError("runtime_release_sha_invalid")
    expires_at = source.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at.strip():
        raise SelectionProvisionError("validation_report_expiry_missing")
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise SelectionProvisionError("validation_report_expiry_invalid") from error
    if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
        raise SelectionProvisionError("validation_report_expired")
    payload = {
        "selection": "selected",
        "strategy_id": selection.get("strategy_id"),
        "venue": selection.get("venue"),
        "report_id": report_id,
        "release_sha": runtime_release_sha or selection.get("release_sha"),
        "card": selection.get("card"),
        "holdout": selection.get("holdout"),
        "benchmark": selected.get("benchmark"),
        "cost_model": selection.get("cost_model"),
        "evidence_ids": selected.get("evidence_ids"),
        "observed_at": source.get("observed_at"),
        "expires_at": expires_at,
    }
    if runtime_release_sha is not None:
        payload["report_release_sha"] = selection.get("release_sha")
    return payload


def _official_etf_close(marker: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    try:
        _number(marker["close_account_cash_usd"])
        _number(marker["close_account_equity_usd"])
        observed = datetime.fromisoformat(marker["close_account_readback_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return False
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    refs = marker.get("close_source_receipt_ids")
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        return False
    for row in rows:
        envelope = row.get("strategy_receipt")
        receipt = envelope.get("receipt") if isinstance(envelope, dict) else None
        if (row.get("receipt_type") != "outcome" or row.get("outcome") != "broker_reconciled"
                or row.get("mode") != ("paper" if marker["owner_id"] == "alpaca-investment-paper" else "live")
                or row.get("client_order_id") != marker.get("close_client_order_id")
                or not isinstance(receipt, dict)
                or any(receipt.get(key) != value for key, value in marker.items())):
            continue
        if not any(intent.get("receipt_type") == "effect_intent"
                   and intent.get("effect_id") == row.get("effect_id")
                   and intent.get("client_order_id") == marker.get("close_client_order_id")
                   and intent.get("owner_id") == marker["owner_id"]
                   and intent.get("strategy_id") == marker["strategy_id"]
                   and intent.get("mode") == row.get("mode")
                   and isinstance(intent.get("order"), dict)
                   and intent["order"].get("side") == "sell"
                   and intent["order"].get("symbol") == marker["symbol"] for intent in rows):
            continue
        try:
            account = _closed_account_readback(envelope.get("account_readback", {}), symbol=marker["symbol"])
            if (account["cash"] != marker["close_account_cash_usd"]
                    or account["equity"] != marker["close_account_equity_usd"]
                    or account["observed_at"] != marker["close_account_readback_at"]):
                continue
            provider_id, price = _close_provider_order(
                row.get("broker", {}), client_order_id=marker["close_client_order_id"],
                symbol=marker["symbol"], expected_qty=_number(marker["position_qty"], positive=True))
            if (provider_id != marker.get("close_provider_order_id")
                    or provider_id != row.get("broker_receipt_id")
                    or price != _number(marker["close_filled_avg_price"], positive=True)):
                continue
            return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


def _official_crypto_closed(marker: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    try:
        entries = [row for row in rows if row.get("receipt_type") == "effect_intent"
                   and row.get("status") == "planned" and row.get("effect_id") == marker.get("entry_effect_id")]
        if len(entries) != 1:
            return False
        intent = entries[0]
        if marker.get('close_reason')=='native_fee_debit':
            recorded_fee_flat_state_from_rows(rows,marker,mode=intent.get('mode'),owner_id=intent.get('owner_id'))
            return True
        close_effect, close_client = marker.get("close_effect_id"), marker.get("close_client_order_id")
        if (close_effect is None) != (close_client is None):
            return False
        effect = close_effect if close_effect is not None else marker["entry_effect_id"]
        outcomes = [row for row in rows if row.get("receipt_type") == "outcome"
                    and row.get("effect_id") == effect and isinstance(row.get("strategy_receipt"), dict)]
        if not outcomes:
            return False
        outcome = outcomes[-1]
        reader = recorded_close_proof_from_rows if close_effect is not None else recorded_no_fill_proof_from_rows
        reader(rows, marker, outcome.get("broker"), outcome["strategy_receipt"].get("account_readback"),
               mode=intent.get("mode"), owner_id=intent.get("owner_id"))
        return True
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def _guard_reports(
    root: Path, existing: Any, reports: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    try:
        ledger = root / "receipts.jsonl"
        if ledger.is_symlink():
            raise ValueError("ledger_symlink")
        rows = _effects._rows(ledger)
        intents = {row["effect_id"]: row for row in rows if row.get("receipt_type") == "effect_intent"}
        outcomes = {row["effect_id"]: row for row in rows if row.get("receipt_type") == "outcome"}
        protected = bool(_effects._unresolved(rows)) or any(
            not _effects._outcome_closed(outcomes.get(effect_id), rows) for effect_id in intents)
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise SelectionProvisionError("selection_ledger_invalid") from error
    owned_strategy = None
    for name in ("etf-owned-position.json", "live-owned-position.json"):
        path = root / name
        if path.is_symlink():
            raise SelectionProvisionError("ownership_state_invalid")
        try:
            marker = json.loads(path.read_text())
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            raise SelectionProvisionError("ownership_state_invalid") from error
        if not isinstance(marker, dict):
            raise SelectionProvisionError("ownership_state_invalid")
        if name == "etf-owned-position.json":
            try:
                if marker.get("owner_id") not in ETF_OWNER_IDS or marker.get("strategy_id") != ETF_STRATEGY_ID:
                    raise ValueError
                _read_open(marker)
            except (TypeError, ValueError) as error:
                raise SelectionProvisionError("ownership_state_invalid") from error
            closed = marker.get("status") == "closed"
            if closed and not _official_etf_close(marker, rows):
                raise SelectionProvisionError("owned_close_evidence_unknown")
            if not closed:
                owned_strategy = ETF_STRATEGY_ID
                protected = True
        else:
            if marker.get("status") not in {"entry_pending", "open", "closing", "closed"}:
                raise SelectionProvisionError("ownership_state_invalid")
            if marker.get("status") == "closed":
                if not _official_crypto_closed(marker, rows):
                    raise SelectionProvisionError("owned_close_evidence_unknown")
            else:
                protected = True
    if protected:
        if not _existing_selected_shape_is_valid(existing) or (
                owned_strategy is not None and existing.get("strategy_id") != owned_strategy):
            raise SelectionProvisionError("owned_policy_identity_unknown")
        def canonical(card):
            return {key: value for key, value in card.items() if key != "status"}
        current = canonical(existing["card"])
        return ([report for report in reports if isinstance(report.get("card"), dict)
                 and canonical(report["card"]) == current], True)
    return reports, False


def provision_selection(path: str | Path, reports_path: str | Path,
                        runtime_release_sha: str | None = None, *, refresh: bool = False) -> dict[str, str]:
    """Serialize selected-policy reads and writes with the existing submit fence."""
    destination = Path(path).expanduser()
    if destination.is_symlink() or destination.parent.is_symlink():
        raise SelectionProvisionError("selection_symlink_refused")
    try:
        with control_fence(destination.parent):
            return _provision_selection_locked(destination, reports_path, runtime_release_sha, refresh=refresh)
    except ValueError as error:
        if isinstance(error, SelectionProvisionError):
            raise
        raise SelectionProvisionError("selection_control_invalid") from error


def _provision_selection_locked(
    path: str | Path,
    reports_path: str | Path,
    runtime_release_sha: str | None = None,
    *,
    refresh: bool = False,
) -> dict[str, str]:
    """Create selected state, preserving valid state unless explicitly refreshing."""
    destination = Path(path).expanduser()
    if destination.is_symlink():
        raise SelectionProvisionError("selection_symlink_refused")
    if runtime_release_sha is not None and not is_valid_release_sha(runtime_release_sha):
        raise SelectionProvisionError("runtime_release_sha_invalid")
    existing_valid = False
    existing = None
    if destination.exists():
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SelectionProvisionError("existing_selection_invalid") from error
        existing_valid = _existing_selection_is_valid(existing)
        if existing_valid and not refresh:
            return {"status": "existing", "path": str(destination)}
        if not existing_valid and not _existing_selection_is_expired(existing):
            raise SelectionProvisionError("existing_selection_invalid")

    reports, protected_policy = _guard_reports(
        destination.parent, existing, _read_reports(Path(reports_path).expanduser()))
    try:
        selection = select_strategy(reports)
        payload = _selection_payload(selection, reports, runtime_release_sha)
    except SelectionProvisionError as error:
        if refresh and existing_valid:
            if (str(error) == "no_strategy_selected" and isinstance(existing, dict)
                    and not protected_policy and reports):
                expired = dict(existing)
                expired["expires_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                encoded = json.dumps(expired, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"))
                _atomic_write(destination, (encoded + "\n").encode("utf-8"))
                return {"status": "expired", "path": str(destination)}
            return {"status": "existing", "path": str(destination)}
        raise
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _atomic_write(destination, (encoded + "\n").encode("utf-8"))
    return {"status": "created", "path": str(destination)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--reports", required=True)
    parser.add_argument("--release-sha")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--hold-on-known-blocker", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = provision_selection(
            args.path,
            args.reports,
            args.release_sha,
            refresh=args.refresh,
        )
    except SelectionProvisionError as error:
        if args.hold_on_known_blocker and str(error) in _KNOWN_HOLD_ERRORS:
            print(json.dumps({
                "next_action": "reconcile_selection_evidence",
                "path": str(Path(args.path).expanduser()),
                "reason": str(error),
                "status": "held",
            }, sort_keys=True))
            return 0
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SelectionProvisionError", "main", "provision_selection"]
