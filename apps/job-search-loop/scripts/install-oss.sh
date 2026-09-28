#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/runtime-paths.sh"
COMMAND="${1:-auto}"
[[ "$#" -eq 0 ]] || shift

usage() {
  print -u2 "usage: $0 {preflight|prepare|start|status|finished|outcomes|stop|uninstall} [--answers /absolute/profile-answers.json]"
}

preflight() {
  local darwin=false arm64=false python_ready=false codex_cli=false codex_authenticated=false cloakbrowser=false disk_headroom=false
  [[ "$(uname -s 2>/dev/null)" == "Darwin" ]] && darwin=true
  [[ "$(uname -m 2>/dev/null)" == "arm64" ]] && arm64=true
  "$JOB_SEARCH_PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 13))' >/dev/null 2>&1 && python_ready=true
  if command -v codex >/dev/null 2>&1; then
    codex_cli=true
    codex login status >/dev/null 2>&1 && codex_authenticated=true
  fi
  for candidate in "$HOME"/.cloakbrowser/chromium-*/Chromium.app/Contents/MacOS/Chromium(N); do
    [[ -x "$candidate" ]] && cloakbrowser=true && break
  done
  local required_kib="${JOB_SEARCH_OSS_REQUIRED_KIB:-524288}"
  df -Pk "$HOME" 2>/dev/null | awk -v required="$required_kib" 'NR==2 {found=1; ok=($4 >= required)} END {exit !(found && ok)}' && disk_headroom=true
  local readiness_status=blocked code=2
  if $darwin && $arm64 && $python_ready && $codex_cli && $codex_authenticated && $cloakbrowser && $disk_headroom; then
    readiness_status=ready
    code=0
  fi
  printf '{"status":"%s","darwin":%s,"arm64":%s,"python":%s,"codex_cli":%s,"codex_authenticated":%s,"cloakbrowser":%s,"disk_headroom":%s}\n' \
    "$readiness_status" "$darwin" "$arm64" "$python_ready" "$codex_cli" "$codex_authenticated" "$cloakbrowser" "$disk_headroom"
  return "$code"
}

