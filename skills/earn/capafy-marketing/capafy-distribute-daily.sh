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
if [ "${LIFE_MANAGER_LOOP_ID:-}" != "capafy-distribute-daily" ] \
    || [ -z "${LIFE_MANAGER_RUN_ID:-}" ] \
    || [ "${LIFE_MANAGER_OCCURRENCE_ID:-}" != "capafy-distribute-daily:${LIFE_MANAGER_RUN_ID:-}" ]; then
  printf 'capafy-distribute-daily: exact runtime occurrence identity required\n' >&2
  exit 1
fi
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
# One article per wake: the loop wakes every 30 min (Dais 2026-10-11: never wait for a
# 3-hour slot). SLOT is the idempotency key, one per JST half hour (48/day).
JST_HOUR=$(( 10#$(TZ=Asia/Tokyo date +%H) )); JST_HALF=$(( 10#$(TZ=Asia/Tokyo date +%M) / 30 ))
SLOT_NUM=$(( JST_HOUR * 2 + JST_HALF ))
SLOT="${JST_DATE}-h$(printf '%02d' "$JST_HOUR")m$(printf '%02d' $((JST_HALF * 30)))"
CHANNEL="${CAPAFY_DISTRIBUTE_CHANNEL:-capafy-distribute}"

# --- idempotent per JST-date: never publish twice for the same day ---------
CHECK_RC=0
python3 "$SELF_DIR/capafy_distribute_ledger.py" check --ledger "$LEDGER" --date "$SLOT" >>"$LOG" 2>&1 || CHECK_RC=$?
if [ "$CHECK_RC" -eq 10 ]; then
  echo "capafy-distribute-daily: already published slot=$SLOT, skipping (fail closed, no duplicate)" >>"$LOG"
  if [ -n "${LIFE_MANAGER_RESULT_HINT_PATH:-}" ]; then
    python3 "$SELF_DIR/capafy_distribute_fence_reconcile.py" \
      --occurrence "$LIFE_MANAGER_OCCURRENCE_ID" \
      --result-hint "$LIFE_MANAGER_RESULT_HINT_PATH" \
      --no-effect-reason daily_limit_reached --slot "$SLOT" >>"$LOG" 2>&1 || exit 1
  fi
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
# Capafy attributes only ct values registered as promotion links in the seller
# console (新しいプロモーションリンク), and it rewrites/truncates the name it is given:
# "capafy-distribute-hook-lab" became ct=capafy_distribute_hook_l, so none of the
# unregistered tokens above ever showed up in traffic sources. These are the ct
# values Capafy issued on 2026-10-07; add a pair here when a new skill is promoted.
case "$CAPAFY_SKILL_SLUG" in
  hook-lab) CAPAFY_CT=hooklab_blog; X_CT=hooklab_x ;;
  tiktok-script-pro) CAPAFY_CT=tiktok_blog; X_CT=tiktok_x ;;
  youtube-script-writer) CAPAFY_CT=youtube_blog; X_CT=youtube_x ;;
  slide-maker) CAPAFY_CT=slides_blog; X_CT=slides_x ;;
  tiktok-series-continuity-planner) CAPAFY_CT=tiktok_series_blog; X_CT=tiktok_series_x ;;
esac
CTA_URL="${CAPAFY_LANDING_URL}${CT_SEP}ct=${CAPAFY_CT}"
X_CTA_URL="${CAPAFY_LANDING_URL}${CT_SEP}ct=${X_CT}"

