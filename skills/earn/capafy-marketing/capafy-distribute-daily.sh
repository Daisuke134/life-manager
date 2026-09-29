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
# modify another loop's code).
#
# Dais decision 2026-09-29: dev.to and Zenn are no longer published to by
# ANY loop. This loop's free article now goes to our own site instead --
# scripts/capafy_free_article.py writes one fully public
# apps/landing/data/research/<slug>.json page straight into the SAME landing
# repo the Writer's self-owned publisher uses
# (skills/writer-agent/scripts/self_owned_article.py), without touching that
# module's paid preview/paid-split contract at all: it only reuses its pure
# git/text helpers. Substack stays skipped (paid-subscription only, per
# $ARTICLE_ROOT/SKILL.md).
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ARTICLE_ROOT="${ARTICLE_ROOT:-$(cd "$SCRIPT_DIR/../../writer-agent" && pwd -P)}"
# shellcheck source=../writer-agent/scripts/writer-runtime-env.sh
source "$ARTICLE_ROOT/scripts/writer-runtime-env.sh"
# writer-runtime-env derives the self-owned site checkout from this loop's own
# state dir, which has no checkout (first live run 2026-09-29: FileNotFoundError
# .../capafy-distribute/checkouts/self-owned-landing). Publish through the Writer's
# existing checkout; capafy_free_article.py refuses a dirty worktree, and the two
# loops run at different times (article-daily 06:00, this loop 07:15 JST).
ARTICLE_SELF_OWNED_LANDING_ROOT="${CAPAFY_DISTRIBUTE_LANDING_ROOT:-$HOME/.local/state/life-manager/writer/checkouts/self-owned-landing}"
export ARTICLE_SELF_OWNED_LANDING_ROOT

# Postiz: use Life Manager's own key from private/marketing.env (the same one the
# mobile-app loops use). A legacy user-level env file is refused by the shared env
# loader ("refusing to load env file beneath a legacy runtime root", first live run
# 2026-09-29 16:18 JST).
if [ -z "${POSTIZ_API_KEY:-}" ]; then
  _lm_marketing_env="${LIFE_MANAGER_MARKETING_ENV_FILE:-$HOME/.local/state/life-manager/private/marketing.env}"
  if [ -f "$_lm_marketing_env" ]; then
    # shellcheck source=/dev/null
    source "$LIFE_MANAGER_REPO/apps/life-manager/scripts/lib/load-env-file.sh"
    lm_load_env_file "$_lm_marketing_env"
  fi
  [ -n "${LM_POSTIZ_API_KEY:-}" ] && export POSTIZ_API_KEY="$LM_POSTIZ_API_KEY"
fi

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
# One article per 3-hour JST slot (8/day); SLOT is the idempotency key.
SLOT_NUM=$(( 10#$(TZ=Asia/Tokyo date +%H) / 3 ))
SLOT="${JST_DATE}-h$(printf '%02d' $((SLOT_NUM * 3)))"
CHANNEL="${CAPAFY_DISTRIBUTE_CHANNEL:-capafy-distribute}"

# --- idempotent per JST-date: never publish twice for the same day ---------
CHECK_RC=0
python3 "$SELF_DIR/capafy_distribute_ledger.py" check --ledger "$LEDGER" --date "$SLOT" >>"$LOG" 2>&1 || CHECK_RC=$?
if [ "$CHECK_RC" -eq 10 ]; then
  echo "capafy-distribute-daily: already published slot=$SLOT, skipping (fail closed, no duplicate)" >>"$LOG"
  exit 0
elif [ "$CHECK_RC" -ne 0 ]; then
  echo "capafy-distribute-daily: ledger check failed rc=$CHECK_RC" >>"$LOG"
  exit 1
fi

# --- pick today's Capafy skill: highest 30d profit/revenue, rotated daily --
PRODUCTS_CONFIG="${CAPAFY_DISTRIBUTE_PRODUCTS_CONFIG:-$ARTICLE_ROOT/config/products.json}"
ANALYTICS_FILE="${CAPAFY_DISTRIBUTE_ANALYTICS_FILE:-$HOME/.local/state/life-manager/state/capafy-skill-analytics.json}"
SELECTION_JSON="$(python3 "$SELF_DIR/select_capafy_distribute_skill.py" \
  --date "$JST_DATE" --slot "$SLOT_NUM" --products "$PRODUCTS_CONFIG" \
  --analytics "$ANALYTICS_FILE" --channel "$CHANNEL")" || {
  echo "capafy-distribute-daily: skill selection failed" >>"$LOG"
  exit 1
}
echo "capafy-distribute-daily: selection=$SELECTION_JSON" >>"$LOG"

CAPAFY_SKILL_SLUG="$(printf '%s' "$SELECTION_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["capafy_skill"])')"
CAPAFY_LANDING_URL="$(printf '%s' "$SELECTION_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["landing_url"])')"
CAPAFY_CT="$(printf '%s' "$SELECTION_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["ct"])')"
CAPAFY_BUYER_PROBLEM="$(printf '%s' "$SELECTION_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("buyer_problem") or "")')"
# PromptBase links already carry ?via= (0% fee referral), so join ct with &.
CT_SEP="?"; case "$CAPAFY_LANDING_URL" in *\?*) CT_SEP="&" ;; esac
PRODUCT_LABEL="Capafy skill"; case "$CAPAFY_LANDING_URL" in https://promptbase.com/*) PRODUCT_LABEL="PromptBase prompt" ;; esac
CTA_URL="${CAPAFY_LANDING_URL}${CT_SEP}ct=${CAPAFY_CT}"
# The X post gets its OWN ct token (distinct from the article's) so Capafy's
# traffic-sources dashboard reports aniccaai.com-article visits and X-post
# visits as two separate rows instead of merging them under one token.
X_CT="capafy-x-${CAPAFY_SKILL_SLUG}"
X_CTA_URL="${CAPAFY_LANDING_URL}${CT_SEP}ct=${X_CT}"

