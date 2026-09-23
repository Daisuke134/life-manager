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

            with self.assertRaisesRegex(module.PublishError, "ahead of origin"):
                module._managed_publisher_root(state, release, "main")

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

    @staticmethod
    def git(*command, cwd=None):
        subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
