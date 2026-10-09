# Treg Product Growth Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution:** Native, one owner in this session, as already authorized by the user. The runner, monitor, and loop registry share one release boundary; no separate implementation session is used.

**Goal:** Make Treg available to Life Manager product-growth agents and report only new public demand signals for all nine current products on a weekly schedule, with Anicca iOS first.

**Architecture:** Codex receives a per-invocation remote Treg MCP configuration and repository-owned `treg`/`lead-signals` skills. A new `lm-loop` owner uses the shared `marketing-agent` route to query X and Reddit, qualifies signals, records a private CSV baseline, and sends a Telegram report only for newly seen keys. The existing `marketing-weekly-review` owner remains untouched because its latest Telegram occurrence is unresolved.

**Tech Stack:** Python stdlib, Codex remote MCP, Treg MCP/CLI, existing Life Manager agent-runner, `lm-loop`, shared Telegram transport, JSON/CSV state.

**Spec:** `docs/superpowers/specs/2026-10-10-treg-product-growth-design.md`

## Global Constraints

- Read only `service=treg_agent:life-manager-product-growth` from `~/.local/share/anicca/credentials.json`; never persist the token in Git, argv, config files, logs, or chat.
- Codex MCP uses `https://treg.to/mcp/`, `env_http_headers = { "X-Treg-Token" = "TREG_TOKEN" }`, and only `catalog_search`, `catalog_get`, `call`, and `balance` tools.
- Only `treg-lead-signals-agent` receives unattended approval for those MCP tools; all other agent approval/sandbox policies stay as configured.
- Do not enable general shell network access for Codex.
- Monitor nine products, Anicca first; query public X and Reddit posts from the last seven days only.
- Limit each weekly monitor to 18 billed routes, at `$0.003` maximum per route and `$0.054` total; stop when balance is below `$0.05`. Do not enable auto-top-up.
- No email/phone enrichment, outreach, posting, or marketing-weekly-review state changes.
- Keep `signals.csv`, Treg receipts, and Telegram receipts outside Git under private state paths with directory mode `0700` and file mode `0600`.
- First monitor run establishes a baseline without sending historical signals. Later runs report only keys absent from the baseline.
- An uncertain provider effect remains fenced; never replay it without exact receipt/readback.
- Preserve existing Codex model/provider routing and unrelated user edits. Release apply requires the existing 2 GiB headroom floor and a main-derived immutable release.

## File Map

| File | Responsibility |
|---|---|
| `runtime/agent-runner/agent_runner.py` | Load the limited Treg token into child environments, expose isolated skills, and add Treg MCP to the dedicated signal task. |
| `runtime/agent-runner/config.json` | Add the dedicated Codex-only `treg-lead-signals-agent` class on the existing `gpt-6.1-sol` medium automation route. |
| `skills/earn/marketing-engine/run_agent.sh` | Allow the new bounded Treg signal task class. |
| `skills/earn/marketing-engine/intel/treg/SKILL.md` | Safe Treg catalog and call rules for Life Manager agents. |
| `skills/earn/marketing-engine/intel/lead-signals/SKILL.md` | Product-fit qualification, baseline, and new-only signal rules. |
| `skills/earn/marketing-engine/intel/lead-signals-products-extra.json` | Four published App Store product profiles absent from the five-row Marketing Engine registry. |
| `skills/earn/marketing-engine/intel/lead-signals-output.schema.json` | Contract for qualified rows and Treg call receipts returned by the agent. |
| `skills/earn/marketing-engine/intel/treg_lead_signals_weekly.py` | Run the bounded agent pass, validate receipts, dedupe keys, write private state, and send only new rows. |
| `skills/earn/marketing-engine/intel/treg_lead_signals_weekly` | Repository-relative loop entrypoint. |
| `skills/earn/marketing-engine/intel/treg_lead_signals_reconcile.py` | Read one occurrence's persisted Telegram receipt; never sends or retries. |
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
- Extend `provider_process_env(...)` to set `TREG_TOKEN` only from the dedicated agent row, then link the two repo-owned skill directories into the invocation's isolated `$HOME/.agents/skills`.
- For `treg-lead-signals-agent`, use per-invocation `-c` overrides for the Treg remote MCP URL, `env_http_headers`, the four allowed MCP tool names, and unattended approval for those scoped tool calls. Keep `--ignore-user-config`; pass only the header name and `TREG_TOKEN` variable name, never the token value.
- Add `treg-lead-signals-agent` to `TOOLLESS_TASK_CLASSES` and `run_agent.sh`; configure it as Codex-only with model `gpt-6.1-sol`, effort `medium`, and profile `acct2`, with no provider fallback. It uses remote MCP tools while the shell remains disabled/read-only.
- Preserve all model/provider selection and sandbox settings; no general network access is added.