# The aniccaai.com blog slug is derived from date+skill (not the title), so
# a retry on the same JST date always resolves to the exact same page
# instead of depending on model-chosen title text for idempotency.
FREE_ARTICLE_SLUG="capafy-${CAPAFY_SKILL_SLUG}-${SLOT}"
# Seller slots with seo/<skill>-keywords.json write a keyword-targeted page instead.
# Source classification and measured outcomes live in the canonical SSOT; page
# creation alone does not establish external search acquisition. Fall back to the
# dated slug when every keyword already has a page.
SEO_KEYWORD_JSON=""
SEO_BRIEF=""
SEO_KEYWORDS_FILE="$SELF_DIR/../seo/${CAPAFY_SKILL_SLUG}-keywords.json"
if [ -f "$SEO_KEYWORDS_FILE" ] && [ -n "${ARTICLE_SELF_OWNED_LANDING_ROOT:-}" ]; then
  SEO_KEYWORD_JSON="$(python3 "$SELF_DIR/pick_seo_keyword.py" "$SEO_KEYWORDS_FILE" \
    "$ARTICLE_SELF_OWNED_LANDING_ROOT/apps/landing/data/research" 2>>"$LOG" || true)"
fi
if [ -n "$SEO_KEYWORD_JSON" ]; then
  FREE_ARTICLE_SLUG="$(printf '%s' "$SEO_KEYWORD_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["slug"])')"
  SEO_BRIEF="$(printf '%s' "$SEO_KEYWORD_JSON" | python3 -c 'import json,sys
k=json.load(sys.stdin); q=k["query"]; lang=k["lang"]
print(f"SEARCH TARGET (overrides the English-only GOAL line): write this page for the search query \"{q}\" in language \"{lang}\", natively. The H1 must contain the query. Copy the structure, length and tone of the template pages apps/landing/data/research/hook-generator-for-tiktok.json (en), ganchos-para-tiktok.json (es) and reels-video-hook-ja.json (ja) in the landing checkout: a short search-intent intro, 30-50 concrete ready-to-use examples of what the promoted product makes (hooks, script beats or titles, matching the query) grouped by niche or type, how to pick and test them, a short FAQ, then the CTA. Where an example needs a real figure, write a fill-in blank such as [ADD: your number]; never invent statistics. No notes to the editor in the body.")')"
  SEO_QUERY="$(printf '%s' "$SEO_KEYWORD_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["query"])')"
  # Conversion (2026-10-18: 0% view->paid): show the seller's real published example right before the CTA.
  SEO_EXAMPLE="$(python3 "$SELF_DIR/pick_seo_keyword.py" --example "$SELF_DIR/../../../capafy/catalog/$CAPAFY_SKILL_SLUG/LISTING.md" 2>/dev/null || true)"
  if [ -n "$SEO_EXAMPLE" ]; then
    SEO_BRIEF="$SEO_BRIEF
Immediately above the CTA, add a section titled \"What the tool returns\" (written in the page language) that quotes this real, published example of the product's input and output. Keep the quoted example lines as given; translate only your own lead-in sentence:
$SEO_EXAMPLE"
  fi
  echo "capafy-distribute-daily: seo keyword=$SEO_KEYWORD_JSON" >>"$LOG"
fi
# Keyword pages must carry the query in the H1 and are announced to IndexNow (key file is public on aniccaai.com).
SEO_QUERY="${SEO_QUERY:-}"
INDEXNOW_KEY=92ec974b25b70513c2cbc172f532bb3b
# Build publisher options as arguments so multiword/UTF-8 queries stay one value.
SEO_PUBLISH_ARGS=()
if [ -n "$SEO_QUERY" ]; then
  SEO_PUBLISH_ARGS+=(--title-must-contain "$SEO_QUERY" --indexnow-key "$INDEXNOW_KEY")
fi
FREE_ARTICLE_URL="${ARTICLE_SELF_OWNED_BASE_URL:-}"
[ -n "$FREE_ARTICLE_URL" ] && FREE_ARTICLE_URL="${FREE_ARTICLE_URL%/}/blog/${FREE_ARTICLE_SLUG}"
# Route Capafy links through our click counter (/go/<agent>/<platform>/<post>?ct=..)
# so /go-stats reports clicks per platform and post; it 302s to Capafy with ct kept.
# Only allow-listed Capafy agents; PromptBase/other landings stay direct.
CAPAFY_AGENT_ID="$(printf '%s' "$SELECTION_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("agent_id") or "")')"
CAPAFY_GO_BASE="${CAPAFY_GO_BASE:-https://capafy-skills-daily.netlify.app/go}"
if [ -n "$CAPAFY_AGENT_ID" ] && grep -q "\"$CAPAFY_AGENT_ID\"" "$SCRIPT_DIR/site/netlify/functions/allowed-agents.json" 2>/dev/null; then
  CTA_URL="${CAPAFY_GO_BASE%/}/${CAPAFY_AGENT_ID}/article/${FREE_ARTICLE_SLUG}?ct=${CAPAFY_CT}"
  X_CTA_URL="${CAPAFY_GO_BASE%/}/${CAPAFY_AGENT_ID}/x/x-${FREE_ARTICLE_SLUG}?ct=${X_CT}"
