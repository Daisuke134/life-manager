# Alpaca ETF Runtime Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the research-only `alpaca-etf-126d-momentum-v1` result into a deterministic, paper-only Alpaca ETF execution boundary that can produce one official paper receipt without permitting live stock orders.

**Architecture:** Keep signal calculation pure and separate from Alpaca I/O. The policy consumes a release-pinned `StrategyCard`, completed daily bars, explicit position ownership, and effect-fence state; it returns a JSON-safe decision. The broker adapter later supplies bars and paper orders, while the live boundary rejects this ETF asset class until a separate promotion gate is passed.

**Tech Stack:** Python 3 standard library, `Decimal`, existing `StrategyCard`, `unittest`, existing Alpaca CLI adapter, Life Manager immutable release workflow.

## Global Constraints

- Fixed ETF universe: `SPY`, `QQQ`, `IWM`, `DIA`, `EFA`, `EEM`, `TLT`, `GLD`.
- Fixed policy parameters: 126 completed sessions for ranking, top momentum symbol only, 21 completed holding sessions.
- Fixed sizing: `$10.00` notional; expected round-trip slippage is 20 bps and expected cost is `$0.02` before any provider-reported difference.
- The policy must reject missing, duplicate, unsorted, future, or in-progress daily bars; it never fills missing values with zero.
- A position or order may be acted on only when `owner_id=alpaca-investment-live` and `strategy_id=alpaca-etf-126d-momentum-v1` match exactly.
- Paper ETF orders are allowed only after deterministic selection and effect-fence checks; live ETF orders remain rejected.
- No Binance transfer, wallet creation, cap increase, live canary, scheduler restart, queue mutation, or registry/runtime-host edit is part of this plan.
- Every production-code change follows RED → GREEN → focused regression tests before commit.
- Historical holdout profit and paper P&L are evidence, not settled live revenue and not permission to increase capital.

---

### Task 1: Pure completed-session ETF policy

**Files:**

- Create: `skills/alpaca-investment/etf_policy.py`
- Create: `skills/alpaca-investment/test_etf_policy.py`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` after the focused test and implementation are verified

**Interfaces:**

- `evaluate(snapshot: Mapping[str, Any], card: StrategyCard | None = None, *, owner_id: str = "alpaca-investment-live") -> dict[str, Any]`
- Required snapshot fields: `daily_bars` (symbol → ordered rows), `completed_through_session` (`YYYY-MM-DD`), `position` (`None` or owned position mapping), `open_orders`, `unresolved_intents`, and `last_decision_session` (`None` or `YYYY-MM-DD`).
- A bar accepts `t`/`timestamp`, `o`/`open`, and `c`/`close`; output contains `action`, `strategy_id`, `symbol`, `decision_session`, `entry_after_session`, `signal_inputs`, `reason`, and `expected_cost_usd`.
- Signal rule: compare each symbol’s latest completed close with its close 126 common sessions earlier; rank by highest Decimal return and break ties by symbol ascending.
- Entry rule: with no owned position, no pending effect, and a new decision session, return `ENTER` for the selected symbol with `entry_after_session` equal to the completed decision session; the order layer must submit no same-session duplicate.
- Position rule: return `EXIT` after 21 completed sessions or when the selected symbol changes; otherwise return `HOLD`. A foreign, malformed, or ambiguous position returns `NO_TRADE`.

- [x] **Step 1: Write failing tests.** Added 127-session fixtures across all eight ETFs and tests for deterministic top-symbol selection; future-bar rejection; missing-symbol rejection; duplicate/unsorted session rejection; same-session re-entry rejection; pending-order fence; foreign-position rejection; 21-session exit; and symbol-change exit.
- [x] **Step 2: Run the focused tests and observe RED.** `python3 -m unittest test_etf_policy` failed as expected with `ModuleNotFoundError: No module named 'etf_policy'` before production code existed.
- [x] **Step 3: Implement the minimum pure policy.** `etf_policy.py` now normalizes sessions and Decimal prices, requires the common latest session to equal `completed_through_session`, computes the ranking with a complete symbol tie-break, and returns fail-closed decisions without broker, subprocess, filesystem-write, scheduler, or credential imports.
- [x] **Step 4: Run focused and regression tests.** `test_etf_policy` and `test_strategy_policy` pass `24/24`; the complete `skills/alpaca-investment` discovery suite passes `175/175`.
- [x] **Step 5: Record evidence and commit.** The SSOT and this plan record that the policy is code-tested only and produced no order or P&L. The implementation is committed and pushed as `feat(investment): add fail-closed ETF daily policy`.

**Task 1 result:** This closes only the pure policy boundary. It does not create a selected runtime state, ingest broker bars, submit a paper order, produce a provider receipt, or authorize live capital.

### Task 2: Release-pinned selection and allocator dispatch

**Files:**

- Modify: `skills/alpaca-investment/strategy_policy.py`
- Modify: `skills/alpaca-investment/allocator.py`
- Modify: `skills/alpaca-investment/test_strategy_policy.py`
- Create: `skills/alpaca-investment/test_etf_allocator.py`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` after verification

