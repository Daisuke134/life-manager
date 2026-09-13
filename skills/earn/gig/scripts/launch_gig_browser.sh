#!/usr/bin/env bash
# Launch the one persistent CloakBrowser process owned by the Gig control plane.
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# The launchd plist points at the stable `current` release symlink. Keep this
# preflight in the executable so the next natural browser start is protected
# without reloading (and evicting) the shared authenticated session.
GIG_DISK_HEADROOM_KIB=524288
GIG_HOST_STATE_DIR="$HOME/.local/state/life-manager/state"
GIG_STATE_DIR="$HOME/gig"
unset GIG_IGNORE_DISK_PRESSURE_BLOCK GIG_IGNORE_DISK_WRITERS_STOP
unset DISK_CONTROL_STATE_DIR OPENCLAW_STATE_DIR LIFE_MANAGER_HOST_STATE_DIR
export GIG_DISK_HEADROOM_KIB GIG_HOST_STATE_DIR GIG_STATE_DIR
GIG_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISK_GUARD="$GIG_SCRIPT_DIR/gig_disk_guard.py"
if ! /usr/bin/python3 "$DISK_GUARD" /usr/bin/true; then
  echo "Gig disk guard blocked browser start" >&2
  exit 1
fi

GIG_BROWSER_PORT="${GIG_BROWSER_PORT:-9223}"
GIG_BROWSER_PROFILE="${GIG_BROWSER_PROFILE:-$HOME/.cloak/profiles/gig-daily-driver}"
GIG_BROWSER_FINGERPRINT="${GIG_BROWSER_FINGERPRINT:-80136}"
GIG_BROWSER_RENDERER_LIMIT="${GIG_BROWSER_RENDERER_LIMIT:-24}"

case "$GIG_BROWSER_PORT" in ''|*[!0-9]*) exit 64 ;; esac
case "$GIG_BROWSER_RENDERER_LIMIT" in ''|*[!0-9]*) exit 64 ;; esac
[ "$GIG_BROWSER_RENDERER_LIMIT" -ge 1 ] && [ "$GIG_BROWSER_RENDERER_LIMIT" -le 64 ] || exit 64
if [ "${GIG_BROWSER_PORT_OWNED:-0}" != 1 ]; then
  PORT_OWNER="${GIG_BROWSER_PORT_OWNER:-$GIG_SCRIPT_DIR/../../../../runtime/host/browser_port_owner.py}"
  [ -f "$PORT_OWNER" ] && [ ! -L "$PORT_OWNER" ] && [ -r "$PORT_OWNER" ] || {
    echo "Gig browser port owner is missing or unsafe" >&2
    exit 1
  }
  if [ -n "${GIG_BROWSER_PORT_STATE_DIR:-}" ]; then
    case "$GIG_BROWSER_PORT_STATE_DIR" in /*) ;; *) exit 64 ;; esac
    exec /usr/bin/python3 -I "$PORT_OWNER" run \
      --state-dir "$GIG_BROWSER_PORT_STATE_DIR" \
      --port "$GIG_BROWSER_PORT" \
      --profile "$GIG_BROWSER_PROFILE" \
      --owner hf-gig-browser \
      -- /usr/bin/env GIG_BROWSER_PORT_OWNED=1 "$0"
  fi
  exec /usr/bin/python3 -I "$PORT_OWNER" run \
    --port "$GIG_BROWSER_PORT" \
    --profile "$GIG_BROWSER_PROFILE" \
    --owner hf-gig-browser \
    -- /usr/bin/env GIG_BROWSER_PORT_OWNED=1 "$0"
fi
mkdir -p "$GIG_BROWSER_PROFILE"
chromium_bin="$(
  ls -d "$HOME"/.cloakbrowser/chromium-*/Chromium.app/Contents/MacOS/Chromium \
    2>/dev/null | sort -V | tail -1
)"
[ -x "$chromium_bin" ] || {
  echo "Gig CloakBrowser binary not found" >&2
  exit 69
}

