import csv
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import heartsteps_research as hr


class HeartStepsResearchH002H004Test(unittest.TestCase):
    def make_fixture(self, directory: Path) -> Path:
        path = directory / "suggestions.csv"
        header = ["user.index", "decision.index", "decision.index.nogap", "study.day.nogap",
                  "avail", "is.randomized", "send", "send.active", "send.sedentary",
                  "jbsteps30", "jbsteps30.zero", "jbsteps30pre", "jbsteps30pre.zero",
                  "dec.location.exact"]
        rows = [
            ["u1", "1", "1", "0", "TRUE", "TRUE", "TRUE", "TRUE", "FALSE", "123", "123", "10", "10", "PRIVATE_SENTINEL"],
            ["u1", "2", "2", "0", "TRUE", "TRUE", "FALSE", "FALSE", "FALSE", "NA", "0", "NA", "0", "HOME_SENTINEL"],
            ["u2", "1", "1", "1", "FALSE", "FALSE", "FALSE", "FALSE", "FALSE", "0", "0", "5", "5", "WORK_SENTINEL"],
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle); writer.writerow(header); writer.writerows(rows)
        return path

    def test_git_blob_hash_uses_git_blob_envelope(self):
        payload = b"abc\n"
        expected = hashlib.sha1(b"blob 4\0" + payload).hexdigest()
        self.assertEqual(hr.git_blob_sha1(payload), expected)

    def test_inspection_reports_shape_headers_missingness_and_safe_counts(self):
        with TemporaryDirectory() as tmp:
            report = hr.inspect_csv(self.make_fixture(Path(tmp)))
        self.assertEqual(report["row_count"], 3)
        self.assertEqual(report["column_count"], 14)
        self.assertEqual(report["missing_counts"]["jbsteps30"], 1)
        self.assertEqual(report["value_counts"]["avail"], {"FALSE": 1, "TRUE": 2})

    def test_sensitive_row_values_are_not_serialized(self):
        with TemporaryDirectory() as tmp:
            report = hr.build_report(self.make_fixture(Path(tmp)), source_url="https://example.org/pinned.csv")
        rendered = json.dumps(report, sort_keys=True)
        for secret in ("PRIVATE_SENTINEL", "HOME_SENTINEL", "WORK_SENTINEL"):
            self.assertNotIn(secret, rendered)

    def test_required_candidate_columns_are_checked_without_alias_guessing(self):
        with TemporaryDirectory() as tmp:
            report = hr.inspect_csv(self.make_fixture(Path(tmp)))
        status = hr.check_candidate_columns(report["headers"])
        self.assertTrue(status["present"]["user.index"])
        self.assertTrue(status["present"]["send.active"])
        self.assertFalse(status["present"]["sugg.decision.utime"])

    def test_duplicate_headers_are_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"; path.write_text("a,a\n1,2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate headers"):
                hr.inspect_csv(path)

    def test_validate_source_rejects_wrong_blob_or_size(self):
        with TemporaryDirectory() as tmp:
            path = self.make_fixture(Path(tmp)); payload = path.read_bytes()
            self.assertEqual(hr.validate_source(path, len(payload), hr.git_blob_sha1(payload))["bytes"], len(payload))
            with self.assertRaisesRegex(ValueError, "byte size"):
                hr.validate_source(path, len(payload) + 1, hr.git_blob_sha1(payload))
            with self.assertRaisesRegex(ValueError, "Git blob"):
                hr.validate_source(path, len(payload), "0" * 40)

    def test_written_reports_contain_only_aggregate_metadata(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); report = hr.build_report(self.make_fixture(root), source_url="https://example.org/pinned.csv")
            out = root / "out"; hr.write_reports(report, out)
            loaded = json.loads((out / "heartsteps_h002_h004.json").read_text(encoding="utf-8"))
            md = (out / "heartsteps_h002_h004.md").read_text(encoding="utf-8")
        self.assertEqual(loaded["inspection"]["row_count"], 3)
        self.assertIn("Raw participant rows are not included", md)
        self.assertNotIn("PRIVATE_SENTINEL", md)


if __name__ == "__main__":
    unittest.main()
