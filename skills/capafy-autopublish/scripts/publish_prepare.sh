#!/usr/bin/env bash
# publish_prepare.sh — DETERMINISTIC first half of a Capafy publish.
#   lint -> clean-WS copy -> publish-init Phase A -> confirmed publish-init ->
#   persist exact edit URL file -> print target pricing.
# After this, the AGENT drives CP1 (Agent-Card save) AGENTICALLY via cp1_agent.py
# (look at screenshots, fix the pricing plan cards, save) until the server shows
# is_confirmed_skills=true — see CP1_AGENTIC.md. Then run publish_finish.sh <agent-id>.
#
# WHY split: the old monolithic drive_cp1.py hardcoded DOM coordinates/positions and
# silently broke when Capafy changed the pricing widget (plan cards re-sort on period
# change -> positional price/cap writes get scrambled -> price tab red -> card never
# saves -> is_confirmed_skills=false -> loop STOP). Per "build agents, don't hardcode", the
# card-save step is now agent-driven, not a brittle script.
#
# Usage: publish_prepare.sh <skill-dir> <LISTING.md> <icon.png> [draft-agent-id]
# Prints (machine-greppable): AGENT_ID, AGENT_VERSION_ID, EDIT_URL_FILE, CONFIG_PATH.
set -euo pipefail

SKILL_DIR="${1:?skill-dir required}"
LISTING="${2:?LISTING.md required}"
ICON="${3:?icon path required}"
REUSE_AGENT_ID="${4:-}"
EXPECTED_UPDATE_ID="${CAPAFY_EXPECTED_AGENT_ID:-}"
EXPECTED_UPDATE_FROM_VERSION="${CAPAFY_EXPECTED_FROM_VERSION_ID:-}"
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/frozen_guard.sh"
_UPDATE_AGENT_ID=""
[ -f "${1:-}/UPDATE.json" ] && _UPDATE_AGENT_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("agent_id") or "")' "${1}/UPDATE.json" 2>/dev/null || true)"
capafy_refuse_frozen "$REUSE_AGENT_ID" "$EXPECTED_UPDATE_ID" "$_UPDATE_AGENT_ID"

# The workflow changes directory to the publisher before it reads LISTING again.
# Resolve caller-relative paths once at the boundary so a valid repo-owned source
# cannot turn into a missing file halfway through a live same-Agent update.
SKILL_DIR="$(cd "$SKILL_DIR" 2>/dev/null && pwd)" || { echo "❌ skill dir not found: $SKILL_DIR"; exit 1; }
LISTING="$(cd "$(dirname "$LISTING")" 2>/dev/null && pwd)/$(basename "$LISTING")"
ICON="$(cd "$(dirname "$ICON")" 2>/dev/null && pwd)/$(basename "$ICON")"

AUTO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUB="$AUTO/vendor/capafy-publisher"
LIFE_MANAGER_STATE_HOME="${LIFE_MANAGER_STATE_HOME:-$HOME/.local/state/life-manager}"
VENV="${CAPAFY_BROWSER_PYTHON:-python3}"
# OpenClaw resolves provider config from the isolated publisher HOME's
# .openclaw/openclaw.json, not from runtime_dir. Give the publisher an isolated HOME so it cannot package the
# operator's live OpenClaw providers. Canonical skill source remains in this repo.
CAPAFY_PUBLISH_HOME_BASE="${CAPAFY_PUBLISH_HOME:-$LIFE_MANAGER_STATE_HOME/runtime/capafy-publisher-home}"
CAPAFY_PUBLISHER_STATE_HOME="${CAPAFY_PUBLISHER_STATE_HOME:-$LIFE_MANAGER_STATE_HOME/runtime/capafy-publisher}"
SKILL_NAME="$(basename "$SKILL_DIR")"
export CAPAFY_PUBLISHER_STATE_HOME
if [ "${CAPAFY_PUBLISH_LOCK_HELD:-}" != "1" ]; then
  exec python3 "$AUTO/scripts/with_publish_lock.py" "$0" "$@"
fi

# launchd and direct recovery runs must use the same private credential SSOT.
# Load names into the process only; never copy values into the repo or output.
for ENV_FILE in "$LIFE_MANAGER_STATE_HOME/.env"; do
  if [ -f "$ENV_FILE" ]; then
    set -a; . "$ENV_FILE" 2>/dev/null; set +a
  fi