# The aniccaai.com blog slug is derived from date+skill (not the title), so
# a retry on the same JST date always resolves to the exact same page
# instead of depending on model-chosen title text for idempotency.
FREE_ARTICLE_SLUG="capafy-${CAPAFY_SKILL_SLUG}-${SLOT}"
FREE_ARTICLE_URL="${ARTICLE_SELF_OWNED_BASE_URL:-}"
[ -n "$FREE_ARTICLE_URL" ] && FREE_ARTICLE_URL="${FREE_ARTICLE_URL%/}/blog/${FREE_ARTICLE_SLUG}"

RUN_TS="capafy-distribute-$SLOT"
RUN_DIR="$CAPAFY_DISTRIBUTE_STATE_DIR/runs/$RUN_TS"
mkdir -p "$RUN_DIR/gates"

# --- dry-run: exercise every deterministic step above with no model/network
# dispatch and no publish attempt. Used by tests. ------------------------
if [ "${CAPAFY_DISTRIBUTE_DRY_RUN:-0}" = "1" ]; then
  RECEIPT_JSON="$(python3 -c 'import json,sys; print(json.dumps({"status":"dry_run","capafy_skill":sys.argv[1],"cta_url":sys.argv[2],"x_cta_url":sys.argv[3],"free_article_url":sys.argv[4],"run_dir":sys.argv[5]}))' \
    "$CAPAFY_SKILL_SLUG" "$CTA_URL" "$X_CTA_URL" "$FREE_ARTICLE_URL" "$RUN_DIR")"
  python3 "$SELF_DIR/capafy_distribute_ledger.py" record --ledger "$LEDGER" --date "$SLOT" --json "$RECEIPT_JSON" >>"$LOG" 2>&1 || exit 1
  echo "capafy-distribute-daily: dry-run complete date=$JST_DATE skill=$CAPAFY_SKILL_SLUG" >>"$LOG"
  exit 0
fi

# aniccaai.com is the live publish target below; the base URL is a pure
# operator/dotenv value (see .env.example) required only once we are past
# the dry-run short-circuit above.
: "${ARTICLE_SELF_OWNED_BASE_URL:?ARTICLE_SELF_OWNED_BASE_URL is required (aniccaai.com base URL)}"
FREE_ARTICLE_URL="${ARTICLE_SELF_OWNED_BASE_URL%/}/blog/${FREE_ARTICLE_SLUG}"

# --- build the model pass prompt: one free English article + X link post --
PROMPT_FILE="$RUN_DIR/prompt.txt"
cat >"$PROMPT_FILE" <<PROMPT_EOF
Run ONE Capafy distribute pass, no daily human in the loop. This is a fresh
loop (capafy-distribute-daily, triggered by launchd label
ai.anicca.capafy-distribute-daily); it is NOT the existing article-daily loop
and must not touch skills/writer-agent/article-daily.sh, its state, or its
publication ledgers.

