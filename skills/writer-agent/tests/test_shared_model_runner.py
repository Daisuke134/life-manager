import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "runtime/shared-model-runner.py"
LEGACY_ENTRY = ROOT / "runtime/model-runner.sh"


class SharedModelRunnerTest(unittest.TestCase):
    def test_judge_preserves_legacy_stdout_through_canonical_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "agent-runner.py"
            fake.write_text("""#!/usr/bin/env python3
import json,pathlib,sys
a=sys.argv[1:]; e=pathlib.Path(a[a.index('--evidence-dir')+1]); e.mkdir(parents=True)
r=e/'result.json'; r.write_text('{"classification":"ACCEPTED"}')
(e/'summary.json').write_text(json.dumps({'result_path':str(r)}))
""")
            fake.chmod(0o755)
            prompt = root / "prompt.txt"; prompt.write_text("classify this message")
            env = {**os.environ, "AGENT_RUNNER_BIN": str(fake),
                   "WRITER_SHARED_RUNNER_STATE": str(root / "state")}
            result = subprocess.run(
                [sys.executable, str(ADAPTER), "judge", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"classification": "ACCEPTED"})

    def test_judge_uses_the_writer_judge_class_that_waits_on_the_second_account(self):
        # 2026-10-23 run 20261023-053932: the Writer agent held acct1 while every identity and
        # conscience judge failed fast with codex_home_busy, so three articles stayed pending.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "agent-runner.py"
            fake.write_text("""#!/usr/bin/env python3
import json,pathlib,sys
a=sys.argv[1:]; e=pathlib.Path(a[a.index('--evidence-dir')+1]); e.mkdir(parents=True)
pathlib.Path(sys.argv[0]).with_name('task-class').write_text(a[a.index('--task-class')+1])
r=e/'result.json'; r.write_text('{"verdict":"PASS"}')
(e/'summary.json').write_text(json.dumps({'result_path':str(r)}))
""")
            fake.chmod(0o755)
            prompt = root / "prompt.txt"; prompt.write_text("judge this")
            env = {**os.environ, "AGENT_RUNNER_BIN": str(fake),
                   "WRITER_SHARED_RUNNER_STATE": str(root / "state")}
            result = subprocess.run(
                [sys.executable, str(ADAPTER), "judge", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "task-class").read_text(), "writer-judge-agent")
        config = json.loads((ROOT.parents[1] / "runtime/agent-runner/config.json").read_text())
        candidates = config["task_classes"]["writer-judge-agent"]["candidates"]
        self.assertEqual([c["profile_alias"] for c in candidates], ["acct2"])
        self.assertFalse(candidates[0].get("fail_fast_provider_lease"))

    def test_judge_salvages_contract_json_after_provider_preamble(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "agent-runner.py"
            fake.write_text("""#!/usr/bin/env python3
import json,pathlib,sys
a=sys.argv[1:]; e=pathlib.Path(a[a.index('--evidence-dir')+1]); e.mkdir(parents=True)
r=e/'result.json'; r.write_text('I checked the article.\\n{"verdict":"PASS","violations":[]}\\n')
(e/'summary.json').write_text(json.dumps({'result_path':str(r)}))
""")
            fake.chmod(0o755)
            prompt = root / "prompt.txt"; prompt.write_text("check identity")
            env = {**os.environ, "AGENT_RUNNER_BIN": str(fake),
                   "WRITER_SHARED_RUNNER_STATE": str(root / "state")}
            result = subprocess.run(
                [sys.executable, str(ADAPTER), "judge", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"verdict": "PASS", "violations": []})

    def test_agent_report_uses_text_envelope_and_unwraps_it(self):
        # 2026-10-17 run 20261017-033711: the schema {} is falsy in agent_runner,
        # so Codex got no --output-schema, answered in prose, and the pass
        # exited rc=1 with empty stdout/stderr after a completed provider rc=0.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "agent-runner.py"
            fake.write_text("""#!/usr/bin/env python3
import json,pathlib,sys
a=sys.argv[1:]; e=pathlib.Path(a[a.index('--evidence-dir')+1]); e.mkdir(parents=True)
schema=json.loads(pathlib.Path(a[a.index('--schema')+1]).read_text())
assert schema['required']==['text'] and schema['properties']['text']=={'type':'string'}, schema
r=e/'result.json'; r.write_text('{"text":"Drafts created; publication pending."}')
(e/'summary.json').write_text(json.dumps({'result_path':str(r)}))
""")
            fake.chmod(0o755)
            prompt = root / "prompt.txt"; prompt.write_text("write today's article")
            env = {**os.environ, "AGENT_RUNNER_BIN": str(fake),
                   "WRITER_SHARED_RUNNER_STATE": str(root / "state")}
            env.pop("ARTICLE_CODEX_OUTPUT_SCHEMA", None)
            result = subprocess.run(
                [sys.executable, str(ADAPTER), "agent", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "Drafts created; publication pending.")

    def test_runner_failure_reason_reaches_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "agent-runner.py"
            fake.write_text("""#!/usr/bin/env python3
import json,pathlib,sys
a=sys.argv[1:]; e=pathlib.Path(a[a.index('--evidence-dir')+1]); e.mkdir(parents=True)
(e/'attempts.jsonl').write_text(json.dumps({'attempt':1,'provider':'codex','rc':0,
  'error_class':'validation_or_task_failure',
  'schema_errors':['result parse failed: no JSON object in provider result']})+'\\n')
print(json.dumps({'status':'failed'}))
sys.exit(1)
""")
            fake.chmod(0o755)
            prompt = root / "prompt.txt"; prompt.write_text("write today's article")
            env = {**os.environ, "AGENT_RUNNER_BIN": str(fake),
                   "WRITER_SHARED_RUNNER_STATE": str(root / "state")}
            result = subprocess.run(
                [sys.executable, str(ADAPTER), "agent", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("validation_or_task_failure", result.stderr)
            self.assertIn("no JSON object", result.stderr)
            self.assertIn(str(root / "state"), result.stderr)

    def test_adapter_contains_no_direct_provider_or_auth_selection(self):
        source = ADAPTER.read_text(encoding="utf-8")
        for forbidden in ("CODEX_HOME", "auth.json", "codex exec", "ARTICLE_PROVIDER"):
            self.assertNotIn(forbidden, source)

    def test_legacy_runner_uses_only_the_direct_codex_provider(self):
        source = LEGACY_ENTRY.read_text(encoding="utf-8")
        self.assertIn('CODEX_PROVIDER_ID="${ARTICLE_CODEX_PROVIDER_ID:-openai}"', source)
        self.assertIn("only the Codex CLI's direct provider is allowed", source)
        self.assertNotIn("configure_codex_provider", source)
        self.assertNotIn("load_codex_provider_key", source)

    def test_local_proxy_provider_is_rejected_before_codex_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "prompt.txt"
            prompt.write_text("portable provider probe")
            called = root / "called"
            fake = root / "codex"
            fake.write_text(
                '#!/usr/bin/env bash\ntouch "$CALLED"\ncat >/dev/null\n'
            )
            fake.chmod(0o755)
            secret = "direct-key-must-not-appear-in-trace"
            env = {**os.environ,
                   "ARTICLE_PROVIDER": "codex",
                   "ARTICLE_CODEX_BIN": str(fake),
                   "ARTICLE_CODEX_PROVIDER_ID": "cliproxy",
                   "ARTICLE_CODEX_PROVIDER_BASE_URL": "http://127.0.0.1:8317/v1",
                   "ARTICLE_CODEX_PROVIDER_ENV_KEY": "CLIPROXY_API_KEY",
                   "ARTICLE_CODEX_PROVIDER_API_KEY_SOURCE": "cliproxyapi",
                   "ARTICLE_CODEX_PROVIDER_API_KEY": secret,
                   "CALLED": str(called)}
            result = subprocess.run(
                ["bash", "-x", str(LEGACY_ENTRY), "agent", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 64, result.stderr)
            self.assertFalse(called.exists())
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_local_proxy_config_is_rejected_even_when_a_key_file_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "prompt.txt"
            prompt.write_text("portable provider fallback")
            called = root / "called"
            fake = root / "codex"
            fake.write_text(
                '#!/usr/bin/env bash\ntouch "$CALLED"\ncat >/dev/null\n'
            )
            fake.chmod(0o755)
            config = root / "cliproxy.conf"
            config.write_text('api-keys:\n  - "fixture-key"\n')
            env = {**os.environ,
                   "ARTICLE_PROVIDER": "codex",
                   "ARTICLE_CODEX_BIN": str(fake),
                   "ARTICLE_CODEX_PROVIDER_ID": "cliproxy",
                   "ARTICLE_CODEX_PROVIDER_BASE_URL": "http://127.0.0.1:8317/v1",
                   "ARTICLE_CODEX_PROVIDER_ENV_KEY": "CLIPROXY_API_KEY",
                   "ARTICLE_CODEX_PROVIDER_API_KEY_SOURCE": "cliproxyapi",
                   "ARTICLE_CLIPROXY_CONFIG": str(config),
                   "CALLED": str(called)}
            env.pop("ARTICLE_CODEX_PROVIDER_API_KEY", None)
            result = subprocess.run(
                ["bash", "-x", str(LEGACY_ENTRY), "agent", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 64, result.stderr)
            self.assertFalse(called.exists())
            self.assertNotIn("fixture-key", result.stdout + result.stderr)

    def test_nondefault_provider_fails_closed_without_any_key_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "prompt.txt"
            prompt.write_text("missing provider credential")
            called = root / "called"
            fake = root / "codex"
            fake.write_text('#!/usr/bin/env bash\ntouch "$CALLED"\n')
            fake.chmod(0o755)
            env = {**os.environ,
                   "ARTICLE_PROVIDER": "codex",
                   "ARTICLE_CODEX_BIN": str(fake),
                   "ARTICLE_CODEX_PROVIDER_ID": "cliproxy",
                   "ARTICLE_CODEX_PROVIDER_BASE_URL": "http://127.0.0.1:8317/v1",
                   "ARTICLE_CODEX_PROVIDER_ENV_KEY": "CLIPROXY_API_KEY",
                   "ARTICLE_CODEX_PROVIDER_API_KEY_SOURCE": "cliproxyapi",
                   "CALLED": str(called)}
            env.pop("ARTICLE_CODEX_PROVIDER_API_KEY", None)
            env.pop("ARTICLE_CLIPROXY_CONFIG", None)
            result = subprocess.run(
                [str(LEGACY_ENTRY), "agent", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(called.exists())
            self.assertIn("only the Codex CLI's direct provider is allowed", result.stderr)

    def test_production_legacy_entry_delegates_to_canonical_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fake = root / "agent-runner.py"
            fake.write_text("""#!/usr/bin/env python3
import json,pathlib,sys
a=sys.argv[1:]; e=pathlib.Path(a[a.index('--evidence-dir')+1]); e.mkdir(parents=True)
r=e/'result.json'; r.write_text('{"delegated":true}')
(e/'summary.json').write_text(json.dumps({'result_path':str(r)}))
"""); fake.chmod(0o755)
            prompt=root/'prompt.txt'; prompt.write_text('delegate this judge')
            env={key:value for key,value in os.environ.items()
                 if key not in {'ARTICLE_CODEX_BIN','ARTICLE_CLAUDE_BIN','ARTICLE_CODEX_EVENTS_FILE'}}
            env.update({'AGENT_RUNNER_BIN':str(fake),'WRITER_SHARED_RUNNER_STATE':str(root/'state')})
            result=subprocess.run([str(LEGACY_ENTRY),'judge','--prompt-file',str(prompt)],
                                  env=env,capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),{'delegated':True})

    def test_production_repair_delegates_cage_session_and_durable_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); workspace=root/'workspace'; workspace.mkdir()
            args_file=root/'args.json'; fake=root/'agent-runner.py'
            fake.write_text("""#!/usr/bin/env python3
import json,os,pathlib,sys
a=sys.argv[1:]; pathlib.Path(os.environ['CAPTURE_ARGS']).write_text(json.dumps(a))
e=pathlib.Path(a[a.index('--evidence-dir')+1]); e.mkdir(parents=True)
(e/'attempt-01.stdout.log').write_text('{"type":"thread.started","thread_id":"thread-123"}\\n')
r=e/'result.json'; r.write_text('{"complete":true}')
(e/'summary.json').write_text(json.dumps({'result_path':str(r)}))
"""); fake.chmod(0o755)
            prompt=root/'prompt.txt'; prompt.write_text('repair this workspace')
            schema=root/'schema.json'; schema.write_text('{}')
            events,last=root/'events.jsonl',root/'last.json'
            env={key:value for key,value in os.environ.items()
                 if key not in {'ARTICLE_CODEX_BIN','ARTICLE_CLAUDE_BIN'}}
            env.update({'AGENT_RUNNER_BIN':str(fake),'WRITER_SHARED_RUNNER_STATE':str(root/'state'),
                        'ARTICLE_PROVIDER':'codex',
                        'ARTICLE_REPAIR_WORKSPACE':str(workspace),'ARTICLE_CODEX_EVENTS_FILE':str(events),
                        'ARTICLE_CODEX_LAST_MESSAGE_FILE':str(last),'ARTICLE_CODEX_OUTPUT_SCHEMA':str(schema),
                        'ARTICLE_CODEX_RESUME_SESSION_ID':'thread-123','CAPTURE_ARGS':str(args_file)})
            result=subprocess.run([str(LEGACY_ENTRY),'repair','--prompt-file',str(prompt)],
                                  env=env,capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,0,result.stderr)
            args=json.loads(args_file.read_text())
            self.assertIn('writer-repair-agent',args)
            self.assertEqual(args[args.index('--codex-resume-session-id')+1],'thread-123')
            self.assertIn('thread.started',events.read_text())
            self.assertEqual(json.loads(last.read_text()),{'complete':True})

    def test_agent_workspace_materializes_private_draft_with_tooled_codex_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "run"
            workspace.mkdir()
            prompt = root / "prompt.txt"
            prompt.write_text("draft only")
            schema = root / "capafy-draft.schema.json"
            schema.write_text('{"type":"object"}')
            output = workspace / "draft-response.json"
            captured = root / "agent-runner-args.json"
            fake = root / "agent-runner.py"
            fake.write_text("""#!/usr/bin/env python3
import json,os,pathlib,sys
a=sys.argv[1:]
pathlib.Path(os.environ["CAPTURE_ARGS"]).write_text(json.dumps(a))
e=pathlib.Path(a[a.index("--evidence-dir")+1]); e.mkdir(parents=True)
r=e/"result.json"
r.write_text(json.dumps({"article_markdown":"draft","x_caption":"caption"}))
(e/"summary.json").write_text(json.dumps({"result_path":str(r)}))
""")
            fake.chmod(0o755)
            env = {
                **os.environ,
                "AGENT_RUNNER_BIN": str(fake),
                "WRITER_SHARED_RUNNER_STATE": str(root / "state"),
                "ARTICLE_RUN_DIR": str(workspace),
                "ARTICLE_CODEX_NO_TOOLS": "1",
                "ARTICLE_CODEX_OUTPUT_FILE": str(output),
                "ARTICLE_CODEX_OUTPUT_SCHEMA": str(schema),
                "CAPTURE_ARGS": str(captured),
            }
            result = subprocess.run(
                [sys.executable, str(ADAPTER), "agent-workspace", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            args = json.loads(captured.read_text())
            self.assertEqual(args[args.index("--task-class") + 1], "composition-agent")
            self.assertEqual(args[args.index("--workdir") + 1], str(workspace.resolve()))
            self.assertEqual(args[args.index("--schema") + 1], str(schema))
            self.assertEqual(json.loads(output.read_text()), {
                "article_markdown": "draft", "x_caption": "caption",
            })
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(result.stdout, "")

    def test_agent_workspace_rejects_sol_audit_role_before_runner_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "run"
            workspace.mkdir()
            prompt = root / "prompt.txt"
            prompt.write_text("draft only")
            schema = root / "capafy-draft.schema.json"
            schema.write_text('{"type":"object"}')
            output = workspace / "draft-response.json"
            dispatched = root / "runner-dispatched"
            fake = root / "agent-runner.py"
            fake.write_text(f"#!/usr/bin/env python3\nfrom pathlib import Path\nPath({str(dispatched)!r}).touch()\n")
            fake.chmod(0o755)
            env = {
                **os.environ,
                "AGENT_RUNNER_BIN": str(fake),
                "WRITER_SHARED_RUNNER_STATE": str(root / "state"),
                "ARTICLE_RUN_DIR": str(workspace),
                "ARTICLE_CODEX_NO_TOOLS": "1",
                "ARTICLE_CODEX_OUTPUT_FILE": str(output),
                "ARTICLE_CODEX_OUTPUT_SCHEMA": str(schema),
                "ARTICLE_MODEL_ROLE": "sol-audit",
            }
            result = subprocess.run(
                [sys.executable, str(ADAPTER), "agent-workspace", "--prompt-file", str(prompt)],
                env=env, capture_output=True, text=True, check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sol-audit", result.stderr)
            self.assertFalse(dispatched.exists())


if __name__ == "__main__":
    unittest.main()