done
# Vendored OpenClaw resolution prioritizes these overrides above HOME. An
# inherited operator path would package another profile's model or secrets.
unset OPENCLAW_CONFIG_PATH OPENCLAW_STATE_DIR

step(){ echo ""; echo "━━━ $* ━━━"; }
die(){ echo "❌ $*"; exit 1; }

step "[0] LINT $LISTING"
python3 "$AUTO/scripts/lint_listing.py" "$LISTING" || die "lint FAIL — fix the listing first"
[ -f "$ICON" ] || die "icon not found: $ICON"
[ -d "$SKILL_DIR" ] || die "skill dir not found: $SKILL_DIR"
if [ -f "$SKILL_DIR/UPDATE.json" ] && [ -z "$REUSE_AGENT_ID" ]; then
  [ -n "$EXPECTED_UPDATE_ID" ] && [ -n "$EXPECTED_UPDATE_FROM_VERSION" ] \
    || die "online update requires its exact Agent/source-version precondition"
fi
TITLE="$(grep -A1 '^## Title' "$LISTING" | tail -1)"
# Resolve the Agent identity before writing its package inputs. Existing Agents
# get an ID-owned HOME; fresh candidates get a unique bootstrap HOME.
export HOME="$CAPAFY_PUBLISH_HOME_BASE"
export CAPAFY_PUBLISHER_STATE_HOME
unset CAPAFY_PUBLISH_WORK_DIR
mkdir -p "$CAPAFY_PUBLISH_HOME_BASE"
cd "$PUB" || die "cd PUB"
PRELIST="$(python3 packager.py publish-list 2>/dev/null)" \
  || die "publish-list failed before preparing inputs"
# Same-Agent updates of online agents are not capped by Capafy (measured 2026-10-05);
# only new-Agent creation and rejected retries need a free slot.
FREE_SLOT_ARG=(--require-free-slot)
[ -n "$EXPECTED_UPDATE_ID" ] && FREE_SLOT_ARG=()
PRESELECTOR=(--title "$TITLE" ${FREE_SLOT_ARG[@]+"${FREE_SLOT_ARG[@]}"})
[ -z "$REUSE_AGENT_ID" ] || PRESELECTOR+=(--reuse-agent-id "$REUSE_AGENT_ID")
if [ -n "$EXPECTED_UPDATE_ID$EXPECTED_UPDATE_FROM_VERSION" ]; then
  [ -n "$EXPECTED_UPDATE_ID" ] && [ -n "$EXPECTED_UPDATE_FROM_VERSION" ] \
    && [ -z "$REUSE_AGENT_ID" ] \
    || die "same-Agent update requires an exact Agent/source-version pair"
  PRESELECTOR+=(--expected-agent-id "$EXPECTED_UPDATE_ID" \
                --expected-version-id "$EXPECTED_UPDATE_FROM_VERSION")
fi
PRESELECTED_ID="$(printf '%s' "$PRELIST" | python3 "$AUTO/scripts/select_publish_agent.py" "${PRESELECTOR[@]}")" \
  || die "cannot bind package inputs to a unique Agent"
if [ -n "$PRESELECTED_ID" ]; then
  CAPAFY_PUBLISH_HOME="$CAPAFY_PUBLISH_HOME_BASE/agents/$PRESELECTED_ID"
else
  mkdir -p "$CAPAFY_PUBLISH_HOME_BASE/bootstrap"
  CAPAFY_PUBLISH_HOME="$(mktemp -d "$CAPAFY_PUBLISH_HOME_BASE/bootstrap/$SKILL_NAME.XXXXXX")" \
    || die "could not allocate unique publisher HOME"
fi
WS="$CAPAFY_PUBLISH_HOME/.openclaw/workspace"
[ -z "${CAPAFY_WORKSPACE:-}" ] || [ "$CAPAFY_WORKSPACE" = "$WS" ] \
  || die "CAPAFY_WORKSPACE override is not Agent-isolated"