GOAL: write and publish ONE free (no paywall, no preview/paid split) English
article promoting the $PRODUCT_LABEL "$CAPAFY_SKILL_SLUG" (buyer problem: $CAPAFY_BUYER_PROBLEM).
Follow $ARTICLE_ROOT/reference/CRAFT.md and the humanizer pass at
$ARTICLE_ROOT/vendor/writing-skills/humanizer/SKILL.md for craft quality, and
the IDENTITY / OPERATOR-IDENTIFIER rules in $ARTICLE_ROOT/SKILL.md (never
identify as AI, never name the operator). Before publishing anywhere, run
$ARTICLE_ROOT/scripts/pii-gate.py on the draft and abort publish (but still
record this run in the ledger with status="blocked" and the gate's reason) if
it fails -- this hard safety gate is never skipped.

The article body must contain exactly one Capafy CTA link, verbatim:
$CTA_URL
Do not invent a second Capafy link in the article body and do not send
readers to any other product's checkout. Give the draft a single H1 title
line ("# ...") -- write $RUN_DIR/article-en.md with that H1 and the full
free article body (no paywall, no preview/paid split, nothing held back;
YAML frontmatter is optional and ignored by the publish step below).

DESTINATIONS:
1. aniccaai.com, FULL FREE PUBLIC PAGE (required -- step 2 depends on its
   URL) -- once article-en.md is frozen, run exactly:
     python3 $SELF_DIR/capafy_free_article.py publish \\
       --draft-file $RUN_DIR/article-en.md \\
       --slug $FREE_ARTICLE_SLUG \\
       --cta-url "$CTA_URL" \\
       --landing-root "$ARTICLE_SELF_OWNED_LANDING_ROOT" \\
       --remote "$ARTICLE_SELF_OWNED_REMOTE" \\
       --branch "$ARTICLE_SELF_OWNED_BRANCH" \\
       --base-url "$ARTICLE_SELF_OWNED_BASE_URL" \\
       --date "$JST_DATE"
   This writes ONE plain public JSON page (no preview/paid split, unlike the
   Writer's own self-owned paid articles) straight into the same landing
   repo the Writer commits to, pushes it, then polls the live page at
   $FREE_ARTICLE_URL until it reads back HTTP 200 with the title and the
   Capafy CTA link both present, before printing its JSON result. Do not
   call self_owned_article.py's build_contract/stage_contracts/resume
   directly and do not edit that module's paid preview/paid-split contract
   to unblock this -- this script exists specifically so this loop never
   touches that paid pipeline. If this command exits non-zero, record
   status="blocked" with its stderr as the reason, skip step 2 entirely
   (there is no live URL to link to), and still run the ledger write below.
2. X, REAL POST (not a draft) -- only if step 1 published. Build one short
   caption containing the aniccaai.com URL from step 1's JSON output ("url")
   and this SEPARATE Capafy link:
   $X_CTA_URL
   Then run exactly:
     python3 $SELF_DIR/capafy_x_post.py --caption "<caption>" \\
       --integration-id "\$POSTIZ_X_INTEGRATION_ID"
   This creates the post via Postiz, promotes it out of draft, and polls
   Postiz's own readback until state=="PUBLISHED" before printing success --
   it never reports success on a QUEUE/DRAFT/ERROR state. If
   POSTIZ_X_INTEGRATION_ID or POSTIZ_API_KEY is not set, or the command exits
   non-zero, record that as skipped/failed with the reason and continue.
3. dev.to, Zenn, Substack: SKIP all three (Dais decision 2026-09-29 -- we do
   not publish to dev.to or Zenn; Substack is still paid-subscription only
   per $ARTICLE_ROOT/SKILL.md). Do not build a publish path to any of them
   in this run; record the skip and move on.

Write the final receipt as JSON to $RUN_DIR/gates/receipt.json with keys
status ("published" if aniccaai.com went live, "blocked" if the PII gate or
step 1 failed, "skipped" if step 1 itself was skipped), capafy_skill,
cta_url, x_cta_url, and a "destinations" object keyed by aniccaai/x with each
entry's status and url (or skip/failure reason) taken verbatim from the two
commands' own JSON output above -- never invent a URL that was not printed by
capafy_free_article.py or capafy_x_post.py. Then run:
  python3 $SELF_DIR/capafy_distribute_ledger.py record --ledger "$LEDGER" \\
    --date "$SLOT" --json "\$(cat $RUN_DIR/gates/receipt.json)"
This ledger write is the ONLY thing that marks today done; if you exit before
writing it, the next scheduled wake will retry today's date.
PROMPT_EOF

ARTICLE_MODEL_RUNNER="${ARTICLE_MODEL_RUNNER:-$ARTICLE_ROOT/runtime/model-runner.sh}"
ARTICLE_MODEL_AGENT_TIMEOUT_SECONDS="${CAPAFY_DISTRIBUTE_MODEL_AGENT_TIMEOUT_SECONDS:-1800}"

BOUNDED_EXEC_STOP_PATHS="${LIFE_MANAGER_HOST_STATE_DIR:-$HOME/.local/state/life-manager/state}/disk-writers.stop" \
ARTICLE_RUN_ID="$RUN_TS" ARTICLE_MODEL_LOG="$LOG" ARTICLE_RUN_DIR="$RUN_DIR" \
  python3 "$LIFE_MANAGER_REPO/runtime/loop/bounded-exec.py" \
    "$ARTICLE_MODEL_AGENT_TIMEOUT_SECONDS" \
    "$ARTICLE_MODEL_RUNNER" agent --prompt-file "$PROMPT_FILE" >>"$LOG" 2>&1
RC=$?
echo "capafy-distribute-daily: model pass exit=$RC slot=$SLOT skill=$CAPAFY_SKILL_SLUG" >>"$LOG"
# The agent CLI exits 1 even after a fully published run (live 2026-09-29 h15:
# receipt published + ledger written, exit 1). The ledger is the effect truth.
POST_RC=0
python3 "$SELF_DIR/capafy_distribute_ledger.py" check --ledger "$LEDGER" --date "$SLOT" >>"$LOG" 2>&1 || POST_RC=$?
[ "$POST_RC" -eq 10 ] && exit 0
exit "$RC"
