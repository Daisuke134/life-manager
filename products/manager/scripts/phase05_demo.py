#!/usr/bin/env python3
"""K014 deterministic, public-safe OFFLINE fixture replay; no actual beneficiary."""
import argparse
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from manager_core.models.source import Source
from manager_core.models.observation import Observation
from manager_core.models.problem import Problem,CausalHypothesis
from manager_core.models.intervention import InterventionOption,InterventionPlan
from manager_core.authority import Grant,AuthorityVerifier
from manager_core.adapters.fixtures import OfflineFixtureAdapter,OfflineFixtureSensor
from manager_core.outbox import DurableOutbox
from manager_core.audit import AuditTrail
from manager_core.kernel import ManagerKernel
from manager_core.evaluator import Comparator,evaluate_outcome
from manager_core.learning import PolicyLearner

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"docs/verification/PHASE05_OFFLINE_DEMO_RESULTS.json"
NOW=datetime(2026,10,21,9,0,tzinfo=timezone.utc)


def _problem():
    source=Source("fictional-public-aggregate","https://example.org/public.csv",
                  "CC-BY-4.0","allowed_with_conditions","a"*64,NOW,"public_nonpersonal")
    observation=Observation(source,"fictional_count","fictional-area",10.0,"count",NOW)
    hypothesis=CausalHypothesis("possible improvement","unvalidated intervention hypothesis",
                               ("fictional-public-aggregate",))
    return Problem("fictional-problem","beneficiary_welfare",(observation,),
                   (hypothesis,),("seasonal conditions","other co-interventions"))


def _plan(domain):
    return InterventionPlan((
        InterventionOption("NO_ACTION",domain,"test-area","NO_ACTION",0,0,None,True),
        InterventionOption("fictional_action",domain,"test-area","fixture_change",2.0,0.1,(5.,8.),False)
    ))


def run_demo():
    with TemporaryDirectory() as tmp:
        path=Path(tmp)
        outbox=DurableOutbox(path/"outbox.sqlite")
        audit=AuditTrail(path/"audit.sqlite")
        authority=AuthorityVerifier({"test-issuer":b"nonproduction-ephemeral-fixture-key"})
        kernel=ManagerKernel(outbox,authority,audit)
        results={"phase":"05","scope":"OFFLINE_FIXTURE_ONLY",
                 "scientific_gate1":"UNMET","field_beneficiary_improvements_verified":0,
                 "domains":{},"failure_paths":{},"policy_learning":{}}
        for domain in ("finance","environment"):
            g=Grant("fixture-"+domain,"test-issuer",domain,"fixture_change","test-area",
                    5.0,NOW-timedelta(hours=1),NOW+timedelta(hours=2))
            a=OfflineFixtureAdapter(domain,"fixture_change","test-area")
            name="demo-"+domain
            sig=authority.sign_for_fixture(g)
            result=kernel.run(name,_problem(),_plan(domain),g,sig,a,OfflineFixtureSensor(a),NOW,
                              causal_support=True)
            # The same intent on a restarted outbox must never send twice.
            second=ManagerKernel(DurableOutbox(path/"outbox.sqlite"),authority,audit).run(
                name,_problem(),_plan(domain),g,sig,a,OfflineFixtureSensor(a),NOW,causal_support=True)
            results["domains"][domain]={
                "status":result.status,
                "replayed_status":second.status,
                "provider_sends_after_replay":a.send_calls,
                "proof_level":result.proof_level,
                "trace_chain_valid":audit.verify_chain(name),
                "benefit_status":audit.public_blessing(name)["benefit_status"]}
        g=Grant("fixture-other","test-issuer","finance","fixture_change","test-area",
                5.0,NOW-timedelta(hours=1),NOW+timedelta(hours=2))
        a=OfflineFixtureAdapter("finance","fixture_change","test-area")
        no=kernel.run("demo-no-action",_problem(),_plan("finance"),g,
                      authority.sign_for_fixture(g),a,OfflineFixtureSensor(a),NOW,
                      causal_support=False)
        results["failure_paths"]["no_action"]={"status":no.status,"provider_sends":a.send_calls}
        a=OfflineFixtureAdapter("finance","fixture_change","test-area")
        rejected=kernel.run("demo-forged",_problem(),_plan("finance"),g,"forged",a,
                            OfflineFixtureSensor(a),NOW,causal_support=True)
        results["failure_paths"]["forged_authority"]={"status":rejected.status,"provider_sends":a.send_calls}
        a=OfflineFixtureAdapter("finance","fixture_change","test-area",timeout_after_effect=True)
        a.lookup_fails=True
        unknown=kernel.run("demo-unknown",_problem(),_plan("finance"),g,
                           authority.sign_for_fixture(g),a,OfflineFixtureSensor(a),NOW,
                           causal_support=True)
        results["failure_paths"]["timeout_after_effect"]={"status":unknown.status,
               "provider_sends":a.send_calls,"benefit_status":audit.public_blessing("demo-unknown")["benefit_status"]}
        a=OfflineFixtureAdapter("finance","fixture_change","test-area",timeout_before_effect=True)
        absent=kernel.run("demo-absent",_problem(),_plan("finance"),g,
                          authority.sign_for_fixture(g),a,OfflineFixtureSensor(a),NOW,
                          causal_support=True)
        results["failure_paths"]["timeout_before_effect"]={"status":absent.status,
               "provider_sends":a.send_calls,"simulated_effects":len(a.effects)}
        a=OfflineFixtureAdapter("environment","fixture_change","test-area")
        g_env=Grant("fixture-sensor","test-issuer","environment","fixture_change","test-area",
                    5.0,NOW-timedelta(hours=1),NOW+timedelta(hours=2))
        missing=kernel.run("demo-missing",_problem(),_plan("environment"),g_env,
                           authority.sign_for_fixture(g_env),a,object(),NOW,causal_support=True)
        results["failure_paths"]["missing_independent_sensor"]={
            "status":missing.status,"provider_sends":a.send_calls}
        # Injected negative, fictional comparison; this is not a trial or P4 evidence.
        negative=evaluate_outcome(-5,-7,-3,1,2,
                    Comparator("randomized",True,"https://example.org/fictional-preregistration",True),
                    "welfare")
        results["failure_paths"]["synthetic_negative_net_effect"]={
            "status":negative.status,"net_effect":negative.net_effect,"proof_level":negative.proof_level}
        learner=PolicyLearner(path/"policies.sqlite")
        learner.initialize("safe-v1")
        learner.propose("candidate-v2",.1,.2,("train-study",),("unseen-study",))
        approved=learner.promote("candidate-v2",baseline_loss=.4)
        rolled=learner.observe_loss(.8,max_allowed_loss=.4)
        results["policy_learning"]={"shadow_and_holdout_approved":approved,
             "active_after_regression":rolled,"persisted_active":PolicyLearner(path/"policies.sqlite").active()}
        return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--write",action="store_true")
    args=parser.parse_args()
    result=run_demo()
    rendered=json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+"\n"
    if args.write:
        REPORT.write_text(rendered,encoding="utf-8")
    if args.check and REPORT.read_text(encoding="utf-8")!=rendered:
        raise SystemExit("PHASE05_OFFLINE_DEMO_REPORT_OUT_OF_SYNC")
    if result["field_beneficiary_improvements_verified"]!=0 or any(
            x["proof_level"]!="P0" for x in result["domains"].values()):
        raise SystemExit("ILLEGAL_REAL_WORLD_IMPACT_CLAIM")
    print(rendered)
    if args.check: print("PASS: two domain fixtures + failure modes + report exactly match")


if __name__=="__main__":
    main()
