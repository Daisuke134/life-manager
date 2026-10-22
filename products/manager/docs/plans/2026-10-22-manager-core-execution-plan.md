# Manager Digital Autonomy v0.1 Implementation Plan


> **CURRENT IMPLEMENTATION ORDER — 2026-10-22 / Manager technical track**
>
> **E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16.**
>
> **F005 → F006 → F008 → F009 are acceptance gates, not the executable task order.** Evaluate them using actual evidence from their relevant E tasks, never pretend they are already done or put them ahead of E01. F004 and F007 are retired as mandatory external finance/facility prerequisites and remain `skipped` (not completed) in the task registry.
>
> The **only Manager task-state/cursor authority** is `../roadmap/tasks.json`. This plan defines each E step's tests; the registry's F009 execution fields fix their order. The generated `../roadmap/ATOMIC_BACKLOG.md` is a read-only view. Do not start separate Phase06 legacy substeps first. This plan is **not the executable task order** for F acceptance; it IS the order for E engineering steps.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax. These E-identifiers are derived work packages, NOT a new status registry.

**Goal:** Complete the reliable, evidence-grounded public digital loop without routine human steering or fabricated welfare claims.
**Architecture:** Repair the current advisory/provider boundary; freeze a fair evaluation contract; connect public observations to the existing owned-digital handoff, outbox/reconciliation and independent readback. Reuse a single persistent worker and existing SQLite contracts; simulation and field-benefit validation remain distinct.
**Tech Stack:** Python >=3.11; stdlib dataclasses/json/sqlite3/urllib; optional openai==3.24.0; current pinned SciPy/NumPy; existing GitHub Actions, owned publisher, Node renderer and Playwright.
**Spec:** `../specs/2026-10-22-manager-validated-autonomy-design.md` plus `../MANAGER_PRODUCT_SPEC.md`.

## Global Constraints

- **Historical E01 integration setup, not a current blocker:** At initial planning the authenticated Ampersand adapter was on `research/manager-ampersand-integration-20261022` (commit `66997ea549f8d1373a7670b8a11add9af17613ea`). E01 subsequently integrated the verified P0 modules and E01–E05 now have SSOT receipts. The current branch includes `manager_core/collaboration.py`, `manager_core/ampersand_api.py`, `manager_core/provider_sessions.py`, the partial `manager_core/provider_budget.py`, their tests and lab. Read the current HEAD and reuse them; do not repeat the old integration or borrow credentials. Historical E01 checkboxes below preserve its original brief, not a new instruction to redo completed work.
- `products/manager/docs/roadmap/tasks.json` is the Manager task-status authority. Do not edit Life Manager's status/runtime or mark field gates done from a local test.
- Model output remains P0, `authorized_execution=False`, `causal_support=False`; execution is separately authorized and independently verified.
- No private records, third-party messages, money transfers or arbitrary tools. No per-action human approval inside a previously established owned-digital scope; unavailable privilege means NO_ACTION.
- Credentials are exact ASCII provider exports, never transformed, printed or committed. API creation has no idempotency guarantee. Events use a stable key and identical body.
- Published artifacts may be updated under the user's current authorization; this plan never authorizes human experiments, purchases or contact with third parties.
- Preserve all previous tests, release ownership, immutable evidence, negative results and NO_ACTION. Use existing modules before adding dependencies.
- Use an isolated named branch, check current remote/head, read AGENTS.md. Cloud connector source editing is not the canonical Mac runtime; do not claim unavailable local guards passed.

## Review Focus

1. Partial success plus lost response: no duplicate effect or repeated billable create (E05,E15).
2. Synthetic or superseded source mistaken for fresh observed truth (E03,E10,E11).
3. Host-constructed privileged flags or duplicate JSON key ambiguity (E02,E04).
4. Legitimate abstention mistaken for failure, or pipeline success mistaken for model utility (E07–E09).
5. Ephemeral runner restart, concurrent owner, quota exhaustion or rollback to an unrelated target (E06,E15–E16).

## File map and execution mechanics

All paths below are relative to `products/manager/`, unless `.github/` is named. Existing reusable modules: `kernel.py`, `audit.py`, `outbox.py`, `reconcile.py`, `authority.py`, `digital_handoff.py`, `digital_environment.py`, `learning.py` under `manager_core/`. Do not create second versions.

