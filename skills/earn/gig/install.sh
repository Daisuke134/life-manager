#!/usr/bin/env bash
set -euo pipefail

GIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "help" ]; then
  cat <<'HELP'
Usage: ./install.sh coconala [command]

Without a command, prepare the Mac, authenticate Codex, open the dedicated Coconala
browser, and show the one-session account/SMS/seller/eKYC/bank checklist.

Commands:
  preflight  Read machine/browser/Codex readiness; make no changes
  prepare    Install only missing public dependencies and authenticate Codex
  start      Start or resume the guided official Coconala setup
  finished   Verify the completed setup in the same browser and start eligible loops
  status     Print the secret-free private onboarding state
  outcomes   Print customer-safe official outcome receipt states
  stop       Stop the six Coconala jobs and preserve definitions/private state
  uninstall  Stop jobs, remove their six plist files, and preserve private state
HELP
  exit 0
fi

if [ "${1:-}" = "preflight" ]; then
  darwin=false; arm64=false; python=false; codex_cli=false
  codex_authenticated=false; cloakbrowser=false

  [ "$(uname -s 2>/dev/null)" = "Darwin" ] && darwin=true
  [ "$(uname -m 2>/dev/null)" = "arm64" ] && arm64=true
  if command -v python3 >/dev/null 2>&1 \
    && python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 13))' >/dev/null 2>&1; then
    python=true
  fi
  if command -v codex >/dev/null 2>&1; then
    codex_cli=true
    codex login status >/dev/null 2>&1 && codex_authenticated=true
  fi
  for candidate in "$HOME"/.cloakbrowser/chromium-*/Chromium.app/Contents/MacOS/Chromium; do
    [ -x "$candidate" ] && cloakbrowser=true && break
  done
  status=blocked; exit_code=2
  if $darwin && $arm64 && $python && $codex_cli && $codex_authenticated \
    && $cloakbrowser; then
    status=ready; exit_code=0
  fi
  printf '{"status":"%s","darwin":%s,"arm64":%s,"python":%s,"codex_cli":%s,"codex_authenticated":%s,"cloakbrowser":%s}\n' \
    "$status" "$darwin" "$arm64" "$python" "$codex_cli" "$codex_authenticated" "$cloakbrowser"
  exit "$exit_code"
fi

if [ "${1:-}" = "prepare" ]; then
  [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] || {
    echo "[coconala] requires Apple Silicon macOS" >&2; exit 2;
  }
  if ! command -v python3 >/dev/null 2>&1 \
    || ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 13))' >/dev/null 2>&1; then
    if ! command -v brew >/dev/null 2>&1; then
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    brew install python@3.14
  fi

  venv="$HOME/.local/share/anicca/gig/venv"
  if [ ! -x "$venv/bin/python" ]; then
    python3 -m venv "$venv"
  fi
  if ! "$venv/bin/python" -c 'import websockets, bs4, jsonschema, cloakbrowser, PIL' >/dev/null 2>&1; then
    "$venv/bin/pip" install websockets beautifulsoup4 jsonschema cloakbrowser pillow
  fi
  "$venv/bin/python" "$GIG_DIR/scripts/coconala_onboarding.py" configure-python \
    --python "$venv/bin/python" >/dev/null

  if ! command -v codex >/dev/null 2>&1; then
    installer="$(mktemp -t codex-install.XXXXXX)"
    trap 'rm -f "$installer"' EXIT
    curl -fsSL https://chatgpt.com/codex/install.sh -o "$installer"
    /bin/bash "$installer"
    rm -f "$installer"
    trap - EXIT
  fi

  if ! command -v gog >/dev/null 2>&1; then
    brew install gogcli
  fi
  if ! codex login status >/dev/null 2>&1; then
    codex login
    codex login status >/dev/null 2>&1 || {
      echo "[coconala] Codex login was not confirmed" >&2; exit 2;
    }
  fi

  if ! compgen -G "$HOME/.cloakbrowser/chromium-*/Chromium.app/Contents/MacOS/Chromium" >/dev/null; then
    "$venv/bin/python" -c 'from cloakbrowser import launch; browser=launch(headless=True); browser.close()'
  fi
  PYTHON="$venv/bin/python" exec bash "$0" preflight
fi

