# Prepared Catalog Shadow Host Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Preserve the user's already chosen execution method and autonomous design approval; do not add another permission pause.

**Goal:** Connect the accepted prepared shadow helper to the existing main host, CLI and explicitly opted-in dispatch, with default and scheduled inference OFF.

**Architecture:** Compare the exact host-selected tuple inside the existing lifecycle gate and store results privately on that host. The CLI projects the existing P0 allowlist into one nested field; the deterministic publisher and owner lifecycle remain independent. Reuse the same checkpoint and provider implementation.

**Tech Stack:** Existing Python 3.11 unittest/Decimal/dataclasses, SQLite checkpoint, GitHub Actions YAML, optional pinned `openai==3.24.0`.

**Spec:** [research specification](https://github.com/Daisuke134/life-manager/blob/63893622d3b2a872fc3ebcd8ceedfeafc7c433ce/products/manager/docs/MANAGER_PRODUCT_SPEC.md) §1.3.2 row 3; `products/manager/docs/plans/2026-10-23-host-shadow-connection-design.md` (committed beside this plan).

## Global Constraints

- Accepted helper source baseline: `07a8957c7f115b99204aeccbb1a06a1f693daae8`; its research synchronization and exact-source CI completed at dc56ba984ee97cb307051c8cac4739f8e914c46a before implementation; do not overwrite concurrent edits.
- Same exact prepared context/assessment/scope tuple; planner calls one; no new owner, memory engine, framework, journal or provider ledger.
- OFF by default; schedule/control/preflight comparisons and client/provider initialization zero.
- Money blank is `None`; finite Decimal in `(0,100]`, exact microdollars, per-call <= cumulative cap; no numeric fallback or cap rotation.
- Constants: comparison budget `120` seconds from `run_once` entry, publisher reserve `120`, client request timeout `30`; existing host lifetime `600`, workflow job `13` minutes unchanged.
- Public nested P0 only: `authorized_execution=False`, `causal_support=False`, `human_outcome='NOT_MEASURED'`, `action_writes=0`, `settled_cost_usd=None`.
- Ordinary advice uncertainty leaves independent publisher admission intact; `CheckpointUnavailable` follows existing fence. SDK client close is attempted exactly once on all comparison exits.
- SDK installation before lease; no new live inference, production activation, benefit claim, or network-backed tests in this source task.

## Review Focus

1. Missing/malformed send settings with saved ACK/intent must still replay ACK or retain UNKNOWN, initialize zero providers, and never invent a budget (Task 2).
2. Comparison delay or repeated preparation must consume the original host/scope/time windows, without renewed scope, replanning, or publisher admission after expiry (Task 1).
3. Ordinary provider UNKNOWN, client cleanup failure, and checkpoint ACK loss must preserve their distinct publisher/fence behavior and leak no raw data (Tasks 1 and 2).
4. Prebound versus planner-returned tuple, no candidate, unsupported current-page cue and recovery/gate exits must use the exact intended seam with no hidden factory invocation (Task 1).
5. A dispatch true value combined with schedule/control must remain OFF, skip SDK installation and secret exposure, and retain the single writer and artifact allowlist (Task 3).

---

### Task 1: Host seam, immutable deadline and client ownership

**Files:**
- Modify `products/manager/manager_core/owned_platform_host.py`: imports/constants, constructor near line 48, `prepare_candidate` near line 78; add private comparison method beside it.
- Test `products/manager/tests/test_owned_platform_host.py`.
- Test `products/manager/tests/test_owned_checkpoint_order.py`.
- Read only `products/manager/manager_core/owned_cycle.py:408` and accepted `owned_provider_shadow.py`; no lifecycle or helper edits planned.

**Interfaces:**
- Consumes existing `compare_prepared_catalog_shadow(checkpoint: PrivateCheckpoint, prepared: tuple[OwnedChangeContext, TechnicalAssessment, OwnedDigitalScope] | None, *, now: datetime, run_id: str, enabled: bool = False, client_factory: Callable[[], Any] | None = None, cap_usd: Decimal | None = None, upper_usd: Decimal | None = None, deadline_monotonic: float) -> dict`.
- Produces frozen `CatalogShadowSettings(deadline_monotonic: float, client_factory: Callable[[], Any] | None = None, cap_usd: Decimal | None = None, upper_usd: Decimal | None = None)`; exclude factory from repr.
- Produces constructor keyword `catalog_shadow: CatalogShadowSettings | None = None`, `_catalog_shadow_result: dict | None`, `_compare_prepared_catalog_shadow(self, prepared: tuple | None) -> None` and three constants named in design. No generic callback interface.

- [ ] **Step 1: Add focused failing tests to the existing exact-host fixtures.** Add `test_prepared_shadow_uses_exact_selected_and_prebound_tuple_once` (identity via `assertIs`, selector one for selected path/zero for prebound; comparator before release reservation; returned objects and bytes unchanged for PASS/ASK/PROPOSE); `test_shadow_off_and_ineligible_paths_initialize_nothing` (OFF comparator zero/result None; enabled no-candidate gets None, unsupported cue factory zero). Extend `platform_fixture(..., catalog_shadow=None)` only as a test helper, passing the new constructor keyword without weakening production exact types.
- [ ] **Step 2: Add time, cleanup and fence failing tests.** `test_shadow_deadline_only_shortens_and_publisher_uses_fresh_time`: started=1000/deadline=1120; comparison at monotonic 1100 with scope 100 seconds left gives deadline 1080 (`1100+100-120`), no factory; at scope 300 seconds left deadline stays1120. Subsequent preparation cannot increase the bound. Delay comparator past scope/host deadline and assert no `send_owned`, scope unchanged, selector one. `test_shadow_closes_client_on_compared_unknown_budget_and_checkpoint_failure`: factory1/close1 for each constructed-client path, checkpoint exception identity retained, cleanup exception text absent; no factory on saved result. `test_advice_unknown_does_not_block_independent_publisher`: existing passing publisher fixture still reaches its admission for advice UNKNOWN; a CheckpointUnavailable comparator does not reserve/send and propagates.
- [ ] **Step 3: Add recovery-gate failing test.** `test_shadow_initialization_follows_all_existing_cycle_gates` in `test_owned_checkpoint_order`: use real `PrivateCheckpoint`, `CycleStore` and exact host, count comparator/factory/provider; owner busy, unresolved rollback/occurrence/current delivery/delivery, STOP, NOT_DUE, release-disabled all zero. Extend existing recovery-before-candidate fixture logic; do not use a platform subclass or mock `run_owned_cycle`.
- [ ] **Step 4: Run the new tests and verify RED.** From `products/manager`: `env PYTHONPATH=.:tests python -m unittest test_owned_platform_host test_owned_checkpoint_order -v`. Expected new constructor/settings symbol failures or missing invocation assertions; existing failures from fixture/environment issues are not evidence of the intended RED boundary. Record the actual failure.
- [ ] **Step 5: Implement only the Task 1 interfaces and seam.** Converge valid selection paths through one local tuple and the private comparison method; preserve `None` candidate return contract. Validate finite internal deadline; compute design min using fresh host time and keep only a decreasing stored bound. Invoke helper lazily with original checkpoint and tuple; track only clients returned by the wrapped factory and close in finally. Retain output only on normal return; do not catch checkpoint failure. Do not call `run_catalog_shadow` or modify cycle authority.
- [ ] **Step 6: Run focused tests GREEN.** Repeat Step 4. Also run `env PYTHONPATH=.:tests python -m unittest test_owned_provider_shadow test_owned_digital_cycle test_owned_platform_rollback -v` to verify existing prepared/replay and lifecycle contracts. Expected all pass, no live calls. Inspect changed paths and record evidence before the independent review gate.
- [ ] **Step 7: Commit reviewed Task 1 paths only.** Suggested message: `feat(manager): compare prepared shadow inside existing host gates`. Source/docs synchronization commits remain separate.

### Task 2: Inert CLI configuration and one public projection

**Files:**
- Modify `products/manager/scripts/run_owned_digital_cycle.py`: imports, new settings parser, `public_summary` near line277, `run_once` near line367 normal/cycle-UNKNOWN returns.
- Test `products/manager/tests/test_owned_cycle_cli.py` (including composed real checkpoint/host fixtures).
- Read only existing `_money`, `valid_api_key`, `make_client`, `public_catalog_shadow_summary`.

**Interfaces:**
- Consumes Task 1 `CatalogShadowSettings`, three constants, constructor keyword and private result field.
- Produces `_catalog_shadow_settings(env: Mapping[str, str], *, started_monotonic: float) -> CatalogShadowSettings | None`.
- Extends `public_summary(report, *, source_sha=None, receipt_sha=None, store=None, catalog_shadow: dict | None = None) -> dict`; raw input only, nested fixed projection once. `run_once(state_store, pages_checkout)` and control/preflight signatures unchanged.
- Env contract: `MANAGER_CATALOG_SHADOW_ENABLED`, `AMPERSAND_API_KEY`, `MANAGER_AMPERSAND_MAX_TOTAL_USD`, `MANAGER_AMPERSAND_MAX_CALL_USD`; exact event/flag gating described in design.

- [ ] **Step 1: Add table-driven config RED tests.** `test_shadow_settings_are_inert_and_preserve_unconfigured_money`: true+dispatch+valid fake `hak_abcdefgh`+`'0.050000'`/`'0.030000'` yields Decimals .05/.03, deadline=start+120, zero constructor calls until invoking factory; factory then calls `make_client(..., timeout=30)`. Missing/blank/whitespace, nonnumeric, NaN/Infinity, zero/negative, >100, .0000001, call>total, malformed key give enabled settings with factory/cap/upper all None. `test_shadow_disabled_schedule_control_and_preflight_are_inert`: omitted/false/'TRUE'/unknown flag or schedule yields None; preflight/stop/rollback/resume never parse/call comparator/factory even with malformed money and true flag. Do not inspect or print real secrets.
- [ ] **Step 2: Add replay and report RED tests.** `test_saved_shadow_replays_without_send_configuration` must use the accepted real helper with a saved ACK fixture and invalid/missing CLI settings: original run/time, create0; prior intent remains UNKNOWN/create0; no receipt gives SKIPPED/PROVIDER_NOT_CONFIGURED. `test_public_shadow_projection_is_nested_exact_and_single_pass`: include sentinel provider ID/raw response/key/path/advice reason in raw private record, assert nested exact19 keys and no sentinel in serialized summary; original run ID preserved; all existing outer status/writes/auth/E16/canary fields unchanged. `test_shadow_result_survives_cycle_unknown_but_not_checkpoint_failure`: cycle UNKNOWN after normal helper return and successful save/release includes projection and exit2; failed save, failed release, helper CheckpointUnavailable and selector exception yield catalog_shadow None, no claimed comparison, and preserve existing fence/release behavior. Always-present null is also asserted for default/control output.
- [ ] **Step 3: Run and inspect RED.** `env PYTHONPATH=.:tests python -m unittest test_owned_cycle_cli -v`; expected absent parser/new public parameter or missing nested-key assertions. Ensure tests exercise normal and cycle-UNKNOWN `run_once` branches, not only a mocked projection.
- [ ] **Step 4: Implement configuration and propagation.** Capture monotonic start at `run_once` entry. Parse only inert settings before acquire. Build the lazy client closure only when every send setting validates; no key logging/normalization, no SDK import in parser, no invented amounts. Pass settings to host and raw private result only to successful lifecycle summary calls. Add `catalog_shadow=None` to all `public_summary` results and call accepted projection only for non-None raw data. Do not alter `_successful_cycle_exit`, proof selection, `run_control`, or provider helper schema. Existing CLI fake host fixtures may gain `_catalog_shadow_result=None` so they model the new concrete interface.
- [ ] **Step 5: Verify GREEN and cross-boundary regression.** `env PYTHONPATH=.:tests python -m unittest test_owned_cycle_cli test_owned_platform_host test_owned_checkpoint_order test_owned_provider_shadow -v`. Expected all pass; static-invalid factory/provider0 is distinguished from persisted-budget refusal client1/session0/close1. The latter can reuse Task1 fixture rather than duplicate the provider ledger matrix.
- [ ] **Step 6: Commit reviewed Task 2 paths only.** Suggested message: `feat(manager): expose opt-in shadow as nested advisory summary`.

### Task 3: Dispatch-only SDK wiring and operational documentation

**Files:**
- Modify repository-root `.github/workflows/manager-phase06-service.yml`: dispatch inputs, conditional SDK step before fresh-state/cycle step, cycle-step env.
- Modify `products/manager/tests/test_owned_workflow_contract.py`.
- Modify `products/manager/deploy/owned-digital/README.md` optional provider and catalog-shadow sections.
- Publish these reviewed design/plan drafts to `products/manager/docs/plans/2026-10-23-host-shadow-connection-design.md` and `products/manager/docs/plans/2026-10-23-host-shadow-connection.md` when root accepts them.

**Interfaces:**
- Consumes Task2 env contract and nested output; existing single CLI invocation and artifact paths unchanged.
- Produces dispatch inputs `catalog_shadow` boolean/default false, `ampersand_max_total_usd` and `ampersand_max_call_usd` optional strings/default `''`.
- Exact effective condition: `github.event_name == 'workflow_dispatch' && github.event.inputs.operation == 'run-once' && github.event.inputs.catalog_shadow == 'true'`.
- Installer executes `python -m pip install -r requirements-ampersand.txt` in `source/products/manager`, before lease-owning CLI. Enabled env maps condition to `'true' || 'false'`; secret maps same condition to `secrets.AMPERSAND_API_KEY || ''`; raw money strings use dispatch inputs, never numeric fallback.

- [ ] **Step 1: Add workflow contract RED tests.** `test_shadow_dispatch_gate_is_exact_and_sdk_install_precedes_lease`: assert default false, exact condition on installer and enabled/secret env, raw optional string budgets, no numeric defaults, installer before existing restore/cycle, pinned requirements file still3.24.0 and no API key env on installer. `test_shadow_schedule_and_controls_remain_off_with_one_writer`: table dispatch-run-once-true enables; schedule with true, omitted flag, false, and dispatch stop/rollback/resume with true stay disabled/no optional install/no secret. Retain actual shell harness assertions for exactly one CLI call per operation and nonzero propagation through pipefail. The harness does not execute GitHub expression language: assert the exact shared expression statically and use concrete evaluated env cases for shell tests; do not claim a live Actions evaluation.
- [ ] **Step 2: Run and inspect RED.** `env PYTHONPATH=.:tests python -m unittest test_owned_workflow_contract -v`; expected absent inputs/installer/gating assertions. Preserve prior operation allowlist and artifact tests.
- [ ] **Step 3: Implement narrow YAML/doc edits.** Use the exact condition consistently; optional secret only in cycle step when enabled. Keep verify/publish dependencies, main workflow identity, writer concurrency, operation allowlist, 13-minute job timeout and three artifact paths. Document the prepared path and replay, cumulative budgets, actual client-before-ledger ordering, cleanup/time limits, P0 and source/live distinction. Remove stale absolute claims that CI never installs SDK or the new connection is unimplemented; do not mark row4 live utility complete.
- [ ] **Step 4: Verify final relevant source contracts.** From `products/manager`, run `env PYTHONPATH=.:tests python -m unittest test_owned_cycle_cli test_owned_workflow_contract test_owned_catalog_planner test_candidate_verification test_owned_digital_cycle test_owned_checkpoint_order test_owned_platform_host test_owned_platform_rollback test_owned_provider test_owned_checkpoint test_provider_session_recovery test_provider_budget test_provider_deadlines test_provider_final_readback test_owned_provider_shadow -v`, then `python scripts/check_boundaries.py`. Expected all pass with no network/model calls. Run any additional repository-mandated checks at implementation time; do not reinstall optional SDK or run live dispatch for source acceptance.
- [ ] **Step 5: Review and commit exact Task 3 paths.** Check `git diff --check`, verify artifact allowlist/source permissions unchanged, confirm review-focus evidence is recorded, then suggested message `feat(manager): wire dispatch-only prepared shadow option`. Root owns integration/publishing decisions under the existing authorization.

## Self-review and evidence limits

Spec row3 maps to host gate/tuple/provider initialization (Task1), optional settings and result privacy (Task2), pre-lease SDK/default/schedule/control behavior (Task3). Every Review Focus has an explicit RED test owner. `owned_cycle.py`, accepted provider/checkpoint schema and authority remain unchanged. No proof of live SDK networking, GitHub authentication, production model usefulness or human benefit follows from these tests. Root ruled out job-window stamping: retain existing cancellation/fence behavior without claiming a known remaining job or checkpoint lease duration.
