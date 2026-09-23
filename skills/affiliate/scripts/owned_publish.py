#!/usr/bin/env python3
"""Deliver one immutable Affiliate article to aniccaai.com and read it back."""

import argparse
import hashlib
import html
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from job_journal import (
    JobStateError,
    reconcile_effect,
    resume_effect,
    start_effect,
    unresolved_effect,
    verify_effect,
)
from provider_cli import atomic_write


class PublishError(Exception):
    pass


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        raise PublishError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _is_ancestor(root, ancestor, descendant):
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=root, capture_output=True, check=False, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _gh(root, *args):
    executable = shutil.which("gh")
    if not executable:
        raise PublishError("GitHub CLI is unavailable")
    try:
        result = subprocess.run(
            [executable, *args], cwd=root, text=True, capture_output=True,
            check=False, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PublishError("GitHub CLI failed") from error
    if result.returncode:
        raise PublishError(result.stderr.strip() or result.stdout.strip() or "GitHub CLI failed")
    return result.stdout.strip()


def _github_repository(remote_url):
    parsed = urlsplit(remote_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
        return None
    return path


def _publication_repository(remote_url):
    repository = _github_repository(remote_url)
    if repository:
        return repository
    parsed = urlsplit(remote_url)
    local_file_url = (
        parsed.scheme == "file"
        and parsed.hostname in {None, ""}
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and parsed.path.startswith("/")
    )
    local_path = not parsed.scheme and Path(remote_url).is_absolute()
    if local_file_url or local_path:
        return None
    raise PublishError("unsupported publisher remote")


def _action_fingerprint(action):
    encoded = json.dumps(action, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _publication_effect(state, slug, action, legacy_action, last_verified):
    pending = unresolved_effect(state, "OWNED_GIT_PUSH", slug)
    allowed = {_action_fingerprint(action), _action_fingerprint(legacy_action)}
    if pending is not None:
        observed = pending.get("action_fingerprint")
        prior = pending.get("last_verified_external_object")
        if (
            observed not in allowed
            or not isinstance(prior, dict)
            or prior.get("remote") != last_verified.get("remote")
            or prior.get("branch") != last_verified.get("branch")
        ):
            raise PublishError("unresolved publication effect does not match current action")
        resumed = resume_effect(state, "OWNED_GIT_PUSH", slug)
        if resumed is None or resumed.get("job_id") != pending.get("job_id"):
            raise PublishError("unresolved publication effect changed during resume")
        return resumed
    actions = {_action_fingerprint(item): item for item in (action, legacy_action)}
    verified = []
    jobs = state.expanduser() / "jobs"
    for fingerprint, expected in actions.items():
        job_key = hashlib.sha256(
            f"OWNED_GIT_PUSH\0{slug}\0{fingerprint}".encode()
        ).hexdigest()
        path = jobs / f"key-{job_key}.json"
        if not path.is_file():
            continue
        row = json.loads(path.read_text(encoding="utf-8"))
        external = row.get("last_verified_external_object")
        if (
            row.get("state") != "VERIFIED"
            or row.get("kind") != "OWNED_GIT_PUSH"
            or row.get("target") != slug
            or row.get("job_key") != job_key
            or row.get("action_fingerprint") != fingerprint
            or not isinstance(external, dict)
            or external.get("state") != "DELIVERED"
            or external.get("remote") != expected.get("remote")
            or external.get("branch") != expected.get("branch")
            or external.get("head") != expected.get("commit")
        ):
            raise PublishError("verified publication effect does not match current action")
        verified.append(row)
    if len(verified) > 1:
        raise PublishError("multiple verified publication effects match current action")
    if verified:
        return verified[0]
    return start_effect(
        state, "OWNED_GIT_PUSH", slug, action, last_verified, 300,
    )


def _pull_request_view(root, repository, pull_request):
    fields = "autoMergeRequest,baseRefName,headRefOid,mergeCommit,state,url"
    try:
        row = json.loads(_gh(
            root, "pr", "view", pull_request, "--repo", repository,
            "--json", fields,
        ))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise PublishError("GitHub pull request readback is invalid") from error
    if not isinstance(row, dict):
        raise PublishError("GitHub pull request readback is invalid")
    return row


def _github_pull_request(
    *, root, repository, remote, target_branch, head_branch, commit, slug,
):
    fields = "autoMergeRequest,baseRefName,headRefOid,mergeCommit,state,url"
    try:
        rows = json.loads(_gh(
            root, "pr", "list", "--repo", repository, "--head", head_branch,
            "--state", "all", "--limit", "10", "--json", fields,
        ))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise PublishError("GitHub pull request list readback is invalid") from error
    if not isinstance(rows, list):
        raise PublishError("GitHub pull request list readback is invalid")
    matches = [
        row for row in rows
        if row.get("baseRefName") == target_branch and row.get("headRefOid") == commit
    ]
    if len(matches) > 1:
        raise PublishError("multiple GitHub pull requests match publication")
    if matches:
        pull_request = matches[0].get("url")
    else:
        git(root, "push", remote, f"{commit}:refs/heads/{head_branch}")
        pull_request = _gh(
            root, "pr", "create", "--repo", repository, "--base", target_branch,
            "--head", head_branch, "--title", f"feat(blog): publish {slug}",
            "--body", "Automated Affiliate publication after policy and quality gates passed.",
        ).strip()
    if not isinstance(pull_request, str) or not re.fullmatch(
        rf"{re.escape(f'https://github.com/{repository}/pull/')}[1-9][0-9]*",
        pull_request,
    ):
        raise PublishError("GitHub pull request URL is invalid")
    row = _pull_request_view(root, repository, pull_request)
    if row.get("baseRefName") != target_branch or row.get("headRefOid") != commit:
        raise PublishError("GitHub pull request identity does not match publication")
    if row.get("state") == "OPEN" and row.get("autoMergeRequest") is None:
        _gh(
            root, "pr", "merge", pull_request, "--repo", repository,
            "--auto", "--merge", "--delete-branch", "--match-head-commit", commit,
        )
        row = _pull_request_view(root, repository, pull_request)
    if row.get("state") == "OPEN":
        return {
            "state": "PULL_REQUEST_OPEN", "head_branch": head_branch,
            "pull_request_url": pull_request,
        }
    if row.get("state") != "MERGED" or not isinstance(row.get("mergeCommit"), dict):
        raise PublishError("GitHub pull request closed without merge")
    merge_commit = row["mergeCommit"].get("oid")
    if not isinstance(merge_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", merge_commit):
        raise PublishError("GitHub merge commit readback is invalid")
    git(root, "fetch", "--no-tags", remote, target_branch)
    git(root, "merge-base", "--is-ancestor", commit, merge_commit)
    git(root, "merge-base", "--is-ancestor", merge_commit, "FETCH_HEAD")
    return {
        "state": "DELIVERED", "head_branch": head_branch,
        "pull_request_url": pull_request,
        "merge_commit": merge_commit,
    }


def _is_single_publication_commit(root, base, head, allowed_path, dirty):
    if dirty or not allowed_path:
        return False
    changed = git(root, "diff", "--name-only", f"{base}..{head}").splitlines()
    count = git(root, "rev-list", "--count", f"{base}..{head}")
    return changed == [allowed_path] and count == "1"


def _managed_publisher_root(state, release_root, branch, allowed_ahead_path=None):
    try:
        metadata = json.loads((release_root / "RELEASE.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise PublishError("managed publisher release metadata is unavailable") from error
    repo = metadata.get("repo")
    release_sha = metadata.get("sha")
    parsed = urlsplit(repo) if isinstance(repo, str) else None
    if (
        not isinstance(release_sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", release_sha)
        or parsed is None
        or parsed.scheme not in {"https", "file"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "https" and not parsed.hostname)
        or (parsed.scheme == "file" and not parsed.path.startswith("/"))
    ):
        raise PublishError("managed publisher release metadata is invalid")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    configured_root = state / "publisher-checkout"
    if configured_root.is_symlink():
        raise PublishError("managed publisher checkout must not be a symlink")
    root = configured_root.resolve()
    if not root.exists():
        temporary = state / f".publisher-checkout.{os.getpid()}.tmp"
        if temporary.exists():
            raise PublishError("managed publisher checkout staging path exists")
        try:
            result = subprocess.run(
                [
                    "git", "clone", "--filter=blob:none", "--no-tags",
                    "--single-branch", "--branch", branch, "--sparse", repo,
                    str(temporary),
                ],
                text=True, capture_output=True, check=False, timeout=180,
            )
            if result.returncode:
                raise PublishError(result.stderr.strip() or "managed publisher clone failed")
            git(temporary, "sparse-checkout", "set", "apps/landing/data/research")
            os.replace(temporary, root)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if git(root, "rev-parse", "--show-toplevel") != str(root):
        raise PublishError("managed publisher checkout is not the exact git worktree")
    if git(root, "remote", "get-url", "origin") != repo:
        raise PublishError("managed publisher remote does not match the release")
    push_urls = git(root, "remote", "get-url", "--push", "--all", "origin").splitlines()
    if push_urls != [repo]:
        raise PublishError("managed publisher push remote does not match the release")
    if git(root, "branch", "--show-current") != branch:
        raise PublishError("managed publisher branch does not match")
    dirty = git(root, "status", "--porcelain", "--untracked-files=all")
    git(root, "fetch", "--no-tags", "origin", branch)
    local_head = git(root, "rev-parse", "HEAD")
    remote_head = git(root, "rev-parse", "FETCH_HEAD")
    release_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", release_sha, remote_head],
        cwd=root, capture_output=True, check=False, timeout=15,
    )
    if release_ancestor.returncode != 0:
        raise PublishError("managed publisher origin does not contain the release")
    if local_head != remote_head:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", local_head, remote_head],
            cwd=root, capture_output=True, check=False, timeout=15,
        )
        if ancestor.returncode == 0:
            if dirty:
                raise PublishError("managed publisher checkout is dirty while origin advanced")
            git(root, "merge", "--ff-only", remote_head)
        else:
            remote_ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", remote_head, local_head],
                cwd=root, capture_output=True, check=False, timeout=15,
            )
            if remote_ancestor.returncode == 0:
                if _is_single_publication_commit(
                    root, remote_head, local_head, allowed_ahead_path, dirty,
                ):
                    return root
                raise PublishError("managed publisher checkout is ahead of origin")
            merge_base = git(root, "merge-base", remote_head, local_head)
            if _is_single_publication_commit(
                root, merge_base, local_head, allowed_ahead_path, dirty,
            ):
                return root
            raise PublishError("managed publisher checkout diverged from origin")
    return root


def load_artifact(state, slug):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,100}", slug):
        raise PublishError("invalid article slug")
    path = state / "content" / f"{slug}.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PublishError("article artifact is unavailable") from error
    if artifact.get("slug") != slug or artifact.get("state") != "READY_FOR_PUBLICATION":
        raise PublishError("article artifact is not publishable")
    markdown = artifact.get("markdown", "")
    if hashlib.sha256(markdown.encode()).hexdigest() != artifact.get("content_sha256"):
        raise PublishError("article artifact hash mismatch")
    if artifact.get("disclosure") == "affiliate_link":
        try:
            policy = json.loads((state / "policy" / f"{slug}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise PublishError("affiliate article policy receipt is unavailable") from error
        if policy.get("decision") != "PASS" or policy.get("content_sha256") != artifact.get("content_sha256"):
            raise PublishError("affiliate article policy receipt does not match")
    return artifact


def public_row(artifact):
    markdown = artifact["markdown"]
    published_date = datetime.fromisoformat(artifact["built_at"]).date().isoformat()
    return {
        "slug": artifact["slug"],
        "title": artifact["title"],
        "date": published_date,
        "project": artifact.get("project", "AI VOICE EVALUATION"),
        "n_papers_cited": len(artifact["source_hashes"]),
        "word_count": len(re.findall(r"\b[\w'-]+\b", markdown)),
        "markdown": markdown,
        "mirrors": {},
    }


def _read_public_markup(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Life-Manager-Affiliate/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return response.read(), "urllib"
    except Exception:
        pass
    parsed = urlsplit(url)
    curl = shutil.which("curl")
    dig = shutil.which("dig")
    if parsed.scheme != "https" or not parsed.hostname or not curl or not dig:
        return None, None
    try:
        port = parsed.port or 443
        resolved = subprocess.run(
            [dig, "+short", "@1.1.1.1", parsed.hostname, "A"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, None
    for candidate in resolved.stdout.splitlines():
        candidate = candidate.strip()
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        try:
            result = subprocess.run(
                [
                    curl, "--fail", "--silent", "--show-error", "--location",
                    "--max-time", "12", "--connect-timeout", "5", "--proto",
                    "=https", "--resolve", f"{parsed.hostname}:{port}:{candidate}",
                    "-A", "Life-Manager-Affiliate/1.0", url,
                ],
                capture_output=True, timeout=20, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return result.stdout, "curl-resolved"
    return None, None


def fetch_readback(artifact, base_url):
    url = f"{base_url.rstrip('/')}/blog/{artifact['slug']}"
    markup, transport = _read_public_markup(url)
    if markup is None:
        return None
    try:
        markup = markup.decode("utf-8")
    except UnicodeDecodeError:
        return None
    visible = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    decoded_markup = html.unescape(markup)
    expected_links = []
    for link in artifact.get("readback_links", []):
        parsed = urlsplit(link)
        placement = parsed.path.strip("/")
        if (
            parsed.scheme == "https"
            and parsed.hostname == "try.elevenlabs.io"
            and not parsed.query
            and not parsed.fragment
            and re.fullmatch(r"[a-z0-9][a-z0-9-]{2,100}", placement)
        ):
            expected_links.append(f"/go/af_{placement}")
        else:
            expected_links.append(link)
    if (
        artifact["title"] not in visible
        or any(marker not in visible for marker in artifact["readback_markers"])
        or any(link not in decoded_markup for link in expected_links)
    ):
        return None
    return {
        "public_url": url,
        "rendered_sha256": hashlib.sha256(markup.encode()).hexdigest(),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "readback_transport": transport,
    }


def publish(args):
    state = args.state.expanduser()
    root = args.landing_root.resolve()
    artifact = load_artifact(state, args.slug)
    target_relative = f"apps/landing/data/research/{args.slug}.json"
    receipt_path = state / "owned-publications" / f"{args.slug}.json"
    receipt = {}
    revision = False
    prior_content_sha256 = None
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("content_sha256") != artifact["content_sha256"]:
            if receipt.get("state") != "LIVE":
                raise PublishError("publication receipt conflicts with artifact")
            revision = True
            prior_content_sha256 = receipt.get("content_sha256")
        else:
            live = fetch_readback(artifact, args.base_url)
            if live:
                reconcile_effect(state, "OWNED_GIT_PUSH", args.slug, {
                    "state": "LIVE", "public_url": live["public_url"],
                    "rendered_sha256": live["rendered_sha256"],
                })
                receipt.update(state="LIVE", **live)
                atomic_write(receipt_path, receipt)
                return receipt
    if not (root / ".git").exists() and (root / "RELEASE.json").is_file():
        if args.remote != "origin":
            raise PublishError("managed publisher remote must be origin")
        root = _managed_publisher_root(state, root, args.branch, target_relative)
    if git(root, "rev-parse", "--show-toplevel") != str(root):
        raise PublishError("landing root is not the exact git worktree")
    target = root / target_relative
    expected = json.dumps(public_row(artifact), ensure_ascii=False, indent=2) + "\n"
    dirty = {line[3:] for line in git(root, "status", "--porcelain", "--untracked-files=all").splitlines() if len(line) >= 4}
    if dirty and dirty != {target_relative}:
        raise PublishError("landing worktree has unrelated changes")
    if target.exists() and target.read_text(encoding="utf-8") != expected:
        try:
            current = json.loads(target.read_text(encoding="utf-8"))
        except ValueError as error:
            raise PublishError("public slug conflicts with different content") from error
        current_sha256 = hashlib.sha256(str(current.get("markdown", "")).encode()).hexdigest()
        if not revision or current.get("slug") != args.slug or current_sha256 != prior_content_sha256:
            raise PublishError("public slug conflicts with different content")
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary.write_text(expected, encoding="utf-8")
        os.replace(temporary, target)
    elif not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary.write_text(expected, encoding="utf-8")
        os.replace(temporary, target)
    if revision:
        receipt.update(
            content_sha256=artifact["content_sha256"], state="INTENT",
            prior_content_sha256=prior_content_sha256,
            revised_at=datetime.now(timezone.utc).isoformat(),
        )
        atomic_write(receipt_path, receipt)
    elif not receipt:
        receipt = {
            "schema_version": 1,
            "receipt_type": "OWNED_PUBLICATION",
            "slug": args.slug,
            "content_sha256": artifact["content_sha256"],
            "state": "INTENT",
            "target": target_relative,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_write(receipt_path, receipt)
    if git(root, "status", "--porcelain", "--", target_relative):
        git(root, "add", "--", target_relative)
        if git(root, "diff", "--cached", "--name-only") != target_relative:
            raise PublishError("git index contains a non-publication target")
        git(root, "commit", "-m", f"feat(blog): publish {args.slug}")
    current_head = git(root, "rev-parse", "HEAD")
    recorded_commit = receipt.get("commit")
    if receipt.get("state") == "DELIVERED":
        if (
            isinstance(recorded_commit, str)
            and re.fullmatch(r"[0-9a-f]{40}", recorded_commit)
            and _is_ancestor(root, recorded_commit, current_head)
        ):
            return receipt
        raise PublishError("delivered publication commit is absent from target branch")
    if receipt.get("state") == "PULL_REQUEST_OPEN":
        if not isinstance(recorded_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", recorded_commit):
            raise PublishError("publication pull request receipt has invalid commit")
        git(root, "rev-parse", f"{recorded_commit}^{{commit}}")
        commit = recorded_commit
    else:
        commit = current_head
    ref = f"refs/heads/{args.branch}"
    remote_row = git(root, "ls-remote", args.remote, ref)
    remote_head = remote_row.split()[0] if remote_row else None
    remote_url = git(root, "remote", "get-url", args.remote)
    repository = _publication_repository(remote_url)
    head_branch = None
    if repository:
        head_branch = f"affiliate/publish-{args.slug}-{artifact['content_sha256'][:12]}"
    legacy_action = {
        "content_sha256": artifact["content_sha256"], "commit": commit,
        "remote": args.remote, "branch": args.branch,
    }
    action = dict(legacy_action)
    if head_branch:
        action.update(delivery="pull_request", head_branch=head_branch)
    job = _publication_effect(
        state, args.slug, action, legacy_action,
        {"remote": args.remote, "branch": args.branch, "head": remote_head},
    )
    if repository:
        delivery = _github_pull_request(
            root=root, repository=repository, remote=args.remote,
            target_branch=args.branch, head_branch=head_branch, commit=commit,
            slug=args.slug,
        )
    else:
        git(root, "push", args.remote, f"{commit}:refs/heads/{args.branch}")
        delivery = {"state": "DELIVERED"}
    receipt.update(
        state=delivery["state"], commit=commit, remote=args.remote,
        branch=args.branch,
    )
    for key in ("head_branch", "pull_request_url", "merge_commit"):
        if delivery.get(key):
            receipt[key] = delivery[key]
    if delivery["state"] != "DELIVERED":
        if job.get("state") == "VERIFIED":
            raise PublishError("verified publication effect is not confirmed by provider")
        atomic_write(receipt_path, receipt)
        return receipt
    if job.get("state") == "EFFECT_STARTED":
        verify_effect(state, job["job_id"], {
            "state": "DELIVERED", "remote": args.remote, "branch": args.branch,
            "head": commit, **{
                key: delivery[key] for key in ("head_branch", "pull_request_url", "merge_commit")
                if delivery.get(key)
            },
        })
    elif job.get("state") != "VERIFIED":
        raise PublishError("publication effect has invalid terminal state")
    atomic_write(receipt_path, receipt)
    live = fetch_readback(artifact, args.base_url)
    if live:
        receipt.update(state="LIVE", **live)
        atomic_write(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(prog="affiliate owned")
    parser.add_argument("command", choices=("publish",))
    parser.add_argument("--slug", required=True)
    parser.add_argument("--landing-root", type=Path, required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--base-url", default="https://aniccaai.com")
    parser.add_argument("--state", type=Path, default=Path("~/.local/state/life-manager/affiliate"))
    args = parser.parse_args()
    result = publish(args)
    print(json.dumps({key: result.get(key) for key in ("slug", "state", "commit", "public_url", "rendered_sha256")}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PublishError, JobStateError, OSError, ValueError, KeyError, json.JSONDecodeError):
        print("affiliate owned: failed closed", file=sys.stderr)
        raise SystemExit(1)
