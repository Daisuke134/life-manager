import json
import shlex
import subprocess
from pathlib import Path


HELPER = Path(__file__).resolve().parents[1] / "browser-context-lease.sh"


def test_context_lease_acquire_and_release_scopes_owner_and_cookies(tmp_path):
    calls = tmp_path / "lease.calls"
    lease = tmp_path / "cdp_context_lease.py"
    lease.write_text(
        "import json, os, sys\n"
        "row={'action':sys.argv[1],'owner':sys.argv[2],"
        "'endpoint':os.environ.get('CLOAK_CDP_BASE_URL'),"
        "'domains':os.environ.get('CLOAK_CONTEXT_COOKIE_DOMAINS'),"
        "'holder':os.environ.get('AI_BROWSER_HOLDER_PID')}\n"
        f"with open({str(calls)!r},'a') as f: f.write(json.dumps(row)+'\\n')\n"
        "if sys.argv[1]=='acquire':\n"
        " print(json.dumps({'ok':True,'context_id':'fundraiser-context',"
        "'target_id':'fundraiser-seed','cookies_seeded':4,"
        "'ws':'ws://[::1]:9333/devtools/page/seed'}))\n"
        "else: print(json.dumps({'ok':True,'released':sys.argv[2]}))\n",
        encoding="utf-8",
    )
    script = "\n".join([
        "set -euo pipefail",
        f"source {shlex.quote(str(HELPER))}",
        f"browser_context_lease_acquire http://[::1]:9333 fundraiser x.com,twitter.com {shlex.quote(str(lease))}",
        "printf '%s\\n' \"$BROWSER_CONTEXT_ENDPOINT\" \"$CLOAK_BROWSER_CONTEXT_ID\" "
        "\"$LIFE_MANAGER_BROWSER_CONTEXT_TARGET_ID\" \"$BROWSER_CONTEXT_COOKIE_COUNT\"",
        "browser_context_lease_release",
    ])
    result = subprocess.run(
        ["/bin/bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "http://[::1]:9333",
        "fundraiser-context",
        "fundraiser-seed",
        "4",
    ]
    rows = [json.loads(line) for line in calls.read_text().splitlines()]
    assert [row["action"] for row in rows] == ["acquire", "release"]
    assert all(row["owner"] == "fundraiser" for row in rows)
    assert all(row["endpoint"] == "http://[::1]:9333" for row in rows)
    assert rows[0]["domains"] == "x.com,twitter.com"
    assert rows[0]["holder"]


def test_registered_resolver_returns_the_expected_loopback_identity(tmp_path):
    resolver = tmp_path / "resolver.py"
    resolver.write_text(
        "import json\n"
        "print(json.dumps({'identity':'interactive:dais','endpoint':'http://[::1]:9333'}))\n",
        encoding="utf-8",
    )
    script = "\n".join([
        "set -euo pipefail",
        f"source {shlex.quote(str(HELPER))}",
        f"browser_context_resolve_registered_endpoint interactive:dais {shlex.quote(str(resolver))} {shlex.quote(str(tmp_path / 'browsers.toml'))}",
    ])
    result = subprocess.run(
        ["/bin/bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "http://[::1]:9333"
