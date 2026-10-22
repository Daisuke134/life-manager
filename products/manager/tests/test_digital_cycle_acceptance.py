"""E16 reference cycle: persistent owner, independent served files, bounded rollback."""
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import test_owned_digital_cycle as owned_tests
from test_owned_effect_recovery import GitOccurrenceFixture
from manager_core.digital_handoff import plan_release
from manager_core.owned_cycle import CycleConfig,CycleStore,run_owned_cycle,LocalGitCycleSandbox
from test_candidate_verification import NOW


class CycleAcceptanceTests(unittest.TestCase):
    def prepare(self,tmp):
        root=Path(tmp);k,c,a,s=owned_tests.OwnedChangeTests().prepare(tmp)
        packet=plan_release(json.loads((c.baseline_bundle/'manifest.json').read_text()),json.loads((c.candidate_bundle/'manifest.json').read_text()),NOW)
        git=GitOccurrenceFixture(root/'external-git',c.baseline_bundle,c.candidate_bundle,packet)
        catalog=json.loads((Path(__file__).resolve().parents[1]/'public_goods/service/catalog.json').read_text())
        audit={'content_rights':'LINK_ONLY','human_outcome':'NOT_MEASURED','sources':[
            {'id':r['id'],'url':r['url'],'status':'REACHABLE_NOT_OUTCOME','http_status':200,'sha256':'f'*64,'observed_at':NOW.isoformat()} for r in catalog['resources']]}
        adapter=LocalGitCycleSandbox(git.root,root/'served',c,a,s,audit)
        config=CycleConfig('fixture-owner',60)
        return config,CycleStore(root/'persistent'),adapter,git

    def test_host_required_not_ci_deployed(self):
        with TemporaryDirectory() as tmp:
            r=run_owned_cycle(CycleConfig('unverified-owner',60),CycleStore(Path(tmp)/'state'),now=NOW)
            self.assertEqual(r['status'],'DEPLOYMENT_HOST_REQUIRED');self.assertFalse(r['deployed'])

    def test_cycle_single_write_independent_readback_replay_zero(self):
        with TemporaryDirectory() as tmp:
            conf,store,host,git=self.prepare(tmp)
            first=run_owned_cycle(conf,store,host=host,now=NOW)
            self.assertEqual(first['status'],'VERIFIED_SANDBOX_TECHNICAL');self.assertEqual(first['writes'],1)
            self.assertEqual(first['human_outcome'],'NOT_MEASURED');self.assertFalse(first['deployed'])
            second=run_owned_cycle(conf,store,host=host,now=NOW+timedelta(minutes=1))
            self.assertEqual(second['writes'],0);self.assertEqual(git.git('rev-list','--count','HEAD'),'2')

    def test_readback_differs_from_success_stops_and_restores_exact_old_bundle(self):
        with TemporaryDirectory() as tmp:
            conf,store,host,git=self.prepare(tmp);host.regress_served=True
            r=run_owned_cycle(conf,store,host=host,now=NOW)
            self.assertEqual(r['status'],'ROLLED_BACK_SANDBOX_REGRESSION')
            for p in host.context.baseline_bundle.iterdir():
                self.assertEqual((host.checkout/'manager-support'/p.name).read_bytes(),p.read_bytes())
                self.assertEqual((host.served/p.name).read_bytes(),p.read_bytes())
            self.assertEqual((host.checkout/'unrelated.html').read_bytes(),b'preserve me')
            self.assertEqual(run_owned_cycle(conf,store,host=host,now=NOW+timedelta(hours=1))['status'],'STOPPED_REGRESSION')

    def test_missed_schedule_catches_up_once(self):
        with TemporaryDirectory() as tmp:
            c,s,h,g=self.prepare(tmp)
            run_owned_cycle(c,s,host=h,now=NOW)
            later=NOW+timedelta(minutes=25)
            self.assertEqual(run_owned_cycle(c,s,host=h,now=later)['writes'],0)
            self.assertEqual(run_owned_cycle(c,s,host=h,now=later)['status'],'NOT_DUE')
            self.assertEqual(s.cycle_count(),2)

    def test_active_owner_rejects_competing_worker(self):
        with TemporaryDirectory() as tmp:
            c,s,h,g=self.prepare(tmp)
            with s.owner_lock() as acquired:
                self.assertTrue(acquired)
                self.assertEqual(run_owned_cycle(c,CycleStore(s.root),host=h,now=NOW)['status'],'OWNER_BUSY')

    def test_lost_checkpoint_never_repeats_committed_effect(self):
        import sqlite3
        with TemporaryDirectory() as tmp:
            c,s,h,g=self.prepare(tmp);run_owned_cycle(c,s,host=h,now=NOW)
            with sqlite3.connect(s.db) as db:db.execute('DELETE FROM schedule')
            r=run_owned_cycle(c,s,host=h,now=NOW)
            self.assertEqual(r['writes'],0);self.assertEqual(g.git('rev-list','--count','HEAD'),'2')

    def test_remote_bearing_repo_is_not_a_sandbox(self):
        with TemporaryDirectory() as tmp:
            c,s,h,g=self.prepare(tmp);g.git('remote','add','origin','https://example.invalid/forbidden')
            with self.assertRaises(PermissionError):run_owned_cycle(c,s,host=h,now=NOW)

    def test_lost_send_response_is_unknown_count_then_reconciled_without_resend(self):
        with TemporaryDirectory() as tmp:
            c,s,h,g=self.prepare(tmp);send=h.send
            def lose_response(*args):
                send(*args)
                raise OSError('lost response after commit')
            h.send=lose_response
            first=run_owned_cycle(c,s,host=h,now=NOW)
            self.assertEqual(first['status'],'UNKNOWN');self.assertIsNone(first['writes'])
            second=run_owned_cycle(c,s,host=h,now=NOW+timedelta(minutes=1))
            self.assertEqual(second['status'],'VERIFIED_SANDBOX_TECHNICAL');self.assertEqual(second['writes'],0)
            self.assertEqual(g.git('rev-list','--count','HEAD'),'2')

    def test_unknown_shadow_record_does_not_become_zero_or_promote_policy(self):
        with TemporaryDirectory() as tmp:
            c,s,h,g=self.prepare(tmp)
            s.learning.initialize('fixed-policy')
            s.learning.record_sandbox_technical({'status':'UNKNOWN','writes':None,'deployed':False,
                                               'proof_level':'P0','human_outcome':'NOT_MEASURED'})
            self.assertIsNone(s.learning.sandbox_technical_observations()[0]['writes'])
            self.assertEqual(s.learning.active(),'fixed-policy')

    def test_candidate_changed_after_assessment_is_denied_before_fixture_commit(self):
        from test_candidate_verification import mutate
        with TemporaryDirectory() as tmp:
            c,s,h,g=self.prepare(tmp);send=h.send
            def replace_candidate(*args):
                mutate(h.context.candidate_bundle,'finance.html',lambda b:b+b'changed after assessment')
                return send(*args)
            h.send=replace_candidate
            self.assertEqual(run_owned_cycle(c,s,host=h,now=NOW)['status'],'UNKNOWN')
            self.assertEqual(g.git('rev-list','--count','HEAD'),'1')
