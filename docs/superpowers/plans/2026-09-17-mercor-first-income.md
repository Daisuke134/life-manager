# Mercor First Income Implementation Plan

> **For agentic workers:** Read the linked spec and `skills/loop-development/SKILL.md`. Execute checked tasks in order in a fresh dedicated worktree from current `origin/main`. Use the available Superpowers execution workflow; one primary owns scope, effects and acceptance. Do not start a second Mercor owner.

**Goal:** Convert truthful Mercor profile and suitable applications into the first verified paid work, then learn from the actual selection funnel.

**Architecture:** Extend the existing `mercor-revenue-application` owner and shared marketplace Apply/learning contracts. Mercor browser code performs only provider-specific profile, fit and application readback. Shared receipts correlate the application with reply, work and payout. The model judges fit and proposes one improvement; deterministic code verifies facts, identity, leases, idempotency and official effects.

**Tech Stack:** Python 3, existing `apps/job-search-loop`, `skills/_shared/marketplace-core`, `skills/earn/mercor`, CDP browser lease, private JSONL receipts, launchd/`lm-loop` immutable releases.

**Spec:** [Mercor first income design](../specs/2026-09-17-mercor-first-income-design.md); existing [Mercor integration SSOT](../specs/2026-08-22-mercor-life-manager-consolidation.md).

## Global constraints

- Success is first official offer or paid work trial, then first official paid/settled earning and received payout. USD 10,000 net received in a complete month is a separate later outcome.
- Profile and résumé claims require private verified fact IDs or the operator's supplied evidence. No synthetic credentials, experience, language level, work samples or profile views.
- Interview, identity, graded assessment and independent work-trial content remain person-bound unless the exact provider step explicitly permits AI. Recheck current Mercor policy before acting.
- Existing Apply/Reply/Paid owners alone mutate Mercor; preserve leases, fences, Telegram dedupe, official readback and immutable-release lifecycle. Do not restart sibling loops to test this plan.
- Keep credential, profile, résumé, recordings, cookies and evidence out of Git and Telegram. Use private state with mode `0700` directories and `0600` files.
- A live official receipt, not a test or model assertion, promotes a business stage. Do not claim first income from a draft, submitted application, offer, or projected rate.

## Cursor and dependency order

`0 auth continuity → 1 baseline → 1A Reply/Paid continuity → 2 profile → 3 fit → 4 funnel → 5 human resume → 6 learning → 7 one-off voice → 8 release and business proof`. Authentication is the current cursor and must pass before live profile or application work. Reply/Paid repair may be investigated read-only alongside Task 0 but effects remain serialized. Each task's own focused tests and review must pass before the next. Tasks 2–6 can be developed separately only with disjoint file ownership; application state and the Mercor account remain serialized.

### Task 0: Stop unnecessary Mercor login mail and prove session reuse

**Files:** Modify `apps/job-search-loop/job_search_loop/mercor_auth_readback.py` and its `apps/job-search-loop/tests/test_mercor_auth_readback.py`; modify `skills/earn/mercor/scripts/application-owner` and `skills/earn/mercor/tests/test_application_owner.py` only if the observed issue requires a bounded recheck before invoking existing `mercor_email_auth.py`. Inspect `apps/job-search-loop/job_search_loop/mercor_page_ready.py`, `skills/browser/scripts/cdp_context_lease.py` and Reply's `skills/earn/mercor/scripts/reply-owner`; change the shared lease only if a failed seed/reuse is actually demonstrated. Do not add an auth service, new vault or second browser.

