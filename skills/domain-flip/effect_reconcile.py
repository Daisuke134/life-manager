"""Read-only reconciliation for uncertain registrar and Sedo effects."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import run


def _reconcile_occurrence_unlocked(
    *,
    occurrence_id: str,
    state_root: Path,
    registrar: Any,
    sedo: Any = None,
    resolve: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Read provider state; retain the fence unless a positive official readback exists."""
    events = [event for event in run.read_events(Path(state_root))
              if event.get("occurrence_id") == occurrence_id]
    if not events:
        return {"status": "not_found", "occurrence_id": occurrence_id}
    operation_state: dict[str, tuple[int, dict[str, Any] | None]] = {}
    for index, event in enumerate(events):
        command = event.get("command")
        if command in {"register", "get_domain", "list_domains"}:
            operation = "registration"
        elif command in {"sedo_insert", "sedo_status"}:
            operation = "listing"
        else:
            continue
        if event.get("effect") in {"pending", "submitted", "effect_unknown"}:
            operation_state[operation] = (index, event)
        elif (event.get("effect") == "verified"
              and event.get("phase") in {"registration-readback", "registration-reconciled",
                                          "listing-readback", "listing-reconciled"}):
            operation_state.pop(operation, None)
    uncertain = [(index, event) for index, event in operation_state.values() if event is not None]
    if not uncertain:
        return {"status": "resolved", "occurrence_id": occurrence_id}
    _, latest = max(uncertain, key=lambda item: item[0])
    domain = latest["candidate_id"]
    context = {key: latest[key] for key in (
        "run_id", "owner_id", "occurrence_id", "release_sha", "loaded_argv", "loaded_env",
    )}

    if latest["command"] in {"register", "get_domain"}:
        receipt_id = next((event.get("provider_receipt_id") for event in reversed(events)
                           if event.get("command") == "register" and event.get("provider_receipt_id")), None)
        try:
            if receipt_id and callable(getattr(registrar, "get_domain", None)):
                readback = registrar.get_domain(str(receipt_id))
            else:
                rows = registrar.list_domains()
                readback = next((row for row in rows if isinstance(row, dict) and row.get("domain") == domain), None)
        except Exception:
            return {"status": "held", "occurrence_id": occurrence_id,
                    "reason_code": "official_readback_unavailable", "external_effects": 0}
        if not isinstance(readback, dict):
            return {"status": "held", "occurrence_id": occurrence_id,
                    "reason_code": "registration_state_ambiguous", "external_effects": 0}
        expected_fingerprint = next((
            event.get("readback", {}).get("owner_handle_fingerprint")
            for event in events if isinstance(event.get("readback"), dict)
            and event["readback"].get("owner_handle_fingerprint")
        ), None)
        status = str(readback.get("status", "")).casefold()
        readback_id = readback.get("id")
        identity_matches = (
            readback.get("provider") == "openprovider"
            and isinstance(readback_id, str)
            and readback_id.isdigit()
            and readback.get("provider_receipt_id") == readback_id
            and (receipt_id is None or readback_id == str(receipt_id))
        )
        conclusive = (
            readback.get("domain") == domain
            and identity_matches
            and readback.get("readback_verified") is True
            and status in {"act", "active", "registered"}
            and expected_fingerprint is not None
            and readback.get("owner_handle_fingerprint") == expected_fingerprint
        )
        if not conclusive:
            return {"status": "held", "occurrence_id": occurrence_id,
                    "reason_code": "registration_state_ambiguous", "external_effects": 0}
        safe = {key: readback[key] for key in (
            "id", "domain", "status", "provider", "provider_receipt_id",
            "readback_verified", "owner_handle_fingerprint", "activation_date", "expiration_date", "renewal_date",
        ) if key in readback}
        run._event(
            Path(state_root), context, domain, phase="registration-reconciled",
            command="get_domain" if receipt_id else "list_domains", effect="verified",
            readback=safe, provider_receipt_id=str(readback["provider_receipt_id"]),
            evidence_refs=[], next_action="sedo_listing",
        )
        if resolve is not None:
            resolve(occurrence_id, safe)
        return {"status": "resolved_registered", "occurrence_id": occurrence_id,
                "domain": domain, "provider_receipt_id": str(readback["provider_receipt_id"]),
                "external_effects": 0}

    if latest["command"] in {"sedo_insert", "sedo_status"} and sedo is not None:
        dispatch = next((event for event in events
                         if event.get("command") == "sedo_insert"
                         and event.get("phase") == "listing-dispatch"
                         and isinstance(event.get("readback"), dict)), None)
        expected = dispatch.get("readback", {}) if dispatch else {}
        try:
            status_readback = sedo.domain_status(domain)
            domain_rows = sedo.domain_list([domain])
        except Exception:
            return {"status": "held", "occurrence_id": occurrence_id,
                    "reason_code": "official_readback_unavailable", "external_effects": 0}
        conclusive, safe = run._listing_terms_match(
            domain, expected.get("price"), expected.get("minimum_accepted_price_eur"),
            status_readback, domain_rows,
        )
        if not conclusive:
            return {"status": "held", "occurrence_id": occurrence_id,
                    "reason_code": "listing_terms_mismatch_or_ambiguous", "external_effects": 0}
        evidence_dir = Path(state_root) / "evidence" / context["run_id"] / domain[:-3]
        run._private_dir(evidence_dir.parent)
        run._private_dir(evidence_dir)
        run._write_private_json(evidence_dir / "sedo-listing-readbacks.json", {
            "domain_status": {key: status_readback[key] for key in (
                "domain", "listed", "status", "price", "currency", "provider",
                "provider_receipt_id", "readback_verified",
            ) if key in status_readback},
            "domain_list": [{key: row[key] for key in (
                "domain", "listed", "price", "min_price", "fixed_price", "currency",
                "provider", "readback_verified",
            ) if key in row} for row in domain_rows if isinstance(row, dict)],
        })
        evidence_ref = f"domain-flip://evidence/{context['run_id']}/{domain[:-3]}/sedo-listing-readbacks.json"
        run._event(
            Path(state_root), context, domain, phase="listing-reconciled",
            command="sedo_status", effect="verified", readback=run._json_ready(safe),
            provider_receipt_id=safe.get("provider_receipt_id"), evidence_refs=[evidence_ref],
            next_action="await_buyer_settlement",
        )
        if resolve is not None:
            resolve(occurrence_id, safe)
        return {"status": "resolved_listed", "occurrence_id": occurrence_id,
                "domain": domain, "external_effects": 0}

    return {"status": "held", "occurrence_id": occurrence_id,
            "reason_code": "effect_type_unsupported", "external_effects": 0}


def reconcile_occurrence(
    *,
    occurrence_id: str,
    state_root: Path,
    registrar: Any,
    sedo: Any = None,
    resolve: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Serialize readback with the owner so the fence cannot be cleared mid-write."""
    with run._owner_lock(Path(state_root)):
        return _reconcile_occurrence_unlocked(
            occurrence_id=occurrence_id, state_root=Path(state_root), registrar=registrar,
            sedo=sedo, resolve=resolve,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrence-id", required=True)
    parser.add_argument("--state-root", type=Path, default=run.DEFAULT_STATE_ROOT)
    args = parser.parse_args()
    sys.path.insert(0, str(HERE))
    import openprovider
    import sedo

    try:
        result = reconcile_occurrence(
            occurrence_id=args.occurrence_id,
            state_root=args.state_root,
            registrar=openprovider.OpenProviderClient(),
            sedo=sedo.SedoClient(),
        )
    except Exception as error:
        result = {"status": "held", "occurrence_id": args.occurrence_id,
                  "reason_code": str(getattr(error, "code", "reconciliation_failed")),
                  "external_effects": 0}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status", "").startswith("resolved") else 1


if __name__ == "__main__":
    raise SystemExit(main())
