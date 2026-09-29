#!/usr/bin/env bash
# capafy-distribute-daily.sh — Capafy's "broaden" loop (spec 2026-09-29
# "スキルの形"): every money skill pairs a build loop with a distribute loop.
# Capafy already has capafy-loop-daily (build); this is the missing distribute
# loop. Once a day it writes ONE free English article promoting whichever
# Capafy skill made the most money in the last 30 days, with every Capafy link
# carrying ct=<channel>-<skill-slug> for Capafy's own traffic-sources
# attribution, and posts the link to X via Postiz.
#
# Deliberately separate from skills/writer-agent/article-daily.sh rather than
# a mode flag inside it (skills/loop-development/SKILL.md: a loop must not
# modify another loop's code). article-daily.sh's own shared destination
# contract (skills/writer-agent/scripts/publication_contract.py) currently
# keeps devto/en dormant and gates note/Substack/aniccaai.com behind a
# preview+paid split (skills/writer-agent/scripts/self_owned_article.py) with
# no free-article path -- flipping either is a shared-contract change that
# belongs to the Writer loop's own owner, not to this new loop's first PR. See
# "KNOWN GAP" below and the PR description for what unblocks devto.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ARTICLE_ROOT="${ARTICLE_ROOT:-$(cd "$SCRIPT_DIR/../../writer-agent" && pwd -P)}"
# shellcheck source=../writer-agent/scripts/writer-runtime-env.sh
source "$ARTICLE_ROOT/scripts/writer-runtime-env.sh"

CAPAFY_DISTRIBUTE_STATE_DIR="${CAPAFY_DISTRIBUTE_STATE_DIR:-$WRITER_STATE_DIR/capafy-distribute}"
mkdir -p "$CAPAFY_DISTRIBUTE_STATE_DIR"
LOG="${CAPAFY_DISTRIBUTE_LOG:-$WRITER_LOG_DIR/capafy-distribute-daily.log}"
mkdir -p "$(dirname "$LOG")"
echo "=== capafy-distribute-daily run $(date '+%F %T %Z') ===" >>"$LOG"

# Single-owner fence, same tool article-daily.sh uses (writer_owner_fence.py),
# with a distinct owner id so this loop never contends with article-daily's
# own fence for the shared daily-driver / model-runner resources.
if [ "${CAPAFY_DISTRIBUTE_OWNER_FENCE_ACTIVE:-0}" != "1" ]; then
  OWNER_FENCE_DIR="${CAPAFY_DISTRIBUTE_OWNER_FENCE_DIR:-$HOME/.local/state/life-manager/writer/owner-fence-capafy-distribute}"
  export CAPAFY_DISTRIBUTE_OWNER_FENCE_ACTIVE=1
  export CAPAFY_DISTRIBUTE_OWNER_FENCE_DIR="$OWNER_FENCE_DIR"
  exec python3 "$ARTICLE_ROOT/scripts/writer_owner_fence.py" run \
    --fence-dir "$OWNER_FENCE_DIR" --owner capafy-distribute \
    --root "$ARTICLE_ROOT" --state "$CAPAFY_DISTRIBUTE_STATE_DIR" \
    --run-id "${CAPAFY_DISTRIBUTE_EXPECTED_RUN_ID:-capafy-distribute-$(TZ=Asia/Tokyo date +%F)}" \
    -- "$0" "$@"
fi

SELF_DIR="$SCRIPT_DIR/scripts"
LEDGER="$CAPAFY_DISTRIBUTE_STATE_DIR/ledger.json"
JST_DATE="$(TZ=Asia/Tokyo date +%F)"
CHANNEL="${CAPAFY_DISTRIBUTE_CHANNEL:-capafy-distribute}"

# --- idempotent per JST-date: never publish twice for the same day ---------
CHECK_RC=0
python3 "$SELF_DIR/capafy_distribute_ledger.py" check --ledger "$LEDGER" --date "$JST_DATE" >>"$LOG" 2>&1 || CHECK_RC=$?
if [ "$CHECK_RC" -eq 10 ]; then
  echo "capafy-distribute-daily: already published date=$JST_DATE, skipping (fail closed, no duplicate)" >>"$LOG"
  exit 0
