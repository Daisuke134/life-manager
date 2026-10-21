import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import effect_reconcile as er  # noqa: E402
from runtime.loop import fence_reconcile as fence_reconcile  # noqa: E402

OWNER = "alpaca-investment-live"
OCC = OWNER + ":18d89ac7ba8a6a98-47263"
QUEUED = "2026-09-25T15:36:02Z"


def fake_get(orders_after, open_orders):
    calls = []

    def get(path):
        calls.append(path)
        if "status=open" in path:
            return {"data": open_orders, "request_id": "open-request"}
        return {"data": orders_after, "request_id": "after-request"}
    get.calls = calls
    return get


class BuildProofTest(unittest.TestCase):
    def test_declared_modes_map_to_their_own_owner_and_endpoint(self):
        self.assertEqual(er.owner_for_mode("live"), "alpaca-investment-live")
        self.assertEqual(er.owner_for_mode("paper"), "alpaca-investment-paper")
        self.assertEqual(er.endpoint_for_mode("live"), er.LIVE_ENDPOINT)
        self.assertEqual(er.endpoint_for_mode("paper"), er.PAPER_ENDPOINT)
        with self.assertRaisesRegex(ValueError, "^investment_mode_invalid$"):
            er.owner_for_mode("shadow")

    def test_no_orders_after_queue_and_none_open_is_verified(self):
        get = fake_get([], [])
        proof = er.build_proof(OWNER, OCC, QUEUED, get)
        self.assertIs(proof["verified"], True)
        self.assertEqual(proof["owner_id"], OWNER)
        self.assertEqual(proof["occurrence_id"], OCC)
        self.assertEqual(proof["provider_receipt_id"], "after-request")
        self.assertEqual(proof["provider_request_ids"], ["after-request", "open-request"])
        self.assertIn("after=" + QUEUED, get.calls[0])
        self.assertIn("status=all", get.calls[0])

    def test_no_order_proof_uses_provider_request_ids(self):
        responses = iter((
            {"data": [], "request_id": "after-request-1"},
            {"data": [], "request_id": "open-request-2"},
        ))
        proof = er.build_proof(OWNER, OCC, QUEUED, lambda _path: next(responses))

        self.assertIs(proof["verified"], True)
        self.assertEqual(proof["provider_receipt_id"], "after-request-1")
        self.assertEqual(proof["provider_request_ids"], ["after-request-1", "open-request-2"])

    def test_missing_provider_request_id_keeps_no_order_unverified(self):
        order = {"id": "provider-order-1", "client_order_id": "client-order-1"}
        responses = iter((
            {"data": [order], "request_id": "after-request-1"},
            {"data": [], "request_id": " "},
        ))
        proof = er.build_proof(OWNER, OCC, QUEUED, lambda _path: next(responses))

        self.assertIs(proof["verified"], False)
        self.assertEqual(proof["reason"], "provider_request_id_missing")
        self.assertEqual(proof["provider_receipt_id"], "after-request-1")
        self.assertEqual(proof["provider_request_ids"], ["after-request-1"])
        self.assertEqual(proof["after_order_count"], 1)
        self.assertEqual(proof["after_order_refs"], [order])
        self.assertEqual(proof["phase"], "readback")
        self.assertEqual(proof["status"], "held")
        self.assertEqual(proof["effect_status"], "unknown")
        self.assertEqual(proof["retryable"], False)
        self.assertEqual(proof["next_action"], "retry_or_repair_official_readback")

    def test_second_get_failure_keeps_first_receipt_and_structured_diagnostic(self):
        order = {"id": "provider-order-1", "client_order_id": "client-order-1"}

        def get(path):
            if "status=open" in path:
                raise OSError("PRIVATE PROVIDER RESPONSE BODY")
            return {"data": [order], "request_id": "after-request-1"}

        proof = er.build_proof(OWNER, OCC, QUEUED, get)

        self.assertFalse(proof["verified"])
        self.assertEqual(proof["reason"], "readback_failed:OSError")
        self.assertEqual(proof["provider_receipt_id"], "after-request-1")
        self.assertEqual(proof["provider_request_ids"], ["after-request-1"])
        self.assertEqual(proof["after_order_count"], 1)
        self.assertEqual(proof["after_order_refs"], [order])
        self.assertEqual(proof["phase"], "readback")
        self.assertEqual(proof["status"], "held")
        self.assertEqual(proof["effect_status"], "unknown")
        self.assertEqual(proof["error_class"], "OSError")
        self.assertTrue(proof["retryable"])
        self.assertEqual(proof["next_action"], "retry_or_repair_official_readback")
        self.assertNotIn("PRIVATE PROVIDER RESPONSE BODY", json.dumps(proof))

    def test_readback_stdout_fits_central_tail_and_keeps_bounded_order_refs(self):
        def order(index, prefix):
            return {
                "id": f"{index:036d}",
                "client_order_id": prefix + "x" * 100 + str(index),
                "status": "filled" * 30,
                "submitted_at": "2026-09-30T12:39:55Z" + "x" * 130,
                "symbol": "BTC/USDC" + "x" * 150,
                "side": "buy" * 50,
            }

        after_orders = [order(i, "after-") for i in range(8)]
        open_orders = [order(i, "open-") for i in range(8)]
        output = StringIO()
        with patch.object(er, "fenced_row", return_value=("claimed", QUEUED)), \
                patch.object(er, "alpaca_get", return_value=fake_get(after_orders, open_orders)), \
                redirect_stdout(output):
            result = er.main(["--occurrence-id", OCC, "--mode", "live", "--readback-only"])

        tail = output.getvalue()[-fence_reconcile.STDOUT_TAIL_LIMIT:]
        records = fence_reconcile._json_output_records(tail)
        self.assertEqual(result, 1)
        self.assertEqual(len(output.getvalue()), len(tail))
        self.assertEqual(len(records), 1)
        proof = records[0]
        self.assertEqual(proof["provider_request_ids"], ["after-request", "open-request"])
        self.assertEqual(proof["after_order_count"], 8)
        self.assertEqual(proof["open_order_count"], 8)
        self.assertTrue(proof["order_refs_truncated"])
        self.assertGreaterEqual(len(proof["after_order_refs"]), 1)
        self.assertGreaterEqual(len(proof["open_order_refs"]), 1)
        self.assertLessEqual(len(proof["after_order_refs"]) + len(proof["open_order_refs"]), 4)
        self.assertEqual(proof["after_order_refs"][0]["id"], f"{0:036d}")
        self.assertTrue(proof["after_order_refs"][0]["client_order_id"].startswith("after-"))

    def test_alpaca_get_preserves_provider_request_id_header(self):
        response = MagicMock()
        response.headers = {"X-Request-ID": "provider-request-1"}
        response.__enter__.return_value = response
        with (patch("alpaca_cli._credentials", return_value={"api_key": "key", "api_secret": "secret"}),
              patch.object(er.urllib.request, "urlopen", return_value=response),
              patch.object(er.json, "load", return_value=[])):
            result = er.alpaca_get(Path("/private/credentials.json"), "paper")("/orders")

        self.assertEqual(result, {"data": [], "request_id": "provider-request-1"})

    def test_fence_resolution_requests_a_fresh_provider_proof(self):
        proof = {
            "owner_id": OWNER, "occurrence_id": OCC, "queued_at": QUEUED,
            "verified": True, "provider_receipt_id": "provider-request-1",
        }

        def resolve(_owner, _occurrence, *, official_readback, expected_state):
            self.assertEqual(expected_state, "claimed")
            before = build.call_count
            self.assertIs(official_readback()["verified"], True)
            self.assertEqual(build.call_count, before + 1)
            return True

        with (patch.object(er, "fenced_row", return_value=("claimed", QUEUED)),
              patch.object(er, "alpaca_get", return_value=lambda _path: []),
              patch.object(er, "build_proof", return_value=proof) as build,
              patch("runtime.host.resource_admission.resolve_unknown_occurrence", side_effect=resolve),
              redirect_stdout(StringIO())):
            result = er.main([
                "--occurrence-id", OCC, "--mode", "paper",
                "--credentials", "/private/credentials.json",
            ])

        self.assertEqual(result, 0)

    def test_any_order_after_queue_is_not_verified(self):
        proof = er.build_proof(OWNER, OCC, QUEUED, fake_get([{"id": "o1"}], []))
        self.assertIs(proof["verified"], False)

    def test_inconclusive_order_readback_keeps_provider_request_and_order_refs(self):
        order = {"id": "provider-order-1", "client_order_id": "lm-ai-" + "a" * 24,
            "status": "filled", "submitted_at": "2026-09-30T12:39:55Z",
            "symbol": "BTC/USDC", "side": "buy"}
        proof = er.build_proof(OWNER, OCC, QUEUED, fake_get([order], []))

        self.assertFalse(proof["verified"])
        self.assertEqual(proof["reason"], "orders_present:after=1,open=0")
        self.assertEqual(proof["provider_receipt_id"], "after-request")
        self.assertEqual(proof["provider_request_ids"], ["after-request", "open-request"])
        self.assertEqual(proof["after_order_count"], 1)
        self.assertEqual(proof["after_order_refs"], [{key: order[key] for key in (
            "id", "client_order_id")}])

    def test_live_readback_defaults_to_canonical_credentials_when_env_is_missing(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(er, "fenced_row", return_value=("claimed", QUEUED)), \
                patch.object(er, "alpaca_get", return_value=fake_get([], [])) as alpaca_get, \
                redirect_stdout(StringIO()):
            result = er.main(["--occurrence-id", OCC, "--mode", "live", "--readback-only"])

        self.assertEqual(result, 0)
        alpaca_get.assert_called_once_with(Path.home() / ".local/share/anicca/credentials.json", "live")

    def test_adapter_failure_emits_secret_free_structured_diagnostic(self):
        output, error_output = StringIO(), StringIO()
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(er, "fenced_row", return_value=("claimed", QUEUED)), \
                patch.object(er, "alpaca_get", side_effect=ValueError("credential secret should never be printed")), \
                redirect_stdout(output), redirect_stderr(error_output):
            result = er.main(["--occurrence-id", OCC, "--mode", "live",
                "--credentials", "/private/credentials.json", "--readback-only"])

        self.assertEqual(result, 1)
        diagnostic = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(diagnostic["owner_id"], OWNER)
        self.assertEqual(diagnostic["occurrence_id"], OCC)
        self.assertEqual(diagnostic["phase"], "readback")
        self.assertEqual(diagnostic["error_class"], "ValueError")
        self.assertEqual(diagnostic["reason_code"], "credentials_unavailable")
        self.assertEqual(diagnostic["retryable"], False)
        self.assertEqual(diagnostic["next_action"], "inspect_readback_credentials")
        self.assertNotIn("credential secret should never be printed", output.getvalue() + error_output.getvalue())

    def test_open_order_is_not_verified(self):
        proof = er.build_proof(OWNER, OCC, QUEUED, fake_get([], [{"id": "o2"}]))
        self.assertIs(proof["verified"], False)

    def test_inconclusive_readback_is_not_verified(self):
        self.assertIs(er.build_proof(OWNER, OCC, QUEUED, fake_get({"code": 1}, []))["verified"], False)

        def boom(path):
            raise OSError("network")
        self.assertIs(er.build_proof(OWNER, OCC, QUEUED, boom)["verified"], False)

    def test_occurrence_must_belong_to_owner(self):
        with self.assertRaises(ValueError):
            er.build_proof(OWNER, "other-owner:1", QUEUED, fake_get([], []))

    def test_cli_defaults_to_live_but_does_not_accept_arbitrary_owner(self):
        self.assertEqual(er.OWNER_ID, "alpaca-investment-live")
        with self.assertRaises(SystemExit):
            er.main(["--owner-id", "alpaca-investment-paper", "--occurrence-id", "x:1"])

    def test_page_limit_hit_is_inconclusive(self):
        proof = er.build_proof(OWNER, OCC, QUEUED, fake_get([], [{}] * er.PAGE_LIMIT))
        self.assertIs(proof["verified"], False)

    def test_module_never_writes_to_alpaca(self):
        with open(er.__file__) as f:
            src = f.read()
        for banned in ('method="POST"', "method='POST'", '"DELETE"', '"PATCH"', "data="):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
