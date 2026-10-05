from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/x-repost/scripts/affiliate_proposal.py"
CLI = ROOT / "skills/x-repost/x-repost-cli.sh"


def valid_job() -> dict:
    return {
        "schema_version": 1,
        "receipt_type": "AFFILIATE_X_DISTRIBUTION_JOB",
        "state": "QUEUED",
        "job_id": "1" * 64,
        "effect_identity": "2" * 64,
        "placement_id": "caption-en-1",
        "owned_article_url": "https://aniccaai.com/blog/caption",
        "content_sha256": "3" * 64,
        "experiment_lineage": {"kind": "BASE", "decision_id": None,
                               "control_placement_id": None},
        "target_x_account": "selawmqt",
        "cadence_class": "AFFILIATE_MONETIZATION",
        "policy_sha256": "4" * 64,
        "source_set_sha256": "5" * 64,
        "created_at": "2026-08-24T00:00:00+00:00",
        "private_tracking_url_state": "NOT_INCLUDED",
        "revenue_credit_state": "NO_REVENUE_CREDIT",
    }


def cli(*args: str, disable: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if disable:
        env["X_REPOST_DISABLE_AFFILIATE"] = "1"
    else:
        env.pop("X_REPOST_DISABLE_AFFILIATE", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, check=False, env=env,
    )


def prepare_unverified_distribution(state: Path, *, quote: bool = True) -> dict[str, Path]:
    state.mkdir(parents=True, exist_ok=True)
    queue = state / "jobs.jsonl"
    claims = state / "affiliate-x-distribution-job-claims.jsonl"
    payloads = state / "affiliate-x-distribution-payloads"
    results = state / "affiliate-x-distribution-job-results.jsonl"
    payloads.mkdir()

    job = valid_job()
    job["job_id"] = "6" * 64
    job["effect_identity"] = "7" * 64
    job["content_sha256"] = "8" * 64
    if quote:
        job.update({
            "distribution_mode": "QUOTE_CONTROL_POST",
            "control_post_url": "https://x.com/selawmqt/status/999",
        })
    next_job = valid_job()
    next_job.update({
        "job_id": "9" * 64,
        "effect_identity": "a" * 64,
        "content_sha256": "b" * 64,
        "created_at": "2026-08-25T00:00:00+00:00",
    })
    queue.write_text(
        json.dumps(job) + "\n" + json.dumps(next_job) + "\n", encoding="utf-8"
    )

    claimed = cli(
        "--job-queue", str(queue), "--job-claims", str(claims),
        "--job-results", str(results), "--claim-next-job", disable=False,
    )
    if claimed.returncode != 0:
        raise AssertionError(claimed.stderr)
    copy_args: tuple[str, ...] = ()
    if quote:
        copy = state / "copy.json"
        copy.write_text(json.dumps({
            "text": "Compare the workflow fit before committing to another recurring publishing tool.",
            "claims": [],
        }), encoding="utf-8")
        copy_args = ("--job-copy", str(copy))
    rendered = cli(
        "--job-claims", str(claims), "--job-payload-dir", str(payloads),
        *copy_args, "--render-claimed-job", disable=False,
    )
    if rendered.returncode != 0:
        raise AssertionError(rendered.stderr)
    effect = cli(
        "--job-claims", str(claims), "--job-payload-dir", str(payloads),
        "--job-results", str(results), "--job-effect-state", disable=False,
    )
    if effect.returncode != 0:
        raise AssertionError(effect.stderr)
    (state / "effect.json").write_text(effect.stdout, encoding="utf-8")
    return {
        "queue": queue, "claims": claims, "payloads": payloads, "results": results,
        "effect": state / "effect.json",
    }


def run_disabled_pass(
    root: Path, state: Path, paths: dict[str, Path], *,
    post_json: dict | None = None, post_rc: int = 0,
    first_browser_unavailable: bool = False,
) -> subprocess.CompletedProcess[str]:
    repo = root / "fake-repo"
    (repo / "skills").mkdir(parents=True)
    (repo / "lib").mkdir()
    (repo / "skills/x-repost").symlink_to(CLI.parent, target_is_directory=True)
    (repo / "lib/registry-enforce.sh").write_text(
        "registry_enforce_or_exit() { return 0; }\n", encoding="utf-8"
    )
    (repo / "skills/browser").mkdir()
    calls_file = root / "browser-calls"
    ensure = repo / "skills/browser/ensure_provision_browser.sh"
    ensure.write_text(
        "#!/usr/bin/env bash\n"
        f"calls_file={json.dumps(str(calls_file))}\n"
        "calls=0; [ ! -f \"$calls_file\" ] || read -r calls <\"$calls_file\"\n"
        "calls=$((calls + 1)); printf '%s\\n' \"$calls\" >\"$calls_file\"\n"
        "if [ \"${X_REPOST_TEST_FIRST_BROWSER_UNAVAILABLE:-0}\" = 1 ] && [ \"$calls\" -eq 1 ]; then\n"
        "  echo unavailable; exit 1\n"
        "fi\n"
        "echo http://cdp.test\n",
        encoding="utf-8",
    )
    ensure.chmod(0o755)

    guard = root / "browser-guard.sh"
    guard.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    guard.chmod(0o755)
    env_file = root / "empty.env"
    env_file.write_text("", encoding="utf-8")
    candidates = root / "candidates.json"
    candidates.write_text('{"candidates": []}\n', encoding="utf-8")

    trace = root / "affiliate-cli.jsonl"
    site_packages = root / "python-test-hooks"
    (site_packages / "playwright").mkdir(parents=True)
    (site_packages / "playwright/__init__.py").write_text("", encoding="utf-8")
    (site_packages / "sitecustomize.py").write_text(
        "import json, os, sys\n"
        "if sys.argv and sys.argv[0].endswith('affiliate_proposal.py'):\n"
        "    with open(os.environ['X_REPOST_TEST_AFFILIATE_TRACE'], 'a', encoding='utf-8') as stream:\n"
        "        stream.write(json.dumps(sys.argv[1:]) + '\\n')\n",
        encoding="utf-8",
    )
    bash_env = root / "bash-env.sh"
    bash_env.write_text(
        "timeout() {\n"
        "  local seconds=\"$1\"; shift; local python=\"$1\"; shift; local script=\"$1\"; shift\n"
        "  if [[ \"$script\" == */x_post.py ]]; then\n"
        "    printf '%s\\n' \"$*\" >>\"$X_REPOST_TEST_POST_TRACE\"\n"
        "    printf '%s\\n' \"$X_REPOST_TEST_POST_JSON\"\n"
        "    return \"$X_REPOST_TEST_POST_RC\"\n"
        "  fi\n"
        "  command timeout \"$seconds\" \"$python\" \"$script\" \"$@\"\n"
        "}\n",
        encoding="utf-8",
    )

    post_trace = root / "x-post-args.log"
    env = os.environ.copy()
    env.update({
        "HOME": str(root / "home"),
        "LIFE_MANAGER_ENV_FILE": str(env_file),
        "X_REPOST_STATE_DIR": str(state),
        "X_REPOST_CANDIDATES_FILE": str(candidates),
        "X_REPOST_DISABLE_AFFILIATE": "1",
        "X_REPOST_TEST_FIRST_BROWSER_UNAVAILABLE": "1" if first_browser_unavailable else "0",
        "X_REPOST_TEST_POST_JSON": json.dumps(post_json or {"posted": False}),
        "X_REPOST_TEST_POST_RC": str(post_rc),
        "X_REPOST_TEST_POST_TRACE": str(post_trace),
        "X_REPOST_TEST_AFFILIATE_TRACE": str(trace),
        "AFFILIATE_X_DISTRIBUTION_QUEUE": str(paths["queue"]),
        "AFFILIATE_REPOST_PROPOSAL_PATH": str(root / "no-proposal.json"),
        "AI_BROWSER_GUARD": str(guard),
        "TWITTER_AUTH_TOKEN": "fixture-only",
        "BASH_ENV": str(bash_env),
        "PYTHONPATH": str(site_packages),
    })
    result = subprocess.run(
        ["bash", str(repo / "skills/x-repost/x-repost-cli.sh")],
        cwd=repo, capture_output=True, text=True, check=False, env=env, timeout=30,
    )
    return result


class XRepostAffiliateDisableTests(unittest.TestCase):
    def test_disabled_mode_does_not_claim_a_queued_affiliate_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "jobs.jsonl"
            claims = root / "claims.jsonl"
            results = root / "results.jsonl"
            queue.write_text(json.dumps(valid_job()) + "\n", encoding="utf-8")

            result = cli(
                "--job-queue", str(queue), "--job-claims", str(claims),
                "--job-results", str(results), "--claim-next-job",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {
                "state": "AFFILIATE_DISABLED", "changed": False,
            })
            self.assertFalse(claims.exists())

    def test_disabled_mode_does_not_requeue_a_no_effect_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / "results.jsonl"
            row = {
                "schema_version": 1,
                "receipt_type": "X_REPOST_DISTRIBUTION_JOB_RESULT",
                "state": "NO_EFFECT",
                "job_id": "1" * 64,
                "effect_identity": "2" * 64,
                "placement_id": "caption-en-1",
                "content_sha256": "3" * 64,
                "text_sha256": "4" * 64,
                "post_url": None,
                "provider": "postiz",
                "provider_submission_id": "postiz-1",
                "owner_label": "ai.anicca.x-repost-pass",
                "observed_at": "2026-08-24T00:00:00+00:00",
            }
            original = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            results.write_text(original, encoding="utf-8")

            result = cli(
                "--job-results", str(results), "--job-id", row["job_id"],
                "--requeue-no-effect",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {
                "state": "AFFILIATE_DISABLED", "changed": False,
            })
            self.assertEqual(results.read_text(encoding="utf-8"), original)

    def test_disabled_mode_only_allows_posted_result_recovery_with_a_complete_receipt(self) -> None:
        result = cli("--record-job-result", "POSTED")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "state": "AFFILIATE_DISABLED", "changed": False,
        })

    def test_disabled_unverified_readback_preserves_ledger_and_reaches_ordinary_recon(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            paths = prepare_unverified_distribution(state)
            recorded = cli(
                "--job-claims", str(paths["claims"]),
                "--job-payload-dir", str(paths["payloads"]),
                "--job-results", str(paths["results"]),
                "--record-job-result", "UNVERIFIED",
                "--provider-submission-id", "postiz-prior-1", disable=False,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            state.mkdir(exist_ok=True)
            posted = state / "posted.jsonl"
            posted.write_text("", encoding="utf-8")
            before = {
                key: paths[key].read_bytes()
                for key in ("queue", "claims", "results")
            }
            before["posted"] = posted.read_bytes()
            result = run_disabled_pass(
                root, state, paths,
                post_json={
                    "posted": True,
                    "post_url": "https://x.com/selawmqt/status/12345",
                    "source_url": "https://x.com/selawmqt/status/999",
                    "provider_submission_id": "postiz-prior-1",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("collected 0 candidates", result.stdout)
            self.assertEqual((state / "posted.jsonl").read_bytes(), before["posted"])
            for key in ("queue", "claims", "results"):
                self.assertEqual(paths[key].read_bytes(), before[key], key)
            evidence_dirs = list((state / "evidence").iterdir())
            self.assertEqual(len(evidence_dirs), 1)
            self.assertEqual(
                json.loads((evidence_dirs[0] / "candidates.json").read_text()),
                {"candidates": [], "candidate_count": 0},
            )

            post_trace = root / "x-post-args.log"
            post_calls = post_trace.read_text().splitlines() if post_trace.exists() else []
            self.assertEqual(len(post_calls), 1)
            self.assertIn("--mode reconcile", post_calls[0])
            self.assertIn("https://x.com/selawmqt/status/999", post_calls[0])
            self.assertNotIn("--mode original", post_calls[0])
            calls = [
                json.loads(line)
                for line in (
                    (root / "affiliate-cli.jsonl").read_text().splitlines()
                    if (root / "affiliate-cli.jsonl").exists() else []
                )
            ]
            self.assertEqual(len(calls), 1)
            self.assertIn("--job-effect-state", calls[0])
            for forbidden in (
                "--claim-next-job", "--render-claimed-job", "--requeue-no-effect",
                "--record-job-result", "--proposal", "--claim", "--render",
            ):
                self.assertNotIn(forbidden, calls[0])
            browser_calls = root / "browser-calls"
            self.assertEqual(
                browser_calls.read_text().splitlines() if browser_calls.exists() else [], ["2"]
            )

    def test_disabled_unverified_browser_unavailable_keeps_state_and_ordinary_recon_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            paths = prepare_unverified_distribution(state)
            recorded = cli(
                "--job-claims", str(paths["claims"]),
                "--job-payload-dir", str(paths["payloads"]),
                "--job-results", str(paths["results"]),
                "--record-job-result", "UNVERIFIED",
                "--provider-submission-id", "postiz-prior-1", disable=False,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            posted = state / "posted.jsonl"
            posted.write_text("", encoding="utf-8")
            original_result = paths["results"].read_bytes()
            result = run_disabled_pass(
                root, state, paths, first_browser_unavailable=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("collected 0 candidates", result.stdout)
            self.assertEqual(paths["results"].read_bytes(), original_result)
            self.assertEqual((state / "posted.jsonl").read_bytes(), b"")
            self.assertFalse((root / "x-post-args.log").exists())
            browser_calls = root / "browser-calls"
            self.assertEqual(
                browser_calls.read_text().splitlines() if browser_calls.exists() else [], ["2"]
            )
            self.assertIn("Affiliate readback browser unavailable", result.stdout)

    def test_disabled_mode_recovers_exact_prior_posted_receipt_without_reposting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            paths = prepare_unverified_distribution(state)
            recovery_evidence = state / "evidence/20261004T000000"
            recovery_evidence.mkdir(parents=True)
            (recovery_evidence / "affiliate-job-effect.json").write_bytes(
                paths["effect"].read_bytes()
            )
            (recovery_evidence / "affiliate-job-post.json").write_text(json.dumps({
                "posted": True,
                "post_url": "https://x.com/selawmqt/status/67890",
                "provider_submission_id": "postiz-accepted-exact-1",
            }), encoding="utf-8")
            posted = state / "posted.jsonl"
            posted.write_text("", encoding="utf-8")
            result = run_disabled_pass(root, state, paths)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            rows = [
                json.loads(line)
                for line in paths["results"].read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(rows[-1]["state"], "POSTED")
            self.assertEqual(rows[-1]["post_url"], "https://x.com/selawmqt/status/67890")
            posted_rows = [
                json.loads(line)
                for line in posted.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(posted_rows), 1)
            self.assertEqual(posted_rows[0]["provider_submission_id"], "postiz-accepted-exact-1")
            self.assertFalse((root / "x-post-args.log").exists())
            calls = [
                json.loads(line)
                for line in (
                    (root / "affiliate-cli.jsonl").read_text().splitlines()
                    if (root / "affiliate-cli.jsonl").exists() else []
                )
            ]
            posted_recovery = [
                call for call in calls
                if "--record-job-result" in call and "POSTED" in call
            ]
            self.assertEqual(len(posted_recovery), 1)


if __name__ == "__main__":
    unittest.main()