**Observed path:** `application-owner` acquires task `mercor-revenue-application` at CDP `:9222` with base vault `~/.cloak/vault/job-search-daily/auth-state.json` and writeback overlay `~/.local/state/anicca/job-search/mercor/application/auth-overlay.json`. `mercor_auth_readback` previously said logged out if the body contained `sign in` on any Mercor path. Every nonzero readback therefore invoked `mercor_email_auth`, which requested a fresh Gmail magic link. The provider's Firebase SDK builds API Authorization from `currentUser.getIdToken()`, whose record lives in IndexedDB `firebaseLocalStorageDb/firebaseLocalStorage`; cookies and local/session storage alone do not restore it in a new context. `commit-cookies` now saves cookies, `mercor-auth-store`, `mercor-session-id`, `mercor-user-ip`, and the declared Firebase IndexedDB record only after authenticated readback. Reply uses the same task lease and overlay.

**Interfaces:** `classify_auth_snapshot` must use `url`, visible authenticated navigation/application markers, and a DOM-derived `login_form_visible` signal. Return `authenticated|logged_out|indeterminate`. Only confirmed `logged_out` after a bounded second observation may call `mercor_email_auth`; `indeterminate` records a retryable state without sending mail. Preserve the last known-good overlay unless authenticated official readback and successful writeback occur.

- [x] **Capture the cause without sending a login email:** on the currently owned page, record only path, readiness, presence of the exact Mercor email-login form, presence of authenticated navigation, and auth classification. Never record cookie/token values or full email links. Compare with the prior `authenticated /explore → logged_out /explore` log sequence. The live probe showed an Explore shell without API Authorization after context recreation; the Firebase IndexedDB record was absent. The exact login form was present after the failed API read. Do not navigate a live owner tab during its pass.
- [x] **Write one focused regression** in `test_mercor_auth_readback.py`: an authenticated `/explore` page whose ordinary text includes `Sign in` remains authenticated when the official nav is present and no login form is visible; an actual `/login` page with login form is logged out; a loading `/explore` page without either signal is indeterminate. Replace the existing assertion that treats `Explore Profile Sign in` as logged out. Add an owner test that `indeterminate` does not call email auth. Run `rtk pytest -q apps/job-search-loop/tests/test_mercor_auth_readback.py skills/earn/mercor/tests/test_application_owner.py` and observe the new regression fail first.
  ```python
  assert classify_auth_snapshot(url="https://work.mercor.com/explore", visible_text="Explore Applications Earnings Profile Sign in", login_form_visible=False) == "authenticated"
  assert classify_auth_snapshot(url="https://work.mercor.com/login", visible_text="Sign in to Mercor", login_form_visible=True) == "logged_out"
  assert classify_auth_snapshot(url="https://work.mercor.com/explore", visible_text="Loading", login_form_visible=False) == "indeterminate"
  ```
- [x] **Make the smallest root-cause edit:** in `mercor_auth_readback.py`, remove body-wide `sign in` as proof of logout, collect the exact login-form signal in `observe`, and keep known authenticated markers. `mercor_email_auth.py` consumes the same signal-aware expression after the magic-link redirect. In `application-owner`, allow one short readback recheck after page readiness before deciding to request a magic link; confirmed login form permits the existing email-auth path. Do not overwrite the overlay after logged-out or indeterminate readback.
- [x] **Run the focused tests** above plus `skills/browser/scripts/test_cdp_context_lease_hangs.py` only if shared lease code changed. Confirm the existing auth and owner cases remain green. Commit and push the focused patch.
- [ ] **Prove production continuity after merge and targeted immutable release:** verify loaded `ProgramArguments` and SHA; observe three natural application wakes, including one context recreation, with official authenticated readback and zero new `Sign in to Mercor` Gmail requests while the provider session remains valid. Verify Reply can borrow the same session without a new login. Separately, if official login is truly shown, verify exactly one email login, authenticated writeback, and reuse on the following wake. Record terminal event and Telegram result. If Mercor invalidates the session server-side despite correct reuse, report that exact provider boundary and retain one bounded recovery; do not claim permanent session validity. A source-branch live probe now proves one context recreation and Authorization-backed Applications API reads; the three installed natural wakes remain pending.

### Task 1: Establish the factual baseline and protect the active release

