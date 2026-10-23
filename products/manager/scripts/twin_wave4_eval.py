#!/usr/bin/env python3
"""Inspect pinned public Twin wave 4 files without evaluating model accuracy."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import types
from pathlib import Path
from typing import Any

REVISION = "f883165a3026fde855dfd448e0cd16443ab257b6"
MAX_FILE_BYTES = 50 * 1024 * 1024
MIN_PUBLISHABLE_CELLS = 20
OFFICIAL_MAD_SHA256 = "b25b7912310c14393b62dcaf5c214496189f98eb82398e86bb8004a14785ff96"
OFFICIAL_MAD_REPOSITORY = "tianyipeng-lab/Digital-Twin-Simulation"
OFFICIAL_MAD_REVISION = "f1eed510c9a4fb47aaa9bb46e178aaa2d9224623"
OFFICIAL_MAD_PATH = "evaluation/mad_accuracy_evaluation.py"
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


def _read_verified_official_code(code_path: Path) -> bytes:
    """Read the one pinned official metric source and check bytes before import."""
    try:
        if code_path.stat().st_size > MAX_FILE_BYTES:
            _fail("OFFICIAL_CODE_SIZE_LIMIT")
        source = code_path.read_bytes()
    except FileNotFoundError:
        _fail("OFFICIAL_CODE_MISSING")
    except OSError:
        _fail("OFFICIAL_CODE_READ_ERROR")
    if len(source) > MAX_FILE_BYTES:
        _fail("OFFICIAL_CODE_SIZE_LIMIT")
    if hashlib.sha256(source).hexdigest() != OFFICIAL_MAD_SHA256:
        _fail("OFFICIAL_CODE_HASH_MISMATCH")
    return source


def _import_verified_official_code(source: bytes, code_path: Path):
    """Import verified bytes only; optional research dependencies stay lazy."""
    module = types.ModuleType("_twin_verified_official_mad")
    module.__file__ = str(code_path)
    try:
        exec(compile(source, str(code_path), "exec"), module.__dict__)
        if not callable(getattr(module, "get_default_column_ranges", None)):
            return None, "OFFICIAL_METRIC_UNAVAILABLE"
        if not callable(getattr(module, "get_default_qid_to_task", None)):
            return None, "OFFICIAL_METRIC_UNAVAILABLE"
        if not callable(getattr(module, "compute_column_mad", None)):
            return None, "OFFICIAL_METRIC_UNAVAILABLE"
        return module, None
    except Exception:
        return None, "OFFICIAL_METRIC_UNAVAILABLE"


def _number(value: str) -> float | None:
    try:
        parsed = float(value.strip())
    except (AttributeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _bounds(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    low = value.get("Min")
    high = value.get("Max")
    if (isinstance(low, bool) or isinstance(high, bool)
            or not isinstance(low, (int, float)) or not isinstance(high, (int, float))):
        return None
    low_value = float(low)
    high_value = float(high)
    if not math.isfinite(low_value) or not math.isfinite(high_value) or high_value <= low_value:
        return None
    return low_value, high_value


def _integer_code(value: str) -> int | None:
    parsed = _number(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def _native_validity(value: str, catalog_item: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate native response codes using question metadata, without exporting values."""
    kind = catalog_item.get("QuestionType")
    settings = catalog_item.get("Settings")
    settings = settings if isinstance(settings, dict) else {}
    if kind == "MC":
        options = catalog_item.get("Options")
        if not isinstance(options, list) or not options:
            return False, "domain"
        selector = settings.get("Selector")
        if selector in ("MAVR", "MAHR"):
            return (value == "1", None if value == "1" else "code")
        code = _integer_code(value)
        return (code is not None and 1 <= code <= len(options), None if code is not None and 1 <= code <= len(options) else "code")
    if kind == "Matrix":
        columns = catalog_item.get("Columns")
        if not isinstance(columns, list) or not columns:
            return False, "domain"
        code = _integer_code(value)
        return (code is not None and 1 <= code <= len(columns), None if code is not None and 1 <= code <= len(columns) else "code")
    if kind == "Slider":
        number = _number(value)
        if number is None:
            return False, "numeric"
        declared = _bounds(catalog_item.get("Range"))
        if declared is not None and not declared[0] <= number <= declared[1]:
            return False, "range"
        return True, None
    if kind == "TE":
        if settings.get("ContentType") == "ValidNumber":
            return (_number(value) is not None, None if _number(value) is not None else "numeric")
        return True, None
    return False, "domain"


