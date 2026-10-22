"""Phase06 blocker removal: independent, privacy-preserving public indoor data;
missing legal/operator grants remain unavailable and never permit execution.
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,21,12,0,tzinfo=timezone.utc)

def public_indoor_fixture():
    return {"data":[
        {"locationId":102112442,"longitude":16.6,"latitude":49.2,
         "sensorType":"Small Sensor","pm25":4.0,"pm10":None,
         "atmp":24.1,"rhum":38.0,"rco2":493,
         "measuredAt":"2026-10-21T11:34:58Z","dataSource":"AirGradient"},
        {"locationId":102112443,"longitude":-122.2,"latitude":37.4,
         "sensorType":"Small Sensor","pm25":1.6,"pm10":None,
         "atmp":21.6,"rhum":54.0,"rco2":937,
         "measuredAt":"2026-10-21T11:36:16Z","dataSource":"AirGradient"}
    ],"total":2,"page":1,"pagesize":2}

class FakeResponse:
    def __init__(self,obj): self.payload=json.dumps(obj).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n=-1): return self.payload if n<0 else self.payload[:n]


class IndoorAirReadOnlyTests(unittest.TestCase):
    def test_F007_public_opt_in_indoor_monitor_really_separate_from_actuator(self):
        from manager_core.adapters.public_indoor_air import PublicIndoorAirObservations
        captured=[]
        def opener(req,timeout=0):
            captured.append(req)
            return FakeResponse(public_indoor_fixture())
        obs=PublicIndoorAirObservations(opener=opener).read(at=NOW)
        self.assertEqual(obs.provider,"AirGradient")
        self.assertEqual(obs.privacy_class,"public_opt_in_aggregate")
        self.assertEqual(obs.source_url,"https://map-data.airgradient.com/map/api/v1/indoor/measurements/current?pagesize=2&page=1")
        self.assertEqual(obs.sample_count,2)
        self.assertAlmostEqual(obs.mean_pm25_ug_m3,2.8)
        self.assertEqual(obs.proof_level,"P0")
        self.assertEqual(obs.field_intervention_status,"NOT_MEASURED")
        self.assertEqual(obs.data_rights,"REVIEW_BEFORE_REUSE")
        self.assertEqual(len(obs.content_sha256),64)
        self.assertNotIn("locationId",repr(obs))
        self.assertNotIn("latitude",repr(obs))
        self.assertNotIn("102112442",repr(obs))
        self.assertEqual(len(captured),1)
        req=captured[0]
        self.assertEqual(req.full_url,obs.source_url)
        self.assertEqual(req.get_method(),"GET")
        self.assertNotIn("Authorization",dict(req.header_items()))
        self.assertIsNone(req.data)

    def test_F007_rejects_provider_failure_empty_and_malformed_sensor_values(self):
        from manager_core.adapters.public_indoor_air import PublicIndoorAirObservations,IndoorAirUnverified
        def failing(req,timeout=0): raise TimeoutError("down")
        with self.assertRaises(IndoorAirUnverified):
            PublicIndoorAirObservations(opener=failing).read(at=NOW)
        for problem in ("empty","invalid_bool","negative","invalid_date","provider_missing","provider_unknown","future","stale"):
            item=public_indoor_fixture()
            if problem=="empty": item["data"]=[]
            elif problem=="invalid_bool": item["data"][0]["pm25"]=True
            elif problem=="negative": item["data"][0]["pm25"]=-1.0
            elif problem=="invalid_date": item["data"][0]["measuredAt"]="yesterday"
            elif problem=="provider_missing": item["data"][0]["dataSource"]=""
            elif problem=="provider_unknown": item["data"][0]["dataSource"]="UnknownPublisher"
            elif problem=="future": item["data"][0]["measuredAt"]="2026-10-25T12:00:00Z"
            elif problem=="stale":
                item["data"][0]["measuredAt"]="2026-09-01T12:00:00Z"
                item["data"][1]["measuredAt"]="2026-09-01T12:00:00Z"
            with self.subTest(problem=problem),self.assertRaises(IndoorAirUnverified):
                PublicIndoorAirObservations(opener=lambda req,timeout:FakeResponse(item)).read(at=NOW)

    def test_F007_missing_pm25_is_not_zero_or_success(self):
        from manager_core.adapters.public_indoor_air import PublicIndoorAirObservations,IndoorAirUnverified
        item=public_indoor_fixture()
        item["data"][0]["pm25"]=None
        result=PublicIndoorAirObservations(opener=lambda req,timeout:FakeResponse(item)).read(at=NOW)
        self.assertEqual(result.sample_count,1)
        self.assertEqual(result.missing_count,1)
        self.assertAlmostEqual(result.mean_pm25_ug_m3,1.6)
        item["data"][1]["pm25"]=None
        with self.assertRaises(IndoorAirUnverified):
            PublicIndoorAirObservations(opener=lambda req,timeout:FakeResponse(item)).read(at=NOW)


class PermissionReadinessTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((ROOT/"pilot/PHASE06_AUTHORITY_READINESS.json").read_text(encoding="utf-8"))

    def test_F004_F007_missing_source_records_are_properly_blocked(self):
        from manager_core.field_readiness import examine_authority_packet
        result=examine_authority_packet(self.data)
        self.assertEqual(result["finance"]["status"],"MISSING_EXTERNAL_EVIDENCE")
        self.assertEqual(result["environment"]["status"],"MISSING_EXTERNAL_EVIDENCE")
        self.assertFalse(result["finance"]["can_execute"])
        self.assertFalse(result["environment"]["can_execute"])
        for req in ("fiscal_host_or_operator_ref","scoped_grant_ref","funding_custody_ref","independent_receipt_source_ref"):
            self.assertIn(req,result["finance"]["missing"])
        for req in ("site_owner_ref","permission_for_portable_actuation_ref","independent_sensor_ref","calibration_ref"):
            self.assertIn(req,result["environment"]["missing"])

    def test_F004_F007_self_attested_fields_cannot_grant_live_authority(self):
        from manager_core.field_readiness import examine_authority_packet,REQUIREMENTS
        data=copy.deepcopy(self.data)
        for domain in ("finance","environment"):
            for field in REQUIREMENTS[domain]:
                data[domain][field]="external-ref-placeholder-"+field
            data[domain]["status"]="AUTHORIZED"  # malicious self claim
        result=examine_authority_packet(data)
        self.assertEqual(result["finance"]["status"],"AWAITING_INDEPENDENT_VALIDATION")
        self.assertEqual(result["environment"]["status"],"AWAITING_INDEPENDENT_VALIDATION")
        self.assertFalse(result["finance"]["can_execute"])
        self.assertFalse(result["environment"]["can_execute"])

    def test_gate_packet_never_contains_secrets_or_private_addresses(self):
        raw=(ROOT/"pilot/PHASE06_AUTHORITY_READINESS.json").read_text(encoding="utf-8")
        self.assertNotIn("api_key",raw)
        self.assertNotIn("private_key",raw)
        self.assertNotIn("recipient_email",raw)
        self.assertNotIn("street_address",raw)
        self.assertIn("NOT_VERIFIED",raw)
        self.assertIn("NO_ACTION",raw)

    def test_retired_registry_does_not_enable_third_party_authority(self):
        from manager_core.field_readiness import examine_authority_packet
        result=examine_authority_packet(self.data)
        self.assertTrue(all(not x["can_execute"] for x in result.values()))
        registry=json.loads((ROOT/"docs/roadmap/tasks.json").read_text(encoding="utf-8"))
        by={x["id"]:x["status"] for x in registry}
        self.assertEqual(by["F004"],"skipped")
        self.assertEqual(by["F007"],"skipped")
        self.assertEqual(by["F005"],"todo")
        self.assertEqual(by["F008"],"todo")
        self.assertEqual(by["F009"],"todo")


if __name__=="__main__":
    unittest.main()