- [x] Create the two skills with triggers, public-signal-only scope, per-call/weekly cost limits, no outreach, and no top-ups.
- [x] Implement exact-SSOT token loading for agent child environments, restrictive directory/file modes, safe skill symlinks, and MCP config overrides only for `treg-lead-signals-agent` without writing token values.
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

- Create: `skills/earn/marketing-engine/intel/treg_lead_signals_weekly.py`
- Create: `skills/earn/marketing-engine/intel/treg_lead_signals_weekly`
- Create: `skills/earn/marketing-engine/intel/treg_lead_signals_reconcile.py`
- Modify: `config/loop-registry.json`

**Interfaces:**

- `run_weekly_monitor(*, state_root: Path, evidence_root: Path, agent_runner=...) -> dict` runs one `treg-lead-signals-agent` pass and returns the Life Manager terminal result fields, `treg_call_ids`, `charged_micro`, `baseline_count`, `new_count`, and optional Telegram `provider_receipt_id`.
- The scheduled signal pass invokes `run_agent.sh --task-class treg-lead-signals-agent`; no general shell/network capability is needed for its Treg MCP calls.
- CSV key: `(product_id, person_url, signal, source_url)`.
- `reconcile_occurrence(state_root: Path, occurrence_id: str) -> dict` returns the exact stored receipt for that occurrence or a typed `unknown`; it never sends.
- Registry owner: `marketing-treg-lead-signals-weekly`, Sunday 21:10 local calendar time, `effect_class=message`, `provider_route=shared-agent-runner`, separate state/log roots.

- [ ] Build the prompt from the five canonical products and four supplements; search the current catalog once per platform, inspect route prices, and make at most two routes per product.
- [ ] Check Treg balance before any paid route; stop without top-up below `$0.05`.
- [ ] Require X/Reddit public results from the last seven days, fit/timing qualification, exact source URLs, and `X-Treg-Route-Max-Cost: 0.003` on each call.
- [ ] Validate the agent JSON and every reported `charged_micro`; reject the run if any route exceeds `$0.003`, total exceeds `$0.054`, or there are more than 18 billed routes.
- [ ] On the first run, write a private baseline and send no old leads. On later runs, compare exact CSV keys and report only new rows.
- [ ] Write state atomically with `0700` directory and `0600` files. Persist `signals.csv` only after the outbox/Telegram decision is durably recorded.
- [ ] Use `skills/_shared/telegram.py`; persist the returned message IDs and receipt before reporting success. If no new rows, do not send.
- [ ] Add a read-only occurrence reconciler that resolves only from the exact persisted provider receipt and never retries a send.
- [ ] Run `python3 -m py_compile` on the three Python entrypoints and `./bin/lm-loop-contract`.
- [ ] Commit and push the loop as its own source change.

### Task 4: Source acceptance and production handoff

**Files:**

- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

- [ ] Run `bash scripts/verify-source-boundary.sh`, `./bin/lm-loop-contract`, and `git diff --check`.
- [ ] Confirm no secrets, signal rows, or provider outputs are staged.
- [ ] Fetch current `origin/main`, preserve unrelated work, push the dedicated branch, and open a PR.
- [ ] Run exact-head CI and read-only review, merge through the standard repository flow, then build a main-derived immutable release.
- [ ] Require `df -k /` free bytes `>= 2 GiB` before release apply. Apply only the new owner through the owner-safe path; do not touch the existing `marketing-weekly-review` unknown occurrence.
- [ ] Confirm the loaded release SHA and Sunday 21:10 schedule. Do not claim production monitoring complete until the natural run records Treg receipts/cost and its baseline; the next natural run must report only unseen keys or no message.
