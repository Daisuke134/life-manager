# CrowdWorks Contract Fulfillment Implementation Plan

> **For agentic workers:** Implement each task in an isolated, leased worktree from fresh `origin/main`. Use the applicable Superpowers execution process and the repository `skills/loop-development/SKILL.md`. The named existing runtime owners retain control of their labels and browser.

**Goal:** Complete each existing CrowdWorks contract's requested work, formal delivery, acceptance, and payout with one post-contract effect owner, then grow verified recurring revenue toward USD 10,000 MRR.

**Architecture:** Apply owns applications; Reply owns proposals and acceptance; the existing Paid owner owns all effects after exact contract-ID handoff. Paid persists one item per contract and one receipt per effect stage. Report reads outcome receipts only.

**Tech Stack:** Existing Python marketplace kernels and CrowdWorks adapters, Playwright/CloakBrowser CDP, private file state, `pytest`, immutable Life Manager release and `lm-loop`.

**Spec:** `docs/superpowers/specs/2026-09-17-crowdworks-contract-fulfillment-design.md`

## Live cursor (2026-09-18)

The five active official contracts are currently all `funded`; formal CrowdWorks delivery is read back for
`63583795` only, and that row is awaiting buyer inspection. Historical form receipts exist for `63583795`
and `63570481`; the former also has a buyer-visible seller message and inspection-pending readback. The
local Paid row for `63583795` must be reconciled before any retry, and the form/delivery must not be replayed.
The next implementation cursor is browser recovery and bounded contract context for the other four
contracts, followed by separate external receipt and `納品する` readback. Do not treat the old
three-contract example below as the current scope; the current scope is all five IDs: `63659463`, `63657015`,
`63583795`, `63570481`, and `63568785`.

**Ready-to-close facts:** `63583795` has a historical form receipt, verified formal delivery, and official
inspection-pending readback; continue to acceptance/settlement without another send. `63570481` has a
historical form receipt but the buyer says the customer-address answer is missing.
**Work-required facts:** `63659463` exposes common/Web-ad/video candidates and needs model-confirmed role
selection; `63657015` exposes a hearing sheet plus a common test and a designer-only branch; `63568785`
provides a Google Docs assignment and no current form. The model must read the full conversation and linked
content before choosing the action; code must not choose the first form or infer work from a URL.

**Current code/runtime evidence:** PR `#5393` adds a 180-second runtime bound and PR `#5401` preserves
the provider-inventory pre-effect hint across the owner shell. Current main is `e4f50c91`, cut into
immutable release `20260918T002409-e4f50c91`, and the targeted Paid plist readback points to that exact SHA.
The installed kickstart ended at the bound with `entrypoint_exit_124`, `effect=0`, and the claimed
occurrence returned to `queued/effect_unknown=0`; no new external effect was accepted. The next live gate
is authenticated browser readback and bounded context, not slot availability.

## Global constraints

- This plan does not authorize another session to mutate the shared CrowdWorks browser, account, state, release, or launchd labels while an existing owner is using them. Coordinate the exact effect window with that owner.
- Keep credentials and buyer content in the private SSOT/state, never in tests, Git, Telegram, or this plan.
- Do actual buyer work and verify the artifact before a completion message or formal delivery. Start production work only after official escrow readback.
- Reuse existing shared kernels, browser lock, receipts, admission and CFO events; do not copy them into a new CrowdWorks framework.
- Commit and push each meaningful slice. Merge/release/apply only after its own acceptance; preserve other 14 loops and their loaded releases.
- Read `skills/earn/gig/TODO.md` immediately before implementation. It is the canonical execution cursor; this plan is the exact patch contract for its CrowdWorks section.

## File map

| File | Responsibility |
|---|---|
| `skills/earn/crowdworks/scripts/reply_adapter.py` | Proposal-only effects and exact contract handoff; no post-contract external form or ordinary message effect |
| `skills/earn/crowdworks/scripts/paid_adapter.py` | Contract inventory, newest buyer instruction, work action, messages, external submission, milestone delivery and readback |
| `skills/earn/crowdworks/scripts/google_form.py` | Existing one-submit/confirmation fence; reuse only when the buyer task genuinely requires that form |
| `skills/_shared/marketplace-core/scripts/paid_kernel.py` | Per-contract state/effect lifecycle; change only if an adapter-only staged event cannot retain every verified receipt |
| `skills/earn/crowdworks/tests/test_reply_adapter.py`, `test_paid_adapter.py` | Focused handoff, quality, stage, duplicate and provider-readback tests |
| `skills/earn/gig/TODO.md` | Completion state and next cursor after official receipts |

