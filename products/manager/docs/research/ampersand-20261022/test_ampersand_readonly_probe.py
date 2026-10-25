"""Offline contract tests. No external requests or credentials needed."""
import io
import json
import os
import unittest
from unittest.mock import patch

import ampersand_readonly_probe as p


class FakeResponse:
    def __init__(self, obj):
        self.body = io.BytesIO(json.dumps(obj).encode())
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.body.read()


class ContractTests(unittest.TestCase):
    def test_request_has_no_tools_or_external_environment(self):
        q = p.session_payload("What should we do?")
        self.assertEqual(q["agent"]["model"], "ampersand-v0.1")
        self.assertEqual(q["environment"], {"type": "none"})
        self.assertNotIn("tools", q["agent"])

    def test_bad_prompt_rejected(self):
        for v in ("", "  ", "x" * 4001, 7):
            with self.assertRaises(ValueError): p.session_payload(v)

    def test_proposal_is_advisory_and_causal_is_false(self):
        q = p.validate_proposal(
            {"decision": "PROPOSE", "reason": "Check changed link", "source_ids": ["pub:a"]},
            {"pub:a"},
        )
        self.assertEqual(q["proof_level"], "P0")
        self.assertFalse(q["authorized_execution"])
        self.assertFalse(q["causal_support"])

    def test_unknown_source_denied(self):
        with self.assertRaises(ValueError):
            p.validate_proposal(
                {"decision": "PROPOSE", "reason": "test", "source_ids": ["pub:unknown"]},
                {"pub:a"},
            )

    def test_action_injection_denied(self):
        with self.assertRaises(ValueError):
            p.validate_proposal(
                {"decision": "PROPOSE", "reason": "test", "source_ids": ["pub:a"], "execute": True},
                {"pub:a"},
            )

    def test_proposal_requires_source(self):
        with self.assertRaises(ValueError):
            p.validate_proposal(
                {"decision": "PROPOSE", "reason": "test", "source_ids": []},
                {"pub:a"},
            )

    def test_invalid_decision_denied(self):
        with self.assertRaises(ValueError):
            p.validate_proposal(
                {"decision": "TRANSFER_MONEY", "reason": "test", "source_ids": []}, set()
            )

    def test_api_header_and_path(self):
        captures = []
        def fake(req, timeout):
            captures.append(req)
            return FakeResponse({"data": [{"id": p.MODEL}]})
        r = p.request_json("GET", "/models", "fake-value", opener=fake)
        self.assertEqual(r["data"][0]["id"], p.MODEL)
        self.assertEqual(captures[0].full_url, p.BASE_URL + "/models")
        self.assertNotIn("Openai-beta", captures[0].headers)

    def test_session_uses_beta_header(self):
        captures = []
        def fake(req, timeout):
            captures.append(req)
            return FakeResponse({"id": "sess_mock"})
        r = p.request_json(
            "POST", "/agents/sessions", "fake-value",
            p.session_payload("hi"), opener=fake
        )
        self.assertEqual(r["id"], "sess_mock")
        self.assertEqual(captures[0].get_header("Openai-beta"), "agents=v1")

    def test_excess_capability_endpoint_denied(self):
        for meth, path in [
            ("POST", "/payments"), ("DELETE", "/agents/sessions"),
            ("POST", "/models")
        ]:
            with self.assertRaises(ValueError):
                p.request_json(meth, path, "fake-value")

    def test_no_key_is_offline(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(p.main(["--smoke"]), 2)

    def test_offline_smoke_succeeds_no_network(self):
        self.assertEqual(p.main(["--offline"]), 0)


if __name__ == "__main__":
    unittest.main()