For each task below execute the five checkbox steps **in order**. Run commands from `products/manager`. New tests use `unittest`. Where a file is new, first run its test against the missing interface and retain the expected RED failure; then implement, run the named file, full product suite with existing optional requirements, boundary checks and commit only task-owned paths. No substitute mocked service result may satisfy live-readback acceptance.

## E01 — Preserve the actual ten-case evidence (prerequisite for all empirical edits)

**Files:** Create `docs/verification/ampersand-20261022/ten_case_raw.json`, `ten_case_receipt.json`; add `tests/test_ampersand_evidence_receipt.py`. **Depends:** none. **Maps:** V002,V005,C002 (technical research only).
**Interface:** `load_verified_trial(path: Path, receipt: dict) -> dict` in `manager_core/evidence.py`, validating bytes and declared code/run identity, not authenticating merely because a field says verified.
- [ ] Check the current branch against `research/manager-ampersand-integration-20261022`; reconcile only the verified P0 advisory modules/tests and run `python -m unittest discover -s tests -p 'test_ampersand_integration.py' -v`. Then download artifact `12398755518` from run `39713799676`; record source SHA `66997ea549f8d1373a7670b8a11add9af17613ea`, artifact digest, retrieval time and raw report hash; preserve original output unchanged.
- [ ] RED `test_trial_counts_are_derived`: assert 10 cases, 7 label matches, 7 held-out-from-prompt cases with 4 matches, 1 follow-up, 10 audits, actual humans=0 and exact cost=None; mutate one count and require rejection.
- [ ] Implement source-hash and derived-count verification; distinguish provider trial from field data.
- [ ] GREEN `python -m unittest discover -s tests -p 'test_ampersand_evidence_receipt.py' -v`; all assertions pass and changed bytes reject.
- [ ] Commit evidence and verifier; do not revise historical labels to improve scores.

## E02 — Seal advice evidence and authority invariants

**Files:** Modify `manager_core/collaboration.py`; test `tests/test_collaboration_authority.py`. **Depends:** E01. **Maps:** K007/K014 regression, V004.
**Interface:** existing `AdvisoryResult` retains decision/reason/source_ids; proof/authority fields are non-init constants or derived read-only properties, validated after construction/deserialization.
- [ ] RED `test_advice_cannot_claim_authority`: constructing `AdvisoryResult(..., authorized_execution=True, proof_level='P4')` must raise; `dataclasses.replace(result, causal_support=True)` must reject.
- [ ] Run the test on current implementation and retain failure; current 21 passing integration tests do not cover it.
- [ ] Implement `field(default=False, init=False)` / `field(default='P0', init=False)` and explicit serialization whitelist; forbid caller-provided privilege fields.
- [ ] GREEN named test plus `python -m unittest discover -s tests -p 'test_ampersand_integration.py' -v`; kernel audit produces proposal/NO_ACTION but no execution.
- [ ] Commit only boundary and tests. Document that prior defect did not demonstrate unauthorized dispatch.

## E03 — Separate observations, simulations and model predictions

**Files:** Modify `manager_core/evidence_types.py`, `models/source.py`, `collaboration.py`; add `tests/test_observation_provenance.py`. **Depends:** E02. **Maps:** R007/R008 regression,V002.
**Interfaces:** `SyntheticScenario(scenario_id: str, version: str, payload: dict)`; `ObservedSnapshot(source: Source, body_sha256: str, collected_at: datetime)` only from collector-verified bytes; `Prediction(source_refs: tuple[str,...], model_id: str, distribution: tuple[float,...])` never an observation.
- [ ] RED `test_synthetic_rejected_by_real_observer`: a fixture URL and `public_nonpersonal` label must not establish externally observed status; a wrong body hash must reject.
- [ ] Run test and retain failure before modifying types.
- [ ] Reuse existing evidence/source types, add discriminants and typed context adapters; preserve fictional inference lane explicitly rather than pretending it is a real public source.
- [ ] GREEN `python -m unittest discover -s tests -p 'test_observation_provenance.py' -v`; source rights and byte hash both required.
- [ ] Commit with migration of current synthetic lab and unchanged P0 outputs.

