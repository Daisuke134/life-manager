#!/usr/bin/env python3
"""S001 study-ID-only SocSci210 split audit. No participant responses are read.

Repository policy: do not download SocSci210 survey/participant rows while the
per-study license, research consent, and data-governance permissions are HOLD.
This script downloads just a 1710-byte, public study-ID split mapping, validates
it, and writes only aggregate metadata; IDs remain ephemeral in memory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

PINNED_DATASET_REVISION = "048481111a4425ed83dc0eacf15f8431f252b21a"
MAPPING_RELATIVE_PATH = "metadata/participant_mapping.json"
MAPPING_URL = (
    "https://huggingface.co/datasets/socratesft/SocSci210/resolve/"
    + PINNED_DATASET_REVISION + "/" + MAPPING_RELATIVE_PATH
)
EXPECTED_BLOB_SHA1 = "8aa37bd598ce8bb00103a5a885948299f75f5ce7"
EXPECTED_BYTES = 1710
EXPECTED_STUDIES = {"seen": 170, "unseen": 40}
_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def git_blob_sha(data: bytes) -> str:
    """Git SHA1 includes the blob envelope, unlike ordinary SHA1(data)."""
    if not isinstance(data, bytes):
        raise TypeError("bytes required")
    return hashlib.sha1(("blob " + str(len(data))).encode("ascii") + bytes([0]) + data).hexdigest()


def inspect_study_mapping(
    payload: bytes, *, expected_blob: str = EXPECTED_BLOB_SHA1,
    expected_bytes: int = EXPECTED_BYTES,
    expected_studies: dict[str, int] | None = None,
) -> dict:
    """Fail closed and emit scalar metadata, never study IDs or respondent rows."""
    counts = EXPECTED_STUDIES if expected_studies is None else expected_studies
    if type(payload) is not bytes or len(payload) != expected_bytes:
        raise ValueError("pinned split byte count mismatch")
    actual_sha = git_blob_sha(payload)
    if actual_sha != expected_blob:
        raise ValueError("pinned split Git blob SHA mismatch")
    try:
        mapping = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid study-level metadata JSON") from exc
    if not isinstance(mapping, dict) or set(mapping) != {"seen", "unseen"}:
        raise ValueError("only seen/unseen study-id arrays are allowed")
    for key in ("seen", "unseen"):
        items = mapping[key]
        if not isinstance(items, list) or any(
            type(item) is not str or _ID.fullmatch(item) is None for item in items
        ):
            raise ValueError("bad study IDs; never accept participant data")
        if len(items) != len(set(items)) or len(items) != counts[key]:
            raise ValueError("duplicate or wrong split study count")
    overlap = len(set(mapping["seen"]) & set(mapping["unseen"]))
    if overlap:
        raise ValueError("leakage: study appears in training and unseen evaluation")
    return {
        "schema": "manager.socsci210.study-metadata-audit.v1",
        "source_dataset": "socratesft/SocSci210",
        "source_revision": PINNED_DATASET_REVISION,
        "source_path": MAPPING_RELATIVE_PATH,
        "content_git_blob_sha1": actual_sha,
        "file_bytes": len(payload),
        "seen_studies": len(mapping["seen"]),
        "unseen_studies": len(mapping["unseen"]),
        "total_studies": sum(len(mapping[k]) for k in ("seen", "unseen")),
        "overlap": overlap,
        "respondent_data_loaded": False,
        "study_ids_serialized": False,
        "socsci_response_model_evaluation": "NOT_PERFORMED",
        "privacy_rights_for_source_studies": "HOLD",
        "source_reference": MAPPING_URL,
    }


def audit_remote() -> dict:
    request = Request(MAPPING_URL, headers={"User-Agent": "Manager-Metadata-Only-Research/1.0"})
    with urlopen(request, timeout=25) as resp:
        data = resp.read(EXPECTED_BYTES + 1)
    return inspect_study_mapping(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_remote()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "s001_aggregate.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
