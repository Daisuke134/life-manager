from __future__ import annotations

import json
from pathlib import Path
import subprocess
from unittest import mock

from lib import promote_gate_run


def test_adversary_uses_codex_cli_without_selecting_another_model(tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def run(command, *, cwd, input, capture_output, text, timeout, env):
        observed.update({
            "command": command,
            "cwd": cwd,
            "input": input,
            "timeout": timeout,
            "env": env,
        })
        output_file = Path(command[command.index("--output-last-message") + 1])
        output_file.write_text(
            json.dumps({"verdict": "PASS", "reason": "candidate improves held-out selection"}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with mock.patch("shutil.which", return_value="/fixture/codex"), \
         mock.patch("subprocess.run", side_effect=run), \
         mock.patch("os.path.exists", return_value=False):
        result = promote_gate_run._invoke_adversary("review this exact diff", str(tmp_path))

    command = observed["command"]
    assert isinstance(command, list)
    assert command[:2] == ["/fixture/codex", "exec"]
    assert "--output-schema" in command
    assert "--output-last-message" in command
    assert "--ephemeral" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--model" not in command and "-m" not in command
    assert not any("claude" in str(arg).lower() for arg in command)
    assert observed["input"] == "review this exact diff"
    env = observed["env"]
    assert isinstance(env, dict)
    assert not any(key.startswith("ANTHROPIC_") for key in env)
    assert result == {
        "ok": True,
        "verdict": "PASS",
        "reason": "candidate improves held-out selection",
        "cost_usd": None,
        "session_id": None,
    }