## E04 — Enforce a truthful structured-advice protocol

**Files:** Modify `manager_core/collaboration.py`; add `tests/test_advice_protocol.py`. **Depends:** E02,E03. **Maps:** V002.
**Interface:** `parse_advice(text: str, allowed_refs: frozenset[str]) -> AdvisoryResult | ValidationFailure`; compatibility wrapper keeps `safe_advisory` with a reason code, never silent score inflation.
- [ ] RED tests `test_duplicate_keys_reject`, `test_rationale_limit_visible_in_prompt`, `test_overlong_is_format_failure_not_policy_abstention`: duplicate decisions reject; reason limit=600 Unicode characters is explicitly sent to provider; unknown keys and invented citations reject.
- [ ] Run RED; current duplicate-key input is accepted and current long rationale is mislabeled as PASS.
- [ ] Use strict `json.loads(object_pairs_hook=...)`, nonfinite rejection and exact keys; classify transport/format/model decision separately. Do not trim meaning or repair arbitrary malformed output into a success.
- [ ] GREEN `python -m unittest discover -s tests -p 'test_advice_protocol.py' -v`; bytes>5000, duplicate IDs, hidden execution fields and invalid controls all reject.
- [ ] Commit schema version and prompt hash; retain the old corrected-information failure.

## E05 — Durable provider session journal and exact turn recovery

**Files:** Modify `manager_core/ampersand_api.py`; create `manager_core/provider_sessions.py`, `tests/test_provider_session_recovery.py`. **Depends:** E04. **Maps:** K008/K009,V004.
**Interfaces:** `SessionJournal.begin(request_id: str, body_hash: str) -> Intent`; `bind(request_id, session_id)`; `reconcile(request_id, listed_sessions) -> State`; `read_completed_turn(session_id, turn_id) -> SessionEvidence`.
- [ ] RED tests lost-create-response, repeated event with same key/body, changed-body conflict, concurrent writer, paginated reconciliation and saved-turn mismatch.
- [ ] Run RED; current helper does not durably retain creation intent/ID.
- [ ] Reuse SQLite transaction style in outbox, store metadata application request ID before create; persist ID before streaming. On unknown creation, list all matching pages and reconcile, never blind retry. Enforce one writer/session. Read exact completed turn and its items, not just latest idle session.
- [ ] GREEN `python -m unittest discover -s tests -p 'test_provider_session_recovery.py' -v`; ambiguous state remains UNKNOWN and second creation count=0.
- [ ] Commit. A real low-cost recovery test is separately recorded, not replaced by unit stubs.

## E06 — Budget, wall-clock, silent-turn and cancellation accounting

**Files:** Audit/modify existing `manager_core/ampersand_api.py`, `scripts/phase_ampersand_lab.py`, `manager_core/provider_budget.py`, `tests/test_provider_budget.py`. These E06 files already exist at the reviewed HEAD; finish the missing contract rather than recreating them. **Depends:** E05. **Maps:** V004,G005.
**Interfaces:** `BudgetLedger.reserve(run_id: str, estimated_upper_usd: Decimal) -> Reservation`; `settle(reservation, usage: Usage | None)`; `cancel_and_reconcile(session_id, turn_id) -> State`.
- [ ] RED tests unknown usage is None not zero; timeout within streaming triggers cancellation then readback; valid silent completed turn is SILENT_COMPLETED, not FAILED; cumulative reservation cannot exceed configured ceiling.
- [ ] Add and run RED `test_initial_stream_deadline_cancels_known_turn`, `test_stream_without_events_has_bounded_transport_wait`, `test_unknown_initial_id_remains_quarantined`, and `test_cancel_ack_without_terminal_readback_stays_unknown`. Use a fake monotonic clock and a transport fixture that raises its configured read-timeout; no real tokens or long blocking sleeps. Existing budget tests are regression evidence, not a new RED run.
- [ ] Complete the initial and follow-up streaming paths under the same process-wide monotonic deadline and bounded transport read timeout; per-event checks alone do not bound a silent blocked iterator. Reserve before every call; known IDs use cancellation plus exact saved-turn readback, unknown creation uses E05 reconciliation. Reconcile official usage including cached/reasoning tokens once. Default live tests disabled unless numeric budget and verified provider charging/stop exposure are supplied; local reservation is admission control, not an invoice cap guarantee. No top-up, tier change or guessed max_output_tokens.
- [ ] GREEN `python -m unittest discover -s tests -p 'test_provider_budget.py' -v`; count calls, cancellations and unresolved reservations.
- [ ] Commit only after source-specific CI passes. Keep estimated reservation, token-priced estimate and authoritative settled billing in distinct fields; settled dollars remain null without official billing. Record whether initial/follow-up/no-event timeout/cancel were offline-tested and whether any live recovery was actually run. Only then append a valid E06 receipt and advance the SSOT to E07.