prepare() {
  [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || {
    print -u2 "[job-hunter] requires Apple Silicon macOS"
    return 2
  }
  if ! command -v brew >/dev/null 2>&1; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
  if ! "$JOB_SEARCH_PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 13))' >/dev/null 2>&1; then
    brew install python@3.14
  fi
  local venv="${XDG_DATA_HOME:-$HOME/.local/share}/anicca/job-search/venv"
  [[ -x "$venv/bin/python" ]] || "$JOB_SEARCH_PYTHON" -m venv "$venv"
  "$venv/bin/python" -c 'import cloakbrowser' >/dev/null 2>&1 || "$venv/bin/pip" install cloakbrowser
  if ! command -v codex >/dev/null 2>&1; then
    local installer
    installer="$(mktemp -t codex-install.XXXXXX)"
    curl -fsSL https://chatgpt.com/codex/install.sh -o "$installer"
    /bin/bash "$installer"
    rm -f "$installer"
  fi
  if ! command -v gog >/dev/null 2>&1; then
    brew install gogcli
  fi
  if ! codex login status >/dev/null 2>&1; then
    codex login
    codex login status >/dev/null 2>&1 || {
      print -u2 "[job-hunter] Codex login was not confirmed"
      return 2
    }
  fi
  local chromium_found=false
  for candidate in "$HOME"/.cloakbrowser/chromium-*/Chromium.app/Contents/MacOS/Chromium(N); do
    [[ -x "$candidate" ]] && chromium_found=true && break
  done
  if ! $chromium_found; then
    "$venv/bin/python" -c 'from cloakbrowser import launch; browser=launch(headless=True); browser.close()'
  fi
  preflight
}

configure_connectors() {
  local email private_dir telegram_env keyring_password bot_token chat_id
  email=$("$JOB_SEARCH_JQ" -er '.candidate.application_email' "$JOB_SEARCH_PROFILE")
  private_dir="${XDG_CONFIG_HOME:-$HOME/.config}/anicca/job-search"
  telegram_env="$private_dir/telegram.env"
  mkdir -p "$private_dir"
  chmod 700 "$private_dir"

  source "$SCRIPT_DIR/private-env.sh"
  if ! job_search_load_private_env GOG_KEYRING_PASSWORD; then
    print -u2 "Create a local Gmail keyring password. It stays on this Mac."
    read -s "keyring_password?Gmail keyring password: "
    print -u2
    [[ -n "$keyring_password" ]] || {
      print -u2 "[job-hunter] Gmail keyring password is required"
      return 2
    }
    printf '%s' "$keyring_password" | "$JOB_SEARCH_PYTHON" -c '
import os,shlex,sys,tempfile
from pathlib import Path
path=Path(sys.argv[1]); value=sys.stdin.read()
path.parent.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(path.parent,0o700)
fd,name=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
try:
 os.fchmod(fd,0o600)
 with os.fdopen(fd,"w",encoding="utf-8") as f:
  f.write("GOG_KEYRING_PASSWORD="+shlex.quote(value)+"\n"); f.flush(); os.fsync(f.fileno())
 os.replace(name,path)
finally:
 try: os.unlink(name)
 except FileNotFoundError: pass
' "$JOB_SEARCH_PRIVATE_ENV"
    typeset -gx GOG_KEYRING_PASSWORD="$keyring_password"
  fi
  if ! gog auth list --json --no-input 2>/dev/null | "$JOB_SEARCH_PYTHON" -c '
import json,sys
v=json.load(sys.stdin); want=sys.argv[1]
raise SystemExit(0 if any(x.get("email")==want and "gmail" in (x.get("services") or []) for x in v.get("accounts",[])) else 1)
' "$email"; then
    gog auth add "$email" --services gmail
  fi

  if [[ ! -f "$telegram_env" ]]; then
    print -u2 "Create a Telegram bot with @BotFather, open its chat, then enter the private values below."
    read -s "bot_token?Telegram bot token: "
    print -u2
    read "chat_id?Telegram chat ID: "
    [[ -n "$bot_token" && "$chat_id" == <-> ]] || {
      print -u2 "[job-hunter] valid Telegram bot token and numeric chat ID are required"
      return 2
    }
    printf '%s\n%s' "$bot_token" "$chat_id" | "$JOB_SEARCH_PYTHON" -c '
import os,shlex,sys,tempfile
from pathlib import Path
path=Path(sys.argv[1]); token,chat=sys.stdin.read().splitlines()
path.parent.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(path.parent,0o700)
fd,name=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
try:
 os.fchmod(fd,0o600)
 with os.fdopen(fd,"w",encoding="utf-8") as f:
  f.write("TELEGRAM_BOT_TOKEN="+shlex.quote(token)+"\n")
  f.write("JOB_SEARCH_TELEGRAM_CHAT_ID="+shlex.quote(chat)+"\n")
  f.flush(); os.fsync(f.fileno())
 os.replace(name,path)
finally:
 try: os.unlink(name)
 except FileNotFoundError: pass
' "$telegram_env"
  fi
}

record_state() {
  local state="$1"
  "$JOB_SEARCH_PYTHON" - "$JOB_SEARCH_INSTALL_CONFIG" "$state" <<'PY'
import json, os, sys, tempfile
from pathlib import Path
path, state = Path(sys.argv[1]), sys.argv[2]
value = json.loads(path.read_text(encoding="utf-8"))
value["oss_onboarding"] = {
    "state": state,
    "browser_profile_ref": "browser-profile://cloakbrowser/job-search-daily",
}
fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(name, path)
finally:
    try: os.unlink(name)
    except FileNotFoundError: pass
PY
}

start_setup() {
  local answers="" replace=0
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --answers) [[ "$#" -ge 2 ]] || { usage; return 2; }; answers="$2"; shift 2 ;;
      --replace) replace=1; shift ;;
      *) usage; return 2 ;;
    esac
  done
  [[ "${JOB_SEARCH_OSS_SKIP_PREP:-0}" == "1" ]] || prepare >/dev/null
  if [[ ! -f "$JOB_SEARCH_PROFILE" || "$replace" == "1" ]]; then
    local profile_args=()
    [[ -z "$answers" ]] || profile_args+=(--answers "$answers")
    [[ "$replace" == "0" ]] || profile_args+=(--replace)
    "$SCRIPT_DIR/setup-profile.sh" "${profile_args[@]}"
  fi
  configure_connectors
  local install_args=(--profile "$JOB_SEARCH_PROFILE" --provider auto --scheduler none)
  [[ "$replace" == "0" ]] || install_args+=(--replace-profile)
  "$SCRIPT_DIR/install-local.sh" "${install_args[@]}" >/dev/null
  "$SCRIPT_DIR/install-launchd.sh" --browser-only
  local ready=false
  for _ in {1..30}; do
    if curl -fsS --max-time 3 http://localhost:9222/json/version >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 1
  done
  $ready || { print -u2 "[job-hunter] dedicated browser did not become ready"; return 2; }
  curl -fsS -X PUT 'http://localhost:9222/json/new?https%3A%2F%2Faccounts.google.com%2F' >/dev/null || true
  record_state browser_ready
  cat <<'GUIDE'

Job Hunter setup is open in the dedicated Life Manager browser.
Complete Google login only on the official page. Workday tenant accounts are created or
reused later by the loop for each fit-qualified job; do not send Life Manager a password,
OTP, identity document, or private legal value.