**Files:** Update only the spec's evidence appendix if current state differs; private observations stay in `~/.local/state/anicca/job-search/mercor/`.

**Interfaces:** Produce `baseline.json` privately with `observed_at`, loaded label→SHA, unique listing/application counts, official application statuses, assessment statuses, trial/contract/earnings states, and `unknown` fields.

- [ ] Read `config/loop-registry.json`, loaded `ProgramArguments`, latest terminal events, current Mercor profile/resume/application/assessment/earnings UI, and `applications.jsonl`, `inspections.jsonl`, `submission-fences.jsonl`. Confirm the current official account identity before any tab movement. Do not use `len(inspections.jsonl)` as a listing count.
- [ ] Build a one-time read-only baseline keyed by stable Mercor listing/application IDs; use `unknown` for absent provider metrics such as profile views. Record the evidence path and official page timestamp for each nonempty stage.
- [ ] Review the baseline against the private `~/.config/anicca/job-search/profile.json` without writing values into Git. Mark each profile claim `verified`, `unsupported`, or `missing from Mercor` and each active application `submitted`, `incomplete`, `closed`, or `unknown` from its official UI.
- [ ] Acceptance: report states exact unique counts and the first currently observed loss stage; no contract, payout or profile-view claim is inferred. If readback is unavailable, record the exact missing surface and continue only independent tasks.

### Task 1A: Restore Reply and Paid observation after host admission

**Files:** Inspect `runtime/loop/lm_loop_run.py` host-admission receipt handling, `skills/earn/mercor/scripts/reply-owner`, `apps/job-search-loop/job_search_loop/mercor_reply_snapshot.py`, and `skills/earn/mercor/scripts/paid_adapter.py`. Modify the narrow proven cause only; add the focused test beside that cause. Do not restart other loops or loosen the global admission limit merely to make Mercor pass.

**Observed path:** Latest checked Reply and Paid terminal events are `blocked` with `host_admission_deferred:resource_effect_unknown`. Paid's last result is `official_work_inventory_stale`; `_official_contracts` requires a Reply-produced official contract snapshot no older than 900 seconds. Apply's `pass` does not refresh that snapshot or prove Reply/Paid effects.

- [ ] Read the exact host-admission receipt and its named resource owner for each blocked wake. Determine whether `resource_effect_unknown` represents another live effect, an unreconciled prior effect, or a stale receipt. Inspect the current loaded release SHA and owner state before a change.
- [x] Refresh the Mercor provider snapshot contract: the current UI loads `https://coil.mercor.com/v1/notifications?limit=25&filter=all` only after opening its visible Notifications control. Normalize its `{items,nextCursor,hasMore}` response to the existing Reply adapter's notification fields. The old `aws.api.mercor.com/work/comms/on-platform` endpoint returned no response and caused `mercor_reply_sources_missing`.
- [ ] Write the smallest focused regression for the proven cause, run it failing, make the minimal repair in its existing owner/host path, then rerun it passing. Preserve effect fencing and existing shared capacity rules.
- [ ] Observe a natural Reply wake that reads the official Applications/Contracts surfaces and writes a fresh identity-bound contract snapshot. Confirm the relevant Gmail/Telegram reply decision and replay-zero from provider readback; an exit code alone does not count.
- [ ] Observe a subsequent natural Paid wake that consumes that fresh snapshot. If the official list has no contract, record `observed_empty` with readback; if a contract exists, bind its exact ID and proceed through the authorized work and payment chain. Do not invent contract or earnings rows.
- [ ] Commit, push, and verify any affected targeted immutable release without restarting siblings. Acceptance: no recurring `resource_effect_unknown` for these owners, Reply snapshot age within 900 seconds when Paid reads it, and both terminal results reflect the official provider state.

### Task 2: Make profile and résumé evidence a maintained input