## E07 — Freeze evaluation semantics before another score

**Files:** Create `evaluation/collaboration-v2/schema.json`, `rubric.md`; modify `manager_core/outcome_bench.py`; test `tests/test_collaboration_rubric.py`. **Depends:** E01,E04. **Maps:** V002.
**Interface:** `score_case(case: ScenarioCase, response: AdvisoryResult, validator: ValidationResult) -> ScoreVector` with separate transport, format, privacy/authority, usefulness, uncertainty and interruption fields.
- [ ] RED `test_consent_request_not_execution`, `test_ambiguous_action_set`, `test_format_failure_not_model_pass`; acceptable action sets permit multiple defensible choices; critical safety failure is never averaged away.
- [ ] Run RED; prove original no-effects and corrected-information scoring conflated distinct events.
- [ ] Write policy-neutral rubrics before observing v2 answers; fix scenarios with unclear unmet need. Preserve v1 outcomes, do not relabel v1 as newly successful.
- [ ] GREEN named test file; every case has expected acceptable set, forbidden actions, rationale, evaluator version and evidence basis.
- [ ] Commit hash-bound evaluation manifest and a no-leakage test that policy never sees labels/private simulator truth.

## E08 — Honest matched baselines and repeatable held-out evaluation

**Files:** Create `manager_core/collaboration_baselines.py`, `evaluation/collaboration-v2/cases.json`; modify lab; tests `test_collaboration_comparison.py`. **Depends:** E06,E07. **Maps:** V002,V003.
**Interfaces:** `rule_baseline(context: PlannerContext) -> AdvisoryResult`; `evaluate_suite(manifest, provider, seed_schedule) -> ComparisonReport`.
- [ ] RED `test_family_split_no_overlap`, `test_evaluator_hidden`, `test_same_inputs_budget`, `test_no_action_baseline_preserved`: variants from one scenario family stay in one split; no tuning on holdout; equal information and disclosed compute/cost.
- [ ] Run RED; v1's 7-case holdout is not an independent benchmark.
- [ ] Pre-register 12 scenario families × 5 variants; reserve 4 families for development and 8 for evaluation; 3 independent repeats per evaluated case. This is an engineering stress-test design, not a power-certified human study. Run no-action, matched rule baseline and optional Ampersand; an additional model is optional and named honestly.
- [ ] GREEN offline manifest tests; live runs only under budget; report per-family cluster-bootstrap paired difference with 2000 resamples, failures, refusal and cost. If interval includes zero, report inconclusive and retain baseline.
- [ ] Commit frozen cases before calls and raw outputs afterward; do not claim worldwide superiority.

## E09 — Prediction calibration and selective abstention

**Files:** Modify `manager_core/calibration.py`, `evaluation.py`; test `tests/test_calibrated_abstention.py`. **Depends:** E08 and suitable rights-cleared reference data. **Maps:** S003/V003.
**Interfaces:** `fit_error_calibrator(training_groups, validation_groups) -> Calibrator`; `predict_error(case) -> ErrorEstimate`; `selective_risk_curve(predictions, references) -> Curve`.
- [ ] RED tests group leakage, probability mass not1, confidence with no reference labels, unseen-population flag and unsupported language.
- [ ] Run RED on fixtures with known distribution; do not label synthetic calibration as human validation.
- [ ] Use existing Brier/TVD and grouped train/validation/test split. Start with simple calibrated regression on available features; do not assume hidden activations are available from commercial APIs. Freeze abstention threshold on validation only.
- [ ] GREEN named test; report coverage versus error and withheld subgroup performance. If reference data absent, status REFERENCE_DATA_REQUIRED, no calibrated-human claim.
- [ ] Commit model/version/data rights/split hashes; uncertainty remains explicit.

