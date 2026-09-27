"""Pure account-manifest product binding for publication identity rows.

The module deliberately has no network or state-write path.  Product/account
registries are read as deterministic JSON fixtures and publication rows are
returned as defensive copies.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gates"))
from product_router import canonical_product_id  # noqa: E402


UNMAPPED_REASON = "account_manifest_integration_unmapped"
BINDING_SOURCE = "account_manifest.publisher_integration_id"


def _manifest_objects(path: Path) -> Iterator[tuple[Path, dict[str, Any]]]:
    """Yield sorted JSON manifest objects, rejecting malformed registry files."""

    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"registry directory missing: {root}")
    for manifest_path in sorted(root.glob("*.json"), key=lambda item: item.name):
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON manifest: {manifest_path}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"manifest object required: {manifest_path}")
        yield manifest_path, value


def _required_id(manifest: dict[str, Any], field: str, path: Path) -> str:
    value = manifest.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {field}: {path}")
    return value


def load_product_ids(path: Path) -> set[str]:
    """Load the registered product IDs from sorted ``*.json`` manifests."""

    product_ids: set[str] = set()
    for manifest_path, manifest in _manifest_objects(path):
        product_ids.add(_required_id(manifest, "product_id", manifest_path))
    return product_ids


def load_account_bindings(path: Path, product_ids: set[str]) -> dict[str, dict[str, str]]:
    """Build an exact integration-ID to account/product index.

    A null or omitted publisher integration is intentionally not indexed.  A
    repeated integration is accepted only when the complete account/product
    mapping is identical; any conflicting duplicate fails closed.
    """

    registered_products = set(product_ids)
    bindings: dict[str, dict[str, str]] = {}
    for manifest_path, manifest in _manifest_objects(path):
        account_id = _required_id(manifest, "account_id", manifest_path)
        product_id = _required_id(manifest, "product_id", manifest_path)
        if product_id not in registered_products:
            raise ValueError(f"unknown product_id {product_id!r}: {manifest_path}")

        integration = manifest.get("publisher_integration_id")
        if integration is None:
            continue
        if not isinstance(integration, str) or not integration.strip():
            raise ValueError(f"invalid publisher_integration_id: {manifest_path}")

        mapping = {"account_id": account_id, "product_id": product_id}
        previous = bindings.get(integration)
        if previous is not None and previous != mapping:
            raise ValueError(f"conflicting duplicate integration mapping: {integration}")
        bindings[integration] = mapping

    return {integration: bindings[integration] for integration in sorted(bindings)}


def bind_product_ids(
    rows: list[dict], bindings: dict[str, dict[str, str]]
) -> tuple[list[dict], dict]:
    """Bind publication rows by exact integration ID, without mutating inputs."""

    outputs: list[dict[str, Any]] = []
    report = {"rows": len(rows), "bound": 0, "unmapped": 0, "already_bound": 0}

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("publication row object required")
        output = copy.deepcopy(row)
        mapping = bindings.get(str(row.get("integration_id") or ""))
        if mapping is None:
            output["product_id"] = None
            output["product_id_null_reason"] = UNMAPPED_REASON
            report["unmapped"] += 1
        else:
            existing = output.get("product_id")
            if existing is not None and canonical_product_id(existing) != mapping["product_id"]:
                raise ValueError("publication product binding conflict")
            output["account_id"] = mapping["account_id"]
            output["product_id"] = mapping["product_id"]
            output["product_id_null_reason"] = None
            output["product_binding_source"] = BINDING_SOURCE
            report["bound"] += 1
            if canonical_product_id(existing) == mapping["product_id"]:
                report["already_bound"] += 1
        outputs.append(output)

    return outputs, report
