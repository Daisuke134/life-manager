import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parent / "reddit-loop-healthcheck.sh"
DAILY = Path(__file__).parent / "reddit-loop-daily.sh"
REPO = Path(__file__).parents[2]


def test_daily_resolves_shared_runner_from_repository(tmp_path):
    result = subprocess.run(
        ["/bin/bash", str(DAILY)],
        env={**os.environ, "HOME": str(tmp_path), "AGENT_WIRING_PROBE_ONLY": "1"},
        capture_output=True,
        text=True,
        check=True,
    )

    assert str(REPO / "skills/earn/marketing-engine/run_agent.sh") in result.stdout


def test_daily_passes_the_account_camofox_session_to_the_agent(tmp_path):
    accounts = tmp_path / "reddit-accounts.json"
    accounts.write_text(
        '{"accounts":[{"username":"anicca_sao","camofox_session":'
        '{"userId":"anicca","sessionKey":"stored-session"}}]}\n'
    )
    runner = tmp_path / "runner.sh"
    runner.write_text(
        "#!/bin/bash\n"
        "printf '%s|%s\n' \"$CF_USER\" \"$CF_SESSION\" > \"$CAPTURE\"\n"
    )
    runner.chmod(0o755)
    capture = tmp_path / "capture.txt"
    result = subprocess.run(
        ["/bin/bash", str(DAILY)],
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "RD_ACCOUNTS": str(accounts),
            "REDDIT_STATE_ROOT": str(tmp_path / "reddit"),
            "RUN_AGENT_BIN": str(runner),
            "CAPTURE": str(capture),
            "AGENT_RUNNER_EVIDENCE_MIN_FREE_BYTES": "0",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0
    assert capture.read_text().strip() == "anicca|stored-session"


def test_daily_prompt_has_a_same_tab_fallback_when_snapshot_turns_empty(tmp_path):
    accounts = tmp_path / "reddit-accounts.json"
    accounts.write_text(
        '{"accounts":[{"username":"anicca_sao","camofox_session":'
        '{"userId":"anicca","sessionKey":"stored-session"}}]}\n'
    )
    runner = tmp_path / "runner.sh"
    runner.write_text(
        "#!/bin/bash\n"
        "cat > \"$PROMPT_CAPTURE\"\n"
    )
    runner.chmod(0o755)
    prompt = tmp_path / "prompt.txt"
    subprocess.run(
        ["/bin/bash", str(DAILY)],
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "RD_ACCOUNTS": str(accounts),
            "REDDIT_STATE_ROOT": str(tmp_path / "reddit"),
            "RUN_AGENT_BIN": str(runner),
            "PROMPT_CAPTURE": str(prompt),
            "AGENT_RUNNER_EVIDENCE_MIN_FREE_BYTES": "0",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    text = prompt.read_text()
    assert "same tab" in text
    assert "cf_screenshot" in text
    assert "do not retry snapshot" in text


def test_stale_heartbeat_is_reported_without_launchd_or_nohup_recovery(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    marker = tmp_path / "mutation"
    function = f'() {{ printf x >> "{marker}"; return 1; }}'
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT)],
        env={
            **os.environ,
            "HOME": str(home),
            "BASH_FUNC_launchctl%%": function,
            "BASH_FUNC_nohup%%": function,
            "BASH_FUNC_tmux%%": "() { return 1; }",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not marker.exists()
    assert "stale/missing" in (
        home / ".local/state/life-manager/reddit/logs/reddit-loop-healthcheck.log"
    ).read_text()
