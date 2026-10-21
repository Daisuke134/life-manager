"""Phase06 F002 / F003 RED-first contracts: pilot design and public ledger readback.

No real transactions are executed. A public historic transaction is NOT
a Manager intervention or an independently verified beneficiary outcome.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "pilot/PREREGISTRATION.json"
LOCK = ROOT / "pilot/PREREGISTRATION.sha256"
NOW = datetime(2026,10,21,10,30,tzinfo=timezone.utc)

class F002PreregistrationTests(unittest.TestCase):
    def test_pilot_primary_outcome_no_action_sample_comparator_are_frozen(self):
        from manager_core.preregistration import validate_preregistration, verify_preregistration_lock
        payload=SPEC.read_bytes()
        self.assertTrue(verify_preregistration_lock(payload, LOCK.read_text(encoding="ascii").strip()))
        study=json.loads(payload)
        self.assertTrue(validate_preregistration(study))
        self.assertEqual(study["primary_outcome"]["name"],"incremental_net_confirmed_third_party_contributions")
        self.assertEqual(study["primary_outcome"]["unit"],"USD_cents_per_campaign")
        self.assertEqual(study["assignment"]["no_action_arm"],"NO_ACTION")
        self.assertGreaterEqual(study["design"]["n_campaigns_total"],40)
        self.assertEqual(study["status"],"PREREGISTERED_DESIGN_ONLY")
        self.assertFalse(study["live_pilot_authorized"])
        self.assertEqual(study["proof_level"],"P0")

    def test_outcome_switch_after_lock_fails(self):
        from manager_core.preregistration import verify_preregistration_lock
        payload=SPEC.read_bytes()
        altered=payload.replace(b"incremental_net_confirmed_third_party_contributions",
                                b"clicks_or_impressions")
        self.assertNotEqual(altered,payload)
        with self.assertRaises(ValueError):
            verify_preregistration_lock(altered,LOCK.read_text(encoding="ascii").strip())

    def test_missing_harms_or_nonrandom_treatment_refused(self):
        from manager_core.preregistration import validate_preregistration
        plan=json.loads(SPEC.read_text(encoding="utf-8"))
        for field in ("harms","method","no_action_arm"):
            data=json.loads(json.dumps(plan))
            if field=="harms": data["harms"]=[]
            if field=="method": data["assignment"]["method"]="self_selection"
            if field=="no_action_arm": data["assignment"]["no_action_arm"]="unrestricted"
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_preregistration(data)


def response_fixture(slug="webpack"):
    return {"data":{"account":{"slug":slug,"transactions":{"totalCount":2,"nodes":[
        {"id":"opaque-tx-01","type":"CREDIT","kind":"CONTRIBUTION",
         "amount":{"valueInCents":2500,"currency":"USD"},"createdAt":"2026-10-19T12:00:00Z"},
        {"id":"opaque-tx-02","type":"DEBIT","kind":"EXPENSE",
         "amount":{"valueInCents":-700,"currency":"USD"},"createdAt":"2026-10-20T14:00:00Z"}
    ]}}}}

class FakeResponse:
    def __init__(self, obj): self.content=json.dumps(obj).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,limit=-1): return self.content if limit==-1 else self.content[:limit]


class F003PublicLedgerTests(unittest.TestCase):
    def test_external_ledger_read_only_and_private_free(self):
        from manager_core.adapters.public_finance import OpenCollectivePublicLedger
        captured=[]
        def opener(req,timeout=0):
            captured.append(req)
            return FakeResponse(response_fixture())
        snapshot=OpenCollectivePublicLedger(opener=opener).read("webpack",at=NOW)
        self.assertEqual(snapshot.transaction_count,2)
        self.assertEqual(snapshot.sample_credit_cents,2500)
        self.assertEqual(snapshot.sample_debit_cents,-700)
        self.assertEqual(snapshot.currencies,("USD",))
        self.assertEqual(snapshot.proof_level,"P0")
        self.assertIsNone(snapshot.verified_beneficiary_impact)
        self.assertEqual(len(snapshot.snapshot_sha256),64)
        self.assertNotIn("opaque-tx-01",repr(snapshot))
        self.assertEqual(len(captured),1)
        request=captured[0]
        self.assertEqual(request.full_url,"https://api.opencollective.com/graphql/v2")
        self.assertEqual(request.get_method(),"POST")
        self.assertNotIn("Authorization",dict(request.header_items()))
        body=json.loads(request.data)
        self.assertEqual(body["variables"],{"slug":"webpack"})
        self.assertTrue(body["query"].strip().startswith("query"))
        self.assertNotIn("mutation",body["query"].lower())
        self.assertNotIn("email",body["query"].lower())
        self.assertNotIn("fromAccount",body["query"])

    def test_bad_slugs_graphql_errors_missing_or_forged_accounts_are_UNKNOWN(self):
        from manager_core.adapters.public_finance import OpenCollectivePublicLedger,LedgerUnverified
        for slug in ("../admin","evil.com","CamelCase","","a"*130,"x\nmutation"):
            with self.subTest(slug=slug),self.assertRaises(ValueError):
                OpenCollectivePublicLedger(opener=lambda req,timeout:None).read(slug,at=NOW)
        for data in ({"errors":[{"message":"permission denied"}]},
                     {"data":{"account":None}},response_fixture(slug="another")):
            with self.subTest(data=data),self.assertRaises(LedgerUnverified):
                OpenCollectivePublicLedger(opener=lambda req,timeout:FakeResponse(data)).read("webpack",at=NOW)

    def test_duplicate_transaction_and_invalid_money_rejected(self):
        from manager_core.adapters.public_finance import OpenCollectivePublicLedger,LedgerUnverified
        for issue in ("duplicate","boolean_money","invalid_date"):
            data=response_fixture()
            nodes=data["data"]["account"]["transactions"]["nodes"]
            if issue=="duplicate": nodes[1]["id"]=nodes[0]["id"]
            if issue=="boolean_money": nodes[0]["amount"]["valueInCents"]=True
            if issue=="invalid_date": nodes[1]["createdAt"]="yesterday"
            with self.subTest(issue=issue),self.assertRaises(LedgerUnverified):
                OpenCollectivePublicLedger(opener=lambda req,timeout:FakeResponse(data)).read("webpack",at=NOW)

    def test_provider_network_or_format_error_never_defaults_to_zero(self):
        from manager_core.adapters.public_finance import OpenCollectivePublicLedger,LedgerUnverified
        def unavailable(req,timeout=0): raise TimeoutError("provider timeout")
        with self.assertRaises(LedgerUnverified):
            OpenCollectivePublicLedger(opener=unavailable).read("webpack",at=NOW)
        class InvalidResponse:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,limit=-1): return b"<html>Denied</html>"
        with self.assertRaises(LedgerUnverified):
            OpenCollectivePublicLedger(opener=lambda req,timeout:InvalidResponse()).read("webpack",at=NOW)

if __name__=="__main__":
    unittest.main()
