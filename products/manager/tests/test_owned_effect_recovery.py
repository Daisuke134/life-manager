"""Persistent intent journal and separate immutable Git fixture occurrence store."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from test_candidate_verification import setup,NOW
from manager_core.digital_handoff import plan_release,PublisherContext,REPOSITORY,SOURCE_REF,WORKFLOW,commit_message,ALLOWED_PATHS
from manager_core.outbox import OwnedEffectJournal
from manager_core.reconcile import reconcile_owned,OwnedOccurrenceEvidence


class GitOccurrenceFixture:
    """Real file/Git sandbox; no remote, token or production authority."""
    def __init__(self,root,before,after,packet):
        self.root=root;self.root.mkdir();self.after=after;self.packet=packet
        self.git('init','-q');self.git('config','user.email','fixture@example.invalid');self.git('config','user.name','Fixture')
        (root/'unrelated.html').write_bytes(b'preserve me')
        (root/'manager-support').mkdir()
        self.copy(before);self.git('add','.');self.git('commit','-qm','baseline');self.parent=self.git('rev-parse','HEAD')
    def git(self,*args):return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.DEVNULL).decode().strip()
    def copy(self,site):
        for p in site.iterdir():(self.root/'manager-support'/p.name).write_bytes(p.read_bytes())
    def send(self,expected_parent):
        # Git update-ref is target CAS. A late old worker may create an orphan
        # commit but can never advance a target with a different parent.
        self.copy(self.after);self.git('add','manager-support');tree=self.git('write-tree')
        sha=self.git('commit-tree',tree,'-p',expected_parent,'-m',commit_message(self.packet))
        self.git('update-ref','HEAD',sha,expected_parent)
        return sha
    def evidence(self,sha):
        parent=self.git('rev-parse',sha+'^')
        def bundle(ref):
            bodies={name:subprocess.check_output(['git','-C',str(self.root),'show',ref+':'+name]) for name in ALLOWED_PATHS}
            bodies={name.removeprefix('manager-support/'):body for name,body in bodies.items()}
            return json.loads(bodies['manifest.json']),bodies
        manifest,bodies=bundle(sha);old,oldb=bundle(parent)
        # Commit timestamp is read from Git, clock chosen after actual commit.
        stamp=self.git('show','-s','--format=%cI',sha)
        receipt={'sha':sha,'html_url':f'https://github.com/{REPOSITORY}/commit/{sha}',
                 'parents':[{'sha':parent}], 'commit':{'committer':{'date':stamp},'message':self.git('show','-s','--format=%B',sha)},
                 'files':[{'filename':n,'status':'modified'} for n in self.git('diff-tree','--no-commit-id','--name-only','-r',sha).splitlines()]}
        return OwnedOccurrenceEvidence(receipt,manifest,bodies,parent,old,oldb)


class OwnedRecoveryTests(unittest.TestCase):
    def prepare(self,tmp):
        root=Path(tmp);a,b,c=setup(root)
        packet=plan_release(json.loads((a/'manifest.json').read_text()),json.loads((b/'manifest.json').read_text()),NOW)
        store=GitOccurrenceFixture(root/'external-git',a,b,packet)
        journal=OwnedEffectJournal(root/'private.sqlite')
        context=PublisherContext(REPOSITORY,SOURCE_REF,WORKFLOW,'b'*40,'12345')
        return packet,store,journal,context
    def reserve(self,p,s,j,c):return j.reserve(p,c,p['baseline'],p['candidate'],s.parent,NOW)

    def test_lost_response_reconciles_exact_commit_after_restart_replay_zero(self):
        from datetime import datetime,timezone
        with TemporaryDirectory() as tmp:
            p,s,j,c=self.prepare(tmp);r=self.reserve(p,s,j,c);self.assertTrue(r.dispatch)
            sha=s.send(s.parent)  # response lost: journal remains DISPATCHING
            restarted=OwnedEffectJournal(Path(tmp)/'private.sqlite')
            result=reconcile_owned(restarted,p['effect_key'],lambda _:s.evidence(sha),datetime.now(timezone.utc)+timedelta(seconds=1))
            self.assertEqual(result.status,'PRESENT');self.assertEqual(result.receipt_ref,sha)
            self.assertFalse(self.reserve(p,s,restarted,c).dispatch)
            self.assertEqual(s.git('rev-list','--count','HEAD'),'2')
            self.assertEqual((s.root/'unrelated.html').read_bytes(),b'preserve me')

    def test_crash_before_reservation_and_after_reservation(self):
        with TemporaryDirectory() as tmp:
            p,s,j,c=self.prepare(tmp);self.assertIsNone(j.record(p['effect_key']))
            self.assertTrue(self.reserve(p,s,j,c).dispatch)
            self.assertFalse(self.reserve(p,s,OwnedEffectJournal(Path(tmp)/'private.sqlite'),c).dispatch)
            self.assertEqual(s.git('rev-list','--count','HEAD'),'1')

    def test_transient_not_found_is_unknown_and_never_retries(self):
        with TemporaryDirectory() as tmp:
            p,s,j,c=self.prepare(tmp);self.reserve(p,s,j,c)
            for reader in (lambda _:None,lambda _:(_ for _ in ()).throw(OSError('temporary outage'))):
                self.assertEqual(reconcile_owned(j,p['effect_key'],reader,NOW).status,'UNKNOWN')
                self.assertFalse(self.reserve(p,s,j,c).dispatch)

    def test_concurrent_workers_reserve_once(self):
        with TemporaryDirectory() as tmp:
            p,s,j,c=self.prepare(tmp)
            with ThreadPoolExecutor(max_workers=4) as pool:
                claims=list(pool.map(lambda _:self.reserve(p,s,j,c),range(8)))
            self.assertEqual(sum(r.dispatch for r in claims),1)

    def test_same_key_changed_body_denied(self):
        with TemporaryDirectory() as tmp:
            p,s,j,c=self.prepare(tmp);self.reserve(p,s,j,c)
            bad=dict(p);bad['candidate_sha256']='f'*64
            with self.assertRaises(ValueError):j.reserve(bad,c,p['baseline'],p['candidate'],s.parent,NOW)

    def test_old_inflight_owner_cannot_commit_new_parent(self):
        with TemporaryDirectory() as tmp:
            p,s,j,c=self.prepare(tmp);self.reserve(p,s,j,c)
            (s.root/'unrelated.html').write_bytes(b'new independent owner')
            s.git('add','.');s.git('commit','-qm','target moved');moved=s.git('rev-parse','HEAD')
            with self.assertRaises(subprocess.CalledProcessError):s.send(s.parent)
            self.assertEqual(s.git('rev-parse','HEAD'),moved)
            self.assertFalse(self.reserve(p,s,j,c).dispatch)

    def test_new_parent_same_effect_requires_reconciliation(self):
        with TemporaryDirectory() as tmp:
            p,s,j,c=self.prepare(tmp);self.reserve(p,s,j,c)
            with self.assertRaises(ValueError):j.reserve(p,c,p['baseline'],p['candidate'],'f'*40,NOW)

    def test_wrong_occurrence_cannot_close_fence(self):
        from dataclasses import replace
        from datetime import datetime,timezone
        with TemporaryDirectory() as tmp:
            p,s,j,c=self.prepare(tmp);self.reserve(p,s,j,c);sha=s.send(s.parent)
            evidence=s.evidence(sha)
            wrong=replace(evidence,parent_commit='f'*40)
            self.assertEqual(reconcile_owned(j,p['effect_key'],lambda _:wrong,datetime.now(timezone.utc)+timedelta(seconds=1)).status,'UNKNOWN')
            self.assertNotEqual(j.record(p['effect_key']).status,'PRESENT')
