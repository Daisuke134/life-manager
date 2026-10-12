import os
import json
import subprocess
import sys
import shlex
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).resolve().parent / "run.sh"


def _run(tmp_path, free_kib: int, guard_script: str, foundation_script: str = "#!/bin/sh\nexit 1\n",
        extra_env=None, hold_run_lock: bool = False, operator_stop: bool = False):
    home = tmp_path / "home"
    home.mkdir()
    calls = tmp_path / "lm-loop.calls"
    cli = tmp_path / "lm-loop"
    cli.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{calls}"\n')
    cli.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Keep the shared gate's OS-owner-home policy scan inside this fixture.
    (bin_dir / "sitecustomize.py").write_text(
        'import os, pwd\nfrom types import SimpleNamespace\n'
        'pwd.getpwuid = lambda uid: SimpleNamespace(pw_dir=os.environ["HOME"])\n'
    )
    host_state = home / ".local/state/life-manager/state"
    if operator_stop:
        host_state.mkdir(parents=True, mode=0o700)
        (host_state / "disk-writers.stop").write_text("owner=operator\n")
    guard = tmp_path / "browser-guard.sh"
    guard.write_text(guard_script)
    guard.chmod(0o755)
    foundation = tmp_path / "ensure_browser.sh"
    foundation.write_text(foundation_script)
    foundation.chmod(0o755)
    resolver = tmp_path / "resolve_cdp_endpoint.py"
    resolver.write_text(
        'import json\nprint(json.dumps({"identity":"fundraiser:fixture",'
        '"endpoint":"http://[::1]:9333","reachable":True}))\n'
    )
    context_lease = tmp_path / "cdp_context_lease.py"
    context_lease.write_text(
        'import json, os, sys\n'
        'with open(os.environ["CONTEXT_LEASE_CALLS"], "a") as f:\n'
        ' f.write(json.dumps({"argv":sys.argv[1:],"endpoint":os.environ.get("CLOAK_CDP_BASE_URL"),'
        '"owner":os.environ.get("CLOAK_BROWSER_OWNER"),'
        '"domains":os.environ.get("CLOAK_CONTEXT_COOKIE_DOMAINS"),'
        '"park_on_idle":os.environ.get("CLOAK_CONTEXT_PARK_ON_IDLE"),'
        '"holder":os.environ.get("AI_BROWSER_HOLDER_PID")})+"\\n")\n'
        'if sys.argv[1] == "acquire":\n'
        ' target_id = None if "--context-only" in sys.argv else "seed-fundraiser"\n'
        ' print(json.dumps({"ok":True,"context_id":"ctx-fundraiser",'
        '"target_id":target_id,"cookies_seeded":4,'
        '"ws":"ws://[::1]:9333/devtools/page/seed"}))\n'
        'else:\n print(json.dumps({"ok":True,"released":sys.argv[2]}))\n'
    )
    if hold_run_lock:
        (home / ".local/state/life-manager/fundraiser/run.lock").mkdir(parents=True)
    df_function = (
        '() { printf "Filesystem 1024-blocks Used Available Capacity Mounted on\\n'
        f'disk 1 1 {free_kib} 1% /\\n"; }}'
    )
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT)],
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "PYTHONPATH": f"{bin_dir}:{os.environ.get('PYTHONPATH', '')}",
            "LIFE_MANAGER_REPO": str(ROOT),
            "LIFE_MANAGER_HOST_STATE_DIR": str(host_state),
            "FUNDRAISER_STATE_ROOT": str(home / ".local/state/life-manager/fundraiser"),
            "LIFE_MANAGER_LOOP_CLI": str(cli),
            "LIFE_MANAGER_BROWSER_GUARD": str(guard),
            "LIFE_MANAGER_BROWSER_FOUNDATION": str(foundation),
            "LIFE_MANAGER_BROWSER_RESOLVER": str(resolver),
            "LIFE_MANAGER_BROWSER_CONTEXT_LEASE": str(context_lease),
            "LIFE_MANAGER_BROWSER_IDENTITY": "fundraiser:fixture",
            "LIFE_MANAGER_BROWSER_TARGET_OWNER": "",
            "CONTEXT_LEASE_CALLS": str(tmp_path / "context-lease.calls"),
            "BASH_FUNC_df%%": df_function,
            "BASH_FUNC_sleep%%": "() { :; }",
            **(extra_env or {}),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return result, calls


