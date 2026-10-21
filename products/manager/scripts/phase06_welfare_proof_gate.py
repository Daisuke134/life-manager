#!/usr/bin/env python3
"""Existing source ladder only; never invent an overall suffering score.

Classifies a digitally published public artifact separately from measured
human mental/physical/financial improvements. Requires no person records,
questionnaire content, account credentials or field execution.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager_core.outcome_ladder import proof_level


def run():
    root=Path(__file__).resolve().parents[1]
    domains=json.loads((root/"pilot/INTERNET_WELFARE_EVIDENCE_CROSSWALK.json").read_text(encoding="utf-8"))
    if {d["domain"] for d in domains}!={"MENTAL","PHYSICAL","FINANCIAL"}:
        raise ValueError("required wellbeing dimensions are distinct")
    for d in domains:
        if (d["beneficiary_welfare_status"]!="NOT_MEASURED"
            or d["observed_people"] is not None
            or d["confidence_interval"] is not None
            or d["measured_effect"] is not None
            or d["proof_level"]!="P0"):
            raise ValueError("unverified beneficiary claim in source crosswalk")
    if proof_level({"external_receipt":True,"independent_readback":True})!=2:
        raise ValueError("existing evidence-ladder output differs from public artifact P2")
    if proof_level({})!=0:
        raise ValueError("empty real-world evidence must never upgrade status")
    return {
        "public_technical_change":"P2_ARTIFACT_ONLY",
        "field_welfare_proof":"NOT_MEASURED",
        "unverified_claims_must_abstain":True,
        "assessment_basis":"existing manager_core.outcome_ladder.proof_level",
        "welfare_by_domain":{d["domain"]:{
            "instrument":d["instrument"],
            "outcome":d["beneficiary_welfare_status"],
            "proof_level":d["proof_level"],
            "observed_people":d["observed_people"]
        } for d in domains}
    }


if __name__=="__main__":
    print(json.dumps(run(),indent=2,sort_keys=True,ensure_ascii=False))