**Files:** Modify `apps/job-search-loop/job_search_loop/profile_setup.py`, `apps/job-search-loop/job_search_loop/mercor_pass.py`, `apps/job-search-loop/prompts/mercor-pass.md`; add focused `apps/job-search-loop/tests/test_mercor_profile_sync.py`. Reuse `skills/_shared/marketplace-core/scripts/apply_policy.py` fact extraction. Keep generated PDF in private materials.

**Interfaces:** A profile proposal is `{version, fact_ids, fields, resume_sha256}`. Official readback is `{profile_version, field_hashes, resume_visible, parser_reviewed, observed_at, evidence_ref}`; only authenticated exact-field readback activates the version. Do not put private field values in a public report.

- [x] Test that a claim without a verified fact ID is excluded, a profile PDF is not considered synced until parser fields and official reload match, and ambiguous save retains the old active version. Use a fake provider readback, not a browser mock claiming hire success.
  ```python
  assert propose_profile(facts=[{"id":"jp","claim":"Native Japanese","evidence":"private"}], claims=[{"fact_id":"jp","text":"Native Japanese"}]).fact_ids == ["jp"]
  assert activate_profile(proposal, readback={"authenticated":False}) is False
  ```
- [x] Run `rtk pytest -q apps/job-search-loop/tests/test_mercor_profile_sync.py`; the proposal/readback contract is now covered by focused tests.
- [x] Implement the smallest proposal/readback contract in the existing pass: claims require verified fact IDs, field hashes and résumé SHA are bound to a profile version, and a provider readback is recorded only when authenticated and exact. The live browser save/reload remains pending until the targeted release is installed.
- [ ] Rerun that focused test and `test_profile_setup.py`. On a real account, perform one authorized profile update using the existing owner, re-open Profile and résumé, and save an official screenshot/DOM receipt. A mismatch leaves the old version active and creates an actionable failure report.
- [ ] Commit and push the focused change before Task 3.

### Task 3: Rank for a realistic first offer, with Mercor fit evidence

**Files:** Reuse `skills/_shared/marketplace-core/scripts/apply_policy.py` unchanged; modify `apps/job-search-loop/prompts/mercor-pass.md`, `apps/job-search-loop/job_search_loop/mercor_pass.py`, `apps/job-search-loop/schemas/mercor-pass-result.v1.schema.json`; extend `apps/job-search-loop/tests/test_mercor_pass_contract.py`.

**Interfaces:** Each inspected candidate emits `{listing_id, listing_status, ranking_band, requirement_evidence:[{requirement, fact_id, disposition}], provider_fit_status, strategy_version}`. `provider_fit_status` is `allowed|warning|blocked|not_shown|unknown`. The model, not a keyword regex, supplies fit judgment and explanation.

- [ ] Add failing fixtures for: Japanese role with verified language/domain overlap; senior engineer with contradictory years; plausible role with a missing preferred skill; official fit warning; official fit blocked; closed listing. Assert no submission for a material contradiction, official block or closed listing, and no human gate for low-fit work.
  ```python
  assert result["inspected_listings"][0]["provider_fit_status"] == "blocked"
  assert result["submitted"] == []
  ```
- [ ] Run `rtk pytest -q apps/job-search-loop/tests/test_mercor_pass_contract.py`; capture the expected failing assertions.
- [x] Update the prompt and schema to require requirement-to-fact evidence, strategy version, profile material hashes and provider fit result. Prioritize official `Job fit` and new listings, but inspect complete details before ranking. A warning can proceed with a specific truthful explanation; `blocked` cannot. Preserve bounded scan, pre-effect fence, readback and other marketplace policy consumers.
- [ ] Rerun focused tests and a read-only current-listing pass. Compare the ranked top candidates with their full official requirements; correct any false high ranking before allowing submission.
- [ ] Commit and push.

### Task 4: Attribute the full Mercor selection funnel