CFG_ONE="$CAPAFY_PUBLISH_HOME/listing-config.json"
# Keep the icon with the Agent's publisher home. Recording the release path broke
# every later resume once that immutable release was pruned (2026-09-28, 9466718786).
ICON_COPY="$CAPAFY_PUBLISH_HOME/icon.${ICON##*.}"
# An existing Agent never prepared on this host (Slide Maker 8828622062, 2026-09-29)
# has no publisher home yet; create it instead of failing the update.
mkdir -p "$CAPAFY_PUBLISH_HOME" || die "could not create publisher HOME"
# Release files are 0444 and cp keeps that mode, so the second prepare of the same
# Agent could not overwrite its own copy (live 2026-09-29, 1037238583). Replace it.
cp -f "$ICON" "$ICON_COPY" && chmod 600 "$ICON_COPY" || die "icon copy failed"
ICON="$ICON_COPY"
python3 "$AUTO/scripts/build_config.py" "$LISTING" "$ICON" "$CFG_ONE" >/dev/null \
  || die "build_config failed"
if [ -f "$SKILL_DIR/UPDATE.json" ] && [ -z "$REUSE_AGENT_ID" ]; then
  python3 - "$SKILL_DIR/UPDATE.json" "$CFG_ONE" "$EXPECTED_UPDATE_ID" "$EXPECTED_UPDATE_FROM_VERSION" <<'PY' \
    || die "catalog update request differs from Agent/source version/model"
import json,sys
request, config = (json.load(open(path, encoding="utf-8")) for path in sys.argv[1:3])
target_model = request.get("target_model_id")
target_fee = request.get("target_one_time_fee")
if not target_model and not target_fee:
    raise SystemExit(1)
if (str(request.get("agent_id")) != sys.argv[3]
        or str(request.get("from_version_id")) != sys.argv[4]
        or (target_model and target_model != config.get("model_id"))
        or (target_fee and str(target_fee) != str(config.get("one_time_fee")))):
    raise SystemExit(1)
PY
fi
read -r CAPAFY_HOSTED_MODEL_ID CAPAFY_HOSTED_MAX_TOKENS < <(
  python3 - "$CFG_ONE" <<'PY'
import json, sys
config = json.load(open(sys.argv[1], encoding="utf-8"))
print(config["model_id"] or "", config["max_tokens"] or "")
PY
)
export CAPAFY_HOSTED_MODEL_ID CAPAFY_HOSTED_MAX_TOKENS

# Download-mode listings (pricing_mode=download, e.g. a one-time-fee update) have
# no hosted LLM/CP2 — verified 2026-09-28 via publish-remote-status on agent
# 3332784488: agent_type=download, is_confirmed_config_keys=false. Skip the
# OpenRouter key-health gate and hosted-provider config for those; both only
# apply to run_online (subscription) skills.
if [ -n "$CAPAFY_HOSTED_MODEL_ID" ]; then
  step "[0b] KEY-HEALTH GATE (fail-closed) — never publish into an under-funded host key"
  # 2026-07-18 A1: 4 agents were rejected with a billing error caused by a THIN OpenRouter
  # balance (NOT a stale key / NOT the provider-name label). Block the publish here so the
  # loop stops cleanly instead of shipping into a $-low account and getting re-rejected.
  "$AUTO/scripts/key_health_gate.sh" || die "KEY-HEALTH gate FAIL — restore OpenRouter funding (>= \$20 remaining) before publishing; see state/lessons.md"
fi

step "clean-WS copy"
mkdir -p "$WS/skills"
# A clean workspace can contain a previous release-derived copy whose files
# inherited the release's read-only mode. It is runtime state, so make just
# that disposable copy writable before replacing it.
chmod -R u+w "$WS/skills/$SKILL_NAME" 2>/dev/null || true
rm -rf "$WS/skills/$SKILL_NAME" 2>/dev/null
cp -R "$SKILL_DIR" "$WS/skills/$SKILL_NAME" || die "clean-WS copy failed"
# Catalog test/ fixtures are not part of the product; shipping them flipped the
# buyer-facing security scan to 注意 (2026-10-07, hook-lab + marketing-strategist).
chmod -R u+w "$WS/skills/$SKILL_NAME" 2>/dev/null || true
rm -rf "$WS/skills/$SKILL_NAME/test"
# Internal catalog files are not part of the skill. LISTING.md and UPDATE.json carry
# operator notes; 2026-10-08 Hook Lab v1.0.6 was scanned 却下 because one of them
# mentioned removing a test directory for the security scan.
rm -f "$WS/skills/$SKILL_NAME"/LISTING*.md "$WS/skills/$SKILL_NAME"/UPDATE.json "$WS/skills/$SKILL_NAME"/PRICE_*.json "$WS/skills/$SKILL_NAME"/icon.*

