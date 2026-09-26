#!/usr/bin/env bash
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$LIFE_MANAGER_REPO" ] || { echo "LIFE_MANAGER_REPO could not be resolved" >&2; exit 2; }
export LIFE_MANAGER_REPO
# One canonical unattended developer pass:
# privacy-safe feedback -> lm:type:self-heal issue -> fresh agent -> tests/evals -> PR.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$HERE/.." && pwd)"
REPO="Daisuke134/life-manager"
PROJECT="${LM_DEV_PROJECT:-$HOME/Projects/life-manager-main}"
RUN_AGENT="${LM_DEV_RUN_AGENT:-$LIFE_MANAGER_REPO/skills/earn/marketing-engine/run_agent.sh}"
STATE="${LM_DEV_STATE_DIR:-$HOME/.local/state/life-manager/state/life-manager-dev}"
DONE="$STATE/done.jsonl"
LOG_DIR="${LM_DEV_LOG_DIR:-$HOME/.local/state/life-manager/logs}"
LOCK_DIR="${LM_DEV_LOCK_DIR:-/tmp/anicca-life-manager-dev-d0.lock.d}"
RESULT_PATH="${LM_DEV_RESULT_PATH:-}"
mkdir -p "$STATE" "$LOG_DIR"

MONEY_STATE="${LM_DEV_MONEY_STATE:-$HOME/.local/state/life-manager/state/STATE.md}"
METRIC_FOCUS="$(MONEY_STATE="$MONEY_STATE" python3 - <<'PY'
import os, re
from pathlib import Path
values = {}
try:
    for line in Path(os.environ["MONEY_STATE"]).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([a-z_]+):\s*(-?\d+(?:\.\d+)?)\s*$", line)
        if m: values[m.group(1)] = float(m.group(2))
except OSError:
    pass
stages = [
    ("calendar", "funnel_users", "funnel_calendar_connected"),
    ("phone", "funnel_calendar_connected", "funnel_phone_saved"),
    ("call", "funnel_phone_saved", "funnel_call_opt_in"),
    ("paid", "funnel_call_opt_in", "funnel_paid"),
]
available = [(name, max(0, values[a] - values[b])) for name, a, b in stages if a in values and b in values]
print(max(available, key=lambda row: (row[1], -stages.index(next(x for x in stages if x[0] == row[0]))))[0] if available else "unknown")
PY
)"
METRIC_MARKER="[lm-metric-focus:${METRIC_FOCUS}]"

log() {
  printf '%s life-manager-dev: %s\n' "$(date '+%F %T')" "$*" >&2
}

record() {
  # shellcheck disable=SC2016
  node -e '
    const [issue, prUrl, status] = process.argv.slice(1);
    process.stdout.write(`${JSON.stringify({
      issue: Number(issue),
      pr_url: prUrl || null,
      status,
      ts: Math.floor(Date.now() / 1000),
    })}\n`);
  ' "$1" "$2" "$3" >> "$DONE"
}

write_result() {
  [ -z "$RESULT_PATH" ] && return 0
  node - "$RESULT_PATH" "$1" "$2" "${3:-}" "${4:-}" <<'NODE'
const fs = require("node:fs");
const [file, status, reason, issueRaw, prRaw] = process.argv.slice(2);
const issue = Number(issueRaw);
const prUrl = /^https:\/\/github\.com\/Daisuke134\/life-manager\/pull\/\d+$/.test(prRaw)
  ? prRaw
  : null;
fs.writeFileSync(file, JSON.stringify({
  status,
  reason,
  issue_number: Number.isInteger(issue) && issue > 0 ? issue : null,
  pr_url: prUrl,
}), { mode: 0o600 });
NODE
}

if [ ! -d "$APP_DIR/node_modules/pg" ]; then
  (cd "$APP_DIR" && npm ci --silent) || log "dependency install failed"
fi
node "$HERE/feedback-to-issue.js" >&2 || {
  log "feedback-to-issue failed; continuing with an already-open issue"
}

if [ -d "$LOCK_DIR" ]; then
  lock_age=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
  [ "$lock_age" -gt 1800 ] && rmdir "$LOCK_DIR" 2>/dev/null || true
fi
mkdir "$LOCK_DIR" 2>/dev/null || {
  log "another D0 pass holds the lock"
  write_result "no_op" "overlapping_d0"
  exit 0
}
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT

node "$HERE/recovery-self-build-bridge.js" >&2 || {
  log "recovery outcome bridge failed; continuing with an already-open issue"
}

ISSUES_JSON="$STATE/issues.json"
if [ -n "${LM_DEV_ISSUE_NUMBER:-}" ]; then
  gh issue view "$LM_DEV_ISSUE_NUMBER" -R "$REPO" \
    --json number,title,body,labels,state > "$ISSUES_JSON"
