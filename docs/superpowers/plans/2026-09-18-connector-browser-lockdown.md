# Connector Browser Lockdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Luma/Connpass Connector continuously safe and attributable from wake admission through official registration, Calendar exact-one, Telegram evidence, and replay-zero while preventing unowned browser contexts from silently accumulating.

**Architecture:** Keep the existing `life-manager-connector-native` owner, 1800-second launchd cadence, `native-pass.js`, production browser rail, provider adapters, Calendar transport, and evidence chain. Connector owns only its target lifecycle; the shared Browser owner owns orphan-context census/recovery and session-vault keepalive coverage. Production is locked only by same-SHA source/release/load evidence plus official provider and Calendar readback.

**Tech Stack:** Bash launchd entrypoints, Node.js Connector runner, Playwright over CloakBrowser CDP `:9222`, Python CDP/session-vault helpers, Google Calendar `gog` transport, append-only state/evidence ledgers.

**Spec:** `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md`

## Global Constraints

- Providers are Luma and Connpass only; do not add X, TechPlay fallback, a second scheduler, or a parallel Connector loop.
- Do not edit `runtime/host/`, `runtime/loop/`, `config/loop-registry.json`, admission SQLite, or another owner’s browser/profile/state from Connector work.
- Never retry an uncertain provider action before official provider readback; `effect_unknown` remains fenced.
- A branch test, exit 0, browser screenshot, or Telegram send alone is not an external-effect proof.
- Every accepted effect requires provider receipt → Google Calendar event ID exact count 1 → independent Calendar readback → durable bundle → Telegram IDs → two natural replay-zero wakes.

---

### Task 1: Connector browser entrypoint (complete)

**Files:**
- Modify: `skills/connector/run.sh`
- Test: `skills/connector/test/native-entrypoint.test.js`

**Interfaces:**
- Consumes: existing `skills/browser/ensure_browser.sh` and `skills/browser/scripts/cdp_tab_gc.py`.
- Produces: `CLOAK_BROWSER_OWNER=life-manager-connector-native`; a pre-provider Browser foundation gate; owner-scoped GC.

- [x] Write and run the failing entrypoint contract test.
- [x] Implement the minimal guard/GC call before `native-pass.js`.
- [x] Verify `bash -n skills/connector/run.sh` and `node --test skills/connector/test/native-entrypoint.test.js` (`18/18` pass).
- [x] Merge PR #5602 as main `5b6e178835`.

### Task 2: Shared orphan-context census (shared Browser owner)

**Files:**
- Modify: `skills/browser/scripts/cdp_context_lease.py`
- Test: `skills/browser/scripts/test_cdp_context_lease_orphan_census.py` (new)
- Read: `skills/browser/scripts/target_ownership.py`, `skills/browser/scripts/cdp_tab_gc.py`

**Interfaces:**
- Consumes: `Target.getBrowserContexts`, `Target.getTargets`, the lease ledger, and target-owner registry.
- Produces: a read-only orphan report containing context ID, page URLs, lease/owner evidence, and disposition; cleanup may close only a context proven stale and owned by the caller’s ledger.

- [x] Write a failing test where `Target.getBrowserContexts` returns one leased context and one unregistered blank context; assert the report marks the latter `unknown_owner` and performs no close.
- [x] Add the read-only `context_inventory()` contract and existing CLI command `python3 skills/browser/scripts/cdp_context_lease.py audit`; do not infer ownership from `about:blank` alone.
- [x] Run `python3 -m pytest -q skills/browser/scripts/test_cdp_context_lease_orphan_census.py skills/browser/scripts/test_cdp_context_lease_gc_lock.py skills/browser/scripts/test_cdp_context_lease_hangs.py skills/browser/scripts/test_cdp_context_lease_pid_reap.py` (`58 passed`) and `python3 -m py_compile skills/browser/scripts/cdp_context_lease.py`.
- [x] Run one live read-only census on `:9222`: 36 contexts, one leased Mercor context, 35 unknown-owner contexts; no context closed. Branch `e0610e2f5d`, PR #5608 is pending main integration.
- [x] Merge PR #5608 as main `a3efd6a28d` and cut complete release `/Users/anicca/loops/releases/20260918T230317-a3efd6a2`; verify `release_paths=ALL`, `context_inventory()` and its test are present.
- [ ] Write the failing proof-gated recovery test for one stale owner-backed row and one unknown context; implement disposal only for the owner-backed row.

