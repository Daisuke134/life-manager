#!/usr/bin/env python3
"""Pinned, aggregate-only HeartSteps source inspection for H002-H004.

This script downloads one public CSV into a temporary directory, verifies the
pinned Git blob and byte size, then writes aggregate metadata only. It does not
persist or print participant rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable
from urllib.request import Request, urlopen

SOURCE_COMMIT = "3016391de426116bdef41880d72bc8cd4b9b2477"
SOURCE_PATH = "data_files/suggestions.csv"
SOURCE_URL = (
    "https://raw.githubusercontent.com/klasnja/HeartStepsV1/"
    f"{SOURCE_COMMIT}/{SOURCE_PATH}"
)
EXPECTED_GIT_BLOB_SHA1 = "67a55efd4d79e1f5646bdb26277f37ec988e2403"
EXPECTED_BYTES = 4_371_854
EXPECTED_ROWS = 8_274
EXPECTED_README_COLUMNS = 86

MISSING_TOKENS = {"", "NA", "NaN", "nan", "N/A", "NULL", "null"}
SAFE_VALUE_COUNT_COLUMNS = (
    "avail", "is.randomized", "send", "send.active", "send.sedentary",
)
CANDIDATE_COLUMNS = (
    "user.index", "decision.index", "decision.index.nogap", "study.day.nogap",
    "sugg.decision.utime", "avail", "is.randomized", "send", "send.active",
    "send.sedentary", "jbsteps30", "jbsteps30.zero", "jbsteps30pre",
    "jbsteps30pre.zero",
)


def git_blob_sha1(payload: bytes) -> str:
    envelope = f"blob {len(payload)}\0".encode("ascii") + payload
    return hashlib.sha1(envelope).hexdigest()


def download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "Anicca-Manager-Research/1.0"})
    with urlopen(request, timeout=120) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def validate_source(path: Path, expected_bytes: int, expected_blob_sha1: str) -> dict:
    payload = path.read_bytes()
    if len(payload) != expected_bytes:
        raise ValueError(f"byte size mismatch: expected {expected_bytes}, got {len(payload)}")
    actual_blob = git_blob_sha1(payload)
    if actual_blob != expected_blob_sha1:
        raise ValueError(f"Git blob mismatch: expected {expected_blob_sha1}, got {actual_blob}")
    return {"bytes": len(payload), "git_blob_sha1": actual_blob,
            "sha256": hashlib.sha256(payload).hexdigest()}


def _is_missing(value: str | None) -> bool:
    return value is None or value.strip() in MISSING_TOKENS


def inspect_csv(path: Path) -> dict:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise ValueError("CSV is empty") from exc
        if not headers or any(not h for h in headers):
            raise ValueError("blank header")
        if len(set(headers)) != len(headers):
            raise ValueError("duplicate headers")
        index = {name: position for position, name in enumerate(headers)}
        missing_counts = {name: 0 for name in headers}
        value_counts = {name: {} for name in SAFE_VALUE_COUNT_COLUMNS if name in index}
        row_count = malformed_rows = 0
        for row in reader:
            row_count += 1
            if len(row) != len(headers):
                malformed_rows += 1
                continue
            for position, name in enumerate(headers):
                if _is_missing(row[position]):
                    missing_counts[name] += 1
            for name, counts in value_counts.items():
                value = row[index[name]].strip()
                normalized = "<MISSING>" if _is_missing(value) else value
                counts[normalized] = counts.get(normalized, 0) + 1
    return {
        "row_count": row_count, "column_count": len(headers), "headers": headers,
        "missing_counts": missing_counts,
        "value_counts": {name: dict(sorted(counts.items())) for name, counts in value_counts.items()},
        "malformed_rows": malformed_rows,
    }


def check_candidate_columns(headers: Iterable[str]) -> dict:
    present_set = set(headers)
    present = {name: name in present_set for name in CANDIDATE_COLUMNS}
    return {"present": present, "missing": [name for name, exists in present.items() if not exists]}


def build_report(path: Path, source_url: str = SOURCE_URL) -> dict:
    inspection = inspect_csv(path)
    return {
        "schema": "manager.heartsteps.h002-h004.v1",
        "source": {"repository": "klasnja/HeartStepsV1", "commit": SOURCE_COMMIT,
                   "path": SOURCE_PATH, "url": source_url},
        "inspection": inspection,
        "candidate_column_check": check_candidate_columns(inspection["headers"]),
        "privacy": {"raw_participant_rows_in_report": False,
                    "sensitive_row_values_in_report": False,
                    "raw_redistribution": "forbidden_by_manager_policy"},
        "claims": {"descriptive_only": True, "causal_effect_estimated": False,
                   "manager_field_impact_measured": False},
    }


def write_reports(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "heartsteps_h002_h004.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inspection = report["inspection"]
    column_check = report["candidate_column_check"]
    source = report["source"]
    lines = ["# HeartSteps H002-H004 aggregate inspection", "",
             f"- Source: `{source['repository']}@{source['commit']}` / `{source['path']}`",
             f"- Rows: **{inspection['row_count']:,}**",
             f"- Columns: **{inspection['column_count']}**",
             f"- Malformed rows: **{inspection['malformed_rows']}**",
             "- Raw participant rows are not included in this report.",
             "- This is descriptive source validation, not a causal-effect estimate.", "",
             "## Candidate columns", ""]
    for name, present in column_check["present"].items():
        lines.append(f"- {'PASS' if present else 'MISSING'} `{name}`")
    lines += ["", "## Safe aggregate counts", ""]
    for name, counts in inspection["value_counts"].items():
        lines.append(f"- `{name}`: `{json.dumps(counts, sort_keys=True)}`")
    (output_dir / "heartsteps_h002_h004.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default=SOURCE_URL)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="manager-heartsteps-") as tmp:
        raw_path = Path(tmp) / "suggestions.csv"
        download(args.url, raw_path)
        identity = validate_source(raw_path, EXPECTED_BYTES, EXPECTED_GIT_BLOB_SHA1)
        report = build_report(raw_path, source_url=args.url)
        report["source_identity"] = identity
        if report["inspection"]["row_count"] != EXPECTED_ROWS:
            raise SystemExit(f"row count mismatch: expected {EXPECTED_ROWS}, got {report['inspection']['row_count']}")
        if report["inspection"]["column_count"] != EXPECTED_README_COLUMNS:
            report["warnings"] = ["README column count differs from the pinned CSV header count; the actual header is preserved in the aggregate report."]
        write_reports(report, args.output)
        print(json.dumps({"rows": report["inspection"]["row_count"],
                          "columns": report["inspection"]["column_count"],
                          "sha256": identity["sha256"],
                          "raw_rows_persisted": False, "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
