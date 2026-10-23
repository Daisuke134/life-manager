"""Exact provider collection and lag-safe delivery recovery, offline transport."""
from datetime import datetime, timedelta, timezone
import importlib
import json
from hashlib import sha256
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from unittest.mock import patch

import test_digital_cycle_acceptance as fixtures
import test_owned_effect_recovery as recovery
from test_candidate_verification import NOW
from manager_core.digital_handoff import REPOSITORY, PUBLIC_BASE
from manager_core.digital_handoff import MAIN_REF, WORKFLOW, PublisherContext, plan_release
from manager_core.digital_environment import PAGES
from manager_core.reconcile import OwnedOccurrenceEvidence
from test_digital_handoff import manifest
from manager_core.owned_cycle import run_owned_cycle
from manager_core.reconcile import reconcile_owned


class PublicCollectorTests(unittest.TestCase):
    def prepare_v1_current_fixture(self, tmp):
        packet,git,journal,publisher=recovery.OwnedRecoveryTests().prepare(tmp)
        journal.reserve(packet,publisher,packet['baseline'],packet['candidate'],git.parent,NOW)
        receipt_sha=git.send(git.parent)
        journal._present(packet['effect_key'],receipt_sha)
        occurrence=git.evidence(receipt_sha)
        observed_at=datetime.now(timezone.utc)+timedelta(seconds=1)
        journal.save_delivery(packet['effect_key'],{
            'status':'VERIFIED','effect_key':packet['effect_key'],'receipt_ref':receipt_sha,
            'candidate_sha256':packet['candidate_sha256'],'observed_at':observed_at.isoformat(),
            'proof_ref':PUBLIC_BASE,'proof_level':'P2','reason':'EXACT_SERVED_CANDIDATE',
            'human_outcome':'NOT_MEASURED'})
        target_url=f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/gh-pages'
        list_url=(f'https://api.github.com/repos/{REPOSITORY}/commits'
                  '?sha=gh-pages&per_page=100&page=1')
        detail_url=f'https://api.github.com/repos/{REPOSITORY}/commits/{receipt_sha}'
        urls={
            target_url:json.dumps({'ref':'refs/heads/gh-pages',
                'object':{'type':'commit','sha':receipt_sha}}).encode(),
            list_url:json.dumps([{'sha':receipt_sha,
                'commit':{'message':occurrence.receipt['commit']['message']}}]).encode(),
            detail_url:json.dumps(occurrence.receipt).encode(),
        }
        for commit,bodies in ((receipt_sha,occurrence.committed_bodies),
                              (git.parent,occurrence.parent_bodies)):
            for name,raw in bodies.items():
                urls[f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/manager-support/{name}']=raw
        urls[PUBLIC_BASE+'manifest.json']=json.dumps(packet['candidate']).encode()
        urls.update({PUBLIC_BASE+name:raw for name,raw in occurrence.committed_bodies.items()
                     if name!='manifest.json'})
        return packet,journal,receipt_sha,observed_at,target_url,urls

    def provider_fixture(self, tmp):
        packet, git, journal, context = recovery.OwnedRecoveryTests().prepare(tmp)
        journal.reserve(packet, context, packet['baseline'], packet['candidate'], git.parent, NOW)
        sha = git.send(git.parent)
        evidence = git.evidence(sha)
        urls = {f'https://api.github.com/repos/{REPOSITORY}/commits/{sha}':
                json.dumps(evidence.receipt).encode()}
        for commit, bodies in [(sha, evidence.committed_bodies),
                               (git.parent, evidence.parent_bodies)]:
            for name, raw in bodies.items():
                urls[f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/manager-support/{name}'] = raw
        def get(url):
            self.assertIn(url, urls, 'collector may only use expected fixed URLs')
            return urls[url]
        return packet, git, journal, sha, urls, get

    def test_delivery_verifies_bytes_but_timeout_or_old_version_stays_unknown(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        for state in ('current', 'old', 'timeout'):
            with self.subTest(state=state), TemporaryDirectory() as tmp:
                packet, git, journal, sha, urls, get = self.provider_fixture(tmp)
                at = datetime.now(timezone.utc) + timedelta(seconds=1)
                reconcile_owned(journal, packet['effect_key'], lambda _: git.evidence(sha), at)
                evidence = git.evidence(sha)
                bodies = evidence.parent_bodies if state == 'old' else evidence.committed_bodies
                for name, raw in bodies.items(): urls[PUBLIC_BASE + name] = raw
                def read(url):
                    if state == 'timeout': raise TimeoutError('fixture HTTP timeout')
                    return get(url)
                result = collector.collect_owned_delivery(packet['effect_key'], journal, at, get=read)
                expected = {'current': 'VERIFIED', 'old': 'PENDING', 'timeout': 'UNKNOWN'}[state]
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['receipt_ref'], sha)
                self.assertEqual(result['proof_level'], 'P0')
                journal.save_delivery(packet['effect_key'], result)
                self.assertEqual(journal.delivery_record(packet['effect_key'])['status'], expected)
                wrong = dict(result, receipt_ref='f' * 40)
                with self.assertRaises(ValueError): journal.save_delivery(packet['effect_key'], wrong)

    def test_occurrence_pagination_collects_saved_packet_and_all_immutable_bytes(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        with TemporaryDirectory() as tmp:
            packet, git, journal, sha, urls, get = self.provider_fixture(tmp)
            list_url = f'https://api.github.com/repos/{REPOSITORY}/commits?sha=gh-pages&per_page=100&page='
            urls[list_url + '1'] = json.dumps([{'sha': 'f' * 40, 'commit': {'message': 'unrelated'}}] * 100).encode()
            urls[list_url + '2'] = json.dumps([json.loads(urls[f'https://api.github.com/repos/{REPOSITORY}/commits/{sha}'])]).encode()
            at = datetime.now(timezone.utc) + timedelta(seconds=1)
            result = collector.collect_owned_occurrence(packet['effect_key'], journal, at, get=get)
            self.assertIsNotNone(result)
            self.assertEqual(result.receipt['sha'], sha)
            self.assertEqual(result.parent_commit, git.parent)
            self.assertEqual(len(result.committed_bodies), 7)
            # Transport injection is a fixture, not authenticated public proof.
            self.assertNotEqual(journal.record(packet['effect_key']).status, 'PRESENT')

    def test_wrong_parent_or_partial_immutable_body_never_closes_occurrence(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        for bad in ('parent', 'body', 'message', 'repository'):
            with self.subTest(bad=bad), TemporaryDirectory() as tmp:
                packet, git, journal, sha, urls, get = self.provider_fixture(tmp)
                receipt_url = f'https://api.github.com/repos/{REPOSITORY}/commits/{sha}'
                receipt = json.loads(urls[receipt_url])
                if bad == 'parent': receipt['parents'][0]['sha'] = 'f' * 40
                if bad == 'message': receipt['commit']['message'] += ' sibling'
                if bad == 'repository': receipt['html_url'] = f'https://github.com/other/repo/commit/{sha}'
                urls[receipt_url] = json.dumps(receipt).encode()
                urls[f'https://api.github.com/repos/{REPOSITORY}/commits?sha=gh-pages&per_page=100&page=1'] = json.dumps([receipt]).encode()
                if bad == 'body':
                    url = f'https://raw.githubusercontent.com/{REPOSITORY}/{sha}/manager-support/finance.html'
                    urls[url] = urls[url][:10]
                self.assertIsNone(collector.collect_owned_occurrence(packet['effect_key'], journal,
                    datetime.now(timezone.utc) + timedelta(seconds=1), get=get))
                self.assertNotEqual(journal.record(packet['effect_key']).status, 'PRESENT')

    def test_delivery_lag_or_missing_file_does_not_rollback(self):
        for failure in ('lag', 'missing', 'hash_only'):
            with self.subTest(failure=failure), TemporaryDirectory() as tmp:
                conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
                real_send = host.send
                def delayed(*args):
                    sha = real_send(*args)
                    if failure == 'lag':
                        for path in host.context.baseline_bundle.iterdir():
                            (host.served / path.name).write_bytes(path.read_bytes())
                    elif failure == 'missing': (host.served / 'finance.html').unlink()
                    else:
                        path = host.served / 'finance.html'
                        path.write_bytes(path.read_bytes() + b'\n')
                    return sha
                with patch.object(host, 'send', side_effect=delayed) as send, \
                        patch.object(host, 'rollback', wraps=host.rollback) as rollback:
                    first = run_owned_cycle(conf, store, host=host, now=NOW)
                    self.assertEqual(first['status'], 'UNKNOWN')
                    self.assertEqual(first.get('rollback_writes'), 0)
                    rollback.assert_not_called()
                    self.assertFalse(store.stopped())
                    # Readback resumes before cadence; it must not republish.
                    host._publish_fixture(git.git('rev-parse', 'HEAD'))
                    run_owned_cycle(conf, store, host=host, now=NOW)
                    self.assertEqual(send.call_count, 1)
                    self.assertEqual(store.journal.delivery_record(first['effect_key'])['status'], 'VERIFIED')

    def test_confirmed_regression_rolls_back_once_with_exact_target(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
            host.regress_served = True
            with patch.object(host, 'rollback', wraps=host.rollback) as rollback:
                self.assertEqual(run_owned_cycle(conf, store, host=host, now=NOW)['status'],
                                 'ROLLED_BACK_SANDBOX_REGRESSION')
                self.assertEqual(run_owned_cycle(conf, store, host=host, now=NOW)['status'], 'STOPPED_REGRESSION')
                self.assertEqual(rollback.call_count, 1)

    def test_sibling_target_advance_does_not_authorize_rollback(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, git = fixtures.CycleAcceptanceTests().prepare(tmp)
            host.regress_served = True
            real_send = host.send
            def moved_target(*args):
                sha = real_send(*args)
                (host.checkout / 'unrelated.html').write_text('another owner advanced target')
                git.git('add', 'unrelated.html'); git.git('commit', '-qm', 'independent target advance')
                return sha
            with patch.object(host, 'send', side_effect=moved_target), \
                    patch.object(host, 'rollback', wraps=host.rollback) as rollback:
                result = run_owned_cycle(conf, store, host=host, now=NOW)
                self.assertEqual(result['status'], 'UNKNOWN')
                self.assertEqual(result.get('rollback_writes'), 0)
                rollback.assert_not_called()
                self.assertEqual(git.git('rev-list', '--count', 'HEAD'), '3')

    def test_v2_regression_requires_exact_commit_parent_deployment_target_and_rubric(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        from manager_core.outbox import OwnedEffectJournal
        from manager_core.digital_handoff import digest

        csp = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
        def page(current=False, csp_ok=True, suffix=''):
            policy = csp if csp_ok else "default-src *"
            current_attr = ' aria-current="page"' if current else ''
            return (f'<!doctype html><html><head><meta http-equiv="Content-Security-Policy" '
                    f'content="{policy}"></head><body><nav aria-label="主な案内">'
                    f'<a href="finance.html"{current_attr}>Finance</a>'
                    '<a href="mental.html">Mental</a></nav>'+suffix+'</body></html>').encode()

        baseline_pages = {name: page(False) for name in PAGES}
        candidate_pages = dict(baseline_pages)
        candidate_pages['finance.html'] = page(True)
        def manifest(pages, source):
            return {'schema':'manager.public-service.v1','source_commit':source,
                    'files':{name:sha256(raw).hexdigest() for name,raw in pages.items()},
                    'beneficiary_outcome':'NOT_MEASURED','real_participants':0,
                    'clinical_claim':False,'experiment_enabled':False}

        baseline = manifest(baseline_pages, 'a'*40)
        candidate = manifest(candidate_pages, 'b'*40)
        packet = plan_release(baseline, candidate, NOW, schema='manager.digital-handoff.v2')
        committed_at = NOW - timedelta(minutes=2)
        receipt = {'sha':'d'*40,
                   'commit':{'committer':{'date':committed_at.isoformat()},
                             'message':'exact saved candidate'},
                   'parents':[{'sha':'c'*40}]}
        evidence = OwnedOccurrenceEvidence(receipt,candidate,
            {'manager-support/'+name:raw for name,raw in candidate_pages.items()},
            'c'*40,baseline,{'manager-support/'+name:raw for name,raw in baseline_pages.items()})

        for state, expected in (('exact','VERIFIED'),('no_deployment','UNKNOWN'),
                                ('wrong_deployment_sha','UNKNOWN'),('old_deployment','UNKNOWN'),
                                ('wrong_target','UNKNOWN'),('cue_failure','REGRESSION'),
                                ('csp_failure','REGRESSION'),('hash_only','UNKNOWN'),
                                ('wrong_receipt','UNKNOWN')):
            with self.subTest(state=state), TemporaryDirectory() as tmp:
                journal = OwnedEffectJournal(Path(tmp)/'cycle.sqlite')
                publisher = PublisherContext(REPOSITORY, MAIN_REF, WORKFLOW, 'b'*40,
                                             '123', workflow_commit='b'*40)
                journal.reserve(packet,publisher,baseline,candidate,'c'*40,NOW)
                journal._present(packet['effect_key'],'d'*40)
                served = dict(candidate_pages)
                if state == 'cue_failure': served['finance.html'] = page(False)
                elif state == 'csp_failure': served['finance.html'] = page(True,csp_ok=False)
                elif state == 'hash_only': served['finance.html'] = page(True,suffix='changed')
                current_sha = 'c'*40 if state == 'wrong_target' else 'd'*40
                run_sha = 'c'*40 if state == 'wrong_deployment_sha' else 'd'*40
                run_time = committed_at - timedelta(minutes=1) if state == 'old_deployment' else NOW
                urls = {
                    f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/gh-pages':
                    json.dumps({'ref':'refs/heads/gh-pages','object':{'type':'commit','sha':current_sha}}).encode(),
                    f'https://api.github.com/repos/{REPOSITORY}/actions/workflows/307239134/runs?branch=gh-pages&per_page=100':
                    json.dumps({'workflow_runs':([] if state == 'no_deployment' else [{
                        'workflow_id':307239134,'path':'.github/workflows/pages.yml',
                        'event':'workflow_dispatch','head_branch':'gh-pages',
                        'head_repository':{'full_name':REPOSITORY},'head_sha':run_sha,
                        'status':'completed','conclusion':'success','created_at':run_time.isoformat()}])}).encode(),
                    PUBLIC_BASE+'manifest.json':json.dumps(candidate).encode(),
                }
                urls.update({PUBLIC_BASE+name:raw for name,raw in served.items()})
                def get(url):
                    self.assertIn(url,urls,'collector used an unexpected public endpoint')
                    return urls[url]
                exact_evidence = evidence
                if state == 'wrong_receipt':
                    exact_evidence = OwnedOccurrenceEvidence(
                        dict(receipt,sha='e'*40),candidate,evidence.committed_bodies,
                        'c'*40,baseline,evidence.parent_bodies)
                with patch.object(collector,'collect_owned_occurrence',return_value=exact_evidence):
                    result = collector.collect_owned_delivery(packet['effect_key'],journal,NOW,get=get)
                self.assertEqual(result['status'],expected)
                if expected == 'REGRESSION':
                    self.assertEqual(result['proof_level'],'P2')
                if expected != 'REGRESSION':
                    self.assertNotIn(result['status'],('REGRESSION',))

    def test_current_target_resamples_candidate_even_when_historical_delivery_is_verified(self):
        collector=importlib.import_module('manager_core.owned_public_collector')
        from manager_core.outbox import OwnedEffectJournal
        from manager_core.digital_handoff import MAIN_REF,WORKFLOW,PublisherContext,plan_release

        baseline=manifest('a'*40,'old')
        candidate=manifest('b'*40,'candidate')
        packet=plan_release(baseline,candidate,NOW,schema='manager.digital-handoff.v2')
        with TemporaryDirectory() as tmp:
            journal=OwnedEffectJournal(Path(tmp)/'cycle.sqlite')
            publisher=PublisherContext(REPOSITORY,MAIN_REF,WORKFLOW,'b'*40,'123',workflow_commit='b'*40)
            journal.reserve(packet,publisher,baseline,candidate,'c'*40,NOW)
            journal._present(packet['effect_key'],'d'*40)
            journal.save_delivery(packet['effect_key'],{
                'status':'VERIFIED','effect_key':packet['effect_key'],'receipt_ref':'d'*40,
                'candidate_sha256':packet['candidate_sha256'],'observed_at':NOW.isoformat(),
                'proof_ref':PUBLIC_BASE,'proof_level':'P2','reason':'EXACT_DEPLOYED_CANDIDATE',
                'human_outcome':'NOT_MEASURED'})
            target_url=f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/gh-pages'
            calls=[]
            def get(url):
                calls.append(url)
                if url==target_url:
                    return json.dumps({'ref':'refs/heads/gh-pages',
                        'object':{'type':'commit','sha':'d'*40}}).encode()
                raise AssertionError(f'unexpected current-target request: {url}')
            regression={'status':'REGRESSION','effect_key':packet['effect_key'],
                'receipt_ref':'d'*40,'candidate_sha256':packet['candidate_sha256'],
                'observed_at':NOW.isoformat(),'proof_ref':PUBLIC_BASE,'proof_level':'P2',
                'reason':'BOUND_CURRENT_PAGE_CUE_FAILURE','human_outcome':'NOT_MEASURED'}
            with patch.object(collector,'collect_owned_delivery',return_value=regression) as observe:
                result=collector.collect_current_owned_delivery(
                    journal,NOW,get=get)
            self.assertEqual(result['kind'],'candidate')
            self.assertEqual(result['evidence'],regression)
            self.assertEqual(calls,[target_url])
            observe.assert_called_once_with(packet['effect_key'],journal,NOW,get=get)

    def test_current_target_rollback_receipt_selects_rollback_p2_collector(self):
        collector=importlib.import_module('manager_core.owned_public_collector')
        from manager_core.outbox import OwnedEffectJournal,plan_owned_rollback
        from manager_core.digital_handoff import MAIN_REF,WORKFLOW,PublisherContext,plan_release

        baseline=manifest('a'*40,'old')
        candidate=manifest('b'*40,'candidate')
        original=plan_release(baseline,candidate,NOW,schema='manager.digital-handoff.v2')
        with TemporaryDirectory() as tmp:
            journal=OwnedEffectJournal(Path(tmp)/'cycle.sqlite')
            publisher=PublisherContext(REPOSITORY,MAIN_REF,WORKFLOW,'b'*40,'123',workflow_commit='b'*40)
            journal.reserve(original,publisher,baseline,candidate,'c'*40,NOW)
            journal._present(original['effect_key'],'d'*40)
            rollback=plan_owned_rollback(original,'d'*40,'c'*40,NOW,controller_sha='b'*40)
            journal.reserve_rollback(rollback,NOW)
            journal._rollback_present(rollback['effect_key'],'e'*40)
            target_url=f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/gh-pages'
            def get(url):
                self.assertEqual(url,target_url)
                return json.dumps({'ref':'refs/heads/gh-pages',
                    'object':{'type':'commit','sha':'e'*40}}).encode()
            expected={'status':'VERIFIED','effect_key':rollback['effect_key'],
                'receipt_ref':'e'*40,'baseline_sha256':rollback['baseline_sha256'],
                'observed_at':NOW.isoformat(),'proof_ref':PUBLIC_BASE,'proof_level':'P2',
                'reason':'EXACT_DEPLOYED_PARENT_BASELINE','human_outcome':'NOT_MEASURED'}
            with patch.object(collector,'collect_owned_rollback_delivery',return_value=expected) as observe:
                result=collector.collect_current_owned_delivery(journal,NOW,get=get)
            self.assertEqual(result['kind'],'rollback')
            self.assertEqual(result['evidence'],expected)
            observe.assert_called_once_with(rollback['effect_key'],journal,NOW,get=get)

    def test_current_v1_receipt_gets_fresh_provider_parent_and_served_p2(self):
        collector=importlib.import_module('manager_core.owned_public_collector')
        from scripts import phase06_kernel_release as release

        with TemporaryDirectory() as tmp:
            packet,journal,receipt_sha,observed_at,target_url,urls=self.prepare_v1_current_fixture(tmp)
            def get(url):
                self.assertIn(url,urls,'v1 current collector used an unexpected public endpoint')
                return urls[url]
            with patch.object(release,'public_get',side_effect=get):
                current=collector.collect_current_owned_delivery(journal,observed_at)
            self.assertEqual(current['kind'],'candidate')
            self.assertEqual(current['effect_key'],packet['effect_key'])
            self.assertEqual(current['receipt_ref'],receipt_sha)
            self.assertEqual(current['evidence']['status'],'VERIFIED')
            self.assertEqual(current['evidence']['proof_level'],'P2')
            self.assertEqual(current['evidence']['reason'],'EXACT_CURRENT_V1_SERVED_BUNDLE')
            self.assertEqual(journal.delivery_record(packet['effect_key'])['status'],'VERIFIED')
            saved=journal.record(packet['effect_key'])
            self.assertFalse(saved.dispatch)
            self.assertEqual(json.loads(saved.packet_json),packet)
            from manager_core.outbox import plan_owned_rollback
            with self.assertRaises(ValueError):
                plan_owned_rollback(packet,receipt_sha,saved.expected_parent,observed_at,
                                    controller_sha='b'*40)

    def test_current_v1_source_target_or_served_body_mismatch_stays_unknown(self):
        collector=importlib.import_module('manager_core.owned_public_collector')
        from scripts import phase06_kernel_release as release

        for failure in ('source','sha','body','move'):
            with self.subTest(failure=failure),TemporaryDirectory() as tmp:
                packet,journal,receipt_sha,observed_at,target_url,urls=self.prepare_v1_current_fixture(tmp)
                if failure=='source':
                    key=f'https://raw.githubusercontent.com/{REPOSITORY}/{receipt_sha}/manager-support/manifest.json'
                    changed=json.loads(urls[key]);changed['source_commit']='e'*40
                    urls[key]=json.dumps(changed).encode()
                elif failure=='sha':
                    target=json.loads(urls[target_url]);target['object']['sha']='e'*40
                    urls[target_url]=json.dumps(target).encode()
                elif failure=='body':
                    urls[PUBLIC_BASE+'finance.html']+=b'\n'
                target_reads=0
                def get(url):
                    nonlocal target_reads
                    self.assertIn(url,urls,'v1 current collector used an unexpected public endpoint')
                    if failure=='move' and url==target_url:
                        target_reads+=1
                        if target_reads>1:
                            return json.dumps({'ref':'refs/heads/gh-pages',
                                'object':{'type':'commit','sha':'e'*40}}).encode()
                    return urls[url]
                with patch.object(release,'public_get',side_effect=get):
                    current=collector.collect_current_owned_delivery(journal,observed_at)
                self.assertIn(current['kind'],('candidate','unmatched'))
                self.assertEqual(current['evidence']['status'],'UNKNOWN')
                self.assertEqual(journal.delivery_record(packet['effect_key'])['status'],'VERIFIED')