fi

RUN_TS="capafy-distribute-$SLOT"
RUN_DIR="$CAPAFY_DISTRIBUTE_STATE_DIR/runs/$RUN_TS"
mkdir -p "$RUN_DIR/gates"
chmod 700 "$RUN_DIR" "$RUN_DIR/gates" || exit 1
CAPTION_FILE="$RUN_DIR/x-caption.txt"
DRAFT_RESPONSE="$RUN_DIR/draft-response-$LIFE_MANAGER_RUN_ID.json"
DRAFT_SCHEMA="$SELF_DIR/capafy-distribute-draft.schema.json"
# Bind the wrapper's actual clock-selected slot to the runtime occurrence before
# any model or publication step. Execute-start may straddle a JST half-hour edge.
if ! CAPAFY_DISTRIBUTE_SCRIPT_DIR="$SELF_DIR" python3 - \
    "$CAPAFY_DISTRIBUTE_STATE_DIR/occurrences/$LIFE_MANAGER_RUN_ID.json" \
    "$SLOT" "$FREE_ARTICLE_SLUG" <<'PY'
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ["CAPAFY_DISTRIBUTE_SCRIPT_DIR"])
from capafy_distribute_fence_reconcile import record_occurrence_manifest

record_occurrence_manifest(
    Path(sys.argv[1]),
    owner_id=os.environ["LIFE_MANAGER_LOOP_ID"],
    run_id=os.environ["LIFE_MANAGER_RUN_ID"],
    occurrence_id=os.environ["LIFE_MANAGER_OCCURRENCE_ID"],
    slot=sys.argv[2],
    article_slug=sys.argv[3],
)
PY
then
  echo "capafy-distribute-daily: occurrence slot binding failed" >>"$LOG"
  exit 1
fi

# --- dry-run: exercise every deterministic step above with no model/network
# dispatch and no publish attempt. Used by tests. ------------------------
if [ "${CAPAFY_DISTRIBUTE_DRY_RUN:-0}" = "1" ]; then
  RECEIPT_JSON="$(python3 -c 'import json,sys; print(json.dumps({"status":"dry_run","capafy_skill":sys.argv[1],"cta_url":sys.argv[2],"x_cta_url":sys.argv[3],"free_article_url":sys.argv[4],"run_dir":sys.argv[5]}))' \
    "$CAPAFY_SKILL_SLUG" "$CTA_URL" "$X_CTA_URL" "$FREE_ARTICLE_URL" "$RUN_DIR")"
  python3 "$SELF_DIR/capafy_distribute_ledger.py" record --ledger "$LEDGER" --date "$SLOT" --json "$RECEIPT_JSON" >>"$LOG" 2>&1 || exit 1
  echo "capafy-distribute-daily: dry-run complete date=$JST_DATE skill=$CAPAFY_SKILL_SLUG" >>"$LOG"
  exit 0
fi

# D7 (SSOT 2026-10-15): one real output image for Hook Lab articles; optional, never blocks.
python3 "$SELF_DIR/capafy_article_image.py" "$RUN_DIR" "$CAPAFY_SKILL_SLUG" >>"$LOG" 2>&1 || true

# aniccaai.com is the live publish target below; the base URL is a pure
# operator/dotenv value (see .env.example) required only once we are past
# the dry-run short-circuit above.
: "${ARTICLE_SELF_OWNED_BASE_URL:?ARTICLE_SELF_OWNED_BASE_URL is required (aniccaai.com base URL)}"
FREE_ARTICLE_URL="${ARTICLE_SELF_OWNED_BASE_URL%/}/blog/${FREE_ARTICLE_SLUG}"

