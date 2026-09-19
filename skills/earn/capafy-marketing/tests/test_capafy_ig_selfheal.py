from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "skills/earn/capafy-marketing/capafy-ig-marketing-daily.sh"
LABELS = [
    "ai.anicca.capafy-goal-monitor",
    "ai.anicca.capafy-goal-monitor-hourly",
    "ai.anicca.capafy-goal-monitor-daily-close",
    "ai.anicca.capafy-loop-daily",
    "ai.anicca.capafy-loop-healthcheck",
    "ai.anicca.capafy-outcome-monitor",
    "ai.anicca.capafy-ig-account-manager",
]


def run_selfheal(
    tmp_path: Path,
    missing_hourly: bool = False,
    fail_bootstrap: bool = False,
    launchd_test: bool = True,
):
    repo = tmp_path / "repo"
    target = repo / "skills/earn/capafy-marketing"
    target.mkdir(parents=True)
    shutil.copy2(SCRIPT, target / SCRIPT.name)
    home = tmp_path / "home"
    launchagents = home / "Library/LaunchAgents"
    launchagents.mkdir(parents=True)
    state = tmp_path / "loaded"
    state.mkdir()
    for label in LABELS:
        (launchagents / f"{label}.plist").write_text("plist")
        if not missing_hourly or label != "ai.anicca.capafy-goal-monitor-hourly":
            (state / label).touch()
    calls = tmp_path / "calls.log"
    safe = tmp_path / "launchctl-safe"
    bootstrap_action = (
        "exit 1" if fail_bootstrap
        else 'label=$(basename "$3" .plist); mkdir -p "$STATE"; touch "$STATE/$label"'
    )
    safe.write_text(
        "#!/bin/sh\n"
        f"echo \"$*\" >> '{calls}'\n"
        "case \"$1\" in\n"
        " print) label=${2##*/}; [ -f \"$STATE/$label\" ] || exit 1 ;;\n"
        f" bootstrap) {bootstrap_action} ;;\n"
        " kickstart) ;;\n"
        " preflight) ;;\n"
        "esac\n",
    )
    safe.chmod(0o755)
    env = os.environ | {
        "HOME": str(home), "LIFE_MANAGER_REPO": str(repo),
        "CAPAFY_LAUNCHCTL_SAFE": str(safe), "CAPAFY_LAUNCHCTL_DOMAIN": "gui/501",
        "STATE": str(state),
    }
    if launchd_test:
        env["CAPAFY_IG_MARKETING_SELFHEAL_TEST"] = "1"
    result = subprocess.run(
        ["bash", str(target / SCRIPT.name)],
        env=env, text=True, capture_output=True, check=False,
    )
    return result, calls.read_text().splitlines() if calls.exists() else []


def test_all_present_prints_only(tmp_path: Path):
    result, calls = run_selfheal(tmp_path)
    assert result.returncode == 0
    assert all(call.startswith("print ") for call in calls)


def test_missing_hourly_bootstraps_and_kickstarts_only_hourly(tmp_path: Path):
    result, calls = run_selfheal(tmp_path, missing_hourly=True)
    assert result.returncode == 0
    assert any(call.startswith("preflight") for call in calls)
    assert any("bootstrap gui/501" in call for call in calls)
    assert calls[-1] == "kickstart gui/501/ai.anicca.capafy-goal-monitor-hourly"


def test_bootstrap_failure_stops_before_marketing(tmp_path: Path):
    result, calls = run_selfheal(tmp_path, missing_hourly=True, fail_bootstrap=True, launchd_test=False)
    assert result.returncode == 2
    assert not any("metrics" in call or "run_agent" in call for call in calls)


