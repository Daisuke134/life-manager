"""Main admission must not silently rewrite historical v1 occurrence identities."""
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from test_digital_handoff import NOW, manifest
import test_digital_publisher_integration as integration


class MainPublisherAdmissionTests(unittest.TestCase):
    def test_main_packet_has_separate_stable_identity_and_v1_still_validates(self):
        from manager_core import digital_handoff as m
        old, new = manifest('a'*40, 'old'), manifest('b'*40, 'new')
        legacy = m.plan_release(old, new, NOW)
        main = m.plan_release(old, new, NOW, schema='manager.digital-handoff.v2')
        self.assertEqual(legacy['ref'], m.SOURCE_REF)
        self.assertEqual(main['ref'], 'refs/heads/main')
        self.assertNotEqual(main['effect_key'], legacy['effect_key'])
        self.assertEqual(main['effect_key'], m.plan_release(old, new, NOW+timedelta(minutes=1),
                         schema='manager.digital-handoff.v2')['effect_key'])
        self.assertEqual(m.validate_intent(legacy), NOW)
        self.assertEqual(m.validate_intent(main), NOW)
        with self.assertRaises(ValueError):
            m.plan_release(old, new, NOW, schema='manager.digital-handoff.v99')
        for field, value in (('schema', 'manager.digital-handoff.v1'),
                             ('ref', m.SOURCE_REF), ('workflow', 'attacker.yml')):
            bad = deepcopy(main); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.validate_intent(bad)

    def test_v2_requires_matching_workflow_commit_and_cannot_upgrade_v1(self):
        from manager_core import digital_handoff as m
        old, new = manifest('a'*40, 'old'), manifest('b'*40, 'new')
        packet = m.plan_release(old, new, NOW, schema='manager.digital-handoff.v2')
        context = m.PublisherContext(m.REPOSITORY, 'refs/heads/main', m.WORKFLOW,
                                     'b'*40, '12345', workflow_commit='b'*40)
        self.assertTrue(m.admit_release(packet, context, old, new, NOW)['dispatch_deployment'])
        for changes in ({'workflow_commit': None}, {'workflow_commit': 'c'*40},
                        {'ref': m.SOURCE_REF}, {'source_commit': 'c'*40}):
            with self.subTest(changes=changes), self.assertRaises(PermissionError):
                m.admit_release(packet, m.PublisherContext(**(context.__dict__ | changes)), old, new, NOW)
        with self.assertRaises(PermissionError):
            m.admit_release(m.plan_release(old, new, NOW), context, old, new, NOW)

    def test_actual_checkout_workflow_sha_and_event_checked_before_staging(self):
        from manager_core import digital_handoff as m
        helper = integration.PublisherIntegrationTests()
        release = helper.load()
        for mutation in (None, 'checkout', 'workflow_sha', 'event', 'ref', 'legacy'):
            with self.subTest(mutation=mutation), TemporaryDirectory() as tmp:
                root = Path(tmp)
                old, new, pages, intent, audit = helper.setup_files(root)
                packet = m.plan_release(json.loads((old/'manifest.json').read_text()),
                                        json.loads((new/'manifest.json').read_text()), NOW,
                                        schema='manager.digital-handoff.v2')
                intent.write_text(json.dumps(packet))
                env = helper.environment() | {
                    'GITHUB_REF': 'refs/heads/main', 'GITHUB_WORKFLOW_SHA': 'b'*40,
                    'GITHUB_EVENT_NAME': 'workflow_dispatch',
                    'GITHUB_WORKFLOW_REF': f'{m.REPOSITORY}/{m.WORKFLOW}@refs/heads/main'}
                checkout_sha = 'b'*40
                if mutation == 'checkout': checkout_sha = 'c'*40
                if mutation == 'workflow_sha': env['GITHUB_WORKFLOW_SHA'] = 'c'*40
                if mutation == 'event': env['GITHUB_EVENT_NAME'] = 'pull_request_target'
                if mutation == 'ref': env['GITHUB_REF'] = m.SOURCE_REF
                if mutation == 'legacy':
                    packet = m.plan_release(packet['baseline'], packet['candidate'], NOW)
                    intent.write_text(json.dumps(packet))
                before = {p.name:p.read_bytes() for p in (pages/'manager-support').iterdir()}
                with patch.dict(os.environ, env, clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value=checkout_sha):
                    if mutation is None:
                        result = release.admit(new, pages, audit, intent, root/'admission.json', NOW)
                        self.assertTrue(result['dispatch_deployment'])
                    else:
                        with self.assertRaises(PermissionError):
                            release.admit(new, pages, audit, intent, root/'admission.json', NOW)
                        self.assertEqual(before, {p.name:p.read_bytes() for p in (pages/'manager-support').iterdir()})

    def test_owned_bridge_revalidates_v2_scope_and_retains_original_packet_lease(self):
        from dataclasses import replace
        from manager_core import digital_handoff as m
        import test_digital_cycle_acceptance as acceptance
        helper = integration.PublisherIntegrationTests(); release = helper.load()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = acceptance.NOW
            _, _, host, _ = acceptance.CycleAcceptanceTests().prepare(tmp)
            prepared = m.prepare_owned_change(host.context, host.assessment, host.scope, now,
                                              schema='manager.digital-handoff.v2')
            self.assertEqual(prepared.packet['schema'], 'manager.digital-handoff.v2')
            audit = root/'audit.json'; audit.write_text(json.dumps(host.source_audit))
            env = helper.environment() | {
                'GITHUB_REF':'refs/heads/main','GITHUB_WORKFLOW_SHA':'b'*40,
                'GITHUB_EVENT_NAME':'workflow_dispatch',
                'GITHUB_WORKFLOW_REF':f'{m.REPOSITORY}/{m.WORKFLOW}@refs/heads/main'}
            with patch.dict(os.environ, env, clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b'*40):
                for bad_scope in (replace(host.scope,revoked=True), replace(host.scope,expires_at=now)):
                    with self.assertRaises(PermissionError):
                        release.admit_owned(host.context,host.assessment,bad_scope,prepared,
                                            host.checkout,audit,root/'admit.json',now)
                result = release.admit_owned(host.context,host.assessment,host.scope,prepared,
                                             host.checkout,audit,root/'admit.json',now+timedelta(seconds=1))
                self.assertTrue(result['dispatch_deployment'])


if __name__ == '__main__': unittest.main()