else
  gh issue list -R "$REPO" --state open --label "lm:type:self-heal" \
    --limit 100 --json number,title,body,labels > "$ISSUES_JSON"
fi

CHOSEN="$(node - "$ISSUES_JSON" "$DONE" <<'NODE'
const fs = require("node:fs");
const [issuesPath, donePath] = process.argv.slice(2);
const value = JSON.parse(fs.readFileSync(issuesPath, "utf8"));
const issues = Array.isArray(value) ? value : [value];
const attempted = new Set();
if (fs.existsSync(donePath)) {
  for (const line of fs.readFileSync(donePath, "utf8").split("\n")) {
    if (!line.trim()) continue;
    try { attempted.add(Number(JSON.parse(line).issue)); } catch {}
  }
}
const chosen = issues.find((issue) =>
  issue
  && issue.state !== "CLOSED"
  && Array.isArray(issue.labels)
  && issue.labels.some((label) => label.name === "lm:type:self-heal")
  && !attempted.has(Number(issue.number))
);
process.stdout.write(JSON.stringify(chosen || {}));
NODE
)"

NUM="$(node -e 'process.stdout.write(String(JSON.parse(process.argv[1]).number || ""))' "$CHOSEN")"
if [ -z "$NUM" ]; then
  log "no unattempted open lm:type:self-heal issue"
  write_result "no_op" "no_unattempted_open_issue"
  exit 0
fi
TITLE="$(node -e 'process.stdout.write(String(JSON.parse(process.argv[1]).title || ""))' "$CHOSEN")"
BODY="$(node -e 'process.stdout.write(String(JSON.parse(process.argv[1]).body || ""))' "$CHOSEN")"
RECOVERY_PR_MARKER=""
RECOVERY_CLASS_MARKER=""
RECOVERY_OWNER_MARKER=""
case "$BODY" in
  *"<!-- lm-recovery:"*)
    RECOVERY_PR_MARKER="[lm-recovery-self-heal]"
    RECOVERY_MARKERS="$(node - "$BODY" "$LIFE_MANAGER_REPO/config/loop-registry.json" "$LIFE_MANAGER_REPO/runtime/loop/recovery-class.cjs" <<'NODE'
const fs = require("node:fs");
const [body, registryPath, classifierPath] = process.argv.slice(2);
const owner = String(body || "").match(/^owner_id: ([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$/m)?.[1];
const registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));
const entry = owner && registry?.loops?.[owner];
if (!entry) process.exit(2);
const { classifyRecoveryJob } = require(classifierPath);
// The class marker is machine-computed provenance; the owner marker travels alongside it so the
// merge guard can independently re-classify the SAME owner against its own registry and refuse a
// PR body that lies about the class. Emitted only when the owner was found and classified above.
process.stdout.write(`[lm-recovery-class:${classifyRecoveryJob(entry)}]\n[lm-recovery-owner:${owner}]`);
NODE
)" || {
      log "recovery owner cannot be classified; no candidate will be produced"
      record "$NUM" "" "recovery_class_unresolved"
      write_result "failed" "recovery_class_unresolved" "$NUM"
      exit 1
    }
    RECOVERY_CLASS_MARKER="$(printf '%s\n' "$RECOVERY_MARKERS" | sed -n '1p')"
    RECOVERY_OWNER_MARKER="$(printf '%s\n' "$RECOVERY_MARKERS" | sed -n '2p')"
    ;;
esac
log "picked issue #$NUM: $TITLE"

BRANCH="${LM_DEV_BRANCH:-feature/lm-dev-$NUM}"
CONTROLLED_WORKTREE="${LM_DEV_EXISTING_WORKTREE:-}"
CREATED_WORKTREE=0
if [ -n "$CONTROLLED_WORKTREE" ]; then
  WT="$CONTROLLED_WORKTREE"
  actual_branch="$(git -C "$WT" branch --show-current)"
  if [ "$actual_branch" != "$BRANCH" ]; then
    log "controlled worktree branch mismatch"
    record "$NUM" "" "worktree_mismatch"
    write_result "failed" "worktree_mismatch" "$NUM"
    exit 1
  fi
else
  WT="$PROJECT/.worktrees/lm-dev-$NUM"
  git -C "$PROJECT" fetch origin main --quiet
  if [ ! -d "$WT" ]; then
    git -C "$PROJECT" worktree add "$WT" -b "$BRANCH" origin/main
    CREATED_WORKTREE=1
  fi
fi

