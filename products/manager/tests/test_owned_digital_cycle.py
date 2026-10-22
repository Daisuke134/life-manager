"""Host-owned narrow handoff retains the original platform admission."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from test_candidate_verification import setup,NOW
from manager_core.audit import AuditTrail
from manager_core.kernel import ManagerKernel
from manager_core.authority import OwnedDigitalScope
from manager_core.collaboration import PlannerContext,PublicFact
from manager_core.digital_handoff import ALLOWED_PATHS,OwnedChangeContext
from manager_core.candidate_verification import verify_candidate

class OwnedChangeTests(unittest.TestCase):
    def prepare(self,tmp):
        a,b,c=setup(Path(tmp))
        context=OwnedChangeContext('owned-run',PlannerContext('Correct the official link',(PublicFact(c.official_sources[0],'Official public target'),),NOW),a,b,c)
        scope=OwnedDigitalScope('host-scope',frozenset(ALLOWED_PATHS),NOW-timedelta(minutes=1),NOW+timedelta(hours=1),7)
        kernel=ManagerKernel(None,None,AuditTrail(Path(tmp)/'trace.sqlite'))
        return kernel,context,verify_candidate(a,b,c),scope

    def test_proposal_is_inert_platform_authority_required(self):
        with TemporaryDirectory() as tmp:
            k,c,a,s=self.prepare(tmp);r=k.prepare_owned_change(c,a,s,NOW)
            self.assertEqual(r.status,'PREPARED_PLATFORM_AUTHORITY_REQUIRED')
            self.assertEqual(r.run_id,'owned-run');self.assertFalse(r.authorized_execution)
            self.assertEqual(len(r.packet['allowed_paths']),7)
            self.assertTrue(k.audit.verify_chain('owned-run'))
            self.assertEqual(k.audit.trace('unrelated-run'),[])

    def test_expired_or_revoked_scope_denies(self):
        with TemporaryDirectory() as tmp:
            k,c,a,s=self.prepare(tmp)
            for scope in (None,replace(s,revoked=True),replace(s,expires_at=NOW)):
                self.assertEqual(k.prepare_owned_change(c,a,scope,NOW).status,'NO_ACTION')

    def test_assessment_cannot_be_forged_for_different_bundle(self):
        with TemporaryDirectory() as tmp:
            k,c,a,s=self.prepare(tmp)
            self.assertEqual(k.prepare_owned_change(c,replace(a,candidate_digest='f'*64),s,NOW).status,'NO_ACTION')

    def test_third_party_or_uncited_context_denies(self):
        with TemporaryDirectory() as tmp:
            k,c,a,s=self.prepare(tmp)
            bad=replace(c.criteria,candidate=replace(c.criteria.candidate,target='https://third-party.example/path'))
            self.assertEqual(k.prepare_owned_change(replace(c,criteria=bad),a,s,NOW).status,'NO_ACTION')
            fact=replace(c.planner.facts[0],source=replace(c.planner.facts[0].source,content_sha256='f'*64))
            self.assertEqual(k.prepare_owned_change(replace(c,planner=replace(c.planner,facts=(fact,))),a,s,NOW).status,'NO_ACTION')

    def test_scope_must_cover_all_changed_files(self):
        with TemporaryDirectory() as tmp:
            k,c,a,s=self.prepare(tmp)
            self.assertEqual(k.prepare_owned_change(c,a,replace(s,max_changed_files=1),NOW).status,'NO_ACTION')

    def test_generic_fixture_executor_stays_disabled(self):
        from manager_core.outbox import DurableOutbox
        with TemporaryDirectory() as tmp:
            with self.assertRaises(PermissionError):
                DurableOutbox(Path(tmp)/'box').execute('key',None,None,None,object(),0,NOW)

    def test_host_bridge_keeps_original_identity_and_revalidates_scope(self):
        from unittest.mock import patch
        import os
        from test_digital_publisher_integration import PublisherIntegrationTests
        with TemporaryDirectory() as tmp:
            k,c,a,s=self.prepare(tmp);prepared=k.prepare_owned_change(c,a,s,NOW)
            publisher=PublisherIntegrationTests().load()
            for scope in (s,replace(s,revoked=True)):
                with patch.dict(os.environ,{},clear=True),self.assertRaises(PermissionError):
                    publisher.admit_owned(c,a,scope,prepared,Path(tmp)/'checkout',Path(tmp)/'audit',Path(tmp)/'result',NOW)