**Interfaces:**

- `candidate_cards()` returns the canonical ETF card in addition to the two BTC cards.
- `load_selected_card(state)` accepts the exact ETF card mapping only when the release SHA and canonical card match byte-for-byte.
- `allocator.choose()` dispatches ETF snapshots to `etf_policy.evaluate()` and keeps BTC behavior unchanged.
- `allocator.gate()` allows only paper ETF decisions; `allocator.order_for()` emits an explicit `asset_class="us_equity"` order shape.

- [x] **Step 1: Write failing regressions** for loading the selected ETF card, rejecting a stale/mutated ETF card, preserving BTC selection behavior, exposing the fixed ETF candidate universe, dispatching the pure policy, and refusing an ETF decision in live mode.
- [x] **Step 2: Run the focused tests and observe RED**; the pre-implementation run failed on the missing ETF card/candidate/order branch.
- [x] **Step 3: Implement the smallest dispatch** by importing the pure ETF card/policy, preserving the existing BTC allow-list, adding fixed ETF candidates when complete daily bars exist, and keeping live ETF orders fail-closed.
- [x] **Step 4: Run the focused allocator/selection suite.** `test_strategy_policy test_etf_allocator` passes `21/21`; the complete Alpaca discovery suite passes `183/183`. The selected-state behavior is verified in temporary test state only; no production state was written.
- [x] **Step 5: Commit and push** the release-pinned selection boundary as `c92d240299` plus the current dispatch changes; no production release was applied from this worktree.

**Task 2 result:** The code boundary is complete, but the Life Manager production release still lacks the ETF files and no production `selected-strategy.json` exists. Task 5 remains required before this becomes a runtime or paper-receipt pass.

### Task 3: Completed daily-bar ingestion

**Files:**

- Modify: `skills/alpaca-investment/alpaca_cli.py`
- Create: `skills/alpaca-investment/test_alpaca_cli.py`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` after read-only command verification

**Interfaces:**

- Add a bounded stock-bars read that returns the fixed universe, sorted by session, with `completed_through_session` explicitly recorded.
- Use the Alpaca market clock to exclude the current incomplete session; a provider row after the declared completed boundary is a typed failure.
- Preserve provider response/source identifiers for later paper receipts; never convert missing bars or unavailable cost to zero.

- [x] **Step 1: Write failing adapter tests** for exact fixed symbols, bounded lookback, completed-session cutoff, duplicate rows, future rows, and provider errors.
- [x] **Step 2: Run the adapter tests RED** before changing the CLI adapter; the missing `read_etf_daily_bars` boundary and fixture setup were caught.
- [x] **Step 3: Implement the read-only stock-bars operation** with `data multi-bars`, `--feed iex`, `--adjustment split`, `--timeframe 1Day`, a bounded 260-calendar-day window, NY-session filtering, 127 common sessions, deterministic source hash, and no order calls. `run.py` now requests the same boundary for both the initial and fresh allocator snapshots. The bounded `data_multi-bars` response budget is `512 KiB`; other CLI operations retain the `64 KiB` limit.
- [x] **Step 4: Run adapter plus pure-policy regressions.** Adapter tests pass `6/6`, the complete Alpaca discovery suite passes `200/200`, and a live paper read-only preflight returned all eight symbols, 127 common sessions through `2026-09-25`, and one source receipt without submitting an order. No live provider order, paper order, or P&L receipt was created.
- [x] **Step 5: Commit and push** the ingestion boundary; the source hash is an evidence reference, not a paper trade or P&L receipt.

**Task 3 result:** The read-only ingestion code and the bounded production-shaped paper data read are complete in this worktree. The loaded production release still lacks the code, and the preflight is a bar-source read rather than a paper order or P&L receipt. Task 4 code is now complete; the Life Manager release handoff and natural paper receipt remain open.

### Task 4: Paper order, ownership, reconciliation, and receipt

**Files:**

- Modify: `skills/alpaca-investment/alpaca_cli.py`
- Modify: `skills/alpaca-investment/allocator.py` (the run-path allocator)
- Create: `skills/alpaca-investment/etf_ownership.py`
- Modify: `skills/alpaca-investment/run.py`
- Create: `skills/alpaca-investment/test_etf_execution.py`
- Modify: `skills/alpaca-investment/test_alpaca_cli.py`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` after focused verification