# --- build the model pass prompt: one free English article + X link post --
CRAFT_GUIDANCE="$(cat "$ARTICLE_ROOT/reference/CRAFT.md")" || exit 1
IDENTITY_GUIDANCE="$(awk '/^## IDENTITY / {printing=1; next} /^## / {if (printing) exit} printing' \
  "$ARTICLE_ROOT/SKILL.md")" || exit 1
PROMPT_FILE="$RUN_DIR/prompt.txt"
cat >"$PROMPT_FILE" <<PROMPT_EOF
Run ONE Capafy distribute draft pass. Do not touch
skills/writer-agent/article-daily.sh, its state, or publication ledgers.

GOAL: write ONE complete free English article (no paywall, no preview/paid
split) promoting the $PRODUCT_LABEL "$CAPAFY_SKILL_SLUG" (buyer problem:
$CAPAFY_BUYER_PROBLEM).

Writing craft:
$CRAFT_GUIDANCE

Author identity and operator privacy:
$IDENTITY_GUIDANCE

Use natural varied English. Cut filler, generic conclusions, empty promotion,
unsupported claims, vague attributions, and invented personal experience.
$SEO_BRIEF

The article body must contain exactly one Capafy CTA link, verbatim:
$CTA_URL
Do not add a second Capafy link or send readers to another product checkout.
Give the draft one H1 title in "article_markdown". Do not invent statistics, product behavior, earnings,
or conversion claims.

For hook-lab, write one short X caption that demonstrates one input topic and
one finished spoken hook from the supplied published example (or
$LIFE_MANAGER_REPO/skills/capafy/catalog/hook-lab/LISTING.md). Briefly say what
Hook Lab returns. Other skills keep their existing caption style. Use only
supplied product facts; do not promise retention, views, or revenue. Include
the article URL $FREE_ARTICLE_URL and separate Capafy link $X_CTA_URL. Write
the caption as the "x_caption" string value.

Do not publish, push commits, call Postiz, run capafy_x_post.py, write a
receipt, update the ledger, or write files. Return exactly one JSON object with
the fields "article_markdown" and "x_caption" containing the complete article
and caption. Do not include code fences or other fields. The trusted wrapper
validates the JSON, writes the draft and caption, runs the PII gate, and owns
article/X publication and ledger updates after you exit. If the PII gate blocks
the draft, the wrapper records a no-effect outcome and retries on a later
cadence. Do not try to read other files or paths.

dev.to, Zenn, and Substack are out of scope. Do not publish or build a route
to any of them.
PROMPT_EOF

ARTICLE_MODEL_RUNNER="${ARTICLE_MODEL_RUNNER:-$ARTICLE_ROOT/runtime/model-runner.sh}"
ARTICLE_MODEL_AGENT_TIMEOUT_SECONDS="${CAPAFY_DISTRIBUTE_MODEL_AGENT_TIMEOUT_SECONDS:-1800}"
if [ -e "$DRAFT_RESPONSE" ] || [ -L "$DRAFT_RESPONSE" ]; then
  echo "capafy-distribute-daily: Codex output path already exists" >>"$LOG"
  exit 1
fi

env -u LIFE_MANAGER_RESULT_HINT_PATH -u CAPAFY_DISTRIBUTE_STATE_DIR \
  -u CAPAFY_DISTRIBUTE_EVENTS_PATH -u CAPAFY_DISTRIBUTE_RUNS_ROOT \
  -u LIFE_MANAGER_RESOURCE_ADMISSION_ROOT -u LIFE_MANAGER_LOOP_ID \
  -u LIFE_MANAGER_RUN_ID -u LIFE_MANAGER_OCCURRENCE_ID \
  -u POSTIZ_API_KEY -u LM_POSTIZ_API_KEY -u LIFE_MANAGER_MARKETING_ENV_FILE \
  BOUNDED_EXEC_STOP_PATHS="${LIFE_MANAGER_HOST_STATE_DIR:-$HOME/.local/state/life-manager/state}/disk-writers.stop" \