### Task 1: Reconcile the three real records and recover Paid inventory

**Files:** `skills/earn/crowdworks/scripts/paid_adapter.py`, `skills/earn/crowdworks/tests/test_paid_adapter.py`.

**Interface:** `observe_active() -> list[dict]` returns an exact contract ID and provider state for every active row; `context(work_id) -> dict` returns official escrow, milestone, conversation and newest buyer-event evidence. `observe_one(work_id)` must agree with the row identity.

- [ ] Read the three authenticated URLs through the existing CrowdWorks owner. Record only sanitized ID, status, milestone, latest buyer event, task kind, due date, and required action in private evidence. Determine whether `63659463` and `63657015` are funded; screenshots alone do not prove it. Check whether proposal `306120094` maps to either contract.
- [ ] Capture the first failing `provider_inventory` boundary from the loaded release and the official `/e/contracts?status=active` page; distinguish auth, browser, DOM and timeout. Do not make a false zero-inventory success.
- [ ] Add a focused test with a realistic contract row and one changed layout/timeout fixture. Expected: every row is either represented or the wake fails with a precise error; one malformed row does not silently erase the two named contracts.
- [ ] Make the minimal adapter correction; run `pytest -q skills/earn/crowdworks/tests/test_paid_adapter.py` and `git diff --check`. Commit and push this slice.

### Task 2: Make exact contract acceptance the effect boundary

**Files:** `skills/earn/crowdworks/scripts/reply_adapter.py`, `skills/earn/crowdworks/scripts/paid_adapter.py`, and their two existing test files.

**Interface:** Reply's verified `accept_contract` receipt carries exact `contract_id`. Paid discovers that ID from official active contracts even if the Reply receipt is late; it never relies on a guessed URL. Both owners use the existing account/browser lock for their short provider mutations.

- [ ] Add a regression fixture for one `/proposals/<id>` thread redirecting to `/contracts/<id>`, followed by a funded buyer instruction. Assert Reply may accept once but produces zero post-contract messages and zero Google Form posts; Paid retains the contract work item.
- [ ] Scope Reply's `required_action` and `mutate` paths to pre-contract proposal state. Reconcile already persisted Reply intents against exact provider effects before changing routing; never discard a potentially submitted form as absent merely because the owner changed.
- [ ] Ensure the handoff survives a missed Reply wake and a duplicate acceptance readback. Run the two focused test files, `git diff --check`, commit and push.

### Task 3: Execute the buyer's actual work with per-contract quality evidence

**Files:** `skills/earn/crowdworks/scripts/paid_adapter.py`, `skills/earn/crowdworks/tests/test_paid_adapter.py`; touch shared `paid_kernel.py` and its focused tests only if its current one-intent-per-event replay rule prevents a verified work stage from advancing to the next stage.

**Interface:** A Paid work item stays keyed by `(provider, account_id, contract_id)`. Each distinct buyer-event/work/form/message/delivery stage has its own intent key and verified receipt. Repeated wakes replay zero; a new buyer revision advances the same work item without losing prior receipts.

- [ ] Add tests for five concrete paths: a Google Docs assignment with an inspectable output; a Google Form task with confirmed form receipt; a funded buyer question needing a substantive reply before work; a contract awaiting escrow; and a buyer correction after a wrong earlier response. Assert no formal delivery for missing artifact, unconfirmed external submit, unfunded work, or a reply that repeats the corrected mistake.
- [ ] Replace the present `form_url`-only decision in `decide()` with model-owned work judgment using the existing agent runner/tool path and the **full** buyer conversation, linked instruction, agreed scope and latest correction. Persist a contract-specific request/acceptance-criterion → action/artifact/proof mapping. The model proposes the actual work and quality checks; deterministic code validates exact contract binding and receipts. If the request lacks a needed fact, send one grounded question and preserve `waiting_for_buyer`.
- [ ] When a contract exposes multiple external forms, retain every exact URL, load each form's visible title/required fields/choices, and give that metadata plus the full buyer context to the model. Submit only the unambiguously requested form. Never choose the first URL or submit all candidates; preserve `waiting_for_buyer` when the mapping is unclear.
- [ ] Verify a real output against each buyer acceptance criterion (opened document/result, required fields, permissions, expected format, completeness, and due date as applicable). After submission, reopen the actual buyer-visible reply, file, link or form result and check its contents and access. Store evidence references per contract in private state; set `correct_work_verified` only for matching work. A polite completion message or provider send receipt by itself cannot pass.
- [ ] Preserve both the external form confirmation and milestone receipt as separate effects. Run focused adapter/kernel tests, `git diff --check`, commit and push.

