# execution-notes.md — sprint-4 M1+M2

## Active /goal
`GOAL-sprint-4-M1-M2.md` (mailed to Dais via Resend id `0493d1f1-...`).

## Sub-feature status

| # | feature | phase | notes |
|---|---|---|---|
| a2 | earnings-to-settle-mirror | ✅ COMPLETE (Phase 6) | Full pipeline PROVEN LIVE on production gig: p-1782887987 roi 0→25000 |
| a1 | LAYER C STARTUP prompt update | ✅ DEPLOYED 2026-07-01 | 3 injections in gig-cli.sh: PRE-B1 CURRENT_PASS_ID binding from oldest tasks/*.json; B2 per-apply task-request-map.jsonl append; EARNED CHECK jq exact-match historical pass_id lookup + task-request-map.errors.jsonl fallback. Restarted per REQ-L3, --status=ALIVE < 30s. M2 auto-closes on first real Coconala 検収. |
| b | earn-roi-reconciler | ✅ COMPLETE | Feature (b) sprint-4 done |
| c | dispatcher-live-dormant | ✅ COMPLETE | Phase 6 converged + live E2E on prod gig; .slot_created marker deployed |
| d | recipe-6-actions | ✅ COMPLETE | 6 real wires (kill_server/send_keys/login/npm_install/git_checkout/escalate_via_bot2bot); 503 tests GREEN; INV-P1/INV-4 preserved |

## Milestone gates
- ✅ **M1** (settle pipeline ready) — reconciler + mirror COMPLETE. Full flow PROVEN LIVE.
- ⏳ **M2** (first real ¥) — pipeline FULLY WIRED including (a1) STARTUP update. Waiting on first real Coconala 検収 in production. Loop is LIVE via launchctl `ai.anicca.gig-proactive` (5-min tick) + hourly reconciler menu item.

## Regression baseline
503/503 tests GREEN.

## Block conditions
1. No settle event in 30 days across ANY slot
2. INV regression uncloseable in 3 iters
3. crypto primitive fails

## sprint-4 (a1) post-deploy notes (2026-07-01)

- (a1) STARTUP deployed successfully; gig-cli.sh --status=ALIVE
- **task #6 hook fix**: `~/.claude/settings.json` PreToolUse:Bash hook was `rtk hook claude` (PATH-dependent). Headless tmux sessions couldn't resolve `rtk` → repeated "PreToolUse:Bash hook error". Fixed by pinning to `/opt/homebrew/bin/rtk hook claude`. Post-fix: session runs clean, no more hook errors.
- **First post-fix pass**: correctly detected concurrency (multiple restarts + healthcheck cron) and skipped browser-driving to avoid collision. Registered cron `52b154a2` for future ticks. This is the CORRECT anti-collision behavior spec'd in HARD 0.36's INV-4.
- **task-request-map.jsonl materialization**: waiting for first uncontested B2 apply pass (next hourly cron fire).
- M2 auto-close path: unchanged. First real Coconala 検収 → gig-cli.sh a1 lookup → earnings row w/ pass_id → (a2) mirror → (b) reconciler → roi_jpy_realized > 0 → M2 satisfied.

## task #2 diagnosis (2026-07-01)

- `~/clips/queue/` is empty because it's fed by `producer.sh` (creates mp4+caption)
  while the proactive-loop dispatcher enqueues `produce-clip` task descriptors to
  `~/loops/clip/tasks/` (34 descriptors queued, 5-min tick, none consumed).
- The clip LAYER C session's STARTUP (`clip-cli.sh:21`) only invokes `run.sh`
  (POSTS from queue), never `producer.sh` (FILLS queue). No consumer bridges
  `~/loops/clip/tasks/` → `producer.sh`.
- FIX (out of scope for M2 sprint-4, deferred to sprint-5): mirror the gig-cli.sh a1
  pattern in clip-cli.sh STARTUP:
    1. Read oldest `~/loops/clip/tasks/*.json`
    2. If `picked.name == "produce-clip"`, invoke `producer.sh` with the task's
       platform/params
    3. Move the consumed task descriptor to `~/loops/clip/tasks/done/`
- Impact: without this fix, `produce-clip` tasks pile up indefinitely and no
  clips are ever posted. NOT a M1/M2 blocker (gig is the M1/M2 primary slot).
- Sprint-5 candidate feature: `clip-cli.sh a1-equivalent` for task-descriptor
  consumption + producer.sh wire.

## task #5 status (山本さん #5123100 あい庵 SNS ¥40k/月) — CLOSED/lost

Full timeline from gig data (2026-06-30 → 07-01):
1. Applied w/ site-specific 3-improvement proposal — buyer replied "契約手続きを進めたい"
2. Formal 見積り sent via direct_offer/4857277 (¥40,000/月, 定期購入, 期限 7/7)
3. Two follow-ups sent (2026-06-30 23:38, 07-01 01:17)
4. **Result**: 公開募集終了 + direct_offer/4857277 → 404 (offer link dead)
   → outcome=`ignored_closed`, lesson: "高額見積りは決断を促す締切設定が必要"

M2 candidate: NO (deal closed). The gig-cli.sh a1 pipeline still stands
ready for the next buyer that reaches 検収 stage. Cron 52b154a2 next
:27 tick continues the discovery.

## task #6 follow-up: hook wrapper (2026-07-01, deeper root cause)

- Absolute-path fix (`/opt/homebrew/bin/rtk hook claude`) alone was NOT enough.
- Continued observing "Failed with non-blocking status code:
  node:internal/modules/cjs/loader:1458" in gig session — Claude Code's own
  internal Node.js error trying to interpret rtk's empty stdout on
  non-rewrite pass-through cases.
- FIX: `/Users/anicca/.claude/hooks/rtk-hook-wrapper.sh` (installed +
  settings.json pointed at it) — always emits valid JSON:
  * rtk rewrite? → forward rtk's JSON
  * rtk silent? → emit `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}`
- Will take effect on next gig-cli restart (currently: 28min-subagent completed
  with 0 applies but tmux still ALIVE; no active hook errors right now).

## task #6 further follow-up: wrapper newline (2026-07-01, +30min)

- After installing rtk-hook-wrapper.sh, hook errors REDUCED but not to zero
  (dropped from 8+/500lines to 3/500lines).
- Root cause: wrapper output was missing trailing newline (`printf '%s'` →
  `printf '%s\n'`). Some Claude Code hook parser paths need line-terminated
  output.
- After fix + gig-cli --restart: session progressing through Coconala gig
  pass 45 with proper phase structure (B1 nurture → B2 apply → B3 learn →
  B4 improve → B5 share → finalize + .last-pass).
- Expected: task-request-map.jsonl materialized during B2 apply; task #1
  verified on B5+finalize.

---

## 8i REPO-CONSOLIDATE — execution log (in progress)

**Source:** Daisuke134/anicca-products @ `540b7a428e8e259e47acaa715812802fdb19f947`, path `apps/life-call/`
**Target:** Daisuke134/life-manager (id 1248111245), path `apps/life-manager/`
**Branch:** `claude/life-manager-e2e-handover-qkp2q6`

### Completed gates
- [x] Read-only source access obtained (add_repo, shallow clone at /workspace/anicca-products)
- [x] Source manifest: 184 tracked files under apps/life-call (183 migrated, .vcsdd/ metadata excluded)
- [x] Snapshot copy apps/life-call -> apps/life-manager (183 files) + canonical spec -> docs/superpowers/specs/
- [x] Byte-equivalence proven: 0 diffs across all 183 files (docs/manifests/8i-life-call-source-manifest.txt, sha256 per file)
- [x] Secret/PII scan: clean (only synthetic fixture phones, no keys/real PII)

### Remaining gates (blockers noted)
- [x] Focused tests on migrated lib/** (all green)
- [x] Full Life Manager test suite: 633 TAP pass / 0 fail (reviewer-measured; earlier 606 was a count-method imprecision)
- [x] Every eval suite: calendar 21/21, late 12/12, context 12/12, score 27/27, panel-privacy pass
- [x] Production build smoke: server.js/scheduler.js syntax OK; nixpacks entrypoints valid
- [x] Fresh-context adversarial review from detached candidate commit 8752cf35: VERDICT APPROVE, 0 blockers, 7 notes (manifest 183/183 sha256 verified vs source AND target; exactly 1 differing line = documented path rename; boot with empty env verified; history-safety PASS)
- [ ] Normal PR + merge
- [ ] Railway deploy of exact merged commit  — NEEDS Railway credentials
- [ ] Prove active Railway commit == canonical main
- [ ] Real production L3: /health, Telegram, canonical /panel  — NEEDS production access
- [ ] Archive + redirect anicca-products (ONLY after cutover)  — NEEDS admin on source repo

### Adversarial review notes (2026-07-24, fresh-context agent, commit 8752cf35)
- APPROVE. Non-blocking notes: test-count label (633 actual), landing subset is 5 migrated + 1 new README, Mac-host paths in daily-preflight-collectors.js carried byte-identically (gateway-host code, not Railway boot), residual "life-call" identity strings consistent, diff secrets/PII clean.
- Reviewer flagged PRE-EXISTING PII on main (predates this PR): execution-notes.md task #5 section names a Coconala counterparty. Scrub separately — public repo.
- Railway boot check: server.js starts with EMPTY env (PORT defaults, no boot-required secrets); all providers lazily guarded.

## 10g BRAIN-a — done (2026-07-24, L2)
- intent-graph.js closed schema (6 kinds, provenance/confidence/expiry), correction-expires-prediction contract, 3 persona fixtures. Tests 7/7; full suite fail 0. Spec §10 row updated in same commit.

## 10h BRAIN-b — done (2026-07-24, L2)
- opportunity-engine.js six-factor gate over 10g graph; intent-cases.jsonl 18/18 (100%); contract 4/4; wired into test+eval chains; full suite fail 0. Spec §10 updated (26 pending).

## 12a MEN-a — done (2026-07-24, L2)
- mental-trigger.js context-driven trigger engine (pre_event/between_events/pre_sleep), cap 3/day, fixed-time impossible by construction; men-cases.jsonl 15/15 (100%); contract 4/4; full suite fail 0. Spec §10 updated (25 pending).

## 11a PHY-a — L2 done (2026-07-24); L3 (real calendar detection) pending
- care-detector.js personal-cadence + explicit-goal detection, no fixed cycle (0-1 visits never flag), no diagnosis fields; phy-cases.jsonl 12/12 (100%); contract 4/4; full suite fail 0. Spec §10 updated (row stays pending, L2 recorded).

## 8i REPO-CONSOLIDATE — DONE (2026-07-24, production cutover complete)
- Cutover executed on the Mac-side agent with Railway access: service re-pointed to life-manager/apps/life-manager, active deployment 6806b0d4 = commit a7ac84d4 (exact main), /health 200 build lm27-voicemail-v1, zero-downtime 358/358, real TG message id 217, authenticated /panel all sections 200.
- Independently verified from cloud session: anicca-products archived=true via GitHub API readback; evidence report in docs/evidence/8i-cutover-report.md (PR #1077); merge containment of a7ac84d4 in origin/main.
- §10: 8i done. Pending count 24.

## 9b MKT-b / M-2 — done
- Existing `ai.anicca.life-manager-daily` label, 10:15 cadence, rotation, account, and shared
  agent-runner remain in place. The slideshow/card creative contract is replaced by the canonical
  16-row local FFmpeg video renderer.
- TDD: missing generator/runtime RED, then generator `5/5` and runtime/launchd `6/6` GREEN.
  Controlled method 1 exposes recursive wrapper invocation; corrective exit-73 guard is RED→GREEN.
  Method 2 exposes combined generation/distribution self-monitoring; it is stopped before side
  effects. Method 3 locks distribution for 9c and succeeds as a bounded generation-only pass.
- Fresh Luna probe returns `LM_LUNA_PROVIDER_OK`. launchd run count advances and finishes exit 0
  with `marketing-agent` → `luna-medium-decision` → `codex/gpt-5.6-luna`, attempt 1.
- Production rotation reads back A01/A02/A03 on three consecutive logical days. All three are
  1080×1920 H.264/AAC, 34.666667s and fresh full-decode exit 0.
- Runtime ledger records provider-reported token counts, subscription cost tier, null unavailable
  provider-equivalent price, and actual marginal cost USD 0 without inventing a price.
- PR #1079 security-gate audit: accepted main run 30069163816 already has the identical
  repository-wide baseline failures (PII shapes 60, gitleaks findings 24, Python workflow missing
  pytest/hypothesis). Changed-path secret scan and every 9b test/eval pass; no detector or test is
  weakened to make the PR green.
- Evidence: `docs/evidence/9b-marketing-video-runtime.md`. Pending count becomes 23; next is 9c.

## 9c MKT-c / M-3 — done
- Reuses the existing `anicca.affirms2` IG account, shared instagrapi poster, and TikTok Postiz
  integration `cmp9txjdp01c8oh0yb6dhlarr`; no account or loop is created.
- TDD binds the same local MP4 and caption file to both adapters and records the same creative id,
  video SHA, and caption SHA in a mode-600 append-only ledger.
- Real IG Reel: `https://www.instagram.com/reel/DbKkdfjsaTZ/`; deterministic logged-out checker
  returns `found=true`, `verdictMaterial=pass`.
- Real TikTok video:
  `https://www.tiktok.com/@anicca_buddha/video/7665973874504256785`; provider id
  `cmryjod3q0193pe0yastxx34h`; logged-out metadata and full public decode pass.
- Corrective TDD rejects Postiz's profile-only release URL and resolves only a recent,
  caption-matching `/video/<id>` artifact. The original profile-only private ledger row remains
  append-only and honest.
- Corrective launchd pass exits 0 on Luna, distribution ledger stays `3→3` (no repost), and the
  existing Telegram report returns message id `3378`.
- Evidence: `docs/evidence/9c-marketing-distribution.md`. Pending count becomes 22; next is 9d.

## 9d MKT-d / M-4 — started; real-time gate pending
- Adds an append-only, mode-600 daily metrics ledger keyed by real JST date and the exact 9c
  creative/video/caption hash pair. Same-day runs are idempotent; gaps reset the streak; simulated
  backfill cannot satisfy the seven-day gate.
- Real Day 1 reads Instagram `17/0/0` and TikTok `9/0/0` views/likes/comments from their public
  URLs. Unavailable watch-time/completion/click/signup values remain null.
- Corrective TDD fixes the integration schema from `reason` to canonical `next_change_reason`.
  Core/runtime tests are `5/5 + 8/8`.
- Controlled launchd finishes exit 0 with Luna attempt 1, distribution `3→3`, measurement `1→1`,
  and real Telegram message id `3379`.
- Evidence: `docs/evidence/9d-marketing-self-improve-started.md`. Pending count remains 22 because
  six distinct real dates remain; cursor advances to independent row 9e.

## 9e MKT-e — equivalence PASS; authentication gate pending
- Direct TikTok Studio adapter uses the existing CloakBrowser CDP context, exact MP4/caption paths,
  and the same terminal fields as Postiz. It requires individual public URL, exact logged-out
  readback, real date, and direct cost USD 0.
- Distribution/direct tests are `10/10 + 8/8`. Only two consecutive real direct days can retire
  Postiz; duplicate/gap/simulation/failure rows cannot.
- Postiz remains the default and its ledger stays at three rows. The exact direct migration env
  gate remains unset.
- Real target login reaches TikTok email verification, but the designated masked mailbox is absent
  from connected Gmail, Keychain/env, and an authenticated domain mail route. No code is guessed,
  no file is uploaded, and no post is created.
- Evidence: `docs/evidence/9e-tiktok-direct-migration-started.md`. Pending remains 22; next is 9f,
  whose Phase 1 prerequisite is evaluated before any X handoff.

## 9f MKT-f — prerequisite blocked; no owner handoff
- A closed gate reads the canonical §10 statuses for 8e/8f/9b/9c/9d/9e. The live blockers are
  `8e, 8f, 9d, 9e`.
- Live output keeps both owner handoff and agent posting false. X credential/session/draft/upload/
  post side effects are zero.
- Even with all prerequisites done, the gate permits only a minimal owner handoff and never agent
  impersonation. A real owner status URL makes the launch permanently one-time.
- Contract tests are `5/5`. Evidence: `docs/evidence/9f-x-owner-launch-blocked.md`.
- Pending remains 22; cursor advances to independent 10a.

## 10a DEV-a — done (real Telegram + DB)
- Explicit feedback is classified and scrubbed at the Telegram edge. The database receives only
  summary, allowlisted labels, and an HMAC source reference; it has zero raw/identity columns.
- Real user message id `3922` receives real bot acknowledgement id `3923`. Railway Postgres row
  id `1` is queued with `feedback,calendar,panel` and a PII-free summary.
- Staging deployment `ac0f6b9a-2a15-4762-88fc-52b7fe92caa4` succeeds after two source-root methods
  fail before build. Production webhook is restored with pending 0/error null; temporary staging
  secrets are removed.
- Focused `8/8`, full fail 0, every eval 100%, changed-path secret/PII 0.
- Evidence: `docs/evidence/10a-telegram-feedback-intake.md`. Pending becomes 21; next is 10b.

## 10b DEV-b — done (real GitHub issue + existing D0)
- The worker atomically claims one privacy-safe production intake row with `FOR UPDATE SKIP LOCKED`,
  creates or recovers a GitHub issue by deterministic HMAC-derived marker, and writes the exact URL
  back to the row. A failed provider call releases the claim; a stale incomplete claim is reclaimable.
- Real production row `1` creates [issue #1085](https://github.com/Daisuke134/life-manager/issues/1085).
  GitHub readback is OPEN with `lm:type:self-heal`; DB readback is `issued` with the exact URL.
- A second pass is `no-op`, the exact marker exists on one issue only, and the existing D0 picker
  selects `#1085`.
- The single `ai.anicca.life-manager-dev` 04:10 launchd job points to the canonical wrapper, which
  runs issue generation before delegating to the existing D0.
- Focused tests are `7/7`; full tests exit 0; all evals remain 100%; changed-path secret/PII scans
  are clean.
- Evidence: `docs/evidence/10b-feedback-to-github-issue.md`. Pending becomes 20; next is 10c.

## 10c DEV-c — done (real fresh-agent PR)
- The existing launchd D0 now targets only canonical `Daisuke134/life-manager`, `origin/main`, and
  `apps/life-manager`. It uses the shared fresh-agent runner and performs full tests/evals before
  creating a PR; it contains no merge or deploy action.
- Run 1 exposes a missing required runner loop argument: fresh agent exits 2 and PR #1087 initially
  contains only D0 infrastructure. The PR is not merged. Corrective TDD makes a nonzero agent exit
  fail closed before test/PR gates.
- Run 2 selects real issue #1085, fresh agent exits 0, commits `9c93bf36…`, and changes the missing
  Calendar model/UI action to exact `Connect Calendar` with focused regression coverage.
- D0 independently passes full tests and every eval, updates real PR
  [#1087](https://github.com/Daisuke134/life-manager/pull/1087), appends a `pr_open` state row, and
  reports to Telegram with message id `3386`.
- Evidence: `docs/evidence/10c-feedback-dev-loop-auto-pr.md`. Pending becomes 19; next is 10d.

## 10d DEV-d — done (real production error intake)
- Reuses `lm_feedback_intake`, its unique `source_ref`, the existing issue worker, the
  `lm:type:self-heal` label, and D0. No second incident queue or developer loop is introduced.
- The closed builder maps provider timeout, failed call/email/post, 5xx, and eval regression into
  three incident classes. Raw provider/error content has no output field and is not part of the
  HMAC fingerprint.
- Controlled live probes observe a timer deadline, child-process side-effect exit 23, and local
  HTTP 503 plus eval exit 1 before persistence.
- Production rows `2/3/4` create real issues
  [#1088](https://github.com/Daisuke134/life-manager/issues/1088),
  [#1089](https://github.com/Daisuke134/life-manager/issues/1089), and
  [#1090](https://github.com/Daisuke134/life-manager/issues/1090).
- A second injection is duplicate for all three; a fourth worker pass is no-op. DB and GitHub
  marker readbacks match, and forbidden-content checks are zero.
- Focused tests are `22/22`. Evidence: `docs/evidence/10d-production-error-intake.md`.
  Pending becomes 18; next is 10e.

## 10e DEV-e — pending after three fresh-adversary stops
- Real production error #1088 enters the existing D0 and produces exactly one PR,
  [#1092](https://github.com/Daisuke134/life-manager/pull/1092).
- Fresh implementation commit `67f38e33…` adds a hanging-calendar-provider regression and bounds
  Composio execution with a 15-second abort signal.
- The post-PR promoter requires exact head/base/mergeability, one issue/one PR, closed path scope,
  blocked actions zero, fresh full test/eval/privacy, fresh artifact-only adversary PASS, and a clean
  worktree before merge.
- Real out-of-guard commit `a94208d3` returns exit 3 with `path_allowlist`; merge/deploy remain zero.
  The controlled file is removed before promotion.
- Corrective RED `5/6` → GREEN `6/6` prevents the guard's own regex definitions from being mistaken
  for executed actions without exempting executable lines.
- Fresh adversary method 1 stops before merge with four blockers: stale rollback-deployment
  acceptance, merge-head TOCTOU, unbound review head, and indirect privileged-action bypass.
  Corrective provider interaction tests are RED `6/10` → GREEN `10/10`; rollback now requires a
  new post-mutation deployment ID, merge uses `--match-head-commit`, review output carries exact
  `reviewed_head`, and routine D0 changes are confined to non-privileged lib/test capabilities.
- Fresh adversary method 2 also stops before merge: candidate tests run before review with inherited
  credentials, and bootstrap files lack immutable review binding. Final RED `8/12` → GREEN `12/12`
  moves review before candidate execution, binds exact head plus complete binary-diff SHA-256,
  executes full gates with a minimal temporary-HOME environment, and blocks routine env/filesystem/
  network/process access. Bootstrap is exact #1088/#1092 reviewed-diff only and cannot recur.
- Method-3 preflight catches bootstrap test rejection-token fixtures as capabilities. Corrective
  RED `8/9` → GREEN `9/9` excludes only reviewed credential-free bootstrap test lines; runtime and
  guard source remain capability-inspected and complete-diff bound.
- Fresh adversary method 3 still fails before merge: the reviewer runner itself inherits credentials
  without filesystem/network isolation, PR uniqueness reads only the first 100 open PRs, and the
  rollback target is not proven to be the currently active exact commit. PR #1092 and issue #1088
  remain OPEN; merge/deploy/provider mutation are zero; production deployment remains
  `73afe498…` SUCCESS.
- Stop boundary after three approaches. Resume requires a credential-free read-only reviewer
  sandbox, paginated all-PR uniqueness, and active-deployment exact-commit discovery in a trusted
  promoter outside candidate code. Pending remains 18; cursor advances to independent 10f.
- Railway postflight binds the GitHub merge SHA to live `meta.commitHash`, production health, and
  issue closure. Failure triggers one rollback to the pre-verified healthy deployment.
- The promoter publishes exact merge/deployment/adversary/health receipt values on PR #1092 after
  successful production readback. Evidence: `docs/evidence/10e-auto-merge-deploy.md`.
  Pending becomes 17; next is 10f.
