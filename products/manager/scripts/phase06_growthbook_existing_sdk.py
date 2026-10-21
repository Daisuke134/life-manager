#!/usr/bin/env python3
"""Official GrowthBook SDK synthetic NO_ACTION experiment; ZERO real participants.

No custom randomization implementation. No external calls or user tracking.
Not a preregistered field RCT nor evidence of beneficiary improvement.
"""
import json
from growthbook import GrowthBook,Experiment


def run():
    exp=Experiment(
        key="manager-public-resource-v1",
        variations=["NO_ACTION","OFFICIAL_RESOURCE_DIRECTORY"],
        weights=[0.5,0.5],
        coverage=1.0,
    )
    outcomes={"NO_ACTION":0,"OFFICIAL_RESOURCE_DIRECTORY":0}
    for i in range(512):
        # Every string is an INVENTED FICTIONAL ID; never real user data.
        cohort=f"synthetic-cohort-{i:04d}"
        a=GrowthBook(attributes={"id":cohort}).run(exp).value
        b=GrowthBook(attributes={"id":cohort}).run(exp).value
        if a!=b or a not in outcomes:
            raise SystemExit("upstream SDK did not return stable safe variation")
        outcomes[a]+=1
    if min(outcomes.values())<=0 or sum(outcomes.values())!=512:
        raise SystemExit("invalid existing GrowthBook SDK experiment split")
    return {
        "upstream_sdk":"growthbook-python",
        "experiment":"synthetic-manager-public-resource-v1",
        "participant_type":"SYNTHETIC_ONLY",
        "assignment_counts":outcomes,
        "action_executed":False,
        "real_participants":0,
        "real_beneficiaries_measured":0,
        "welfare_outcome":"NOT_MEASURED",
        "proof_level":"P0",
    }


if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,indent=2))
