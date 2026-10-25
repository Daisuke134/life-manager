"""Build and validate the catalog-only EBA v1 source manifest.

The 90 upstream records are a literature/system landscape, not 90 compatible
benchmark runs. This module deliberately leaves rights, task mappings, scores,
and human outcomes unresolved until each is established with separate evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


MANAGER_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = MANAGER_ROOT / "docs/research/evals/EVAL_LANDSCAPE_20261022.json"
MANIFEST_PATH = MANAGER_ROOT / "experiments/behavior-model/eba-v1-manifest.json"
INVENTORY_SHA256 = "a57feea7c2e96b90d6e9b664346224d756ef59da0e4b3a37857609c0c60bb634"
INVENTORY_COUNT = 90
SCHEMA = "manager.eba.catalog.v1"

DIMENSIONS: tuple[dict[str, str], ...] = (
    {
        "id": "forecast",
        "name": "EBA-Forecast",
        "definition": "Predict outcomes or event probabilities at a frozen forecast time; report proper scores and calibration.",
    },
    {
        "id": "sim",
        "name": "EBA-Sim",
        "definition": "Reproduce population distributions and subgroup structure without access to future labels.",
    },
    {
        "id": "intervention",
        "name": "EBA-Intervention",
        "definition": "Predict differences caused by interventions only where a credible identified contrast exists.",
    },
    {
        "id": "decision",
        "name": "EBA-Decision",
        "definition": "Compare actions under uncertainty, budgets, permissions, harm constraints, and a valid NO_ACTION option.",
    },
    {
        "id": "execution",
        "name": "EBA-Execution",
        "definition": "Verify bounded authorized actions against independent external state and attributable receipts.",
    },
    {
        "id": "welfare",
        "name": "EBA-Welfare",
        "definition": "Measure consented human outcomes, burden, and adverse events against a credible comparator.",
    },
    {
        "id": "generalization",
        "name": "EBA-Generalization",
        "definition": "Test replication across populations, sites, operators, and time, including subgroup harm and spillovers.",
    },
)


class EbaManifestError(ValueError):
    """A stable, testable EBA manifest contract violation."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject_constant(_value: str) -> None:
    raise EbaManifestError("INVALID_JSON_CONSTANT")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EbaManifestError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _load_json(data: bytes) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except EbaManifestError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise EbaManifestError("INVALID_JSON") from None


def _dimension_record(dimension: dict[str, str]) -> dict[str, Any]:
    return {
        **dimension,
        "candidate_ids": [],
        "mapping_status": "NOT_REVIEWED",
        "status": "NOT_RUN",
        "score": None,
        "score_unit": None,
    }


def _candidate_record(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": source["id"],
        "source": source,
        "catalog_status": "CANDIDATE_ONLY",
        "upstream_version": None,
        "version_status": "NOT_PINNED",
        "rights_clearance": "NOT_VERIFIED",
        "population": None,
        "population_status": "NOT_DOCUMENTED_IN_CATALOG",
        "unit": None,
        "unit_status": "NOT_DOCUMENTED_IN_CATALOG",
        "labels": None,
        "labels_status": "NOT_DOCUMENTED_IN_CATALOG",
        "holdout": None,
        "holdout_status": "NOT_DOCUMENTED_IN_CATALOG",
        "metric": source.get("metric"),
        "metric_status": "SOURCE_DESCRIPTION_UNVERIFIED",
        "dimension_ids": [],
        "mapping_status": "NOT_REVIEWED",
        "execution_status": "NOT_RUN",
        "score": None,
        "human_outcome": "NOT_MEASURED",
        "unmeasured": [source["does_not_prove"]],
    }


def build_catalog(inventory_bytes: bytes) -> dict[str, Any]:
    """Create a deterministic catalog from the exact pinned source inventory."""
    digest = hashlib.sha256(inventory_bytes).hexdigest()
    if digest != INVENTORY_SHA256:
        raise EbaManifestError("SOURCE_HASH_MISMATCH")
    inventory = _load_json(inventory_bytes)
    if not isinstance(inventory, list) or len(inventory) != INVENTORY_COUNT:
        raise EbaManifestError("SOURCE_INVENTORY_SHAPE_MISMATCH")
    ids = [item.get("id") for item in inventory if isinstance(item, dict)]
    if len(ids) != INVENTORY_COUNT or any(not isinstance(item, str) or not item for item in ids):
        raise EbaManifestError("INVALID_SOURCE_ID")
    if len(set(ids)) != INVENTORY_COUNT:
        raise EbaManifestError("DUPLICATE_SOURCE_ID")
    if any(not isinstance(item.get("does_not_prove"), str) for item in inventory):
        raise EbaManifestError("SOURCE_LIMITATION_MISSING")

    return {
        "schema": SCHEMA,
        "status": "CATALOG_ONLY_NOT_BENCHMARK",
        "source_inventory": {
            "path": "docs/research/evals/EVAL_LANDSCAPE_20261022.json",
            "sha256": digest,
            "candidate_count": INVENTORY_COUNT,
            "interpretation": "A source-backed candidate landscape; entries are not runs or mutually comparable evaluations.",
        },
        "claim_limits": {
            "global_score": None,
            "missingness": "UNKNOWN_NOT_ZERO",
            "human_outcome": "NOT_MEASURED",
            "rights_clearance": "NOT_VERIFIED",
            "interpretation": "No benchmark result, model ranking, intervention effect, or beneficiary outcome is established by this catalog.",
        },
        "dimensions": [_dimension_record(item) for item in DIMENSIONS],
        "candidates": [_candidate_record(item) for item in inventory],
    }


