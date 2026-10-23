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

    def test_cli_failure_has_empty_stdout_and_sanitized_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pins = fixture(root)
            pins["files"][0]["sha256"] = "0" * 64
            pins_path = root / "pins.json"
            pins_path.write_text(json.dumps({"wave4_inspection": pins}))
            completed = subprocess.run([sys.executable, str(SCRIPT), "inspect", temp, "--pins", str(pins_path)], text=True, capture_output=True)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr.strip(), "twin-wave4: SOURCE_HASH_MISMATCH")
        self.assertNotIn(temp, completed.stderr)


if __name__ == "__main__":
    unittest.main()
