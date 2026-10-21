"""Adversarial regression tests: privacy, stale sources, spoofing and cross-domain authority."""
import concurrent.futures
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_phase05_kernel import NOW, source, observation, problem, plan, grant, verifier


class AdversarialTests(unittest.TestCase):
    def test_source_must_match_observed_bytes(self):
        from manager_core.models.source import Source
        raw=b"public aggregate,not a person\n"
        from hashlib import sha256
        s=replace(source(),content_sha256=sha256(raw).hexdigest())
        self.assertTrue(s.verify_content(raw))
        with self.assertRaises(ValueError): s.verify_content(b"modified upstream content")

    def test_stale_public_observation_abstains_even_with_valid_grant(self):
        from manager_core.models.problem import Problem,CausalHypothesis
        from manager_core.models.observation import Observation
        from manager_core.kernel import ManagerKernel
        from manager_core.outbox import DurableOutbox
        from manager_core.audit import AuditTrail
        from manager_core.adapters.fixtures import OfflineFixtureAdapter,OfflineFixtureSensor
        old=replace(source(),retrieved_at=NOW-timedelta(days=5))
        obs=Observation(old,"public-count","test-area",10.0,"count",NOW-timedelta(days=5))
        p=Problem("stale","welfare",(obs,),(
            CausalHypothesis("possible","seasonality",("public-example",)),),("different explanation",))
        with TemporaryDirectory() as tmp:
            k=ManagerKernel(DurableOutbox(Path(tmp)/"outbox.db"),verifier(),AuditTrail(Path(tmp)/"audit.db"))
            a=OfflineFixtureAdapter("finance","fixture_change","test-area")
            g=grant()
            r=k.run("stale-run",p,plan(),g,verifier().sign_for_fixture(g),
                    a,OfflineFixtureSensor(a),NOW,causal_support=True)
            self.assertEqual(r.status,"NO_ACTION")
            self.assertEqual(a.send_calls,0)

    def test_offline_flag_spoof_does_not_enable_an_untrusted_executor(self):
        from manager_core.outbox import DurableOutbox
        class FakeLiveAdapter:
            domain,action,target="finance","fixture_change","test-area"
            offline_fixture=True
            calls=0
            def send(self,key):
                self.calls+=1
                return "fake-effect"
        with TemporaryDirectory() as tmp:
            out=DurableOutbox(Path(tmp)/"out.db")
            a=FakeLiveAdapter()
            g=grant()
            with self.assertRaises(PermissionError):
                out.execute("forged-adapter",g,verifier().sign_for_fixture(g),verifier(),a,2,NOW)
            self.assertEqual(a.calls,0)
            self.assertIsNone(out.record("forged-adapter"))

    def test_plan_domain_mismatch_never_dispatches(self):
        from manager_core.kernel import ManagerKernel
        from manager_core.outbox import DurableOutbox
        from manager_core.audit import AuditTrail
        from manager_core.adapters.fixtures import OfflineFixtureAdapter,OfflineFixtureSensor
        with TemporaryDirectory() as tmp:
            k=ManagerKernel(DurableOutbox(Path(tmp)/"out.db"),verifier(),AuditTrail(Path(tmp)/"audit.db"))
            a=OfflineFixtureAdapter("environment","fixture_change","test-area")
            g=grant("environment")
            r=k.run("wrong-domain",problem(),plan("finance"),g,verifier().sign_for_fixture(g),
                    a,OfflineFixtureSensor(a),NOW,causal_support=True)
            self.assertEqual(r.status,"REJECTED")
            self.assertEqual(a.send_calls,0)

    def test_timeout_before_effect_absent_not_replayed(self):
        from manager_core.outbox import DurableOutbox
        from manager_core.reconcile import Reconciler
        from manager_core.adapters.fixtures import OfflineFixtureAdapter
        with TemporaryDirectory() as tmp:
            o=DurableOutbox(Path(tmp)/"out.db")
            a=OfflineFixtureAdapter("finance","fixture_change","test-area",timeout_before_effect=True)
            v=verifier();g=grant();sig=v.sign_for_fixture(g)
            self.assertEqual(o.execute("absent-effect",g,sig,v,a,2,NOW).status,"UNKNOWN")
            self.assertEqual(Reconciler(o).reconcile("absent-effect",a).status,"ABSENT")
            for _ in range(10): o.execute("absent-effect",g,sig,v,a,2,NOW)
            self.assertEqual(a.send_calls,1)
            self.assertEqual(o.record("absent-effect").status,"ABSENT")

    def test_simultaneous_replays_share_single_sqlite_reservation(self):
        from manager_core.outbox import DurableOutbox
        from manager_core.adapters.fixtures import OfflineFixtureAdapter
        with TemporaryDirectory() as tmp:
            o=DurableOutbox(Path(tmp)/"out.db")
            a=OfflineFixtureAdapter("finance","fixture_change","test-area")
            v=verifier();g=grant();sig=v.sign_for_fixture(g)
            def one(_): return o.execute("concurrent-intent",g,sig,v,a,2,NOW).status
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
                results=list(pool.map(one,range(10)))
            self.assertEqual(results,["SUBMITTED"]*10)
            self.assertEqual(a.send_calls,1)

    def test_audit_has_complete_public_provenance_and_options(self):
        from manager_core.kernel import ManagerKernel
        from manager_core.outbox import DurableOutbox
        from manager_core.audit import AuditTrail
        from manager_core.adapters.fixtures import OfflineFixtureAdapter,OfflineFixtureSensor
        with TemporaryDirectory() as tmp:
            trail=AuditTrail(Path(tmp)/"audit.db")
            k=ManagerKernel(DurableOutbox(Path(tmp)/"out.db"),verifier(),trail)
            a=OfflineFixtureAdapter("finance","fixture_change","test-area")
            g=grant()
            k.run("trace",problem(),plan(),g,verifier().sign_for_fixture(g),
                  a,OfflineFixtureSensor(a),NOW,causal_support=True)
            events=trail.trace("trace")
            s=next(e for e in events if e["stage"]=="source")
            self.assertEqual(s["data"]["source_url"],"https://example.org/public.csv")
            self.assertEqual(s["data"]["content_hash"],"a"*64)
            proposals=[e for e in events if e["stage"]=="proposal"]
            self.assertTrue(any(x["data"]["option_id"]=="do-nothing" for x in proposals))
            self.assertTrue(any(x["data"]["option_id"]=="opt-1" for x in proposals))
            self.assertTrue(trail.verify_chain("trace"))

    def test_missing_independent_sensor_does_not_pass(self):
        from manager_core.kernel import ManagerKernel
        from manager_core.outbox import DurableOutbox
        from manager_core.audit import AuditTrail
        from manager_core.adapters.fixtures import OfflineFixtureAdapter
        with TemporaryDirectory() as tmp:
            k=ManagerKernel(DurableOutbox(Path(tmp)/"out.db"),verifier(),AuditTrail(Path(tmp)/"audit.db"))
            a=OfflineFixtureAdapter("environment","fixture_change","test-area")
            g=grant("environment")
            r=k.run("missing-sensor",problem(),plan("environment"),g,
                    verifier().sign_for_fixture(g),a,object(),NOW,causal_support=True)
            self.assertEqual(r.status,"MEASUREMENT_MISSING")
            self.assertEqual(a.send_calls,1)

    def test_invalid_holdout_or_shadow_cannot_promote(self):
        from manager_core.learning import PolicyLearner
        with TemporaryDirectory() as tmp:
            l=PolicyLearner(Path(tmp)/"policy.db")
            l.initialize("safe")
            l.propose("bad",.8,.9,("a",),("b",))
            self.assertFalse(l.promote("bad",baseline_loss=.4))
            self.assertEqual(l.active(),"safe")


if __name__=="__main__":
    unittest.main()
