import json
import os
import shutil
import subprocess
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[3]


def _write(path, content, *, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o700)


@pytest.mark.parametrize("profile_busy", [True, False])
def test_connector_uses_task_context_without_holding_daily_driver_profile(tmp_path, profile_busy):
    repo = tmp_path / "repo"
    (repo / "skills/connector").mkdir(parents=True)
    (repo / "skills/browser").mkdir(parents=True)
    shutil.copy2(ROOT / "skills/connector/run.sh", repo / "skills/connector/run.sh")
    shutil.copy2(
        ROOT / "skills/browser/browser-context-lease.sh",
        repo / "skills/browser/browser-context-lease.sh",
    )
    _write(repo / "apps/life-manager/lib/connector-minimal-production.js", "// fixture\n")
    _write(repo / "skills/connector/lib/load-connector-env.js", "// fixture\n")
    _write(repo / "skills/connector/lib/native-state.js", "// fixture\n")
    _write(repo / "skills/connector/native-pass.js", "// fixture\n")

    guard_calls = tmp_path / "guard.calls"
    profile_lock = tmp_path / "profile.lock"
    guard_script = (
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {str(guard_calls)!r}\n"
        f"if [ \"$1\" = release ]; then rm -f {str(profile_lock)!r}; exit 0; fi\n"
        "if [ \"$PROFILE_BUSY\" = 1 ]; then exit 9; fi\n"
        f"touch {str(profile_lock)!r}\n"
        "echo 'http://[::1]:9333'\n"
        "exit 0\n"
    )
    _write(
        repo / "skills/browser/browser-guard.sh",
        guard_script,
        executable=True,
    )
    recovery_calls = tmp_path / "recovery.calls"
    _write(
        repo / "skills/browser/ensure_browser.sh",
        f"#!/bin/sh\ntouch {str(recovery_calls)!r}\nexit 1\n",
        executable=True,
    )
    _write(
        repo / "skills/browser/resolve_cdp_endpoint.py",
        "import json\n"
        "print(json.dumps({'identity':'interactive:dais','endpoint':'http://[::1]:9333'}))\n",
    )
    lease_calls = tmp_path / "context.calls"
    _write(
        repo / "skills/browser/scripts/cdp_context_lease.py",
        "import json,os,sys\n"
        "row={'action':sys.argv[1],'owner':sys.argv[2],"
        "'endpoint':os.environ.get('CLOAK_CDP_BASE_URL'),"
        "'domains':os.environ.get('CLOAK_CONTEXT_COOKIE_DOMAINS')}\n"
        f"with open({str(lease_calls)!r},'a') as f: f.write(json.dumps(row)+'\\n')\n"
        "if sys.argv[1]=='acquire':\n"
        " print(json.dumps({'ok':True,'context_id':'connector-context',"
        "'target_id':'connector-seed','cookies_seeded':3,"
        "'ws':'ws://[::1]:9333/devtools/page/seed'}))\n"
        "else: print(json.dumps({'ok':True}))\n",
    )
    _write(repo / "skills/browser/scripts/cdp_tab_gc.py", "raise SystemExit(0)\n")

    native_pass_capture = tmp_path / "native-pass.env"
    fake_node = tmp_path / "node"
    _write(
        fake_node,
        "#!/bin/bash\n"
        "case \"$1\" in\n"
        "  */native-state.js)\n"
        "    case \"$2\" in\n"
        "      token) echo owner-token ;;\n"
        "      acquire) echo '{\"status\":\"acquired\"}' ;;\n"
        "      *) exit 0 ;;\n"
        "    esac ;;\n"
        "  */native-pass.js)\n"
        f"    if [ -e {str(profile_lock)!r} ]; then profile=locked; else profile=unlocked; fi\n"
        f"    printf '%s\\n' \"$CLOAK_BROWSER_CONTEXT_ID\" \"$LIFE_MANAGER_BROWSER_CONTEXT_TARGET_ID\" \"$CLOAK_CDP_BASE_URL\" \"$profile\" > {str(native_pass_capture)!r} ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        executable=True,
    )
    state_home = tmp_path / "state"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ["PATH"],
        "LIFE_MANAGER_STATE_HOME": str(state_home),
        "LM_CONNECTOR_STATE_DIR": str(state_home / "connector-native"),
        "LM_CONNECTOR_SHARED_ENV_FILE": str(tmp_path / "shared.env"),
        "NODE_BIN": str(fake_node),
        "LIFE_MANAGER_BROWSER_IDENTITY": "interactive:dais",
        "LIFE_MANAGER_BROWSER_TARGET_OWNER": "life-manager-connector-native",
        "LIFE_MANAGER_BROWSER_RESOLVER": str(repo / "skills/browser/resolve_cdp_endpoint.py"),
        "LIFE_MANAGER_BROWSER_CONTEXT_LEASE": str(repo / "skills/browser/scripts/cdp_context_lease.py"),
        "LIFE_MANAGER_BROWSER_TAB_GC": str(repo / "skills/browser/scripts/cdp_tab_gc.py"),
        "AI_BROWSER_REGISTRY": str(tmp_path / "browsers.toml"),
        "NATIVE_PASS_CAPTURE": str(native_pass_capture),
        "PROFILE_BUSY": "1" if profile_busy else "0",
    }
    (tmp_path / "home").mkdir()
    result = subprocess.run(
        ["/bin/bash", str(repo / "skills/connector/run.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert native_pass_capture.read_text().splitlines() == [
        "connector-context",
        "connector-seed",
        "http://[::1]:9333",
        "unlocked",
    ]
    rows = [json.loads(line) for line in lease_calls.read_text().splitlines()]
    assert [row["action"] for row in rows] == ["acquire", "release"]
    assert all(row["owner"] == "life-manager-connector-native" for row in rows)
    assert all(row["endpoint"] == "http://[::1]:9333" for row in rows)
    assert rows[0]["domains"] == "luma.com"
    assert guard_calls.read_text().splitlines() == (
        ["acquire interactive:dais"]
        if profile_busy else ["acquire interactive:dais", "release interactive:dais"]
    )
    assert not recovery_calls.exists()