# Chromium 145 offers ML-KEM by default.  The current local network path drops
# its larger TLS ClientHello: curl reaches Coconala, while Chromium establishes
# TCP and then returns ERR_TIMED_OUT.  Chromium's supported temporary policy is
# the vendor-prescribed compatibility switch through version 146:
# https://chromeenterprise.google/policies/#PostQuantumKeyAgreementEnabled
#
# Keep this bounded to the two installed/supported majors.  A later Chromium
# must be re-qualified instead of silently carrying a removed policy forever.
#
# CloakBrowser ships 150+ now, so a machine installing today lands outside that
# range and used to get no switch and not a word about it -- the worst shape this
# failure has, because the symptom is a browser that completes TCP and then times
# out while curl on the same box is fine, with nothing pointing at the cause.
# Say it instead, and still launch: plenty of networks never drop the larger
# ClientHello, and refusing to start would break them for a risk they do not have.
# GIG_BROWSER_TLS_COMPAT=force applies it once someone has qualified a newer major.
apply_tls_compat() {
  /usr/bin/defaults write \
    org.chromium.Chromium PostQuantumKeyAgreementEnabled -bool false
  [ "$(/usr/bin/defaults read \
    org.chromium.Chromium PostQuantumKeyAgreementEnabled)" = "0" ]
}

chromium_version="${chromium_bin#"$HOME/.cloakbrowser/chromium-"}"
chromium_major="${chromium_version%%.*}"
case "${GIG_BROWSER_TLS_COMPAT:-auto}:$chromium_major" in
  auto:145|auto:146|force:*)
    apply_tls_compat || {
      echo "Gig CloakBrowser TLS compatibility policy was not persisted" >&2
      exit 78
    }
    ;;
  *)
    echo "Gig CloakBrowser: Chromium $chromium_major is outside the qualified 145-146 range," \
         "so the ML-KEM compatibility switch was NOT applied. If the site loads under curl but" \
         "this browser times out, that is why -- relaunch with GIG_BROWSER_TLS_COMPAT=force." >&2
    ;;
esac

"$chromium_bin" \
  --no-first-run \
  --no-default-browser-check \
  --password-store=basic \
  --use-mock-keychain \
  --disable-sync \
  --disable-features=MacAppCodeSignClone \
  --no-sandbox \
  --fingerprint="$GIG_BROWSER_FINGERPRINT" \
  --fingerprint-platform=macos \
  --remote-debugging-address=127.0.0.1 \
  --remote-allow-origins='*' \
  --renderer-process-limit="$GIG_BROWSER_RENDERER_LIMIT" \
  --remote-debugging-port="$GIG_BROWSER_PORT" \
  --user-data-dir="$GIG_BROWSER_PROFILE" \
  about:blank &
browser_pid=$!

forward_signal() {
  local signal="$1" status="$2"
  kill "-$signal" "$browser_pid" 2>/dev/null || true
  wait "$browser_pid" 2>/dev/null || true
  exit "$status"
}
trap 'forward_signal TERM 143' TERM
trap 'forward_signal INT 130' INT

# KeepAlive can replace a crashed Chromium, but the replacement is useful only after its
# authenticated state is restored. Wait for this exact child to expose CDP, restore the
# profile's existing vault once, then remain its launchd-supervised parent.
cdp_base="${CLOAK_CDP_BASE_URL:-http://127.0.0.1:$GIG_BROWSER_PORT}"
vault_dir="${SESSION_VAULT_DIR:-$HOME/.cloak/vault/gig-daily-driver}"
vault_helper="${GIG_SESSION_VAULT_HELPER:-$GIG_SCRIPT_DIR/../../../browser/scripts/session_vault.py}"
for _ in $(jot 30); do
  kill -0 "$browser_pid" 2>/dev/null || break
  if /usr/bin/curl -fsS --max-time 1 "$cdp_base/json/version" >/dev/null 2>&1; then
    if [ -r "$vault_dir/auth-state.json" ] && [ -r "$vault_helper" ]; then
      vault_python=/opt/homebrew/bin/python3
      [ -x "$vault_python" ] || vault_python=/usr/bin/python3
      SESSION_VAULT_DIR="$vault_dir" SESSION_VAULT_PORT="$GIG_BROWSER_PORT" \
        CLOAK_CDP_BASE_URL="$cdp_base" \
        "$vault_python" "$vault_helper" restore || \
        echo "Gig CloakBrowser session vault restore failed" >&2
    fi
    break
  fi
  sleep 1
done

if wait "$browser_pid"; then
  exit 0
else
  exit $?
fi