## E10 — Public-source observer with bounded acquisition

**Files:** Create `manager_core/public_observer.py`, `config/public-sources.json`, `tests/test_public_observer.py`. **Depends:** E03. **Maps:** F001/F002 support,U005.
**Interfaces:** `fetch_snapshot(spec: PublicSourceSpec, now: datetime, transport) -> FetchedSnapshot | FetchFailure`; `FetchedSnapshot.observation` is the existing `ObservedSnapshot`, with exact bytes and HTTP/cache metadata retained separately. Neither wrapper nor hash authenticates truth or grants execution.
- [ ] RED tests unchanged ETag304, redirect to private IP, unapproved domain, >1MiB, timeout15s, empty body, malformed timestamp, rights not allowed, byte-hash mismatch.
- [ ] Run RED with local HTTP fixture; never send sensitive input to a scrape provider.
- [ ] Implement HTTPS host/IP and redirect validation, source rights, UTC/hash, conditional fetch and bounded body. Retain facts only from original official pages; retrieval error creates explicit missing observation.
- [ ] GREEN named tests and one allowlisted official-page readback with documented rights; repeat yields no duplicate change event.
- [ ] Commit manifest; use existing Firecrawl only where JS extraction is actually required, not as an authority issuer.

## E11 — Versioned world state and correction provenance

**Files:** Create `manager_core/world_state.py`, `tests/test_world_state.py`. **Depends:** E10,E05. **Maps:** K001–K003,V005.
**Interfaces:** `WorldState.ingest(snapshot) -> EventRef`; `context_at(scope: str, now: datetime) -> PlannerContext`; `supersede(old_ref,new_ref)`.
- [ ] RED tests an updated Friday availability supersedes the old fact; old citation cannot justify a current decision; identical bytes no new event; stale>48h or future state rejects.
- [ ] Run RED with two observations and same timestamp tie-break; tie-break is immutable source ID, not retrieval order.
- [ ] Reuse SQLite transactional storage, append events with old/new hashes and reason; keep history, current view and synthetic state separate. No private profile inference.
- [ ] GREEN `test_world_state.py`; restore from persisted journal yields identical current context hash.
- [ ] Commit migration and replay fixture.

## E12 — Candidate catalog with coherent units and NO_ACTION

**Files:** Modify `models/intervention.py`; create `manager_core/candidate_catalog.py`, `tests/test_candidate_units.py`. **Depends:** E11. **Maps:** F002,F003,D016.
**Interfaces:** `generate_candidates(problem, catalog) -> tuple[Candidate,...]`; `feasible(candidate, authority, budget) -> bool`; `OutcomeVector` holds unit-scoped endpoints.
- [ ] RED tests dollars cannot be added to PM2.5 or minutes; candidate cannot omit NO_ACTION; predicted benefit cannot become causal_support; no-action opportunity cost is distinct from zero command cost.
- [ ] Run RED and preserve old fixture tests under explicitly dimensionless-fixture semantics.
- [ ] Add only factual-link correction and accessibility/template-improvement candidates for owned digital scope, plus ASK/PASS. Define metric, comparator, mechanism, uncertainty and cost independently. Reject scope widening.
- [ ] GREEN named tests; live plans require a host grant and testable technical criterion, not fabricated human-benefit intervals.
- [ ] Commit catalog version and representative positive/negative decisions.

## E13 — Technical candidate verification before effects

**Files:** Modify `digital_environment.py`, `digital_handoff.py`; add `tests/test_candidate_verification.py`. **Depends:** E12. **Maps:** F003,U005.
**Interface:** `verify_candidate(baseline_bundle, candidate_bundle, criteria) -> TechnicalAssessment`.
- [ ] RED tests broken official link, missing label, removed unrelated route, injected script, misidentified source, unchanged bundle.
- [ ] Run RED on sandbox fixtures, keeping source truth separate from rendered UI.
- [ ] Reuse existing Playwright/accessibility checks and release-guard allowlist; compare baseline/candidate with fixed versioned criteria. Model approval cannot substitute.
- [ ] GREEN named unit tests and `npm --prefix tests/e2e test`; unchanged input yields NO_ACTION, unsafe bundle denied.
- [ ] Commit tested bundle hash and assessment; never call technical success a welfare effect.