**Interfaces:**

- Paper stock order must be `asset_class=us_equity`, symbol in the fixed universe, notional exactly `$10.00`, market/day, and carry owner/strategy/client identity.
- Live mode must return a typed refusal for every ETF order attempt.
- Ownership state must record owner, strategy, symbol, decision session, order identity, provider receipt identity, and position quantity; foreign state is never adopted.
- A receipt is complete only after provider order/fill/account readback and replay-zero identity checking.

- [x] **Step 1: Write failing order/ownership/reconciliation tests** for paper acceptance, live refusal, wrong symbol, wrong owner, duplicate client identity, missing fill, and replay-zero. `test_etf_execution.py` now covers these plus the run callback and pre-outcome callback ordering (`11` tests).
- [x] **Step 2: Run the focused tests RED.** The first run failed at the missing `etf_ownership` module; subsequent RED runs isolated the missing `submit_order` identity parameters and effect callback before implementation. Existing BTC tests remained green.
- [x] **Step 3: Implement paper-only stock submission and durable ownership** using existing effect fences and official readback helpers. The boundary validates fixed ETF symbols, exact `$10.00` market/day paper shape, owner/strategy/client identity, provider fill identity, account position quantity, foreign-state rejection, and replay-zero. Live ETF submission returns `live_etf_rejected` before provider access.
- [x] **Step 4: Run the complete Alpaca investment suite** and a read-only paper preflight; no live order is submitted. `python3 -m unittest discover -p 'test_*.py'` passes `200/200`; official paper read-only account/bar preflight passes with no order submission.
- [x] **Step 5: Commit and push** the paper receipt boundary and update the SSOT with the exact evidence status. Code commit/push: `faab25176a`.

**Task 4 result:** The paper ETF order/ownership/reconciliation boundary is complete and pushed in `faab25176a`. A filled provider order must be followed by account-position readback before `etf-owned-position.json` is written; the effect callback runs before the ledger closes, so a crash can replay the same identity without a duplicate effect. The official paper preflight read only bars/account state and submitted no order. The loaded Life Manager release still lacks this boundary, so no provider paper receipt or P&L exists yet; Task 5 remains open.

### Task 5: Life Manager release handoff and natural receipt

**Files:**

- Read-only: Life Manager registry, loaded immutable release, state receipts, and official Alpaca paper readback
- Modify only: the three investment spec/plan files after the owner release/readback exists

**Acceptance:** a Life Manager-owned immutable release contains the pure policy, selected state, completed-bar ingestion, paper-only order boundary, and the release-time safe owner-manifest provisioner; one natural scheduler wake produces a typed terminal result, official paper order/fill readback, durable receipt, and replay-zero notification. A runtime `resource_capacity_busy` or `resource_fifo_wait` event remains a hold and does not count as a trade.

