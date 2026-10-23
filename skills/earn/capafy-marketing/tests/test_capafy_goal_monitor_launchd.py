from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MONITOR = ROOT / "skills/earn/capafy-marketing/capafy-goal-monitor.sh"


def test_probe_resolves_release_root_without_git(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    marketing = release_root / "skills/earn/capafy-marketing"
    marketing.mkdir(parents=True)
    shutil.copy2(MONITOR, marketing / MONITOR.name)
    (marketing / "account_state.sh").write_text(
        "capafy_ig_accounts_file(){ printf '%s\\n' \"$CAPAFY_FIXTURE_ACCOUNTS\"; }\n"
        "resolve_capafy_ig_handle(){ printf fixture; }\n"
        "resolve_capafy_ig_port(){ printf 9332; }\n"
        "resolve_capafy_ig_session_owner(){ printf browser; }\n"
        "resolve_capafy_ig_started_warming(){ printf 2020-01-01; }\n"
        "capafy_ig_warming_day(){ printf 3; }\n",
        encoding="utf-8",
    )
    accounts = tmp_path / "accounts.json"
    accounts.write_text("[]\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "CAPAFY_FIXTURE_ACCOUNTS": str(accounts),
            "CAPAFY_GOAL_MONITOR_PROBE_ONLY": "1",
        }
    )
    env.pop("LIFE_MANAGER_REPO", None)
    result = subprocess.run(
        ["bash", str(marketing / MONITOR.name)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert not (release_root / ".git").exists()
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"active_handle=fixture active_port=9332 accounts_path={accounts}"
    )


def test_probe_fails_closed_when_release_root_lacks_account_state_helper(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    marketing = release_root / "skills/earn/capafy-marketing"
    marketing.mkdir(parents=True)
    shutil.copy2(MONITOR, marketing / MONITOR.name)
    home = tmp_path / "home"
    home.mkdir()

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "CAPAFY_GOAL_MONITOR_PROBE_ONLY": "1",
        }
    )
    env.pop("LIFE_MANAGER_REPO", None)
    env.pop("CAPAFY_ACCOUNT_STATE_HELPER", None)
    result = subprocess.run(
        ["bash", str(marketing / MONITOR.name)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "active_handle=" not in result.stdout
    assert "CAPAFY_ACCOUNT_STATE_HELPER" in result.stderr


def run_monitor(
    tmp_path: Path,
    print_output: str,
    *,
    bootout_stuck: bool = False,
    bootstrap_fail: bool = False,
    post_mismatch: bool = False,
    launchd_test: bool = True,
) -> tuple[subprocess.CompletedProcess, list[str]]:
    repo = tmp_path / "repo"
    marketing = repo / "skills/earn/capafy-marketing"
    marketing.mkdir(parents=True)
    shutil.copy2(MONITOR, marketing / MONITOR.name)
    (marketing / "account_state.sh").write_text(
        "capafy_ig_accounts_file(){ echo /tmp/accounts.json; }\n"
        "resolve_capafy_ig_handle(){ echo fixture; }\n"
        "resolve_capafy_ig_port(){ echo 9332; }\n"
        "resolve_capafy_ig_session_owner(){ echo browser; }\n"
        "resolve_capafy_ig_started_warming(){ echo 2020-01-01; }\n"
        "capafy_ig_warming_day(){ echo 3; }\n",
        encoding="utf-8",
    )
    safe = tmp_path / "launchctl-safe"
    calls = tmp_path / "calls.log"
    state = tmp_path / "state"
    (tmp_path / "home/Library/LaunchAgents").mkdir(parents=True)
    safe.write_text(
        "#!/bin/sh\n"
        f"echo \"$*\" >> '{calls}'\n"
        "mkdir -p \"$STATE\"\n"
        "case \"$1\" in\n"
        "  print) if [ -f \"$STATE/hourly\" ] && [ \"$POST_MISMATCH\" = 1 ]; then echo 'run interval = 7200 seconds'; elif [ -f \"$STATE/hourly\" ]; then echo 'run interval = 3600 seconds'; elif [ -f \"$STATE/bootout\" ] && [ \"$BOOTOUT_STUCK\" != 1 ]; then exit 1; else printf '%s\\n' \"$PRINT_OUTPUT\"; fi ;;\n"
        "  preflight) exit 0 ;;\n"
        "  bootout) touch \"$STATE/bootout\" ;;\n"
        "  bootstrap) [ \"$BOOTSTRAP_FAIL\" = 1 ] && exit 1; mkdir -p \"$STATE\"; touch \"$STATE/hourly\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    safe.chmod(0o755)
    env = os.environ | {
        "HOME": str(tmp_path / "home"),
        "LIFE_MANAGER_REPO": str(repo),
        "CAPAFY_LAUNCHCTL_SAFE": str(safe),
        "CAPAFY_LAUNCHCTL_DOMAIN": "gui/501",
        "STATE": str(state),
        "PRINT_OUTPUT": print_output,
        "BOOTOUT_STUCK": "1" if bootout_stuck else "0",
        "BOOTSTRAP_FAIL": "1" if bootstrap_fail else "0",
        "POST_MISMATCH": "1" if post_mismatch else "0",
        "CAPAFY_IG_UNLOAD_POLL_ATTEMPTS": "2",
        "CAPAFY_IG_UNLOAD_POLL_SLEEP": "0",
    }
    if launchd_test:
        env["CAPAFY_GOAL_MONITOR_LAUNCHD_TEST"] = "1"
    result = subprocess.run(["bash", str(marketing / MONITOR.name)], env=env, text=True, capture_output=True, check=False)
    return result, calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []


def test_already_hourly_has_no_launchctl_mutation(tmp_path: Path) -> None:
    result, calls = run_monitor(tmp_path, "run interval = 3600 seconds")
    assert result.returncode == 0
    assert calls == ["print gui/501/ai.anicca.capafy-ig-marketing-daily"]


def test_calendar_mismatch_boots_out_and_bootstraps_exact_service(tmp_path: Path) -> None:
    result, calls = run_monitor(tmp_path, "run interval = 86400 seconds")
    assert result.returncode == 0
    assert calls[:3] == [
        "print gui/501/ai.anicca.capafy-ig-marketing-daily",
        "preflight",
        "bootout gui/501/ai.anicca.capafy-ig-marketing-daily",
    ]
    assert calls[3].startswith("print gui/501/ai.anicca.capafy-ig-marketing-daily")
    assert calls[4].startswith("bootstrap gui/501 ")
    assert calls[5] == "print gui/501/ai.anicca.capafy-ig-marketing-daily"


def test_bootout_wait_timeout_fails_closed(tmp_path: Path) -> None:
    result, _ = run_monitor(tmp_path, "run interval = 86400 seconds", bootout_stuck=True)
    assert result.returncode != 0


def test_bootstrap_failure_fails_closed(tmp_path: Path) -> None:
    result, _ = run_monitor(tmp_path, "run interval = 86400 seconds", bootstrap_fail=True)
    assert result.returncode != 0


def test_post_readback_interval_mismatch_fails_closed(tmp_path: Path) -> None:
    result, _ = run_monitor(tmp_path, "run interval = 86400 seconds", post_mismatch=True)
    assert result.returncode != 0


def test_full_goal_monitor_propagates_bootstrap_failure_before_healthy_continuation(tmp_path: Path) -> None:
    result, _ = run_monitor(
        tmp_path,
        "run interval = 86400 seconds",
        bootstrap_fail=True,
        launchd_test=False,
    )
    assert result.returncode == 2


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _goal_monitor_fixture(tmp_path: Path) -> dict[str, Path]:
    """Build a full-script fixture whose downstream integrations are inert."""
    repo = tmp_path / "repo"
    marketing = repo / "skills/earn/capafy-marketing"
    marketing.mkdir(parents=True)
    shutil.copy2(MONITOR, marketing / MONITOR.name)

    helper = tmp_path / "account_state.sh"
    helper.write_text(
        "capafy_ig_accounts_file(){ printf '%s\\n' \"$CAPAFY_FIXTURE_ACCOUNTS\"; }\n"
        "resolve_capafy_ig_handle(){ printf 'fixture'; }\n"
        "resolve_capafy_ig_port(){ printf '9332'; }\n"
        "resolve_capafy_ig_session_owner(){ printf 'browser'; }\n"
        "resolve_capafy_ig_started_warming(){ printf '2020-01-01'; }\n"
        "capafy_ig_warming_day(){ printf '3'; }\n",
        encoding="utf-8",
    )

    daily_tool = repo / "skills/self/capafy-loop/capafy_daily_terminal.py"
    daily_tool.parent.mkdir(parents=True, exist_ok=True)
    daily_tool.write_text(
        "import json\nprint(json.dumps({'consecutive_healthy_days': 0, 'pass': False}))\n",
        encoding="utf-8",
    )
    scripts = repo / "skills/earn/capafy-marketing/scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name, marker in (
        ("capafy_hourly_reconcile.py", "reconcile"),
        ("capafy_company_receipt.py", "deliver"),
    ):
        (scripts / name).write_text(
            "import os\n"
            "with open(os.environ['CAPAFY_TEST_DOWNSTREAM'], 'a', encoding='utf-8') as f:\n"
            f"    f.write('{marker}\\n')\n",
            encoding="utf-8",
        )

    home = tmp_path / "home"
    (home / ".local/bin").mkdir(parents=True)
    (home / ".local/state/life-manager/logs").mkdir(parents=True)
    accounts = home / ".cloak/accounts.json"
    accounts.parent.mkdir(parents=True, exist_ok=True)
    accounts.write_text("[]\n", encoding="utf-8")
    state_home = tmp_path / "state-home"
    (state_home / "state").mkdir(parents=True)
    earn_ledger = state_home / "state/capafy-hourly-reconcile.json"
    earn_ledger.write_text(
        json.dumps({
            "orders": 1,
            "money": {"gross_usd": 2.0},
            "observed_at": "2026-08-23T00:00:00+09:00",
        }),
        encoding="utf-8",
    )
    (state_home / "state/capafy-skill-analytics.json").write_text(
        json.dumps({
            "daily_revenue_trend_last_30d": [
                {"date": "2026-08-20", "revenue": 2.0, "orders": 1},
                {"date": "2026-08-21", "revenue": 0.0, "orders": 0},
                {"date": "2026-08-22", "revenue": -2.0, "orders": -1},
            ]
        }),
        encoding="utf-8",
    )

    safe_calls = tmp_path / "launchctl-safe.calls"
    safe = tmp_path / "launchctl-safe"
    _write_executable(
        safe,
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$CAPAFY_SAFE_CALLS\"\n"
        "exit 99\n",
    )
    _write_executable(
        home / ".local/bin/launchctl",
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$CAPAFY_LAUNCHCTL_CALLS\"\n"
        "printf ''\n",
    )
    downstream = tmp_path / "downstream.calls"
    return {
        "repo": repo,
        "home": home,
        "state_home": state_home,
        "helper": helper,
        "accounts": accounts,
        "safe": safe,
        "safe_calls": safe_calls,
        "launchctl_calls": tmp_path / "launchctl.calls",
        "downstream": downstream,
    }


def _run_full_goal_monitor(
    tmp_path: Path,
    *,
    headless: bool,
    hourly_reconcile_body: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Path]]:
    fixture = _goal_monitor_fixture(tmp_path)
    if hourly_reconcile_body is not None:
        reconcile_script = fixture["repo"] / "skills/earn/capafy-marketing/scripts/capafy_hourly_reconcile.py"
        reconcile_script.write_text(hourly_reconcile_body, encoding="utf-8")
    env = os.environ | {
        "HOME": str(fixture["home"]),
        "LIFE_MANAGER_REPO": str(fixture["repo"]),
        "LIFE_MANAGER_STATE_HOME": str(fixture["state_home"]),
        "CAPAFY_ACCOUNT_STATE_HELPER": str(fixture["helper"]),
        "CAPAFY_FIXTURE_ACCOUNTS": str(fixture["accounts"]),
        "CAPAFY_LAUNCHCTL_SAFE": str(fixture["safe"]),
        "CAPAFY_LAUNCHCTL_DOMAIN": "gui/501",
        "CAPAFY_SAFE_CALLS": str(fixture["safe_calls"]),
        "CAPAFY_LAUNCHCTL_CALLS": str(fixture["launchctl_calls"]),
        "CAPAFY_TEST_DOWNSTREAM": str(fixture["downstream"]),
        "CAPAFY_REPORT_KIND": "hourly",
    }
    if headless:
        env["CAPAFY_HEADLESS_BRIDGE"] = "1"
    result = subprocess.run(
        ["bash", str(fixture["repo"] / "skills/earn/capafy-marketing/capafy-goal-monitor.sh")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, fixture


def test_real_goal_monitor_headless_bridge_skips_safe_and_reaches_report_state(tmp_path: Path) -> None:
    result, fixture = _run_full_goal_monitor(tmp_path, headless=True)

    assert result.returncode == 0, result.stderr
    assert not fixture["safe_calls"].exists()
    assert fixture["downstream"].read_text(encoding="utf-8").splitlines() == ["reconcile", "deliver"]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["goal_c"]["go_live_action"] == "headless_bridge"
    state = json.loads((fixture["state_home"] / "state/capafy-goal-monitor.json").read_text(encoding="utf-8"))
    assert state["latest"] == report


def test_goal_monitor_separates_reconcile_date_from_last_revenue_day(tmp_path: Path) -> None:
    result, _ = _run_full_goal_monitor(tmp_path, headless=True)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    goal_b = report["goal_b"]
    assert goal_b["reconcile_observed_date"] == "2026-08-23"
    assert goal_b["last_positive_revenue_date_30d"] == "2026-08-20"
    assert "last_sales_date" not in goal_b


def test_hourly_monitor_state_uses_reconcile_written_in_same_run(tmp_path: Path) -> None:
    reconcile_body = (
        "import json, os\n"
        "from pathlib import Path\n"
        "ledger = Path(os.environ['LIFE_MANAGER_STATE_HOME']) / 'state/capafy-hourly-reconcile.json'\n"
        "data = json.loads(ledger.read_text(encoding='utf-8'))\n"
        "data['observed_at'] = '2026-08-24T00:30:00+09:00'\n"
        "data['orders'] = 4\n"
        "data['money']['gross_usd'] = '8.00'\n"
        "ledger.write_text(json.dumps(data), encoding='utf-8')\n"
        "with open(os.environ['CAPAFY_TEST_DOWNSTREAM'], 'a', encoding='utf-8') as f:\n"
        "    f.write('reconcile\\n')\n"
    )
    result, fixture = _run_full_goal_monitor(
        tmp_path,
        headless=True,
        hourly_reconcile_body=reconcile_body,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["goal_b"]["reconcile_observed_at"] == "2026-08-24T00:30:00+09:00"
    assert report["goal_b"]["orders"] == 4
    assert report["goal_b"]["gross_usd"] == "8.00"
    state = json.loads((fixture["state_home"] / "state/capafy-goal-monitor.json").read_text(encoding="utf-8"))
    assert state["latest"] == report


def test_real_goal_monitor_normal_mode_still_fails_closed_before_report(tmp_path: Path) -> None:
    result, fixture = _run_full_goal_monitor(tmp_path, headless=False)

    assert result.returncode == 2
    assert fixture["safe_calls"].read_text(encoding="utf-8").splitlines() == [
        "print gui/501/ai.anicca.capafy-ig-marketing-daily",
        "preflight",
    ]
    assert not fixture["downstream"].exists()
    assert not (fixture["state_home"] / "state/capafy-goal-monitor.json").exists()


def test_report_kind_falls_back_to_loop_id_when_env_absent() -> None:
    # lm-loop registry entries carry no env, so the hourly loop must derive its kind
    # from LIFE_MANAGER_LOOP_ID or it silently runs the morning path (no reconcile).
    source = MONITOR.read_text(encoding="utf-8")
    assert "capafy-goal-monitor-hourly) REPORT_KIND=hourly" in source
    assert "capafy-goal-monitor-daily-close) REPORT_KIND=daily_close" in source