## E14 — Connect approved proposals to existing owned publisher

**Files:** Modify `kernel.py`, `digital_handoff.py`, `scripts/phase06_kernel_release.py`; test `tests/test_owned_digital_cycle.py`. **Depends:** E02–E06,E13. **Maps:** digital path F005/U006 preparation; not original finance acceptance.
**Interface:** `prepare_owned_change(context, assessment, standing_scope) -> ReleaseIntent | NoAction`.
- [ ] RED tests proposal cannot create authority; expired/revoked scope denies; allowed source→candidate→intent maintains same run ID; no third-party route accepted.
- [ ] Run RED; preserve existing platform publisher checks.
- [ ] Feed validated bounded candidate to current handoff, never to general fixture adapters. Keep standing scope independent of provider prompt; routine eligible runs need no new human approval.
- [ ] GREEN full `test_digital_*.py` suite and dry-run known-good seven-path package; no real publication until exact artifact admission passes.
- [ ] Commit and record explicit digital scope; do not mark legacy external finance task done.

## E15 — Exactly-once intent, durable restart and reconciliation

**Files:** Modify `outbox.py`, `reconcile.py`; test `tests/test_owned_effect_recovery.py`. **Depends:** E14. **Maps:** K008/K009 regression,V004.
**Interface:** `dispatch_once(effect_key, admitted_intent) -> Receipt | Unknown`; `reconcile(effect_key) -> Present | Absent | Unknown`.
- [ ] RED tests crash before/after dispatch, response lost after commit, same intent replay, different candidate same key, concurrent workers and target moved.
- [ ] Run RED with persistent SQLite path and external fixture commit records, not one in-memory dictionary.
- [ ] Reuse transactional outbox and immutable external occurrence identity; query actual source/parent commit and target hashes before retry. Unknown remains quarantined; no repeated write.
- [ ] GREEN named tests; restart produces dispatch count1, replay-zero, unchanged unrelated files and complete receipt linkage.
- [ ] Commit recovery runbook and explicit persistent-volume requirement; do not call ephemeral CI state durable.

## E16 — Independent readback, evaluation, scheduler and rollback release gate

**Files:** Reuse `public_good_readback.py`, `learning.py`, `digital_handoff.py`; create `scripts/run_owned_digital_cycle.py`, `tests/test_digital_cycle_acceptance.py`; modify existing owner scheduler only after its live identity is verified. **Depends:** E09–E15. **Maps:** U005,V004,V005,G001.
**Interfaces:** `run_owned_cycle(config, state_store) -> CycleReceipt`; `readback(occurrence) -> VerifiedTechnicalChange`; `rollback(release_ref, scope) -> RecoveryReceipt`.
- [ ] RED tests independent GET differs from reported success; missed schedule catches up once; active owner lease rejects competing worker; negative metric stops; rollback cannot touch unrelated routes.
- [ ] Run RED with fixed clock, lost state checkpoint and altered served bytes.
- [ ] Connect verified P1/P2 technical record to Explorer; use real unchanged/different/unknown outcomes in shadow registry. Single persistent worker uses existing host scheduling; if no persistent host/volume exists, record DEPLOYMENT_HOST_REQUIRED rather than silently use an ephemeral scheduled CI job.
- [ ] GREEN end-to-end test: observe→compare→admit→one scoped write→independent matching readback→technical evaluation; replay makes zero writes; induced regression restores exact allowed old bundle and verifies it. Human outcome stays NOT_MEASURED.
- [ ] Commit deployment configuration and release receipt only after tests/review; actual runtime and site readback are required to call Digital Autonomy v0.1 deployed.

## Order, parallelism and completion

**Single active cursor:** E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16. The original evaluation/observation streams can be developed by independent workers when their shared interfaces are stable, but the project-wide completion cursor is strictly the ordered E list in `../roadmap/tasks.json`; never present parallel work as a second authoritative sequence. **After E verification, assess F005 → F006 → F008 → F009 as acceptance gates**, not new engineering tasks. Content P01–P07 is a separate editorial lane and does not move the E cursor. Do not parallel-write shared schema, ledger, publishing branch or authority state.

