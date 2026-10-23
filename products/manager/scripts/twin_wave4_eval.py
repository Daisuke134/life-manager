#!/usr/bin/env python3
"""Inspect pinned public Twin wave 4 files without evaluating model accuracy."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

REVISION = "f883165a3026fde855dfd448e0cd16443ab257b6"
MAX_FILE_BYTES = 50 * 1024 * 1024
EXPECTED = {
    "question_catalog_and_human_response_csv/question_catalog.json": ("catalog.json", "question_catalog"),
    "LLM_simulation_results/wave4_formatted_to_catalog_mapping.json": ("mapping.json", "official_mapping"),
    "question_catalog_and_human_response_csv/wave1_3_response.csv": ("history.csv", "wave1_3_history"),
    "question_catalog_and_human_response_csv/wave4_response.csv": ("target.csv", "wave4_target"),
    "LLM_simulation_results/GPT4.1-mini-simulation-llm-vs-human/responses_llm_imputed_formatted.csv": ("output.csv", "released_output_unverified"),
}
ID_RE = re.compile(r"^[1-9][0-9]*$")


class InspectionError(Exception):
    """Stable sanitized failure code; source content is never included."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise InspectionError(code)


def description_row_hash(row: list[str]) -> str:
    """Hash a parsed row's canonical JSON representation without exposing it."""
    encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validated_pin_index(pins: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(pins, dict) or pins.get("revision") != REVISION:
        _fail("SOURCE_REVISION_MISMATCH")
    rows = pins.get("files")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED):
        _fail("INVALID_METADATA")
    index = {}
    names = set()
    paths = set()
    for row in rows:
        if not isinstance(row, dict):
            _fail("INVALID_METADATA")
        path = row.get("source_path")
        expected = EXPECTED.get(path)
        if expected is None:
            _fail("SOURCE_ROLE_FORBIDDEN")
        name, role = expected
        if row.get("name") != name or row.get("role") != role:
            _fail("SOURCE_ROLE_FORBIDDEN")
        if name in names or path in paths:
            _fail("INVALID_METADATA")
        count = row.get("bytes")
        digest = row.get("sha256")
        if type(count) is not int or count < 0 or count > MAX_FILE_BYTES:
            _fail("INVALID_METADATA")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            _fail("INVALID_METADATA")
        if role == "released_output_unverified":
            description = row.get("description_row")
            if (not isinstance(description, dict) or description.get("position") != 2
                    or not isinstance(description.get("sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", description["sha256"]) is None):
                _fail("DESCRIPTION_ROW_PIN_MISSING")
        index[name] = row
        names.add(name)
        paths.add(path)
    if paths != set(EXPECTED):
        _fail("INVALID_METADATA")
    return index


def load_verified_snapshot(input_dir: Path, pins: dict[str, Any]) -> dict[str, bytes]:
    """Read every pinned byte sequence and verify all hashes before parsing any."""
    index = _validated_pin_index(pins)
    files: dict[str, bytes] = {}
    try:
        for path, (name, _role) in EXPECTED.items():
            source = input_dir / name
            if source.stat().st_size > MAX_FILE_BYTES:
                _fail("SOURCE_SIZE_LIMIT")
            with source.open("rb") as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                _fail("SOURCE_SIZE_LIMIT")
            files[name] = data
    except FileNotFoundError:
        _fail("MISSING_SOURCE_FILE")
    except OSError:
        _fail("SOURCE_READ_ERROR")
    for name, data in files.items():
        pin = index[name]
        if len(data) != pin["bytes"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
            _fail("SOURCE_HASH_MISMATCH")
    return files


def _decode_json(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("INVALID_METADATA")


def _csv_rows(data: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        text = data.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error, StopIteration):
        _fail("INVALID_CSV")
    if not header or any(not column for column in header):
        _fail("INVALID_HEADER")
    if len(set(header)) != len(header):
        _fail("DUPLICATE_HEADER")
    if any(len(row) != len(header) for row in rows):
        _fail("ROW_WIDTH_MISMATCH")
    return header, rows


def load_metadata(input_dir: Path, pins: dict[str, Any]) -> tuple[list[Any], list[Any], dict[str, list[str]]]:
    files = load_verified_snapshot(input_dir, pins)
    catalog = _decode_json(files["catalog.json"])
    mapping = _decode_json(files["mapping.json"])
    if not isinstance(catalog, list) or not isinstance(mapping, list):
        _fail("INVALID_METADATA")
    headers = {}
    index = _validated_pin_index(pins)
    for source_path, (name, _role) in EXPECTED.items():
        if not name.endswith(".csv"):
            continue
        header, _ = _csv_rows(files[name])
        headers[index[name]["role"]] = header
    return catalog, mapping, headers


def resolve_items(catalog: list[Any], mapping: list[Any], headers: dict[str, list[str]]) -> list[dict[str, str]]:
    if not isinstance(catalog, list) or not isinstance(mapping, list):
        _fail("INVALID_METADATA")
    formatted_seen: set[str] = set()
    csv_seen: set[str] = set()
    items = []
    history = set(headers.get("wave1_3_history", []))
    target = set(headers.get("wave4_target", []))
    release = set(headers.get("released_output_unverified", []))
    for entry in mapping:
        if not isinstance(entry, dict):
            _fail("INVALID_METADATA")
        formatted = entry.get("formatted_column")
        qid = entry.get("QuestionID")
        column = entry.get("catalog_csv_column")
        if not all(isinstance(v, str) and v for v in (formatted, qid, column)):
            _fail("INVALID_METADATA")
        if formatted in formatted_seen or column in csv_seen:
            _fail("MAPPING_NOT_BIJECTIVE")
        formatted_seen.add(formatted)
        csv_seen.add(column)
        hits = []
        for row in catalog:
            if not isinstance(row, dict):
                _fail("INVALID_METADATA")
            row_columns = row.get("csv_columns")
            if (row.get("source") == "wave4_Q_wave1_3_A" and row.get("QuestionID") == qid
                    and isinstance(row_columns, list) and column in row_columns):
                hits.append(row)
        if len(hits) != 1:
            _fail("CATALOG_AMBIGUOUS" if len(hits) > 1 else "CATALOG_ITEM_MISSING")
        item_type = hits[0].get("QuestionType")
        if not isinstance(item_type, str) or not item_type:
            _fail("INVALID_METADATA")
        if formatted not in release or column not in target or column not in history:
            _fail("MAPPED_COLUMN_MISSING")
        items.append({"formatted_column": formatted, "catalog_csv_column": column, "question_type": item_type})
    if not items:
        _fail("MAPPING_NOT_BIJECTIVE")
    return items


def _inspect_role(data: bytes, role: str, expected_id_column: str, mapped: list[str], pins: dict[str, Any], name: str) -> tuple[dict[str, Any], set[str]]:
    header, rows = _csv_rows(data)
    if expected_id_column not in header:
        _fail("ROLE_HEADER_MISMATCH")
    pin = next(row for row in pins["files"] if row["name"] == name)
    if role == "released_output_unverified":
        if len(rows) == 0:
            _fail("DESCRIPTION_ROW_MISSING")
        description = rows[0]
        desc_pin = pin["description_row"]
        if desc_pin.get("position") != 2 or description_row_hash(description) != desc_pin["sha256"]:
            _fail("DESCRIPTION_ROW_MISMATCH")
        rows = rows[1:]
    ids: set[str] = set()
    empty = 0
    nonempty = 0
    for row in rows:
        person_id = row[header.index(expected_id_column)]
        if not ID_RE.fullmatch(person_id):
            _fail("INVALID_ID")
        if person_id in ids:
            _fail("DUPLICATE_ID")
        ids.add(person_id)
        for column in mapped:
            value = row[header.index(column)]
            if value == "":
                empty += 1
            else:
                nonempty += 1
    return ({"role": role, "rows": len(rows), "mapped_columns": len(mapped),
             "mapped_cells_empty": empty, "mapped_cells_nonempty": nonempty,
             "extra_columns_excluded": len(header) - len(mapped)}, ids)


def inspect_snapshot(input_dir: Path, pins: dict[str, Any]) -> dict[str, Any]:
    files = load_verified_snapshot(input_dir, pins)
    catalog = _decode_json(files["catalog.json"])
    mapping = _decode_json(files["mapping.json"])
    if not isinstance(catalog, list) or not isinstance(mapping, list):
        _fail("INVALID_METADATA")
    headers = {}
    csv_data = {}
    for source_path, (name, role) in EXPECTED.items():
        if not name.endswith(".csv"):
            continue
        header, _rows = _csv_rows(files[name])
        headers[role] = header
        csv_data[role] = files[name]
    items = resolve_items(catalog, mapping, headers)
    mapped_history = [item["catalog_csv_column"] for item in items]
    mapped_target = mapped_history
    mapped_output = [item["formatted_column"] for item in items]
    roles = {}
    id_sets = {}
    for role, id_column, mapped, name in (
        ("wave1_3_history", "pid", mapped_history, "history.csv"),
        ("wave4_target", "pid", mapped_target, "target.csv"),
        ("released_output_unverified", "TWIN_ID", mapped_output, "output.csv"),
    ):
        roles[role], id_sets[role] = _inspect_role(csv_data[role], role, id_column, mapped, pins, name)
    history_ids = id_sets["wave1_3_history"]
    target_ids = id_sets["wave4_target"]
    output_ids = id_sets["released_output_unverified"]
    shared = history_ids & target_ids & output_ids
    types: dict[str, int] = {}
    for item in items:
        kind = item["question_type"]
        types[kind] = types.get(kind, 0) + 1
    return {
        "status": "INSPECTED",
        "source": {"revision": REVISION, "license": "CC-BY-4.0", "private": False, "gated": False},
        "catalog": {
            "entries": len(catalog),
            "distinct_question_ids": len({row.get("QuestionID") for row in catalog if isinstance(row, dict) and isinstance(row.get("QuestionID"), str)}),
            "duplicate_question_id_count": len(catalog) - len({row.get("QuestionID") for row in catalog if isinstance(row, dict) and isinstance(row.get("QuestionID"), str)}),
        },
        "mapping": {"mapped_items": len(items), "question_types": dict(sorted(types.items()))},
        "roles": roles,
        "ids": {
            "history": len(history_ids), "target": len(target_ids), "released_output": len(output_ids),
            "history_target_intersection": len(history_ids & target_ids),
            "history_output_intersection": len(history_ids & output_ids),
            "target_output_intersection": len(target_ids & output_ids),
            "triple_intersection": len(shared),
            "join_verified": True,
            "all_id_sets_equal": history_ids == target_ids == output_ids,
        },
        "provenance": {
            "code": "RELEASED_OUTPUT_PROVENANCE_UNVERIFIED",
            "generation_run_binding": "UNKNOWN",
            "model_training_exposure": "UNKNOWN",
            "expected_eligible_cells": None,
            "verified_generated_cells": None,
        },
        "accuracy": None,
        "scientific_pass": False,
    }


def _load_pins(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        dataset = value.get("dataset") if isinstance(value, dict) and "dataset" in value else value
        snapshot = dataset.get("wave4_inspection") if isinstance(dataset, dict) else None
        if not isinstance(snapshot, dict):
            _fail("INVALID_METADATA")
        return snapshot
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail("INVALID_METADATA")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="twin-wave4")
    parser.add_argument("mode", choices=("inspect",))
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--pins", type=Path)
    args = parser.parse_args(argv)
    try:
        pin_path = args.pins or Path(__file__).resolve().parents[3] / "docs/research/manager/evidence/artificial-societies-20261022/reuse.json"
        report = inspect_snapshot(args.input_dir, _load_pins(pin_path))
    except InspectionError as error:
        print(f"twin-wave4: {error.code}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
