import os
import sys
import unittest

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
            return open_orders
        return orders_after
    get.calls = calls
    return get


class BuildProofTest(unittest.TestCase):
    def test_no_orders_after_queue_and_none_open_is_verified(self):
        get = fake_get([], [])
        proof = er.build_proof(OWNER, OCC, QUEUED, get)
        self.assertIs(proof["verified"], True)
        self.assertEqual(proof["owner_id"], OWNER)
        self.assertEqual(proof["occurrence_id"], OCC)
        self.assertEqual(proof["provider_receipt_id"], "alpaca-orders-none-after-" + QUEUED)
        self.assertIn("after=" + QUEUED, get.calls[0])
        self.assertIn("status=all", get.calls[0])

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

    def test_page_limit_hit_is_inconclusive(self):
        proof = er.build_proof(OWNER, OCC, QUEUED, fake_get([], [{}] * er.PAGE_LIMIT))
        self.assertIs(proof["verified"], False)

    def test_module_never_writes_to_alpaca(self):
        src = open(er.__file__).read()
        for banned in ('method="POST"', "method='POST'", '"DELETE"', '"PATCH"', "data="):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