elif [ "$CHECK_RC" -ne 0 ]; then
  echo "capafy-distribute-daily: ledger check failed rc=$CHECK_RC" >>"$LOG"
  exit 1
fi

# --- pick today's Capafy skill: highest 30d profit/revenue, rotated daily --
PRODUCTS_CONFIG="${CAPAFY_DISTRIBUTE_PRODUCTS_CONFIG:-$ARTICLE_ROOT/config/products.json}"
ANALYTICS_FILE="${CAPAFY_DISTRIBUTE_ANALYTICS_FILE:-$HOME/.local/state/life-manager/state/capafy-skill-analytics.json}"
SELECTION_JSON="$(python3 "$SELF_DIR/select_capafy_distribute_skill.py" \
  --date "$JST_DATE" --products "$PRODUCTS_CONFIG" \
  --analytics "$ANALYTICS_FILE" --channel "$CHANNEL")" || {
  echo "capafy-distribute-daily: skill selection failed" >>"$LOG"
  exit 1
}
echo "capafy-distribute-daily: selection=$SELECTION_JSON" >>"$LOG"

CAPAFY_SKILL_SLUG="$(printf '%s' "$SELECTION_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["capafy_skill"])')"
CAPAFY_LANDING_URL="$(printf '%s' "$SELECTION_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["landing_url"])')"
CAPAFY_CT="$(printf '%s' "$SELECTION_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["ct"])')"
CAPAFY_BUYER_PROBLEM="$(printf '%s' "$SELECTION_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("buyer_problem") or "")')"
CTA_URL="${CAPAFY_LANDING_URL}?ct=${CAPAFY_CT}"

RUN_TS="capafy-distribute-$JST_DATE"
RUN_DIR="$CAPAFY_DISTRIBUTE_STATE_DIR/runs/$RUN_TS"
mkdir -p "$RUN_DIR/gates"

# --- dry-run: exercise every deterministic step above with no model/network
# dispatch and no publish attempt. Used by tests. ------------------------
if [ "${CAPAFY_DISTRIBUTE_DRY_RUN:-0}" = "1" ]; then
  RECEIPT_JSON="$(python3 -c 'import json,sys; print(json.dumps({"status":"dry_run","capafy_skill":sys.argv[1],"cta_url":sys.argv[2],"run_dir":sys.argv[3]}))' \
    "$CAPAFY_SKILL_SLUG" "$CTA_URL" "$RUN_DIR")"
  python3 "$SELF_DIR/capafy_distribute_ledger.py" record --ledger "$LEDGER" --date "$JST_DATE" --json "$RECEIPT_JSON" >>"$LOG" 2>&1 || exit 1
  echo "capafy-distribute-daily: dry-run complete date=$JST_DATE skill=$CAPAFY_SKILL_SLUG" >>"$LOG"
  exit 0
fi

# --- build the model pass prompt: one free English article + X link post --
PROMPT_FILE="$RUN_DIR/prompt.txt"
cat >"$PROMPT_FILE" <<PROMPT_EOF
Run ONE Capafy distribute pass, no daily human in the loop. This is a fresh
loop (capafy-distribute-daily, triggered by launchd label
ai.anicca.capafy-distribute-daily); it is NOT the existing article-daily loop
and must not touch skills/writer-agent/article-daily.sh, its state, or its
publication ledgers.

