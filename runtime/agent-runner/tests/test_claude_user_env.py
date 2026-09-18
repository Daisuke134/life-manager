import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent_runner import provider_process_env  # noqa: E402


class ClaudeUserEnvTest(unittest.TestCase):
    """launchd omits USER; the claude CLI reads stored OAuth credentials only
    when USER is set, so a launchd-run claude call fails "Not logged in"
    without this (measured 2026-09-04)."""

    def test_claude_direct_gets_user_when_missing(self):
        launchd_environ = {"HOME": "/srv/operator", "PATH": "/usr/bin:/bin"}
        with patch("agent_runner.pwd.getpwuid", return_value=SimpleNamespace(pw_name="operator")):
            env = provider_process_env("claude-direct", {}, environ=launchd_environ)
        self.assertTrue(env.get("USER"))

    def test_claude_direct_keeps_existing_user(self):
        environ = {"HOME": "/srv/operator", "PATH": "/usr/bin:/bin", "USER": "someone"}
        with patch("agent_runner.pwd.getpwuid", return_value=SimpleNamespace(pw_name="operator")):
            env = provider_process_env("claude-direct", {}, environ=environ)
        self.assertEqual(env.get("USER"), "someone")

    def test_claude_direct_does_not_inherit_codex_home_lock_scope(self):
        environ = {
            "HOME": "/srv/operator",
            "PATH": "/usr/bin:/bin",
            "CODEX_HOME": "/fixture/busy-codex-home",
        }
        with patch("agent_runner.pwd.getpwuid", return_value=SimpleNamespace(pw_name="operator")):
            env = provider_process_env("claude-direct", {}, environ=environ)
        self.assertNotIn("CODEX_HOME", env)

    def test_claude_direct_does_not_inherit_clipproxy_key(self):
        environ = {
            "HOME": "/srv/operator",
            "PATH": "/usr/bin:/bin",
            "CLIPROXY_API_KEY": "must-not-reach-claude",
            "ARTICLE_CODEX_PROVIDER_API_KEY": "must-not-reach-claude-either",
        }
        with patch("agent_runner.pwd.getpwuid", return_value=SimpleNamespace(pw_name="operator")):
            env = provider_process_env("claude-direct", {}, environ=environ)
        self.assertNotIn("CLIPROXY_API_KEY", env)
        self.assertNotIn("ARTICLE_CODEX_PROVIDER_API_KEY", env)

    def test_codex_loads_clipproxy_key_from_owner_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "cliproxy.conf"
            config.write_text('api-keys:\n  - "codex-image-key"\n', encoding="utf-8")
            env = provider_process_env(
                "codex",
                {},
                environ={
                    "ARTICLE_CODEX_PROVIDER_API_KEY_SOURCE": "cliproxyapi",
                    "ARTICLE_CODEX_PROVIDER_ENV_KEY": "CLIPROXY_API_KEY",
                    "ARTICLE_CODEX_PROVIDER_ID": "local_proxy",
                    "ARTICLE_CLIPROXY_CONFIG": str(config),
                },
        )
        self.assertEqual(env["CLIPROXY_API_KEY"], "codex-image-key")

    def test_direct_openai_codex_does_not_read_clipproxy_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "cliproxy.conf"
            auth = Path(directory) / "auth.json"
            openai_key = Path(directory) / "openai.key"
            auth.write_text("{}", encoding="utf-8")
            openai_key.write_text("openai-image-key", encoding="utf-8")
            config.write_text('api-keys:\n  - "must-not-load"\n', encoding="utf-8")
            env = provider_process_env(
                "codex",
                {
                    "model_provider": "openai",
                    "model_providers": {
                        "openai": {
                            "env_key": "OPENAI_API_KEY",
                            "auth_token_file": str(openai_key),
                        },
                        "local_proxy": {
                            "env_key": "CLIPROXY_API_KEY",
                            "auth_token_file": str(config),
                        },
                    },
                    "automation_home": str(Path(directory) / "codex-home"),
                    "auth_file": str(auth),
                },
                environ={
                    "ARTICLE_CODEX_PROVIDER_API_KEY_SOURCE": "cliproxyapi",
                    "ARTICLE_CODEX_PROVIDER_ENV_KEY": "CLIPROXY_API_KEY",
                    "ARTICLE_CODEX_PROVIDER_ID": "local_proxy",
                    "CLIPROXY_API_KEY": "inherited-proxy-key",
                    "ARTICLE_CODEX_PROVIDER_API_KEY": "inherited-direct-key",
                    "OPENAI_API_KEY": "inherited-openai-key",
                    "ARTICLE_CLIPROXY_CONFIG": str(config),
                },
            )
            self.assertNotIn("CLIPROXY_API_KEY", env)
            self.assertNotIn("ARTICLE_CODEX_PROVIDER_API_KEY", env)
            self.assertEqual(env["OPENAI_API_KEY"], "openai-image-key")


if __name__ == "__main__":
    unittest.main()
