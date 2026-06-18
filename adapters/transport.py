"""Life Manager transport adapter — Python sibling of adapters/transport.js.
LIFE_TRANSPORT=gog (local, user keys) | composio (cloud, wired in #49).
Consumers call calendar.list/create — never subprocess gog directly. argv-EQUIVALENT
to current call sites (gog flags order-independent, verified gog 0.17.0)."""
import json
import os
import subprocess

GOG_BIN = os.environ.get("GOG_BIN", "gog")


class _GogCalendar:
    def __init__(self, account, keyring):
        self.account = account
        self._env = {**os.environ, "GOG_KEYRING_PASSWORD": keyring or "", "GOG_ACCOUNT": account}

    def _run(self, args, timeout=60):
        return subprocess.run([GOG_BIN, *args, "--account", self.account],
                              capture_output=True, text=True, env=self._env, timeout=timeout)

    def list(self, frm="today", to=None, max=250):
        args = ["calendar", "events", "list", "-j", "--from", frm, "--all-pages", "--max", str(max)]
        if to:
            args += ["--to", to]
        out = self._run(args)
        if out.returncode != 0:
            raise RuntimeError(f"gog list failed: {out.stderr[:200]}")
        d = json.loads(out.stdout)
        return d if isinstance(d, list) else d.get("events", d.get("items", []))

    def create(self, summary, frm, to, location, description, calendar="primary"):
        out = self._run(["calendar", "create", calendar, "-j",
                         "--summary", summary, "--from", frm, "--to", to,
                         "--location", location, "--description", description], timeout=30)
        if out.returncode != 0:
            raise RuntimeError(f"gog create failed: {out.stderr[:200]}")
        try:
            return json.loads(out.stdout)["event"]["id"]
        except Exception:
            return None


class _NyiCalendar:
    def list(self, *a, **k):
        raise RuntimeError("composio transport not wired yet (#49 web app)")

    def create(self, *a, **k):
        raise RuntimeError("composio transport not wired yet (#49 web app)")


def make_transport(account, keyring="", kind=None):
    kind = (kind or os.environ.get("LIFE_TRANSPORT", "gog")).lower()
    cal = _NyiCalendar() if kind == "composio" else _GogCalendar(account, keyring)
    return type("Transport", (), {"calendar": cal})()