def _suppressible_count(value: int) -> int | None:
    if 0 < value < MIN_PUBLISHABLE_CELLS:
        return None
    return value


def _comparison_summary(matches: int, count: int) -> dict[str, Any]:
    if count < MIN_PUBLISHABLE_CELLS:
        return {"matches": None, "n": None, "rate": None, "suppressed": True}
    return {
        "matches": matches,
        "n": count,
        "rate": round(matches / count, 6),
        "suppressed": False,
    }


def _catalog_item_for_mapping(catalog: list[Any], item: dict[str, str]) -> dict[str, Any]:
    hits = [
        row for row in catalog
        if isinstance(row, dict)
        and row.get("source") == "wave4_Q_wave1_3_A"
        and row.get("QuestionID") == item["question_id"]
        and isinstance(row.get("csv_columns"), list)
        and item["catalog_csv_column"] in row["csv_columns"]
    ]
    if len(hits) != 1:
        _fail("CATALOG_AMBIGUOUS" if len(hits) > 1 else "CATALOG_ITEM_MISSING")
    return hits[0]


def _load_role_rows(data: bytes, role: str, id_column: str, mapped: list[str], pins: dict[str, Any], name: str):
    header, rows = _csv_rows(data)
    if id_column not in header:
        _fail("ROLE_HEADER_MISMATCH")
    if role == "released_output_unverified":
        pin = next(row for row in pins["files"] if row["name"] == name)
        description = pin.get("description_row")
        if not rows or not isinstance(description, dict) or description.get("position") != 2:
            _fail("DESCRIPTION_ROW_MISSING")
        if description_row_hash(rows[0]) != description.get("sha256"):
            _fail("DESCRIPTION_ROW_MISMATCH")
        rows = rows[1:]
    positions = {column: header.index(column) for column in mapped}
    id_position = header.index(id_column)
    by_id = {}
    for row in rows:
        person_id = row[id_position]
        if not ID_RE.fullmatch(person_id):
            _fail("INVALID_ID")
        if person_id in by_id:
            _fail("DUPLICATE_ID")
        by_id[person_id] = {column: row[position] for column, position in positions.items()}
    return by_id


def _official_definitions(official_module):
    if official_module is None:
        return None, None, "OFFICIAL_METRIC_UNAVAILABLE"
    try:
        raw_ranges = official_module.get_default_column_ranges()
        raw_tasks = official_module.get_default_qid_to_task()
    except Exception:
        return None, None, "OFFICIAL_METRIC_UNAVAILABLE"
    if not isinstance(raw_ranges, dict) or not isinstance(raw_tasks, dict):
        return None, None, "OFFICIAL_METRIC_UNAVAILABLE"
    ranges = {}
    original_keys = {}
    for key, value in raw_ranges.items():
        if not isinstance(key, str) or not isinstance(value, (tuple, list)) or len(value) != 2:
            return None, None, "OFFICIAL_METRIC_UNAVAILABLE"
        low, high = value
        if (isinstance(low, bool) or isinstance(high, bool)
                or not isinstance(low, (int, float)) or not isinstance(high, (int, float))):
            return None, None, "OFFICIAL_METRIC_UNAVAILABLE"
        low_value, high_value = float(low), float(high)
        if not math.isfinite(low_value) or not math.isfinite(high_value) or high_value <= low_value:
            return None, None, "OFFICIAL_METRIC_UNAVAILABLE"
        normalized = key.upper()
        if normalized in ranges:
            return None, None, "OFFICIAL_METRIC_UNAVAILABLE"
        ranges[normalized] = (low_value, high_value)
        original_keys[normalized] = key
    tasks = {}
    for key, task in raw_tasks.items():
        if not isinstance(key, str) or not isinstance(task, str):
            return None, None, "OFFICIAL_METRIC_UNAVAILABLE"
        normalized = key.upper()
        if normalized in tasks:
            return None, None, "OFFICIAL_METRIC_UNAVAILABLE"
        tasks[normalized] = task
    return (ranges, tasks, original_keys), None, None