**Files:** Modify `apps/job-search-loop/job_search_loop/mercor_application_receipt.py`, `apps/job-search-loop/job_search_loop/mercor_reply_snapshot.py`, `skills/earn/mercor/scripts/reply_adapter.py`, `skills/earn/mercor/scripts/paid_adapter.py` only where an existing receipt cannot carry the stage. Add `apps/job-search-loop/job_search_loop/mercor_funnel.py` and `apps/job-search-loop/tests/test_mercor_funnel.py`; reuse shared marketplace receipt/ledger types.

**Interfaces:** `project_funnel(application_receipts, reply_receipts, work_receipts, payment_receipts) -> dict` keyed by stable application/listing and official contract/payment IDs. Each stage has `status`, `observed_at`, `evidence_ref`, `profile_version`, `strategy_version`; absent stage is `unknown`. Unique counts are derived from IDs, never scan rows.

- [ ] Add tests for duplicated inspection rows, changed application requirements, a trial invitation without contract, a paid trial without contract, an offer without billable work, and a received payout. Assert none of the earlier states counts as received cash.
  ```python
  assert project_funnel(apps=[same_application, same_application], replies=[], works=[], payments=[])["unique_applications"] == 1
  assert project_funnel(apps=[submitted], replies=[trial_invite], works=[], payments=[])["received_usd"] == 0
  ```
- [ ] Run `rtk pytest -q apps/job-search-loop/tests/test_mercor_funnel.py` and observe the intended failure.
- [ ] Implement an additive projection over existing append-only stores. Preserve source IDs and evidence, avoid migrating or rewriting ledgers, and expose counts plus `unknown` stage coverage to the shared reporting path.
- [ ] Rerun focused Mercor receipt/reply/paid tests and compare the private projection to official Applications, Assessments, Contracts and Earnings pages. Any mismatch is `unknown` with exact evidence gap, never a fabricated zero or payout.
- [ ] Commit and push.

### Task 5: Resume the exact application after person-bound work

**Files:** Modify `apps/job-search-loop/job_search_loop/mercor_human_gate.py`, `mercor_human_gate_notify.py`, `mercor_pass.py`, and `apps/job-search-loop/prompts/mercor-pass.md`; extend `test_mercor_human_gate.py` and `test_mercor_human_gate_notify.py`.

**Interfaces:** Human gate key is `(account_id, listing_id, step_id)` with exact job URL, official step name, last official status and Telegram delivery ID. Recheck status on a natural wake. Only `completed` from the same account/application releases the gate; once released, the existing submission fence still governs Submit.

- [ ] Test one notification for repeated pending observations, continuation to other candidates, a completed step resuming the same listing, a newly added required step returning to pending, and an ambiguous submit never retried.
  ```python
  assert next_action(gate="pending", official_step="completed", same_listing=True) == "resume_application"
  assert next_action(gate="pending", official_step="unknown", same_listing=True) == "recheck_later"
  ```
- [ ] Run the focused human-gate tests and verify the new cases fail.
- [ ] Implement provider readback and gate transition using the existing owner and Telegram outbox. Include exact link/action and a safe return path in the notification. Do not click into interviews or graded forms or request media permission in the automation context.
- [ ] Rerun tests. For a real person-completed step, verify one official completion readback and one subsequent owner continuation; do not manufacture an assessment completion for a test.
- [ ] Commit and push.

### Task 6: Add source-backed, bounded improvement to the existing learning path

**Files:** Modify `apps/job-search-loop/job_search_loop/learning.py` or its existing adapter only if it can consume Mercor funnel receipts; add a Mercor-specific input builder beside `mercor_funnel.py`; extend `apps/job-search-loop/tests/test_learning_pass.py`. Do not create a second scheduler or an unbounded web crawler.

**Interfaces:** One `learning_candidate` contains `{source_url, source_kind, observation, hypothesis, target_stage, one_variable, strategy_version, baseline_cohort, proposed_change}`. Source kinds distinguish official guidance, first-person anecdote, marketing, and code. The shared evaluator returns `keep|revert|pause|insufficient_evidence` with later official cohort evidence.

