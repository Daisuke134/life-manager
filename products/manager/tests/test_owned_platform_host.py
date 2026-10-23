"""P0 contract probes for the exact GitHub Actions cycle adapter.

All GitHub CLI boundaries are patched in tests. No test proves real OIDC,
GitHub authority, provider writes, or public delivery.
"""
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_candidate_verification import NOW
import test_owned_digital_cycle as owned_change_fixtures
from manager_core.authority import OwnedDigitalScope
from manager_core.digital_handoff import (
    ALLOWED_PATHS, MAIN_REF, REPOSITORY, WORKFLOW, plan_release,
)
from manager_core.owned_cycle import CycleConfig, CycleStore, run_owned_cycle
from manager_core.owned_checkpoint import PrivateCheckpoint
from test_owned_checkpoint import MemoryGateway


WORKFLOW_REF = f'{REPOSITORY}/{WORKFLOW}@{MAIN_REF}'


def github_environment(**changes):
    value = {
        'GITHUB_REPOSITORY': REPOSITORY,
        'GITHUB_REF': MAIN_REF,
        'GITHUB_WORKFLOW_REF': WORKFLOW_REF,
        'GITHUB_WORKFLOW': 'Manager Phase06 Digital Environment',
        'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_SHA': 'b' * 40,
        'GITHUB_WORKFLOW_SHA': 'b' * 40,
        'GITHUB_RUN_ID': '123',
        'GITHUB_RUN_ATTEMPT': '1',
        'RUNNER_ENVIRONMENT': 'github-hosted',
        'MANAGER_RELEASE_ENABLED': 'true',
    }
    value.update(changes)
    return value


def platform_fixture(root, *, context_values=True, audit=True):
    root = Path(root)
    model_root = root / 'models'
    model_root.mkdir(parents=True, exist_ok=True)
    _, context, assessment, scope = owned_change_fixtures.OwnedChangeTests().prepare(model_root)

    audit_path = root / 'source-audit.json'
    catalog = json.loads((Path(__file__).resolve().parents[1] / 'public_goods/service/catalog.json').read_text())
    audit_value = {
        'content_rights': 'LINK_ONLY', 'human_outcome': 'NOT_MEASURED',
        'sources': [
            {'id': row['id'], 'url': row['url'], 'status': 'REACHABLE_NOT_OUTCOME',
             'http_status': 200, 'sha256': 'f' * 64, 'observed_at': NOW.isoformat()}
            for row in catalog['resources']
        ],
    }
    if audit:
        audit_path.write_text(json.dumps(audit_value))

    seed = CycleStore(root / 'seed')
    gateway = MemoryGateway(seed.db.read_bytes())
    checkpoint = PrivateCheckpoint(gateway, run_id='123', run_attempt='1')
    db_path = checkpoint.acquire(root / 'private-scratch')
    store = CycleStore(db_path.parent)

    packet = plan_release(
        json.loads((context.baseline_bundle / 'manifest.json').read_text()),
        json.loads((context.candidate_bundle / 'manifest.json').read_text()),
        NOW, schema='manager.digital-handoff.v2',
    )
    from test_owned_effect_recovery import GitOccurrenceFixture
    pages = GitOccurrenceFixture(root / 'pages', context.baseline_bundle,
                                 context.candidate_bundle, packet)
    pages.git('branch', '-m', 'gh-pages')
    pages.git('remote', 'add', 'origin', 'https://github.com/Daisuke134/life-manager.git')

    from manager_core.owned_platform_host import GitHubActionsCycleHost
    candidate_context, candidate_assessment, candidate_scope = (
        (context, assessment, scope) if context_values else (None, None, None)
    )
    host = GitHubActionsCycleHost(
        checkpoint, pages.root, audit_path if audit else None,
        context=candidate_context, assessment=candidate_assessment,
        scope=candidate_scope,
    )
    return CycleConfig('platform-fixture-owner', 60), store, host, gateway, context, assessment, scope, pages


