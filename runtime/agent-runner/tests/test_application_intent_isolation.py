import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_runner import provider_process_env


class ApplicationIntentIsolationTest(unittest.TestCase):
    def setUp(self):
        self.source = {
            "PATH": "/usr/bin:/bin",
            "CODEX_HOME": "/tmp/codex",
            "LANCERS_CDP_URL": "http://127.0.0.1:9227",
            "PLAYWRIGHT_WS_ENDPOINT": "ws://localhost:9227/devtools/browser/secret",
            "MARKETPLACE_TOKEN": "fixture-token",
        }

    def test_application_intent_planner_removes_browser_routes_only(self):
        child_env = provider_process_env(
            "codex",
            {},
            self.source,
            task_class="application-intent-planner",
        )

        self.assertEqual(child_env["PATH"], "/usr/bin:/bin")
        self.assertEqual(child_env["CODEX_HOME"], "/tmp/codex")
        self.assertEqual(child_env["MARKETPLACE_TOKEN"], "fixture-token")
        self.assertNotIn("LANCERS_CDP_URL", child_env)
        self.assertNotIn("PLAYWRIGHT_WS_ENDPOINT", child_env)

    def test_normal_task_preserves_original_environment(self):
        child_env = provider_process_env("codex", {}, self.source)

        self.assertEqual(child_env, self.source)

    def test_codex_proxy_auth_is_loaded_even_with_openai_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token_file = root / "proxy-token"
            auth_file = root / "auth.json"
            token_file.write_text("proxy-fixture\n", encoding="utf-8")
            auth_file.write_text("{}\n", encoding="utf-8")
            child_env = provider_process_env("codex", {
                "automation_home": str(root / "automation"),
                "auth_file": str(auth_file),
                "model_providers": {"local_proxy": {
                    "env_key": "CLIPROXY_API_KEY",
                    "auth_token_file": str(token_file),
                }},
            }, {"OPENAI_API_KEY": "unrelated-fixture"})

        self.assertEqual(child_env["CLIPROXY_API_KEY"], "proxy-fixture")

    def test_application_intent_planner_config(self):
        config_path = ROOT / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(config["task_classes"]["application-intent-planner"], {
            "route": "luna-high-isolated-application-intent",
            "requires_explicit_escalation": True,
            "token_reservation": 24576,
            "timeout_seconds": 420,
            "candidates": [
                {"provider": "codex", "model": "gpt-5.6-luna", "effort": "high", "profile_alias": "acct1"},
                {"provider": "codex", "model": "gpt-5.6-terra", "effort": "medium", "profile_alias": "acct1"},
                {"provider": "claude-direct", "model": "claude-sonnet-5"},
            ],
        })

    def test_every_caller_of_the_planner_passes_an_escalation_reason(self):
        """Two lanes share this task class. A caller that omits the reason dies on its first wake."""
        repo_root = ROOT.parents[1]
        callers = (
            repo_root / "skills/earn/gig/scripts/application_parent.py",
            repo_root / "skills/earn/lancers/scripts/application_loop.py",
        )
        for caller in callers:
            with self.subTest(caller=caller.name):
                source = caller.read_text(encoding="utf-8")
                self.assertIn("application-intent-planner", source)
                self.assertIn("--escalation-reason", source)


if __name__ == "__main__":
    unittest.main()
