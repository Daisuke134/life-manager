# Treg Product Growth Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution:** Native, one owner in this session, as already authorized by the user. The runner, monitor, and loop registry share one release boundary; no separate implementation session is used.

**Goal:** Make Treg available to Life Manager product-growth agents and report only new public demand signals for all nine current products on a weekly schedule, with Anicca iOS first.

**Architecture:** Codex receives a per-invocation local stdio Treg MCP budget gate and repository-owned `treg`/`lead-signals` skills. The gate proxies only the four allowed tools to Treg's stateless JSON/HTTP MCP and checks/reserves each paid route before forwarding. A new `lm-loop` owner uses the shared `marketing-agent` route to query X and Reddit, qualifies signals, records a private CSV baseline plus a hash marker, and sends a Telegram report only for newly seen keys. The existing `marketing-weekly-review` owner remains untouched because its latest Telegram occurrence is unresolved.

**Tech Stack:** Python stdlib, Codex remote MCP, Treg MCP/CLI, existing Life Manager agent-runner, `lm-loop`, shared Telegram transport, JSON/CSV state.

**Spec:** `docs/superpowers/specs/2026-10-10-treg-product-growth-design.md`

## Global Constraints

- Read only `service=treg_agent:life-manager-product-growth` from `~/.local/share/anicca/credentials.json`; never persist the token in Git, argv, config files, logs, or chat.
- Every Codex agent task uses the local stdio MCP gate when the dedicated Treg identity is present. The gate reads that token from credential SSOT itself; neither Codex nor its shell receives the token. Only `catalog_search`, `catalog_get`, `call`, and `balance` are exposed.
- Treg tools use the existing unattended agent policy. Their shared private gate enforces 18 billed routes / `$0.054` per UTC day and blocks calls below the `$0.05` team balance floor.
- Do not enable general shell network access for Codex.
- Monitor nine products, Anicca first; query public X and Reddit posts from the last seven days only.
- Limit each weekly monitor to 18 billed routes, at `$0.003` maximum per route and `$0.054` total; the local gate checks the latest balance before each call and leaves `$0.05`. Do not enable auto-top-up.
- The dedicated Treg agent identity has a daily proxy-call cap of 18. Treg documents this gate as fail-open if its quota database check errors, so the local gate persists each maximum-cost reservation before forwarding and the server cap remains defense in depth.
- No email/phone enrichment, outreach, posting, or marketing-weekly-review state changes.
- Keep `signals.csv`, Treg receipts, and Telegram receipts outside Git under private state paths with directory mode `0700` and file mode `0600`.
- First monitor run establishes a baseline without sending historical signals. Later runs report only keys absent from the baseline.
- An uncertain provider effect remains fenced; never replay it without exact receipt/readback.
- Preserve existing Codex model/provider routing and unrelated user edits. Release apply requires the existing 2 GiB headroom floor and a main-derived immutable release.

## File Map

| File | Responsibility |
|---|---|
| `runtime/agent-runner/agent_runner.py` | Detect the limited Treg identity without putting its value in child environments, expose isolated skills, and configure the local MCP gate for Codex tasks. |
| `runtime/agent-runner/treg_credentials.py` | Read only the scoped Treg credential from private SSOT for the runner's eligibility check and local gate. |
| `runtime/agent-runner/treg_budget_mcp.py` | Run the local stdio MCP proxy, preserve the four upstream tool schemas/results, and hard-gate/reserve each billed call before forwarding. |
| `runtime/agent-runner/config.json` | Add the dedicated Codex-only `treg-lead-signals-agent` class on the existing `gpt-6.1-sol` medium automation route. |
| `skills/earn/marketing-engine/run_agent.sh` | Allow the new bounded Treg signal task class. |
| `skills/earn/marketing-engine/intel/treg/SKILL.md` | Safe Treg catalog and call rules for Life Manager agents. |
| `skills/earn/marketing-engine/intel/lead-signals/SKILL.md` | Product-fit qualification, baseline, and new-only signal rules. |
| `skills/earn/marketing-engine/intel/lead-signals-products-extra.json` | Four published App Store product profiles absent from the five-row Marketing Engine registry. |
| `skills/earn/marketing-engine/intel/lead-signals-output.schema.json` | Template for qualified rows and Treg call receipts; the runner injects current product IDs. |
| `skills/earn/marketing-engine/intel/treg_lead_signals_weekly.py` | Run the bounded agent pass, validate receipts, dedupe keys, write private state, and send only new rows. |
| `runtime/agent-runner/tests/test_treg_budget_mcp.py` and `skills/earn/marketing-engine/intel/test_treg_lead_signals_weekly.py` | Prove pre-call route/balance gates and CSV baseline marker behavior without live Treg calls. |
| `skills/earn/marketing-engine/intel/treg-lead-signals-weekly` | Repository-relative loop entrypoint. |
| `skills/earn/marketing-engine/intel/treg_lead_signals_reconcile.py` | Read one occurrence's persisted Telegram receipt; never sends or retries. |
| `runtime/loop/lm_loop_run.py` | Allow this exact owner/entrypoint to record a Telegram receipt or a verified no-message result. |
| `config/loop-registry.json` | Register `marketing-treg-lead-signals-weekly` at Sunday 21:10 JST. |
| `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` | Record task state and current cursor; remains the only TODO/state SSOT. |