class GitHubActionsCycleHostTests(unittest.TestCase):
    def run_platform(self, root, env=None):
        conf, store, host, gateway, *_ = platform_fixture(root)
        from scripts import phase06_kernel_release as release
        environment = github_environment() if env is None else env
        with patch.dict('os.environ', environment, clear=True), \
             patch.object(release, 'source_checkout_commit', return_value='b' * 40):
            return conf, store, host, gateway, run_owned_cycle(conf, store, host=host, now=NOW)

    def test_only_exact_platform_identity_reaches_platform_checkout(self):
        changes = (
            {'GITHUB_REPOSITORY': 'attacker/other'},
            {'GITHUB_REF': 'refs/heads/research/other'},
            {'GITHUB_WORKFLOW_REF': 'attacker.yml@refs/heads/main'},
            {'GITHUB_EVENT_NAME': 'pull_request_target'},
            {'RUNNER_ENVIRONMENT': 'self-hosted'},
            {'GITHUB_SHA': 'c' * 40},
            {'GITHUB_WORKFLOW_SHA': 'c' * 40},
            {'GITHUB_RUN_ATTEMPT': '0'},
        )
        for changed in changes:
            with self.subTest(changed=changed), TemporaryDirectory() as tmp:
                conf, store, host, *_ = platform_fixture(Path(tmp))
                from scripts import phase06_kernel_release as release
                with patch.dict('os.environ', github_environment(**changed), clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value='b' * 40):
                    with self.assertRaises(PermissionError):
                        run_owned_cycle(conf, store, host=host, now=NOW)
                self.assertEqual(store.journal.pending_records(), ())

    def test_release_control_blocks_candidate_after_read_only_session_admission(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, *_ = platform_fixture(Path(tmp))
            from scripts import phase06_kernel_release as release
            with patch.dict('os.environ', github_environment(MANAGER_RELEASE_ENABLED='false'), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                 patch.object(release, 'admit_owned') as admit:
                result = run_owned_cycle(conf, store, host=host, now=NOW)
            self.assertEqual(result['status'], 'NO_ACTION')
            self.assertEqual(result['reason'], 'RELEASE_DISABLED')
            admit.assert_not_called()
            self.assertEqual(store.journal.pending_records(), ())

    def test_arbitrary_callable_and_platform_subclass_do_not_create_host_authority(self):
        from manager_core.owned_platform_host import GitHubActionsCycleHost
        with TemporaryDirectory() as tmp:
            conf, store, host, *_ = platform_fixture(Path(tmp))
            class DerivedHost(GitHubActionsCycleHost):
                pass
            derived = DerivedHost(host.checkpoint, host.checkout, host.source_audit_path)
            for untrusted in (lambda *_: None, {}, derived):
                result = run_owned_cycle(conf, store, host=untrusted, now=NOW)
                self.assertEqual(result['status'], 'DEPLOYMENT_HOST_REQUIRED')

    def test_requires_typed_optional_candidate_and_accepts_absence(self):
        from manager_core.owned_platform_host import GitHubActionsCycleHost
        with TemporaryDirectory() as tmp:
            conf, store, host, *_ = platform_fixture(Path(tmp), context_values=False)
            from scripts import phase06_kernel_release as release
            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40):
                result = run_owned_cycle(conf, store, host=host, now=NOW)
            self.assertEqual(result['status'], 'NO_ACTION')
            self.assertEqual(result['writes'], 0)
            with self.assertRaises((TypeError, ValueError)):
                GitHubActionsCycleHost(host.checkpoint, host.checkout, host.source_audit_path,
                                       context=object())

    def test_expired_or_revoked_scope_is_no_action_without_staging(self):
        for changed_scope in (
            OwnedDigitalScope('expired', frozenset(ALLOWED_PATHS),
                              NOW - timedelta(hours=1), NOW, len(ALLOWED_PATHS)),
            OwnedDigitalScope('revoked', frozenset(ALLOWED_PATHS),
                              NOW - timedelta(minutes=1), NOW + timedelta(hours=1),
                              len(ALLOWED_PATHS), revoked=True),
        ):
            with self.subTest(scope=changed_scope.scope_id), TemporaryDirectory() as tmp:
                conf, store, host, *_ = platform_fixture(Path(tmp))
                host.scope = changed_scope
                from scripts import phase06_kernel_release as release
                with patch.dict('os.environ', github_environment(), clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                     patch.object(release, 'admit_owned') as admit, \
                     patch.object(host, '_now', return_value=NOW):
                    result = run_owned_cycle(conf, store, host=host, now=NOW)
                self.assertEqual(result['status'], 'NO_ACTION')
                admit.assert_not_called()
                self.assertEqual(store.journal.pending_records(), ())

    def test_wrong_or_dirty_pages_checkout_refuses_before_original_admission(self):
        for mutation in ('wrong_branch', 'dirty', 'wrong_origin'):
            with self.subTest(mutation=mutation), TemporaryDirectory() as tmp:
                conf, store, host, *_ = platform_fixture(Path(tmp))
                from scripts import phase06_kernel_release as release
                if mutation == 'wrong_branch':
                    host._git('checkout', '-qb', 'main')
                elif mutation == 'dirty':
                    (host.checkout / 'unrelated.html').write_text('uncommitted')
                else:
                    host._git('remote', 'set-url', 'origin', 'https://example.invalid/wrong.git')
                with patch.dict('os.environ', github_environment(), clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                     patch.object(release, 'admit_owned') as admit, \
                     patch.object(host, '_now', return_value=NOW):
                    result = run_owned_cycle(conf, store, host=host, now=NOW)
                self.assertEqual(result['status'], 'NO_ACTION')
                admit.assert_not_called()
                self.assertEqual(store.journal.pending_records(), ())

    def test_changed_candidate_and_moved_remote_parent_refuse_before_staging(self):
        for mutation in ('candidate', 'parent'):
            with self.subTest(mutation=mutation), TemporaryDirectory() as tmp:
                conf, store, host, *_ = platform_fixture(Path(tmp))
                from scripts import phase06_kernel_release as release
                if mutation == 'candidate':
                    candidate = host.context.candidate_bundle / 'finance.html'
                    candidate.write_bytes(candidate.read_bytes() + b'changed after assessment')
                    manifest_path = host.context.candidate_bundle / 'manifest.json'
                    manifest = json.loads(manifest_path.read_text())
                    manifest['files']['finance.html'] = 'f' * 64
                    manifest_path.write_text(json.dumps(manifest))
                else:
                    original = host._run_cli

                    def moved_parent(argv, *, input_data=None, timeout=None):
                        if argv[:3] == ['git', '-C', str(host.checkout)] and 'fetch' in argv:
                            (host.checkout / '.git' / 'FETCH_HEAD').write_text('c' * 40 + '\tbranch refs/heads/gh-pages\n')
                            return ''
                        return original(argv, input_data=input_data, timeout=timeout)

                    host._run_cli = moved_parent
                before = (host.checkout / 'manager-support' / 'manifest.json').read_bytes()
                with patch.dict('os.environ', github_environment(), clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                     patch.object(release, 'admit_owned') as admit, \
                     patch.object(host, '_now', return_value=NOW):
                    if mutation == 'candidate':
                        result = run_owned_cycle(conf, store, host=host, now=NOW)
                        self.assertEqual(result['status'], 'NO_ACTION')
                    else:
                        result = run_owned_cycle(conf, store, host=host, now=NOW)
                        self.assertEqual(result['status'], 'NO_ACTION')
                admit.assert_not_called()
                self.assertEqual(before, (host.checkout / 'manager-support' / 'manifest.json').read_bytes())
                self.assertEqual(store.journal.pending_records(), ())


if __name__ == '__main__':
    unittest.main()