- [x] **Step 1: Verify the candidate release artifact** contains the committed investment boundary, safe manifest provisioner, deployment hook, and exact registry argv. Isolated release `d14f12306a8fe30558391685226e74436548f673` has `release_paths=ALL` and contains `provision_manifest.py`, `cross_venue_run.py`, `bin/reconcile-agent-runner-release.sh`, and the `investment-cross-venue-report` row. This is candidate evidence (`pushed-not-yet-on-main`), not a production readback.
- [x] **Step 1a: Add the selected-strategy handoff boundary.** `provision_selection.py` reads an explicitly configured validation-report JSON, requires a timezone-aware future `expires_at`, invokes the deterministic selector, and atomically creates a release-pinned `selected-strategy.json` only for a complete selected report; missing/rejected/unbounded reports remain fail-closed and existing valid state is preserved. The reconciler calls it only when `LIFE_MANAGER_INVESTMENT_VALIDATION_REPORTS_PATH` is set. Tests: selection `6/6`, investment-core `120/120`, Alpaca `200/200`, release-reconciler `16/16`.
- [x] **Step 1c: Re-cut the candidate release after the selection boundary.** Immutable candidate `e90d1eaef72838ffaea44a1e15f3132fb9cd6010` has `release_paths=ALL`, `provenance=pushed-not-yet-on-main`, the selection/manifest provisioners, reconciler hook, cross-venue entrypoint, and both investment registry rows. `current` remains unchanged.
- [x] **Step 1d: Re-cut after the expiry gate with bounded paths.** Sparse immutable candidate `4c947f831cde78ae279b7bdc5f34f20a8ec40647` includes both provisioners, cross-venue/Alpaca runtime, reconciler hook, and both investment registry rows. The full-tree attempt stopped at dependency-bundle `ENOSPC`; sparse candidate proof completed with `current` unchanged.
- [x] **Step 1e: Rotate an expired selected state safely.** `provision_selection.py` preserves a future valid state, rejects malformed/missing expiry, and atomically replaces only a structurally valid expired state after a fresh bounded report is selected. Focused selection tests are `8/8`; fresh report generation and installed production handoff remain open.
- [x] **Step 1f: Read back the rotation candidate.** Sparse immutable candidate `06b41add1c530cbf9e679518a4a874351dfd8c2a` was cut at `/Users/anicca/loops/releases/20260929T092626-06b41add` with `current` unchanged. Release-local dry handoff replaced an expired state with the reviewed report and a runtime release SHA, while retaining `report_release_sha`.
- [ ] **Step 1b: Verify the installed production release artifact** contains the same boundary and exact loaded argv/env. Current production `current` lacks the provisioner and `investment-cross-venue-report` is unloaded.
- [ ] **Step 2: Allow the Life Manager owner path to apply/reconcile** only through its normal release workflow; do not edit registry, admission DB, LaunchAgent, or production state from this lane.
- [ ] **Step 3: Observe one natural wake** and collect run ID, occurrence ID, release SHA, effect journal, provider readback, receipt ID, and Telegram message ID.
- [ ] **Step 4: Update the SSOT and primary plan** with pass/fail; only a complete receipt opens the next Alpaca sample step.

## Completion definition

This plan is complete only when Tasks 1–5 have their stated evidence. A passing unit suite, an in-memory selector, a loaded registry row, or a paper backtest does not complete the plan. Live ETF trading, Binance funding, capital expansion, and the $10,000/month claim remain closed until the separate investment SSOT gates pass.

### Latest source synchronization (2026-09-29)

- `origin/main=d3e302adac50568b38b4fc081895aaa446b7ea57` was merged into the investment branch as `561c22d20b`; the merge contained only the concurrent writer change and preserved the investment boundary.
- After the merge, investment-core discovery passed `125/125`, Alpaca discovery passed `211/211`, the selected runtime suites passed `293/293`, `./bin/lm-loop-contract` returned `ok=true` with `registry_jobs=172` and `errors=[]`, and `./bin/lm-loop doctor` returned `ok=true` with no missing or unmanaged entries.
- The byte-stable runtime fixture was regenerated from the canonical registry renderer after the new `investment-strategy-validation` row was found at the wrong list position; the focused production-render regression and the full runtime suite now pass.
- This is source/candidate evidence only. The production `current` release remains the older immutable release, the candidate is not on `origin/main`, and no production selected state, natural paper order/fill receipt, provider P&L, funding, wallet, or live order exists.
- **Current cursor remains Step 1b / INV-001-B:** verify the installed Life Manager release and exact loaded argv/env through the normal owner path, then observe one natural paper wake. Steps 1b–4 remain unchecked until those external readbacks exist.

### Candidate readback after synchronization (2026-09-29)

- Candidate `/Users/anicca/loops/releases/20260929T095928-19ece29f` has SHA `19ece29f3b59e33bd2b067a4edf2867bba74ccb0`, `provenance=pushed-not-yet-on-main`, and sparse paths `bin config apps/life-manager/investment-core skills/alpaca-investment runtime/loop skills/_shared`; `current` remains `/Users/anicca/loops/releases/20260929T094848-d3e302ad` at `d3e302adac50568b38b4fc081895aaa446b7ea57`.
- The candidate contains `validation_runner.py`, `provision_selection.py`, `provision_manifest.py`, `cross_venue_run.py`, ETF policy/ownership, the three investment registry rows, and `reviewed-validation-reports.json`; all three investment helper `--help` boundaries pass and registry readback shows the expected `revenue` Alpaca/report owners plus the paper validation job.
- The sparse candidate intentionally omits unrelated general Life Manager contract helper files, so the full contract gate is authoritative from the source branch (`ok=true`), not from executing a partial candidate. This is candidate proof, not an installed production readback.
- Production selected state, loaded ETF boundary, natural paper order/fill, provider receipt, cost-complete P&L, funding, and live order remain absent. Step 1b is still open.

