"""Provision a release-pinned strategy only from complete validation reports."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from strategy_cards import StrategyCard, is_valid_release_sha, validate_strategy_card
from strategy_validation import select_strategy


class SelectionProvisionError(ValueError):
    """The deployment cannot safely create or retain a selected strategy."""


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


def _existing_selection_is_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    selection = value.get("selection")
    if selection == "no_strategy":
        return value.get("strategy_id") == "NO_STRATEGY"
    if selection != "selected":
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


def _selection_payload(selection: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "selection": "selected",
        "strategy_id": selection.get("strategy_id"),
        "venue": selection.get("venue"),
        "report_id": report_id,
        "release_sha": selection.get("release_sha"),
        "card": selection.get("card"),
        "holdout": selection.get("holdout"),
        "cost_model": selection.get("cost_model"),
        "evidence_ids": selected.get("evidence_ids"),
    }


def provision_selection(path: str | Path, reports_path: str | Path) -> dict[str, str]:
    """Create a selected state once; never overwrite an existing owner state."""
    destination = Path(path).expanduser()
    if destination.is_symlink():
        raise SelectionProvisionError("selection_symlink_refused")
    if destination.exists():
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SelectionProvisionError("existing_selection_invalid") from error
        if not _existing_selection_is_valid(existing):
            raise SelectionProvisionError("existing_selection_invalid")
        return {"status": "existing", "path": str(destination)}

    reports = _read_reports(Path(reports_path).expanduser())
    selection = select_strategy(reports)
    payload = _selection_payload(selection)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _atomic_write(destination, (encoded + "\n").encode("utf-8"))
    return {"status": "created", "path": str(destination)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--reports", required=True)
    args = parser.parse_args(argv)
    try:
        result = provision_selection(args.path, args.reports)
    except SelectionProvisionError as error:
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SelectionProvisionError", "main", "provision_selection"]
