"""Exercise actual files and the original release guard, with no network/write token."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
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

    def test_plan_selects_versioned_main_intent_only_for_main_workflow_ref(self):
        from manager_core.digital_handoff import MAIN_SOURCE_REF, SOURCE_REF
        m=self.load()
        with TemporaryDirectory() as t,patch('manager_core.digital_environment.datetime',FixedReviewDate):
            old,new,_,_,_=self.setup_files(Path(t))
            before=json.loads((old/'manifest.json').read_text())
            bodies={name:(old/name).read_bytes() for name in before['files']}
            bodies['manifest.json']=(old/'manifest.json').read_bytes()
            with patch.object(m,'live_snapshot',return_value=(before,bodies)),patch.dict(os.environ,{'GITHUB_REF':MAIN_SOURCE_REF}):
                main_packet=m.prepare(new,Path(t)/'main-out',NOW)
            self.assertEqual(main_packet['ref'],MAIN_SOURCE_REF)
            self.assertEqual(main_packet['schema'],'manager.digital-handoff.v2')
            with patch.object(m,'live_snapshot',return_value=(before,bodies)),patch.dict(os.environ,{'GITHUB_REF':'refs/heads/research/manager-e01-e16-execution-20261022'}):
                research_packet=m.prepare(new,Path(t)/'research-out',NOW)
            self.assertEqual(research_packet['ref'],SOURCE_REF)
            self.assertEqual(research_packet['schema'],'manager.digital-handoff.v1')

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

    def test_main_admission_requires_fresh_bound_request_and_exact_target_parent(self):
        from manager_core.digital_handoff import MAIN_SOURCE_REF, plan_release
        from manager_core.owned_platform_host import create_owned_workflow_request
        m=self.load()
        with TemporaryDirectory() as t,patch('manager_core.digital_environment.datetime',FixedReviewDate):
            old,new,pages,intent,audit=self.setup_files(Path(t))
            subprocess.run(['git','-C',str(pages),'init','-q'],check=True)
            subprocess.run(['git','-C',str(pages),'config','user.name','Manager fixture'],check=True)
            subprocess.run(['git','-C',str(pages),'config','user.email','manager-fixture@example.invalid'],check=True)
            subprocess.run(['git','-C',str(pages),'add','.'],check=True)
            subprocess.run(['git','-C',str(pages),'commit','-qm','fixture baseline'],check=True)
            parent=subprocess.check_output(['git','-C',str(pages),'rev-parse','HEAD'],text=True).strip()
            before=json.loads((old/'manifest.json').read_text())
            candidate=json.loads((new/'manifest.json').read_text())
            packet=plan_release(before,candidate,NOW,source_ref=MAIN_SOURCE_REF)
            intent.write_text(json.dumps(packet))
            request=create_owned_workflow_request(packet,'manager-owner-1',parent)
            env={'GITHUB_REPOSITORY':'Daisuke134/life-manager','GITHUB_REF':MAIN_SOURCE_REF,
                 'GITHUB_WORKFLOW_REF':f'Daisuke134/life-manager/.github/workflows/manager-phase06-service.yml@{MAIN_SOURCE_REF}',
                 'GITHUB_SHA':'b'*40,'GITHUB_RUN_ID':'12345','GITHUB_EVENT_NAME':'workflow_dispatch',
                 'MANAGER_RELEASE_ENABLED':'true','MANAGER_OWNER_ID':'manager-owner-1',
                 'MANAGER_REQUEST_ID':request.request_id}
            original={p.name:p.read_bytes() for p in (pages/'manager-support').iterdir()}
            for changes in ({'GITHUB_EVENT_NAME':'push'},
                            {'MANAGER_OWNER_ID':'other-owner'},
                            {'MANAGER_RELEASE_ENABLED':'false'}):
                with self.subTest(changes=changes),patch.dict(os.environ,{**env,**changes}),self.assertRaises(PermissionError):
                    m.admit(new,pages,audit,intent,Path(t)/'rejected-admission.json',NOW,
                            owned_request=request)
                self.assertEqual(original,{p.name:p.read_bytes() for p in (pages/'manager-support').iterdir()})
            with patch.dict(os.environ,env):
                result=m.admit(new,pages,audit,intent,Path(t)/'main-admission.json',NOW,
                               owned_request=request)
            self.assertEqual(result['status'],'ADMITTED_MANAGER_PREFIX_ONLY')
            self.assertEqual(len(result['changed_files']),7)

            snapshot={p.name:p.read_bytes() for p in (pages/'manager-support').iterdir()}
            subprocess.run(['git','-C',str(pages),'add','manager-support'],check=True)
            subprocess.run(['git','-C',str(pages),'commit','-qm','bound request replay fixture'],check=True)
            with patch.dict(os.environ,env),self.assertRaises(PermissionError):
                m.admit(new,pages,audit,intent,Path(t)/'replayed-admission.json',NOW,
                        owned_request=request)
            self.assertEqual(snapshot,{p.name:p.read_bytes() for p in (pages/'manager-support').iterdir()})
            bad_request=create_owned_workflow_request(packet,'manager-owner-1','f'*40)
            with patch.dict(os.environ,env),self.assertRaises(PermissionError):
                m.admit(new,pages,audit,intent,Path(t)/'bad-admission.json',NOW,
                        owned_request=bad_request)
            self.assertEqual(snapshot,{p.name:p.read_bytes() for p in (pages/'manager-support').iterdir()})


if __name__=='__main__':unittest.main()