## Review Focus

1. Missing, duplicate, or malformed Treg credential: skip Treg and never log a token.
2. Treg route above `$0.003`, aggregate above `$0.054`, or low balance: stop before another paid route.
3. Unknown product ID, non-HTTPS profile/source URL, or a source URL not present in the captured Treg response: reject the row.
4. Empty, malformed, or duplicate `signals.csv`: fail closed or establish a baseline; never mark unreported new rows as delivered.
5. Telegram send timeout or missing receipt: retain the occurrence fence and never resend automatically.

## Tasks

### Task 1: Expose Treg to isolated Life Manager agents

**Files:**

- Modify: `runtime/agent-runner/agent_runner.py`
- Modify: `runtime/agent-runner/config.json`
- Modify: `skills/earn/marketing-engine/run_agent.sh`
- Create: `skills/earn/marketing-engine/intel/treg/SKILL.md`
- Create: `skills/earn/marketing-engine/intel/lead-signals/SKILL.md`

**Interfaces:**

- Add `_load_treg_agent_token(credentials_path: Path | None = None) -> str | None`; accept exactly one `treg_agent:life-manager-product-growth` row and return its token only in memory.
- Extend `provider_process_env(...)` to remove any inherited `TREG_TOKEN`, check the dedicated credential for Codex eligibility, and link the two repo-owned skill directories into the invocation's isolated `$HOME/.agents/skills` without exporting the token.
- For every eligible Codex task, use per-invocation `-c` overrides for the local stdio MCP command/args and four allowed tools. The gate reads the private credential SSOT and sends `Authorization: Bearer` upstream. Keep `--ignore-user-config`; no token value or token environment variable enters Codex config or child environments.
- Add `treg-lead-signals-agent` to `TOOLLESS_TASK_CLASSES` and `run_agent.sh`; configure it as Codex-only with model `gpt-6.1-sol`, effort `medium`, and profile `acct2`, with no provider fallback. It uses the same local gated MCP as other Codex tasks while its shell remains disabled/read-only.
- Preserve all model/provider selection and sandbox settings; no general network access is added.

- [x] Create the two skills with triggers, public-signal-only scope, per-call/weekly cost limits, no outreach, and no top-ups.
- [x] Implement exact-SSOT token loading for the local gate process, restrictive directory/file modes, safe skill symlinks, and MCP config overrides without writing token values to Codex or shell environments.
- [x] Add `treg-lead-signals-agent` using the existing account-2 profile and current `gpt-6.1-sol` medium model; include it in the `run_agent.sh` allowlist and Codex read-only/tool-less task set.
- [x] Run `python3 -m py_compile runtime/agent-runner/agent_runner.py`.
- [x] Run `python3 -m json.tool runtime/agent-runner/config.json` and `bash -n skills/earn/marketing-engine/run_agent.sh`.
- [x] Run `codex mcp list --json` with an isolated `CODEX_HOME` and the per-run overrides; verify the `treg` server lists without making a provider call.
- [x] Run a no-cost isolated `treg balance` smoke using the generated child environment; print only success, not the token or raw config.
- [x] Commit and push this task before moving to the loop implementation.

### Task 2: Define the nine product profiles and agent output contract

**Files:**

- Create: `skills/earn/marketing-engine/intel/lead-signals-products-extra.json`
- Create: `skills/earn/marketing-engine/intel/lead-signals-output.schema.json`
- Reuse: `skills/earn/marketing-engine/registry/products/*.json`

**Interfaces:**

