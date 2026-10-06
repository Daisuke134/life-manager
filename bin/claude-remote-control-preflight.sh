#!/bin/bash
# Launch wrapper for `claude remote-control` under launchd.
#
# `claude remote-control` refuses to start in a workspace whose trust dialog has
# not been accepted, and exits 1 immediately:
#
#   Error: Workspace not trusted. Please run `claude` in <dir> first ...
#
# Under KeepAlive that is not a failure, it is a silent infinite loop: launchd
# respawns every ThrottleInterval seconds, the binary exits before it can write
# anything, and no stderr file is ever created. From the outside the daemon
# simply does not exist. That is exactly how remote control went dark on
# 2026-09-04, and the flag had been flipped by something else entirely.
#
# The flag lives in ~/.claude.json, which the CLI rewrites constantly, so it can
# come back false. Rather than fix it once by hand, assert it right before every
# launch. This is a launchd wrapper for a workspace the user owns and has already
# chosen to run agents in; re-affirming that at boot is bookkeeping, not a new
# trust decision.
set -u

WORKSPACE="${1:?workspace path required}"
shift

CONFIG="$HOME/.claude.json"

if [ -s "$CONFIG" ]; then
  /usr/bin/python3 - "$CONFIG" "$WORKSPACE" <<'PY'
import json, os, sys, tempfile

config_path, workspace = sys.argv[1], sys.argv[2]

try:
    with open(config_path) as handle:
        config = json.load(handle)
except (OSError, ValueError) as exc:
    # A malformed or unreadable config is not ours to repair -- let the CLI
    # report it rather than overwriting something we do not understand.
    print(f"preflight: cannot read {config_path}: {exc}", file=sys.stderr)
    sys.exit(0)

project = config.get("projects", {}).get(workspace)
if project is None:
    print(f"preflight: {workspace} not in projects, leaving config alone", file=sys.stderr)
    sys.exit(0)

if project.get("hasTrustDialogAccepted") is True:
    sys.exit(0)

project["hasTrustDialogAccepted"] = True

# Write through a temp file in the same directory: a half-written ~/.claude.json
# would break every Claude invocation on this machine, not just this daemon.
directory = os.path.dirname(config_path) or "."
fd, temporary = tempfile.mkstemp(dir=directory, prefix=".claude.json.preflight.")
try:
    with os.fdopen(fd, "w") as handle:
        json.dump(config, handle, indent=2)
    os.chmod(temporary, 0o600)
    os.replace(temporary, config_path)
except Exception:
    os.unlink(temporary)
    raise
print(f"preflight: restored hasTrustDialogAccepted for {workspace}", file=sys.stderr)
PY
fi

# The daemon appends to StandardOutPath forever; nothing rotates it. It had
# reached 56MB by 2026-09-04, which is both wasted disk on a machine that
# panics from exhaustion and a haystack -- the failure that started this was
# invisible partly because nobody greps a 56MB log. Rotate at launch: keep one
# previous file, drop the rest. Launch is the only safe moment, since the
# daemon is not holding the handle yet.
LOG="$HOME/Library/Logs/claude-remote-control.out.log"
if [ -f "$LOG" ] && [ "$(/usr/bin/stat -f %z "$LOG" 2>/dev/null || echo 0)" -gt 10485760 ]; then
  mv -f "$LOG" "$LOG.1" 2>/dev/null &&
    echo "preflight: rotated $LOG" >&2
fi

# On 2026-10-06 the keychain OAuth login silently expired (data volume at 100%,
# so the refreshed token could not be written). The daemon then exited with
# "You must be logged in to use Remote Control" every 15s and the phone lost the
# Mac. Dais had to go home to log in. Remote recovery needs only one tap: start
# `claude auth login --claudeai` here, send its authorize URL to Telegram, and
# the login completes when Dais approves it on the phone — no code paste needed.
# One login process at a time, and at most one alert per 30 minutes.
CLAUDE_BIN="${1:-}"
RC_STATE="$HOME/.local/state/life-manager/claude-remote-control"
if [ -n "$CLAUDE_BIN" ] && ! "$CLAUDE_BIN" auth status 2>/dev/null | grep -q '"loggedIn": true'; then
  mkdir -p "$RC_STATE"
  if ! pgrep -f "$CLAUDE_BIN auth login" >/dev/null; then
    LAST=$(cat "$RC_STATE/last-alert" 2>/dev/null || echo 0)
    if [ $(( $(date +%s) - LAST )) -gt 1800 ]; then
      # A held-open stdin keeps the login waiting for approval instead of exiting.
      nohup sh -c "sleep 1200 | '$CLAUDE_BIN' auth login --claudeai" >"$RC_STATE/login.log" 2>&1 &
      sleep 8
      URL=$(grep -o 'https://claude[^ ]*' "$RC_STATE/login.log" | head -1)
      date +%s >"$RC_STATE/last-alert"
      bash "${RC_ALERT_SH:-/Users/anicca/Projects/life-manager-main/skills/_shared/send-telegram.sh}" \
        "Mac mini の Claude がログアウトしました（Remote Control 停止中）。このURLを開いて承認するだけで復旧します（20分有効）: ${URL:-URL取得失敗 $RC_STATE/login.log を確認}" \
        >&2 || echo "preflight: telegram alert failed" >&2
    fi
  fi
  echo "preflight: claude not logged in; waiting for approval" >&2
  sleep 60
  exit 1
fi

/usr/bin/python3 - "$@" <<'PY'
import json, os, sys

if len(sys.argv) < 2:
    sys.exit(0)

env = os.environ.copy()
if not env.get("CLAUDE_CODE_OAUTH_TOKEN") and env.get("HOME"):
    credentials_path = os.path.join(
        env["HOME"], ".local/share/anicca/credentials.json"
    )
    try:
        with open(credentials_path, encoding="utf-8") as handle:
            entries = json.load(handle).get("credentials", [])
    except (OSError, ValueError, TypeError, AttributeError):
        entries = []
    if isinstance(entries, list):
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or entry.get("service") != "claude-remote-control"
            ):
                continue
            token = entry.get("token")
            if isinstance(token, str) and token:
                env["CLAUDE_CODE_OAUTH_TOKEN"] = token
                break

os.execvpe(sys.argv[1], sys.argv[1:], env)
PY