GOAL: write and publish ONE free (no paywall, no preview/paid split) English
article promoting the Capafy skill "$CAPAFY_SKILL_SLUG" (buyer problem: $CAPAFY_BUYER_PROBLEM).
Follow $ARTICLE_ROOT/reference/CRAFT.md and the humanizer pass at
$ARTICLE_ROOT/vendor/writing-skills/humanizer/SKILL.md for craft quality, and
the IDENTITY / OPERATOR-IDENTIFIER rules in $ARTICLE_ROOT/SKILL.md (never
identify as AI, never name the operator). Before publishing anywhere, run
$ARTICLE_ROOT/scripts/pii-gate.py on the draft and abort publish (but still
record this run in the ledger with status="blocked" and the gate's reason) if
it fails -- this hard safety gate is never skipped.

The article must contain exactly one CTA link, verbatim: $CTA_URL
Do not invent a second Capafy link and do not send readers to any other
product's checkout.

DESTINATIONS (independent -- one failing never blocks the other):
1. dev.to: this destination is currently DORMANT in the shared Writer
   publication contract ($ARTICLE_ROOT/scripts/publication_contract.py,
   DORMANT_PAIRS includes "devto/en"). Read that file and
   $ARTICLE_ROOT/scripts/devto-publish/devto.py before attempting anything.
   Do NOT flip DORMANT_PAIRS/ACTIVE_PAIRS (shared with article-daily.sh). If
   you can construct a minimal valid ARTICLE_PUBLICATION_STATE for an
   English-only free article and DEVTO_API_KEY / DEVTO_ACCOUNT_HANDLE /
   ARTICLE_MEDIA_RAW_BASE are configured, stage via devto.py's own stage()
   function (not publication_resume.py's dual-language init, which requires
   a Japanese draft this run does not have). If any required credential or
   precondition is missing, or you are not confident the state you built is
   valid, SKIP dev.to for this run, record why in gates/devto-skip.json, and
   continue -- do not guess at the API.
2. X (Postiz): build one short caption containing the CTA link above and post
   it with: python3 $SELF_DIR/capafy_x_post.py --caption "<caption>"
   --integration-id "\$CAPAFY_DISTRIBUTE_X_INTEGRATION_ID". If
   CAPAFY_DISTRIBUTE_X_INTEGRATION_ID or POSTIZ_API_KEY is not set, skip X,
   record why, and continue.
3. aniccaai.com and Substack: SKIP both. Neither has a free (non-paywalled)
   publish path today ($ARTICLE_ROOT/scripts/self_owned_article.py requires a
   non-empty paid section; Substack is paid-subscription only per
   $ARTICLE_ROOT/SKILL.md). Do not build a new paywall-free path in this run;
   record the skip and move on.

Write the final receipt as JSON to $RUN_DIR/gates/receipt.json with keys
status ("published" if at least one destination went live, "blocked" if the
PII gate failed, "skipped" if every destination was skipped), capafy_skill,
cta_url, and a "destinations" object keyed by dev.to/x with each entry's
status and url (or skip reason). Then run:
  python3 $SELF_DIR/capafy_distribute_ledger.py record --ledger "$LEDGER" \\
    --date "$JST_DATE" --json "\$(cat $RUN_DIR/gates/receipt.json)"
This ledger write is the ONLY thing that marks today done; if you exit before
writing it, the next scheduled wake will retry today's date, so never invent
a "published" status without a URL you actually observed.
PROMPT_EOF

ARTICLE_MODEL_RUNNER="${ARTICLE_MODEL_RUNNER:-$ARTICLE_ROOT/runtime/model-runner.sh}"
ARTICLE_MODEL_AGENT_TIMEOUT_SECONDS="${CAPAFY_DISTRIBUTE_MODEL_AGENT_TIMEOUT_SECONDS:-1800}"

BOUNDED_EXEC_STOP_PATHS="${LIFE_MANAGER_HOST_STATE_DIR:-$HOME/.local/state/life-manager/state}/disk-writers.stop" \
ARTICLE_RUN_ID="$RUN_TS" ARTICLE_MODEL_LOG="$LOG" ARTICLE_RUN_DIR="$RUN_DIR" \
  python3 "$LIFE_MANAGER_REPO/runtime/loop/bounded-exec.py" \
    "$ARTICLE_MODEL_AGENT_TIMEOUT_SECONDS" \
    "$ARTICLE_MODEL_RUNNER" agent --prompt-file "$PROMPT_FILE" >>"$LOG" 2>&1
RC=$?
echo "capafy-distribute-daily: model pass exit=$RC date=$JST_DATE skill=$CAPAFY_SKILL_SLUG" >>"$LOG"
exit "$RC"
