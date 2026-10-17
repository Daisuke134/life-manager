import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import effect_reconcile as er  # noqa: E402

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
        responses = iter((
            {"data": [], "request_id": "after-request-1"},
            {"data": [], "request_id": " "},
        ))
        proof = er.build_proof(OWNER, OCC, QUEUED, lambda _path: next(responses))

        self.assertIs(proof["verified"], False)
        self.assertEqual(proof["reason"], "provider_request_id_missing")

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


class CredentialPathTest(unittest.TestCase):
    def test_minimal_launchd_env_falls_back_to_the_lane_credentials_ssot(self):
        # lm-fence-reconciler runs without the lane plist env; the adapter must
        # resolve the same SSOT path the lane plists set, not fail closed on env.
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(er, "fenced_row", return_value=("claimed", QUEUED)), \
                patch.object(er, "alpaca_get", return_value=fake_get([], [])) as getter, \
                redirect_stdout(StringIO()):
            self.assertEqual(er.main(["--mode", "paper", "--occurrence-id",
                                      "alpaca-investment-paper:1", "--readback-only"]), 0)
        self.assertEqual(getter.call_args.args[0],
                         Path("~/.local/share/anicca/credentials.json").expanduser())

    def test_explicit_env_still_wins(self):
        with patch.dict(os.environ, {"ALPACA_INVESTMENT_LIVE_CREDENTIALS_FILE": "/x/c.json"},
                        clear=True), \
                patch.object(er, "fenced_row", return_value=("claimed", QUEUED)), \
                patch.object(er, "alpaca_get", return_value=fake_get([], [])) as getter, \
                redirect_stdout(StringIO()):
            er.main(["--occurrence-id", OCC, "--readback-only"])
        self.assertEqual(getter.call_args.args[0], Path("/x/c.json"))


class OccurrenceWindowTest(unittest.TestCase):
    def _events(self, rows):
        import json, tempfile
        directory = tempfile.mkdtemp()
        path = Path(directory) / "events.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return path

    def test_terminal_event_bounds_the_window(self):
        path = self._events([
            {"occurrence_id": OCC, "phase": "execute", "exit_code": None,
             "timestamp": "2026-09-25T15:37:00+00:00"},
            {"occurrence_id": OCC, "phase": "report", "exit_code": 75,
             "timestamp": "2026-09-25T15:38:00.5+00:00"},
            {"occurrence_id": OWNER + ":other", "phase": "report", "exit_code": 0,
             "timestamp": "2026-09-26T00:00:00+00:00"},
        ])
        self.assertEqual(er.occurrence_window_end(path, OCC), "2026-09-25T15:43:01Z")

    def test_missing_or_ambiguous_terminal_leaves_window_open(self):
        self.assertIsNone(er.occurrence_window_end(Path("/nonexistent/events.jsonl"), OCC))
        running = self._events([{"occurrence_id": OCC, "phase": "execute", "exit_code": None,
                                 "timestamp": "2026-09-25T15:37:00+00:00"}])
        self.assertIsNone(er.occurrence_window_end(running, OCC))
        twice = self._events([
            {"occurrence_id": OCC, "phase": "report", "exit_code": 75,
             "timestamp": "2026-09-25T15:38:00+00:00"},
            {"occurrence_id": OCC, "phase": "report", "exit_code": 0,
             "timestamp": "2026-09-25T16:38:00+00:00"},
        ])
        self.assertIsNone(er.occurrence_window_end(twice, OCC))

    def test_window_end_bounds_the_order_query_and_is_recorded(self):
        get = fake_get([], [])
        proof = er.build_proof(OWNER, OCC, QUEUED, get, until="2026-09-25T15:43:01Z")
        self.assertIs(proof["verified"], True)
        self.assertIn("until=2026-09-25T15:43:01Z", get.calls[0])
        self.assertEqual(proof["window_end"], "2026-09-25T15:43:01Z")

    def test_open_orders_still_hold_even_with_a_bounded_window(self):
        proof = er.build_proof(OWNER, OCC, QUEUED, fake_get([], [{"id": "x"}]),
                               until="2026-09-25T15:43:01Z")
        self.assertIs(proof["verified"], False)