ARTICLE_RUN_ID="$RUN_TS" ARTICLE_MODEL_LOG="$LOG" ARTICLE_RUN_DIR="$RUN_DIR" \
ARTICLE_CODEX_NO_TOOLS=1 ARTICLE_CODEX_OUTPUT_FILE="$DRAFT_RESPONSE" \
ARTICLE_CODEX_OUTPUT_SCHEMA="$DRAFT_SCHEMA" CODEX_SESSION_MODE=0 \
  python3 "$LIFE_MANAGER_REPO/runtime/loop/bounded-exec.py" \
    "$ARTICLE_MODEL_AGENT_TIMEOUT_SECONDS" \
    "$ARTICLE_MODEL_RUNNER" agent-workspace --prompt-file "$PROMPT_FILE" >>"$LOG" 2>&1
RC=$?
echo "capafy-distribute-daily: model pass exit=$RC slot=$SLOT skill=$CAPAFY_SKILL_SLUG" >>"$LOG"
[ -f "$DRAFT_RESPONSE" ] && [ ! -L "$DRAFT_RESPONSE" ] || exit 1
chmod 600 "$DRAFT_RESPONSE" || exit 1
python3 "$SELF_DIR/capafy_draft_output.py" materialize \
  --response "$DRAFT_RESPONSE" --run-dir "$RUN_DIR" >>"$LOG" 2>&1 || exit 1
# The ledger is the effect truth, not the exit code. Before PR #8249 the agent
# exited 1 even after a fully published run (live 2026-09-29 h15) because its
# prose report failed the shared runner's JSON contract; rc is still advisory.
# The article model cannot publish or update the ledger. Gate every model-written
# public surface before the trusted wrapper reaches any provider.
PII_RC=0
if [ -s "$RUN_DIR/article-en.md" ]; then
  PII_FILES=("$RUN_DIR/article-en.md")
  [ -s "$CAPTION_FILE" ] && PII_FILES+=("$CAPTION_FILE")
  python3 "$ARTICLE_ROOT/scripts/pii-gate.py" --stage capafy-distribute-publish \
    "${PII_FILES[@]}" >>"$LOG" 2>&1 || PII_RC=$?
fi
if [ "$PII_RC" -ne 0 ]; then
  echo "capafy-distribute-daily: PII gate blocked provider publish rc=$PII_RC" >>"$LOG"
  if [ -n "${LIFE_MANAGER_RESULT_HINT_PATH:-}" ]; then
    python3 - "$SELF_DIR" "$LIFE_MANAGER_RESULT_HINT_PATH" \
      "$LIFE_MANAGER_OCCURRENCE_ID" "$SLOT" "$PII_RC" >>"$LOG" 2>&1 <<'PY' || exit 1
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).parents[3]))
from runtime.loop.lm_loop_run import write_capafy_pii_gate_attestation

if not write_capafy_pii_gate_attestation(
        Path(sys.argv[2]), sys.argv[3], sys.argv[4],
        gate_exit_code=int(sys.argv[5])):
    raise SystemExit(1)
PY
    python3 "$SELF_DIR/capafy_distribute_fence_reconcile.py" \
      --occurrence "$LIFE_MANAGER_OCCURRENCE_ID" \
      --result-hint "$LIFE_MANAGER_RESULT_HINT_PATH" \
      --no-effect-reason pii_gate_blocked --slot "$SLOT" >>"$LOG" 2>&1 || exit 1
    exit 0
  fi
  exit 1