- `load_product_profiles(registry_dir: Path, extras_file: Path) -> list[dict]` returns the five canonical product rows plus four App Store supplements, ordered with `anicca-ios` first.
- Agent output contains `signals[]` with `product_id`, `platform`, `person_url`, `signal`, `source_url`, `observed_at`, and `why_now`; it also contains one `treg_calls[]` receipt per billed route with `call_id` and `charged_micro`.

- [x] Record the four Apple listing IDs, exact listing URLs, and concise buyer descriptions grounded in the current Apple lookup metadata.
- [x] Write the JSON Schema to reject unknown products/platforms, absent source/person URLs, missing reasons, and missing Treg call receipts.
- [x] Run `python3 -m json.tool` on both JSON files.
- [x] Commit and push this task.

### Task 3: Implement the private weekly signal owner

**Files:**

- Modify: `runtime/loop/lm_loop_run.py`
- Modify: `skills/earn/marketing-engine/intel/treg/SKILL.md`
- Modify: `skills/earn/marketing-engine/intel/lead-signals/SKILL.md`
- Modify: `skills/earn/marketing-engine/intel/lead-signals-output.schema.json`
- Create: `skills/earn/marketing-engine/intel/treg_lead_signals_weekly.py`
- Create: `skills/earn/marketing-engine/intel/treg-lead-signals-weekly`
- Create: `skills/earn/marketing-engine/intel/treg_lead_signals_reconcile.py`
- Modify: `config/loop-registry.json`

**Interfaces:**

- `run_weekly_monitor(*, state_root: Path, evidence_root: Path, agent_runner=...) -> dict` runs one `treg-lead-signals-agent` pass and returns the Life Manager terminal result fields, `treg_call_ids`, `charged_micro`, `baseline_count`, `new_count`, and optional Telegram `provider_receipt_id`.
- The scheduled signal pass invokes `run_agent.sh --task-class treg-lead-signals-agent`; no general shell/network capability is needed for its Treg MCP calls.
- The local stdio gate is the only process that connects to Treg; the Codex shell stays disabled and has no general network access.
- The local gate's private ledger is authoritative for route reservations; end-of-run validation matches its occurrence rows to Codex JSONL arguments and Treg call IDs/costs.
- Every billed MCP `call` includes `headers: {"X-Treg-Route-Max-Cost": "0.003"}`. Treg forwards this tool argument to its upstream route; the parent validates the captured arguments. The product ID enum and one-signal-per-product maximum are generated from the currently loaded profiles.
- Validate call IDs, prices, costs, and exact source/profile URLs against the captured `mcp_tool_call` results in the agent's JSONL evidence; model-provided receipts alone are insufficient.
- CSV key: `(product_id, person_url, signal, source_url)`.
- Pass previously seen keys whose post dates remain inside the current seven-day window so the agent can choose the strongest unseen candidate; the host remains the final deduplication authority.
- `reconcile_occurrence(state_root: Path, occurrence_id: str) -> dict` returns the exact stored receipt for that occurrence or a typed `unknown`; it never sends.
- The repository loop runner accepts only the dedicated owner ID plus entrypoint for `verified_effect` hints. A no-lead/baseline result uses a separately allowlisted `verified_no_effect` reason.
- Registry owner: `marketing-treg-lead-signals-weekly`, Sunday 21:10 local calendar time, `effect_class=message`, `provider_route=shared-agent-runner`, separate state/log roots.

