"""A public release is a separate platform capability, never a fixture grant."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def manifest(commit, content):
    from manager_core.digital_environment import PAGES
    return {'schema': 'manager.public-service.v1', 'source_commit': commit,
            'files': {n: sha256((n + content).encode()).hexdigest() for n in PAGES},
            'beneficiary_outcome': 'NOT_MEASURED', 'real_participants': 0,
            'clinical_claim': False, 'experiment_enabled': False}


class DigitalHandoffTests(unittest.TestCase):
    def api(self):
        from manager_core import digital_handoff
        return digital_handoff

    def packet(self):
        m = self.api()
        return m.plan_release(manifest('a'*40, 'old'), manifest('b'*40, 'new'), NOW)

    def context(self):
        m = self.api()
        return m.PublisherContext(m.REPOSITORY, m.SOURCE_REF, m.WORKFLOW,
                                  'b'*40, '12345')

    def test_effect_identity_survives_new_run_and_new_observation_time(self):
        m = self.api()
        a = self.packet()
        b = m.plan_release(manifest('a'*40,'old'), manifest('b'*40,'new'), NOW+timedelta(minutes=1))
        self.assertEqual(a['effect_key'], b['effect_key'])
        self.assertEqual(a['decision'], 'PROPOSE_TECHNICAL_RELEASE')
        self.assertEqual(a['human_outcome'], 'NOT_MEASURED')
        self.assertEqual(a['external_authority'], 'REQUIRED_PLATFORM_CONTEXT')

    def test_unchanged_candidate_is_no_action_and_no_welfare_claim(self):
        m = self.api(); same = manifest('b'*40,'new')
        p = m.plan_release(same, same, NOW)
        self.assertEqual(p['decision'], 'NO_ACTION')
        self.assertEqual(p['changed_pages'], [])
        self.assertFalse(p['causal_effect_verified'])

    def test_missing_or_unobserved_baseline_never_proposes_release(self):
        m = self.api()
        with self.assertRaises(ValueError):
            m.plan_release(None, manifest('b'*40,'new'), NOW)

    def test_admission_is_bound_to_authenticated_platform_and_exact_bundle(self):
        m = self.api(); p = self.packet()
        result = m.admit_release(p, self.context(), manifest('a'*40,'old'),
                                 manifest('b'*40,'new'), NOW)
        self.assertEqual(result['effect_key'], p['effect_key'])
        self.assertEqual(result['status'], 'ADMITTED_MANAGER_PREFIX_ONLY')
        for changes in ({'repository':'attacker/repo'}, {'ref':'refs/heads/main'},
                        {'workflow':'.github/workflows/other.yml'}, {'source_commit':'c'*40}):
            c = self.context().__dict__ | changes
            with self.subTest(changes=changes), self.assertRaises(PermissionError):
                m.admit_release(p, m.PublisherContext(**c), manifest('a'*40,'old'),
                                manifest('b'*40,'new'), NOW)

    def test_main_source_uses_versioned_admission_and_exact_workflow_ref(self):
        m = self.api()
        p = m.plan_release(manifest('a'*40, 'old'), manifest('b'*40, 'new'), NOW,
                           source_ref=m.MAIN_SOURCE_REF)
        self.assertEqual(p['schema'], 'manager.digital-handoff.v2')
        self.assertEqual(p['ref'], m.MAIN_SOURCE_REF)
        context = m.PublisherContext(m.REPOSITORY, m.MAIN_SOURCE_REF, m.WORKFLOW,
                                     'b'*40, '12345')
        accepted = m.admit_release(p, context, manifest('a'*40, 'old'),
                                   manifest('b'*40, 'new'), NOW)
        self.assertEqual(accepted['status'], 'ADMITTED_MANAGER_PREFIX_ONLY')
        with self.assertRaises(PermissionError):
            m.admit_release(p, self.context(), manifest('a'*40, 'old'),
                            manifest('b'*40, 'new'), NOW)
        with self.assertRaises(ValueError):
            m.plan_release(manifest('a'*40, 'old'), manifest('b'*40, 'new'), NOW,
                           source_ref='refs/heads/research/unreviewed')

    def test_tampered_expired_revoked_and_widened_intents_are_denied(self):
        m = self.api()
        mutations = [lambda p:p['candidate']['files'].__setitem__('index.html','f'*64),
                     lambda p:p['allowed_paths'].append('index.html'),
                     lambda p:p.__setitem__('human_outcome','IMPROVED'),
                     lambda p:p.__setitem__('expires_at',(NOW+timedelta(days=99)).isoformat()),
                     lambda p:p.__setitem__('money_budget',100),
                     lambda p:p.__setitem__('new_unknown_field',True)]
        for mutate in mutations:
            p = deepcopy(self.packet()); mutate(p)
            with self.subTest(mutate=mutate), self.assertRaises((ValueError, PermissionError)):
                m.admit_release(p,self.context(),manifest('a'*40,'old'),manifest('b'*40,'new'),NOW)
        with self.assertRaises(PermissionError):
            m.admit_release(self.packet(),self.context(),manifest('a'*40,'old'),manifest('b'*40,'new'),NOW+timedelta(days=2))
        with self.assertRaises(PermissionError):
            m.admit_release(self.packet(),self.context(),manifest('a'*40,'old'),manifest('b'*40,'new'),NOW,revoked=True)

    def test_changed_baseline_denied_but_same_applied_candidate_is_replay(self):
        m = self.api(); p = self.packet()
        with self.assertRaises(PermissionError):
            m.admit_release(p,self.context(),manifest('c'*40,'other'),manifest('b'*40,'new'),NOW)
        result = m.admit_release(p,self.context(),manifest('b'*40,'new'),manifest('b'*40,'new'),NOW)
        self.assertEqual(result['status'],'NO_ACTION_ALREADY_PRESENT')
        self.assertFalse(result['dispatch_deployment'])

    def test_receipt_validation_requires_exact_commit_occurrence_and_changed_paths(self):
        m = self.api(); p = self.packet()
        def bodies(value, content):
            return {**{n:(n+content).encode() for n in value['files']},
                    'manifest.json':json.dumps(value).encode()}
        bundles={'committed_bodies':bodies(p['candidate'],'new'),
                 'parent_commit':'a'*40,'parent_manifest':p['baseline'],
                 'parent_bodies':bodies(p['baseline'],'old')}
        receipt = {'sha':'d'*40,'html_url':f'https://github.com/{m.REPOSITORY}/commit/'+ 'd'*40,
                   'commit':{'message':m.commit_message(p),'committer':{'date':NOW.isoformat()}},
                   'parents':[{'sha':'a'*40}],
                   'files':[{'filename':'manager-support/'+n,'status':'modified'} for n in bundles['committed_bodies']]}
        valid = m.validate_commit_receipt(p, receipt, p['candidate'], NOW+timedelta(minutes=1), **bundles)
        self.assertEqual(valid['status'],'MATCHED_PUBLIC_COMMIT_DATA')
        self.assertEqual(valid['human_outcome'],'NOT_MEASURED')
        for mutate in (lambda r:r['commit'].__setitem__('message','unrelated occurrence'),
                       lambda r:r['files'].append({'filename':'index.html','status':'modified'}),
                       lambda r:r.__setitem__('html_url','https://attacker.test/fake'),
                       lambda r:r['commit']['committer'].__setitem__('date',(NOW+timedelta(days=5)).isoformat())):
            bad=deepcopy(receipt); mutate(bad)
            with self.subTest(mutate=mutate),self.assertRaises((ValueError,PermissionError)):
                m.validate_commit_receipt(p,bad,p['candidate'],NOW+timedelta(minutes=1), **bundles)

    def test_kernel_records_intent_without_touching_fixture_authority_or_executor(self):
        from manager_core.kernel import ManagerKernel
        from manager_core.audit import AuditTrail
        from manager_core.authority import AuthorityVerifier
        from manager_core.outbox import DurableOutbox
        from manager_core.config import DEFAULTS
        with TemporaryDirectory() as t:
            k=ManagerKernel(DurableOutbox(Path(t)/'outbox.sqlite'),
                            AuthorityVerifier({'fixture':b'x'*32}),AuditTrail(Path(t)/'audit.sqlite'))
            p=k.prepare_digital_release('run1',manifest('a'*40,'old'),manifest('b'*40,'new'),NOW)
            self.assertEqual(p['decision'],'PROPOSE_TECHNICAL_RELEASE')
            self.assertTrue(k.audit.verify_chain('run1'))
            self.assertIsNone(k.outbox.record(p['effect_key']))
            self.assertFalse(DEFAULTS.live_external_writes)
            self.assertFalse(DEFAULTS.public_posting)


if __name__ == '__main__': unittest.main()
