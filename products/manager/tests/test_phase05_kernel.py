"""Phase 05 contract tests. All cases use public-only, deliberately fictional offline fixtures."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)

def source():
    from manager_core.models.source import Source
    return Source("public-example", "https://example.org/public.csv", "CC-BY-4.0",
                  "allowed_with_conditions", "a"*64, NOW, "public_nonpersonal")

def observation(**kw):
    from manager_core.models.observation import Observation
    values=dict(source=source(), measure_id="public-count", scope="fictional-area",
                value=10.0, unit="count", recorded_at=NOW)
    values.update(kw)
    return Observation(**values)

def problem():
    from manager_core.models.problem import Problem, CausalHypothesis
    o=observation()
    h=CausalHypothesis("intervention might help", "hypothetical mechanism", ("public-example",))
    return Problem("problem-a", "beneficiary_welfare", (o,), (h,), ("seasonal change",))

def plan(domain="finance"):
    from manager_core.models.intervention import InterventionPlan, InterventionOption
    return InterventionPlan((
        InterventionOption("do-nothing",domain,"test-area","NO_ACTION",0,0,None,True),
        InterventionOption("opt-1",domain,"test-area","fixture_change",2.0,0.1,(5.0,8.0),False)
    ))

def grant(domain="finance"):
    from manager_core.authority import Grant
    return Grant("grant-001","test-issuer",domain,"fixture_change","test-area",
                 5.0,NOW-timedelta(hours=1),NOW+timedelta(hours=2))

def verifier():
    from manager_core.authority import AuthorityVerifier
    return AuthorityVerifier({"test-issuer":b"test-secret-only-do-not-use-in-production"})

class ProvenanceTests(unittest.TestCase):
    def test_K001_fail_closed_unknown_rights_private_or_missing_hash(self):
        from manager_core.models.source import Source
        s=source()
        self.assertEqual(s.content_sha256,"a"*64)
        for change in ({"rights":"hold"},{"privacy_class":"unknown"},
                       {"privacy_class":"public_personal"},{"content_sha256":""},
                       {"url":"http://localhost/data"},{"url":"https://127.0.0.1/x"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                Source(**{**vars(s),**change})
        with self.assertRaises(ValueError):
            s.require_fresh(NOW+timedelta(days=4),max_age_hours=24)

    def test_K002_timestamp_unit_missingness_distinguish_observations(self):
        self.assertNotEqual(observation(),observation(unit="kg"))
        self.assertNotEqual(observation(),observation(recorded_at=NOW+timedelta(minutes=1)))
        with self.assertRaises(ValueError): observation(value=None)
        with self.assertRaises(ValueError): observation(value=3,missing_reason="unknown")
        self.assertIsNone(observation(value=None,missing_reason="sensor_offline").value)

    def test_K003_unsupported_causal_claim_is_rejected(self):
        from manager_core.models.problem import Problem,CausalHypothesis
        p=problem()
        with self.assertRaises(ValueError):
            Problem(p.problem_id,p.target_metric,p.observations,
                    (CausalHypothesis("certainty","mechanism",("missing-source",)),),p.alternative_explanations)
        with self.assertRaises(ValueError):
            Problem(p.problem_id,p.target_metric,p.observations,p.causal_hypotheses,())

    def test_K004_NO_ACTION_retained_on_uncertainty(self):
        from manager_core.models.intervention import InterventionPlan
        p=plan()
        self.assertEqual(p.choose(supports_causal=False).action,"NO_ACTION")
        self.assertEqual(p.choose(supports_causal=True).action,"fixture_change")
        with self.assertRaises(ValueError):
            InterventionPlan((p.options[1],))

    def test_K005_forecast_and_causal_scores_are_distinct(self):
        from manager_core.forecast import ForecastDistribution,RCTEffectEstimate,prediction_score,effect_error
        f=ForecastDistribution({"yes":0.6,"no":0.4},"event",("train-1",))
        self.assertEqual(prediction_score(f,{"yes":0.7,"no":0.3}).kind,"descriptive_tvd")
        a=RCTEffectEstimate(0.2,0.1,0.3,"randomized-study")
        self.assertEqual(effect_error(a,0.1).kind,"causal_ate_absolute_error")
        with self.assertRaises(TypeError): effect_error(f,0.1)

class ExecutionTests(unittest.TestCase):
    def test_K006_illegal_transitions_and_unknown_never_verified(self):
        from manager_core.state_machine import StateMachine,State
        m=StateMachine()
        with self.assertRaises(ValueError): m.transition(State.VERIFIED)
        for state in (State.HYPOTHESIZED,State.PROPOSED,State.RISK_CHECKED,State.AUTHORIZED):
            m.transition(state)
        m.transition(State.UNKNOWN_EFFECT)
        with self.assertRaises(ValueError): m.transition(State.VERIFIED)
        self.assertEqual(m.state,State.UNKNOWN_EFFECT)

    def test_K007_expired_forged_revoked_wrong_domain_overbudget(self):
        from manager_core.authority import AuthorityVerifier
        v=verifier()
        g=grant()
        sig=v.sign_for_fixture(g)
        self.assertTrue(v.authorize(g,sig,"finance","fixture_change","test-area",2,NOW))
        for s,d,a,t,c,at in [("forged","finance","fixture_change","test-area",2,NOW),
              (sig,"environment","fixture_change","test-area",2,NOW),
              (sig,"finance","other","test-area",2,NOW),
              (sig,"finance","fixture_change","wrong",2,NOW),
              (sig,"finance","fixture_change","test-area",6,NOW),
              (sig,"finance","fixture_change","test-area",2,NOW+timedelta(days=2))]:
            with self.subTest(s=s,d=d,c=c),self.assertRaises(PermissionError):
                v.authorize(g,s,d,a,t,c,at)
        revoked=AuthorityVerifier({"test-issuer":b"test-secret-only-do-not-use-in-production"},revoked={"grant-001"})
        with self.assertRaises(PermissionError):
            revoked.authorize(g,sig,"finance","fixture_change","test-area",2,NOW)

    def test_K008_ten_replays_restart_once_and_aggregate_budget(self):
        from manager_core.outbox import DurableOutbox
        from manager_core.adapters.fixtures import OfflineFixtureAdapter
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"outbox.sqlite3"
            a=OfflineFixtureAdapter("finance","fixture_change","test-area")
            v=verifier();g=grant();sig=v.sign_for_fixture(g)
            out=DurableOutbox(db)
            for _ in range(10):
                r=out.execute("planned-effect-001",g,sig,v,a,2,NOW)
                self.assertEqual(r.status,"SUBMITTED")
            self.assertEqual(a.send_calls,1)
            self.assertEqual(DurableOutbox(db).record("planned-effect-001").status,"SUBMITTED")
            with self.assertRaises(PermissionError):
                out.execute("planned-effect-002",g,sig,v,a,4,NOW)
            with self.assertRaises(ValueError):
                out.execute("planned-effect-001",g,sig,v,a,3,NOW)

    def test_K008_live_adapter_refused_even_with_signed_grant(self):
        from manager_core.outbox import DurableOutbox
        from manager_core.adapters.fixtures import OfflineFixtureAdapter
        with tempfile.TemporaryDirectory() as tmp:
            out=DurableOutbox(Path(tmp)/"effects.sqlite")
            a=OfflineFixtureAdapter("finance","fixture_change","test-area")
            a.offline_fixture=False
            v=verifier();g=grant()
            with self.assertRaises(PermissionError):
                out.execute("live-attempt",g,v.sign_for_fixture(g),v,a,2,NOW)
            self.assertIsNone(out.record("live-attempt"))

    def test_K009_timeout_after_effect_never_resubmitted(self):
        from manager_core.outbox import DurableOutbox
        from manager_core.reconcile import Reconciler
        from manager_core.adapters.fixtures import OfflineFixtureAdapter
        with tempfile.TemporaryDirectory() as tmp:
            out=DurableOutbox(Path(tmp)/"outbox.sqlite")
            a=OfflineFixtureAdapter("finance","fixture_change","test-area",timeout_after_effect=True)
            v=verifier();g=grant();sig=v.sign_for_fixture(g)
            self.assertEqual(out.execute("uncertain",g,sig,v,a,2,NOW).status,"UNKNOWN")
            for _ in range(10):
                self.assertEqual(out.execute("uncertain",g,sig,v,a,2,NOW).status,"UNKNOWN")
            self.assertEqual(a.send_calls,1)
            r=Reconciler(out).reconcile("uncertain",a)
            self.assertEqual(r.status,"PRESENT")
            self.assertEqual(a.send_calls,1)

    def test_K009_lookup_failure_stays_UNKNOWN(self):
        from manager_core.outbox import DurableOutbox
        from manager_core.reconcile import Reconciler
        from manager_core.adapters.fixtures import OfflineFixtureAdapter
        with tempfile.TemporaryDirectory() as tmp:
            out=DurableOutbox(Path(tmp)/"outbox.sqlite")
            a=OfflineFixtureAdapter("finance","fixture_change","test-area",timeout_after_effect=True)
            v=verifier();g=grant()
            out.execute("lost",g,v.sign_for_fixture(g),v,a,2,NOW)
            a.lookup_fails=True
            self.assertEqual(Reconciler(out).reconcile("lost",a).status,"UNKNOWN")
            self.assertEqual(a.send_calls,1)

    def test_K010_executor_receipt_is_not_independent_evidence(self):
        from manager_core.verifier import ExternalReadback,verify_outcome
        from manager_core.outbox import EffectRecord
        r=EffectRecord("key","grant-001","finance","fixture_change","test-area",2,"SUBMITTED","receipt-x")
        self.assertEqual(verify_outcome(r,None).status,"NOT_VERIFIED")
        rb=ExternalReadback("key","fixture-executor","fixture-executor",NOW,10,"receipt-x")
        self.assertEqual(verify_outcome(r,rb).status,"NOT_VERIFIED")
        rb=ExternalReadback("key","fixture-sensor","fixture-executor",NOW,10,"receipt-x")
        self.assertEqual(verify_outcome(r,rb).status,"VERIFIED_FIXTURE_ONLY")
        self.assertEqual(verify_outcome(r,rb).proof_level,"P0")
        self.assertEqual(verify_outcome(r,ExternalReadback("other","fixture-sensor","fixture-executor",NOW,10,"receipt-x")).status,"NOT_VERIFIED")

class EvaluationTests(unittest.TestCase):
    def test_K011_no_comparator_no_harms_or_activity_cannot_prove_benefit(self):
        from manager_core.evaluator import Comparator,evaluate_outcome
        c=Comparator("randomized",True,"https://example.org/preregistered",True)
        self.assertEqual(evaluate_outcome(5,3,7,1,None,c,"welfare").status,"UNKNOWN_HARMS")
        self.assertEqual(evaluate_outcome(5,3,7,1,0,None,"welfare").status,"NO_COMPARATOR")
        self.assertEqual(evaluate_outcome(5,3,7,1,0,c,"activity").status,"ACTIVITY_ONLY")
        e=evaluate_outcome(-5,-7,-3,1,2,c,"welfare")
        self.assertEqual(e.status,"NEGATIVE")
        self.assertLess(e.net_effect,0)
        self.assertEqual(e.proof_level,"P0")

    def test_K012_holdout_shadow_and_rollback_persist(self):
        from manager_core.learning import PolicyLearner
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"policy.sqlite"
            l=PolicyLearner(path)
            l.initialize("safe-v1")
            with self.assertRaises(ValueError):
                l.propose("unsafe-v2",.1,.2,("study-A",),("study-A",))
            l.propose("candidate-v2",.1,.2,("study-A",),("study-B",))
            self.assertTrue(l.promote("candidate-v2",baseline_loss=.4))
            self.assertEqual(l.active(),"candidate-v2")
            self.assertEqual(l.observe_loss(.8,max_allowed_loss=.4),"safe-v1")
            self.assertEqual(PolicyLearner(path).active(),"safe-v1")

    def test_K013_chain_audit_preserves_UNKNOWN_rejects_secrets(self):
        from manager_core.audit import AuditTrail
        with tempfile.TemporaryDirectory() as tmp:
            a=AuditTrail(Path(tmp)/"audit.sqlite")
            a.append("run-1","source",{"source_id":"public-example"})
            a.append("run-1","execution",{"status":"UNKNOWN"})
            self.assertTrue(a.verify_chain("run-1"))
            self.assertEqual(a.trace("run-1")[-1]["data"]["status"],"UNKNOWN")
            with self.assertRaises(ValueError):
                a.append("run-1","authorization",{"api_token":"secret"})
            self.assertEqual(a.public_blessing("run-1")["benefit_status"],"NOT_MEASURED")

class CrossDomainTests(unittest.TestCase):
    def test_K014_same_kernel_two_adapters_and_NO_ACTION(self):
        from manager_core.kernel import ManagerKernel
        from manager_core.adapters.fixtures import OfflineFixtureAdapter,OfflineFixtureSensor
        from manager_core.outbox import DurableOutbox
        from manager_core.audit import AuditTrail
        with tempfile.TemporaryDirectory() as tmp:
            k=ManagerKernel(DurableOutbox(Path(tmp)/"outbox.sqlite"),verifier(),
                            AuditTrail(Path(tmp)/"audit.sqlite"))
            outcomes=[]
            for domain in ("finance","environment"):
                a=OfflineFixtureAdapter(domain,"fixture_change","test-area")
                g=grant(domain); sig=verifier().sign_for_fixture(g)
                p=plan(domain)
                result=k.run("run-"+domain,problem(),p,g,sig,a,OfflineFixtureSensor(a),NOW,causal_support=True)
                outcomes.append(result.status)
                self.assertEqual(a.send_calls,1)
                self.assertEqual(result.proof_level,"P0")
            self.assertEqual(outcomes,["VERIFIED_FIXTURE_ONLY"]*2)
            a=OfflineFixtureAdapter("finance","fixture_change","test-area")
            g=grant()
            result=k.run("run-abstain",problem(),plan(),g,verifier().sign_for_fixture(g),
                         a,OfflineFixtureSensor(a),NOW,causal_support=False)
            self.assertEqual(result.status,"NO_ACTION")
            self.assertEqual(a.send_calls,0)

    def test_K014_timeout_unknown_no_blessing(self):
        from manager_core.kernel import ManagerKernel
        from manager_core.adapters.fixtures import OfflineFixtureAdapter,OfflineFixtureSensor
        from manager_core.outbox import DurableOutbox
        from manager_core.audit import AuditTrail
        with tempfile.TemporaryDirectory() as tmp:
            audit=AuditTrail(Path(tmp)/"audit.sqlite")
            k=ManagerKernel(DurableOutbox(Path(tmp)/"outbox.sqlite"),verifier(),audit)
            a=OfflineFixtureAdapter("environment","fixture_change","test-area",timeout_after_effect=True)
            a.lookup_fails=True
            g=grant("environment");sig=verifier().sign_for_fixture(g)
            result=k.run("run-unknown",problem(),plan("environment"),g,sig,a,
                         OfflineFixtureSensor(a),NOW,causal_support=True)
            self.assertEqual(result.status,"UNKNOWN_EFFECT")
            self.assertEqual(a.send_calls,1)
            self.assertEqual(audit.public_blessing("run-unknown")["benefit_status"],"NOT_MEASURED")
if __name__=="__main__":
    unittest.main()
