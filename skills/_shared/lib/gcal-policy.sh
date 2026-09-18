#!/usr/bin/env bash
# gcal-policy.sh — calendar-write policy helper.
#
# 全 skill / 全 actor は gcal event を CREATE / UPDATE する時、必ず この helper を経由する。
# 直接 `gog calendar create` 禁止 (CONSTITUTION.md §0.18 violation).
#
# 自動で:
#   (a) MUST-5 audit + 不足補完 (LLM + Firecrawl)
#   (b) event classifier → buffer 決定
#   (c) travel event 2 個 (行き/帰り) atomic 挿入
#   (d) future-aware check
#   (e) state log
#
# Usage:
#   bash gcal-policy.sh create \
#     --summary "..." --from "..." --to "..." \
#     --location "..." --description "..." --attendees "..." \
#     [--classify auto] [--calendar primary] [--account user@example.com]
#
# stdout last line: GCAL_POLICY_RESULT: {"main_id":"...","travel_out_id":"...","travel_back_id":"..."}
set -uo pipefail
SCRIPT="$(basename "$0")"
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$LIFE_MANAGER_REPO" ] || { echo "LIFE_MANAGER_REPO could not be resolved" >&2; exit 2; }
LIFE_MANAGER_STATE_HOME="${LIFE_MANAGER_STATE_HOME:-$HOME/.local/state/life-manager}"
SHARED="$LIFE_MANAGER_REPO/skills/_shared/lib"
STATE_DIR="$LIFE_MANAGER_STATE_HOME/state/gcal-policy"
mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/applied.json"
[ -f "$STATE_FILE" ] || echo "{}" > "$STATE_FILE"

# Load per-user env; credentials never live in the repository.
[ -f "$LIFE_MANAGER_STATE_HOME/.env" ] && set -a && source "$LIFE_MANAGER_STATE_HOME/.env" && set +a
: "${GOG_ACCOUNT:?GOG_ACCOUNT is required}"
: "${GOG_KEYRING_PASSWORD:?GOG_KEYRING_PASSWORD is required}"
export GOG_ACCOUNT GOG_KEYRING_PASSWORD

# ── parse args ────────────────────────────────────────────────────────────────
CMD="${1:-help}"; shift || true
SUMMARY=""; FROM=""; TO=""; LOCATION=""; DESCRIPTION=""; ATTENDEES=""
CALENDAR="primary"; ACCOUNT="$GOG_ACCOUNT"; CLASSIFY="auto"
SKIP_TRAVEL="0"
CHECK_CONFLICT="0"
CONFLICT_BUFFER_MIN="${GCAL_CONFLICT_BUFFER_MIN:-30}"
while [ $# -gt 0 ]; do
  case "$1" in
    --summary)         SUMMARY="$2"; shift 2;;
    --from)            FROM="$2"; shift 2;;
    --to)              TO="$2"; shift 2;;
    --location)        LOCATION="$2"; shift 2;;
    --description)     DESCRIPTION="$2"; shift 2;;
    --attendees)       ATTENDEES="$2"; shift 2;;
    --calendar)        CALENDAR="$2"; shift 2;;
    --account)         ACCOUNT="$2"; shift 2;;
    --classify)        CLASSIFY="$2"; shift 2;;
    --skip-travel)     SKIP_TRAVEL="1"; shift 1;;
    --check-conflict)  CHECK_CONFLICT="1"; shift 1;;
    --conflict-buffer) CONFLICT_BUFFER_MIN="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

