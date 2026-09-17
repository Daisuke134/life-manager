import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[4]


def test_owner_uses_shared_browser_lease_and_revenue_name():
    source = (ROOT / "skills/earn/mercor/scripts/application-owner").read_text()
    assert 'TASK="mercor-revenue-application"' in source
    assert 'CDP="http://127.0.0.1:9222"' in source
    assert 'cdp_context_lease.py' in source
    assert 'park "$TASK"' in source
    assert 'MERCOR_CDP_PAGE_WS' in source
    assert 'MERCOR_APPLICATION_STATE_ROOT="$STATE_ROOT"' in source
    assert 'LEGACY_ROOT="${STATE_ROOT:h}"' in source
    assert 'LEASE_PYTHON="${LIFE_MANAGER_LEASE_PYTHON:-/usr/bin/python3}"' in source
    assert "MERCOR_RUN_EARNINGS_SYNC=0" in source
    assert "job_search_loop.mercor_page_ready" in source
    assert '--ws "$MERCOR_CDP_PAGE_WS"' in source
    assert 'commit-cookies "$TASK" --domain mercor.com' in source
    assert "job_search_loop.mercor_auth_readback" in source
    assert "job_search_loop.mercor_email_auth" in source
    assert '--after-epoch "$RUN_STARTED_AT"' in source
    assert '--profile "$HOME/.config/anicca/job-search/profile.json"' in source
    assert source.count('"$ROOT/apps/job-search-loop/scripts/run-mercor.sh"') == 1
    assert source.index("job_search_loop.mercor_auth_readback") < source.index(
        'commit-cookies "$TASK" --domain mercor.com'
    )
    assert '"reason":"authenticated_readback_required"' in source
    assert '--origin https://work.mercor.com --local-storage-key mercor-auth-store' in source
    assert '--session-storage-key mercor-session-id --session-storage-key mercor-user-ip' in source
    assert '--indexeddb firebaseLocalStorageDb/firebaseLocalStorage' in source
    assert 'CLOAK_SESSION_VAULT_WRITEBACK_FILE="$STATE_ROOT/auth-overlay.json"' in source
    assert 'CLOAK_CONTEXT_COOKIE_DOMAINS="mercor.com"' in source
    assert 'LIFE_MANAGER_RESULT_HINT_PATH' in source
    assert 'pre_effect_failure' in source
    reply = (ROOT / "skills/earn/mercor/scripts/reply-owner").read_text()
    assert 'CLOAK_CONTEXT_COOKIE_DOMAINS="mercor.com"' in reply
    assert 'session-writeback.json' in source
    assert '--token "$LEASE_TOKEN" --generation "$LEASE_GENERATION"' in source
    assert "9334" not in source
    assert source.index("commit_auth_writeback") < source.index(
        '"$ROOT/apps/job-search-loop/scripts/run-mercor.sh"'
    )
    assert "firebase_profile_readback_verified" in source
    assert source.index("read_profile_readback_status") < source.index(
        'if [[ "$AUTH_STATUS" == "indeterminate" ]]; then\n  sleep 1'
    )


def test_owner_only_requests_email_auth_after_confirmed_logout():
    source = (ROOT / "skills/earn/mercor/scripts/application-owner").read_text()
    assert 'AUTH_STATUS=' in source
    assert '[[ "$AUTH_STATUS" == "indeterminate" ]]' in source
    assert '[[ "$AUTH_STATUS" == "logged_out" ]]' in source
    assert 'authenticated_readback_required' in source
    assert source.index('[[ "$AUTH_STATUS" == "logged_out" ]]') < source.index(
        "job_search_loop.mercor_email_auth"
    )
    assert source.count('[[ "$AUTH_STATUS" == "logged_out" ]]') >= 2
    assert "second bounded observation" in source


def test_mercor_pass_binds_exact_leased_page():
    source = (ROOT / "apps/job-search-loop/scripts/run-mercor.sh").read_text()
    prompt = (ROOT / "apps/job-search-loop/prompts/mercor-pass.md").read_text()
    assert "--cdp-page-ws" in source
    assert "drive only that exact leased page websocket" in prompt


def test_owner_does_not_release_foreign_lease_when_acquire_is_busy(tmp_path):
    calls = tmp_path / "calls"
    fake_lease_python = tmp_path / "lease-python"
    fake_lease_python.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$2\" >>\"$CALLS\"\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_lease_python.chmod(0o755)
    state_root = tmp_path / "state"
    env = {
        **os.environ,
        "CALLS": str(calls),
        "LIFE_MANAGER_LEASE_PYTHON": str(fake_lease_python),
        "LIFE_MANAGER_PYTHON": "/usr/bin/python3",
        "LIFE_MANAGER_STATE_ROOT": str(state_root),
    }

    result = subprocess.run(
        ["zsh", str(ROOT / "skills/earn/mercor/scripts/application-owner")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert calls.read_text(encoding="utf-8").splitlines() == ["acquire"]


def test_owner_stops_after_failed_profile_readback_without_retrying(tmp_path):
    calls = tmp_path / "calls"
    fake_lease_python = tmp_path / "lease-python"
    fake_lease_python.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "calls = os.environ['CALLS']\n"
        "def log(value):\n"
        "    with open(calls, 'a', encoding='utf-8') as handle: handle.write(value + '\\n')\n"
        "if len(sys.argv) >= 3 and sys.argv[1] != '-m':\n"
        "    command = sys.argv[2]; log(command)\n"
        "    if command == 'acquire':\n"
        "        print(json.dumps({'ok': True, 'ws': 'ws://127.0.0.1:9222/devtools/page/test', 'token': 't', 'generation': 1}))\n"
        "    else: print(json.dumps({'ok': True}))\n"
        "    raise SystemExit(0)\n"
        "if len(sys.argv) >= 3 and sys.argv[1] == '-m':\n"
        "    module = sys.argv[2]; log(module)\n"
        "    output = sys.argv[sys.argv.index('--output') + 1]\n"
        "    if module.endswith('mercor_page_ready'):\n"
        "        payload = {'ok': True, 'url': 'https://work.mercor.com/explore'}\n"
        "        code = 0\n"
        "    else:\n"
        "        payload = {'status': 'indeterminate', 'firebase_profile_readback_verified': False}\n"
        "        code = 2\n"
        "    with open(output, 'w', encoding='utf-8') as handle: json.dump(payload, handle)\n"
        "    raise SystemExit(code)\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    fake_lease_python.chmod(0o755)
    state_root = tmp_path / "state"
    hint = tmp_path / "hint.json"
    env = {
        **os.environ,
        "CALLS": str(calls),
        "LIFE_MANAGER_LEASE_PYTHON": str(fake_lease_python),
        "LIFE_MANAGER_PYTHON": "/usr/bin/python3",
        "LIFE_MANAGER_STATE_ROOT": str(state_root),
        "LIFE_MANAGER_RESULT_HINT_PATH": str(hint),
    }

    result = subprocess.run(
        ["zsh", str(ROOT / "skills/earn/mercor/scripts/application-owner")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 75
    observed_calls = calls.read_text(encoding="utf-8").splitlines()
    assert observed_calls.count("job_search_loop.mercor_auth_readback") == 1
    assert "commit-cookies" not in observed_calls
    assert json.loads(hint.read_text(encoding="utf-8")) == {
        "status": "pre_effect_failure",
        "effect": 0,
    }