# The one skills/ directory (if any) this issue's owner may touch, derived from the WORKTREE's own
# registry entrypoint by the guard's own repairScopeForOwner -- never guessed here and never trusted
# from anything but the owner id already parsed from the issue's `owner_id:` line above. Only a
# registry-verified deterministic/effect-none owner gets a non-empty scope; every other owner keeps
# the existing apps/life-manager + runtime/loop boundary untouched.
REPAIR_SCOPE=""
if [ -n "$RECOVERY_OWNER_MARKER" ]; then
  OWNER_ID="$(printf '%s\n' "$RECOVERY_OWNER_MARKER" | sed -n 's/^\[lm-recovery-owner:\(.*\)\]$/\1/p')"
  if [ -n "$OWNER_ID" ]; then
    REPAIR_SCOPE="$(node - "$WT/apps/life-manager/lib/dev-merge-guard.js" "$WT/config/loop-registry.json" "$OWNER_ID" <<'REPAIR_SCOPE_NODE'
const fs = require("node:fs");
const [guardPath, registryPath, ownerId] = process.argv.slice(2);
const { repairScopeForOwner } = require(guardPath);
const registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));
process.stdout.write(repairScopeForOwner(registry, ownerId) || "");
REPAIR_SCOPE_NODE
)" || true
  fi
fi

DENIED_PATHS="$(node -e 'const g=require(process.argv[1]); console.log(g.GUARD_SELF_PATHS.map((r) => r.source).join(" , "))' "$APP_DIR/lib/dev-merge-guard.js" 2>/dev/null || true)"
SCOPE_SENTENCE=""
if [ -n "$REPAIR_SCOPE" ]; then
  SCOPE_SENTENCE=" This issue's owner is registry-verified deterministic with no external effect, so ${REPAIR_SCOPE} is also editable for this fix, including a retained regression fixture under ${REPAIR_SCOPE}tests/."
fi
PROMPT="You are the fresh Life Manager D0 implementation agent. Fix GitHub issue #$NUM in this canonical Daisuke134/life-manager worktree. Title: $TITLE. Privacy-safe body: $BODY. Current production funnel focus: $METRIC_FOCUS. Work only inside apps/life-manager and runtime/loop. Use test-driven development: add a failing retained regression fixture first, verify RED, implement the smallest fix, then run focused tests. Preserve every existing test and privacy invariant. Do not touch docs, specs, CI, secrets, policy, external-effect owners, the recovery control plane, the foundation evaluator, this producer, the reviewer, or the merge guard. Never edit these guard-denied paths (regex; any diff touching them is rejected before test): ${DENIED_PATHS:-unavailable}. Editable: apps/life-manager/lib/, apps/life-manager/test/, apps/life-manager/scripts/ and runtime/loop/ outside those.${SCOPE_SENTENCE} If the fix needs a denied path, make no change and say so. Commit the complete allowed change on branch $BRANCH with a message referencing #$NUM. Do not push, open a PR, merge, deploy, or change production; the guarded caller performs promotion after independent review, test, canary, health and rollback gates."
AGENT_OUT="$LOG_DIR/life-manager-dev-agent-last.out"
EVIDENCE_DIR="$HOME/.local/state/life-manager/state/agent-runner-evidence/life-manager-dev-$NUM/$(date +%s)-$$"
printf '%s\n' "$PROMPT" | "$RUN_AGENT" \
  --task-class self-heal-code-agent \
  --evidence-dir "$EVIDENCE_DIR" \
  --task-label "life-manager-dev-$NUM" \
  --loop "life-manager-dev" \
  --workdir "$WT" \
  > "$AGENT_OUT" 2>> "$LOG_DIR/life-manager-dev.err.log"
AGENT_RC=$?
log "fresh agent exit=$AGENT_RC"
if [ "$AGENT_RC" -ne 0 ]; then
  log "fresh agent failed; no test gate or PR"
  record "$NUM" "" "agent_failed"
  write_result "failed" "agent_failed" "$NUM"
  exit 1
fi

PREFLIGHT_JSON="$(node - "$APP_DIR/lib/dev-merge-guard.js" "$APP_DIR/lib/self-build-daily.js" "$WT" "$REPAIR_SCOPE" <<'PREFLIGHT_NODE'
const { execFileSync } = require("node:child_process");
const [guardPath, selfBuildPath, worktree, repairScopeArg] = process.argv.slice(2);
const { classifyChangedPath, isRetainedRegressionFixture, parseNameStatus } = require(guardPath);
const { SELF_BUILD_PROTECTED_PATHS } = require(selfBuildPath);
const repairScope = repairScopeArg || null;
const git = (args) => String(execFileSync("git", ["-C", worktree, ...args], { encoding: "utf8" }) || "");
const files = new Set();
for (const args of [
  ["diff", "--name-status", "-M", "origin/main...HEAD"],
  ["diff", "--name-status", "-M", "HEAD"],
  ["diff", "--cached", "--name-status", "-M", "HEAD"],
]) {
  for (const file of parseNameStatus(git(args))) files.add(file);
}
const untracked = execFileSync(
  "git", ["-C", worktree, "ls-files", "-z", "--others", "--exclude-standard"],
);
for (const file of untracked.toString("utf8").split("\0").filter(Boolean)) files.add(file);
const changed = [...files];
const denied = changed.map((file) => ({ file, verdict: classifyChangedPath(file, {
  protectedPaths: SELF_BUILD_PROTECTED_PATHS,
  repairScope,
}) })).filter(({ verdict }) => !verdict.allowed && !verdict.conditional);
const hasFixture = changed.some((file) => isRetainedRegressionFixture(file, { repairScope }));
if (!changed.length || denied.length || !hasFixture) {
  process.stderr.write(JSON.stringify({ changed, denied, regression_fixture: hasFixture }));
  process.exit(1);
}
process.stdout.write(JSON.stringify({
  changed,
  runtime_changed: changed.some((file) => file.startsWith("runtime/loop/")),
}));
PREFLIGHT_NODE
)" || {
  log "candidate path/regression preflight RED; no test execution or PR"
  record "$NUM" "" "candidate_preflight_red"
  write_result "failed" "candidate_preflight_red" "$NUM"
  exit 1
}
RUNTIME_CHANGED="$(node -e 'process.stdout.write(JSON.parse(process.argv[1]).runtime_changed ? "1" : "0")' "$PREFLIGHT_JSON")"