- [x] Build the prompt from the five canonical products and four supplements; search the current catalog once per platform, inspect route prices, and make at most two routes per product.
- [x] If the loaded product set would require more than 18 routes for one X and one Reddit scan per product, fail before paid calls instead of silently omitting products.
- [x] Include `X-Treg-Route-Max-Cost: 0.003` in the `headers` argument of every billed `call`, and reject any captured call that omits it.
- [ ] Enforce balance and route limits in the local MCP process before each paid route. Under a private `fcntl` lock, require a current catalog quote at or below `$0.003`, the exact max-cost header, fewer than 18 prior reservations, cumulative reserved cost below `$0.054`, and fresh balance less current route cost plus unresolved reservations at least `$0.05`; persist the reservation before forwarding and never release an uncertain reservation.
- [x] Require X/Reddit public results from the last seven days, fit/timing qualification, exact source URLs, and the per-call cost header.
- [x] Generate the agent schema from the current product IDs. Validate the JSON and each receipt against captured Treg MCP results; reject if any route exceeds `$0.003`, total exceeds `$0.054`, or there are more than two billed routes per product.
- [x] Keep at most one strongest new signal per product in the weekly report so one digest covers every product without flooding Telegram.
- [ ] On the first run, write a private baseline and a SHA-256 marker and send no old leads. On later runs, require marker/CSV hash match, pass recent exact keys to the agent, then compare exact CSV keys and report only new rows; an unmarked header-only CSV must fail before paid calls.
- [x] Write state atomically with `0700` directory and `0600` files. Persist `signals.csv` only after the outbox/Telegram decision is durably recorded.
- [x] Use `skills/_shared/telegram.py`; persist the returned message IDs and receipt before reporting success. If no new rows, do not send and write a `verified_no_effect` hint.
- [x] Add an owner/entrypoint-scoped receipt-hint allowlist; for a delivered message write a `verified_effect` hint with its Telegram message ID.
- [x] Add a read-only occurrence reconciler that checks the exact terminal event, private outbox, and Telegram user-history message ID/body prefix/sender/time, then resolves only the matching occurrence; it never retries a send.
- [x] Run `python3 -m py_compile` on the three Python entrypoints and `./bin/lm-loop-contract`.
- [x] Commit and push the loop as its own source change (`f3a39585fc`).

### Task 4: Close read-only review findings

**Files:**

- Modify: `runtime/agent-runner/agent_runner.py`
- Modify: `docs/manifests/oss-merge-1-sources.json`
- Create: `runtime/agent-runner/treg_credentials.py`
- Create: `runtime/agent-runner/treg_budget_mcp.py`
- Modify: `skills/earn/marketing-engine/intel/treg_lead_signals_weekly.py`
- Create: `runtime/agent-runner/tests/test_treg_budget_mcp.py`
- Create: `skills/earn/marketing-engine/intel/test_treg_lead_signals_weekly.py`
- Modify: this plan and `docs/superpowers/specs/2026-10-10-treg-product-growth-design.md`

**Acceptance:**

- Each paid `call` is rejected locally before upstream forwarding unless the endpoint has a current safe quote, the exact route cap header is present, the shared UTC-day and occurrence ledgers have fewer than 18 reserved routes / `$0.054`, and a fresh balance read leaves `$0.05` after this route and unresolved reservations.
- The shared daily ledger lives at private `~/.local/state/life-manager/treg-budget/`; each task's occurrence ledger lives beside its private evidence and matches every captured Treg receipt.
- Unresolved maximum-cost reservations survive UTC daily-ledger rotation in a private pending ledger and are deducted from later balance preflights until an exact receipt settles them.
- The gate durably records the maximum `$0.003` reservation before forwarding; a missing/invalid receipt never frees the route or its uncertain cost, and prevents another paid call in that occurrence.
- General Codex tasks can call Treg only through this same gate; no Codex/provider shell process receives the dedicated token. The shared daily ledger therefore covers all Codex task classes.
- Parent validation matches every captured paid MCP call to the local gate's occurrence ledger and exact Treg receipt.
- Existing `signals.csv` without a valid hash marker fails closed. An established empty baseline remains distinguishable from a pre-created header-only CSV.
- Tests use local fixtures only; they make no paid Treg call and send no Telegram message.

- [x] Write the baseline, route-budget, runner-config/credential-isolation, and parent-receipt regressions first; confirm each fails for its missing behavior.
- [x] Implement the local MCP budget gate and hash-bound baseline marker with no new dependency.
- [x] Run focused tests, source boundary, loop contract, syntax/JSON checks, and diff check after token-isolation changes.
- [ ] Update the SSOT cursor with final evidence and push the dedicated branch.

### Task 5: Source acceptance and production handoff

**Files:**

- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

- [ ] Run `bash scripts/verify-source-boundary.sh`, `./bin/lm-loop-contract`, and `git diff --check`.
- [ ] Confirm no secrets, signal rows, or provider outputs are staged.
- [ ] Fetch current `origin/main`, preserve unrelated work, push the dedicated branch, and open a PR.
- [ ] Run exact-head CI and read-only review, merge through the standard repository flow, then build a main-derived immutable release.
- [ ] Require `df -k /` free bytes `>= 2 GiB` before release apply. Apply only the new owner through the owner-safe path; do not touch the existing `marketing-weekly-review` unknown occurrence.
- [ ] Confirm the loaded release SHA and Sunday 21:10 schedule. Do not claim production monitoring complete until the natural run records Treg receipts/cost and its baseline; the next natural run must report only unseen keys or no message.
