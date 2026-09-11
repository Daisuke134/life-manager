"""Provider-neutral Storefront judgement kernel.

Follows the one dependency direction this house's loop-engineering rules require
(``loop config -> reusable recipe -> shared runtime -> provider adapter -> official
provider``): this module holds the platform-independent judgement a Storefront wake
makes -- portfolio allocation, mutation-contract sealing/validation, official demand
scoring, replace-plan rendering, in-flight draft recovery, and the proposal-rejection
guard -- so a second marketplace consumer (Lancers, CrowdWorks, ...) never has to
rebuild it from scratch the way it would if this judgement stayed locked inside one
provider's script.

Extracted from the first marketplace provider adapter that grew this judgement, which
keeps thin module-level aliases to every function moved here so its own, much larger
call-site file and its existing tests keep working unchanged. This is a move, not a
redesign: no field is renamed, no return shape changed, no threshold altered. Anything
that named a DOM selector, an official URL, a form label, or a fixed platform string
was left behind or turned into a parameter here instead -- this module must not know
which marketplace is calling it.

Two functions here (``families_with_unpublished_drafts`` and
``recover_prepared_create_contract``) take an ``observed_deleted_draft_ids`` callable
rather than reading deleted-draft evidence themselves: the provider adapter owns that
read (and its own tests monkeypatch it), so the kernel accepts it as a dependency
instead of importing or duplicating the adapter's version.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------------
# Small file-IO primitives duplicated intentionally.
#
# The originals (``_jsonl_rows``, ``_append``, ``_append_key_once``,
# ``_load_portfolio_scorecard``) live in storefront_direct.py and are still used there
# by many call sites this extraction does not touch. Per the extraction rule -- take a
# helper along only when it has no other caller left behind -- those stay put, and this
# module carries its own minimal copies so it never has to import back into the
# provider adapter for plain JSON/JSONL file IO.
# ---------------------------------------------------------------------------------

def _append(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    path.chmod(0o600)


def _jsonl_rows(path: Path) -> tuple[list[dict], str | None]:
    if not path.is_file():
        return [], f"{path.name}_missing"
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    except (OSError, json.JSONDecodeError):
        return [], f"{path.name}_invalid"
    return rows, None


def _append_key_once(path: Path, field: str, value: dict) -> bool:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                prior = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"{path.stem}_ledger_invalid") from error
            if prior.get(field) == value.get(field):
                return False
    _append(path, value)
    return True


def _load_portfolio_scorecard(scorecard_path: Path) -> dict:
    try:
        scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("storefront_portfolio_policy_invalid") from error
    policy = scorecard.get("portfolio_policy")
    services = scorecard.get("services")
    backlog = scorecard.get("priority_backlog")
    if (not isinstance(policy, dict) or policy.get("version") != 1
            or type(policy.get("slot_limit")) is not int or policy["slot_limit"] <= 0
            or type(policy.get("minimum_views_for_retirement")) is not int
            or policy.get("short_term_zero_sales_can_retire") is not False
            or policy.get("retirement_mode") != "recoverable_unpublish_before_delete"
            or not isinstance(services, list) or not isinstance(backlog, list)
            or not isinstance(policy.get("replacement_candidates"), list)):
        raise RuntimeError("storefront_portfolio_policy_invalid")
    return scorecard


# ---------------------------------------------------------------------------------
# Portfolio allocation: KEEP / IMPROVE / RETIRE / REPLACE.
# ---------------------------------------------------------------------------------

def allocate_portfolio(
    state_dir: Path, contracts: list[dict], funnel: dict, scorecard_path: Path, now: int,
    duplicate_listings: list[dict] | None = None,
) -> dict:
    scorecard = _load_portfolio_scorecard(scorecard_path)
    policy = scorecard["portfolio_policy"]
    services = scorecard["services"]
    backlog = scorecard["priority_backlog"]
    latest_analytics = {}
    analytics_path = state_dir / "analytics.jsonl"
    rows, analytics_error = _jsonl_rows(analytics_path)
    for row in rows:
        if str(row.get("service_id") or "").isdigit():
            latest_analytics[str(row["service_id"])] = row
    contract_by_id = {str(row["service_id"]): row for row in contracts}
    demand = {str(row.get("service_id") or ""): ((row.get("scores") or {}).get("demand"))
              for row in services if isinstance(row, dict)}
    gaps = {str(row.get("service_id") or ""): row for row in sorted(
        (row for row in backlog if isinstance(row, dict)), key=lambda row: int(row.get("priority") or 9999),
    )}
    events, funnel_error = _jsonl_rows(state_dir / "funnel-events.jsonl")
    inquiries = {}
    payments = {}
    net = {}
    for event in events:
        service_id = str(event.get("service_id") or "")
        if not service_id:
            continue
        if event.get("event_kind") == "inquiry":
            inquiries[service_id] = inquiries.get(service_id, 0) + 1
        elif event.get("event_kind") == "payment":
            payments[service_id] = payments.get(service_id, 0) + 1
            if type(event.get("net_receipt_jpy")) in {int, float}:
                net[service_id] = net.get(service_id, 0.0) + float(event["net_receipt_jpy"])
    evidence_identity = {
        "contracts": {key: value["service_version_sha256"] for key, value in sorted(contract_by_id.items())},
        "analytics": {key: {"window": value.get("window"), "metrics": value.get("metrics")}
                      for key, value in sorted(latest_analytics.items())},
        "funnel": funnel.get("cutoff_cursor"), "policy": policy,
    }
    evidence_cursor = hashlib.sha256(json.dumps(
        evidence_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    capacity_pressure = len(contract_by_id) >= policy["slot_limit"]
    # A listing that duplicates another needs no measurement window to justify removing it: it
    # should never have been published, and the pair splits the same buyers between two pages.
    # The later listing is the one that goes, so the older page keeps whatever history it has.
    duplicate_of = {}
    for pair in duplicate_listings or []:
        first, second = sorted(str(value) for value in pair.get("service_ids") or [])
        if first and second:
            duplicate_of[second] = first
    replacements = policy["replacement_candidates"]
    allocations = []
    appended = 0
    for service_id, contract in sorted(contract_by_id.items()):
        analytics = latest_analytics.get(service_id, {})
        metrics = analytics.get("metrics") if isinstance(analytics.get("metrics"), dict) else {}
        views = ((metrics.get("views") or {}).get("value"))
        purchases = ((metrics.get("purchases") or {}).get("value"))
        favorites = ((metrics.get("favorites") or {}).get("value"))
        known = type(views) is int and type(purchases) is int and type(favorites) is int
        minimum_sample = known and views >= policy["minimum_views_for_retirement"]
        weak_demand = demand.get(service_id) in {0, 1}
        replacement = next((row for row in replacements if isinstance(row, dict)
                            and row.get("replaces_service_id") == service_id), None)
        stronger_paid_demand = bool(
            replacement and type(replacement.get("paid_demand_score")) is int
            and replacement["paid_demand_score"] > 0
        )
        untouched_by_buyers = (inquiries.get(service_id, 0) == 0
                               and payments.get(service_id, 0) == 0
                               and (purchases == 0 or purchases is None))
        duplicates = duplicate_of.get(service_id) if untouched_by_buyers else None
        retire_ready = bool(duplicates) or bool(
            minimum_sample and inquiries.get(service_id, 0) == 0 and purchases == 0
            and payments.get(service_id, 0) == 0 and weak_demand and capacity_pressure
        )
        replace_ready = bool(
            replacement and minimum_sample and untouched_by_buyers and weak_demand
            and (capacity_pressure or stronger_paid_demand)
        )
        recoverable_ready = retire_ready or replace_ready
        gap = gaps.get(service_id)
        if replace_ready:
            action = "REPLACE"
            reason = ("all_replacement_gates_met" if capacity_pressure
                      else "stronger_paid_demand_replaces_zero_purchase_offer")
        elif retire_ready:
            action = "RETIRE"
            reason = (f"duplicate_of_service_{duplicates}" if duplicates
                      else "recoverable_retire_gates_met_without_stronger_candidate")
        elif payments.get(service_id, 0) > 0 or (known and purchases > 0):
            action, reason = "KEEP", "verified_purchase_or_payment"
        elif gap is not None:
            action = "IMPROVE"
            reason = "known_offer_gap" if minimum_sample else "minimum_sample_open_improve_known_gap"
        else:
            action, reason = "KEEP", "insufficient_evidence_for_retirement" if not known else "no_stronger_candidate"
        allocation = {
            "version": 1, "service_id": service_id,
            "listing_version": contract["service_version_sha256"], "action": action,
            "reason": reason, "evidence_cursor": evidence_cursor, "observed_at_epoch": now,
            "metrics": {"views": views, "favorites": favorites, "purchases": purchases,
                        "inquiries": inquiries.get(service_id, 0),
                        "verified_payments": payments.get(service_id, 0),
                        "verified_net_jpy": net.get(service_id, 0.0)},
            "gates": {"metrics_known": known, "minimum_sample_met": minimum_sample,
                      "weak_demand_evidence": weak_demand, "stronger_replacement_candidate": bool(replacement),
                      "slot_capacity_pressure": capacity_pressure,
                      "duplicate_of_service_id": duplicates,
                      "recoverable_retire_gates_met": recoverable_ready},
            "improvement_field": gap.get("field") if gap else None,
            "rollback_version": contract["service_version_sha256"],
            "official_readback_required": action in {"IMPROVE", "RETIRE", "REPLACE"},
        }
        identity = f"storefront:portfolio:v1:{service_id}:{contract['service_version_sha256']}:{evidence_cursor}"
        allocation["allocation_key"] = hashlib.sha256(identity.encode()).hexdigest()
        appended += int(_append_key_once(
            state_dir / "portfolio-allocations.jsonl", "allocation_key", allocation,
        ))
        allocations.append(allocation)
    counts = {name: sum(row["action"] == name for row in allocations)
              for name in ("KEEP", "IMPROVE", "RETIRE", "REPLACE")}
    selected = next((row for row in allocations if row["action"] in {"REPLACE", "RETIRE"}), None)
    if selected is None:
        selected = next((row for service_id in gaps for row in allocations
                         if row["service_id"] == service_id and row["action"] == "IMPROVE"), None)
    if selected is None:
        selected = next((row for row in allocations if row["action"] == "IMPROVE"), None)
    return {"version": 1, "evidence_cursor": evidence_cursor, "service_count": len(allocations),
            "capacity": {"used": len(allocations), "limit": policy["slot_limit"],
                         "pressure": capacity_pressure}, "counts": counts, "appended": appended,
            "selected": selected, "unknown_sources": [value for value in (analytics_error, funnel_error) if value]}


# ---------------------------------------------------------------------------------
# Mutation-contract sealing and validation.
# ---------------------------------------------------------------------------------

MUTATION_FIELDS = {"image", "title", "catchphrase", "body", "package", "FAQ", "price", "listing_state"}
MUTATION_CONTRACT_FIELDS = {
    "version", "platform", "service_id", "precondition_listing_version_sha256",
    "changed_field", "before_value", "proposed_value", "allowed_delta", "rollback_value",
    "official_readback", "success_metric", "observation_window_days", "capability_family",
    "evidence", "contract_sha256",
}
# The provider's listing-state control is its own hidden delta key (the first provider
# adapter's is a `mode` field, not a `data[...]` input). storefront_direct.py's own
# LISTING_STATE_DELTA is the source of truth there and has another caller besides mutation-
# contract validation (`_render_listing_state_mutation`), so it is not moved; this is an
# independent copy of the same value for this module's own validation use.
_LISTING_STATE_DELTA = "mode"


def validate_mutation_contract(
    contract: dict, capability_families: dict[str, str], *,
    platform: str, prohibited_copy_terms: tuple[str, ...] = (),
) -> None:
    unsigned = {key: value for key, value in contract.items() if key != "contract_sha256"}
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    service_id = str(contract.get("service_id") or "")
    allowed_delta = contract.get("allowed_delta")
    evidence = contract.get("evidence")
    delta_ok = (
        isinstance(allowed_delta, list) and len(allowed_delta) == 1
        and isinstance(allowed_delta[0], str)
        and (allowed_delta[0] == _LISTING_STATE_DELTA
             if contract.get("changed_field") == "listing_state"
             else allowed_delta[0].startswith("data["))
    )
    if (set(contract) != MUTATION_CONTRACT_FIELDS or contract.get("version") != 1
            or contract.get("platform") != platform or not service_id.isdigit()
            or capability_families.get(service_id) != contract.get("capability_family")
            or not re.fullmatch(r"[0-9a-f]{64}", str(contract.get("precondition_listing_version_sha256") or ""))
            or contract.get("changed_field") not in MUTATION_FIELDS
            or contract.get("before_value") == contract.get("proposed_value")
            or contract.get("rollback_value") != contract.get("before_value")
            or not delta_ok
            or not isinstance(contract.get("official_readback"), dict) or not contract["official_readback"]
            or not isinstance(contract.get("success_metric"), str) or not contract["success_metric"].strip()
            or type(contract.get("observation_window_days")) is not int
            or contract["observation_window_days"] <= 0
            or not isinstance(evidence, list) or not evidence
            or not all(isinstance(value, str) and value.strip() for value in evidence)
            or contract.get("contract_sha256") != hashlib.sha256(canonical.encode()).hexdigest()):
        raise RuntimeError("storefront_mutation_contract_invalid")
    # A proposal that puts a platform-prohibited term back into a live listing is how the
    # account loses one. The value already on the listing is not judged here; only what this
    # loop would write.
    joined = json.dumps(contract.get("proposed_value"), ensure_ascii=False)
    prohibited = sorted({term for term in prohibited_copy_terms if term in joined})
    if prohibited:
        raise RuntimeError("storefront_copy_names_prohibited_tool:" + ",".join(prohibited))


def seal_mutation_contract(
    unsigned: dict, capability_families: dict[str, str], *,
    platform: str, prohibited_copy_terms: tuple[str, ...] = (),
) -> dict:
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    contract = {**unsigned, "contract_sha256": hashlib.sha256(canonical.encode()).hexdigest()}
    validate_mutation_contract(
        contract, capability_families, platform=platform, prohibited_copy_terms=prohibited_copy_terms,
    )
    return contract


# ---------------------------------------------------------------------------------
# Official search-page demand extraction and scoring.
# ---------------------------------------------------------------------------------

def extract_search_demand(body: str) -> dict:
    """Demand facts an official search page states: result count and reviewed comparables.

    A review on this marketplace can only follow a purchase, so a reviewed comparable is
    evidence that buyers pay for this work. Search cards do not state sales counts, so those
    stay absent rather than being inferred.
    """
    total = re.search(r"([0-9,]+)\s*件中", body)
    comparables = [
        {"rating": float(rating), "review_count": int(review.replace(",", "")),
         "display_price_jpy": int(price.replace(",", ""))}
        for rating, review, price in re.findall(
            r"([0-5]\.[0-9])\s*\n\(([0-9,]+)\)\s*\n([0-9,]+)\s*円", body)
    ]
    return {
        "visible_result_count": int(total.group(1).replace(",", "")) if total else None,
        "comparables": comparables[:12],
    }


def family_market(state_dir: Path, family_name: str) -> dict | None:
    """The public market facts this account has already measured for one capability family.

    Reduces the newest `demand-evidence.jsonl` row naming `family_name` to the price/rating/
    review distribution a proposal is allowed to see and cite -- never the query text, the
    model's own rationale, a competitor's title, or any url beyond `evidence_path` (the local
    JSON file backing the row, not a page the model could read seller wording from). This is
    the same distinction `extract_search_demand`'s docstring draws: what the marketplace states
    as fact versus what a seller or this loop wrote about it.

    Returns None when the family has no row yet, or when the ledger is missing or unreadable --
    `allocate_portfolio` above treats its own ledger reads the same way (via `_jsonl_rows`)
    rather than raising, so an IMPROVE prompt with no measured market still gets built instead
    of failing the wake.
    """
    rows, _ = _jsonl_rows(state_dir / "demand-evidence.jsonl")
    for row in reversed(rows):
        if row.get("capability_family") != family_name:
            continue
        comparables = [
            {"display_price_jpy": comparable.get("display_price_jpy"),
             "rating": comparable.get("rating"), "review_count": comparable.get("review_count")}
            for comparable in row.get("comparables") or [] if isinstance(comparable, dict)
        ]
        return {
            "median_price_jpy": row.get("median_price_jpy"),
            "sold_comparables": row.get("sold_comparables"),
            "reviewed_comparables": row.get("reviewed_comparables"),
            "visible_result_count": row.get("visible_result_count"),
            "evidence_path": row.get("evidence_path"),
            "comparables": comparables,
        }
    return None


def score_demand_cluster(cluster: dict) -> dict:
    """Score one official demand cluster from what the marketplace actually shows.

    Demand is only credited when comparables prove buyers pay: a query with results but
    no sold comparable scores zero rather than being called demand.
    """
    results = cluster.get("visible_result_count")
    comparables = [row for row in cluster.get("comparables") or [] if isinstance(row, dict)]
    sold = [row for row in comparables if type(row.get("sales_count")) is int and row["sales_count"] > 0]
    reviewed = [row for row in comparables if type(row.get("review_count")) is int and row["review_count"] > 0]
    prices = [row["display_price_jpy"] for row in comparables
              if type(row.get("display_price_jpy")) is int and row["display_price_jpy"] > 0]
    if type(results) is not int or not comparables:
        return {"status": "unknown", "reason": "official_demand_evidence_incomplete", "score": None}
    return {
        "status": "known",
        "score": len(sold) * 3 + len(reviewed),
        "visible_result_count": results,
        "sold_comparables": len(sold),
        "reviewed_comparables": len(reviewed),
        "median_price_jpy": sorted(prices)[len(prices) // 2] if prices else None,
    }


# ---------------------------------------------------------------------------------
# Replace-plan rendering (one atomic RETIRE-then-CREATE pairing).
# ---------------------------------------------------------------------------------

def render_replace_plan(
    retire_contract: dict, create_contract: dict | None, allocation: dict, *, platform: str,
) -> dict:
    """One atomic REPLACE: free the slot recoverably, then fill it, or restore the old listing.

    The replacement contract must already exist before anything is retired, so a failed
    creation can never leave the portfolio with an empty slot and no way back.
    """
    if allocation.get("action") != "REPLACE":
        raise RuntimeError("storefront_replace_allocation_invalid")
    if create_contract is None:
        raise RuntimeError("storefront_replace_without_ready_candidate")
    retired_id = str(retire_contract.get("service_id") or "")
    created_id = str(create_contract.get("draft_service_id") or "")
    if (retire_contract.get("changed_field") != "listing_state"
            or retired_id != str(allocation.get("service_id") or "")
            or not created_id.isdigit() or created_id == retired_id):
        raise RuntimeError("storefront_replace_identity_invalid")
    unsigned = {
        "version": 1, "platform": platform, "action": "REPLACE",
        "allocation_key": allocation["allocation_key"],
        "retired_service_id": retired_id, "created_service_id": created_id,
        "sequence": ["retire", "create"],
        "retire_contract_sha256": retire_contract["contract_sha256"],
        "create_contract_sha256": create_contract["contract_sha256"],
        "official_readback": {
            "retired": retire_contract["official_readback"],
            "created": {"public_url": create_contract["expected_public_url"]},
        },
        "rollback": {"republish_service_id": retired_id,
                     "restore_to": retire_contract["rollback_value"]["listing_state"],
                     "on": "create_failed_after_retire"},
    }
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**unsigned, "plan_sha256": hashlib.sha256(canonical.encode()).hexdigest()}


# ---------------------------------------------------------------------------------
# In-flight draft recovery.
#
# `observed_deleted_draft_ids` is accepted as a callable rather than read here: the provider
# adapter owns the evidence-directory scan (and the adapter's own tests monkeypatch it), so
# this module takes it as a dependency instead of importing or duplicating that scan.
# ---------------------------------------------------------------------------------

def families_with_unpublished_drafts(
    state_dir: Path, inventory_ids: set[str], *,
    observed_deleted_draft_ids: Callable[[Path], set[str]],
    live_draft_ids: set[str] | None = None,
) -> dict[str, tuple[str, int]]:
    """Map every capability family to the draft it already has in flight, if any.

    A draft is built over more than one wake -- the blank draft is created, then filled, then
    published -- because a wake spends exactly one effect. So a family can be two thirds of the
    way to a listing while its most recent proposals were still being refused, and abandoning
    the demand cluster then throws that real draft away. The conditions are the same ones the
    create path already uses to offer a draft back for reuse.

    Each value is `(draft_id, first_seen_index)`. `first_seen_index` is the row's position in
    the append-only ledger the first time that draft id appears there -- the ledger carries no
    per-row timestamp, but earlier lines were always appended in earlier wakes, so this stands
    in for "how long has this draft been waiting" when more than one family has one in flight.

    Reads the ledger once, however many families are checked, rather than re-reading it per
    family: the file is scanned newest-first exactly once, and a family's answer is fixed the
    first time (i.e. the most recent time) a row for it satisfies the conditions -- the same
    result the old per-family reversed scan gave, one family at a time.
    """
    ledger = state_dir / "new-listing-drafts.jsonl"
    if not ledger.is_file():
        return {}
    deleted = observed_deleted_draft_ids(state_dir / "evidence")
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    first_seen_index: dict[str, int] = {}
    for index, row in enumerate(rows):
        first_seen_index.setdefault(str(row.get("draft_service_id") or ""), index)
    # The ledger outlives the drafts it describes. A draft deleted on an earlier wake leaves
    # its row behind as soon as the evidence directory naming that deletion is collected, and
    # `observed_deleted_draft_ids` can only report deletions it can still see. Four such rows
    # were live in production, and because the caller prefers the longest-waiting draft, the
    # stalest row -- the one most likely to name something that no longer exists -- won every
    # time. When the caller can say which drafts the seller's own card census shows, that
    # census decides; without it the ledger is all there is and the old behaviour stands.
    result: dict[str, tuple[str, int]] = {}
    for row in reversed(rows):
        family = row.get("capability_family")
        if not isinstance(family, str) or family in result:
            continue
        draft_id = str(row.get("draft_service_id") or "")
        if (draft_id.isdigit() and draft_id not in inventory_ids and draft_id not in deleted
                and (live_draft_ids is None or draft_id in live_draft_ids)
                and int(row.get("public_effect") or 0) == 0
                and row.get("status") in {"draft_created", "prepared"}):
            result[family] = (draft_id, first_seen_index[draft_id])
    return result


def family_has_unpublished_draft(
    state_dir: Path, family_name: str, inventory_ids: set[str], *,
    observed_deleted_draft_ids: Callable[[Path], set[str]],
) -> str | None:
    """Name the draft `family_name` already has in flight, if any.

    Thin wrapper around `families_with_unpublished_drafts` for the single-family call sites;
    see that function for the conditions and the reasoning behind them.
    """
    match = families_with_unpublished_drafts(
        state_dir, inventory_ids, observed_deleted_draft_ids=observed_deleted_draft_ids,
    ).get(family_name)
    return match[0] if match is not None else None


def _healed_subscription(contract: dict) -> dict:
    """Recompute a create contract's subscription pair from its own recorded intent.

    A contract sealed before the `can_subscribe`/`discount_ratio` pairing fix (or one that
    otherwise drifted) can sit in `generated-create-contract.json` with a subscription that no
    longer matches its own `recurring_support_included` flag -- draft 4385273 kept that stale
    `{enabled: True, discount_ratio: "5"}` pair for mobile_app_dev, a family whose category offers
    no subscription, so every recovered wake resubmitted the same rejected pair. Deriving the
    pair fresh from `recurring_support_included` every time a contract is recovered, instead of
    trusting whatever was baked in at seal time, means any future stale draft heals itself on the
    next wake rather than needing a one-off manual correction.
    """
    wants_recurring = bool((contract.get("capability_evidence") or {}).get("recurring_support_included"))
    return {"enabled": True, "discount_ratio": "5"} if wants_recurring else {"enabled": False, "discount_ratio": "0"}


def reseal_healed_contract(contract: dict) -> dict:
    if not isinstance(contract.get("subscription"), dict):
        return contract  # not a full create contract shape; nothing to heal
    healed = _healed_subscription(contract)
    if contract.get("subscription") == healed:
        return contract
    corrected = {**contract, "subscription": healed}
    unsigned = {key: value for key, value in corrected.items()
                if key not in {"contract_sha256", "hero_image"}}
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**corrected, "contract_sha256": hashlib.sha256(canonical.encode()).hexdigest()}


def recover_prepared_create_contract(
    state_dir: Path, family_name: str, demand_evidence_path: str, *,
    observed_deleted_draft_ids: Callable[[Path], set[str]],
) -> dict | None:
    wakes = state_dir / "wakes.jsonl"
    if not wakes.is_file():
        return None
    # A draft this loop has since deleted must never be recovered again: its evidence still
    # satisfies every integrity check below, but the URL it names no longer exists, so reusing
    # it would trade one stuck loop for another instead of letting a genuinely blank draft take
    # its place.
    deleted_draft_ids = observed_deleted_draft_ids(state_dir / "evidence")
    for line in reversed(wakes.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        draft = row.get("new_listing_draft") if isinstance(row.get("new_listing_draft"), dict) else {}
        # `draft_created` is accepted alongside `prepared` because a draft created before a
        # wake could fill and publish in one pass never reaches `prepared`, so its sealed
        # contract was never offered back and every later wake generated a fresh proposal and
        # re-rolled the dice against every content guard. Draft 4387924 sat filled and
        # unpublished through three such rounds. The contract is re-validated below either way,
        # so accepting the earlier stage widens what can be recovered, not what can be trusted.
        stage = draft.get("status")
        # A prepared draft was read back, so that readback is still required of it. A
        # draft_created row is from before the form was filled and has none to require --
        # dropping the check for both stages would have quietly weakened the older path.
        if (row.get("status") != "completed"
                or stage not in {"prepared", "draft_created"}
                or (stage == "prepared" and int(draft.get("readback") or 0) != 1)
                or int(draft.get("public_effect") or 0) != 0
                or draft.get("capability_family") != family_name
                or str(draft.get("demand_evidence_path") or "") != demand_evidence_path
                or str(draft.get("draft_service_id") or "") in deleted_draft_ids):
            continue
        path = state_dir / "evidence" / str(row.get("pass_id") or "") / "generated-create-contract.json"
        try:
            contract = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        digest = str(contract.get("contract_sha256") or "")
        unsigned = {
            key: value for key, value in contract.items()
            if key not in {"contract_sha256", "hero_image"}
        }
        expected = hashlib.sha256(json.dumps(
            unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        # A contract sealed before facet groups were discovered per category never carries a
        # "facets" key at all: it inherited whichever facet ids the source listing's own family
        # happened to use, silently wrong for any other category. Recovering it verbatim would
        # re-fail the exact publish error this key exists to prevent, so it is regenerated
        # instead of reused.
        if "facets" not in (contract.get("category_specific") or {}):
            continue
        if (digest == expected == draft.get("contract_sha256")
                and str(contract.get("draft_service_id") or "") == str(draft.get("draft_service_id") or "")):
            # Heal after verifying the file matches what this loop actually recorded, so a
            # tampered or corrupted contract still fails closed above -- only a genuine, intact
            # contract gets its subscription pair recomputed here.
            return reseal_healed_contract(contract)
    return None


# ---------------------------------------------------------------------------------
# Proposal-rejection guard: three strikes from the same guard stalls a gap.
# ---------------------------------------------------------------------------------

def append_proposal_rejection(
    state_dir: Path, *, gap_key: str, rejection: str, proposed_value: object, pass_id: str,
) -> None:
    """Persist one rejected proposal so a later wake's prompt can see why it failed.

    Unlike `_append_key_once`, every rejection is a distinct event: the whole point is that a
    gap can be rejected more than once, for the same or a different reason, and the three-strike
    check needs all of the recent ones -- deduplicating on gap_key would keep only the first.
    """
    _append(state_dir / "proposal-rejections.jsonl", {
        "version": 1, "gap_key": gap_key, "rejection": str(rejection)[:160],
        "proposed_value": proposed_value, "observed_at_epoch": int(time.time()), "pass_id": pass_id,
    })


def recent_proposal_rejections(state_dir: Path, gap_key: str) -> list[dict]:
    """Return up to the 3 most recent rejections recorded for gap_key, newest last."""
    path = state_dir / "proposal-rejections.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"{path.stem}_ledger_invalid") from error
        if row.get("gap_key") == gap_key:
            rows.append(row)
    return rows[-3:]


def rejection_guard_name(rejection: object) -> str:
    """The guard identity is the text before the first `:`, e.g. the RuntimeError's own message
    prefix. Two prohibited-term rejections naming different terms are the same guard finding
    two different terms, not two different guards."""
    return str(rejection or "").split(":", 1)[0]


def three_strike_same_guard(
    rejections: list[dict], *, since_epoch: int | None = None,
) -> str | None:
    """Name the guard if the 3 most recent rejections for a gap all came from it, else None.

    A rejection is evidence that the generator, as it was configured then, kept producing
    something a guard refuses. It stops being evidence once that configuration changes. The
    title guard refused `line_bot_dev` three times, and all three predated the two prompt
    changes that taught the model the shapes it was getting wrong -- so the gap was closed
    permanently on the strength of a claim that had already been answered, and the filled
    draft behind it could never be finished.

    `since_epoch` is the moment the running configuration began, normally when its release
    was cut. Rejections older than that describe a generator that no longer exists and are
    not counted, which makes shipping a fix the thing that clears the count. Without it the
    old behaviour stands, because a caller that cannot say when its configuration changed
    has no basis for discarding evidence.
    """
    if since_epoch is not None:
        rejections = [row for row in rejections
                      if int(row.get("observed_at_epoch") or 0) >= since_epoch]
    if len(rejections) < 3:
        return None
    guards = {rejection_guard_name(row.get("rejection")) for row in rejections}
    return next(iter(guards)) if len(guards) == 1 else None
