"""Trusted provider readback to native technical observations and safe view."""
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_owned_public_collector as collector_fixtures
from manager_core.learning import NativeTechnicalObservation, PolicyLearner
from manager_core.digital_handoff import SOURCE_REF, REPOSITORY, WORKFLOW, PUBLIC_BASE, PublisherContext, plan_release
from manager_core.digital_environment import PAGES
from manager_core.reconcile import OwnedOccurrenceEvidence
from manager_core.owned_cycle import CycleStore
from scripts import phase06_kernel_release
from scripts import run_owned_digital_cycle as cycle_cli
from test_digital_handoff import manifest


class NativeObservationBridgeTests(unittest.TestCase):
    def test_trusted_current_seed_readback_appends_replay_stable_p1_and_p2(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        with TemporaryDirectory() as tmp:
            packet, journal, receipt, observed_at, target_url, urls = (
                collector_fixtures.PublicCollectorTests().prepare_v1_current_fixture(tmp))

            def get(url):
                self.assertIn(url, urls, 'trusted default read used an unexpected public URL')
                return urls[url]

            learner = PolicyLearner(journal.path)
            with patch.object(phase06_kernel_release, 'public_get', side_effect=get):
                first = collector.collect_current_owned_delivery(journal, observed_at)
                second = collector.collect_current_owned_delivery(journal, observed_at)
                later = collector.collect_current_owned_delivery(
                    journal, observed_at + timedelta(seconds=1))

            self.assertEqual(first['evidence']['status'], 'VERIFIED')
            self.assertEqual(first['evidence']['proof_level'], 'P2')
            self.assertEqual(second['evidence']['reason'], 'EXACT_CURRENT_V1_SERVED_BUNDLE')
            rows = learner.native_technical_observations(effect_key=packet['effect_key'])
            self.assertEqual(later['evidence']['status'], 'VERIFIED')
            self.assertEqual(len(rows), 3, 'retries dedupe while a later distinct snapshot stays historical')
            p1, = [row for row in rows if row.proof_level == 'P1']
            p2_rows = [row for row in rows if row.proof_level == 'P2']
            self.assertEqual((p1.measure_id, p1.unit, p1.status),
                             ('owned.pages.commit_occurrence', 'commit_occurrence', 'VERIFIED'))
            self.assertEqual(p1.receipt_ref, receipt)
            self.assertEqual(p1.observed_at.isoformat(),
                             urls[f'https://api.github.com/repos/{collector_fixtures.REPOSITORY}/commits/{receipt}']
                             and datetime.fromisoformat(json.loads(urls[
                                 f'https://api.github.com/repos/{collector_fixtures.REPOSITORY}/commits/{receipt}'])
                                 ['commit']['committer']['date'].replace('Z', '+00:00')).isoformat())
            self.assertEqual(len(p2_rows), 2)
            for p2 in p2_rows:
                self.assertEqual((p2.measure_id, p2.unit, p2.status, p2.proof_level),
                                 ('owned.pages.served_bundle_bytes', 'byte', 'VERIFIED', 'P2'))
                self.assertIs(type(p2.native_value), int)
                self.assertGreater(p2.native_value, 0)
                self.assertEqual(p2.human_outcome, 'NOT_MEASURED')
                self.assertEqual(p2.native_value,sum(
                    len(raw) for url,raw in urls.items()
                    if url.startswith(collector_fixtures.PUBLIC_BASE) and
                    url!=collector_fixtures.PUBLIC_BASE+'manifest.json'))

    def test_current_missing_does_not_overwrite_a_historical_verified_native_snapshot(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        with TemporaryDirectory() as tmp:
            packet, journal, receipt, observed_at, target_url, urls = (
                collector_fixtures.PublicCollectorTests().prepare_v1_current_fixture(tmp))
            old_at=observed_at-timedelta(seconds=1)
            learner=PolicyLearner(journal.path)
            learner.record_native_technical_observation(NativeTechnicalObservation(
                packet['effect_key'],packet['candidate_sha256'],receipt,old_at,
                'owned.pages.served_bundle_bytes','byte','VERIFIED','P2',456,None,
                'NOT_MEASURED',(f'https://github.com/{collector_fixtures.REPOSITORY}/commit/{receipt}',
                                collector_fixtures.PUBLIC_BASE)))
            urls[collector_fixtures.PUBLIC_BASE+'finance.html'] += b' changed after the old proof'

            def get(url):
                self.assertIn(url,urls)
                return urls[url]

            with patch.object(phase06_kernel_release,'public_get',side_effect=get):
                current=collector.collect_current_owned_delivery(journal,observed_at)
            self.assertNotEqual(current['evidence']['status'],'VERIFIED')
            rows=learner.native_technical_observations(effect_key=packet['effect_key'])
            p2=[row for row in rows if row.proof_level=='P2']
            self.assertEqual(len(p2),2)
            historical=[row for row in p2 if row.observed_at==old_at]
            missing=[row for row in p2 if row.observed_at==observed_at]
            self.assertEqual(len(historical),1)
            self.assertEqual((historical[0].native_value,historical[0].status),
                             (456,'VERIFIED'))
            self.assertEqual(len(missing),1)
            self.assertEqual((missing[0].native_value,missing[0].status),
                             (None,'UNKNOWN'))
            self.assertEqual(missing[0].missing_reason,'DELIVERY_UNCONFIRMED')

    def test_v2_current_delivery_persists_p2_only_after_receipt_deployment_and_bytes_match(self):
        collector=importlib.import_module('manager_core.owned_public_collector')
        from manager_core.outbox import OwnedEffectJournal
        from manager_core.digital_handoff import MAIN_REF
        csp="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"

        def page(current=False):
            selected=' aria-current="page"' if current else ''
            return (f'<!doctype html><html><head><meta http-equiv="Content-Security-Policy" '
                    f'content="{csp}"></head><body><nav aria-label="主な案内">'
                    f'<a href="finance.html"{selected}>Finance</a>'
                    '<a href="mental.html">Mental</a></nav></body></html>').encode()

        old_pages={name:page() for name in PAGES}
        new_pages=dict(old_pages);new_pages['finance.html']=page(True)

        def make_manifest(pages,source):
            from hashlib import sha256
            return {'schema':'manager.public-service.v1','source_commit':source,
                    'files':{name:sha256(raw).hexdigest() for name,raw in pages.items()},
                    'beneficiary_outcome':'NOT_MEASURED','real_participants':0,
                    'clinical_claim':False,'experiment_enabled':False}

        baseline=make_manifest(old_pages,'a'*40)
        candidate=make_manifest(new_pages,'b'*40)
        at=datetime.now(timezone.utc)
        packet=plan_release(baseline,candidate,at,schema='manager.digital-handoff.v2')
        receipt='d'*40;parent='c'*40
        committed_at=at-timedelta(minutes=1)
        receipt_data={'sha':receipt,
            'html_url':f'https://github.com/{REPOSITORY}/commit/{receipt}',
            'commit':{'committer':{'date':committed_at.isoformat()}},
            'parents':[{'sha':parent}]}
        occurrence=OwnedOccurrenceEvidence(receipt_data,candidate,
            {'manager-support/'+name:raw for name,raw in new_pages.items()},
            parent,baseline,{'manager-support/'+name:raw for name,raw in old_pages.items()})
        target_url=f'https://api.github.com/repos/{REPOSITORY}/git/ref/heads/gh-pages'
        runs_url=(f'https://api.github.com/repos/{REPOSITORY}/actions/workflows/307239134/runs'
                  '?branch=gh-pages&per_page=100')
        urls={target_url:json.dumps({'ref':'refs/heads/gh-pages',
                    'object':{'type':'commit','sha':receipt}}).encode(),
              runs_url:json.dumps({'workflow_runs':[{
                    'workflow_id':307239134,'path':'.github/workflows/pages.yml',
                    'event':'workflow_dispatch','head_branch':'gh-pages',
                    'head_repository':{'full_name':REPOSITORY},'head_sha':receipt,
                    'status':'completed','conclusion':'success',
                    'created_at':at.isoformat()}]}).encode(),
              PUBLIC_BASE+'manifest.json':json.dumps(candidate).encode()}
        urls.update({PUBLIC_BASE+name:raw for name,raw in new_pages.items()})
        with TemporaryDirectory() as tmp:
            journal=OwnedEffectJournal(Path(tmp)/'cycle.sqlite')
            publisher=PublisherContext(REPOSITORY,MAIN_REF,WORKFLOW,'b'*40,'123',
                                      workflow_commit='b'*40)
            journal.reserve(packet,publisher,baseline,candidate,parent,at)
            journal._present(packet['effect_key'],receipt)
            learner=PolicyLearner(journal.path)
            learner.record_native_technical_observation(NativeTechnicalObservation(
                packet['effect_key'],packet['candidate_sha256'],receipt,committed_at,
                'owned.pages.commit_occurrence','commit_occurrence','VERIFIED','P1',1,None,
                'NOT_MEASURED',(receipt_data['html_url'],)))
            def get(url):
                self.assertIn(url,urls)
                return urls[url]
            with patch.object(collector,'collect_owned_occurrence',return_value=occurrence), \
                 patch.object(phase06_kernel_release,'public_get',side_effect=get):
                result=collector.collect_owned_delivery(packet['effect_key'],journal,at)
            self.assertEqual((result['status'],result['proof_level']),('VERIFIED','P2'))
            observations=learner.native_technical_observations()
            self.assertEqual(len(observations),2)
            observation,= [row for row in observations if row.proof_level=='P2']
            self.assertEqual((observation.effect_key,observation.candidate_sha256,
                              observation.receipt_ref,observation.measure_id,
                              observation.proof_level,observation.status),
                             (packet['effect_key'],packet['candidate_sha256'],receipt,
                              'owned.pages.served_bundle_bytes','P2','VERIFIED'))

            urls[PUBLIC_BASE+'finance.html'] += b' served bytes no longer match manifest'
            missing_at=at+timedelta(seconds=1)
            with patch.object(collector,'collect_owned_occurrence',return_value=occurrence), \
                 patch.object(phase06_kernel_release,'public_get',side_effect=get):
                missing=collector.collect_owned_delivery(packet['effect_key'],journal,missing_at)
            self.assertEqual((missing['status'],missing['reason']),('UNKNOWN','HASH_MISMATCH_ONLY'))
            observations=learner.native_technical_observations()
            missing_row,= [row for row in observations
                           if row.proof_level=='P2' and row.observed_at==missing_at]
            self.assertIsNone(missing_row.native_value)
            self.assertEqual(missing_row.status,'UNKNOWN')
            self.assertEqual(missing_row.missing_reason,'HASH_MISMATCH_ONLY')
            summary=cycle_cli.public_summary({
                'status':'UNKNOWN','proof_level':'P2','deployed':True,
                'effect_key':packet['effect_key'],'receipt_ref':receipt},
                store=CycleStore(tmp))
            self.assertEqual(summary['positive_canary'],'NOT_RUN')

    def test_injected_provider_fixture_never_enters_native_p1_or_p2_store(self):
        collector = importlib.import_module('manager_core.owned_public_collector')
        with TemporaryDirectory() as tmp:
            packet, journal, receipt, observed_at, target_url, urls = (
                collector_fixtures.PublicCollectorTests().prepare_v1_current_fixture(tmp))

            def fixture_get(url):
                self.assertIn(url, urls)
                return urls[url]

            result = collector.collect_current_owned_delivery(journal, observed_at, get=fixture_get)
            self.assertEqual(result['evidence']['proof_level'], 'P0')
            self.assertEqual(PolicyLearner(journal.path).native_technical_observations(), [])

    def test_invalid_saved_receipt_creates_no_native_observation_identity(self):
        collector=importlib.import_module('manager_core.owned_public_collector')
        with TemporaryDirectory() as tmp:
            packet,journal,receipt,observed_at,target_url,urls=(
                collector_fixtures.PublicCollectorTests().prepare_v1_current_fixture(tmp))
            detail_url=f'https://api.github.com/repos/{REPOSITORY}/commits/{receipt}'
            broken=json.loads(urls[detail_url]);broken['html_url']='https://example.invalid/other'
            urls[detail_url]=json.dumps(broken).encode()
            def get(url):
                self.assertIn(url,urls)
                return urls[url]
            with patch.object(phase06_kernel_release,'public_get',side_effect=get):
                current=collector.collect_current_owned_delivery(journal,observed_at)
            self.assertNotEqual(current['evidence'].get('proof_level'),'P2')
            self.assertEqual(PolicyLearner(journal.path).native_technical_observations(),[])

    def test_explorer_projection_reads_bound_store_and_omits_private_fields(self):
        with TemporaryDirectory() as tmp:
            learner = PolicyLearner(Path(tmp) / 'cycle.sqlite')
            now = datetime(2026, 10, 23, tzinfo=timezone.utc)
            effect = 'a' * 64
            candidate = 'b' * 64
            receipt = 'c' * 40
            learner.record_native_technical_observation(NativeTechnicalObservation(
                effect, candidate, receipt, now, 'owned.pages.served_bundle_bytes', 'byte',
                'VERIFIED', 'P2', 123, None, 'NOT_MEASURED',
                (f'https://github.com/Daisuke134/life-manager/commit/{receipt}',
                 'https://daisuke134.github.io/life-manager/manager-support/')))
            learner.record_native_technical_observation(NativeTechnicalObservation(
                effect, candidate, receipt, now, 'owned.pages.commit_occurrence',
                'commit_occurrence', 'VERIFIED', 'P1', 1, None, 'NOT_MEASURED',
                (f'https://github.com/Daisuke134/life-manager/commit/{receipt}',)))
            report = {
                'status': 'VERIFIED_PUBLIC_ARTIFACT_ONLY',
                'technical_proof': 'exact_public_artifact_bytes', 'human_outcome': 'NOT_MEASURED',
                'effect_key': effect, 'source_commit': 'd' * 40, 'pages_commit': receipt,
                'parent_pages_commit': 'e' * 40, 'committed_at': now.isoformat(),
                'observed_at': now.isoformat(), 'observation_decision': 'RELEASE',
                'reconciled_existing_occurrence': False, 'changed_pages': ['finance.html'],
                'receipt_url': f'https://github.com/Daisuke134/life-manager/commit/{receipt}',
                'candidate_sha256': candidate, 'candidate': {'private_snapshot': 'secret'},
                'served_bundle_bytes': 123,
            }
            html = phase06_kernel_release.render_explorer(report, learner=learner)
            self.assertIn('served_bundle_bytes', html)
            self.assertIn('commit_occurrence', html)
            self.assertIn('123 byte', html)
            self.assertNotIn(effect, html)
            self.assertNotIn(candidate, html)
            self.assertNotIn('private_snapshot', html)
            self.assertNotIn('provenance_refs', html)

    def test_explorer_projection_rejects_unbound_native_observations(self):
        with TemporaryDirectory() as tmp:
            learner = PolicyLearner(Path(tmp) / 'cycle.sqlite')
            now = datetime(2026, 10, 23, tzinfo=timezone.utc)
            learner.record_native_technical_observation(NativeTechnicalObservation(
                'a' * 64, 'b' * 64, 'c' * 40, now, 'owned.pages.served_bundle_bytes',
                'byte', 'VERIFIED', 'P2', 123, None, 'NOT_MEASURED',
                ('https://example.test/receipt',)))
            report = {
                'status': 'VERIFIED_PUBLIC_ARTIFACT_ONLY',
                'technical_proof': 'exact_public_artifact_bytes', 'human_outcome': 'NOT_MEASURED',
                'effect_key': 'f' * 64, 'source_commit': 'd' * 40, 'pages_commit': 'e' * 40,
                'parent_pages_commit': 'g' * 40, 'committed_at': now.isoformat(),
                'observed_at': now.isoformat(), 'observation_decision': 'RELEASE',
                'reconciled_existing_occurrence': False, 'changed_pages': ['finance.html'],
                'receipt_url': 'https://example.test/receipt', 'candidate_sha256': 'h' * 64,
                'candidate': {'private_snapshot': 'secret'},
            }
            html = phase06_kernel_release.render_explorer(report, learner=learner)
            self.assertNotIn('served_bundle_bytes', html)
            self.assertNotIn('123 byte', html)

    def test_cli_canary_requires_saved_exact_native_p2_and_never_closes_e16(self):
        with TemporaryDirectory() as tmp:
            store = CycleStore(tmp)
            baseline=manifest('a'*40,'old')
            candidate=manifest('b'*40,'candidate')
            packet=plan_release(baseline,candidate,datetime.now(timezone.utc))
            receipt='c'*40
            publisher=PublisherContext(REPOSITORY,SOURCE_REF,WORKFLOW,'b'*40,'123')
            store.journal.reserve(packet,publisher,baseline,candidate,'d'*40,datetime.now(timezone.utc))
            store.journal._present(packet['effect_key'],receipt)
            now=datetime.now(timezone.utc)
            store.learning.record_native_technical_observation(NativeTechnicalObservation(
                packet['effect_key'],packet['candidate_sha256'],receipt,now,
                'owned.pages.served_bundle_bytes','byte','VERIFIED','P2',123,None,
                'NOT_MEASURED',(f'https://github.com/{REPOSITORY}/commit/{receipt}',PUBLIC_BASE)))
            report={'status':'VERIFIED_PUBLIC_ARTIFACT_ONLY','proof_level':'P2','deployed':True,
                    'effect_key':packet['effect_key'],'receipt_ref':receipt,'writes':1}
            summary=cycle_cli.public_summary(report,store=store)
            self.assertEqual(summary['positive_canary'],'P2_ARTIFACT_VERIFIED')
            self.assertEqual(summary['E16_ACCEPTANCE'],'INCOMPLETE')
            self.assertEqual(summary['human_outcome'],'NOT_MEASURED')
            self.assertEqual(cycle_cli.public_summary({**report,'status':'NO_ACTION','writes':0},
                                                       store=store)['positive_canary'],'NOT_RUN')
            self.assertEqual(cycle_cli.public_summary({**report,'receipt_ref':'e'*40},
                                                       store=store)['positive_canary'],'NOT_RUN')


if __name__ == '__main__':
    unittest.main()
