import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "model_boundary.py"
CLI = Path(__file__).parents[1] / "x-repost-cli.sh"
MODEL_SCHEMA = Path(__file__).parents[1] / "config" / "model-output.schema.json"
DIGEST_SCRIPT = Path(__file__).parents[1] / "x-repost-digest.sh"


class ModelBoundaryTest(unittest.TestCase):
    def test_shared_model_schema_is_strict_and_covers_each_stage(self) -> None:
        schema = json.loads(MODEL_SCHEMA.read_text())
        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        for field in ("selected", "drafts", "tone", "text", "supported", "five_points"):
            self.assertIn(field, schema["properties"])

    def test_digest_harvest_schema_matches_fact_consumer(self) -> None:
        schema = json.loads(MODEL_SCHEMA.read_text())
        self.assertIn("facts", schema["required"])
        facts = schema["properties"]["facts"]
        self.assertEqual(facts["type"], ["array", "null"])
        item = facts["items"]
        self.assertEqual(item["type"], "object")
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(set(item["required"]), {"fact", "measured_on", "source"})
        self.assertEqual(set(item["required"]), set(item["properties"]))
        properties = item["properties"]
        for field in ("fact", "measured_on", "source"):
            self.assertEqual(properties[field]["type"], "string")
        source = DIGEST_SCRIPT.read_text()
        contracts = (
            '--schema "$MODEL_SCHEMA"',
            '"facts":[{"fact":',
            'facts = data.get("facts") if isinstance(data, dict) else None',
            'if isinstance(facts, list):',
        )
        for contract in contracts:
            self.assertIn(contract, source)
        critic_prompt = CLI.read_text()
        for example in (
            "He probado este paso antes de publicar; si falla, revisa los permisos. = es",
            "Or, cette étape permet de vérifier les droits avant de publier. = fr",
            "He crashed; restart manually, abort on timeout. = en",
        ):
            self.assertIn(example, critic_prompt)

    def run_boundary(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], check=False, text=True,
            capture_output=True,
        )

    def test_prepare_creates_isolated_home_bound_to_requested_auth(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            auth = root_path / "account-2" / "auth.json"
            auth.parent.mkdir()
            auth.write_text(json.dumps({"tokens": {"access_token": "secret"}}))
            automation_home = root_path / "automation"
            result = self.run_boundary(
                "prepare", "--home", str(automation_home), "--auth", str(auth)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), automation_home.resolve())
            self.assertEqual((automation_home / "auth.json").resolve(), auth.resolve())
            self.assertEqual(os.stat(automation_home).st_mode & 0o777, 0o700)

    def test_prepare_rejects_an_existing_different_auth_target(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            expected, wrong = root_path / "account-2.json", root_path / "account-1.json"
            expected.write_text("{}")
            wrong.write_text("{}")
            automation_home = root_path / "automation"
            automation_home.mkdir()
            (automation_home / "auth.json").symlink_to(wrong)
            result = self.run_boundary(
                "prepare", "--home", str(automation_home), "--auth", str(expected)
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("auth target mismatch", result.stderr)
            self.assertEqual((automation_home / "auth.json").resolve(), wrong.resolve())

    def test_classify_reads_usage_limit_from_codex_event_stream(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            stdout = Path(root) / "model.stdout"
            stdout.write_text(json.dumps({
                "type": "error", "message": "You've hit your usage limit. Try again later."
            }))
            result = self.run_boundary("classify", str(stdout))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "quota")

    def test_classify_ignores_limit_words_in_non_error_events(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            stdout = Path(root) / "model.stdout"
            stdout.write_text(json.dumps({
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "Add API rate limit handling."},
            }))
            result = self.run_boundary("classify", str(stdout))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "other")

    def test_classify_preserves_network_failure_even_when_outer_timeout_fires(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            stdout = Path(root) / "model.stdout"
            stdout.write_text(json.dumps({
                "type": "error",
                "message": "failed to lookup address information: nodename nor servname provided",
            }))
            result = self.run_boundary(
                "classify", str(stdout), "--returncode", "124"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "network")

    def test_cli_routes_all_model_calls_through_shared_runner(self) -> None:
        normalized = " ".join(CLI.read_text().split())
        self.assertIn('"$PY" "$AGENT_RUNNER" --task-class composition-agent', normalized)
        self.assertIn('--schema "$MODEL_SCHEMA"', normalized)
        self.assertNotIn('CODEX_HOME=', normalized)
        self.assertNotIn('auth.json', normalized)
        self.assertNotIn(' codex exec ', normalized)
        self.assertIn('2>"$EV/model.err"', normalized)
        self.assertNotIn('2>>"$EV/model.err"', normalized)
        self.assertEqual(normalized.count("handle_model_failure"), 8)

    def test_cli_preserves_working_browser_lease_through_postiz_readback(self) -> None:
        source = CLI.read_text()
        self.assertIn('BROWSER_LEASED=1', source)
        self.assertNotIn('LEASE_HELD=', source)
        self.assertNotIn('CDP=""', source)

    def test_real_shell_boundary_maps_provider_failures_without_publish(self) -> None:
        source = CLI.read_text()
        ask_start = source.index("ask_model() {")
        handle_start = source.index("handle_model_failure() {")
        handle_end = source.index("# Publishing and collection", handle_start)
        functions = source[ask_start:handle_end]
        cases = (
            ("transient_quota", "quota", 0, True),
            ("transient_unavailable", "network", 1, False),
            ("transient_auth", "auth", 1, False),
            ("transient_timeout", "timeout", 1, False),
        )
        for error_class, expected_kind, expected_rc, expected_heartbeat in cases:
            with self.subTest(expected_kind=expected_kind), tempfile.TemporaryDirectory() as root:
                root_path = Path(root)
                fake = root_path / "agent-runner"
                fake.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]; evidence=pathlib.Path(args[args.index('--evidence-dir')+1]); evidence.mkdir(parents=True)
attempts=evidence/'attempts.jsonl'; attempts.write_text(json.dumps({'error_class':os.environ['FAKE_ERROR_CLASS']})+'\\n')
(evidence/'summary.json').write_text(json.dumps({'attempts_path':str(attempts),'result_path':None}))
raise SystemExit(1)
""")
                fake.chmod(0o755)
                prompt = root_path / "prompt.txt"
                prompt.write_text("return json")
                state, evidence = root_path / "state", root_path / "evidence"
                state.mkdir()
                evidence.mkdir()
                values = {
                    "PY": sys.executable, "AGENT_RUNNER": str(fake),
                    "AGENT_RUNNER_CONFIG": str(root_path / "config.json"),
                    "MODEL_SCHEMA": str(CLI.parent / "config/model-output.schema.json"),
                    "LOOP_NAME": "x-repost", "FAKE_ERROR_CLASS": error_class,
                    "SKILL": str(CLI.parent), "EV": str(evidence), "STATE": str(state),
                }
                assignments = "\n".join(
                    f"{key}={shlex.quote(value)}" for key, value in values.items()
                )
                harness = f"""set -uo pipefail
{assignments}
export FAKE_ERROR_CLASS
X_REPOST_MODEL_TIMEOUT=1
MODEL_FAILURE=other
{functions}
report() {{ :; }}
lesson() {{ :; }}
run_x_post() {{ touch {shlex.quote(str(root_path / 'published'))}; }}
finish() {{ rc=$1; [ "$rc" -eq 0 ] && touch "$STATE/.last-pass"; return "$rc"; }}
if ask_model {shlex.quote(str(prompt))} {shlex.quote(str(evidence / 'raw'))} >{shlex.quote(str(evidence / 'json'))}; then exit 42; fi
printf 'kind=%s\\n' "$MODEL_FAILURE"
handle_model_failure step {shlex.quote(str(evidence / 'raw'))}
exit $?
"""
                result = subprocess.run(
                    ["bash", "-c", harness], text=True, capture_output=True, check=False
                )
                self.assertEqual(result.returncode, expected_rc, result.stderr)
                self.assertIn(f"kind={expected_kind}", result.stdout)
                self.assertEqual((state / ".last-pass").exists(), expected_heartbeat)
                self.assertFalse((root_path / "published").exists())


if __name__ == "__main__":
    unittest.main()