fi
# The trusted wrapper publishes the draft and waits for official public-page
# readback; the model cannot perform or record this provider effect.
python3 "$SELF_DIR/capafy_distribute_ledger.py" check --ledger "$LEDGER" --date "$SLOT" >/dev/null 2>&1
if [ "$?" -eq 0 ] && [ -s "$RUN_DIR/article-en.md" ] && [ "${CAPAFY_DISTRIBUTE_DRY_RUN:-0}" != "1" ]; then
  PUB_OUT="$(python3 "$SELF_DIR/capafy_free_article.py" publish \
    --draft-file "$RUN_DIR/article-en.md" --slug "$FREE_ARTICLE_SLUG" --cta-url "$CTA_URL" \
    --landing-root "$ARTICLE_SELF_OWNED_LANDING_ROOT" --remote "$ARTICLE_SELF_OWNED_REMOTE" \
    --branch "$ARTICLE_SELF_OWNED_BRANCH" --base-url "$ARTICLE_SELF_OWNED_BASE_URL" \
    --date "$JST_DATE" "${SEO_PUBLISH_ARGS[@]}" 2>>"$LOG" | tail -1)" || true
  echo "capafy-distribute-daily: wrapper publish: ${PUB_OUT:0:300}" >>"$LOG"
  PUB_OUT="$PUB_OUT" LEDGER="$LEDGER" SLOT="$SLOT" SKILL="$CAPAFY_SKILL_SLUG" CTA="$CTA_URL" XCTA="$X_CTA_URL" \
  DRAFT="$RUN_DIR/article-en.md" CAPTION_FILE="$CAPTION_FILE" LEDGER_TOOL="$SELF_DIR/capafy_distribute_ledger.py" \
  python3 - <<'PY' >>"$LOG" 2>&1 || true
import json, os, subprocess, sys
try:
    out = json.loads(os.environ.get("PUB_OUT") or "{}")
except ValueError:
    out = {}
ok = out.get("status") == "published" and out.get("url")
entry = {"status": "published" if ok else "blocked", "capafy_skill": os.environ["SKILL"],
         "cta_url": os.environ["CTA"], "x_cta_url": os.environ["XCTA"], "publisher": "wrapper",
         "destinations": {"aniccaai": {"status": "published", "url": out["url"]} if ok
                          else {"status": "blocked", "reason": "capafy_free_article.py did not confirm the live page"}}}
subprocess.run([sys.executable, os.environ["LEDGER_TOOL"], "record", "--ledger", os.environ["LEDGER"],
                "--date", os.environ["SLOT"], "--json", json.dumps(entry)], check=True)
cap = os.environ["CAPTION_FILE"]
if ok and not (os.path.exists(cap) and os.path.getsize(cap)):
    title = next((l[2:].strip() for l in open(os.environ["DRAFT"], encoding="utf-8") if l.startswith("# ")), "")
    open(cap, "w", encoding="utf-8").write(f"{title}\n{out['url']}\nTry it on Capafy: {os.environ['XCTA']}\n")
PY
fi
X_CHECK_RC=0
python3 "$SELF_DIR/capafy_distribute_ledger.py" check --ledger "$LEDGER" --date "$SLOT" >/dev/null 2>&1 || X_CHECK_RC=$?
if [ "$X_CHECK_RC" -eq 10 ] && [ -s "$CAPTION_FILE" ] \
    && [ -n "${POSTIZ_X_INTEGRATION_ID:-}" ]; then
  # Postiz strips links from X posts (2026-10-11), so the caption ends with a Capafy search CTA.
  X_OUT="$(python3 "$SELF_DIR/capafy_x_post.py" --caption "$(cat "$CAPTION_FILE")" \
    --integration-id "$POSTIZ_X_INTEGRATION_ID" \
    --search-slug "$CAPAFY_SKILL_SLUG" \
    2>>"$LOG" | tail -1)" || true
  echo "capafy-distribute-daily: x post: ${X_OUT:0:300}" >>"$LOG"
  X_OUT="$X_OUT" LEDGER="$LEDGER" SLOT="$SLOT" LEDGER_TOOL="$SELF_DIR/capafy_distribute_ledger.py" python3 - <<'PY' >>"$LOG" 2>&1 || true
import json, os, subprocess, sys
ledger, slot = os.environ["LEDGER"], os.environ["SLOT"]
try:
    entry = json.load(open(ledger)).get(slot) or {}