### Task 4: Formally deliver, inspect, revise and reconcile payout

**Files:** `skills/earn/crowdworks/scripts/paid_adapter.py`, `skills/earn/crowdworks/tests/test_paid_adapter.py`; use existing shared receipt/CFO modules rather than adding a provider ledger.

**Interface:** `readback(intent)` proves the exact contract and milestone moved to inspection after the named `納品完了報告をする` control; payment and bank payout are separate observed states. A buyer revision becomes a new task version, not a duplicate first submission.

- [ ] Add tests where a normal message is visible but milestone remains open (delivery must be incomplete), where delivery click times out (official status decides retry), where buyer requests revision, where the submitted content is wrong despite a successful send receipt, and where one contract is blocked while another advances. The wrong-content case must remain open and become a new repair task.
- [ ] After verified work, use the selected milestone form and exact named submit control. Read the exact contract state back. Persist revision and payout transitions separately; never convert `delivered` to `paid` by inference.
- [ ] For `63657015` and `63659463`, let the natural owner wake perform the actual requested task and delivery only after its own official escrow/task readback. Record per-contract official effect, acceptance, settlement, payout and replay-zero. If the buyer has not provided an executable instruction, retain the precise waiting state and send a specific question.
- [ ] Run focused tests and natural-wake/provider-readback acceptance for each ready contract. Confirm that the installed loop itself read the current buyer context, performed the task, submitted the **right** artifact/reply and inspected the buyer-visible result. If the result is wrong or the buyer corrects it, trace the first bad decision, fix the same owner, re-run the focused regression, deploy the corrected release and observe another natural wake. Repeat until the item reaches `correct_work_verified` and the subsequent buyer/official state is honestly classified, or record the exact external blocker. Commit and push each repair; follow the repository's main-derived release/apply path for only the CrowdWorks labels after required host/GUI preflight. Do not reload siblings.

### Task 5: Measure the recurring revenue path and share only proven lessons

**Files:** `skills/earn/gig/TODO.md` and existing shared CFO/report integration only if an accepted CrowdWorks receipt is not already captured.

- [ ] Reconcile `proposal → contract → escrow → artifact → formal delivery → accepted → settled → payout` for each contract ID. Report cash received separately from the monthly equivalent of an active, paid retainer. Record client repeat rate, accepted delivery time, revision count, gross margin and capacity; do not call the current escrow MRR.
- [ ] After the existing backlog is delivered, target recurring scopes the team can fulfill repeatedly and propose renewal/continuation only from real buyer demand. Derive the required number of active retainers from actual net monthly value (`10,000 / verified net USD per active retainer`); leave the number unknown until pricing and FX are evidenced.
- [ ] Extract the reusable contract-ID handoff, task-quality and formal-delivery receipt rules only after CrowdWorks proof and a second provider shows the same need. For Lancers, inspect its official proposal/project/message/delivery path first; do not carry over a CrowdWorks URL assumption.
- [ ] Update the TODO with exact contract receipts and next cursor. Publish a concise internal report distinguishing code tests, natural wake, provider effect, buyer acceptance, payout and MRR.

## Plan self-check

Every spec requirement maps to one of Tasks 1–5. The largest implementation risk is the shared Paid kernel's current same-event replay rule: Task 3 explicitly requires stage advancement with separate verified receipts, while preserving replay-zero for already completed effects. The external risk is that the buyer work behind the Google Doc cannot be inferred from the screenshot; Task 1 requires authenticated inspection before choosing the action. The live correctness gate is stronger than a submit/readback gate: Task 4 keeps a wrong buyer-visible result open and requires a repaired natural owner wake.
