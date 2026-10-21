"""Exercise actual files and the original release guard, with no network/write token."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from datetime import datetime, timedelta, timezone
from phase06_fixed_clock import FixedReviewDate

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,22,tzinfo=timezone.utc)


class PublisherIntegrationTests(unittest.TestCase):
    def load(self):
        p=ROOT/'scripts/phase06_kernel_release.py'
        spec=importlib.util.spec_from_file_location('kernel_release',p)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        return m

    def setup_files(self,root):
        from manager_core.digital_environment import build_site
        from manager_core.digital_handoff import plan_release
        old,new,checkout=root/'old',root/'new',root/'pages'
        checkout.mkdir();(checkout/'unrelated.html').write_text('keep exact bytes')
        catalog=json.loads((ROOT/'public_goods/service/catalog.json').read_text())
        with patch('manager_core.digital_environment.datetime',FixedReviewDate):
            before=build_site(catalog,old,'a'*40);after=build_site(catalog,new,'b'*40)
            build_site(catalog,checkout/'manager-support','a'*40)
        intent=root/'intent.json';intent.write_text(json.dumps(plan_release(before,after,NOW)))
        audit=root/'audit.json';audit.write_text(json.dumps({
            'content_rights':'LINK_ONLY','human_outcome':'NOT_MEASURED',
            'sources':[{'id':r['id'],'url':r['url'],'status':'REACHABLE_NOT_OUTCOME',
                        'http_status':200,'sha256':'f'*64,'observed_at':NOW.isoformat()} for r in catalog['resources']]}))
        return old,new,checkout,intent,audit

    def environment(self):
        from manager_core.digital_handoff import REPOSITORY,SOURCE_REF,WORKFLOW
        return {'GITHUB_REPOSITORY':REPOSITORY,'GITHUB_REF':SOURCE_REF,
                'GITHUB_WORKFLOW_REF':f'{REPOSITORY}/{WORKFLOW}@{SOURCE_REF}',
                'GITHUB_SHA':'b'*40,'GITHUB_RUN_ID':'12345','MANAGER_RELEASE_ENABLED':'true'}

    def test_real_file_admission_replay_and_exact_bounded_rollback(self):
        from manager_core.digital_environment import verify_bundle
        m=self.load()
        with TemporaryDirectory() as t,patch.dict(os.environ,self.environment()),patch('manager_core.digital_environment.datetime',FixedReviewDate):
            old,new,pages,intent,audit=self.setup_files(Path(t))
            first=m.admit(new,pages,audit,intent,Path(t)/'first.json',NOW)
            self.assertEqual(first['status'],'ADMITTED_MANAGER_PREFIX_ONLY')
            self.assertEqual(len(first['changed_files']),7)
            second=m.admit(new,pages,audit,intent,Path(t)/'second.json',NOW)
            self.assertEqual(second['status'],'NO_ACTION_ALREADY_PRESENT')
            self.assertEqual(second['changed_files'],[])
            self.assertFalse(second['dispatch_deployment'])
            # Existing scope guard can restore an exact verified previous bundle.
            rollback=m.stage_release(old,pages,json.loads(audit.read_text()))
            self.assertEqual(rollback['status'],'STAGED_MANAGER_ONLY')
            self.assertTrue(verify_bundle(pages/'manager-support',json.loads((old/'manifest.json').read_text())))
            self.assertEqual((pages/'unrelated.html').read_text(),'keep exact bytes')

    def test_missing_workflow_identity_revocation_or_stale_audit_writes_nothing(self):
        m=self.load()
        for bad in ('workflow','revoked','stale','future'):
            with self.subTest(bad=bad),TemporaryDirectory() as t,patch.dict(os.environ,self.environment()),patch('manager_core.digital_environment.datetime',FixedReviewDate):
                old,new,pages,intent,audit=self.setup_files(Path(t))
                snapshot={p.name:p.read_bytes() for p in (pages/'manager-support').iterdir()}
                if bad=='workflow':os.environ['GITHUB_WORKFLOW_REF']='wrong'
                if bad=='revoked':os.environ['MANAGER_RELEASE_ENABLED']='false'
                if bad in ('stale','future'):
                    d=json.loads(audit.read_text())
                    shift=timedelta(days=-1 if bad=='stale' else 1)
                    for r in d['sources']:r['observed_at']=(NOW+shift).isoformat()
                    audit.write_text(json.dumps(d))
                with self.assertRaises((ValueError,PermissionError)):
                    m.admit(new,pages,audit,intent,Path(t)/'admission.json',NOW)
                self.assertEqual(snapshot,{p.name:p.read_bytes() for p in (pages/'manager-support').iterdir()})


if __name__=='__main__':unittest.main()
