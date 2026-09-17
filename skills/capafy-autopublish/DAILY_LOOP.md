# Capafy Daily Loop — runbook for the provider-agnostic tool agent

You are a headless tool agent, fired once a day by launchd. No human is watching.
Your job: drain ONE pre-verified listing from inventory and publish it to Capafy, fully verified,
or stop cleanly if there's nothing to do. Be terse. Do NOT generate new skills here (inventory is
built by the interactive Opus session). You only DRAIN + VERIFY + PUBLISH + REPORT.

**ONE-SHOT, SYNCHRONOUS, NO BACKGROUND (self-fix-capafy-loop, 2026-07-17):** this `claude -p`
invocation is a single turn-budgeted process. There is no follow-up turn, no daemon, nobody
polling you later. "I'll monitor in background and report when it finishes" is IMPOSSIBLE here —
if you say that without having actually driven the browser/API calls to completion, you have done
NOTHING and the run is a silent no-op (observed 2026-07-17: exactly this happened, agent stayed
review_rejected). Every action must be a real tool call executed NOW, in this invocation. If you
truly cannot finish within the turn budget, STOP and report the concrete blocker — never claim
monitoring/deferred work.

## Guardrails
- NEVER publish a listing that fails `lint_listing.py` (fail-closed).
- NEVER claim success without `publish-remote-status` showing `platform_status=1` ∧
  `is_confirmed_config_keys=true`.
- Do NOT spawn the Opus vcsdd-adversary (cost). Inventory was already adversary-verified when built.
  Your verification = lint (deterministic) + your own careful re-read against BEST_PRACTICES.md +
  the in-pipeline checks (price-tab GREEN, CP2 VERIFIED) + remote-status.
- One listing per run. If anything is uncertain, STOP and report — do not force.

## Steps
0. **Reconcile the ledger with the server** (already run for you by daily_loop.sh via
   `scripts/reconcile_ledger.py`): state/published.jsonl now mirrors the SERVER — every
   online agent is recorded, and any `REVIEW_REJECTED` agent is flagged. Never trust the
   local ledger over `publish-list`/`publish-remote-status`; the server is the only truth.
1. **Five simultaneous submissions**: use the reconciled inventory verdict. Draft and under-review
   agents occupy the five slots. A `PUBLISHABLE` `resume_draft` for an exact-title repository
   `draft` may proceed at occupied=5, preserving that exact `agent_id`; completing it does not
   create a sixth Agent. `recover_delisted` and `test_and_publish` also proceed at occupied=5
   because both operate under the existing Agent ID. `under_review` remains
   wait-only. If occupied is 5, STOP and report
   "cap full, N listed" for both fresh and retry work when no resumable draft exists. Once a slot
   is free, prefer an in-place REVIEW_REJECTED repair over creating a fresh agent. Never create a
   sixth submission.
2. **Execute the authoritative inventory action**:
   a. For `test_and_publish`, open the approved version for the exact `agent_id`, run **Test Run**
      with its saved test input, and require a completed non-error response. Then use the manual
      publish control exactly once and require official `publish-list` readback to become `online`.
      If Test Run returns an LLM/provider error, do not publish: record the sanitized provider code,
      leave the version ready, and let key-health/self-fix repair it on a later wake. Never infer
      runtime health from approval alone.
      After the official `online` readback, record/report that one effect and STOP; do not continue
      into Steps 3–7 because this action has no listing/skill/icon inputs.
   b. For `recover_delisted`, open `/developer/agent/<agent_id>` in the owned CloakBrowser tab,
      click **Create New Version / 新しいバージョンを作成**, and verify the same Agent ID now has
      a draft whose card, package, and hosted keys were copied. In the fourth card submenu,
      **Version / バージョン**, select **Manual Publish / このバージョンを手動公開** and provide
      a factual change note. In **Pricing / 価格設定**, select **No Free Trial / 無料トライアルなし**
      for every plan, saving after each plan so React state cannot drop a rapid second click.
      Confirm the preview lists no free-trial days/requests, save, submit for review, and require
      official `publish-list` readback for that same ID to become `under_review`. Never rebuild or
      upload the package in this recovery path. Stop after this one bounded submission; a later
      wake handles `pending_online` by Test Run and manual publish.
      After the official `under_review` readback, report and STOP; do not continue into Steps 3–7.
   c. If reconcile flagged a `REVIEW_REJECTED` inventory item (e.g. O9 youtube) whose skill
      dir + icon + LISTING still exist → RE-PUBLISH it. **First check remote-status**
      (`vendor/capafy-publisher/packager.py publish-remote-status --agent-id <ID>` →
      `.latest_version.platform_status`/`.is_confirmed_skills`/`.is_confirmed_config_keys`).
      A rejected version is not eligible for direct resubmission: invoke
      `scripts/publish_prepare.sh <skill-dir> <LISTING.md> <icon> <ID>` so Phase A and
      `publish-init --selections-file` create a new version under the same Agent ID.
      Then complete CP1 if `is_confirmed_skills` is not already true, and continue with
      `publish_finish.sh` with the prepare-emitted `AGENT_VERSION_ID`. Never point CP3 at the stale rejected package.
   d. For `update_existing`, use the exact catalog `UPDATE.json` Agent ID and
      `from_version_id`. Set `CAPAFY_EXPECTED_AGENT_ID` and
      `CAPAFY_EXPECTED_FROM_VERSION_ID` when calling `publish_prepare.sh`; it
      checks both against fresh official inventory under the publisher lock
      before creating one new version. Complete CP1 and `publish_finish.sh` with
      the emitted `AGENT_VERSION_ID`, verify same Agent/new version is under
      review, then STOP. Do not create a fresh Agent in this wake.
   e. Else the next canonical `skills/capafy/catalog/<slug>/` listing with SKILL.md, LISTING.md and a valid icon (legacy
      `$LIFE_MANAGER_STATE_HOME/features/capafy-*` remains readable during migration) whose title
      is not online, in-flight, or rejected under an existing Agent ID.
   If neither → STOP and report the typed inventory state. Never start a second
   platform action after this wake's official effect readback.