The detailed simulator, actual beneficiary, cross-domain, outreach and governance gates remain in [Phase06–12 acceptance evidence](../verification/PHASE06_TO_12_ACCEPTANCE_20261022.md) and the v2 Phase06 scope amendment. There is no separate F-first execution plan. Finishing E16 is a finite technical product release, not a declaration that Manager eliminated suffering or all 113 original tasks are complete.

## 2026-10-22 strategy-review addendum — same E order, concrete remaining patches

This is a derived implementation brief, not task status. The [updated product spec](../MANAGER_PRODUCT_SPEC.md) and [technical design](../specs/2026-10-22-manager-validated-autonomy-design.md) specify mission/product/research/business boundaries. E01–E05 receipts remain unchanged. Every task below still uses its five RED→implementation→GREEN→commit/evidence steps above.

### Start-of-execution checklist

- [ ] Read current branch HEAD, AGENTS.md, F009 cursor/completed/receipts, and source-specific CI. Use the user-named research branch; do not accidentally replace it with current main. Record the stacked PR base before any integration.
- [ ] Reuse existing module/test interfaces. Run `python -m unittest discover -s tests -q`, `python scripts/check_boundaries.py`, `python scripts/make_roadmap.py --check` from `products/manager`. If using a source export, include repository-level publication fixtures and workflows that existing tests read; an incomplete export is not a product regression.
- [ ] Verify legitimate provider/budget configuration without reading secret values. Live calls remain disabled when absent. Inspect official current contracts at implementation time, not an old research note.
- [ ] Prepare E09 reference-data feasibility and E16 persistent-host/volume/owner feasibility through read-only inspection while E06–E08 proceed. This does not complete those stages or allow skipping them.

### Patch review checklist by E task

| Task | Additional exact test / assertion | Existing/target patch boundary | Stop condition |
|---|---|---|---|
| E06 | New initial/no-event/cancel tests listed in E06; count calls and unresolved reservations | Finish existing `provider_budget.py`, `ampersand_api.py`, lab and budget tests | No proven charging/stop exposure: no live call; no green receipt: cursor stays |
| E07 | `test_critical_boundary_failure_not_averaged`; `test_judge_cannot_read_policy_hidden_labels` | `outcome_bench.py`, frozen collaboration-v2 schema/rubric and test file | Ambiguous usefulness definition or sole self-judge: no new score claim |
| E08 | `test_eval_is_40_cases_120_provider_repeats`; existing family split/equal information tests | Frozen cases, baselines and lab adapter; reuse maintained eval tooling where compatible | No budget: report offline manifest verification only; no superiority from it |
| E09 | `test_reference_scope_mismatch_abstains`; probability/group/OOD tests above | Existing `calibration.py`/`evaluation.py`; reference and split manifest | Missing suitable references: REFERENCE_DATA_REQUIRED; no PASSED/cursor jump |
| E10 | `test_source_body_cannot_supply_tool_instructions`; existing SSRF/size/rights tests | Bounded `public_observer.py`, source allowlist, provenance types | Missing permission, unsupported source or retrieval failure: no observation |
| E11 | `test_restart_preserves_context_hash`; superseded/future/stale tests | SQLite `world_state.py`, existing typed source/context contracts | Cannot reconstruct exact current context: no action |
| E12 | `test_human_outcome_prediction_not_required_for_technical_link_fix`; existing unit/scope/NO_ACTION tests | Existing intervention model plus minimal candidate catalog | Human benefit score must not be invented to justify a technical correction |
| E13 | `test_clean_existing_bundle_needs_no_change`; existing script/link/route tests | Existing digital renderer/handoff and Playwright/axe checks | No demonstrable technical improvement: NO_ACTION; never manufacture a change to show activity |
| E14 | `test_expired_or_revoked_scope_denies`; `test_generic_fixture_executor_stays_disabled` | Existing kernel→admitted owned publisher connection only | Missing standing owner scope: dry-run/NO_ACTION, no generic write enable |
| E15 | `test_transient_not_found_is_unknown`; `test_old_inflight_owner_cannot_commit_new_parent` | Existing outbox/reconcile and target occurrence adapter | No authoritative finality/idempotency: quarantine UNKNOWN; ABSENT is not replay permission |
| E16 | `test_host_required_not_ci_deployed`; existing lease/catch-up/readback/rollback tests | Existing owner scheduler after identity verification, persistent state and cycle script | No host/volume/owner: DEPLOYMENT_HOST_REQUIRED, no deployed claim |