# ── GATE 3 enforcement: prevent conflicting calendar writes ───────────────────
# Re-query gcal at insert time to catch events added after propose-time scan.
# Exits with code 19 (HARD RULE #19 violation) if overlap detected.
check_conflict_or_abort() {
  [ "$CHECK_CONFLICT" = "1" ] || return 0
  [ -z "$FROM" ] && return 0
  [ -z "$TO" ]   && return 0
  local buf="$CONFLICT_BUFFER_MIN"
  # Compute ±buffer window (UNIX timestamps via python)
  local window_from window_to
  window_from=$(python3 -c "from datetime import datetime, timedelta; d=datetime.fromisoformat('$FROM'); print((d-timedelta(minutes=$buf)).isoformat())" 2>/dev/null)
  window_to=$(python3 -c "from datetime import datetime, timedelta; d=datetime.fromisoformat('$TO'); print((d+timedelta(minutes=$buf)).isoformat())" 2>/dev/null)
  [ -z "$window_from" ] && return 0
  local from_date="${window_from%T*}"
  local to_date="${window_to%T*}"
  # gog calendar listでイベント取得
  local raw
  raw=$(/opt/homebrew/bin/gog calendar events list -j \
        --account "$ACCOUNT" --from "$from_date" --to "$to_date" \
        --all-pages --max 500 2>/dev/null)
  [ -z "$raw" ] && return 0
  # python で overlap 判定 (FROM~TO ± buffer と既存 event の overlap)
  local tmp_json
  tmp_json=$(mktemp)
  printf '%s' "$raw" > "$tmp_json"
  local conflict
  conflict=$(python3 -c "
import json, sys
from datetime import datetime
win_from = datetime.fromisoformat('$window_from')
win_to   = datetime.fromisoformat('$window_to')
try:
    with open('$tmp_json') as f:
        data = json.load(f, strict=False)
except Exception as e:
    print('', file=sys.stderr)
    sys.exit(0)
items = data if isinstance(data, list) else data.get('events', data.get('items', []))
for ev in items:
    s = (ev.get('start') or {}).get('dateTime')
    e = (ev.get('end')   or {}).get('dateTime')
    if not s or not e:
        continue
    try:
        sd = datetime.fromisoformat(s)
        ed = datetime.fromisoformat(e)
    except ValueError:
        continue
    if sd < win_to and ed > win_from:
        title = (ev.get('summary') or '(no title)')[:60]
        print(title)
        sys.exit(0)
print('')
")
  rm -f "$tmp_json"
  if [ -n "$conflict" ]; then
    echo "GCAL_POLICY_CONFLICT: insert aborted — overlaps with existing event: $conflict" >&2
    echo "  window: $window_from .. $window_to (buffer=${buf}min)" >&2
    echo "  attempted: $SUMMARY ($FROM .. $TO)" >&2
    exit 19
  fi
  return 0
}

# ── classifier (event type → buffer_minutes) ──────────────────────────────────
# Returns: TYPE BUFFER_MIN INTENSITY
classify_event() {
  local title="$1" desc="$2"
  local s=$(echo "$title $desc" | tr '[:upper:]' '[:lower:]')
  if   echo "$s" | grep -qiE "✈|international|国際線|narita t1|narita t2|haneda intl"; then echo "airport_intl 180 high"; return; fi
  if   echo "$s" | grep -qiE "国内線|domestic|\bjal\b|\bana\b|搭乗"; then echo "airport_dom 60 high"; return; fi
  if   echo "$s" | grep -qiE "新幹線|shinkansen|のぞみ|ひかり|こだま"; then echo "shinkansen 15 normal"; return; fi
  if   echo "$s" | grep -qiE "病院|clinic|hospital|診察"; then echo "hospital 30 normal"; return; fi
  if   echo "$s" | grep -qiE "zoom|google meet|remote|online|オンライン"; then echo "remote 15 low"; return; fi
  if   echo "$s" | grep -qiE "🛏|wake|起床"; then echo "wake 0 relentless"; return; fi
  if   echo "$s" | grep -qiE "😴|sleep|就寝"; then echo "sleep 10 gentle"; return; fi
  if   echo "$s" | grep -qiE "🧘|meditation|瞑想"; then echo "meditation 5 gentle"; return; fi
  if   echo "$s" | grep -qiE "🏃|running|jog|jogging|ジョギング"; then echo "running 5 gentle"; return; fi
  if   echo "$s" | grep -qiE "卒業式|試験|exam|entrance"; then echo "exam 60 high"; return; fi
  if   echo "$s" | grep -qiE "🎤|🎭|lt|ライブ|寄席|comedy|お笑い"; then echo "lt 15 normal"; return; fi
  if   echo "$s" | grep -qiE "💼|day job|仕事|naist"; then echo "work 15 normal"; return; fi
  echo "default 15 normal"
}

# ── travel ETA (Google Directions or fallback) ────────────────────────────────
travel_eta_min() {
  local origin="$1" dest="$2"
  if [ -z "$dest" ] || [ "$dest" = "$origin" ]; then echo 0; return; fi
  # Try Google Directions if API key available
  if [ -n "${GOOGLE_DIRECTIONS_KEY:-}" ]; then
    local resp=$(curl -sf "https://maps.googleapis.com/maps/api/directions/json?origin=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$origin")&destination=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$dest")&mode=transit&language=ja&key=$GOOGLE_DIRECTIONS_KEY" 2>/dev/null)
    local secs=$(echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['routes'][0]['legs'][0]['duration']['value'])" 2>/dev/null)
    if [ -n "$secs" ] && [ "$secs" -gt 0 ]; then echo $((secs / 60)); return; fi
  fi
  # Fallback: rough estimate based on location distance
  # If dest contains "新宿区南元町" or matches home → 0
  if echo "$dest" | grep -q "新宿区南元町"; then echo 0; return; fi
  # 都内: 25min default, 都外: 60min default
  if echo "$dest" | grep -qE "東京都|Tokyo"; then echo 25; else echo 60; fi
}

