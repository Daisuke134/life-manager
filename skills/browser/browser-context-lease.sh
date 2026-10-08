#!/usr/bin/env bash

browser_context_resolve_registered_endpoint() {
  local identity="$1" resolver="$2" registry="$3" payload
  [[ "$identity" =~ ^[a-z0-9][a-z0-9:_-]{1,127}$ ]] || return 2
  [ -f "$resolver" ] || return 2
  payload="$(python3 "$resolver" --registry "$registry" --identity "$identity" 2>/dev/null)" || return 75
  printf '%s\n' "$payload" | python3 -c '
import json,sys
from urllib.parse import urlsplit
try:
    expected=sys.argv[1]
    row=json.load(sys.stdin)
    endpoint=row.get("endpoint")
    parsed=urlsplit(str(endpoint or ""))
    port=parsed.port
    if (row.get("identity") != expected or parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1","localhost","::1"} or not port
        or parsed.username or parsed.password or parsed.path not in {"","/"}
        or parsed.query or parsed.fragment):
        raise ValueError()
    print(endpoint)
except (ValueError, TypeError, json.JSONDecodeError):
    raise SystemExit(1)
' "$identity" 2>/dev/null
}

browser_context_lease_acquire() {
  local endpoint="$1" owner="$2" cookie_domains="$3" lease_script="$4" lease_json
  case "$endpoint" in
    http://127.0.0.1:*|http://localhost:*|http://\[::1\]:*) ;;
    *) return 75 ;;
  esac
  [[ "$owner" =~ ^[A-Za-z0-9._:-]{1,128}$ ]] || return 2
  [ -f "$lease_script" ] || return 2

  BROWSER_CONTEXT_ENDPOINT="$endpoint"
  BROWSER_CONTEXT_OWNER="$owner"
  BROWSER_CONTEXT_LEASE_SCRIPT="$lease_script"
  BROWSER_CONTEXT_LEASED=0
  CLOAK_BROWSER_OWNER="$owner"
  CLOAK_CONTEXT_COOKIE_DOMAINS="$cookie_domains"
  export CLOAK_BROWSER_OWNER CLOAK_CONTEXT_COOKIE_DOMAINS

  if ! lease_json="$(AI_BROWSER_HOLDER_PID=$$ CLOAK_CDP_BASE_URL="$endpoint" \
      CLOAK_CONTEXT_COOKIE_DOMAINS="$cookie_domains" \
      python3 "$lease_script" acquire "$owner" about:blank 2>/dev/null)"; then
    return 75
  fi
  BROWSER_CONTEXT_LEASED=1
  if ! BROWSER_CONTEXT_FIELDS="$(printf '%s\n' "$lease_json" | python3 -c '
import json,re,sys
try:
    row=json.load(sys.stdin)
    context_id=str(row.get("context_id") or "")
    target_id=str(row.get("target_id") or "")
    cookies_seeded=row.get("cookies_seeded")
    if (row.get("ok") is not True or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}",context_id)
        or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}",target_id)
        or isinstance(cookies_seeded,bool) or not isinstance(cookies_seeded,int)
        or cookies_seeded < 1):
        raise ValueError()
    print(context_id)
    print(target_id)
    print(cookies_seeded)
except (ValueError,TypeError,json.JSONDecodeError):
    raise SystemExit(1)
' 2>/dev/null)"; then
    browser_context_lease_release >/dev/null 2>&1 || true
    return 75
  fi

  BROWSER_CONTEXT_ID="${BROWSER_CONTEXT_FIELDS%%$'\n'*}"
  BROWSER_CONTEXT_TARGET_ID="$(printf '%s\n' "$BROWSER_CONTEXT_FIELDS" | sed -n '2p')"
  BROWSER_CONTEXT_COOKIE_COUNT="$(printf '%s\n' "$BROWSER_CONTEXT_FIELDS" | sed -n '3p')"
  CLOAK_CDP_BASE_URL="$endpoint"
  CLOAK_BROWSER_CONTEXT_ID="$BROWSER_CONTEXT_ID"
  LIFE_MANAGER_BROWSER_CONTEXT_TARGET_ID="$BROWSER_CONTEXT_TARGET_ID"
  export CLOAK_CDP_BASE_URL CLOAK_BROWSER_CONTEXT_ID LIFE_MANAGER_BROWSER_CONTEXT_TARGET_ID
  return 0
}

browser_context_lease_release() {
  [ "${BROWSER_CONTEXT_LEASED:-0}" -eq 1 ] || return 0
  if AI_BROWSER_HOLDER_PID=$$ CLOAK_CDP_BASE_URL="$BROWSER_CONTEXT_ENDPOINT" \
      CLOAK_CONTEXT_COOKIE_DOMAINS="$CLOAK_CONTEXT_COOKIE_DOMAINS" \
      python3 "$BROWSER_CONTEXT_LEASE_SCRIPT" release "$BROWSER_CONTEXT_OWNER" >/dev/null 2>&1; then
    BROWSER_CONTEXT_LEASED=0
    return 0
  fi
  return 1
}