def test_production_mode_runs_selfheal_before_account_and_metrics(tmp_path: Path):
    result, calls = run_selfheal(tmp_path, launchd_test=False)
    assert calls and all(call.startswith("print ") for call in calls)
    assert result.returncode != 0


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _real_ig_probe_fixture(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "repo"
    target = repo / "skills/earn/capafy-marketing"
    target.mkdir(parents=True)
    shutil.copy2(SCRIPT, target / SCRIPT.name)

    helper = target / "account_state.sh"
    helper.write_text(
        "capafy_ig_accounts_file(){ printf '%s\\n' \"$CAPAFY_FIXTURE_ACCOUNTS\"; }\n"
        "resolve_capafy_ig_handle(){ printf 'fixture'; }\n"
        "resolve_capafy_ig_port(){ printf '9332'; }\n"
        "resolve_capafy_ig_started_warming(){ printf '2020-01-01'; }\n"
        "capafy_ig_provision_reason(){ return 0; }\n",
        encoding="utf-8",
    )

    engine = repo / "skills/earn/marketing-engine"
    engine.mkdir(parents=True)
    for name in ("provision_prompt.sh", "load_manifest.sh"):
        shutil.copy2(ROOT / "skills/earn/marketing-engine" / name, engine / name)
    (engine / "manifests").mkdir()
    shutil.copy2(
        ROOT / "skills/earn/marketing-engine/manifests/capafy.manifest.sh",
        engine / "manifests/capafy.manifest.sh",
    )

    # These files fail the test if the probe unexpectedly advances into side-effecting work.
    side_effects = tmp_path / "side-effects.calls"
    scripts = target / "scripts"
    scripts.mkdir(parents=True)
    for name in ("ig_metrics.py", "pull_attribution.py", "build_landing.py"):
        (scripts / name).write_text(
            "import os\n"
            "with open(os.environ['CAPAFY_SIDE_EFFECTS'], 'a', encoding='utf-8') as f:\n"
            f"    f.write('{name}\\n')\n",
            encoding="utf-8",
        )
    _write_executable(
        engine / "run_agent.sh",
        "#!/bin/sh\nprintf '%s\\n' run_agent >> \"$CAPAFY_SIDE_EFFECTS\"\nexit 99\n",
    )

    browser = repo / "skills/browser/scripts/cdp_context_lease.py"
    browser.parent.mkdir(parents=True)
    browser.write_text(
        "import os, sys\n"
        "with open(os.environ['CAPAFY_LEASE_CALLS'], 'a', encoding='utf-8') as f:\n"
        "    f.write(' '.join(sys.argv[1:]) + '\\n')\n",
        encoding="utf-8",
    )

    home = tmp_path / "home"
    (home / ".local/state/life-manager/logs").mkdir(parents=True)
    accounts = home / ".cloak/accounts.json"
    accounts.parent.mkdir(parents=True, exist_ok=True)
    accounts.write_text("[]\n", encoding="utf-8")
    safe_calls = tmp_path / "launchctl-safe.calls"
    safe = tmp_path / "launchctl-safe"
    _write_executable(
        safe,
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$CAPAFY_SAFE_CALLS\"\n"
        "exit 99\n",
    )
    return {
        "repo": repo,
        "target": target,
        "home": home,
        "accounts": accounts,
        "safe": safe,
        "safe_calls": safe_calls,
        "lease_calls": tmp_path / "lease.calls",
        "side_effects": side_effects,
    }


def _run_real_ig_probe(tmp_path: Path, *, headless: bool) -> tuple[subprocess.CompletedProcess[str], dict[str, Path]]:
    fixture = _real_ig_probe_fixture(tmp_path)
    env = os.environ | {
        "HOME": str(fixture["home"]),
        "LIFE_MANAGER_REPO": str(fixture["repo"]),
        "CAPAFY_FIXTURE_ACCOUNTS": str(fixture["accounts"]),
        "CAPAFY_LAUNCHCTL_SAFE": str(fixture["safe"]),
        "CAPAFY_LAUNCHCTL_DOMAIN": "gui/501",
        "CAPAFY_SAFE_CALLS": str(fixture["safe_calls"]),
        "CAPAFY_LEASE_CALLS": str(fixture["lease_calls"]),
        "CAPAFY_SIDE_EFFECTS": str(fixture["side_effects"]),
        "CAPAFY_IG_PROBE_ONLY": "1",
    }
    if headless:
        env["CAPAFY_HEADLESS_BRIDGE"] = "1"
    result = subprocess.run(
        ["bash", str(fixture["target"] / SCRIPT.name)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, fixture


def test_real_ig_headless_bridge_reaches_probe_without_safe_or_side_effects(tmp_path: Path):
    result, fixture = _run_real_ig_probe(tmp_path, headless=True)

    assert result.returncode == 0, result.stderr
    assert "active_handle=fixture" in result.stdout
    assert "provision_needed=no" in result.stdout
    assert not fixture["safe_calls"].exists()
    assert not fixture["lease_calls"].exists()
    assert not fixture["side_effects"].exists()


def test_real_ig_normal_mode_remains_fail_closed_before_probe(tmp_path: Path):
    result, fixture = _run_real_ig_probe(tmp_path, headless=False)

    assert result.returncode == 2
    assert fixture["safe_calls"].read_text(encoding="utf-8").splitlines() == [
        "print gui/501/ai.anicca.capafy-goal-monitor",
    ]
    assert "active_handle=fixture" not in result.stdout
    assert not fixture["side_effects"].exists()