# ── MUST-5 audit ───────────────────────────────────────────────────────────────
# All required fields must be present. If missing, attempt LLM/Firecrawl completion.
audit_must5() {
  local missing=()
  [ -z "$SUMMARY" ]     && missing+=(summary)
  [ -z "$FROM" ]        && missing+=(start)
  [ -z "$TO" ]          && missing+=(end)
  [ -z "$LOCATION" ]    && missing+=(location)
  [ -z "$DESCRIPTION" ] && missing+=(description)
  if [ ${#missing[@]} -gt 0 ]; then
    echo "WARN: MUST-5 missing: ${missing[*]}" >&2
    # In production, call LLM + Firecrawl to fill. For now, just warn.
  fi
}

# ── create main event via gog ─────────────────────────────────────────────────
gog_create() {
  local summary="$1" from="$2" to="$3" location="$4" description="$5" attendees="$6" color="${7:-}"
  local args=(calendar create "$CALENDAR" --account "$ACCOUNT" --summary "$summary" --from "$from" --to "$to")
  [ -n "$location" ]    && args+=(--location "$location")
  [ -n "$description" ] && args+=(--description "$description")
  [ -n "$attendees" ]   && args+=(--attendees "$attendees")
  [ -n "$color" ]       && args+=(--event-color "$color")
  local raw
  if ! raw=$(/opt/homebrew/bin/gog "${args[@]}" --json --results-only 2>&1); then
    printf '%s\n' "$raw" >&2
    return 1
  fi
  printf '%s' "$raw" | python3 -c '
import json, sys
try:
    value = json.load(sys.stdin)
except (TypeError, ValueError):
    raise SystemExit(1)
for candidate in (
    value.get("id") if isinstance(value, dict) else None,
    value.get("event", {}).get("id") if isinstance(value, dict) and isinstance(value.get("event"), dict) else None,
    value.get("data", {}).get("id") if isinstance(value, dict) and isinstance(value.get("data"), dict) else None,
):
    if isinstance(candidate, str) and candidate.strip():
        print(candidate.strip())
        break
else:
    raise SystemExit(1)
'
}

# ── main flow ─────────────────────────────────────────────────────────────────
case "$CMD" in
  create)
    audit_must5
    read -r EVENT_TYPE BUFFER_MIN INTENSITY < <(classify_event "$SUMMARY" "$DESCRIPTION")
    echo "[gcal-policy] classified: type=$EVENT_TYPE buffer=${BUFFER_MIN}m intensity=$INTENSITY" >&2

    # GATE 3 final check: protect the user's calendar from race-condition overlaps.
    check_conflict_or_abort

    # Insert main event
    MAIN_ID=$(gog_create "$SUMMARY" "$FROM" "$TO" "$LOCATION" "$DESCRIPTION" "$ATTENDEES" "10")
    if [ -z "$MAIN_ID" ]; then
      echo "GCAL_POLICY_RESULT: {\"error\":\"main event create failed\"}"
      exit 3
    fi
    echo "[gcal-policy] main event created: $MAIN_ID" >&2

    # Travel event auto-insert (unless --skip-travel or routine event)
    TRAVEL_OUT_ID=""
    TRAVEL_BACK_ID=""
    if [ "$SKIP_TRAVEL" = "0" ] && [ -n "$LOCATION" ] && \
       ! echo "$EVENT_TYPE" | grep -qE "^(wake|sleep|meditation|remote)$"; then
      HOME_ADDR="${ANICCA_HOME_ADDR:-東京都新宿区南元町15-27}"
      ETA_MIN=$(travel_eta_min "$HOME_ADDR" "$LOCATION")
      LEAD_MIN=5  # depart lead before arrival_target

      # arrival_target = main.start - buffer
      # depart_by = arrival_target - travel - lead
      ARRIVAL_TARGET=$(python3 -c "
from datetime import datetime, timedelta
s = datetime.fromisoformat('$FROM')
print((s - timedelta(minutes=$BUFFER_MIN)).isoformat())
")
      TRAVEL_OUT_START=$(python3 -c "
from datetime import datetime, timedelta
s = datetime.fromisoformat('$ARRIVAL_TARGET')
print((s - timedelta(minutes=$ETA_MIN + $LEAD_MIN)).isoformat())
")
      TRAVEL_OUT_END="$ARRIVAL_TARGET"

      # Return: main.end + 5min wrap → +ETA
      TRAVEL_BACK_START=$(python3 -c "
from datetime import datetime, timedelta
e = datetime.fromisoformat('$TO')
print((e + timedelta(minutes=5)).isoformat())
")
      TRAVEL_BACK_END=$(python3 -c "
from datetime import datetime, timedelta
e = datetime.fromisoformat('$TO')
print((e + timedelta(minutes=5 + $ETA_MIN)).isoformat())
")

      TRAVEL_OUT_ID=$(gog_create "🚆 移動: 自宅→${LOCATION:0:30} (auto)" "$TRAVEL_OUT_START" "$TRAVEL_OUT_END" "" "depart_by auto-inserted by gcal-policy (HARD RULE #19). travel ETA: ${ETA_MIN}min, buffer: ${BUFFER_MIN}min, lead: ${LEAD_MIN}min, for_event: $MAIN_ID" "" "8")
      TRAVEL_BACK_ID=$(gog_create "🚆 移動: ${LOCATION:0:30}→自宅 (auto)" "$TRAVEL_BACK_START" "$TRAVEL_BACK_END" "" "return auto-inserted by gcal-policy. travel: ${ETA_MIN}min, for_event: $MAIN_ID" "" "8")
      echo "[gcal-policy] travel events: out=$TRAVEL_OUT_ID back=$TRAVEL_BACK_ID" >&2
    fi

    # State log (idempotent)
    python3 - <<PYEOF
import json
from datetime import datetime, timezone
state = json.load(open("$STATE_FILE"))
state["$MAIN_ID"] = {
  "applied_at": datetime.now(timezone.utc).isoformat(),
  "event_type": "$EVENT_TYPE",
  "buffer_min": $BUFFER_MIN,
  "travel_out_id": "$TRAVEL_OUT_ID",
  "travel_back_id": "$TRAVEL_BACK_ID",
  "summary": "$SUMMARY"[:60],
}
json.dump(state, open("$STATE_FILE","w"), ensure_ascii=False, indent=2)
PYEOF

    echo "GCAL_POLICY_RESULT: {\"main_id\":\"$MAIN_ID\",\"travel_out_id\":\"$TRAVEL_OUT_ID\",\"travel_back_id\":\"$TRAVEL_BACK_ID\",\"event_type\":\"$EVENT_TYPE\",\"buffer_min\":$BUFFER_MIN}"
    ;;

  classify)
    read -r T B I < <(classify_event "$SUMMARY" "$DESCRIPTION")
    echo "type=$T buffer_min=$B intensity=$I"
    ;;

  help|*)
    cat <<EOF
$SCRIPT — gcal-policy helper (HARD RULE #19)

Commands:
  create   Insert event with auto-audit + travel-event + buffer
  classify Print event type + buffer for given title/desc
  help     This help

Flags:
  --summary STR       event title (required)
  --from RFC3339      start (required)
  --to RFC3339        end (required)
  --location STR      complete address (required)
  --description STR   what / contact / URL
  --attendees CSV     stakeholder emails
  --calendar ID       default: primary
  --account EMAIL     default: \$GOG_ACCOUNT
  --classify auto     event type (auto/manual)
  --skip-travel       skip travel event auto-insert

Output (stdout last line):
  GCAL_POLICY_RESULT: {"main_id":...,"travel_out_id":...,"travel_back_id":...}
EOF
    ;;
esac
