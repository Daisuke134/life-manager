#!/usr/bin/env python3
"""Append a model-decided external effect to a durable project ledger."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


REQUIRED = ("effect_key", "target", "payload_sha256", "official_receipt_url",
            "exact_readback", "quality_status", "qualification_sources", "semantic_contract_sha256")


def valid_checkpoint(value: object) -> bool:
    return (
        isinstance(value, dict)
        and all(key in value for key in REQUIRED)
        and all(str(value[key]).strip() for key in (
            "effect_key", "target", "payload_sha256", "official_receipt_url",
        ))
        and value["exact_readback"] is True
        and value["quality_status"] in {"qualified", "qualification", "invalid"}
        and isinstance(value["qualification_sources"], list)
        and len(str(value["semantic_contract_sha256"])) == 64
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--effect-json", required=True, type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    source = args.effect_json.resolve()
    if root not in source.parents or source.is_symlink() or not source.is_file():
        raise SystemExit("effect JSON must be a regular project-owned file")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not valid_checkpoint(value):
        raise SystemExit("invalid effect checkpoint")
    ledger = root / "delivery" / "paid-remote-progress.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if ledger.is_file():
        existing = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    matches = [row for row in existing if row.get("effect_key") == value["effect_key"]]
    revision = value.get("classification_revision") is True
    if matches and not revision:
        print(json.dumps({"status": "already_checkpointed", "effect_key": value["effect_key"]}))
        return 0
    if revision:
        if not matches or not str(value.get("revision_reason") or "").strip():
            raise SystemExit("classification revision requires an existing effect and reason")
        prior = matches[-1]
        immutable = ("target", "payload_sha256", "official_receipt_url", "exact_readback",
                     "semantic_contract_sha256")
        if any(value.get(key) != prior.get(key) for key in immutable):
            raise SystemExit("classification revision cannot change effect identity")
        value["record_type"] = "classification_revision"
    elif matches:
        raise SystemExit("duplicate effect checkpoint")
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps({"status": "classification_revised" if revision else "checkpointed",
                      "effect_key": value["effect_key"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
