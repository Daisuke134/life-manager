"""Synthetic contract tests for the public aggregate inspector.

Fixtures below contain invented labels and numbers only. They never read or
copy the private Nature source files.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "products/manager/scripts/inspect_external_behavior_benchmark.py"
LEGACY_SCRIPT = (
    REPO_ROOT
    / "docs/research/manager/evidence/artificial-societies-20261022/inspect_source_data.py"
)
sys.path.insert(0, str(SCRIPT.parent))

import inspect_external_behavior_benchmark as inspector  # noqa: E402


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS}

PANEL_A_HEADERS = [
    "study",
    "reference_condition",
    "outcome.name",
    "condition.name",
    "estimate",
    "prediction",
    "group",
]
PANEL_B_HEADERS = [
    "model",
    "model_class",
    "estimate",
    "ci.lb",
    "ci.ub",
    "cor_raw",
    "cor_raw_ci.lb",
    "cor_raw_ci.ub",
]
REQUIRED_FILES = ("supplement.pdf", "fig1.xlsx", "fig2.xlsx", "fig3.xlsx")


@dataclass(frozen=True)
class CellSpec:
    value: object
    kind: str = "auto"


def make_panel_a_rows() -> list[dict[str, object]]:
    """Return complete directed contrasts for repeated labels in four scopes."""
    rows: list[dict[str, object]] = []
    blocks = [
        ("study-one", "outcome-a", "published", 0.4, 0.3),
        ("study-one", "outcome-b", "published", -0.2, -0.1),
        ("study-two", "outcome-a", "unpublished", 0.8, 0.5),
        ("study-two", "outcome-b", "unpublished", 0.1, -0.3),
    ]
    for study, outcome, group, estimate, prediction in blocks:
        rows.append(
            {
                "study": study,
                "reference_condition": "control",
                "outcome.name": outcome,
                "condition.name": "treatment",
                "estimate": estimate,
                "prediction": prediction,
                "group": group,
            }
        )
        rows.append(
            {
                "study": study,
                "reference_condition": "treatment",
                "outcome.name": outcome,
                "condition.name": "control",
                "estimate": -estimate,
                "prediction": -prediction,
                "group": group,
            }
        )
    return rows


def make_panel_b_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(8):
        model = "gpt-4" if index == 5 else f"model-{index}"
        rows.append(
            {
                "model": model,
                "model_class": "gpt",
                "estimate": 0.91 + index / 1000,
                "ci.lb": 0.80 + index / 1000,
                "ci.ub": 0.95 + index / 1000,
                "cor_raw": 0.85 + index / 1000,
                "cor_raw_ci.lb": 0.81 + index / 1000,
                "cor_raw_ci.ub": 0.88 + index / 1000,
            }
        )
    return rows


def column_name(number: int) -> str:
    output = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        output = chr(65 + remainder) + output
    return output


def write_xlsx(
    sheets: dict[str, tuple[list[str], list[dict[str, object]]]],
    *,
    duplicate_cell_reference: bool = False,
) -> bytes:
    """Build a deliberately small OOXML workbook with optional shared strings."""
    shared_values: list[str] = []
    shared_indexes: dict[str, int] = {}

    def collect(value: object) -> None:
        if isinstance(value, CellSpec):
            if value.kind == "inline" or value.kind in {"error", "number"}:
                return
            value = value.value
        if isinstance(value, str) and value not in shared_indexes:
            shared_indexes[value] = len(shared_values)
            shared_values.append(value)

    for headers, records in sheets.values():
        for value in headers:
            collect(value)
        for record in records:
            for value in record.values():
                collect(value)

    workbook = ET.Element(f"{{{MAIN_NS}}}workbook")
    sheet_list = ET.SubElement(workbook, f"{{{MAIN_NS}}}sheets")
    rel_root = ET.Element(f"{{{PKG_REL_NS}}}Relationships")
    for index, sheet_name in enumerate(sheets, start=1):
        ET.SubElement(
            sheet_list,
            f"{{{MAIN_NS}}}sheet",
            {
                "name": sheet_name,
                "sheetId": str(index),
                f"{{{DOC_REL_NS}}}id": f"rId{index}",
            },
        )
        ET.SubElement(
            rel_root,
            f"{{{PKG_REL_NS}}}Relationship",
            {
                "Id": f"rId{index}",
                "Type": f"{DOC_REL_NS}/worksheet",
                "Target": f"worksheets/sheet{index}.xml",
            },
        )
    ET.SubElement(
        rel_root,
        f"{{{PKG_REL_NS}}}Relationship",
        {
            "Id": "rId99",
            "Type": f"{DOC_REL_NS}/customXml",
            "Target": "../customXml/item1.xml",
        },
    )

    files: dict[str, bytes] = {
        "xl/workbook.xml": ET.tostring(workbook, encoding="utf-8", xml_declaration=True),
        "xl/_rels/workbook.xml.rels": ET.tostring(rel_root, encoding="utf-8", xml_declaration=True),
    }
    if shared_values:
        shared = ET.Element(f"{{{MAIN_NS}}}sst", {"count": str(len(shared_values)), "uniqueCount": str(len(shared_values))})
        for value in shared_values:
            si = ET.SubElement(shared, f"{{{MAIN_NS}}}si")
            ET.SubElement(si, f"{{{MAIN_NS}}}t").text = value
        files["xl/sharedStrings.xml"] = ET.tostring(shared, encoding="utf-8", xml_declaration=True)

    for sheet_index, (sheet_name, (headers, records)) in enumerate(sheets.items(), start=1):
        worksheet = ET.Element(f"{{{MAIN_NS}}}worksheet")
        sheet_data = ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetData")
        matrix = [headers] + [[record.get(header) for header in headers] for record in records]
        for row_index, values in enumerate(matrix, start=1):
            row_el = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(row_index)})
            for column_index, raw_value in enumerate(values, start=1):
                address = f"{column_name(column_index)}{row_index}"
                cell = raw_value if isinstance(raw_value, CellSpec) else CellSpec(raw_value)
                value = cell.value
                if (
                    sheet_name == "panelA"
                    and row_index == 2
                    and column_index == 1
                    and cell.kind == "auto"
                    and isinstance(value, str)
                ):
                    cell = CellSpec(value, "inline")
                if value is None and cell.kind == "auto":
                    ET.SubElement(row_el, f"{{{MAIN_NS}}}c", {"r": address})
                    continue
                cell_el = ET.SubElement(row_el, f"{{{MAIN_NS}}}c", {"r": address})
                if cell.kind == "inline":
                    cell_el.set("t", "inlineStr")
                    inline = ET.SubElement(cell_el, f"{{{MAIN_NS}}}is")
                    ET.SubElement(inline, f"{{{MAIN_NS}}}t").text = str(value)
                elif cell.kind == "error":
                    cell_el.set("t", "e")
                    ET.SubElement(cell_el, f"{{{MAIN_NS}}}v").text = str(value)
                elif cell.kind == "number":
                    ET.SubElement(cell_el, f"{{{MAIN_NS}}}v").text = str(value)
                elif isinstance(value, str):
                    cell_el.set("t", "s")
                    ET.SubElement(cell_el, f"{{{MAIN_NS}}}v").text = str(shared_indexes[value])
                else:
                    ET.SubElement(cell_el, f"{{{MAIN_NS}}}v").text = str(value)
                if duplicate_cell_reference and sheet_name == "panelA" and row_index == 2 and column_index == 1:
                    duplicate = ET.SubElement(row_el, f"{{{MAIN_NS}}}c", {"r": address})
                    ET.SubElement(duplicate, f"{{{MAIN_NS}}}v").text = "0"
        files[f"xl/worksheets/sheet{sheet_index}.xml"] = ET.tostring(
            worksheet, encoding="utf-8", xml_declaration=True
        )

    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def diagnostics(rows: list[dict[str, object]]) -> dict[str, float]:
    x = [float(row["prediction"]) for row in rows]
    y = [float(row["estimate"]) for row in rows]
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    variance_x = sum((a - mean_x) ** 2 for a in x)
    variance_y = sum((b - mean_y) ** 2 for b in y)
    return {
        "naive_all_directed_rows_pearson_r": covariance / math.sqrt(variance_x * variance_y),
        "naive_all_directed_rows_ols_slope": covariance / variance_x,
        "naive_all_directed_rows_ols_intercept": mean_y - (covariance / variance_x) * mean_x,
        "naive_all_directed_rows_rmse_scale0to1": math.sqrt(
            sum((a - b) ** 2 for a, b in zip(x, y)) / len(x)
        ),
    }


def make_snapshot(
    case: unittest.TestCase,
    *,
    panel_a_headers: list[str] | None = None,
    panel_a_rows: list[dict[str, object]] | None = None,
    panel_b_headers: list[str] | None = None,
    panel_b_rows: list[dict[str, object]] | None = None,
    missing_sheet: str | None = None,
    duplicate_cell_reference: bool = False,
    missing_file: str | None = None,
) -> tuple[Path, dict[str, object], list[dict[str, object]]]:
    rows = panel_a_rows if panel_a_rows is not None else make_panel_a_rows()
    models = panel_b_rows if panel_b_rows is not None else make_panel_b_rows()
    a_headers = panel_a_headers if panel_a_headers is not None else PANEL_A_HEADERS.copy()
    b_headers = panel_b_headers if panel_b_headers is not None else PANEL_B_HEADERS.copy()
    sheets: dict[str, tuple[list[str], list[dict[str, object]]]] = {
        "panelA": (a_headers, rows),
        "panelB": (b_headers, models),
        "panelC": (["model", "summary"], []),
    }
    if missing_sheet is not None:
        sheets.pop(missing_sheet, None)

    contents = {
        "supplement.pdf": b"synthetic-public-supplement-fixture",
        "fig1.xlsx": write_xlsx(sheets, duplicate_cell_reference=duplicate_cell_reference),
        # Their worksheet metadata is inventoried; their cells are not analyzed.
        "fig2.xlsx": write_xlsx({"fig2": (["inventory-only"], [])}),
        "fig3.xlsx": write_xlsx(
            {
                "panelA": ([], []),
                "panelB": ([], []),
                "panelC": ([], []),
                "panelD": ([], []),
            }
        ),
    }
    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(temporary.cleanup)
    input_dir = Path(temporary.name)
    file_pins = []
    for name, content in contents.items():
        file_pins.append({"name": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        if name != missing_file:
            (input_dir / name).write_bytes(content)

    receipt_rows = make_panel_a_rows()
    receipt_models = make_panel_b_rows()
    receipt: dict[str, object] = {
        "primary_archive_studies": len({row["study"] for row in receipt_rows}),
        "released_directed_contrasts_rows": len(receipt_rows),
        "declared_distinct_effects": 4,
        "group_counts_rows": {
            "published": sum(row["group"] == "published" for row in receipt_rows),
            "unpublished": sum(row["group"] == "unpublished" for row in receipt_rows),
        },
        **diagnostics(receipt_rows),
        "published_panelB_summaries": [
            {key: str(row[key]) for key in PANEL_B_HEADERS} for row in receipt_models
        ],
        "files": file_pins,
    }
    nature: dict[str, object] = {
        "doi": "10.1038/s41586-026-10742-x",
        "version": "2026-07-08 version of record",
        "supplement_url": "https://example.test/supplement.pdf",
        "source_data_redistribution_license": "NOT_VERIFIED_NO_CC_ASSUMED",
        "execution_receipt": receipt,
        "source_downloads": [
            {"key": "fig1", "url": "https://example.test/fig1.xlsx", "sheetnames": ["panelA", "panelB", "panelC"]},
            {"key": "fig2", "url": "https://example.test/fig2.xlsx", "sheetnames": ["fig2"]},
            {"key": "fig3", "url": "https://example.test/fig3.xlsx", "sheetnames": ["panelA", "panelB", "panelC", "panelD"]},
        ],
    }
    return input_dir, nature, rows


class ExternalBehaviorBenchmarkTests(unittest.TestCase):
    def assert_inspection_error(self, expected_code: str, action) -> None:
        with self.assertRaises(inspector.InspectionError) as raised:
            action()
        self.assertEqual(raised.exception.code, expected_code)

    def test_valid_snapshot_returns_only_aggregate_directional_counts(self) -> None:
        input_dir, nature, rows = make_snapshot(self)

        result = inspector.inspect_snapshot(input_dir, nature)
        encoded = json.dumps(result, allow_nan=False)
        self.assertEqual(result["counts"]["studies"], 2)
        self.assertEqual(result["counts"]["directed_contrasts"], 8)
        self.assertEqual(result["counts"]["unordered_pairs"], 4)
        self.assertEqual(result["counts"]["study_outcome_blocks"], 4)
        self.assertEqual(result["counts"]["source_declared_distinct_effects"], 4)
        self.assertEqual(result["counts"]["groups"], {"published": 4, "unpublished": 4})
        self.assertAlmostEqual(
            result["diagnostics"]["pearson_r"],
            diagnostics(rows)["naive_all_directed_rows_pearson_r"],
        )
        self.assertEqual(result["units"]["effect_scale"], "full-scale signed difference in [-1, 1]")
        self.assertEqual(result["units"]["direction"], "condition minus reference")
        self.assertEqual(result["units"]["percentage_points_multiplier"], 100)
        self.assertEqual(result["scope"]["strictly_analyzed_sheets"], ["fig1.panelA", "fig1.panelB"])
        self.assertIn("panelC", result["scope"]["acquired_sheet_inventory"]["fig1"])
        self.assertEqual(result["scope"]["acquired_sheet_inventory"]["fig3"], ["panelA", "panelB", "panelC", "panelD"])
        self.assertEqual(result["published_summaries"]["gpt4"]["raw_correlation"], 0.855)
        self.assertNotIn("study-one", encoded)
        self.assertNotIn("outcome-a", encoded)
        self.assertNotIn("control", encoded)
        self.assertNotIn(str(input_dir), encoded)
        self.assertIn("dependent", result["limitations"]["independence"])
        self.assertIn("NOT_VERIFIED_NO_CC_ASSUMED", result["limitations"]["redistribution_license"])

    def test_repository_loader_uses_the_existing_nature_metadata_shape(self) -> None:
        nature = inspector._load_repository_nature()

        self.assertEqual(nature["source_downloads"][0]["key"], "fig1")
        self.assertIn("execution_receipt", nature)

    def test_nonworksheet_relationships_do_not_break_pinned_workbook_inventory(self) -> None:
        input_dir, nature, _ = make_snapshot(self)

        result = inspector.inspect_snapshot(input_dir, nature)

        self.assertEqual(result["counts"]["directed_contrasts"], 8)

    def test_all_four_source_pins_are_checked_before_any_workbook_is_parsed(self) -> None:
        wrong_headers = PANEL_A_HEADERS.copy()
        wrong_headers[0] = "not-the-pinned-schema"
        input_dir, nature, _ = make_snapshot(
            self, panel_a_headers=wrong_headers, missing_file="fig3.xlsx"
        )

        self.assert_inspection_error(
            "MISSING_SOURCE_FILE", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_a_tampered_source_is_rejected_by_its_byte_pin(self) -> None:
        input_dir, nature, _ = make_snapshot(self)
        (input_dir / "fig1.xlsx").write_bytes(b"tampered and not a workbook")

        self.assert_inspection_error(
            "SOURCE_HASH_MISMATCH", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_missing_panel_a_header_is_rejected(self) -> None:
        input_dir, nature, _ = make_snapshot(self, panel_a_headers=PANEL_A_HEADERS[:-1])

        self.assert_inspection_error(
            "MISSING_HEADER", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_duplicate_header_is_rejected(self) -> None:
        headers = PANEL_A_HEADERS.copy()
        headers[-1] = headers[-2]
        input_dir, nature, _ = make_snapshot(self, panel_a_headers=headers)

        self.assert_inspection_error(
            "DUPLICATE_HEADER", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_duplicate_cell_reference_is_rejected(self) -> None:
        input_dir, nature, _ = make_snapshot(self, duplicate_cell_reference=True)

        self.assert_inspection_error(
            "DUPLICATE_CELL", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_missing_required_cell_is_not_treated_as_zero(self) -> None:
        rows = make_panel_a_rows()
        rows[0]["estimate"] = None
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)

        self.assert_inspection_error(
            "MISSING_CELL", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_nonfinite_nonnumeric_and_error_cells_are_rejected(self) -> None:
        bad_values = [
            CellSpec("not-a-number", "number"),
            CellSpec("NaN", "number"),
            CellSpec("Infinity", "number"),
        ]
        for bad_value in bad_values:
            with self.subTest(value=bad_value):
                rows = make_panel_a_rows()
                rows[0]["estimate"] = bad_value
                input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)
                self.assert_inspection_error(
                    "INVALID_NUMBER", lambda: inspector.inspect_snapshot(input_dir, nature)
                )
        rows = make_panel_a_rows()
        rows[0]["estimate"] = CellSpec("#VALUE!", "error")
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)
        self.assert_inspection_error(
            "INVALID_CELL", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_panel_b_sheet_is_required_and_receipt_values_are_checked(self) -> None:
        input_dir, nature, _ = make_snapshot(self, missing_sheet="panelB")

        self.assert_inspection_error(
            "MISSING_SHEET", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

        input_dir, nature, _ = make_snapshot(self)
        receipt = nature["execution_receipt"]
        receipt["published_panelB_summaries"][5]["cor_raw"] = "0.123"
        self.assert_inspection_error(
            "RECEIPT_MISMATCH", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_duplicate_directed_key_is_rejected_within_study_and_outcome(self) -> None:
        rows = make_panel_a_rows()
        rows.append(rows[0].copy())
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)

        self.assert_inspection_error(
            "DUPLICATE_CONTRAST", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_self_comparison_is_rejected(self) -> None:
        rows = make_panel_a_rows()
        rows[0]["condition.name"] = rows[0]["reference_condition"]
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)

        self.assert_inspection_error(
            "SELF_COMPARISON", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_missing_reverse_contrast_is_rejected(self) -> None:
        rows = make_panel_a_rows()
        rows.pop(1)
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)

        self.assert_inspection_error(
            "MISSING_REVERSE", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_reverse_estimate_and_prediction_must_have_opposite_signs(self) -> None:
        rows = make_panel_a_rows()
        rows[1]["estimate"] = rows[0]["estimate"]
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)

        self.assert_inspection_error(
            "REVERSE_MISMATCH", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_reverse_prediction_must_have_opposite_signs(self) -> None:
        rows = make_panel_a_rows()
        rows[1]["prediction"] = rows[0]["prediction"]
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)

        self.assert_inspection_error(
            "REVERSE_MISMATCH", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_a_study_cannot_change_group_between_rows(self) -> None:
        rows = make_panel_a_rows()
        rows[1]["group"] = "unpublished"
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)

        self.assert_inspection_error(
            "INCONSISTENT_STUDY_GROUP", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_signed_effects_outside_full_scale_range_are_rejected(self) -> None:
        rows = make_panel_a_rows()
        rows[0]["estimate"] = 1.000001
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)

        self.assert_inspection_error(
            "INVALID_NUMBER", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_each_study_outcome_block_has_a_complete_directed_graph(self) -> None:
        rows = make_panel_a_rows()
        triple = [
            {"study": "study-one", "reference_condition": "control", "outcome.name": "outcome-a", "condition.name": "treatment", "estimate": 0.4, "prediction": 0.3, "group": "published"},
            {"study": "study-one", "reference_condition": "treatment", "outcome.name": "outcome-a", "condition.name": "control", "estimate": -0.4, "prediction": -0.3, "group": "published"},
            {"study": "study-one", "reference_condition": "control", "outcome.name": "outcome-a", "condition.name": "alternate", "estimate": 0.2, "prediction": 0.1, "group": "published"},
            {"study": "study-one", "reference_condition": "alternate", "outcome.name": "outcome-a", "condition.name": "control", "estimate": -0.2, "prediction": -0.1, "group": "published"},
            {"study": "study-one", "reference_condition": "treatment", "outcome.name": "outcome-a", "condition.name": "alternate", "estimate": -0.2, "prediction": -0.2, "group": "published"},
            {"study": "study-one", "reference_condition": "alternate", "outcome.name": "outcome-a", "condition.name": "treatment", "estimate": 0.2, "prediction": 0.2, "group": "published"},
        ]
        # Keep only one complete reverse pair from the three-condition graph.
        rows = triple[:4] + rows[2:]
        input_dir, nature, _ = make_snapshot(self, panel_a_rows=rows)

        self.assert_inspection_error(
            "INCOMPLETE_COMPARISONS", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_panel_b_required_cells_are_not_silently_accepted(self) -> None:
        models = make_panel_b_rows()
        models[0]["cor_raw"] = None
        input_dir, nature, _ = make_snapshot(self, panel_b_rows=models)

        self.assert_inspection_error(
            "MISSING_CELL", lambda: inspector.inspect_snapshot(input_dir, nature)
        )

    def test_cli_hash_failure_is_sanitized_even_under_optimization(self) -> None:
        with tempfile.TemporaryDirectory(prefix="private-benchmark-input-") as directory:
            private_dir = Path(directory)
            (private_dir / "supplement.pdf").write_bytes(b"wrong source")
            process = subprocess.run(
                [sys.executable, "-B", "-O", str(SCRIPT), str(private_dir)],
                cwd=private_dir,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, "")
        self.assertEqual(process.stderr.strip(), "ERROR SNAPSHOT_INVALID")
        self.assertNotIn(str(private_dir), process.stderr)
        self.assertNotIn("study", process.stderr.lower())

    def test_legacy_entrypoint_delegates_from_an_unrelated_working_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="private-benchmark-input-") as directory:
            private_dir = Path(directory)
            process = subprocess.run(
                [sys.executable, "-B", str(LEGACY_SCRIPT), str(private_dir)],
                cwd=private_dir,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, "")
        self.assertEqual(process.stderr.strip(), "ERROR SNAPSHOT_INVALID")
        self.assertNotIn(str(private_dir), process.stderr)


if __name__ == "__main__":
    unittest.main()