if [ "${1:-}" = "init" ]; then
  exec "${PYTHON:-python3}" "$GIG_DIR/scripts/coconala_onboarding.py" init
fi

if [ "${1:-}" = "status" ]; then
  venv="$HOME/.local/share/anicca/gig/venv"
  python="${PYTHON:-$venv/bin/python}"
  [ -x "$python" ] || { echo "[coconala] onboarding is not initialized" >&2; exit 2; }
  exec "$python" "$GIG_DIR/scripts/coconala_onboarding.py" status
fi

if [ "${1:-}" = "outcomes" ]; then
  venv="$HOME/.local/share/anicca/gig/venv"
  python="${PYTHON:-$venv/bin/python}"
  [ -x "$python" ] || { echo '{"status":"waiting","receipts":[]}' ; exit 0; }
  exec "$python" "$GIG_DIR/scripts/coconala_outcomes.py"
fi

if [ "${1:-}" = "stop" ] || [ "${1:-}" = "uninstall" ]; then
  labels=(
    ai.anicca.hf-gig-browser ai.anicca.hf-gig-apply-direct
    ai.anicca.hf-gig-reply-detector ai.anicca.hf-gig-storefront-direct
  )
  domain="gui/$(id -u)"
  for label in "${labels[@]}"; do
    /bin/launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
    if [ "$1" = "uninstall" ]; then
      rm -f "$HOME/Library/LaunchAgents/$label.plist"
    fi
  done
  printf '{"status":"%s","jobs":4,"private_state":"preserved"}\n' "$1"
  exit 0
fi

if [ "${1:-}" = "start" ]; then
  preflight="$(bash "$0" prepare)"
  venv="$HOME/.local/share/anicca/gig/venv"
  PYTHON="$venv/bin/python" bash "$0" init >/dev/null
  preflight_sha="$(printf '%s' "$preflight" | shasum -a 256 | awk '{print $1}')"
  "$venv/bin/python" "$GIG_DIR/scripts/coconala_onboarding.py" record \
    --state preflight --evidence-sha256 "$preflight_sha" >/dev/null
  "$venv/bin/python" "$GIG_DIR/scripts/gig_release.py" activate \
    --jobs ai.anicca.hf-gig-browser
  for _ in {1..30}; do
    curl -fsS http://127.0.0.1:9223/json/version >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS http://127.0.0.1:9223/json/version >/dev/null 2>&1 || {
    echo "[coconala] dedicated browser did not become ready" >&2; exit 2;
  }
  curl -fsS -X PUT \
    'http://127.0.0.1:9223/json/new?https%3A%2F%2Fcoconala.com%2Fusers%2Fsignup' \
    >/dev/null
  cat <<'GUIDE'

Coconala setup is open in the dedicated Life Manager browser.
Complete all of these on the official site in that same browser/profile:
  1. Create or recover the Coconala account and verify email
  2. Complete SMS verification
  3. Complete seller information and required consents
  4. Complete smartphone eKYC and wait for approval
  5. Register the matching domestic bank account

Do not send Life Manager your password, OTP, identity document, face image, or bank data.
When every item is complete, return to Life Manager and click Resume.
Recovery-only terminal command: ./install.sh coconala finished
GUIDE
  exit 0
fi

