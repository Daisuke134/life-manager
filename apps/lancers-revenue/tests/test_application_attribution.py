from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "skills/earn/lancers/scripts/application_loop.py"


def load():
    spec = importlib.util.spec_from_file_location("lancers_application_attribution_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ApplicationAttributionTests(unittest.TestCase):
    def test_seller_proof_exposes_stable_conversion_attribution_versions(self):
        proof = load()._seller_proof()

        self.assertEqual(proof["catalog_product_id"], "monthly-sns-content-ops-v1")
        self.assertEqual(proof["catalog_product_version"], 5)
        for field in ("profile_version", "proof_version", "price_version"):
            self.assertRegex(proof[field], r"^[0-9a-f]{64}$")
        self.assertEqual(len({proof["profile_version"], proof["proof_version"], proof["price_version"]}), 3)

    def test_attribution_append_is_idempotent_by_proposal_id(self):
        module = load()
        record = {
            "application_external_id": "27999999",
            "opportunity_external_id": "5609999",
            "proposal_version": "a" * 64,
            "profile_version": "b" * 64,
            "proof_version": "c" * 64,
            "price_version": "d" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "application-attribution.jsonl"
            self.assertTrue(module._record_attribution(path, record))
            self.assertFalse(module._record_attribution(path, record))
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["application_external_id"], "27999999")

    def test_verified_application_records_attribution_for_future_funnel_join(self):
        module = load()
        opportunity = {
            "schema_version": 1,
            "record_type": "lancers_public_opportunity",
            "platform": "lancers",
            "external_id": "5609998",
            "title": "業務システムの改善",
            "description": "業務フローを整理し、Webシステムを実装して納品します。",
            "url": "https://www.lancers.jp/work/detail/5609998",
            "category": "システム開発",
            "budget_type": "fixed",
            "budget_min_minor": 100000,
            "budget_max_minor": 300000,
            "currency": "JPY",
            "buyer_external_id": "buyer-5609998",
            "observed_at": "2026-09-18T00:00:00Z",
        }
        decision = {
            "request_id": "5609998",
            "business_class": "submit_required",
            "reason_codes": [],
            "proposal_text": "要件を整理し、画面設計、実装、動作確認、引き継ぎ資料まで一貫して納品します。" * 8,
            "price_jpy": 150000,
            "deliver_date": "2026-09-25",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = module._plan_and_submit(
                [opportunity], date(2026, 9, 18), root / "evidence",
                planner=lambda *_args: {"decisions": [decision]},
                safety_verifier=lambda *_args: {"safe_to_submit": True, "reason": "approved", "blocker_evidence": None},
                submitter=lambda **_kwargs: {"ok": True, "submitted": True, "application_verified": True, "project_id": "5609998", "provider_proposal_id": "27999998"},
                state_path=root / "application.json",
            )
            rows = [json.loads(line) for line in (root / "application-attribution.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(result.verified_count, 1)
        self.assertEqual(rows[0]["application_external_id"], "27999998")
        self.assertEqual(rows[0]["opportunity_external_id"], "5609998")


if __name__ == "__main__":
    unittest.main()