def test_low_reported_disk_does_not_preempt_shared_gate(tmp_path):
    result, calls = _run(
        tmp_path, free_kib=1,
        guard_script="#!/bin/sh\necho http://localhost:9222\nexit 0\n",
        hold_run_lock=True,
    )
    assert result.returncode == 0
    assert not calls.exists(), "producer preflight must not mutate shared cleanup"
    assert (tmp_path / "context-lease.calls").exists()
    markers = list((tmp_path / "home" / ".local" / "state" / "life-manager" / "fundraiser" / "effect-markers").glob("*.json"))
    assert len(markers) == 1
    marker = json.loads(markers[0].read_text())
    assert marker["owner_id"] == "fundraiser"
    assert marker["phase"] == "pre_effect"
    assert marker["effect"] == 0


def test_operator_disk_stop_defers_before_browser_dispatch(tmp_path):
    result, calls = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script="#!/bin/sh\necho http://localhost:9222\nexit 0\n",
        hold_run_lock=True, operator_stop=True,
    )
    assert result.returncode == 75
    assert not calls.exists()
    assert not (tmp_path / "context-lease.calls").exists()
    marker_path, = (tmp_path / "home/.local/state/life-manager/fundraiser/effect-markers").glob("*.json")
    marker = json.loads(marker_path.read_text())
    assert (marker["phase"], marker["effect"]) == ("pre_effect", 0)


def test_browser_profile_busy_uses_registered_identity_and_isolated_context(tmp_path):
    # A profile holder can coexist with a task-owned context; stop at run-lock
    # so this test never starts the Fundraiser agent or an external effect.
    result, calls = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script="#!/bin/sh\nexit 9\n",
        foundation_script='#!/bin/sh\nprintf "recovery must not run" >&2\nexit 1\n',
        hold_run_lock=True,
        extra_env={"CLOAK_CONTEXT_PARK_ON_IDLE": ""},
    )
    lease_calls_path = tmp_path / "context-lease.calls"
    assert result.returncode == 0
    assert lease_calls_path.exists()
    lease_calls = [json.loads(line) for line in lease_calls_path.read_text().splitlines()]
    assert [row["argv"][0] for row in lease_calls] == ["acquire", "release"]
    assert lease_calls[0]["argv"] == [
        "acquire", "ai.anicca.fundraiser", "about:blank", "--context-only",
    ]
    assert lease_calls[0]["owner"] == "ai.anicca.fundraiser"
    prompt = (ROOT / "skills/fundraiser-agent/prompts/daily.md").read_text(encoding="utf-8")
    assert prompt.count('--owner "$CLOAK_BROWSER_OWNER"') == 3
    assert lease_calls[0]["endpoint"] == "http://[::1]:9333"
    assert lease_calls[0]["domains"] == "x.com,twitter.com"
    assert lease_calls[0]["park_on_idle"] == "1"
    assert lease_calls[0]["holder"]
    assert not calls.exists() or calls.read_text().strip() == ""


@pytest.mark.parametrize("identity", ["", "interactive:dais"])
def test_missing_or_personal_browser_identity_defers_before_browser_dispatch(tmp_path, identity):
    guard_calls = tmp_path / "guard.calls"
    result, _ = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script=f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{guard_calls}"\necho http://localhost:9222\n',
        hold_run_lock=True,
        extra_env={"LIFE_MANAGER_BROWSER_IDENTITY": identity},
    )
    assert result.returncode == 75
    assert not guard_calls.exists()
    assert not (tmp_path / "context-lease.calls").exists()
    marker_path, = (tmp_path / "home/.local/state/life-manager/fundraiser/effect-markers").glob("*.json")
    marker = json.loads(marker_path.read_text())
    assert (marker["phase"], marker["effect"]) == ("pre_effect", 0)