# run_online packaging scans the clean runtime, not the operator's ~/.openclaw.
# Give that runtime one explicit hosted provider contract.  Keep only an env
# reference here: CP2 supplies the real key from the private state env.
# Download-mode listings have no hosted model — nothing to write.
if [ -n "$CAPAFY_HOSTED_MODEL_ID" ]; then
  mkdir -p "$CAPAFY_PUBLISH_HOME/.openclaw"
  python3 - "$CAPAFY_PUBLISH_HOME/.openclaw/openclaw.json" "$CAPAFY_HOSTED_MODEL_ID" "$CAPAFY_HOSTED_MAX_TOKENS" <<'PY'
import json, sys
model_id, max_tokens = sys.argv[2], int(sys.argv[3])
json.dump({
  "models": {"providers": {"openrouter": {
    "baseUrl": "https://openrouter.ai/api/v1",
    "api": "openai-responses",
    "apiKey": "${CAPAFY_HOST_OPENROUTER_KEY}",
    "models": [{"id": model_id, "name": model_id, "maxTokens": max_tokens}]
  }}},
  "agents": {"defaults": {"model": {"primary": "openrouter/" + model_id}}}
}, open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
PY
else
  # `publish-init --env openclaw` validates the runtime root before it knows
  # that this is a download-only listing. Download agents deliberately have
  # no model/provider route, but still need a valid root for discovery.
  mkdir -p "$CAPAFY_PUBLISH_HOME/.openclaw"
  printf '{}\n' > "$CAPAFY_PUBLISH_HOME/.openclaw/openclaw.json"
fi

step "[1] publish-init Phase A discovery"
export HOME="$CAPAFY_PUBLISH_HOME"
export CAPAFY_PUBLISHER_STATE_HOME
cd "$PUB" || die "cd PUB"
TITLE="$(grep -A1 '^## Title' "$LISTING" | tail -1)"
# RESUME GUARD: every failed run used to publish-init a NEW draft, so failures piled
# up orphan drafts that eat the 5-slot cap until the loop hard-blocks. Reuse an
# EXACT-title agent that already exists (the "(LM generated…)" auto-stub has a suffix
# so it is NOT matched). The selector consumes only the official 0.9.11 snake_case
# top-level agents array and fails closed on duplicate/invalid rows.
LIST_OUT="$(python3 packager.py publish-list 2>/dev/null)" \
  || die "publish-list failed; cannot select an Agent safely"
SELECTOR_ARGS=(--title "$TITLE" ${FREE_SLOT_ARG[@]+"${FREE_SLOT_ARG[@]}"})
[ -z "$REUSE_AGENT_ID" ] || SELECTOR_ARGS+=(--reuse-agent-id "$REUSE_AGENT_ID")
[ -z "$EXPECTED_UPDATE_ID" ] || SELECTOR_ARGS+=(--expected-agent-id "$EXPECTED_UPDATE_ID" \
                                                   --expected-version-id "$EXPECTED_UPDATE_FROM_VERSION")
if ! ID="$(printf '%s' "$LIST_OUT" | python3 "$AUTO/scripts/select_publish_agent.py" "${SELECTOR_ARGS[@]}")"; then
  die "publish-list Agent selection failed closed (duplicate or invalid official shape)"
fi
[ "$ID" = "$PRESELECTED_ID" ] \
  || die "Agent identity changed after package inputs were prepared"
if [ -n "$REUSE_AGENT_ID" ] && [ "$ID" != "$REUSE_AGENT_ID" ]; then
  die "explicit reuse target is missing or is not draft/review_rejected: $REUSE_AGENT_ID"
fi
if [ -n "$ID" ]; then
  if [ -n "$REUSE_AGENT_ID" ]; then
    echo "REUSE explicit retry agent_id=$ID — not creating a different agent"
  else
    echo "RESUME existing agent_id=$ID (title match) — not creating a new draft"
  fi
  # The publisher resolves this once at Python process startup.  Bind before
  # publish-init so this retry cannot reset or ship a previous agent's state.
  # A scheduler/agent-runner may inherit this from an unrelated prior attempt.
  # Never let that ambient value redirect a resume into another agent's manifest.
  export CAPAFY_PUBLISH_WORK_DIR="$CAPAFY_PUBLISHER_STATE_HOME/work/agents/$ID"
  # BUG FIX 2026-07-17: this branch used to skip publish-init entirely, leaving the
  # LOCAL publish work-state manifest pointed at whatever
  # agent_id a PRIOR run last touched. the final submit then failed closed with
  # "agent_id does not match local publish work-state" — but the old finish
  # fallback treated that failure as benign and resubmitted STALE
  # content unchanged. Rebind local state to THIS agent_id now. If the agent is
  # A previous agent's manifest is deliberately discarded here: publish-init is the
  # boundary that creates this retry's new version and its matching local manifest.
  # Never suppress an init failure. Doing so used to let publish_finish reach submit
  # with a different agent's work-state and fail only after CP1/CP2 work had run.
  DISCOVERY_OUT="$(python3 packager.py publish-init --env openclaw --runtime-dir "$WS" --skill-dir "$WS/skills/$SKILL_NAME" --agent-id "$ID" 2>&1)" \
    || die "Phase A publish-init discovery failed for selected agent_id=$ID"
  DISCOVERY_STATUS="$(printf '%s' "$DISCOVERY_OUT" | python3 -c "import json,sys
try: print(str(json.loads(sys.stdin.read(),strict=False).get('status','')).strip())
except Exception: print('')")"
  [ "$DISCOVERY_STATUS" = "needs_selection" ] \
    || die "Phase A publish-init did not return needs_selection for agent_id=$ID"
  echo "Phase A discovery complete for agent_id=$ID"
  SEL_FILE="$LIFE_MANAGER_STATE_HOME/state/capafy-autopublish/sel_one.json"
  SELECTION_RESULT="$(printf '%s' "$DISCOVERY_OUT" | python3 "$AUTO/scripts/build_publish_selection.py" --skill-dir "$WS/skills/$SKILL_NAME" --title "$TITLE" --agent-id "$ID" --output "$SEL_FILE")" \
    || die "Phase A candidate did not map uniquely to the explicit skill; no init effect attempted"
  SELECTION_FILE="$(printf '%s' "$SELECTION_RESULT" | sed -n 's/^SELECTION_FILE=//p' | tail -1)"
  [ "$SELECTION_FILE" = "$SEL_FILE" ] || die "Phase A selection file path was not returned as expected"
  REBIND_OUT="$(python3 packager.py publish-init --reset-local-state --env openclaw --runtime-dir "$WS" --skill-dir "$WS/skills/$SKILL_NAME" --agent-id "$ID" --selections-file "$SEL_FILE" 2>&1)" \
    || die "could not rebind local publish work-state to selected agent_id=$ID"
  REBOUND_ID="$(printf '%s' "$REBIND_OUT" | python3 -c "import json,sys
try: print(str(json.loads(sys.stdin.read(),strict=False).get('agent_id','')).strip())
except Exception: print('')")"
  [ "$REBOUND_ID" = "$ID" ] \
    || die "publish-init rebound unexpected agent_id=$REBOUND_ID (selected $ID)"
  echo "local publish work-state rebound and verified for agent_id=$ID"
else
  BOOTSTRAP_ROOT="$CAPAFY_PUBLISHER_STATE_HOME/work/bootstrap"
  mkdir -p "$BOOTSTRAP_ROOT"
  BOOTSTRAP_WORK_DIR="$(mktemp -d "$BOOTSTRAP_ROOT/capafy.XXXXXX")"
  export CAPAFY_PUBLISH_WORK_DIR="$BOOTSTRAP_WORK_DIR"
  DISCOVERY_OUT="$(python3 packager.py publish-init --env openclaw --runtime-dir "$WS" --skill-dir "$WS/skills/$SKILL_NAME" 2>&1)" \
    || die "Phase A publish-init discovery failed for new agent"
  DISCOVERY_STATUS="$(printf '%s' "$DISCOVERY_OUT" | python3 -c "import json,sys
try: print(str(json.loads(sys.stdin.read(),strict=False).get('status','')).strip())
except Exception: print('')")"
  [ "$DISCOVERY_STATUS" = "needs_selection" ] \
    || die "Phase A publish-init did not return needs_selection for new agent"
  echo "Phase A discovery complete for new agent"
  SEL_FILE="$LIFE_MANAGER_STATE_HOME/state/capafy-autopublish/sel_one.json"
  SELECTION_RESULT="$(printf '%s' "$DISCOVERY_OUT" | python3 "$AUTO/scripts/build_publish_selection.py" --skill-dir "$WS/skills/$SKILL_NAME" --title "$TITLE" --output "$SEL_FILE")" \
    || die "Phase A candidate did not map uniquely to the explicit skill; no init effect attempted"
  SELECTION_FILE="$(printf '%s' "$SELECTION_RESULT" | sed -n 's/^SELECTION_FILE=//p' | tail -1)"
  [ "$SELECTION_FILE" = "$SEL_FILE" ] || die "Phase A selection file path was not returned as expected"
  INIT_OUT="$(python3 packager.py publish-init --env openclaw --runtime-dir "$WS" --skill-dir "$WS/skills/$SKILL_NAME" --selections-file "$SEL_FILE" 2>&1)" \
    || die "publish-init failed for new agent"
  ID="$(printf '%s' "$INIT_OUT" | python3 -c "import json,sys
try: print(json.loads(sys.stdin.read()).get('agent_id',''))
except: print('')")"
  [ -n "$ID" ] || die "publish-init returned no agent_id (dup title? cap full = 5 unlisted max? see publish-list)"
  AGENT_WORK_DIR="$CAPAFY_PUBLISHER_STATE_HOME/work/agents/$ID"
  mkdir -p "$(dirname "$AGENT_WORK_DIR")"
  [ ! -e "$AGENT_WORK_DIR" ] || die "publisher work-state already exists for new agent_id=$ID"
  mv "$BOOTSTRAP_WORK_DIR" "$AGENT_WORK_DIR" \
    || die "could not bind publish work-state to agent_id=$ID"
  export CAPAFY_PUBLISH_WORK_DIR="$AGENT_WORK_DIR"
fi

python3 "$AUTO/scripts/publish_input_contract.py" write \
  --agent-id "$ID" --skill-name "$SKILL_NAME" --config "$CFG_ONE" \
  --workspace "$WS" --publisher-home "$CAPAFY_PUBLISH_HOME" \
  --work-dir "$CAPAFY_PUBLISH_WORK_DIR" \
  || die "could not bind publisher inputs to agent_id=$ID"
AGENT_VERSION_ID="$(python3 - "$CAPAFY_PUBLISH_WORK_DIR/publisher-inputs.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["agent_version_id"])
PY
)" || die "prepared version identity is missing"

