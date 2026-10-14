from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("verify_gate13.py")
SPEC = importlib.util.spec_from_file_location("verify_gate13", MODULE_PATH)
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verify
SPEC.loader.exec_module(verify)


class Gate13VerifierTest(unittest.TestCase):
    def test_verifier_recomputes_complete_truthful_result_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_names = list(verify.experiment_attribution.REQUIRED_METRICS)
            results = []
            for name in result_names:
                results.append({
                    "metric_name": name, "status": "not_mature", "value": None,
                    "unit": "count", "source": "source", "attribution_class": "unknown",
                    "confidence": 0.0, "window_start": "2026-08-01T20:15:00Z",
                    "window_end": "2026-08-01T20:30:00Z", "evidence_refs": ["e"],
                    "null_reason": "not_mature", "model": None,
                })
            for name, reason in (
                ("actual_cost_usd", "publication_scoped_cost_evidence_unavailable"),
                ("human_interventions", "publication_scoped_intervention_evidence_unavailable"),
            ):
                metric = next(row for row in results if row["metric_name"] == name)
                metric.update({"status": "unknown", "null_reason": reason})
            click = next(row for row in results
                         if row["metric_name"] == "qualified_clicks")
            click.update({"status": "observed", "value": 0,
                          "attribution_class": "deterministic",
                          "confidence": 1.0, "null_reason": None})
            snapshot = {
                "schema_version": "marketing.experiment-attribution.v2",
                "attribution_id": verify.experiment_attribution.stable_id(
                    "attribution", ["publication.abc", "2026-08-01T20:30:00Z"]),
                "observed_at": "2026-08-01T20:30:00Z", "publish_key": "publication.abc",
                "experiment_id": "experiment.one", "creative_id": "creative.one",
                "product_id": "ebook-ja", "account_id": "account.one",
                "hook_id": "hook.one", "renderer_id": "renderer.one",
                "attribution_token": "ej_token", "postiz_post_id": "postiz-1",
                "native_post_id": "native-1", "native_post_url": "https://example.test/1",
                "published_at": "2026-08-01T20:15:00Z", "results": results,
            }
            ledger = root / "ledger.jsonl"
            ledger.write_text(json.dumps(snapshot) + "\n")
            evidence = root / "evidence.json"
            evidence.write_text(json.dumps({
                "status": "verified", "attribution_id": snapshot["attribution_id"],
                "click_query": {"status": "available", "count": 0},
            }))
            report = verify.verify_gate13(ledger, evidence)
            self.assertTrue(report["gate_pass"])
            self.assertEqual(report["result_records"], 12)
            self.assertEqual(report["fabricated_zero_count"], 0)
            self.assertIn("actual_cost_usd", report["unknown_metrics"])
            self.assertIn("human_interventions", report["unknown_metrics"])
            self.assertEqual(
                report["unknown_metric_reasons"]["actual_cost_usd"],
                "publication_scoped_cost_evidence_unavailable",
            )
            self.assertEqual(
                report["unknown_metric_reasons"]["human_interventions"],
                "publication_scoped_intervention_evidence_unavailable",
            )


if __name__ == "__main__":
    unittest.main()