except (OSError, ValueError):
    entry = {}
try:
    out = json.loads(os.environ.get("X_OUT") or "{}")
except ValueError:
    out = {}
post = out.get("post") or {}
if out.get("action") == "published":
    x = {"status": "PUBLISHED", "post_id": out.get("post_id"), "url": post.get("releaseURL")}
else:
    x = {"status": "failed", "reason": "capafy_x_post.py did not confirm PUBLISHED"}
entry.setdefault("destinations", {})["x"] = x
subprocess.run([sys.executable, os.environ["LEDGER_TOOL"], "record", "--ledger", ledger,
                "--date", slot, "--json", json.dumps(entry)], check=True)
PY
fi
# Dais 2026-10-08: every published article reaches Telegram with clickable links.
# Keep this idempotency marker outside the draft-only model workspace.
TG_MARK="$CAPAFY_DISTRIBUTE_STATE_DIR/notifications/$LIFE_MANAGER_RUN_ID.telegram-sent"
mkdir -p "$(dirname "$TG_MARK")"
if [ ! -e "$TG_MARK" ] && [ "${CAPAFY_DISTRIBUTE_DRY_RUN:-0}" != "1" ]; then
  TG_MSG="$(LEDGER="$LEDGER" SLOT="$SLOT" FALLBACK_URL="${ARTICLE_SELF_OWNED_BASE_URL:-https://aniccaai.com}/blog/$FREE_ARTICLE_SLUG" python3 - <<'PY' 2>>"$LOG"
import json, os
try:
    e = json.load(open(os.environ["LEDGER"])).get(os.environ["SLOT"]) or {}
except (OSError, ValueError):
    e = {}
if e.get("status") == "published":
    d = e.get("destinations") or {}
    article = (d.get("aniccaai") or {}).get("url") or os.environ["FALLBACK_URL"]
    x = (d.get("x") or {}).get("url") or "not posted"
    print(f"Capafy article published ({os.environ['SLOT']}, {e.get('capafy_skill', '')})\nArticle: {article}\nX: {x}\nCapafy: {e.get('cta_url', '')}")
PY
)"
  if [ -n "$TG_MSG" ]; then
    . "$LIFE_MANAGER_REPO/skills/_shared/scripts/telegram-notify.sh" 2>/dev/null || true
    if command -v telegram_notify >/dev/null 2>&1 && telegram_notify "$TG_MSG" >>"$LOG" 2>&1; then
      : >"$TG_MARK"
    fi
  fi
fi
# Postiz strips links from X posts; reply to our own recent posts with their ct link (non-fatal).
if [ "${CAPAFY_DISTRIBUTE_DRY_RUN:-0}" != "1" ]; then
  python3 "$SELF_DIR/capafy_x_link_reply.py" --limit 4 >>"$LOG" 2>&1 || true
fi
POST_RC=0
python3 "$SELF_DIR/capafy_distribute_ledger.py" check --ledger "$LEDGER" --date "$SLOT" >>"$LOG" 2>&1 || POST_RC=$?
if [ "$POST_RC" -eq 10 ]; then
  if [ "${CAPAFY_DISTRIBUTE_DRY_RUN:-0}" != "1" ] \
      && [ -n "${LIFE_MANAGER_RESULT_HINT_PATH:-}" ]; then
    python3 "$SELF_DIR/capafy_distribute_fence_reconcile.py" \
      --occurrence "$LIFE_MANAGER_OCCURRENCE_ID" \
      --result-hint "$LIFE_MANAGER_RESULT_HINT_PATH" >>"$LOG" 2>&1 || exit 1
  fi
  exit 0
fi
if [ "$RC" -eq 0 ] && [ "${CAPAFY_DISTRIBUTE_DRY_RUN:-0}" != "1" ] \
    && [ -n "${LIFE_MANAGER_RESULT_HINT_PATH:-}" ]; then
  echo "capafy-distribute-daily: published slot lacks a verified result hint" >>"$LOG"
  exit 1
fi
exit "$RC"
