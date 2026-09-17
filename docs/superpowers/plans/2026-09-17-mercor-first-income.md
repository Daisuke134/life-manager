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

`1 baseline → 2 profile → 3 fit → 4 funnel → 5 human resume → 6 learning → 7 one-off voice → 8 release and business proof`. Each task's own focused tests and review must pass before the next. Tasks 2–6 can be developed separately only with disjoint file ownership; application state and the Mercor account remain serialized.

### Task 1: Establish the factual baseline and protect the active release

**Files:** Update only the spec's evidence appendix if current state differs; private observations stay in `~/.local/state/anicca/job-search/mercor/`.

**Interfaces:** Produce `baseline.json` privately with `observed_at`, loaded label→SHA, unique listing/application counts, official application statuses, assessment statuses, trial/contract/earnings states, and `unknown` fields.

- [ ] Read `config/loop-registry.json`, loaded `ProgramArguments`, latest terminal events, current Mercor profile/resume/application/assessment/earnings UI, and `applications.jsonl`, `inspections.jsonl`, `submission-fences.jsonl`. Confirm the current official account identity before any tab movement. Do not use `len(inspections.jsonl)` as a listing count.
- [ ] Build a one-time read-only baseline keyed by stable Mercor listing/application IDs; use `unknown` for absent provider metrics such as profile views. Record the evidence path and official page timestamp for each nonempty stage.
- [ ] Review the baseline against the private `~/.config/anicca/job-search/profile.json` without writing values into Git. Mark each profile claim `verified`, `unsupported`, or `missing from Mercor` and each active application `submitted`, `incomplete`, `closed`, or `unknown` from its official UI.
- [ ] Acceptance: report states exact unique counts and the first currently observed loss stage; no contract, payout or profile-view claim is inferred. If readback is unavailable, record the exact missing surface and continue only independent tasks.

### Task 2: Make profile and résumé evidence a maintained input

**Files:** Modify `apps/job-search-loop/job_search_loop/profile_setup.py`, `apps/job-search-loop/job_search_loop/mercor_pass.py`, `apps/job-search-loop/prompts/mercor-pass.md`; add focused `apps/job-search-loop/tests/test_mercor_profile_sync.py`. Reuse `skills/_shared/marketplace-core/scripts/apply_policy.py` fact extraction. Keep generated PDF in private materials.

**Interfaces:** A profile proposal is `{version, fact_ids, fields, resume_sha256}`. Official readback is `{profile_version, field_hashes, resume_visible, parser_reviewed, observed_at, evidence_ref}`; only authenticated exact-field readback activates the version. Do not put private field values in a public report.

- [ ] Test that a claim without a verified fact ID is excluded, a profile PDF is not considered synced until parser fields and official reload match, and ambiguous save retains the old active version. Use a fake provider readback, not a browser mock claiming hire success.
  ```python
  assert propose_profile(facts=[{"id":"jp","claim":"Native Japanese","evidence":"private"}], claims=[{"fact_id":"jp","text":"Native Japanese"}]).fact_ids == ["jp"]
  assert activate_profile(proposal, readback={"authenticated":False}) is False
  ```
- [ ] Run `rtk pytest -q apps/job-search-loop/tests/test_mercor_profile_sync.py`; confirm the new assertions fail for the missing proposal/readback path.
- [ ] Implement the smallest proposal/readback path in the existing owner. The model drafts concise role outcomes, 2–4 representative projects, core skills, languages and availability from verified private material; the provider adapter saves fields and PDF, reloads, compares visible values and parser output, then records a version hash. No periodic rewriting when source facts and provider fields are unchanged.
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
- [ ] Update the prompt and schema to require requirement-to-fact evidence, status, current profile version and provider fit result. Prioritize official `Job fit` and new listings, but inspect complete details before ranking. A warning can proceed with a specific truthful explanation; `blocked` cannot. Preserve bounded scan, pre-effect fence, readback and other marketplace policy consumers.
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

- [ ] Test that an X testimonial without a verifiable hire/payout cannot become an income receipt or profile fact, that a small/no-outcome cohort returns `insufficient_evidence`, and that only one strategy variable changes per candidate.
  ```python
  assert evaluate_claim({"source_kind":"marketing","claimed_income":10000})["verified_income"] == 0
  assert decide_change(before=[], after=[])["decision"] == "insufficient_evidence"
  ```
- [ ] Run `rtk pytest -q apps/job-search-loop/tests/test_learning_pass.py`; record failing new cases.
- [ ] Adapt the existing learning wake to search official Mercor updates, X, first-person web accounts and GitHub for the earliest measured funnel loss. Record `source_url`, `published_at`, `observed_at`, author, claimed outcome, evidence grade, and `source_unavailable` when a search surface fails. Use official Mercor guidance as the initial hypothesis source. Propose profile proof, qualification, or application presentation one at a time. Never automatically assert a new private fact from external content. Do not add a second scheduler or scrape credentials.
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