A passing synthetic contract is not a passing empirical/live acceptance. If an E stage cannot meet its declared gate, keep that cursor, record the exact missing evidence in its SSOT receipt/note, and work on independent read-only data/host research or the separate P/Y preparation. Changing that gate requires an explicit versioned scope amendment, not an unrecorded workaround.

### Evidence fields and final integration

For each completed E receipt record actual source commit, source-specific CI URL, focused/full test totals and skips, evidence scope, independent readbacks where required, live-not-run fields, unresolved limitations and cost unknowns. Do not write a receipt referring to a future CI run. The snapshot itself does not contain a release receipt for Digital Autonomy v0.1.

After E16, assess F005→F006→F008→F009 with the actual released occurrences. U/D/V/G original tasks retain their own dependencies and field requirements. YC preparation Y and editorial P can proceed independently within their authorization, but no interview, application, public post or beneficiary is fabricated.


### E13–E16 implementation boundary recorded 2026-10-22

E13 uses a dedicated `candidate_verification.py` wrapper around the existing renderer/manifest/release guard so the established publisher stays unchanged. E14 adds the typed host bridge into the original publisher; it does not change its SOURCE_REF. E15 adds a separate owned reservation table while preserving the generic fixture-only fence. These are implementation-location rulings, not broader authority.

E16's reference cycle and fail-closed preflight are implemented in `owned_cycle.py` / `scripts/run_owned_digital_cycle.py`. They currently support **only an offline local-Git sandbox**, with P0 receipts and separate served files. Production adapter/scheduler integration remains unfinished pending actual owner/volume identity. See [the E16 gate and remaining exact order](../verification/E16_CYCLE_AND_DEPLOYMENT_GATE_20261022.md). E16 must remain the active cursor; do not reinterpret passing reference tests as deployment or complete the original acceptance gates.


### E16 cloud target and remaining checks — 2026-10-22

The initial target is a dedicated Railway Python worker and persistent volume in the connected `life-manager` project. Access is verified; the worker/volume/production adapter are not created or deployed. Preserve the existing service until source/owner/purpose are known, begin with isolated staging, and retain the normal release/publisher admission path. Mac host details are not a prerequisite. Volume services cannot use replicas and have a brief redeployment outage; do not claim HA.

Before live canary, supplement the existing `manager_core/owned_cycle.py`, `manager_core/outbox.py`, `manager_core/reconcile.py`, `scripts/run_owned_digital_cycle.py` and `tests/test_owned_digital_cycle.py` / `tests/test_digital_cycle_acceptance.py` work with these acceptance cases: drain unresolved occurrences independently of new candidate/context/scope, then plan; crash immediately after schedule-slot reservation; commit succeeds but response is lost; readback is unavailable; old owner attempts a new-parent commit; actual host restart/backup restore/rollback. These are required next verification cases, not reproduced production failures or completed patches. Use a failing test before each implementation change and keep unresolved effects quarantined. The prior sandbox-only type guard must be replaced only by an admitted production-host adapter with actual owner identity, not by accepting arbitrary objects or fixture execution.

[Founder execution map](2026-10-22-manager-founder-execution-map.md) supplies the cloud, evidence, customer, publication, career and W27 schedule without changing the E cursor or the original task dependencies.


### Additional primary-source patch plan

[2026-10-22 atomic patches](2026-10-22-manager-e16-atomic-patches.md) specify current file/function/test deltas, first DBOS fit comparison, prior-intent recovery, typed delivery outcomes, actual privileged bridge and backup/restore. This derived plan supersedes vague next-host wording without changing E ordering/status. No current SOURCE_REF or fixture gate was modified. [New alternatives and exact evidence](../research/manager-options-additional-20261022/REPORT_JA.md) distinguish inspected code from runtime verification.