### Latest production readback after candidate cut (2026-09-29)

- Read-only `lm-loop status alpaca-investment-live` shows installed/event release `d3e302adac50568b38b4fc081895aaa446b7ea57`, `loaded-idle`, and the latest terminal boundary `host_admission_deferred:resource_capacity_busy` (`exit=75`, `retry_after_eligibility`). `effect_status=unknown`, `provider_receipt_id=null`, and `official_readback_ref=null`; therefore no paper or real provider transaction is counted.
- Read-only `lm-loop status investment-cross-venue-report` returns `unknown loop id` against the current release. The production cross-venue state root and validation state root are absent, so no daily report, selected production state, or notification receipt exists.
- Existing Alpaca account state remains `net_pnl_usd=-0.15`, `completed_round_trips=1`, `capital_expansion_allowed=false`; it is account readback, not proof that this candidate ran. `INV-001-B` remains open, and the next valid boundary is Life Manager's normal immutable-release handoff.

### Admission diagnosis and economic boundary (2026-09-29)

- The authoritative v2 admission database shows the currently queued Alpaca occurrence as `admission_class=borrow`, `base_priority=support`, sequence `277843`, while active revenue owners occupy the finite agent capacity. This matches `host_admission_deferred:resource_capacity_busy`; it is not a strategy signal and it did not create a provider effect.
- The pushed investment candidate already declares `alpaca-investment-live` as `admission_class=revenue`, `priority=revenue`, and includes the cross-venue/validation rows. That change can only affect runtime after the candidate is accepted through the immutable `main` release path. No direct admission DB, launchd, or sibling owner mutation is allowed from this worktree.
- Paper/backtest evidence remains a validation input only. Real transaction means an official provider order/fill/account readback with a receipt ID; revenue means settled net cash after fees/slippage/model cost. The current candidate has none.

### Historical real canary clarification (2026-09-29)

- A prior bounded crypto canary is already verified and closed: BTC/USDC buy notional `$2.00`, official entry order `1a1f83e4-aaba-440f-a94e-9db3c3323f4a`, official close order `7712069c-6f24-425a-986e-752dae8c1607`, fee `0.004896691 USDC`, and realized net `-0.006970681885 USDC`. This proves the narrow live crypto execution/readback path, not ETF live eligibility or profitability.
- The current scheduled Alpaca loop has no new provider transaction: its latest occurrence is admission-deferred before child/provider execution. The next evidence remains candidate deployment → one natural ETF paper order/fill → cost-complete P&L; no second live canary is authorized by this readback.
- The loaded production owner is `LIFE_MANAGER_INVESTMENT_MODE=live`; its ETF policy rejects `us_equity` live orders, while `investment-strategy-validation` is read-only and submits no orders. A natural paper ETF receipt therefore requires a separate paper owner/state/effect fence; switching or reusing the live owner is not an acceptable handoff.
- Candidate source now declares `alpaca-investment-paper` with its own state root and `effect_reconcile.py --mode paper`; the validation row provisions independent selected-state files for the live and paper owners. This closes the source-side mode boundary only. The installed release, natural paper order/fill, provider receipt, and cost-complete P&L remain open.

### Candidate-local handoff readback (2026-09-29)

- Candidate `/Users/anicca/loops/releases/20260929T102440-cebd5051` was exercised without changing production. The selection provisioner created separate live and paper selected states for `alpaca-etf-126d-momentum-v1`, both pinned to the candidate SHA and future reviewed-report expiry; the manifest provisioner created a zero-capital manifest with no snapshot specs. This proves the candidate-local state handoff only. The installed/current release still lacks the paper owner and validation/report rows, so the remaining acceptance is production owner-path install → natural paper order/fill/account readback → replay-zero receipt.

- The source-side paper execution boundary now supports the complete entry→exit cycle. A paper ETF sell requires the owned quantity, official filled sell readback, and an empty account position before the state is closed; the close receipt records gross P&L but leaves costs unknown. The full Alpaca suite is `219/219`. This is candidate evidence only; the production handoff and natural paper receipt remain open.

- The post-exit candidate is `/Users/anicca/loops/releases/20260929T103943-06d34a4a` (`06d34a4a2d`, `pushed-not-yet-on-main`). Its live/paper selected states and zero-capital manifest were provisioned in temporary release-local state and pinned to the candidate. The installed/current release remains `5a71af45`; no natural paper order or provider receipt exists.