When Google is ready, return to Terminal and run the same public command again.
Recovery command from this checkout: ./install.sh job-hunter finished
GUIDE
}

status() {
  if [[ ! -f "$JOB_SEARCH_PROFILE" || ! -f "$JOB_SEARCH_INSTALL_CONFIG" ]]; then
    print '{"status":"uninitialized"}'
    return 2
  fi
  local browser=false stage=profile_ready
  curl -fsS --max-time 3 http://localhost:9222/json/version >/dev/null 2>&1 && browser=true
  stage=$("$JOB_SEARCH_PYTHON" - "$JOB_SEARCH_INSTALL_CONFIG" <<'PY'
import json,sys
from pathlib import Path
v=json.loads(Path(sys.argv[1]).read_text())
print((v.get("oss_onboarding") or {}).get("state") or "profile_ready")
PY
  )
  local result=needs_setup code=2
  [[ "$stage" == "activated" && "$browser" == "true" ]] && result=ready code=0
  printf '{"status":"%s","profile":true,"browser":%s,"stage":"%s"}\n' "$result" "$browser" "$stage"
  return "$code"
}

finished() {
  [[ -f "$JOB_SEARCH_PROFILE" && -f "$JOB_SEARCH_INSTALL_CONFIG" ]] || {
    print '{"status":"blocked","missing":["profile"]}'
    return 2
  }
  curl -fsS --max-time 3 http://localhost:9222/json/version >/dev/null 2>&1 || {
    print '{"status":"blocked","missing":["browser"]}'
    return 2
  }
  if ! preflight >/dev/null; then
    print '{"status":"blocked","missing":["machine_preflight"]}'
    return 2
  fi
  source "$SCRIPT_DIR/private-env.sh"
  if ! job_search_load_private_env GOG_KEYRING_PASSWORD || ! command -v gog >/dev/null 2>&1; then
    print '{"status":"blocked","missing":["gmail"]}'
    return 2
  fi
  local connector_receipt="$JOB_SEARCH_STATE_ROOT/connector-preflight.json"
  export PYTHONPATH="$JOB_SEARCH_APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
  if ! "$JOB_SEARCH_PYTHON" -m job_search_loop.connector_preflight \
    --profile "$JOB_SEARCH_PROFILE" \
    --outbox "$JOB_SEARCH_STATE_ROOT/telegram-outbox.sqlite3" \
    --output "$connector_receipt"; then
    print '{"status":"blocked","missing":["gmail_or_telegram"]}'
    return 2
  fi
  "$SCRIPT_DIR/install-launchd.sh"
  record_state activated
  "$JOB_SEARCH_PYTHON" - "$connector_receipt" <<'PY'
import json,sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps({
    "status":"ready",
    "gmail":"ready",
    "telegram":"ready",
    "telegram_message_id":value["telegram"]["message_id"],
    "owners":5,
}, sort_keys=True))
PY
}

outcomes() {
  "$JOB_SEARCH_PYTHON" - "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" <<'PY'
import json, sqlite3, sys
from pathlib import Path
path=Path(sys.argv[1])
count=0
if path.is_file():
    with sqlite3.connect(path) as db:
        count=db.execute("SELECT COUNT(*) FROM applications WHERE current_state='submitted'").fetchone()[0]
print(json.dumps({"status":"ready" if count else "waiting", "receipts":[{"receipt_id":"application","state":"proven","count":count}] if count else []}, sort_keys=True))
PY
}

stop_or_uninstall() {
  local uninstall="$1" domain="gui/$(id -u)"
  for label in ai.anicca.job-search-browser ai.anicca.job-search-daily ai.anicca.job-search-inbox ai.anicca.job-search-learning ai.anicca.job-search-health; do
    "$JOB_SEARCH_LAUNCHCTL" bootout "$domain/$label" >/dev/null 2>&1 || true
    [[ "$uninstall" == "uninstall" ]] && rm -f "$JOB_SEARCH_LAUNCH_AGENT_DIR/$label.plist"
  done
  printf '{"status":"%s","private_state":"preserved"}\n' "$uninstall"
}

case "$COMMAND" in
  auto) [[ -f "$JOB_SEARCH_INSTALL_CONFIG" ]] && finished || start_setup "$@" ;;
  preflight) preflight ;;
  prepare) prepare ;;
  start) start_setup "$@" ;;
  status) status ;;
  finished) finished ;;
  outcomes) outcomes ;;
  stop) stop_or_uninstall stop ;;
  uninstall) stop_or_uninstall uninstall ;;
  -h|--help|help) usage ;;
  *) usage; exit 2 ;;
esac