### Task 3: Session keepalive coverage (shared Browser owner)

**Files:**
- Modify: `skills/browser/scripts/session_vault_tick.sh`
- Test: `skills/browser/tests/test_session_vault_tick_connector_urls.py` (new or existing session-vault tick test)

**Interfaces:**
- Consumes: existing `session_vault.py keepalive` and the current daily-driver vault.
- Produces: one 30-minute keepalive/readback for the authenticated Connpass and Luma URLs without a second scheduler or automatic credential fabrication.

- [x] Write and run the failing test asserting the tick command contains the approved authenticated Connpass and Luma URLs.
- [x] Add the URLs to the existing `KA_OUT` command only; preserve existing Coconala/Instagram/X behavior and Telegram alerting. PR #5615 merged as main `8eae86892e`.
- [x] Run the focused shell/static test and existing vault tests (`31/31` pass); cut release `/Users/anicca/loops/releases/20260918T231001-8eae8689` with `release_paths=ALL`.
- [ ] Reconcile stale `session-vault:18d606ad782b0140-83191`, load the release, and record `logged_out` explicitly if either provider is unauthenticated; do not report it as registered.

### Task 4: Reconcile the shared effect fence and load the merged release

**Files:**
- Read-only: `~/.local/state/life-manager/host-admission/resources/admission-v2.sqlite3`
- Read-only: launchd status and Connector state

**Interfaces:**
- Consumes: shared admission owner’s official/pre-effect reconciliation of `life-manager-connector-native:18d66aef19152518-55543`.
- Produces: loaded-idle Connector label with one complete main-derived SHA and no unresolved pending occurrence.

- [x] Do not edit the SQLite file or reclaim by age. The earlier Connector effect fence became `released/effect_unknown=0` through the existing path.
- [x] After the shared fence became released/known, load the latest complete release with:

```bash
LIFE_MANAGER_RELEASE_ROOT=/Users/anicca/loops/current \
  bin/lm-loop reconcile deterministic --loaded-idle-only --max-owners 1 \
  --loop-id life-manager-connector-native
bin/lm-loop status life-manager-connector-native
```

- [x] Installed and loaded Connector SHA now agree at `8eae86892e`; a natural wake on the previous SHA reached `completed_no_effect`, while the next manual wake was safely deferred by `resource_control_busy` before provider work and remains queued.

### Task 5: Official authentication and new effect

**Files:**
- Read-only: Connector-owned 9222 profile and official Connpass/Luma pages
- Existing code only: `apps/life-manager/lib/connpass-browser-provider.js`, `apps/life-manager/lib/connector-luma-workflow.js`, `apps/life-manager/lib/transport/calendar-gog.js`

**Interfaces:**
- Consumes: an ordinary authenticated Connpass/Luma session; no X OAuth substitute.
- Produces: one new eligible event with official `registered`/`pending`, Calendar exact-one, independent readback, bundle, and Telegram provider IDs.

- [ ] Read official 404714 first; if it is `login_required`, do not resend.
- [ ] On a new free/open/Calendar-free event, allow at most one existing adapter Submit.
- [ ] Read the official provider state after the action and bind the receipt to the exact event URL/ID.
- [ ] Create/reuse exactly one Calendar event and verify exact count 1 through the independent API path.

### Task 6: Replay-zero and closeout

**Files:**
- Read-only: `wake-reports.jsonl`, `action-history.jsonl`, Calendar API, provider page
- Modify: the Connector section of the canonical spec only after evidence is complete

**Interfaces:**
- Consumes: the new effect bundle and loaded SHA.
- Produces: two subsequent natural wakes with official provider state preserved, Submit 0, Calendar exact count 1, duplicate 0, and final Telegram receipts.

- [ ] Observe replay wake 1 without kickstarting or changing cadence.
- [ ] Observe replay wake 2 on the same loaded SHA.
- [ ] Record run IDs, wake IDs, terminal results, provider receipt, Calendar ID, exact-one query, bundle ID, Telegram IDs, and release SHA.
- [ ] Mark CN-C03–CN-C05 closed only when every receipt is present; otherwise retain truthful no-work or blocker state.