def validate_catalog(document: Any, inventory_bytes: bytes) -> None:
    """Validate source linkage and enforce honest, unscored catalog semantics."""
    digest = hashlib.sha256(inventory_bytes).hexdigest()
    if digest != INVENTORY_SHA256:
        raise EbaManifestError("SOURCE_HASH_MISMATCH")
    expected = build_catalog(inventory_bytes)
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise EbaManifestError("INVALID_MANIFEST_SCHEMA")
    if document.get("status") != "CATALOG_ONLY_NOT_BENCHMARK":
        raise EbaManifestError("INVALID_CATALOG_STATUS")

    source_inventory = document.get("source_inventory")
    if not isinstance(source_inventory, dict) or source_inventory.get("sha256") != digest:
        raise EbaManifestError("SOURCE_HASH_MISMATCH")
    if source_inventory != expected["source_inventory"]:
        raise EbaManifestError("SOURCE_INVENTORY_METADATA_MISMATCH")

    claim_limits = document.get("claim_limits")
    if not isinstance(claim_limits, dict):
        raise EbaManifestError("INVALID_CLAIM_LIMITS")
    if claim_limits.get("global_score") is not None:
        raise EbaManifestError("GLOBAL_SCORE_FORBIDDEN")
    if claim_limits != expected["claim_limits"]:
        raise EbaManifestError("CLAIM_LIMITS_MISMATCH")

    dimensions = document.get("dimensions")
    if not isinstance(dimensions, list) or len(dimensions) != len(DIMENSIONS):
        raise EbaManifestError("DIMENSION_SET_MISMATCH")
    if [item.get("id") if isinstance(item, dict) else None for item in dimensions] != [
        item["id"] for item in DIMENSIONS
    ]:
        raise EbaManifestError("DIMENSION_SET_MISMATCH")
    if dimensions != expected["dimensions"]:
        if any(isinstance(item, dict) and item.get("score") is not None for item in dimensions):
            raise EbaManifestError("SCORE_WHILE_NOT_RUN")
        raise EbaManifestError("UNREVIEWED_DIMENSION_MAPPING")

    candidates = document.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != INVENTORY_COUNT:
        raise EbaManifestError("CANDIDATE_SET_MISMATCH")
    candidate_ids = [item.get("id") if isinstance(item, dict) else None for item in candidates]
    if any(not isinstance(item, str) or not item for item in candidate_ids):
        raise EbaManifestError("INVALID_CANDIDATE_ID")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise EbaManifestError("DUPLICATE_CANDIDATE_ID")
    expected_ids = [item["id"] for item in expected["candidates"]]
    if candidate_ids != expected_ids:
        raise EbaManifestError("CANDIDATE_SET_MISMATCH")

    for candidate, expected_candidate in zip(candidates, expected["candidates"], strict=True):
        if not isinstance(candidate, dict):
            raise EbaManifestError("INVALID_CANDIDATE")
        if candidate.get("source") != expected_candidate["source"]:
            raise EbaManifestError("SOURCE_RECORD_MISMATCH")
        if candidate.get("rights_clearance") != "NOT_VERIFIED":
            raise EbaManifestError("RIGHTS_NOT_VERIFIED")
        if candidate.get("version_status") != "NOT_PINNED":
            raise EbaManifestError("VERSION_NOT_PINNED")
        if candidate.get("dimension_ids") != [] or candidate.get("mapping_status") != "NOT_REVIEWED":
            raise EbaManifestError("UNREVIEWED_DIMENSION_MAPPING")
        if candidate.get("execution_status") != "NOT_RUN" or candidate.get("score") is not None:
            raise EbaManifestError("SCORE_WHILE_NOT_RUN")
        if candidate != expected_candidate:
            raise EbaManifestError("CANDIDATE_METADATA_MISMATCH")

    if document != expected:
        raise EbaManifestError("MANIFEST_CONTENT_MISMATCH")


def _serialize(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Regenerate the checked-in catalog manifest.")
    mode.add_argument("--check", action="store_true", help="Verify source pin and deterministic manifest bytes.")
    args = parser.parse_args(argv)

    try:
        inventory_bytes = INVENTORY_PATH.read_bytes()
        expected = build_catalog(inventory_bytes)
        validate_catalog(expected, inventory_bytes)
        expected_bytes = _serialize(expected)
        if args.write:
            MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST_PATH.write_bytes(expected_bytes)
            print(f"EBA catalog written: {MANIFEST_PATH.relative_to(MANAGER_ROOT)}")
            return 0
        actual_bytes = MANIFEST_PATH.read_bytes()
        validate_catalog(_load_json(actual_bytes), inventory_bytes)
        if actual_bytes != expected_bytes:
            raise EbaManifestError("MANIFEST_NOT_REPRODUCIBLE")
        print(f"EBA catalog PASS: {INVENTORY_COUNT} candidates; 7 dimensions; scores NOT_RUN")
        return 0
    except OSError as exc:
        print(f"EBA catalog ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1
    except EbaManifestError as exc:
        print(f"EBA catalog ERROR: {exc.code}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
