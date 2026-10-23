import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "public_event_forecast.py"
sys.path.insert(0, str(SCRIPT.parent))
import public_event_forecast as forecast


class PublicEventForecastTests(unittest.TestCase):
    def payload(self, p=0.4):
        contract = forecast.fixed_contract()
        payload = {
            "schema": "manager.public-event-forecast.v1",
            "case_id": contract["case_id"],
            "target_id": contract["target_id"],
            "protocol_id": contract["protocol_id"],
            "protocol_sha256": forecast.protocol_digest(),
            "event_kind": contract["event_kind"],
            "event_schedule": contract["event_schedule"],
            "cutoff": contract["cutoff"],
            "resolution_deadline": contract["resolution_deadline"],
            "question": contract["question"],
            "outcome_rule": contract["outcome_rule"],
            "context_manifest": {
                "source_hashes": copy.deepcopy(forecast.PINNED_SOURCE_HASHES),
                "context_digest": forecast.context_digest(forecast.PINNED_SOURCE_HASHES),
                "sources": copy.deepcopy(forecast.PINNED_CONTEXT_SOURCES),
            },
            "predictor": {"kind": "manual", "id": "synthetic-test", "procedure_sha256": "a" * 64},
            "prediction": {"p": p, "unit": "probability-0-to-1", "target_id": contract["target_id"]},
            "baselines": {
                "persistence": {"p": 0.0, "rule": "latest upper unchanged at 4.00 percent"},
                "historical_frequency": {"p": 0.25, "rule": "(0+1)/(2+2); 0 cuts / 2 transitions / 3 values", "cuts": 0, "transitions": 2, "values": 3},
                "history_source_hashes": copy.deepcopy(forecast.PINNED_HISTORY_HASHES),
            },
            "scoring": contract["scoring"],
            "integrity": {"canonicalization": forecast.CANONICALIZATION},
        }
        payload["baselines"]["baseline_digest"] = forecast.baseline_digest(payload["baselines"])
        return payload

    def test_freeze_is_content_addressed_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "new-store"
            digest = forecast.freeze_forecast(self.payload(), store)
            raw = (store / f"{digest}.json").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            self.assertEqual(forecast.read_forecast(store, digest), self.payload())
            with self.assertRaises(forecast.ForecastError) as error:
                forecast.freeze_forecast(self.payload(), store)
            self.assertEqual(error.exception.code, "STORE_ALREADY_EXISTS")
            self.assertEqual((store / f"{digest}.json").read_bytes(), raw)

    def test_freeze_rejects_boolean_and_nonfinite_probability(self):
        for p in (True, float("nan"), float("inf"), -0.01, 1.01):
            with self.subTest(p=p), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(forecast.ForecastError) as error:
                    forecast.freeze_forecast(self.payload(p), Path(tmp) / "store")
                self.assertEqual(error.exception.code, "INVALID_PROBABILITY")

    def test_freeze_rejects_context_hash_or_fixed_contract_mismatch(self):
        bad = self.payload()
        bad["context_manifest"]["source_hashes"] = {"calendar": "0" * 64}
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(forecast.ForecastError) as error:
            forecast.freeze_forecast(bad, Path(tmp) / "store")
        self.assertEqual(error.exception.code, "CONTEXT_HASH_MISMATCH")
        bad = self.payload()
        bad["cutoff"] = "2026-10-27T00:00:00Z"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(forecast.ForecastError) as error:
            forecast.freeze_forecast(bad, Path(tmp) / "store")
        self.assertEqual(error.exception.code, "FIXED_CONTRACT_MISMATCH")

    def test_freeze_rejects_post_cutoff_context_and_changed_baseline_hash(self):
        trusted_before = (copy.deepcopy(forecast.PINNED_CONTEXT_SOURCES), copy.deepcopy(forecast.PINNED_SOURCE_HASHES), copy.deepcopy(forecast.PINNED_HISTORY_HASHES))
        bad = self.payload()
        bad["context_manifest"]["sources"][0]["observed_at"] = "2026-10-27T00:00:00Z"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(forecast.ForecastError) as error:
            forecast.freeze_forecast(bad, Path(tmp) / "store")
        self.assertEqual(error.exception.code, "CONTEXT_AFTER_CUTOFF")
        self.assertEqual((forecast.PINNED_CONTEXT_SOURCES, forecast.PINNED_SOURCE_HASHES, forecast.PINNED_HISTORY_HASHES), trusted_before)
        bad = self.payload()
        bad["baselines"]["history_source_hashes"] = {"tampered": "0" * 64}
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(forecast.ForecastError) as error:
            forecast.freeze_forecast(bad, Path(tmp) / "store")
        self.assertEqual(error.exception.code, "BASELINE_HASH_MISMATCH")

    def test_correction_rule_is_part_of_fixed_protocol_and_payload_digest(self):
        payload = self.payload()
        self.assertEqual(payload["protocol_sha256"], forecast.protocol_digest())
        self.assertEqual(payload["outcome_rule"]["primary_version_rule"], "deadline-current-same-meeting-official-statement-after-explicit-corrections")
        self.assertEqual(payload["outcome_rule"]["initial_version_diagnostic"], "preserve-first-publication-bytes-and-report-value-separately")
        self.assertEqual(payload["outcome_rule"]["post_deadline_correction"], "append-annotation-only-never-overwrite-primary")
        changed_contract = copy.deepcopy(forecast.fixed_contract())
        changed_contract["outcome_rule"]["post_deadline_correction"] = "overwrite-primary"
        self.assertNotEqual(forecast.protocol_digest(), forecast.canonical_digest(changed_contract))
        changed = copy.deepcopy(payload)
        changed["outcome_rule"]["post_deadline_correction"] = "overwrite-primary"
        self.assertNotEqual(forecast.canonical_digest(payload), forecast.canonical_digest(changed))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(forecast.ForecastError) as error:
            forecast.freeze_forecast(changed, Path(tmp) / "store")
        self.assertEqual(error.exception.code, "FIXED_CONTRACT_MISMATCH")

    def test_history_counts_match_fixed_three_statement_sequence(self):
        result = forecast.history_change_summary(["3.75", "3.75", "4.00"])
        self.assertEqual(result, {"cuts": 0, "transitions": 2, "values": 3, "p": 0.25})

    def test_payload_rejects_self_consistent_but_wrong_historical_cut_count(self):
        bad = self.payload()
        bad["baselines"]["historical_frequency"] = {
            "p": 0.5, "rule": "(1+1)/(2+2); 1 cuts / 2 transitions / 3 values",
            "cuts": 1, "transitions": 2, "values": 3,
        }
        bad["baselines"]["baseline_digest"] = forecast.baseline_digest(bad["baselines"])
        with self.assertRaises(forecast.ForecastError) as error:
            forecast.validate_payload(bad)
        self.assertEqual(error.exception.code, "INVALID_BASELINE")

    def test_payload_change_gets_a_distinct_digest(self):
        self.assertNotEqual(forecast.canonical_digest(self.payload(0.4)), forecast.canonical_digest(self.payload(0.5)))

    def test_preflight_rejects_same_length_tampering_before_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp)
            for row in forecast.PINNED_SOURCES.values():
                (source_dir / row["file"]).write_bytes(b"x" * row["bytes"])
            with self.assertRaises(forecast.ForecastError) as error:
                forecast.preflight_official_context(source_dir)
            self.assertEqual(error.exception.code, "SOURCE_HASH_MISMATCH")

    def test_cli_errors_are_sanitized_and_return_exit_two(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = forecast.main(["freeze", "--payload-file", "/private/not-present.json", "--store", "/tmp/not-created"])
        self.assertEqual(result, 2)
        self.assertEqual(stderr.getvalue(), "forecast-check failed: PAYLOAD_READ_FAILED\n")
        self.assertNotIn("/private", stderr.getvalue())

    def test_json_loader_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(forecast.ForecastError) as error:
                forecast.strict_json_loads(raw)
            expected = "DUPLICATE_JSON_KEY" if raw == b'{"a":1,"a":2}' else "NONFINITE_JSON_NUMBER"
            self.assertEqual(error.exception.code, expected)

    def test_store_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(forecast.ForecastError) as error:
            forecast.freeze_forecast(self.payload(), Path(tmp) / ".." / "escape")
        self.assertEqual(error.exception.code, "UNSAFE_STORE_PATH")

    def test_store_rejects_existing_directory_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "existing"
            existing.mkdir()
            with self.assertRaises(forecast.ForecastError) as error:
                forecast.freeze_forecast(self.payload(), existing)
            self.assertEqual(error.exception.code, "STORE_ALREADY_EXISTS")
            store = Path(tmp) / "store"
            store.mkdir()
            digest = forecast.canonical_digest(self.payload())
            target = Path(tmp) / "target"
            target.write_text("{}")
            (store / f"{digest}.json").symlink_to(target)
            with self.assertRaises(forecast.ForecastError) as error:
                forecast.read_forecast(store, digest)
            self.assertEqual(error.exception.code, "UNSAFE_RECORD_PATH")

    def test_attestation_rejects_wrong_repo_and_late_server_merge_time(self):
        record = self.payload()
        with self.assertRaises(forecast.ForecastError) as error:
            forecast.verify_github_pr_lock(record, "other/repository", 1)
        self.assertEqual(error.exception.code, "GITHUB_TARGET_REJECTED")
        late_pr = {"number": 1, "merged": True, "merged_at": "2026-10-27T00:00:00Z", "merge_commit_sha": "a" * 40, "base": {"repo": {"full_name": forecast.REPO}, "ref": "main"}}
        with patch.object(forecast, "_github_get", return_value=(late_pr, forecast._parse_time("2026-10-27T00:01:00Z"))):
            result = forecast.verify_github_pr_lock(record, forecast.REPO, 1)
        self.assertEqual(result["status"], "ATTESTATION_UNAVAILABLE")
        self.assertEqual(result["reason"], "MERGED_AFTER_CUTOFF")

    def test_attestation_rejects_wrong_base_branch(self):
        record = self.payload()
        wrong_base = {"number": 1, "merged": True, "merged_at": "2026-10-20T00:00:00Z", "merge_commit_sha": "a" * 40, "base": {"repo": {"full_name": forecast.REPO}, "ref": "release"}}
        with patch.object(forecast, "_github_get", return_value=(wrong_base, forecast._parse_time("2026-10-20T00:01:00Z"))):
            result = forecast.verify_github_pr_lock(record, forecast.REPO, 1)
        self.assertEqual(result["reason"], "WRONG_PR_BASE")

    def test_attestation_without_live_official_readback_is_never_verified(self):
        assessment = forecast.attestation_assessment(None)
        self.assertEqual(assessment["status"], "LOCAL_RECORD_ONLY")
        forged = {"verified": True, "merged_at": "2026-10-20T00:00:00Z"}
        self.assertEqual(forecast.attestation_assessment(forged)["status"], "LOCAL_RECORD_ONLY")

    def test_missing_outcome_remains_unavailable_without_scoring(self):
        self.assertIsNone(forecast.resolved_binary_outcome("OUTCOME_UNAVAILABLE", None))
        self.assertEqual(forecast.resolved_binary_outcome("RESOLVED", 0), 0)

    def test_rate_reader_uses_the_final_range_after_a_change_size(self):
        synthetic = b"<p>The Committee decided to raise the target range for the federal funds rate by 1/4 percentage point to 3-3/4 to 4 percent.</p>"
        self.assertEqual(forecast._statement_upper(synthetic), "4.00")


if __name__ == "__main__":
    unittest.main()