TEST_LOG="$LOG_DIR/life-manager-dev-test-last.out"
if ! (
  cd "$WT/apps/life-manager"
  unset LIFE_MANAGER_REPO
  npm ci --silent
  npm test
  npm run eval
  npm run eval:panel-privacy
  if [ "$RUNTIME_CHANGED" = "1" ]; then
    cd "$WT"
    node --test runtime/loop/__tests__/*.test.mjs
    python3 -m unittest discover -s runtime/loop/tests -p 'test_*.py'
  fi
) > "$TEST_LOG" 2>&1; then
  log "test/eval gate RED; no PR"
  record "$NUM" "" "test_red"
  write_result "failed" "test_red" "$NUM"
  exit 1
fi
log "test/eval gate GREEN"

ADD_PATHS=(apps/life-manager runtime/loop)
[ -n "$REPAIR_SCOPE" ] && ADD_PATHS+=("$REPAIR_SCOPE")
git -C "$WT" add "${ADD_PATHS[@]}"
if ! git -C "$WT" diff --cached --quiet; then
  git -C "$WT" commit -m "fix(life-manager): resolve feedback issue #$NUM"
fi
if [ "$(git -C "$WT" rev-list --count "origin/main..$BRANCH")" -eq 0 ]; then
  log "no committed fix; no PR"
  record "$NUM" "" "no_diff"
  write_result "failed" "no_diff" "$NUM"
  exit 1
fi

git -C "$WT" push -u origin "$BRANCH"
PR_URL="$(gh pr view "$BRANCH" -R "$REPO" --json url --jq .url 2>/dev/null || true)"
if [ -z "$PR_URL" ]; then
  PR_URL="$(gh pr create -R "$REPO" --base main --head "$BRANCH" \
    --title "fix(life-manager): #$NUM $TITLE" \
    --body "Fixes #$NUM.

Unattended canonical Life Manager D0 pass. Full app tests and every eval passed before this PR was opened. The loop does not merge or deploy.

[lm-metric-focus:$METRIC_FOCUS]

[lm-dev-loop]

$RECOVERY_PR_MARKER

$RECOVERY_CLASS_MARKER

$RECOVERY_OWNER_MARKER

That marker is machine-readable provenance, not decoration. The daily self-build pass
(apps/life-manager/scripts/self-build-daily.js, LOOP_PR_MARKER) hands a PR to the unattended merge
guard ONLY if this exact string is in the body. A branch name and an author login are conventions a
human can satisfy by accident; this line is written by this script and by nothing else.")"
fi
if [ -z "$PR_URL" ]; then
  log "PR creation failed"
  record "$NUM" "" "pr_failed"
  write_result "failed" "pr_failed" "$NUM"
  exit 1
fi

record "$NUM" "$PR_URL" "pr_open"
write_result "pr_open" "pr_created" "$NUM" "$PR_URL"
if [ -n "${LM_DEV_TELEGRAM_TARGET:-}" ]; then
  "$LIFE_MANAGER_REPO/skills/_shared/send-telegram.sh" \
    "🤖 Life Manager dev loop: issue #$NUM → $PR_URL (tests/evals green, not merged)" \
    "$LM_DEV_TELEGRAM_TARGET" >> "$LOG_DIR/life-manager-dev.out.log" 2>&1 \
    || log "Telegram report failed"
else
  log "Telegram report skipped: LM_DEV_TELEGRAM_TARGET unavailable"
fi

if [ "$CREATED_WORKTREE" -eq 1 ]; then
  git -C "$PROJECT" worktree remove "$WT" --force || true
fi
log "pass complete: #$NUM -> $PR_URL"