def test_browser_identity_mismatch_defers_without_shared_browser_recovery(tmp_path):
    # The browser's registry owner performs recovery, never this application pass.
    guard_calls = tmp_path / "guard.calls"
    foundation_calls = tmp_path / "foundation.calls"
    guard_script = f"""#!/bin/sh
printf "%s\\n" "$*" >> "{guard_calls}"
n=$(wc -l < "{guard_calls}")
if [ "$n" -eq 1 ]; then
  exit 10
fi
echo http://[::1]:9333
exit 0
"""
    result, calls = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script=guard_script,
        foundation_script=f'#!/bin/sh\ntouch "{foundation_calls}"\necho RECOVERED\n',
        hold_run_lock=True,
    )
    assert result.returncode == 75
    assert guard_calls.read_text().splitlines() == ["acquire fundraiser:fixture"]
    assert not foundation_calls.exists()
    assert not (tmp_path / "context-lease.calls").exists()


def test_browser_identity_mismatch_with_failed_recovery_defers(tmp_path):
    result, calls = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script="#!/bin/sh\nexit 10\n",
        foundation_script="#!/bin/sh\necho FAILED\n",
    )
    assert result.returncode == 75


def test_invalid_browser_endpoint_is_rejected(tmp_path):
    result, _ = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script="#!/bin/sh\necho http://evil.example.test:9222\nexit 0\n",
    )
    assert result.returncode == 75


def test_leased_ipv6_endpoint_reaches_both_browser_helpers(tmp_path):
    # Missing/ambient CDP must not send nav/eval to a different browser than tab creation.
    captured = tmp_path / "browser-endpoints.json"
    helper_dir = ROOT / "skills/browser/scripts"
    probe = (
        "import cdp, cdp_default_tab, json; "
        f"json.dump([cdp.BASE, cdp_default_tab._cdp_base(), cdp._browser_context_id()], "
        f"open({str(captured)!r}, 'w'))"
    )
    node_probe = (
        f"() {{ PYTHONPATH={shlex.quote(str(helper_dir))} "
        f"{shlex.quote(sys.executable)} -c {shlex.quote(probe)}; return 2; }}"
    )
    result, _ = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script="#!/bin/sh\necho 'http://[::1]:9333'\nexit 0\n",
        extra_env={"BASH_FUNC_node%%": node_probe, "CDP": "http://127.0.0.1:9999"},
    )
    assert result.returncode == 2
    assert json.loads(captured.read_text()) == [
        "http://[::1]:9333", "http://[::1]:9333", "ctx-fundraiser",
    ]


def test_tab_transport_failure_does_not_recover_or_retry_inside_pass(tmp_path):
    captured = tmp_path / "transport-result.json"
    recovery_calls = tmp_path / "recovery.calls"
    recovery = tmp_path / "recovery.sh"
    recovery.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(recovery_calls))}\nexit 0\n")
    helper_dir = ROOT / "skills/browser/scripts"
    probe = "\n".join([
        "import cdp_default_tab, json",
        "calls = []",
        "def operation():",
        "    calls.append(True)",
        "    raise ConnectionError('connection refused')",
        "try:",
        "    cdp_default_tab._run_with_recovery(operation)",
        "except Exception as error:",
        "    result = {'calls': len(calls), 'failure_returned': isinstance(error, ConnectionError)}",
        "else:",
        "    result = {'calls': len(calls), 'failure_returned': False}",
        f"json.dump(result, open({str(captured)!r}, 'w'))",
    ])
    node_probe = (
        f"() {{ PYTHONPATH={shlex.quote(str(helper_dir))} "
        f"{shlex.quote(sys.executable)} -c {shlex.quote(probe)}; return 2; }}"
    )
    result, _ = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script="#!/bin/sh\necho 'http://[::1]:9333'\nexit 0\n",
        extra_env={"BASH_FUNC_node%%": node_probe, "CLOAK_BROWSER_RECOVERY_SCRIPT": str(recovery)},
    )
    assert result.returncode == 2
    assert json.loads(captured.read_text()) == {"calls": 1, "failure_returned": True}
    assert not recovery_calls.exists()