REFRESH_RC=0
RAW="$(python3 packager.py publish-refresh-url --agent-id "$ID" --step init 2>/dev/null)" || REFRESH_RC=$?
[ "$REFRESH_RC" -eq 0 ] || die "publish-refresh-url failed; no edit URL was stored"
EDIT_URL_PATH="$CAPAFY_PUBLISHER_STATE_HOME/review-urls/$ID/init.url"
EDIT_URL_RESULT="$(printf '%s' "$RAW" | python3 "$AUTO/scripts/save_review_url.py" --agent-id "$ID" --output "$EDIT_URL_PATH")" \
  || die "publish-refresh-url response failed strict Agent-ID/URL validation"
EDIT_URL_FILE="$(printf '%s' "$EDIT_URL_RESULT" | sed -n 's/^EDIT_URL_FILE=//p' | tail -1)"
[ "$EDIT_URL_FILE" = "$EDIT_URL_PATH" ] || die "review URL file path was not returned as expected"
step "PREPARE DONE — hand off to agentic CP1"
echo "AGENT_ID=$ID"
echo "AGENT_VERSION_ID=$AGENT_VERSION_ID"
echo "EDIT_URL_FILE=$EDIT_URL_FILE"
echo "CONFIG_PATH=$CFG_ONE"
echo ""
echo "TARGET PRICING (drive each plan card to these EXACT values on the 価格設定 tab):"
python3 - "$CFG_ONE" <<'PY'
import json,sys
c=json.load(open(sys.argv[1]))
if c.get("pricing_mode") == "download":
    print(f"  download : one-time fee ${c['one_time_fee']} (no cap/trial/hosted model — CP2 skipped)")
for p in c["plans"]:
    tr = p.get("trial")
    trial_target = (f"Free Trial {tr['hours']}h / {tr['requests']} requests"
                    if isinstance(tr, dict) else "No Free Trial")
    print(f"  {p['cycle']:5} : price ${p['price']}  cap {p['cap']}  trial={trial_target}")
print("  category:", c.get("category"), "| model:", c.get("model"))
PY
echo ""
echo "NEXT: drive CP1 agentically (CP1_AGENTIC.md), then: publish_finish.sh $ID $SKILL_NAME '$LISTING' $AGENT_VERSION_ID"
