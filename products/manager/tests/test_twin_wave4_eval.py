"""Synthetic tests for the pinned Twin wave 4 structural inspection gate."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "twin_wave4_eval.py"
sys.path.insert(0, str(SCRIPT.parent))
import twin_wave4_eval as gate  # noqa: E402


def csv_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue().encode()


def fixture(root: Path, *, ids=("1", "2"), released_ids=None):
    released_ids = released_ids or ids
    catalog = [
        {"QuestionID": "QID1", "QuestionType": "MC", "source": "wave1_3_persona_json", "csv_columns": ["QID1"]},
        {"QuestionID": "QID1", "QuestionType": "Slider", "source": "wave4_Q_wave1_3_A", "csv_columns": ["QID1"]},
        {"QuestionID": "QID2", "QuestionType": "TE", "source": "wave4_Q_wave1_3_A", "csv_columns": ["QID2"]},
    ]
    mapping = [
        {"formatted_column": "Scale item", "QuestionID": "QID1", "catalog_csv_column": "QID1"},
        {"formatted_column": "Text item", "QuestionID": "QID2", "catalog_csv_column": "QID2"},
    ]
    desc = ["Twin response output", "description", "metadata", ""]
    data = {
        "catalog.json": json.dumps(catalog, separators=(",", ":")).encode(),
        "mapping.json": json.dumps(mapping, separators=(",", ":")).encode(),
        "history.csv": csv_bytes([["pid", "QID1", "QID2"], *[[i, "a", "x"] for i in ids]]),
        "target.csv": csv_bytes([["pid", "QID1", "QID2"], *[[i, "b", ""] for i in ids]]),
        "output.csv": csv_bytes([["TWIN_ID", "Scale item", "Text item", "allowed metadata"], desc, *[[i, "c", "free text", "z"] for i in released_ids]]),
    }
    for name, content in data.items():
        (root / name).write_bytes(content)
    role_paths = {
        "catalog.json": ("question_catalog_and_human_response_csv/question_catalog.json", "question_catalog"),
        "mapping.json": ("LLM_simulation_results/wave4_formatted_to_catalog_mapping.json", "official_mapping"),
        "history.csv": ("question_catalog_and_human_response_csv/wave1_3_response.csv", "wave1_3_history"),
        "target.csv": ("question_catalog_and_human_response_csv/wave4_response.csv", "wave4_target"),
        "output.csv": ("LLM_simulation_results/GPT4.1-mini-simulation-llm-vs-human/responses_llm_imputed_formatted.csv", "released_output_unverified"),
    }
    files = []
    for name, content in data.items():
        source_path, role = role_paths[name]
        entry = {"name": name, "source_path": source_path, "role": role, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        if name == "output.csv":
            entry["description_row"] = {"position": 2, "sha256": gate.description_row_hash(desc)}
        files.append(entry)
    return {"revision": gate.REVISION, "files": files}


class _MiniFrame:
    """Only the DataFrame surface used by the official scorer test double."""

    def __init__(self, data, index=None):
        self.data = data
        self.columns = list(data)
        self.index = list(range(len(next(iter(data.values()))))) if index is None else list(index)

    def __len__(self):
        return len(self.index)


class _MiniPandas:
    @staticmethod
    def DataFrame(data, index=None):
        return _MiniFrame(data, index)


class _MiniMetricTable:
    empty = False

    def __init__(self, row):
        self.iloc = [row]

    def __len__(self):
        return 1


class _OfficialMetricStub:
    """Boundary spy: scoring math remains owned by the pinned official code."""

    pd = _MiniPandas()

    def __init__(self):
        self.ranges = {
            "NOMINAL CHOICE": (1, 3),
            "SLIDER SCALE": (0, 10),
            "ORDINAL MATRIX": (1, 3),
            "NUMERIC ENTRY": (0, 100),
            "TEXT ENTRY": (0, 10),
        }
        self.tasks = {name: "synthetic task" for name in self.ranges}
        self.calls = []

    def get_default_column_ranges(self):
        return dict(self.ranges)

    def get_default_qid_to_task(self):
        return dict(self.tasks)

    def compute_column_mad(self, predictions, ground_truth, column_ranges):
        self.calls.append((tuple(predictions.columns), len(predictions), dict(column_ranges)))
        return _MiniMetricTable({
            "predictions vs. ground_truth": 0.125,
            "number of respondents": len(predictions),
        })


class _UnavailableOfficialMetricStub(_OfficialMetricStub):
    def get_default_column_ranges(self):
        return None


def agreement_fixture(root: Path, *, reverse=False, n=40, perfect=False, specials=True):
    catalog = [
        {"QuestionID": "QMC", "QuestionType": "MC", "source": "wave4_Q_wave1_3_A",
         "csv_columns": ["MC"], "Options": ["A", "B", "C"], "Settings": {"Selector": "SAVR"}},
        {"QuestionID": "QSL", "QuestionType": "Slider", "source": "wave4_Q_wave1_3_A",
         "csv_columns": ["SL"], "Range": {"Min": 0, "Max": 10, "Ticks": 10}},
        {"QuestionID": "QMX", "QuestionType": "Matrix", "source": "wave4_Q_wave1_3_A",
         "csv_columns": ["MX"], "Columns": ["Low", "Middle", "High"]},
        {"QuestionID": "QNUM", "QuestionType": "TE", "source": "wave4_Q_wave1_3_A",
         "csv_columns": ["NUM"], "Settings": {"Selector": "SL", "ContentType": "ValidNumber"}},
        {"QuestionID": "QFREE", "QuestionType": "TE", "source": "wave4_Q_wave1_3_A",
         "csv_columns": ["TEXT"], "Settings": {"Selector": "ML", "ContentType": ""}},
        {"QuestionID": "QNORANGE", "QuestionType": "MC", "source": "wave4_Q_wave1_3_A",
         "csv_columns": ["NORANGE"], "Options": ["A", "B", "C"], "Settings": {"Selector": "SAVR"}},
    ]
    mapping = [
        {"formatted_column": "Nominal Choice", "QuestionID": "QMC", "catalog_csv_column": "MC"},
        {"formatted_column": "Slider Scale", "QuestionID": "QSL", "catalog_csv_column": "SL"},
        {"formatted_column": "Ordinal Matrix", "QuestionID": "QMX", "catalog_csv_column": "MX"},
        {"formatted_column": "Numeric Entry", "QuestionID": "QNUM", "catalog_csv_column": "NUM"},
        {"formatted_column": "Text Entry", "QuestionID": "QFREE", "catalog_csv_column": "TEXT"},
        {"formatted_column": "No Range", "QuestionID": "QNORANGE", "catalog_csv_column": "NORANGE"},
    ]
    headers = ["pid", "MC", "SL", "MX", "NUM", "TEXT", "NORANGE"]
    output_header = ["TWIN_ID", "Nominal Choice", "Slider Scale", "Ordinal Matrix",
                     "Numeric Entry", "Text Entry", "No Range", "extra metadata"]
    history_rows = []
    target_rows = []
    output_rows = []
    for person in range(1, n + 1):
        if perfect:
            mc = str((person - 1) % 3 + 1)
            slider = str((person - 1) % 11)
            matrix = str((person - 1) % 3 + 1)
            numeric = str((person - 1) % 101)
            text = "SYNTHETIC_RESPONSE_" + str(person)
            no_range = str((person - 1) % 3 + 1)
            row = [str(person), mc, slider, matrix, numeric, text, no_range]
            history_rows.append(row)
            target_rows.append(row[:])
            output_rows.append(row[:])
            continue
        history_mc = "1"
        target_mc = "1" if person <= n // 2 else "2"
        output_mc = "1" if person <= n // 4 else "2"
        history_slider = "0"
        target_slider = "0" if person <= n // 4 else "1"
        output_slider = "0"
        history_matrix = "1"
        target_matrix = "1" if person <= n // 2 else "2"
        output_matrix = "1"
        history_numeric = "0"
        target_numeric = "0" if person <= n // 2 else "10"
        output_numeric = "0"
        history_text = "SYNTHETIC_RESPONSE_HISTORY_" + str(person)
        target_text = "SYNTHETIC_RESPONSE_TARGET_" + str(person)
        output_text = "SYNTHETIC_RESPONSE_RELEASE_" + str(person)
        history_no_range = "1"
        target_no_range = "2" if person <= n // 2 else "1"
        output_no_range = "1"
        if specials and person > n // 2:
            history_slider = "11"  # Outside the declared native slider range.
        history_rows.append([str(person), history_mc, history_slider, history_matrix,
                             history_numeric, history_text, history_no_range])
        target_rows.append([str(person), target_mc, target_slider, target_matrix,
                            target_numeric, target_text, target_no_range])
        output_rows.append([str(person), output_mc, output_slider, output_matrix,
                            output_numeric, output_text, output_no_range])
    if specials:
        # One missing target cell exercises a shared nonempty mask.
        history_rows.append([str(n + 1), "1", "0", "1", "0", "SYNTHETIC_RESPONSE_HISTORY_MISSING", "1"])
        target_rows.append([str(n + 1), "1", "", "1", "0", "SYNTHETIC_RESPONSE_TARGET_MISSING", "1"])
        output_rows.append([str(n + 1), "1", "0", "1", "0", "SYNTHETIC_RESPONSE_RELEASE_MISSING", "1"])
        # Invalid category/range codes are excluded from native comparison denominators.
        history_rows.append([str(n + 2), "99", "11", "9", "999", "SYNTHETIC_RESPONSE_HISTORY_INVALID", "1"])
        target_rows.append([str(n + 2), "1", "9", "3", "50", "SYNTHETIC_RESPONSE_TARGET_INVALID", "1"])
        output_rows.append([str(n + 2), "1", "10", "3", "60", "SYNTHETIC_RESPONSE_RELEASE_INVALID", "1"])
    if reverse:
        history_rows.reverse()
        target_rows.reverse()
        output_rows.reverse()
    description = ["Synthetic output", "description", "metadata", "", "", "", "", ""]
    data = {
        "catalog.json": json.dumps(catalog, separators=(",", ":")).encode(),
        "mapping.json": json.dumps(mapping, separators=(",", ":")).encode(),
        "history.csv": csv_bytes([headers, *history_rows]),
        "target.csv": csv_bytes([headers, *target_rows]),
        "output.csv": csv_bytes([output_header, description,
                                  *[[*row[:1], *row[1:6], row[6], "ignored"] for row in output_rows]]),
    }
    role_paths = {
        "catalog.json": ("question_catalog_and_human_response_csv/question_catalog.json", "question_catalog"),
        "mapping.json": ("LLM_simulation_results/wave4_formatted_to_catalog_mapping.json", "official_mapping"),
        "history.csv": ("question_catalog_and_human_response_csv/wave1_3_response.csv", "wave1_3_history"),
        "target.csv": ("question_catalog_and_human_response_csv/wave4_response.csv", "wave4_target"),
        "output.csv": ("LLM_simulation_results/GPT4.1-mini-simulation-llm-vs-human/responses_llm_imputed_formatted.csv", "released_output_unverified"),
    }
    files = []
    for name, content in data.items():
        (root / name).write_bytes(content)
        source_path, role = role_paths[name]
        entry = {"name": name, "source_path": source_path, "role": role,
                 "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        if name == "output.csv":
            entry["description_row"] = {"position": 2, "sha256": gate.description_row_hash(description)}
        files.append(entry)
    return {"revision": gate.REVISION, "files": files}


def _run_agreement_fixture(root: Path, pins):
    files = gate.load_verified_snapshot(root, pins)
    return gate._audit_snapshot_bytes(files, pins, _OfficialMetricStub())


def _rewrite_agreement_column(root: Path, pins, filename: str, column: str, values):
    rows = list(csv.reader(io.StringIO((root / filename).read_text(encoding="utf-8"), newline="")))
    start = 2 if filename == "output.csv" else 1
    position = rows[0].index(column)
    values = list(values)
    if len(values) != len(rows) - start:
        raise ValueError("fixture row count mismatch")
    for row, value in zip(rows[start:], values):
        row[position] = value
    encoded = csv_bytes(rows)
    (root / filename).write_bytes(encoded)
    pin = next(row for row in pins["files"] if row["name"] == filename)
    pin["bytes"] = len(encoded)
    pin["sha256"] = hashlib.sha256(encoded).hexdigest()
    if filename == "output.csv":
        pin["description_row"]["sha256"] = gate.description_row_hash(rows[1])
    return pins


class TwinWave4GateTests(unittest.TestCase):
    def test_gate_reports_aggregate_structure_and_unknown_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root)
            result = gate.inspect_snapshot(root, pins)
        self.assertEqual(result["status"], "INSPECTED")
        self.assertEqual(result["mapping"]["mapped_items"], 2)
        self.assertEqual(result["roles"]["released_output_unverified"]["extra_columns_excluded"], 2)
        self.assertEqual(result["roles"]["wave1_3_history"]["rows"], 2)
        self.assertEqual(result["ids"]["triple_intersection"], 2)
        self.assertIsNone(result["provenance"]["verified_generated_cells"])
        self.assertEqual(result["provenance"]["code"], "RELEASED_OUTPUT_PROVENANCE_UNVERIFIED")
        self.assertIsNone(result["accuracy"])
        serialized = json.dumps(result)
        self.assertNotIn("free text", serialized)
        self.assertNotIn('"1"', serialized)

    def test_hash_mismatch_precedes_csv_parsing_even_under_optimized_python(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root)
            (root / "history.csv").write_bytes(b'"unterminated')
            script = "import sys; sys.path.insert(0, %r); import twin_wave4_eval as g;\ntry: g.inspect_snapshot(__import__('pathlib').Path(%r), %r)\nexcept g.InspectionError as e: print(e.code)" % (str(SCRIPT.parent), temp, pins)
            completed = subprocess.run([sys.executable, "-O", "-c", script], text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), "SOURCE_HASH_MISMATCH")
        self.assertNotIn("CSV", completed.stderr)

    def test_duplicate_question_ids_are_resolved_by_source_type_and_column(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root)
            catalog, mapping, headers = gate.load_metadata(root, pins)
            items = gate.resolve_items(catalog, mapping, headers)
        self.assertEqual([item["question_type"] for item in items], ["Slider", "TE"])

    def test_duplicate_catalog_match_and_non_bijective_mapping_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root)
            catalog, mapping, headers = gate.load_metadata(root, pins)
            ambiguous = catalog + [{**catalog[1], "QuestionType": "Matrix"}]
            with self.assertRaises(gate.InspectionError) as raised:
                gate.resolve_items(ambiguous, mapping, headers)
            self.assertEqual(raised.exception.code, "CATALOG_AMBIGUOUS")
            duplicate_mapping = mapping + [mapping[0]]
            with self.assertRaises(gate.InspectionError) as raised:
                gate.resolve_items(catalog, duplicate_mapping, headers)
            self.assertEqual(raised.exception.code, "MAPPING_NOT_BIJECTIVE")

    def test_duplicate_csv_header_is_rejected_after_pinned_bytes_validate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root)
            history = csv_bytes([["pid", "QID1", "QID1"], ["1", "a", "x"]])
            (root / "history.csv").write_bytes(history)
            pin = next(f for f in pins["files"] if f["name"] == "history.csv")
            pin.update(bytes=len(history), sha256=hashlib.sha256(history).hexdigest())
            with self.assertRaises(gate.InspectionError) as raised:
                gate.inspect_snapshot(root, pins)
        self.assertEqual(raised.exception.code, "DUPLICATE_HEADER")

    def test_shuffled_ids_join_by_value_and_report_only_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root, ids=("1", "2"), released_ids=("2", "1"))
            result = gate.inspect_snapshot(root, pins)
        self.assertEqual(result["ids"]["triple_intersection"], 2)
        self.assertTrue(result["ids"]["join_verified"])
        self.assertNotIn("person_ids", result["ids"])

    def test_duplicate_and_blank_ids_are_typed_failures(self):
        for records, expected in [((("1", "a", "x"), ("1", "b", "y")), "DUPLICATE_ID"), ((("", "a", "x"),), "INVALID_ID")]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                pins = fixture(root)
                history = csv_bytes([["pid", "QID1", "QID2"], *records])
                (root / "history.csv").write_bytes(history)
                pin = next(f for f in pins["files"] if f["name"] == "history.csv")
                pin.update(bytes=len(history), sha256=hashlib.sha256(history).hexdigest())
                with self.assertRaises(gate.InspectionError) as raised:
                    gate.inspect_snapshot(root, pins)
                self.assertEqual(raised.exception.code, expected)

    def test_description_row_is_dropped_only_after_exact_contract_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root)
            result = gate.inspect_snapshot(root, pins)
            self.assertEqual(result["roles"]["released_output_unverified"]["rows"], 2)
            pins["files"][-1]["description_row"]["sha256"] = "0" * 64
            with self.assertRaises(gate.InspectionError) as raised:
                gate.inspect_snapshot(root, pins)
        self.assertEqual(raised.exception.code, "DESCRIPTION_ROW_MISMATCH")

    def test_forbidden_input_roles_are_rejected_even_with_valid_hashes(self):
        for invalid_role in ("full_persona", "wave4_target"):
            with self.subTest(role=invalid_role), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                pins = fixture(root)
                next(f for f in pins["files"] if f["name"] == "history.csv")["role"] = invalid_role
                with self.assertRaises(gate.InspectionError) as raised:
                    gate.inspect_snapshot(root, pins)
                self.assertEqual(raised.exception.code, "SOURCE_ROLE_FORBIDDEN")

    def test_missing_description_contract_never_discards_a_person_row(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root)
            data = csv_bytes([["TWIN_ID", "Scale item", "Text item", "allowed metadata"], ["1", "c", "free text", "z"]])
            (root / "output.csv").write_bytes(data)
            pin = next(f for f in pins["files"] if f["name"] == "output.csv")
            pin.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            with self.assertRaises(gate.InspectionError) as raised:
                gate.inspect_snapshot(root, pins)
        self.assertEqual(raised.exception.code, "DESCRIPTION_ROW_MISMATCH")

    def test_cli_rejects_custom_pins_override_with_empty_stdout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root)
            pins_path = root / "pins.json"
            pins_path.write_text(json.dumps({"wave4_inspection": pins}))
            completed = subprocess.run([sys.executable, str(SCRIPT), "inspect", temp, "--pins", str(pins_path)], text=True, capture_output=True)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr.strip(), "twin-wave4: PIN_OVERRIDE_FORBIDDEN")

    def test_cli_uses_repository_pins_for_synthetic_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture(Path(temp))
            completed = subprocess.run([sys.executable, str(SCRIPT), "inspect", temp], text=True, capture_output=True)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr.strip(), "twin-wave4: SOURCE_HASH_MISMATCH")

    def test_released_agreement_joins_ids_and_uses_one_common_native_mask(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = agreement_fixture(root)
            result = _run_agreement_fixture(root, pins)
        slider = next(item for item in result["agreement"]["items"] if item["item_code"] == "SL")
        comparison = slider["comparisons"]
        self.assertEqual(result["agreement"]["mask"]["mapped_slots"], 6 * 42)
        self.assertEqual(slider["common_nonempty_cells"], 41)
        self.assertEqual(slider["native_valid_cells"], 20)
        self.assertEqual(comparison["released_output_vs_wave4"]["n"], 20)
        self.assertEqual(comparison["wave1_3_history_vs_wave4"]["n"], 20)
        self.assertEqual(comparison["released_output_vs_wave4"]["matches"], 10)
        self.assertEqual(comparison["wave1_3_history_vs_wave4"]["matches"], 10)
        self.assertEqual(result["quality"]["native_range_invalid_cells_by_role"]["wave1_3_history"], 21)
        self.assertTrue(result["ids"]["join_verified"])
        self.assertTrue(result["agreement"]["mask"]["pair_denominators_equal"])
        self.assertEqual(set(result["source"]["input_sha256"]), {
            "question_catalog", "official_mapping", "wave1_3_history", "wave4_target", "released_output_unverified",
        })
        self.assertEqual(result["source"]["dataset_repository"], "LLM-Digital-Twin/Twin-2K-500")
        self.assertEqual(result["source"]["official_metric_revision"], "f1eed510c9a4fb47aaa9bb46e178aaa2d9224623")
        self.assertIsNone(result["accuracy"])

    def test_row_order_does_not_change_aggregate_agreement_or_mad(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "base"
            shuffled = Path(temp) / "shuffled"
            base.mkdir(); shuffled.mkdir()
            base_result = _run_agreement_fixture(base, agreement_fixture(base))
            shuffled_result = _run_agreement_fixture(shuffled, agreement_fixture(shuffled, reverse=True))
        self.assertEqual(base_result["agreement"], shuffled_result["agreement"])
        self.assertEqual(base_result["normalized_mad"], shuffled_result["normalized_mad"])

    def test_numeric_native_agreement_ignores_lexical_spelling(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = agreement_fixture(root, n=22, specials=False)
            pins = _rewrite_agreement_column(root, pins, "history.csv", "NUM", ["7"] * 22)
            pins = _rewrite_agreement_column(root, pins, "target.csv", "NUM", ["7.0"] * 22)
            pins = _rewrite_agreement_column(root, pins, "output.csv", "Numeric Entry", ["7.000"] * 22)
            pins = _rewrite_agreement_column(root, pins, "history.csv", "MC", ["1"] * 22)
            pins = _rewrite_agreement_column(root, pins, "target.csv", "MC", ["1"] * 22)
            pins = _rewrite_agreement_column(root, pins, "output.csv", "Nominal Choice", ["2"] * 22)
            pins = _rewrite_agreement_column(root, pins, "history.csv", "MX", ["1"] * 22)
            pins = _rewrite_agreement_column(root, pins, "target.csv", "MX", ["1"] * 22)
            pins = _rewrite_agreement_column(root, pins, "output.csv", "Ordinal Matrix", ["2"] * 22)
            result = _run_agreement_fixture(root, pins)
        numeric = next(item for item in result["agreement"]["items"] if item["item_code"] == "NUM")
        nominal = next(item for item in result["agreement"]["items"] if item["item_code"] == "MC")
        ordinal = next(item for item in result["agreement"]["items"] if item["item_code"] == "MX")
        self.assertEqual(numeric["native_valid_cells"], 22)
        for comparison in numeric["comparisons"].values():
            self.assertEqual(comparison["matches"], 22)
            self.assertEqual(comparison["rate"], 1.0)
        self.assertEqual(nominal["comparisons"]["released_output_vs_wave4"]["matches"], 0)
        self.assertEqual(nominal["comparisons"]["wave1_3_history_vs_wave4"]["matches"], 22)
        self.assertEqual(ordinal["comparisons"]["released_output_vs_wave4"]["matches"], 0)
        self.assertEqual(ordinal["comparisons"]["wave1_3_history_vs_wave4"]["matches"], 22)

    def test_zero_numeric_comparability_is_unscorable_not_privacy_suppressed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = agreement_fixture(root, n=30, specials=False)
            pins = _rewrite_agreement_column(root, pins, "output.csv", "Numeric Entry", ["101"] * 30)
            result = _run_agreement_fixture(root, pins)
        numeric = next(item for item in result["normalized_mad"]["items"] if item["item_code"] == "NUM")
        self.assertEqual(numeric["status"], "UNSCORABLE")
        self.assertEqual(numeric["reason"], "NO_COMMON_IN_OFFICIAL_RANGE_CELLS")
        self.assertFalse(numeric["suppressed"])
        self.assertEqual(numeric["common_native_valid_cells"], 30)
        self.assertEqual(numeric["common_numeric_cells"], 0)
        self.assertEqual(numeric["official_range_excluded_cells_by_role"]["released_output_unverified"], 30)
        self.assertEqual(numeric["value_unit"], "UNSPECIFIED_NATIVE_RESPONSE_UNIT")
        self.assertEqual(result["normalized_mad"]["numeric_scale_candidate_columns"], 2)
        self.assertEqual(result["normalized_mad"]["numeric_scale_scored_columns"], 1)

    def test_positive_small_numeric_comparability_is_privacy_suppressed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = agreement_fixture(root, n=30, specials=False)
            pins = _rewrite_agreement_column(
                root, pins, "output.csv", "Numeric Entry", ["5"] * 19 + ["101"] * 11
            )
            result = _run_agreement_fixture(root, pins)
        numeric = next(item for item in result["normalized_mad"]["items"] if item["item_code"] == "NUM")
        self.assertEqual(numeric["status"], "SUPPRESSED")
        self.assertEqual(numeric["reason"], "SMALL_AGGREGATE_SUPPRESSED")
        self.assertTrue(numeric["suppressed"])
        self.assertEqual(numeric["common_native_valid_cells"], 30)
        self.assertIsNone(numeric["common_numeric_cells"])
        self.assertEqual(result["normalized_mad"]["numeric_scale_candidate_columns"], 2)
        self.assertEqual(result["normalized_mad"]["numeric_scale_scored_columns"], 1)

    def test_official_mad_excludes_nominal_and_ordinal_codes_and_unranged_items(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = _run_agreement_fixture(root, agreement_fixture(root))
        mad_items = result["normalized_mad"]["items"]
        codes = {item["item_code"] for item in mad_items}
        self.assertEqual(codes, {"SL", "NUM"})
        self.assertEqual(result["normalized_mad"]["official_range_covered_columns"], 5)
        self.assertEqual(result["normalized_mad"]["no_official_range_columns"], 1)
        self.assertEqual(result["normalized_mad"]["numeric_scale_eligible_columns"], 2)
        self.assertEqual(mad_items[0]["output_vs_wave4_normalized_mad"], 0.125)
        self.assertEqual(result["normalized_mad"]["excluded_by_reason"], {
            "NO_OFFICIAL_RANGE": 1,
            "NO_NUMERIC_INTERVAL_METADATA": 1,
            "NOMINAL_MC_EXCLUDED": 1,
            "ORDINAL_MATRIX_EXCLUDED": 1,
        })
        self.assertNotIn("MC", codes)
        self.assertNotIn("MX", codes)
        self.assertNotIn("NORANGE", codes)

    def test_perfect_agreement_never_promotes_output_provenance_or_scientific_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = agreement_fixture(root, n=24, perfect=True, specials=False)
            result = _run_agreement_fixture(root, pins)
        self.assertEqual(result["agreement"]["comparisons"]["released_output_vs_wave4"]["rate"], 1.0)
        self.assertEqual(
            result["agreement"]["comparisons"]["released_output_vs_history"]["matches"],
            result["agreement"]["comparisons"]["released_output_vs_history"]["n"],
        )
        self.assertEqual(result["provenance"]["code"], "RELEASED_OUTPUT_PROVENANCE_UNVERIFIED")
        self.assertEqual(result["provenance"]["generated_cell_provenance"], "UNVERIFIED")
        self.assertIsNone(result["provenance"]["verified_generated_cells"])
        self.assertIsNone(result["provenance"]["expected_eligible_cells"])
        self.assertEqual(result["provenance"]["model_training_exposure"], "UNKNOWN")
        self.assertIsNone(result["predictive_accuracy"])
        self.assertFalse(result["scientific_pass"])

    def test_unavailable_official_definitions_leave_numeric_scores_null(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = agreement_fixture(root)
            files = gate.load_verified_snapshot(root, pins)
            result = gate._audit_snapshot_bytes(files, pins, _UnavailableOfficialMetricStub())
        self.assertEqual(result["agreement"]["mask"]["common_native_valid_cells"], 228)
        self.assertEqual(result["normalized_mad"]["status"], "UNAVAILABLE")
        self.assertEqual(result["normalized_mad"]["reason"], "OFFICIAL_METRIC_UNAVAILABLE")
        self.assertIsNone(result["normalized_mad"]["numeric_scale_eligible_columns"])
        self.assertEqual(result["normalized_mad"]["items"], [])

    def test_private_values_and_small_aggregates_are_suppressed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = agreement_fixture(root, n=2, specials=False)
            result = _run_agreement_fixture(root, pins)
        serialized = json.dumps(result, sort_keys=True)
        self.assertNotIn("SYNTHETIC_RESPONSE_", serialized)
        self.assertNotIn('"pid"', serialized)
        self.assertNotIn('"TWIN_ID"', serialized)
        self.assertIsNone(result["agreement"]["comparisons"]["released_output_vs_wave4"]["n"])
        self.assertTrue(result["agreement"]["comparisons"]["released_output_vs_wave4"]["suppressed"])

    def test_bad_official_source_hash_fails_before_snapshot_read_or_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "imported"
            code = root / "untrusted.py"
            code.write_text("from pathlib import Path\nPath(%r).write_text('loaded')\n" % str(marker))
            with self.assertRaises(gate.InspectionError) as raised:
                gate.audit_released_agreement(root / "missing-snapshot", {}, code)
        self.assertEqual(raised.exception.code, "OFFICIAL_CODE_HASH_MISMATCH")
        self.assertFalse(marker.exists())

    def test_optimized_cli_fails_closed_on_bad_official_source_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            code = root / "untrusted.py"
            code.write_text("raise RuntimeError('must not import')\n")
            completed = subprocess.run(
                [sys.executable, "-O", str(SCRIPT), "released-agreement", str(root / "missing-snapshot"), str(code)],
                text=True, capture_output=True,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr.strip(), "twin-wave4: OFFICIAL_CODE_HASH_MISMATCH")


if __name__ == "__main__":
    unittest.main()