3. **For `resume_draft`, `retry_existing`, `update_existing`, or `create_fresh` — Lint**:
   `scripts/lint_listing.py <LISTING.md>` → must PASS. If FAIL → STOP, report the failure.
4. **Sanity re-read** (you, Sonnet): open the LISTING + SKILL.md; confirm against BEST_PRACTICES.md
   §6 (no overclaim: no browse/scrape/live/retrieval/posts/sends/guarantee). If anything reads like
   an overclaim the linter missed → STOP, report it. (This is your cheap adversary pass.)
5. **Publish** (agentic CP1 — the card-save step needs YOUR eyes, not a brittle script):
   a. For new/retry/update only, `scripts/publish_prepare.sh <skill-dir> <LISTING.md> <icon>`
      → prints `AGENT_ID=`, `AGENT_VERSION_ID=`, `EDIT_URL_FILE=`, and target pricing.
      `resume_draft` uses its existing manifest and official refreshed URL without
      creating another version. Deterministic, fail-closed on lint and capacity.
   b. **Drive CP1 agentically** per `CP1_AGENTIC.md`: with `scripts/cp1_agent.py`, open the
      exact URL read from `EDIT_URL_FILE`, LOOK at each screenshot, fix the 価格設定 plan cards to the target values
      until the price tab is GREEN, then 下書きを保存 → 提出を確認. Loop until server
      `publish-remote-status --agent-id <AGENT_ID>` shows
      `latest_version.is_confirmed_skills=true`.
      Do NOT re-tune coordinates blindly — read the screenshot and decide each click.
   c. `scripts/publish_finish.sh <AGENT_ID> <skill-name> <LISTING.md> <AGENT_VERSION_ID>` → verify CP1 →
      ordinary `publish-submit --action prepare` and require strict same-Agent
      `security_ready` →
      `publish-submit --action continue_upload` exactly once → use the final review
      page for CP2 key hosting → refresh (or reuse) the `publish` review page for CP3
      exactly once → poll official status → ledger. The wrapper does not synthesize
      deep-scan findings or retry an uncertain upload.
      Fail-closed: refuses unless `is_confirmed_skills=true`, exits 0 only on
      `platform_status=1 ∧ is_confirmed_config_keys=true`. If `package_uploaded` is already true, never
      repeat the upload effect.
   (Legacy `publish_one.sh` is an unsupported no-op shim kept only as a migration
   reference. Use the a→b→c agentic flow.)
6. **Verify**: confirm remote-status `platform_status=1` ∧
   `is_confirmed_config_keys=true` ∧ `agent_type=run_online`. Screenshot the
   card-done / review-submitted page via CloakBrowser (:9222) as fresh evidence.
7. **Record + report**: append to `state/published.jsonl`, `git add -A && commit && push` (main-internal),
   and send a Telegram summary (1 listing published OR why it stopped).

## Notes
- Browser = CloakBrowser daily-driver (CDP :9222), already running. Never close it.
- Keys: CAPAFY_HOST_OPENROUTER_KEY / CAPAFY_HOST_OPENAI_KEY in $LIFE_MANAGER_STATE_HOME/.env.
- The published Skill's hosted model comes from its LISTING.md contract and the same-Agent CP1/CP2 readback; never assume Sonnet or buyer-funded provider cost.
- Keep total work tiny: 1 listing, ≤ ~15 tool calls. This protects the Claude subscription quota.
