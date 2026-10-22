"""E04: strict text-output contract, never equate a parser failure with policy PASS."""
from datetime import datetime,timezone
import json
import unittest

from manager_core.collaboration import (
    AdvisoryResult, ValidationFailure, MAX_REASON,
    parse_advice, advisory_from_text, safe_advisory,
    PublicFact, PlannerContext, render_prompt,
)
from manager_core.models.source import Source

NOW=datetime(2026,10,22,tzinfo=timezone.utc)


def context():
    src=Source("public:a","https://www.mhlw.go.jp/","public-license",
        "allowed_with_conditions","0"*64,NOW,"public_nonpersonal")
    return PlannerContext("Offer accurate public guidance",(PublicFact(src,"Official support directory"),),NOW)


class StrictAdviceProtocol(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        raw='{"decision":"PROPOSE","decision":"PASS","reason":"Maybe","source_ids":["public:a"]}'
        with self.assertRaises(ValueError):
            advisory_from_text(raw,context())
        result=parse_advice(raw,frozenset({"public:a"}))
        self.assertIsInstance(result,ValidationFailure)
        self.assertEqual(result.kind,"FORMAT_ERROR")

    def test_nonfinite_and_unknown_keys_fail_closed(self):
        for raw in (
            '{"decision":"PASS","reason":NaN,"source_ids":[]}',
            '{"decision":"ASK","reason":"Ask","source_ids":[],"authorized_execution":true}',
            '{"decision":"PROPOSE","reason":"Fix","source_ids":["forged:id"]}',
        ):
            with self.subTest(raw=raw):
                result=parse_advice(raw,frozenset({"public:a"}))
                self.assertIsInstance(result,ValidationFailure)
                self.assertNotEqual(result.kind,"POLICY_PASS")

    def test_model_is_told_reason_length_limit(self):
        p=render_prompt(context())
        self.assertIn("reason",p)
        self.assertIn(str(MAX_REASON),p)
        self.assertIn("characters",p)

    def test_overlong_reason_is_format_error_not_model_pass(self):
        raw=json.dumps({"decision":"PROPOSE","reason":"x"*(MAX_REASON+1),
                        "source_ids":["public:a"]})
        result=parse_advice(raw,frozenset({"public:a"}))
        self.assertIsInstance(result,ValidationFailure)
        self.assertEqual(result.kind,"FORMAT_ERROR")
        safe=safe_advisory(raw,context())
        self.assertEqual(safe.decision,"PASS")
        self.assertEqual(safe.status,"INVALID_MODEL_OUTPUT")
        self.assertNotEqual(safe.status,"MODEL_ADVICE_P0")

    def test_valid_prespecified_json_is_advice_P0_not_action(self):
        raw=json.dumps({"decision":"PROPOSE","reason":"Check the directory",
                        "source_ids":["public:a"]})
        response=parse_advice(raw,frozenset({"public:a"}))
        self.assertIsInstance(response,AdvisoryResult)
        self.assertEqual(response.decision,"PROPOSE")
        self.assertFalse(response.authorized_execution)

    def test_reject_empty_and_unbounded_provider_output(self):
        for raw in ("","{bad", "A"*5001):
            with self.subTest(raw=len(raw)):
                self.assertIsInstance(parse_advice(raw,frozenset({"public:a"})),
                                      ValidationFailure)


if __name__=="__main__":
    unittest.main()
