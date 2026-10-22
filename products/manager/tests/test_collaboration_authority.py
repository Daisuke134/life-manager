"""E02 — model advisory output must not mint execution or welfare proof."""
from dataclasses import asdict, replace, FrozenInstanceError
import unittest

from manager_core.collaboration import AdvisoryResult, advisory_receipt


class AdvisoryAuthorityBoundary(unittest.TestCase):
    def test_proof_grade_not_settable_in_constructor(self):
        with self.assertRaises(TypeError):
            AdvisoryResult("PROPOSE", "Great idea", ("public:a",), proof_level="P4")

    def test_execution_authority_not_settable_in_constructor(self):
        with self.assertRaises(TypeError):
            AdvisoryResult("PROPOSE", "Great idea", ("public:a",), authorized_execution=True)

    def test_causal_support_not_settable_in_constructor(self):
        with self.assertRaises(TypeError):
            AdvisoryResult("ASK", "Clarify", (), causal_support=True)

    def test_human_outcome_not_settable_in_constructor(self):
        with self.assertRaises(TypeError):
            AdvisoryResult("PASS", "Quiet", (), human_outcome="SUFFERING_REDUCED")

    def test_replace_cannot_enable_privilege(self):
        safe = AdvisoryResult("PROPOSE", "Optional info", ("public:a",))
        for name, value in (("proof_level", "P4"), ("causal_support", True),
                            ("authorized_execution", True), ("human_outcome", "BENEFITED")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(safe, **{name: value})

    def test_public_receipt_never_contains_untrusted_exec_or_causal_claim(self):
        advice=AdvisoryResult("ASK", "Confirm first", ("public:a",))
        receipt=advisory_receipt(advice)
        self.assertEqual(set(receipt), {
            "decision","reason","source_ids","status",
            "proof_level","human_outcome","causal_support","authorized_execution",
        })
        self.assertEqual(receipt["proof_level"], "P0")
        self.assertEqual(receipt["human_outcome"], "NOT_MEASURED")
        self.assertIs(receipt["causal_support"], False)
        self.assertIs(receipt["authorized_execution"], False)
        self.assertEqual(receipt["source_ids"], ["public:a"])

    def test_receipt_rejects_arbitrary_object(self):
        with self.assertRaises(ValueError):
            advisory_receipt({"decision": "PROPOSE", "authorized_execution": True})

    def test_existing_advice_immutable(self):
        advice=AdvisoryResult("PASS", "Safe", ())
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            advice.authorized_execution=True
        self.assertFalse(advice.authorized_execution)


if __name__=="__main__":
    unittest.main()