def _numeric_basis(catalog_item: dict[str, Any], range_entry, task_available: bool) -> str:
    if range_entry is None:
        return "NO_OFFICIAL_RANGE"
    if not task_available:
        return "NO_OFFICIAL_TASK"
    kind = catalog_item.get("QuestionType")
    if kind == "MC":
        return "NOMINAL_MC_EXCLUDED"
    if kind == "Matrix":
        return "ORDINAL_MATRIX_EXCLUDED"
    if kind == "Slider":
        bounds = _bounds(catalog_item.get("Range"))
        if bounds is None:
            return "NO_CATALOG_INTERVAL_RANGE"
        if bounds != range_entry:
            return "OFFICIAL_RANGE_MISMATCH"
        return "CATALOG_SLIDER_RANGE"
    if kind == "TE":
        settings = catalog_item.get("Settings")
        if isinstance(settings, dict) and settings.get("ContentType") == "ValidNumber":
            return "OFFICIAL_NUMERIC_ENTRY_RANGE"
        return "NO_NUMERIC_INTERVAL_METADATA"
    return "NO_NUMERIC_INTERVAL_METADATA"


def _metric_result_value(result) -> tuple[float, int] | None:
    if result is None or getattr(result, "empty", False) or len(result) == 0:
        return None
    row = result.iloc[0]
    try:
        normalized_mad = float(row["predictions vs. ground_truth"])
        respondents = int(row["number of respondents"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(normalized_mad) or respondents < 0:
        return None
    return round(normalized_mad, 6), respondents


def _audit_snapshot_bytes(files: dict[str, bytes], pins: dict[str, Any], official_module,
                          official_unavailable_reason: str | None = None) -> dict[str, Any]:
    """Compute aggregate-only released agreement from already hash-verified bytes."""
    catalog = _decode_json(files["catalog.json"])
    mapping = _decode_json(files["mapping.json"])
    if not isinstance(catalog, list) or not isinstance(mapping, list):
        _fail("INVALID_METADATA")
    headers = {}
    parsed = {}
    for _path, (name, role) in EXPECTED.items():
        if not name.endswith(".csv"):
            continue
        header, _rows = _csv_rows(files[name])
        headers[role] = header
        parsed[role] = files[name]
    items = resolve_items(catalog, mapping, headers)
    catalog_by_item = {}
    mapping_by_column = {}
    for entry in mapping:
        catalog_item = _catalog_item_for_mapping(catalog, {
            "question_id": entry["QuestionID"],
            "catalog_csv_column": entry["catalog_csv_column"],
        })
        catalog_by_item[entry["formatted_column"]] = catalog_item
        mapping_by_column[entry["formatted_column"]] = entry
    items = sorted(items, key=lambda item: item["formatted_column"].upper())
    history_columns = [item["catalog_csv_column"] for item in items]
    output_columns = [item["formatted_column"] for item in items]
    role_rows = {
        "wave1_3_history": _load_role_rows(parsed["wave1_3_history"], "wave1_3_history", "pid", history_columns, pins, "history.csv"),
        "wave4_target": _load_role_rows(parsed["wave4_target"], "wave4_target", "pid", history_columns, pins, "target.csv"),
        "released_output_unverified": _load_role_rows(parsed["released_output_unverified"], "released_output_unverified", "TWIN_ID", output_columns, pins, "output.csv"),
    }
    history_ids = set(role_rows["wave1_3_history"])
    target_ids = set(role_rows["wave4_target"])
    output_ids = set(role_rows["released_output_unverified"])
    shared_ids = sorted(history_ids & target_ids & output_ids, key=lambda value: int(value))
    all_id_sets_equal = history_ids == target_ids == output_ids

    definitions, unavailable_reason, _unused = _official_definitions(official_module)
    official_definitions_available = definitions is not None
    if definitions is None:
        normalized_ranges, normalized_tasks, original_range_keys = {}, {}, {}
        official_unavailable_reason = official_unavailable_reason or unavailable_reason or "OFFICIAL_METRIC_UNAVAILABLE"
    else:
        normalized_ranges, normalized_tasks, original_range_keys = definitions
        official_unavailable_reason = None

    missing_counts = {role: 0 for role in role_rows}
    invalid_counts = {role: 0 for role in role_rows}
    native_range_counts = {role: 0 for role in role_rows}
    numeric_parse_counts = {role: 0 for role in role_rows}
    official_range_counts = {role: 0 for role in role_rows}
    for role, rows in role_rows.items():
        column_names = history_columns if role != "released_output_unverified" else output_columns
        for row in rows.values():
            for column in column_names:
                if row[column] == "":
                    missing_counts[role] += 1

    comparison_names = (
        "released_output_vs_wave4",
        "wave1_3_history_vs_wave4",
        "released_output_vs_history",
    )
    pair_roles = {
        "released_output_vs_wave4": ("released_output_unverified", "wave4_target"),
        "wave1_3_history_vs_wave4": ("wave1_3_history", "wave4_target"),
        "released_output_vs_history": ("released_output_unverified", "wave1_3_history"),
    }
    total_matches = {name: 0 for name in comparison_names}
    total_native_cells = 0
    total_nonempty_cells = 0
    total_numeric_cells = 0
    per_item = []
    mad_candidates = []
    range_covered = 0
    task_covered = 0
    range_and_task_covered = 0
    no_official_range = 0
    excluded_by_reason: dict[str, int] = {}

    for item in items:
        formatted = item["formatted_column"]
        catalog_column = item["catalog_csv_column"]
        catalog_item = catalog_by_item[formatted]
        kind = item["question_type"]
        official_key = formatted.upper()
        range_entry = normalized_ranges.get(official_key)
        task_available = official_key in normalized_tasks
        if range_entry is not None:
            range_covered += 1
        else:
            no_official_range += 1
        if task_available:
            task_covered += 1
        if range_entry is not None and task_available:
            range_and_task_covered += 1
        numeric_reason = _numeric_basis(catalog_item, range_entry, task_available)
        if numeric_reason not in ("CATALOG_SLIDER_RANGE", "OFFICIAL_NUMERIC_ENTRY_RANGE"):
            excluded_by_reason[numeric_reason] = excluded_by_reason.get(numeric_reason, 0) + 1
        item_nonempty = 0
        item_native = 0
        item_matches = {name: 0 for name in comparison_names}
        numeric_values = {role: [] for role in role_rows}
        numeric_indices = []
        native_role_values = {role: [] for role in role_rows}
        native_role_status = {role: [] for role in role_rows}
        for row_index, person_id in enumerate(shared_ids):
            values = {
                "wave1_3_history": role_rows["wave1_3_history"][person_id][catalog_column],
                "wave4_target": role_rows["wave4_target"][person_id][catalog_column],
                "released_output_unverified": role_rows["released_output_unverified"][person_id][formatted],
            }
            for role in role_rows:
                valid, reason = _native_validity(values[role], catalog_item) if values[role] != "" else (False, "missing")
                native_role_values[role].append(values[role])
                native_role_status[role].append((valid, reason))
                if values[role] != "" and not valid:
                    invalid_counts[role] += 1
                    if reason == "range":
                        native_range_counts[role] += 1
                    elif reason == "numeric":
                        numeric_parse_counts[role] += 1
            if any(values[role] == "" for role in role_rows):
                continue
            item_nonempty += 1
            if not all(native_role_status[role][-1][0] for role in role_rows):
                continue
            item_native += 1
            for name, (left_role, right_role) in pair_roles.items():
                if values[left_role] == values[right_role]:
                    item_matches[name] += 1
            if numeric_reason not in ("CATALOG_SLIDER_RANGE", "OFFICIAL_NUMERIC_ENTRY_RANGE"):
                continue
            low, high = range_entry
            parsed_values = {role: _number(values[role]) for role in role_rows}
            if any(parsed_values[role] is None for role in role_rows):
                for role in role_rows:
                    if parsed_values[role] is None:
                        numeric_parse_counts[role] += 1
                continue
            if any(not low <= parsed_values[role] <= high for role in role_rows):
                for role in role_rows:
                    if not low <= parsed_values[role] <= high:
                        official_range_counts[role] += 1
                continue
            numeric_indices.append(row_index)
            for role in role_rows:
                numeric_values[role].append(parsed_values[role])
        total_nonempty_cells += item_nonempty
        total_native_cells += item_native
        total_numeric_cells += len(numeric_indices)
        for name in comparison_names:
            total_matches[name] += item_matches[name]

        item_comparisons = {
            name: _comparison_summary(item_matches[name], item_native)
            for name in comparison_names
        }
        per_item.append({
            "item_code": catalog_column,
            "question_type": kind,
            "common_nonempty_cells": _suppressible_count(item_nonempty),
            "native_valid_cells": _suppressible_count(item_native),
            "comparisons": item_comparisons,
        })
        if numeric_reason in ("CATALOG_SLIDER_RANGE", "OFFICIAL_NUMERIC_ENTRY_RANGE"):
            mad_candidates.append({
                "item_code": catalog_column,
                "question_type": kind,
                "official_key": original_range_keys.get(official_key, formatted),
                "numeric_basis": numeric_reason,
                "range": range_entry,
                "indices": numeric_indices,
                "values": numeric_values,
            })

    comparison_summaries = {
        name: _comparison_summary(total_matches[name], total_native_cells)
        for name in comparison_names
    }
    normalized_mad_status = "AVAILABLE"
    normalized_mad_reason = None
    mad_values_by_item = {}
    if not official_definitions_available:
        normalized_mad_status = "UNAVAILABLE"
        normalized_mad_reason = official_unavailable_reason or "OFFICIAL_METRIC_UNAVAILABLE"
    else:
        try:
            for candidate in mad_candidates:
                count = len(candidate["indices"])
                if count < MIN_PUBLISHABLE_CELLS:
                    mad_values_by_item[candidate["item_code"]] = None
                    continue
                official_column = candidate["official_key"]
                width = candidate["range"][1] - candidate["range"][0]
                pred_data = {official_column: candidate["values"]["released_output_unverified"]}
                target_data = {official_column: candidate["values"]["wave4_target"]}
                history_data = {official_column: candidate["values"]["wave1_3_history"]}
                numeric_index = list(range(count))
                output_result = official_module.compute_column_mad(
                    official_module.pd.DataFrame(pred_data, index=numeric_index),
                    official_module.pd.DataFrame(target_data, index=numeric_index),
                    {official_column: float(width)},
                )
                history_result = official_module.compute_column_mad(
                    official_module.pd.DataFrame(history_data, index=numeric_index),
                    official_module.pd.DataFrame(target_data, index=numeric_index),
                    {official_column: float(width)},
                )
                output_value = _metric_result_value(output_result)
                history_value = _metric_result_value(history_result)
                if (output_value is None or history_value is None
                        or output_value[1] != count or history_value[1] != count):
                    raise ValueError("official metric returned no aligned result")
                mad_values_by_item[candidate["item_code"]] = {
                    "output_vs_wave4": output_value[0],
                    "wave1_3_history_vs_wave4": history_value[0],
                    "n": count,
                }
        except Exception:
            normalized_mad_status = "UNAVAILABLE"
            normalized_mad_reason = "OFFICIAL_METRIC_EXECUTION_FAILED"
            mad_values_by_item = {}

    mad_items = []
    for candidate in mad_candidates:
        values = mad_values_by_item.get(candidate["item_code"])
        row = {
            "item_code": candidate["item_code"],
            "question_type": candidate["question_type"],
            "numeric_basis": candidate["numeric_basis"],
            "common_numeric_cells": _suppressible_count(len(candidate["indices"])),
            "suppressed": len(candidate["indices"]) < MIN_PUBLISHABLE_CELLS,
        }
        if normalized_mad_status == "UNAVAILABLE":
            row.update({
                "output_vs_wave4_normalized_mad": None,
                "wave1_3_history_vs_wave4_normalized_mad": None,
                "reason": normalized_mad_reason,
            })
        elif values is None:
            row.update({
                "output_vs_wave4_normalized_mad": None,
                "wave1_3_history_vs_wave4_normalized_mad": None,
                "reason": "SMALL_AGGREGATE_SUPPRESSED",
            })
        else:
            row.update({
                "output_vs_wave4_normalized_mad": values["output_vs_wave4"],
                "wave1_3_history_vs_wave4_normalized_mad": values["wave1_3_history_vs_wave4"],
                "reason": None,
            })
        mad_items.append(row)

    return {
        "status": "DESCRIPTIVE_AGGREGATE_AUDIT",
        "source": {
            "dataset_repository": "LLM-Digital-Twin/Twin-2K-500",
            "revision": REVISION,
            "license": "CC-BY-4.0",
            "private": False,
            "gated": False,
            "input_sha256": {row["role"]: row["sha256"] for row in pins["files"]},
            "official_metric_repository": OFFICIAL_MAD_REPOSITORY,
            "official_metric_revision": OFFICIAL_MAD_REVISION,
            "official_metric_path": OFFICIAL_MAD_PATH,
            "official_metric_sha256": OFFICIAL_MAD_SHA256,
            "official_metric_license": "Apache-2.0",
        },
        "catalog": {
            "entries": len(catalog),
            "distinct_question_ids": len({row.get("QuestionID") for row in catalog if isinstance(row, dict) and isinstance(row.get("QuestionID"), str)}),
            "duplicate_question_id_count": len(catalog) - len({row.get("QuestionID") for row in catalog if isinstance(row, dict) and isinstance(row.get("QuestionID"), str)}),
        },
        "mapping": {
            "mapped_items": len(items),
            "mapped_slots_per_joined_person": len(items),
            "question_types": dict(sorted({kind: sum(item["question_type"] == kind for item in items) for kind in {item["question_type"] for item in items}}.items())),
        },
        "ids": {
            "history_rows": _suppressible_count(len(history_ids)),
            "target_rows": _suppressible_count(len(target_ids)),
            "released_output_rows": _suppressible_count(len(output_ids)),
            "triple_intersection": _suppressible_count(len(shared_ids)),
            "join_verified": True,
            "all_id_sets_equal": all_id_sets_equal,
        },
        "agreement": {
            "mask": {
                "mapped_slots": _suppressible_count(len(items) * len(shared_ids)),
                "common_nonempty_cells": _suppressible_count(total_nonempty_cells),
                "common_native_valid_cells": _suppressible_count(total_native_cells),
                "pair_denominators_equal": True,
            },
            "comparisons": comparison_summaries,
            "items": per_item,
        },
        "quality": {
            "missing_cells_by_role": {role: _suppressible_count(value) for role, value in missing_counts.items()},
            "invalid_native_cells_by_role": {role: _suppressible_count(value) for role, value in invalid_counts.items()},
            "native_range_invalid_cells_by_role": {role: _suppressible_count(value) for role, value in native_range_counts.items()},
            "numeric_parse_invalid_cells_by_role": {role: _suppressible_count(value) for role, value in numeric_parse_counts.items()},
            "official_range_invalid_cells_by_role": {role: _suppressible_count(value) for role, value in official_range_counts.items()},
        },
        "normalized_mad": {
            "status": normalized_mad_status,
            "reason": normalized_mad_reason,
            "official_range_covered_columns": range_covered if official_definitions_available else None,
            "official_task_covered_columns": task_covered if official_definitions_available else None,
            "official_range_and_task_covered_columns": range_and_task_covered if official_definitions_available else None,
            "no_official_range_columns": no_official_range if official_definitions_available else None,
            "numeric_scale_eligible_columns": len(mad_candidates) if official_definitions_available else None,
            "common_numeric_cells": _suppressible_count(total_numeric_cells) if official_definitions_available else None,
            "excluded_by_reason": dict(sorted(excluded_by_reason.items())) if official_definitions_available else None,
            "items": mad_items if official_definitions_available else [],
        },
        "provenance": {
            "code": "RELEASED_OUTPUT_PROVENANCE_UNVERIFIED",
            "generated_cell_provenance": "UNVERIFIED",
            "generation_run_binding": "UNKNOWN",
            "model_training_exposure": "UNKNOWN",
            "expected_eligible_cells": None,
            "verified_generated_cells": None,
        },
        "accuracy": None,
        "predictive_accuracy": None,
        "scientific_pass": False,
        "interpretation": {
            "scope": "Retrospective descriptive agreement for the released output and public human response waves.",
            "native_match_mask": "Three-role common nonempty cells that pass catalog-native validation.",
            "released_output_vs_history": "Equality is descriptive only and does not establish fallback or generation provenance.",
            "missingness": "Blank cells are not classified as generation failure.",
            "predictive_accuracy": "NOT_ASSESSED",
        },
    }


def audit_released_agreement(input_dir: Path, pins: dict[str, Any], official_code_path: Path) -> dict[str, Any]:
    """Run the bounded aggregate agreement audit with repository pins and official code."""
    source = _read_verified_official_code(official_code_path)
    files = load_verified_snapshot(input_dir, pins)
    official_module, unavailable_reason = _import_verified_official_code(source, official_code_path)
    return _audit_snapshot_bytes(files, pins, official_module, unavailable_reason)


def _load_repository_pins() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[3] / "docs/research/manager/evidence/artificial-societies-20261022/reuse.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        dataset = value.get("dataset") if isinstance(value, dict) else None
        snapshot = dataset.get("wave4_inspection") if isinstance(dataset, dict) else None
        if not isinstance(snapshot, dict):
            _fail("INVALID_METADATA")
        return snapshot
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail("INVALID_METADATA")


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if any(argument == "--pins" or argument.startswith("--pins=") for argument in arguments):
        print("twin-wave4: PIN_OVERRIDE_FORBIDDEN", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(prog="twin-wave4")
    modes = parser.add_subparsers(dest="mode", required=True)
    inspect_parser = modes.add_parser("inspect")
    inspect_parser.add_argument("input_dir", type=Path)
    agreement_parser = modes.add_parser("released-agreement")
    agreement_parser.add_argument("input_dir", type=Path)
    agreement_parser.add_argument("official_code_path", type=Path)
    args = parser.parse_args(arguments)
    try:
        pins = _load_repository_pins()
        if args.mode == "inspect":
            report = inspect_snapshot(args.input_dir, pins)
        else:
            report = audit_released_agreement(args.input_dir, pins, args.official_code_path)
    except InspectionError as error:
        print(f"twin-wave4: {error.code}", file=sys.stderr)
        return 2
    except Exception:
        if args.mode != "released-agreement":
            raise
        print("twin-wave4: AGREEMENT_AUDIT_FAILED", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
