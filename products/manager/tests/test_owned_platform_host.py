"""P0 contract probes for the exact GitHub Actions cycle adapter.

All GitHub CLI boundaries are patched in tests. No test proves real OIDC,
GitHub authority, provider writes, or public delivery.
"""
from datetime import timedelta
import json
from pathlib import Path
import shlex
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_candidate_verification import NOW
import test_owned_digital_cycle as owned_change_fixtures
from manager_core.authority import OwnedDigitalScope
from manager_core.digital_handoff import (
    ALLOWED_PATHS, MAIN_REF, REPOSITORY, WORKFLOW, plan_release,
    verify_readback,
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
            from manager_core import owned_catalog_planner as planner
            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                 patch.object(planner, 'plan_catalog_change', return_value=None) as select:
                result = run_owned_cycle(conf, store, host=host, now=NOW)
            select.assert_called_once_with(host.checkout, host.checkpoint.db.parent / 'planning',
                                           'b' * 40, NOW, run_id='123')
            self.assertEqual(host.source_audit_path, host.checkpoint.db.parent / 'planning' / 'source-audit.json')
            self.assertFalse(host.source_audit_path.exists())
            self.assertEqual(result['status'], 'NO_ACTION')
            self.assertEqual(result['writes'], 0)
            with self.assertRaises((TypeError, ValueError)):
                GitHubActionsCycleHost(host.checkpoint, host.checkout, host.source_audit_path,
                                       context=object())


    def test_fixed_selector_failure_is_unknown_not_a_noop_candidate(self):
        from manager_core.owned_platform_host import CatalogSelectionUnavailable, GitHubActionsCycleHost
        from manager_core import owned_catalog_planner as planner
        with TemporaryDirectory() as tmp:
            _, _, host, *_ = platform_fixture(Path(tmp), context_values=False)
            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(planner, 'plan_catalog_change', side_effect=ValueError('served mismatch')) as select:
                with self.assertRaises(CatalogSelectionUnavailable):
                    host.prepare_candidate(NOW)
            select.assert_called_once()
            self.assertEqual(host.source_audit_path, host.checkpoint.db.parent / 'planning' / 'source-audit.json')

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

    def test_privileged_git_hooks_do_not_run_and_committed_tree_matches_admission(self):
        with TemporaryDirectory() as tmp:
            conf, store, host, gateway, *_ = platform_fixture(Path(tmp))
            from scripts import phase06_kernel_release as release
            import manager_core.owned_public_collector as collector
            parent = host._git('rev-parse', 'HEAD')
            events = []
            marker = Path(tmp) / 'hook-ran'
            outside = host.checkout / 'outside-scope.txt'
            hook_body = (
                '#!/bin/sh\n'
                f'printf hook-ran > {shlex.quote(str(marker))}\n'
                f'printf hook-created > {shlex.quote(str(outside))}\n'
                f'git -C {shlex.quote(str(host.checkout))} add -- outside-scope.txt\n'
            )
            hooks = host.checkout / '.git' / 'hooks'
            for name in ('pre-commit', 'prepare-commit-msg', 'commit-msg',
                         'post-commit', 'reference-transaction', 'pre-push'):
                path = hooks / name
                path.write_text(hook_body)
                path.chmod(0o700)

            actual_admit = release.admit_owned
            admitted_paths = []

            def admitted(*args, **kwargs):
                value = actual_admit(*args, **kwargs)
                admitted_paths.extend(value.get('changed_files', ()))
                return value

            actual_cli = host._run_cli

            def cli_boundary(argv, *, input_data=None, timeout=None):
                if argv[:3] == ['git', '-C', str(host.checkout)] and 'fetch' in argv:
                    (host.checkout / '.git' / 'FETCH_HEAD').write_text(
                        parent + '\tbranch refs/heads/gh-pages\n')
                    return ''
                if argv[0] == 'git' and 'push' in argv:
                    events.append('push')
                    return ''
                if argv[0] == 'gh':
                    events.append('dispatch')
                    return ''
                return actual_cli(argv, input_data=input_data, timeout=timeout)

            with patch.dict('os.environ', github_environment(), clear=True), \
                 patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                 patch.object(release, 'admit_owned', side_effect=admitted), \
                 patch.object(host, '_run_cli', side_effect=cli_boundary), \
                 patch.object(collector, 'collect_owned_occurrence', return_value=None), \
                 patch.object(host, '_now', return_value=NOW):
                result = run_owned_cycle(conf, store, host=host, now=NOW)

            commit = host._git('rev-parse', 'HEAD')
            paths = set(host._git('diff-tree', '--no-commit-id', '--name-only', '-r', '-z', commit).split('\x00')) - {''}
            self.assertEqual(result['status'], 'UNKNOWN')
            self.assertEqual(events, ['push', 'dispatch'])
            self.assertFalse(marker.exists())
            self.assertFalse(outside.exists())
            self.assertTrue(paths)
            self.assertEqual(paths, set(admitted_paths))
            self.assertTrue(paths <= set(ALLOWED_PATHS))
            self.assertEqual(host._git('rev-parse', f'{commit}^'), parent)
            self.assertEqual(host._git('show', '-s', '--format=%an <%ae>', commit),
                             'github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>')
            manifest = json.loads(host._git_blob(commit, 'manager-support/manifest.json'))
            expected_manifest = json.loads((host.context.candidate_bundle / 'manifest.json').read_text())
            self.assertEqual(manifest, expected_manifest)
            page_bodies = {
                name: host._git_blob(commit, f'manager-support/{name}')
                for name in manifest['files']
            }
            verify_readback(manifest, page_bodies)
            self.assertEqual(host._git('rev-parse', f'{commit}^{{tree}}'),
                             host._git('write-tree'))

    def test_tainted_commit_path_or_manifest_is_rejected_before_ref_update_and_push(self):
        for mutation in ('outside_path', 'manifest'):
            with self.subTest(mutation=mutation), TemporaryDirectory() as tmp:
                conf, store, host, gateway, *_ = platform_fixture(Path(tmp))
                from scripts import phase06_kernel_release as release
                parent = host._git('rev-parse', 'HEAD')
                events = []
                actual_git = host._git

                def tainted_git(*args):
                    if args == ('write-tree',):
                        if mutation == 'outside_path':
                            (host.checkout / 'outside-scope.txt').write_text('unexpected')
                            actual_git('add', '--', 'outside-scope.txt')
                        else:
                            manifest_path = host.checkout / 'manager-support' / 'manifest.json'
                            manifest = json.loads(manifest_path.read_text())
                            manifest['source_commit'] = 'c' * 40
                            manifest_path.write_text(json.dumps(manifest))
                            actual_git('add', '--', 'manager-support/manifest.json')
                    return actual_git(*args)

                def cli_boundary(argv, *, input_data=None, timeout=None):
                    if argv[:3] == ['git', '-C', str(host.checkout)] and 'fetch' in argv:
                        (host.checkout / '.git' / 'FETCH_HEAD').write_text(
                            parent + '\tbranch refs/heads/gh-pages\n')
                        return ''
                    if argv[0] == 'git' and 'push' in argv:
                        events.append('push')
                        return ''
                    if argv[0] == 'gh':
                        events.append('dispatch')
                        return ''
                    return actual_cli(argv, input_data=input_data, timeout=timeout)

                actual_cli = host._run_cli
                with patch.dict('os.environ', github_environment(), clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                     patch.object(host, '_git', side_effect=tainted_git), \
                     patch.object(host, '_run_cli', side_effect=cli_boundary), \
                     patch.object(host, '_now', return_value=NOW):
                    result = run_owned_cycle(conf, store, host=host, now=NOW)

                self.assertEqual(result['status'], 'UNKNOWN')
                self.assertEqual(events, [])
                self.assertEqual(actual_git('rev-parse', 'HEAD'), parent)

    def test_final_fetch_crossing_packet_or_host_deadline_never_pushes(self):
        for crossing in ('host_lifetime', 'packet_expiry'):
            with self.subTest(crossing=crossing), TemporaryDirectory() as tmp:
                conf, store, host, gateway, *_ = platform_fixture(Path(tmp))
                from scripts import phase06_kernel_release as release
                parent = host._git('rev-parse', 'HEAD')
                events = []
                elapsed = [100.0]
                current_time = [NOW]
                host._started_at = 100.0
                fetches = [0]
                actual_cli = host._run_cli

                def cli_boundary(argv, *, input_data=None, timeout=None):
                    if argv[:3] == ['git', '-C', str(host.checkout)] and 'fetch' in argv:
                        fetches[0] += 1
                        if fetches[0] == 3:
                            elapsed[0] = 701.0 if crossing == 'host_lifetime' else 200.0
                            if crossing == 'packet_expiry':
                                current_time[0] = NOW + timedelta(hours=6)
                        (host.checkout / '.git' / 'FETCH_HEAD').write_text(
                            parent + '\tbranch refs/heads/gh-pages\n')
                        return ''
                    if argv[0] == 'git' and 'push' in argv:
                        events.append('push')
                        return ''
                    if argv[0] == 'gh':
                        events.append('dispatch')
                        return ''
                    return actual_cli(argv, input_data=input_data, timeout=timeout)

                with patch.dict('os.environ', github_environment(), clear=True), \
                     patch.object(release, 'source_checkout_commit', return_value='b' * 40), \
                     patch.object(host, '_run_cli', side_effect=cli_boundary), \
                     patch('manager_core.owned_platform_host.monotonic', side_effect=lambda: elapsed[0]), \
                     patch.object(host, '_now', side_effect=lambda: current_time[0]):
                    result = run_owned_cycle(conf, store, host=host, now=NOW)

                self.assertEqual(result['status'], 'UNKNOWN')
                self.assertEqual(events, [])
                self.assertEqual(fetches[0], 3)


if __name__ == '__main__':
    unittest.main()
