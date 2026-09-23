import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import owned_publish as module


class OwnedPublishRevisionTest(unittest.TestCase):
    def test_immutable_release_delivers_to_configured_live_site_repository(self):
        """A runtime release repo is not necessarily the public site's deploy repo."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            canonical = base / "canonical"
            canonical_remote = base / "canonical.git"
            site = base / "site"
            site_remote = base / "site.git"
            release = base / "release"
            state = base / "state"
            for source, remote, label in (
                (canonical, canonical_remote, "canonical"),
                (site, site_remote, "site"),
            ):
                source.mkdir()
                self.git("git", "init", "-b", "main", cwd=source)
                self.git("git", "init", "--bare", str(remote))
                self.git("git", "remote", "add", "origin", str(remote), cwd=source)
                (source / "README.md").write_text(f"{label}\n")
                self.git("git", "add", ".", cwd=source)
                self.git("git", "commit", "-m", f"initial {label}", cwd=source)
                self.git("git", "push", "-u", "origin", "main", cwd=source)
            release.mkdir()
            release_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=canonical, text=True,
            ).strip()
            (release / "RELEASE.json").write_text(json.dumps({
                "sha": release_sha, "repo": canonical_remote.as_uri(),
            }))
            slug = "configured-live-site"
            markdown = "# Configured live site\n"
            content_hash = hashlib.sha256(markdown.encode()).hexdigest()
            for name in ("content", "policy", "owned-publications"):
                (state / name).mkdir(parents=True, exist_ok=True)
            artifact = {
                "slug": slug, "state": "READY_FOR_PUBLICATION",
                "markdown": markdown, "content_sha256": content_hash,
                "disclosure": "affiliate_link", "title": "Configured live site",
                "built_at": "2026-09-23T00:00:00+00:00", "project": "P",
                "source_hashes": [], "readback_markers": [], "readback_links": [],
            }
            (state / "content" / f"{slug}.json").write_text(json.dumps(artifact))
            (state / "policy" / f"{slug}.json").write_text(json.dumps({
                "decision": "PASS", "content_sha256": content_hash,
            }))

            # Reproduce production: the old publisher delivered to the runtime
            # repository and marked the effect verified, but the live site repo
            # never received the article.
            canonical_target = (
                canonical / "apps/landing/data/research" / f"{slug}.json"
            )
            canonical_target.parent.mkdir(parents=True)
            canonical_target.write_text(
                json.dumps(module.public_row(artifact), ensure_ascii=False, indent=2) + "\n"
            )
            self.git("git", "add", ".", cwd=canonical)
            self.git("git", "commit", "-m", f"feat(blog): publish {slug}", cwd=canonical)
            self.git("git", "push", "origin", "main", cwd=canonical)
            wrong_commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=canonical, text=True,
            ).strip()
            receipt_path = state / "owned-publications" / f"{slug}.json"
            receipt_path.write_text(json.dumps({
                "schema_version": 1, "receipt_type": "OWNED_PUBLICATION",
                "slug": slug, "content_sha256": content_hash,
                "state": "DELIVERED", "target": canonical_target.relative_to(canonical).as_posix(),
                "commit": wrong_commit, "remote": "origin", "branch": "main",
            }))
            wrong_action = {
                "content_sha256": content_hash, "commit": wrong_commit,
                "remote": "origin", "branch": "main",
            }
            wrong_job = module.start_effect(
                state, "OWNED_GIT_PUSH", slug, wrong_action,
                {"remote": "origin", "branch": "main", "head": release_sha}, 300,
            )
            module.verify_effect(state, wrong_job["job_id"], {
                "state": "DELIVERED", "remote": "origin",
                "branch": "main", "head": wrong_commit,
            })

            with patch.object(module, "fetch_readback", return_value=None):
                result = module.publish(Namespace(
                    state=state, landing_root=release, slug=slug,
                    base_url="https://example.test", remote="origin", branch="main",
                    repository=site_remote.as_uri(),
                ))

            self.assertEqual(result["state"], "DELIVERED")
            self.assertEqual(result["repository"], site_remote.as_uri())
            self.assertEqual(result["legacy_deliveries"][0]["commit"], wrong_commit)
            published = subprocess.check_output([
                "git", f"--git-dir={site_remote}", "show",
                f"main:apps/landing/data/research/{slug}.json",
            ], text=True)
            self.assertEqual(json.loads(published)["slug"], slug)
            events = [
                json.loads(line)
                for line in (state / "job-events.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len({row["job_id"] for row in events}), 2)
            self.assertEqual(events[-1]["state"], "VERIFIED")

    def test_immutable_release_provisions_managed_publisher_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            remote = base / "remote.git"
            release = base / "release"
            state = base / "state"
            source.mkdir()
            release.mkdir()
            self.git("git", "init", "-b", "main", cwd=source)
            self.git("git", "init", "--bare", str(remote))
            self.git("git", "remote", "add", "origin", str(remote), cwd=source)
            (source / "README.md").write_text("publisher fixture\n")
            self.git("git", "add", ".", cwd=source)
            self.git("git", "commit", "-m", "initial", cwd=source)
            self.git("git", "push", "-u", "origin", "main", cwd=source)
            (release / "RELEASE.json").write_text(json.dumps({
                "sha": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=source, text=True,
                ).strip(),
                "repo": remote.as_uri(),
            }))
            slug = "managed-publisher"
            markdown = "# Managed publisher\n"
            for name in ("content", "policy", "owned-publications"):
                (state / name).mkdir(parents=True, exist_ok=True)
            content_hash = hashlib.sha256(markdown.encode()).hexdigest()
            (state / "content" / f"{slug}.json").write_text(json.dumps({
                "slug": slug, "state": "READY_FOR_PUBLICATION",
                "markdown": markdown, "content_sha256": content_hash,
                "disclosure": "affiliate_link", "title": "Managed publisher",
                "built_at": "2026-09-23T00:00:00+00:00", "project": "P",
                "source_hashes": [], "readback_markers": [], "readback_links": [],
            }))
            (state / "policy" / f"{slug}.json").write_text(json.dumps({
                "decision": "PASS", "content_sha256": content_hash,
            }))
            git_identity = {
                "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
            }

            with patch.dict(os.environ, git_identity), patch.object(
                module, "fetch_readback", return_value=None,
            ):
                result = module.publish(Namespace(
                    state=state, landing_root=release, slug=slug,
                    base_url="https://example.test", remote="origin", branch="main",
                    repository=remote.as_uri(),
                ))

            managed = state / "publisher-checkout"
            self.assertEqual(result["state"], "DELIVERED")
            self.assertTrue((managed / ".git").exists())
            self.assertTrue((managed / "apps/landing/data/research" / f"{slug}.json").is_file())
            self.assertFalse((release / ".git").exists())
            pushed = subprocess.check_output([
                "git", f"--git-dir={remote}", "show",
                f"main:apps/landing/data/research/{slug}.json",
            ], text=True)
            self.assertEqual(json.loads(pushed)["slug"], slug)
            with patch.object(module, "fetch_readback", return_value=None):
                with self.assertRaisesRegex(module.PublishError, "remote must be origin"):
                    module.publish(Namespace(
                        state=state, landing_root=release, slug=slug,
                        base_url="https://example.test", remote=remote.as_uri(),
                        branch="main",
                    ))
            other_remote = base / "other.git"
            self.git("git", "init", "--bare", str(other_remote))
            self.git(
                "git", "remote", "set-url", "--add", "--push", "origin",
                other_remote.as_uri(), cwd=managed,
            )
            with self.assertRaisesRegex(module.PublishError, "push remote"):
                module._managed_publisher_root(state, release, "main")
            self.git(
                "git", "config", "--unset-all", "remote.origin.pushurl", cwd=managed,
            )
            self.git("git", "pull", "--ff-only", "origin", "main", cwd=source)
            (source / "README.md").write_text("publisher fixture advanced\n")
            self.git("git", "add", "README.md", cwd=source)
            self.git("git", "commit", "-m", "advance", cwd=source)
            self.git("git", "push", "origin", "main", cwd=source)

            resolved = module._managed_publisher_root(state, release, "main")

            self.assertEqual(
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=resolved, text=True,
                ).strip(),
                subprocess.check_output(
                    ["git", f"--git-dir={remote}", "rev-parse", "main"], text=True,
                ).strip(),
            )
            pending = resolved / "apps/landing/data/research/unpushed.json"
            pending.write_text("{}\n")
            self.git("git", "add", str(pending.relative_to(resolved)), cwd=resolved)
            self.git(
                "git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                "commit", "-m", "unpushed", cwd=resolved,
            )

            self.assertEqual(
                module._managed_publisher_root(
                    state, release, "main",
                    "apps/landing/data/research/unpushed.json",
                ),
                resolved,
            )
            (source / "README.md").write_text("publisher fixture advanced again\n")
            self.git("git", "add", "README.md", cwd=source)
            self.git("git", "commit", "-m", "advance again", cwd=source)
            self.git("git", "push", "origin", "main", cwd=source)
            self.assertEqual(
                module._managed_publisher_root(
                    state, release, "main",
                    "apps/landing/data/research/unpushed.json",
                ),
                resolved,
            )
            with self.assertRaisesRegex(module.PublishError, "managed publisher checkout"):
                module._managed_publisher_root(
                    state, release, "main",
                    "apps/landing/data/research/different.json",
                )

            symlink_state = base / "symlink-state"
            symlink_state.mkdir()
            (symlink_state / "publisher-checkout").symlink_to(source)
            with self.assertRaisesRegex(module.PublishError, "must not be a symlink"):
                module._managed_publisher_root(symlink_state, release, "main")

    def test_readback_accepts_fixed_host_redirect_for_provider_link(self):
        placement = "subtitle-experiment-1"
        artifact = {
            "slug": "subtitle-experiment", "title": "Subtitle experiment",
            "readback_markers": ["Affiliate disclosure"],
            "readback_links": [f"https://try.elevenlabs.io/{placement}"],
        }
        markup = (
            '<html><h1>Subtitle experiment</h1><p>Affiliate disclosure</p>'
            f'<a href="/go/af_{placement}">Try it</a></html>'
        ).encode()
        with patch.object(module, "_read_public_markup", return_value=(markup, "test")):
            result = module.fetch_readback(artifact, "https://example.test")
        self.assertEqual(result["public_url"], "https://example.test/blog/subtitle-experiment")

    def test_live_same_slug_revision_requires_and_replaces_prior_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "landing"
            remote = Path(temporary) / "remote.git"
            state = Path(temporary) / "state"
            root.mkdir()
            self.git("git", "init", "-b", "main", cwd=root)
            self.git("git", "config", "user.email", "test@example.com", cwd=root)
            self.git("git", "config", "user.name", "Test", cwd=root)
            self.git("git", "init", "--bare", str(remote))
            self.git("git", "remote", "add", "origin", str(remote), cwd=root)
            slug, old, new = "same-slug", "# Old\n", "# New\n"
            target = root / "apps/landing/data/research" / f"{slug}.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({"slug": slug, "markdown": old}) + "\n")
            self.git("git", "add", ".", cwd=root)
            self.git("git", "commit", "-m", "old", cwd=root)
            self.git("git", "push", "origin", "main", cwd=root)
            for name in ("content", "policy", "owned-publications"):
                (state / name).mkdir(parents=True, exist_ok=True)
            new_hash = hashlib.sha256(new.encode()).hexdigest()
            artifact = {
                "slug": slug, "state": "READY_FOR_PUBLICATION", "markdown": new,
                "content_sha256": new_hash, "disclosure": "affiliate_link",
                "title": "Title", "built_at": "2026-08-16T00:00:00+00:00",
                "project": "P", "source_hashes": [], "readback_markers": [],
                "readback_links": [],
            }
            (state / "content" / f"{slug}.json").write_text(json.dumps(artifact))
            (state / "policy" / f"{slug}.json").write_text(json.dumps({
                "decision": "PASS", "content_sha256": new_hash,
            }))
            (state / "owned-publications" / f"{slug}.json").write_text(json.dumps({
                "slug": slug, "state": "LIVE",
                "content_sha256": hashlib.sha256(old.encode()).hexdigest(),
                "public_url": "https://example.test/blog/same-slug",
            }))
            readback = {
                "public_url": "https://example.test/blog/same-slug",
                "rendered_sha256": "a" * 64, "observed_at": "now",
            }
            target.write_text(json.dumps({"slug": slug, "markdown": "# Unexpected\n"}) + "\n")
            with self.assertRaises(module.PublishError):
                module.publish(Namespace(
                    state=state, landing_root=root, slug=slug,
                    base_url="https://example.test", remote="origin", branch="main",
                ))
            target.write_text(json.dumps({"slug": slug, "markdown": old}) + "\n")
            with patch.object(module, "fetch_readback", return_value=readback):
                result = module.publish(Namespace(
                    state=state, landing_root=root, slug=slug,
                    base_url="https://example.test", remote="origin", branch="main",
                ))
            self.assertEqual(result["state"], "LIVE")
            self.assertEqual(json.loads(target.read_text())["markdown"], new)

    def test_github_delivery_uses_deterministic_pull_request_and_auto_merge(self):
        root = Path("/tmp/publisher-checkout")
        commit = "a" * 40
        branch = "affiliate/publish-protected-main-" + "b" * 12
        pull_request = "https://github.com/Daisuke134/life-manager/pull/9999"
        views = [
            json.dumps({
                "autoMergeRequest": None,
                "baseRefName": "main",
                "headRefOid": commit,
                "mergeCommit": None,
                "state": "OPEN",
                "url": pull_request,
            }),
            json.dumps({
                "autoMergeRequest": {"enabledAt": "2026-09-23T00:00:00Z"},
                "baseRefName": "main",
                "headRefOid": commit,
                "mergeCommit": {"oid": "c" * 40},
                "state": "MERGED",
                "url": pull_request,
            }),
        ]

        def gh_side_effect(_root, *args):
            if args[:2] == ("pr", "list"):
                return "[]"
            if args[:2] == ("pr", "create"):
                return pull_request
            if args[:2] == ("pr", "view"):
                return views.pop(0)
            if args[:2] == ("pr", "merge"):
                return ""
            raise AssertionError(args)

        with patch.object(module, "git", return_value="") as git_mock, patch.object(
            module, "_gh", side_effect=gh_side_effect,
        ):
            result = module._github_pull_request(
                root=root,
                repository="Daisuke134/life-manager",
                remote="origin",
                target_branch="main",
                head_branch=branch,
                commit=commit,
                slug="protected-main",
            )

        self.assertEqual(result["state"], "DELIVERED")
        self.assertEqual(result["pull_request_url"], pull_request)
        pushes = [call.args for call in git_mock.call_args_list if call.args[1] == "push"]
        self.assertEqual(pushes, [(root, "push", "origin", f"{commit}:refs/heads/{branch}")])
        self.assertNotIn("HEAD:refs/heads/main", repr(git_mock.call_args_list))
        self.assertIn(
            (root, "merge-base", "--is-ancestor", commit, "c" * 40),
            [call.args for call in git_mock.call_args_list],
        )
        self.assertIn(
            (root, "merge-base", "--is-ancestor", "c" * 40, "FETCH_HEAD"),
            [call.args for call in git_mock.call_args_list],
        )

    def test_github_delivery_merges_unprotected_site_pull_request_immediately(self):
        root = Path("/tmp/site-publisher-checkout")
        commit = "d" * 40
        branch = "affiliate/publish-site-" + "e" * 12
        pull_request = "https://github.com/Daisuke134/anicca-products/pull/9999"
        views = [
            json.dumps({
                "autoMergeRequest": None, "baseRefName": "main",
                "headRefOid": commit, "mergeCommit": None,
                "state": "OPEN", "url": pull_request,
            }),
            json.dumps({
                "autoMergeRequest": None, "baseRefName": "main",
                "headRefOid": commit, "mergeCommit": {"oid": "f" * 40},
                "state": "MERGED", "url": pull_request,
            }),
        ]
        calls = []

        def gh_side_effect(_root, *args):
            calls.append(args)
            if args[:2] == ("pr", "list"):
                return "[]"
            if args[:2] == ("pr", "create"):
                return pull_request
            if args[:2] == ("pr", "view"):
                return views.pop(0)
            if args[:2] == ("pr", "merge"):
                return ""
            raise AssertionError(args)

        with patch.object(module, "git", return_value=""), patch.object(
            module, "_gh", side_effect=gh_side_effect,
        ):
            result = module._github_pull_request(
                root=root, repository="Daisuke134/anicca-products",
                remote="origin", target_branch="main", head_branch=branch,
                commit=commit, slug="site", merge_mode="immediate",
            )

        self.assertEqual(result["state"], "DELIVERED")
        merge_call = next(args for args in calls if args[:2] == ("pr", "merge"))
        self.assertIn("--merge", merge_call)
        self.assertNotIn("--auto", merge_call)

    def test_publication_repository_accepts_github_or_local_only(self):
        self.assertEqual(
            module._publication_repository("https://github.com/Daisuke134/life-manager.git"),
            "Daisuke134/life-manager",
        )
        self.assertIsNone(module._publication_repository("file:///tmp/life-manager.git"))
        self.assertIsNone(module._publication_repository("/tmp/life-manager.git"))
        for remote in (
            "git@github.com:Daisuke134/life-manager.git",
            "https://token@github.com/Daisuke134/life-manager.git",
            "https://gitlab.com/Daisuke134/life-manager.git",
            "relative/repository.git",
        ):
            with self.subTest(remote=remote), self.assertRaisesRegex(
                module.PublishError, "unsupported publisher remote",
            ):
                module._publication_repository(remote)

    def test_unresolved_publication_effect_rejects_unrelated_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            last_verified = {"remote": "origin", "branch": "main", "head": "a" * 40}
            module.start_effect(
                state, "OWNED_GIT_PUSH", "fingerprint-check",
                {"content_sha256": "wrong", "commit": "b" * 40,
                 "remote": "origin", "branch": "main"},
                last_verified, 300,
            )
            current = {
                "content_sha256": "c" * 64, "commit": "d" * 40,
                "remote": "origin", "branch": "main", "delivery": "pull_request",
                "head_branch": "affiliate/publish-fingerprint-check-cccccccccccc",
            }
            legacy = {key: current[key] for key in (
                "content_sha256", "commit", "remote", "branch",
            )}
            with self.assertRaisesRegex(module.PublishError, "does not match"):
                module._publication_effect(
                    state, "fingerprint-check", current, legacy, last_verified,
                )

    def test_legacy_unresolved_effect_resumes_diverged_checkout_through_one_pr(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, remote, release, state = (
                base / "source", base / "remote.git", base / "release", base / "state",
            )
            source.mkdir()
            release.mkdir()
            self.git("git", "init", "-b", "main", cwd=source)
            self.git("git", "init", "--bare", str(remote))
            self.git("git", "remote", "add", "origin", str(remote), cwd=source)
            (source / "README.md").write_text("base\n")
            self.git("git", "add", ".", cwd=source)
            self.git("git", "commit", "-m", "initial", cwd=source)
            self.git("git", "push", "-u", "origin", "main", cwd=source)
            release_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=source, text=True,
            ).strip()
            (release / "RELEASE.json").write_text(json.dumps({
                "sha": release_sha, "repo": remote.as_uri(),
            }))
            slug = "legacy-resume"
            markdown = "# Legacy resume\n"
            content_sha = hashlib.sha256(markdown.encode()).hexdigest()
            for name in ("content", "policy", "owned-publications"):
                (state / name).mkdir(parents=True, exist_ok=True)
            artifact = {
                "slug": slug, "state": "READY_FOR_PUBLICATION", "markdown": markdown,
                "content_sha256": content_sha, "disclosure": "affiliate_link",
                "title": "Legacy resume", "built_at": "2026-09-23T00:00:00+00:00",
                "project": "P", "source_hashes": [], "readback_markers": [],
                "readback_links": [],
            }
            (state / "content" / f"{slug}.json").write_text(json.dumps(artifact))
            (state / "policy" / f"{slug}.json").write_text(json.dumps({
                "decision": "PASS", "content_sha256": content_sha,
            }))
            receipt_path = state / "owned-publications" / f"{slug}.json"
            receipt_path.write_text(json.dumps({
                "schema_version": 1, "receipt_type": "OWNED_PUBLICATION",
                "slug": slug, "content_sha256": content_sha, "state": "INTENT",
                "target": f"apps/landing/data/research/{slug}.json",
            }))
            managed = module._managed_publisher_root(
                state, release, "main", f"apps/landing/data/research/{slug}.json",
            )
            target = managed / "apps/landing/data/research" / f"{slug}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(module.public_row(artifact), ensure_ascii=False, indent=2) + "\n")
            self.git("git", "add", str(target.relative_to(managed)), cwd=managed)
            self.git("git", "commit", "-m", f"feat(blog): publish {slug}", cwd=managed)
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=managed, text=True,
            ).strip()
            legacy_action = {
                "content_sha256": content_sha, "commit": commit,
                "remote": "origin", "branch": "main",
                "delivery": "pull_request",
                "head_branch": (
                    f"affiliate/publish-{slug}-{content_sha[:12]}"
                ),
            }
            initial_job = module.start_effect(
                state, "OWNED_GIT_PUSH", slug, legacy_action,
                {"remote": "origin", "branch": "main", "head": release_sha}, 300,
            )
            (source / "README.md").write_text("main advanced\n")
            self.git("git", "add", "README.md", cwd=source)
            self.git("git", "commit", "-m", "advance main", cwd=source)
            self.git("git", "push", "origin", "main", cwd=source)
            pending = {
                "state": "PULL_REQUEST_OPEN", "head_branch": "affiliate/publish-legacy",
                "pull_request_url": "https://github.com/Daisuke134/life-manager/pull/9998",
            }
            delivered = {
                **pending, "state": "DELIVERED", "merge_commit": "e" * 40,
            }
            args = Namespace(
                state=state, landing_root=release, slug=slug,
                base_url="https://example.test", remote="origin", branch="main",
                repository=remote.as_uri(),
            )
            original_atomic_write = module.atomic_write
            crash = {"pending": True}

            def crash_after_verify(path, value):
                if (
                    path == receipt_path
                    and value.get("state") == "DELIVERED"
                    and crash["pending"]
                ):
                    crash["pending"] = False
                    raise OSError("simulated crash after journal verification")
                return original_atomic_write(path, value)

            with patch.object(module, "fetch_readback", return_value=None), patch.object(
                module, "_github_repository", return_value="Daisuke134/life-manager",
            ), patch.object(
                module, "_github_pull_request", side_effect=[pending, delivered, delivered],
            ), patch.object(module, "atomic_write", side_effect=crash_after_verify):
                first = module.publish(args)
                with self.assertRaisesRegex(OSError, "simulated crash"):
                    module.publish(args)
                second = module.publish(args)
            self.assertEqual(first["state"], "PULL_REQUEST_OPEN")
            self.assertEqual(second["state"], "DELIVERED")
            events = [json.loads(line) for line in (state / "job-events.jsonl").read_text().splitlines()]
            self.assertEqual({row["job_id"] for row in events}, {initial_job["job_id"]})
            self.assertEqual(events[-1]["state"], "VERIFIED")
            self.assertEqual(events[-1]["attempt"], 3)
            live = {
                "public_url": "https://example.test/blog/legacy-resume",
                "rendered_sha256": "f" * 64, "observed_at": "now",
                "readback_transport": "test",
            }
            with patch.object(module, "fetch_readback", return_value=live):
                third = module.publish(args)
            self.assertEqual(third["state"], "LIVE")
            self.assertEqual(
                len((state / "job-events.jsonl").read_text().splitlines()), len(events),
            )

    @staticmethod
    def git(*command, cwd=None):
        subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
