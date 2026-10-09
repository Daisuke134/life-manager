"""Operator-authored diagnostic limits. No free-space admission thresholds."""
from dataclasses import dataclass, fields
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class StoragePolicy:
    owner_id: str
    diagnostic_segment_bytes: int
    diagnostic_backup_count: int
    chunk_bytes: int
    head_bytes: int
    metadata_max_bytes: int
    structured_record_max_bytes: int
    owner_diagnostic_retained_bytes: int
    host_diagnostic_retained_bytes: int


def load_storage_policy(path: Path, owner_id: str) -> StoragePolicy | None:
    if not isinstance(owner_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", owner_id):
        raise ValueError("invalid storage owner")
    path = Path(path)
    if path.is_symlink():
        raise ValueError("storage policy symlink")
    value = json.loads(path.read_text())
    names = {f.name for f in fields(StoragePolicy)} - {"owner_id"}
    if (not isinstance(value, dict) or set(value) != {"version", "defaults", "owners"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["defaults"], dict) or set(value["defaults"]) != names
            or not isinstance(value["owners"], dict)):
        raise ValueError("invalid storage policy shape")
    for override in value["owners"].values():
        if not isinstance(override, dict) or set(override) - names:
            raise ValueError("invalid storage owner override")
    limits = {**value["defaults"], **value["owners"].get(owner_id, {})}
    if any(type(v) is not int or v <= 0 for v in limits.values()):
        raise ValueError("storage limits must be positive integers")
    if limits["chunk_bytes"] > limits["diagnostic_segment_bytes"]:
        raise ValueError("storage chunk exceeds segment")
    registry = json.loads((path.parent / "loop-registry.json").read_text())
    if owner_id not in registry["loops"]:
        return None
    limits["owner_diagnostic_retained_bytes"] = min(limits["owner_diagnostic_retained_bytes"],
        max(1, value["defaults"]["host_diagnostic_retained_bytes"] // max(1, len(registry["loops"]))))
    return StoragePolicy(owner_id=owner_id, **limits)
