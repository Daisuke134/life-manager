#!/usr/bin/env python3
"""Read-only validation of the pinned released Nature aggregate snapshot."""

from __future__ import annotations

import hashlib
import io
import json
import math
import posixpath
import re
import statistics
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any


DOI = "10.1038/s41586-026-10742-x"
TOLERANCE = 1e-10
REQUIRED_FILES = ("supplement.pdf", "fig1.xlsx", "fig2.xlsx", "fig3.xlsx")
PANEL_A_FIELDS = (
    "study",
    "reference_condition",
    "outcome.name",
    "condition.name",
    "estimate",
    "prediction",
    "group",
)
PANEL_B_FIELDS = (
    "model",
    "model_class",
    "estimate",
    "ci.lb",
    "ci.ub",
    "cor_raw",
    "cor_raw_ci.lb",
    "cor_raw_ci.ub",
)
PANEL_B_NUMERIC_FIELDS = PANEL_B_FIELDS[2:]
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS}
CELL_REF = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_ERROR_CELL = object()


class InspectionError(Exception):
    """A stable validation code without source-derived details."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise InspectionError(code)


def _finite_number(value: Any, code: str = "INVALID_NUMBER") -> float:
    if value is None or isinstance(value, bool):
        _fail(code)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        _fail(code)
    if not math.isfinite(number):
        _fail(code)
    return number


def _metadata_pins(nature: dict[str, Any]) -> dict[str, dict[str, Any]]:
    try:
        receipt = nature["execution_receipt"]
        file_rows = receipt["files"]
    except (KeyError, TypeError):
        _fail("INVALID_METADATA")
    if not isinstance(file_rows, list):
        _fail("INVALID_METADATA")
    pins: dict[str, dict[str, Any]] = {}
    for row in file_rows:
        if not isinstance(row, dict):
            _fail("INVALID_METADATA")
        name = row.get("name")
        byte_count = row.get("bytes")
        digest = row.get("sha256")
        if name in pins or name not in REQUIRED_FILES:
            _fail("INVALID_METADATA")
        if type(byte_count) is not int or byte_count < 0:
            _fail("INVALID_METADATA")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            _fail("INVALID_METADATA")
        pins[name] = {"bytes": byte_count, "sha256": digest.lower()}
    if set(pins) != set(REQUIRED_FILES):
        _fail("INVALID_METADATA")
    return pins


def _validate_bytes(input_dir: Path, pins: dict[str, dict[str, Any]]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    try:
        for name in REQUIRED_FILES:
            files[name] = (input_dir / name).read_bytes()
    except FileNotFoundError:
        _fail("MISSING_SOURCE_FILE")
    except OSError:
        _fail("SOURCE_READ_ERROR")

    for name in REQUIRED_FILES:
        data = files[name]
        expected = pins[name]
        if len(data) != expected["bytes"]:
            _fail("SOURCE_HASH_MISMATCH")
        if hashlib.sha256(data).hexdigest() != expected["sha256"]:
            _fail("SOURCE_HASH_MISMATCH")
    return files


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    except (ET.ParseError, OSError, RuntimeError):
        _fail("INVALID_WORKBOOK")
    output = []
    for item in root.findall("m:si", NS):
        output.append("".join((node.text or "") for node in item.findall(".//m:t", NS)))
    return output


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str | object | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "e":
        return _ERROR_CELL
    if cell_type == "inlineStr":
        inline = cell.find("m:is", NS)
        if inline is None:
            return None
        return "".join((node.text or "") for node in inline.findall(".//m:t", NS))
    value = cell.find("m:v", NS)
    if value is None or value.text is None:
        return None
    if cell_type == "s":
        try:
            index = int(value.text)
        except (ValueError, TypeError):
            _fail("INVALID_WORKBOOK")
        if index < 0 or index >= len(shared_strings):
            _fail("INVALID_WORKBOOK")
        return shared_strings[index]
    return value.text


def _column_number(letters: str) -> int:
    result = 0
    for letter in letters:
        result = result * 26 + (ord(letter) - ord("A") + 1)
    return result


def _read_sheet_rows(archive: zipfile.ZipFile, path: str, shared: list[str]) -> list[dict[int, str | object | None]]:
    try:
        root = ET.fromstring(archive.read(path))
    except (KeyError, ET.ParseError, OSError, RuntimeError):
        _fail("INVALID_WORKBOOK")
    rows: list[dict[int, str | object | None]] = []
    seen_references: set[str] = set()
    seen_row_numbers: set[int] = set()
    for row in root.findall(".//m:sheetData/m:row", NS):
        row_text = row.attrib.get("r")
        if row_text is None or not row_text.isdigit() or int(row_text) < 1:
            _fail("INVALID_WORKBOOK")
        row_number = int(row_text)
        if row_number in seen_row_numbers:
            _fail("INVALID_WORKBOOK")
        seen_row_numbers.add(row_number)
        cells: dict[int, str | object | None] = {}
        for cell in row.findall("m:c", NS):
            reference = cell.attrib.get("r")
            match = CELL_REF.fullmatch(reference or "")
            if match is None or int(match.group(2)) != row_number:
                _fail("INVALID_WORKBOOK")
            if reference in seen_references:
                _fail("DUPLICATE_CELL")
            seen_references.add(reference)
            column = _column_number(match.group(1))
            if column in cells:
                _fail("DUPLICATE_CELL")
            cells[column] = _cell_value(cell, shared)
        rows.append({-1: row_number, **cells})
    if not rows:
        _fail("MISSING_HEADER")
    rows.sort(key=lambda item: item[-1])
    return rows


def _workbook_sheet_paths(data: bytes) -> tuple[zipfile.ZipFile, dict[str, str], list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        _fail("INVALID_WORKBOOK")
    names = archive.namelist()
    if len(names) != len(set(names)):
        archive.close()
        _fail("INVALID_WORKBOOK")
    try:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ET.ParseError, OSError, RuntimeError):
        archive.close()
        _fail("INVALID_WORKBOOK")

    relation_targets: dict[str, str] = {}
    relation_types: dict[str, str] = {}
    for relation in relationships.findall(f"{{{PKG_REL_NS}}}Relationship"):
        identifier = relation.attrib.get("Id")
        target = relation.attrib.get("Target")
        relation_type = relation.attrib.get("Type", "")
        if not identifier or not target or identifier in relation_types:
            archive.close()
            _fail("INVALID_WORKBOOK")
        if relation.attrib.get("TargetMode") == "External":
            archive.close()
            _fail("INVALID_WORKBOOK")
        relation_types[identifier] = relation_type
        if relation_type.endswith("/worksheet"):
            target_path = target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
            target_path = posixpath.normpath(target_path)
            if not target_path.startswith("xl/"):
                archive.close()
                _fail("INVALID_WORKBOOK")
            relation_targets[identifier] = target_path

    sheet_paths: dict[str, str] = {}
    inventory: list[str] = []
    for sheet in workbook.findall(".//m:sheets/m:sheet", NS):
        name = sheet.attrib.get("name")
        identifier = sheet.attrib.get(f"{{{DOC_REL_NS}}}id")
        if not name or name in sheet_paths or not identifier:
            archive.close()
            _fail("INVALID_WORKBOOK")
        target = relation_targets.get(identifier)
        if target is None or not relation_types.get(identifier, "").endswith("/worksheet"):
            archive.close()
            _fail("INVALID_WORKBOOK")
        sheet_paths[name] = target
        inventory.append(name)
    if not inventory:
        archive.close()
        _fail("INVALID_WORKBOOK")
    return archive, sheet_paths, inventory


def _read_required_tables(data: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    archive, sheet_paths, _inventory = _workbook_sheet_paths(data)
    try:
        for target in sheet_paths.values():
            if target not in archive.namelist():
                _fail("MISSING_SHEET")
        for required_sheet in ("panelA", "panelB"):
            if required_sheet not in sheet_paths:
                _fail("MISSING_SHEET")
            if sheet_paths[required_sheet] not in archive.namelist():
                _fail("MISSING_SHEET")
        shared = _shared_strings(archive)
        panel_a = _table_records(_read_sheet_rows(archive, sheet_paths["panelA"], shared), PANEL_A_FIELDS)
        panel_b = _table_records(_read_sheet_rows(archive, sheet_paths["panelB"], shared), PANEL_B_FIELDS)
        return panel_a, panel_b, list(sheet_paths)
    finally:
        archive.close()


def _read_sheet_inventory(data: bytes) -> list[str]:
    archive, sheet_paths, inventory = _workbook_sheet_paths(data)
    try:
        members = set(archive.namelist())
        if any(target not in members for target in sheet_paths.values()):
            _fail("MISSING_SHEET")
        return inventory
    finally:
        archive.close()


def _required_text(value: str | object | None) -> str:
    if value is _ERROR_CELL:
        _fail("INVALID_CELL")
    if value is None or not isinstance(value, str) or not value.strip():
        _fail("MISSING_CELL")
    return value


def _required_number(value: str | object | None) -> float:
    if value is _ERROR_CELL:
        _fail("INVALID_CELL")
    if value is None or (isinstance(value, str) and not value.strip()):
        _fail("MISSING_CELL")
    number = _finite_number(value)
    if number < -1.0 or number > 1.0:
        _fail("INVALID_NUMBER")
    return number


def _table_records(
    rows: list[dict[int, str | object | None]], required_fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    header_row = next((row for row in rows if row[-1] == 1), None)
    if header_row is None:
        _fail("MISSING_HEADER")
    headers: dict[int, str] = {}
    seen_headers: set[str] = set()
    for column, value in header_row.items():
        if column == -1:
            continue
        if value is _ERROR_CELL or value is None or not isinstance(value, str):
            continue
        if not value.strip():
            continue
        if value in seen_headers:
            _fail("DUPLICATE_HEADER")
        seen_headers.add(value)
        headers[column] = value
    if any(field not in headers.values() for field in required_fields):
        _fail("MISSING_HEADER")
    field_columns = {field: next(column for column, name in headers.items() if name == field) for field in required_fields}

    records: list[dict[str, Any]] = []
    numeric_fields = {"estimate", "prediction"} if "prediction" in required_fields else set(PANEL_B_NUMERIC_FIELDS)
    for row in rows:
        if row[-1] == 1:
            continue
        if all(value is None for column, value in row.items() if column != -1):
            continue
        record: dict[str, Any] = {}
        for field, column in field_columns.items():
            if column not in row:
                _fail("MISSING_CELL")
            value = row[column]
            if field in numeric_fields:
                record[field] = _required_number(value) if field in {"estimate", "prediction"} else _required_panel_number(value)
            else:
                record[field] = _required_text(value)
        records.append(record)
    if not records:
        _fail("MISSING_CELL")
    return records


def _required_panel_number(value: str | object | None) -> float:
    if value is _ERROR_CELL:
        _fail("INVALID_CELL")
    if value is None or (isinstance(value, str) and not value.strip()):
        _fail("MISSING_CELL")
    return _finite_number(value)


def _validate_panel_a(rows: list[dict[str, Any]]) -> dict[str, Any]:
    directed: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    by_block: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    study_groups: dict[str, str] = {}
    groups = {"published": 0, "unpublished": 0}

    for row in rows:
        study = row["study"]
        outcome = row["outcome.name"]
        reference = row["reference_condition"]
        condition = row["condition.name"]
        if reference == condition:
            _fail("SELF_COMPARISON")
        group = row["group"]
        if group not in groups:
            _fail("INVALID_GROUP")
        previous_group = study_groups.setdefault(study, group)
        if previous_group != group:
            _fail("INCONSISTENT_STUDY_GROUP")
        groups[group] += 1
        key = (study, outcome, reference, condition)
        if key in directed:
            _fail("DUPLICATE_CONTRAST")
        directed[key] = row
        by_block[(study, outcome)].append(row)

    unordered: set[tuple[str, str, str, str]] = set()
    for key, row in directed.items():
        study, outcome, reference, condition = key
        reverse = directed.get((study, outcome, condition, reference))
        if reverse is None:
            _fail("MISSING_REVERSE")
        if abs(row["estimate"] + reverse["estimate"]) > TOLERANCE:
            _fail("REVERSE_MISMATCH")
        if abs(row["prediction"] + reverse["prediction"]) > TOLERANCE:
            _fail("REVERSE_MISMATCH")
        first, second = sorted((reference, condition))
        unordered.add((study, outcome, first, second))

    for block_rows in by_block.values():
        conditions = {row["reference_condition"] for row in block_rows}
        conditions.update(row["condition.name"] for row in block_rows)
        if len(block_rows) != len(conditions) * (len(conditions) - 1):
            _fail("INCOMPLETE_COMPARISONS")

    return {
        "studies": len(study_groups),
        "directed_contrasts": len(rows),
        "unordered_pairs": len(unordered),
        "study_outcome_blocks": len(by_block),
        "groups": groups,
    }


def _validate_panel_b(rows: list[dict[str, Any]], expected: Any) -> dict[str, Any]:
    if not isinstance(expected, list) or len(expected) != len(rows):
        _fail("RECEIPT_MISMATCH")
    actual_by_model: dict[str, dict[str, Any]] = {}
    for row in rows:
        model = row["model"]
        if model in actual_by_model:
            _fail("DUPLICATE_SUMMARY")
        actual_by_model[model] = row
    expected_by_model: dict[str, dict[str, Any]] = {}
    for row in expected:
        if not isinstance(row, dict) or not isinstance(row.get("model"), str):
            _fail("RECEIPT_MISMATCH")
        model = row["model"]
        if model in expected_by_model:
            _fail("RECEIPT_MISMATCH")
        expected_by_model[model] = row
    if set(actual_by_model) != set(expected_by_model):
        _fail("RECEIPT_MISMATCH")
    for model, actual in actual_by_model.items():
        published = expected_by_model[model]
        if actual["model_class"] != published.get("model_class"):
            _fail("RECEIPT_MISMATCH")
        for field in PANEL_B_NUMERIC_FIELDS:
            actual_number = _finite_number(actual.get(field), "INVALID_NUMBER")
            expected_number = _finite_number(published.get(field), "RECEIPT_MISMATCH")
            if abs(actual_number - expected_number) > TOLERANCE:
                _fail("RECEIPT_MISMATCH")
    if "gpt-4" not in actual_by_model:
        _fail("RECEIPT_MISMATCH")
    gpt4 = actual_by_model["gpt-4"]
    return {
        "model": "gpt-4",
        "adjusted_correlation": gpt4["estimate"],
        "adjusted_ci_lower": gpt4["ci.lb"],
        "adjusted_ci_upper": gpt4["ci.ub"],
        "raw_correlation": gpt4["cor_raw"],
        "raw_ci_lower": gpt4["cor_raw_ci.lb"],
        "raw_ci_upper": gpt4["cor_raw_ci.ub"],
    }


def _diagnostics(rows: list[dict[str, Any]], receipt: dict[str, Any]) -> dict[str, float]:
    predictions = [row["prediction"] for row in rows]
    estimates = [row["estimate"] for row in rows]
    mean_prediction = statistics.mean(predictions)
    mean_estimate = statistics.mean(estimates)
    covariance = sum(
        (prediction - mean_prediction) * (estimate - mean_estimate)
        for prediction, estimate in zip(predictions, estimates)
    )
    prediction_ss = sum((prediction - mean_prediction) ** 2 for prediction in predictions)
    estimate_ss = sum((estimate - mean_estimate) ** 2 for estimate in estimates)
    if prediction_ss == 0.0 or estimate_ss == 0.0:
        _fail("INVALID_DIAGNOSTICS")
    slope = covariance / prediction_ss
    computed = {
        "naive_all_directed_rows_pearson_r": covariance / math.sqrt(prediction_ss * estimate_ss),
        "naive_all_directed_rows_ols_slope": slope,
        "naive_all_directed_rows_ols_intercept": mean_estimate - slope * mean_prediction,
        "naive_all_directed_rows_rmse_scale0to1": math.sqrt(
            statistics.mean((prediction - estimate) ** 2 for prediction, estimate in zip(predictions, estimates))
        ),
    }
    for name, value in computed.items():
        expected = _finite_number(receipt.get(name), "INVALID_METADATA")
        if abs(value - expected) > TOLERANCE:
            _fail("RECEIPT_MISMATCH")
    return computed


def _source_metadata(
    nature: dict[str, Any],
    pins: dict[str, dict[str, Any]],
    actual_inventory: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    downloads = nature.get("source_downloads")
    if not isinstance(downloads, list):
        _fail("INVALID_METADATA")
    by_key: dict[str, dict[str, Any]] = {}
    for row in downloads:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            _fail("INVALID_METADATA")
        if row["key"] in by_key or not isinstance(row.get("url"), str):
            _fail("INVALID_METADATA")
        sheetnames = row.get("sheetnames")
        if not isinstance(sheetnames, list) or any(not isinstance(name, str) for name in sheetnames):
            _fail("INVALID_METADATA")
        by_key[row["key"]] = row
    if not {"fig1", "fig2", "fig3"}.issubset(by_key):
        _fail("INVALID_METADATA")
    supplement_url = nature.get("supplement_url")
    doi = nature.get("doi")
    version = nature.get("version")
    if not isinstance(supplement_url, str) or not isinstance(doi, str) or not isinstance(version, str):
        _fail("INVALID_METADATA")
    files = [
        {
            "name": "supplement.pdf",
            "url": supplement_url,
            **pins["supplement.pdf"],
        }
    ]
    inventory: dict[str, list[str]] = {}
    for key in ("fig1", "fig2", "fig3"):
        source = by_key[key]
        name = f"{key}.xlsx"
        files.append({"name": name, "url": source["url"], **pins[name]})
        if source["sheetnames"] != actual_inventory.get(key):
            _fail("RECEIPT_MISMATCH")
        inventory[key] = list(actual_inventory[key])
    return files, inventory


def inspect_snapshot(input_dir: Path, nature: dict[str, Any]) -> dict[str, Any]:
    """Validate pinned bytes, then inspect only Fig1 panelA and panelB aggregates."""
    if not isinstance(input_dir, Path) or not isinstance(nature, dict):
        _fail("INVALID_ARGUMENT")
    pins = _metadata_pins(nature)
    files = _validate_bytes(input_dir, pins)
    # No workbook is opened until every pinned source file above has passed.
    panel_a_rows, panel_b_rows, fig1_inventory = _read_required_tables(files["fig1.xlsx"])
    actual_inventory = {
        "fig1": fig1_inventory,
        "fig2": _read_sheet_inventory(files["fig2.xlsx"]),
        "fig3": _read_sheet_inventory(files["fig3.xlsx"]),
    }
    counts = _validate_panel_a(panel_a_rows)
    receipt = nature.get("execution_receipt")
    if not isinstance(receipt, dict):
        _fail("INVALID_METADATA")
    declared_effects = receipt.get("declared_distinct_effects")
    if type(declared_effects) is not int or declared_effects < 0:
        _fail("INVALID_METADATA")
    expected_counts = {
        "studies": receipt.get("primary_archive_studies"),
        "directed_contrasts": receipt.get("released_directed_contrasts_rows"),
        "groups": receipt.get("group_counts_rows"),
    }
    if counts["studies"] != expected_counts["studies"]:
        _fail("RECEIPT_MISMATCH")
    if counts["directed_contrasts"] != expected_counts["directed_contrasts"]:
        _fail("RECEIPT_MISMATCH")
    if counts["groups"] != expected_counts["groups"]:
        _fail("RECEIPT_MISMATCH")
    diagnostic_values = _diagnostics(panel_a_rows, receipt)
    published_gpt4 = _validate_panel_b(panel_b_rows, receipt.get("published_panelB_summaries"))
    source_files, inventory = _source_metadata(nature, pins, actual_inventory)

    return {
        "schema_version": 1,
        "source": {
            "doi": nature["doi"],
            "version": nature["version"],
            "files": source_files,
        },
        "counts": {**counts, "source_declared_distinct_effects": declared_effects},
        "diagnostics": {
            "kind": "naive pooled directed-row diagnostics; dependent and unadjusted",
            "pearson_r": diagnostic_values["naive_all_directed_rows_pearson_r"],
            "ols_slope": diagnostic_values["naive_all_directed_rows_ols_slope"],
            "ols_intercept": diagnostic_values["naive_all_directed_rows_ols_intercept"],
            "rmse_full_scale_0_to_1": diagnostic_values["naive_all_directed_rows_rmse_scale0to1"],
        },
        "published_summaries": {"gpt4": published_gpt4},
        "units": {
            "effect_scale": "full-scale signed difference in [-1, 1]",
            "direction": "condition minus reference",
            "percentage_points_multiplier": 100,
            "reversed_pairs": "both estimate and prediction change sign",
            "reverse_tolerance": TOLERANCE,
        },
        "scope": {
            "kind": "released aggregate inspection; no new model inference",
            "strictly_analyzed_sheets": ["fig1.panelA", "fig1.panelB"],
            "acquired_sheet_inventory": inventory,
            "supplement_pdf": "hash-verified only",
            "other_panels": "acquired and inventory-listed only; no strict row analysis",
        },
        "limitations": {
            "independence": (
                "Directed contrast rows are dependent within study and outcome; 3356 rows are not independent studies or trials. "
                f"The receipt declares {declared_effects} distinct treatment effects; that count is not independent replication."
            ),
            "method": "No original random-reference, attenuation-adjusted, study-bootstrap, or confidence-interval protocol is reproduced.",
            "prediction": "Published model summaries and released predictions are historical source data, not fresh predictions or independent proof.",
            "human_benefit": "No new human experiment, behavior outcome, or benefit is measured.",
            "redistribution_license": nature.get("source_data_redistribution_license", "NOT_VERIFIED_NO_CC_ASSUMED"),
            "source_bytes": "Original source data bytes are not redistributed by this inspector.",
        },
    }


def _load_repository_nature() -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[3]
    manifest_path = (
        repository_root
        / "docs/research/manager/evidence/artificial-societies-20261022/reuse.json"
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        nature = dict(manifest["nature"])
    except (OSError, ValueError, KeyError, TypeError):
        _fail("INVALID_METADATA")
    return nature


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("ERROR SNAPSHOT_INVALID", file=sys.stderr)
        return 2
    try:
        result = inspect_snapshot(Path(arguments[0]), _load_repository_nature())
        rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    except Exception:
        print("ERROR SNAPSHOT_INVALID", file=sys.stderr)
        return 2
    sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