if [ "${1:-}" = "finished" ]; then
  venv="$HOME/.local/share/anicca/gig/venv"
  [ -x "$venv/bin/python" ] || { echo "[coconala] run setup first" >&2; exit 2; }
  curl -fsS http://127.0.0.1:9223/json/version >/dev/null 2>&1 || {
    echo "[coconala] dedicated browser is not running" >&2; exit 2;
  }
  "$venv/bin/python" "$GIG_DIR/scripts/coconala_onboarding_observe.py"
  if ! (
  gog_account="$(gog auth list --json --no-input | "$venv/bin/python" -c '
import json,sys
data=json.load(sys.stdin)
for row in data.get("accounts", []):
    if "gmail" in (row.get("services") or []):
        print(row.get("email") or "")
        break
')"
  if [ -z "$gog_account" ]; then
    printf 'Google email for Coconala reports: ' >&2
    IFS= read -r gog_account
    gog auth add "$gog_account" --services gmail
    gog auth list --json --no-input | "$venv/bin/python" -c '
import json,sys
data=json.load(sys.stdin)
want=sys.argv[1]
raise SystemExit(0 if any(row.get("email")==want and "gmail" in (row.get("services") or []) for row in data.get("accounts", [])) else 2)
' "$gog_account" || { echo "[coconala] Gmail OAuth was not confirmed" >&2; exit 2; }
  fi
  "$venv/bin/python" "$GIG_DIR/scripts/coconala_onboarding.py" configure-email \
    --account "$gog_account" >/dev/null
  nonce="$(printf '%s:%s' "$gog_account" "$(date +%s)" | shasum -a 256 | cut -c1-24)"
  sent="$(gog --account "$gog_account" gmail send --to="$gog_account" \
    --subject="[Life Manager] Coconala ready $nonce" \
    --body="Coconala email reports are connected. receipt:$nonce" --json --no-input)"
  printf '%s' "$sent" | "$venv/bin/python" -c '
import json,sys
value=json.load(sys.stdin)
raise SystemExit(0 if value.get("id") or value.get("messageId") else 2)
' || { echo "[coconala] Gmail setup send was not acknowledged" >&2; exit 2; }
  email_ready=false
  for _ in {1..12}; do
    if gog --account "$gog_account" gmail messages search \
      "in:anywhere newer_than:1d \"$nonce\"" --max=10 --include-body --json --no-input \
      | "$venv/bin/python" -c '
import json,sys
value=json.load(sys.stdin)
rows=value.get("messages", value if isinstance(value, list) else [])
needle=sys.argv[1]
raise SystemExit(0 if any(needle in str(row.get("subject", ""))+str(row.get("body", "")) for row in rows) else 2)
' "$nonce"; then
      email_ready=true
      break
    fi
    sleep 2
  done
  $email_ready || { echo "[coconala] Gmail setup receipt was not found" >&2; exit 2; }
  ); then
    echo "[coconala] Gmail reports are not ready; lanes continue and Terminal outcomes remain available" >&2
  fi
  ready=""
  if ! ready="$("$venv/bin/python" "$GIG_DIR/scripts/coconala_onboarding.py" ready)"; then
    printf '%s\n' "$ready"
    missing="$(printf '%s' "$ready" | "$venv/bin/python" -c \
      'import json,sys; value=json.load(sys.stdin); print((value.get("missing") or [""])[0])')"
    setup_url=""
    case "$missing" in
      authenticated|email_verified) setup_url='https%3A%2F%2Fcoconala.com%2Fusers%2Fsignup' ;;
      sms_verified) setup_url='https%3A%2F%2Fcoconala.com%2Fmypage%2Fsms' ;;
      seller_information) setup_url='https%3A%2F%2Fcoconala.com%2Fmypage%2Fuser_information' ;;
      identity_approved) setup_url='https%3A%2F%2Fcoconala.com%2Fmypage%2Fuser_identification' ;;
      bank_registered) setup_url='https%3A%2F%2Fcoconala.com%2Fmypage%2Fbank' ;;
    esac
    if [ -n "$setup_url" ]; then
      curl -fsS -X PUT "http://127.0.0.1:9223/json/new?$setup_url" >/dev/null
      echo "[coconala] opened the official page for missing gate: $missing" >&2
    else
      echo "[coconala] missing gate: $missing; rerun ./install.sh coconala" >&2
    fi
    exit 2
  fi
  four_lanes="$("$venv/bin/python" "$GIG_DIR/scripts/gig_release.py" activate)"
  launchd_sha="$(printf '%s\n' "$four_lanes" | shasum -a 256 | awk '{print $1}')"
  "$venv/bin/python" "$GIG_DIR/scripts/coconala_onboarding.py" record \
    --state launchd_readback --evidence-sha256 "$launchd_sha" >/dev/null
  printf '%s\n%s\n' "$ready" "$four_lanes"
  exit 0
fi

if [ "$#" -eq 0 ]; then
  receipt="$HOME/.config/anicca/gig/coconala-onboarding.json"
  if [ -f "$receipt" ] \
    && curl -fsS http://127.0.0.1:9223/json/version >/dev/null 2>&1; then
    exec bash "$0" finished
  fi
  exec bash "$0" start
fi

exec "${PYTHON:-python3}" "$GIG_DIR/scripts/money_loop_onboarding.py" "$@"
