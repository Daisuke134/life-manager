"""E03: synthetic scenarios, observed bytes and model forecasts never share evidentiary rank."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import nan
import unittest

from manager_core.evidence_types import SyntheticScenario, ObservedSnapshot, Prediction
from manager_core.models.source import Source
from manager_core.collaboration import PublicFact, PlannerContext, render_prompt

NOW = datetime(2026, 10, 22, 13, tzinfo=timezone.utc)


def source(source_id="official:test", payload=b"official byte fixture", *, stale=False):
    return Source(
        source_id=source_id, url="https://example.org/official-not-fetched",
        license_id="test-license", rights="allowed_with_conditions",
        content_sha256=sha256(payload).hexdigest(),
        retrieved_at=NOW-timedelta(hours=72) if stale else NOW,
        privacy_class="public_nonpersonal",
    )


class ObservationProvenanceContract(unittest.TestCase):
    def test_synthetic_person_not_castable_as_observed_public_fact(self):
        s=source("synthetic:case-1")
        with self.assertRaises(ValueError):
            PublicFact(s, "fictional advice user")
        scenario=PublicFact(s, "fictional advice user", source_kind="SYNTHETIC_SCENARIO")
        context=PlannerContext("A fictional case", (scenario,), NOW)
        p=render_prompt(context)
        self.assertIn('"source_kind": "SYNTHETIC_SCENARIO"',p)
        self.assertIn("SYNTHETIC",p)
        self.assertNotIn("AUTHORIZED_REAL_OBSERVATION",p)

    def test_public_fact_cannot_claim_synthetic_kind(self):
        with self.assertRaises(ValueError):
            PublicFact(source("official:public"), "Published public quote", source_kind="SYNTHETIC_SCENARIO")

    def test_public_observed_content_requires_matching_actual_bytes(self):
        raw=b"Real downloaded bytes need external-origin validation later"
        s=source("official:public", raw)
        record=ObservedSnapshot.from_bytes(s, raw, NOW)
        self.assertEqual(record.body_sha256, sha256(raw).hexdigest())
        self.assertFalse(record.origin_verified)
        self.assertEqual(record.status,"CONTENT_HASH_MATCH_ORIGIN_UNVERIFIED")
        self.assertEqual(record.proof_level,"P0")
        self.assertFalse(record.causal_support)

    def test_url_and_declared_sha_are_not_sufficient(self):
        s=source("official:public",b"expected payload")
        with self.assertRaises(ValueError):
            ObservedSnapshot.from_bytes(s,b"not matching",NOW)
        with self.assertRaises(TypeError):
            ObservedSnapshot(source=s,body_sha256=s.content_sha256,collected_at=NOW)

    def test_synthetic_or_stale_source_rejected_from_observation(self):
        for s in (source("synthetic:case-1"),source("official:stale",stale=True)):
            with self.subTest(s=s.source_id), self.assertRaises(ValueError):
                ObservedSnapshot.from_bytes(s,b"official byte fixture", NOW)

    def test_scenario_is_explicitly_fictional_and_immutable(self):
        s=SyntheticScenario("case-1","v1",{"person":"fictional"})
        self.assertEqual(s.evidence_kind,"SYNTHETIC_SCENARIO")
        self.assertEqual(s.proof_level,"P0")
        with self.assertRaises((AttributeError,TypeError)):
            s.proof_level="P4"
        with self.assertRaises(ValueError):
            SyntheticScenario("","v1",{"person":"fictional"})

    def test_prediction_is_a_probability_not_a_measured_intervention(self):
        p=Prediction(("official:public",),"ampersand-v0.1",(0.3,0.7))
        self.assertEqual(p.proof_level,"P0")
        self.assertEqual(p.human_outcome,"NOT_MEASURED")
        self.assertFalse(p.authorized_execution)
        self.assertFalse(p.causal_support)
        self.assertEqual(sum(p.distribution),1.0)
        for vals in [(0.2,0.9),(1.1,-0.1),(nan,1.0),(),("0.5",0.5)]:
            with self.subTest(vals=vals), self.assertRaises(ValueError):
                Prediction(("official:public",),"ampersand-v0.1",vals)


if __name__=="__main__":
    unittest.main()