- [x] Test that an X testimonial without a verifiable hire/payout cannot become an income receipt or profile fact, that a small/no-outcome cohort returns `insufficient_evidence`, and that only one strategy variable changes per candidate.
  ```python
  assert evaluate_claim({"source_kind":"marketing","claimed_income":10000})["verified_income"] == 0
  assert decide_change(before=[], after=[])["decision"] == "insufficient_evidence"
  ```
- [x] Run `rtk pytest -q apps/job-search-loop/tests/test_learning_pass.py`; the new cases now pass after the contract implementation.
- [ ] Adapt the existing learning wake to search official Mercor updates, X, first-person web accounts and GitHub for the earliest measured funnel loss. The new `mercor_learning.py` contract now keeps source labels, verified-receipt income, and one-variable proposals bounded; the wake still must record `published_at`, `observed_at`, author, claimed outcome, evidence grade, and `source_unavailable` when a search surface fails. Use official Mercor guidance as the initial hypothesis source. Propose profile proof, qualification, or application presentation one at a time. Never automatically assert a new private fact from external content. Do not add a second scheduler or scrape credentials.
- [ ] Rerun focused tests. Generate one dry read-only learning proposal from the private baseline and verify its source links, affected strategy version, and explicit `insufficient_evidence` when outcome data is inadequate.
- [ ] Commit and push.

### Task 7: Finish the Japanese Voice Actor application as a one-off

**Files:** No new recurring loop code. Private inputs are the seven user-supplied `.m4a` files and verified profile facts; write only provider-owned application state and private evidence.

**Interfaces:** Exact listing ID `list_AAABnMGxTAHltg__YT9Cvpll`. A private artifact manifest maps each uploaded recording to the official upload slot and readback. It is not an assessment result.

- [ ] In the authenticated owned Mercor context, inspect the current listing and step instructions. Verify the seven files are playable, count/duration constraints and whether the provider accepts M4A; prepare only necessary conversions from originals if the UI requires them.
- [ ] Fill factual biography from verified material: Tokyo, weekly Sunday Japanese comedy, comedy-school voice lessons, technology/AI podcast, iPhone and microphone. Mark unverified role-specific claims absent. Upload seven recordings, reopen the application and read back each file/slot.
- [ ] If English Bilingual Interview or Voice Actor Japanese Assessment remains required, create/reuse candidate-local Telegram gate and continue other jobs. After the operator completes those steps, official readback and the existing submit fence govern the one-time final submission.
- [ ] Acceptance: one official submitted confirmation for this listing or an exact pending human step; never report seven uploads alone as a submitted application.

### Task 8: Release safely and prove the first business milestones

**Files:** Update the canonical Mercor spec's cursor and this plan's checkboxes as tasks complete. Runtime release is created only from merged `main` using existing release tooling.

- [ ] Review focused diff, verify no secrets/materials in Git, and run only the relevant Mercor/shared learning tests. Ensure registry entrypoints still resolve and the old production interpreter imports required modules.
- [ ] Merge one complete reviewed implementation through the repository's required PR flow, create an immutable release from merged `main`, and use `lm-loop` targeted apply only after owner/GUI preflight. Keep reply and paid sibling releases untouched unless their exact contract was changed and tested.
- [ ] Observe one natural application wake and official profile/application readback. Observe reply and paid natural wakes and reconcile current contract/earnings inventory. Record terminal event, loaded SHA, effect receipts, Telegram delivery and replay-zero for any mutation. An exit code alone is insufficient.
- [ ] **Business milestone A:** official Mercor offer or paid work-trial invitation with exact ID, deadline and account. **B:** official accepted contract or completed paid trial. **C:** paid/settled Mercor earnings row. **D:** received payout. Leave each unchecked until provider/bank evidence exists. Continue suitable applications and learning while waiting; do not rename progress as income.
