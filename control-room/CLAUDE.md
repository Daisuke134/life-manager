# CLAUDE.md — control-room context loader

> When invoked in this `control-room/` directory, you (Claude / Codex / any
> LLM agent) are acting as an **operator of the Anicca fleet**, not the
> agent itself. Read in the order below before doing any fleet work.

## Priority reading order (every task)

| # | File | Why |
|---|---|---|
| 1 | `README.md` | system map, architecture diagram, what this dir is / is not |
| 2 | `shared/architecture.md` | why 10 profiles per instance × N colony |
| 3 | `profiles/<target-name>/inventory.md` | target profile's role + scope + tools |
| 4 | `profiles/<target-name>/runbook.md` | restart / debug / logs / kickstart |
| 5 | `shared/commands.md` | common ops syntax (`hermes status`, `bws`, etc.) |
| 6 | `shared/security.md` | secret rotation policy, never-commit list |
| 7 | the spec it derives from (`specs/07-HERMES-PIVOT.md` or `specs/05-SERVER-NATIVE-DEPLOY.md`) | authoritative source of truth |

## HARD RULES (inherited from repository root `../AGENTS.md`)

| Rule | Applied here as |
|---|---|
| #0 Superpowers workflow | any change to this directory reads the current applicable skills, verifies, reviews, integrates, and removes the exact worktree |
| #0.12 verify-before-completion | every "done" claim needs fresh evidence (run command, paste output, check exit code) |
| #18 NO parallel implementation | one profile edit at a time; never edit two profiles' files in parallel |
| #-2 NO secrets in OSS | never paste raw `CDP_*`, `OPENROUTER_API_KEY`, `BWS_*`, wallet privkey, or any value from `~/.openclaw/.env` into any file under this directory |

## What you may NEVER do here

1. Paste raw secrets (any value from `~/.openclaw/.env` or Bitwarden vault).
2. Paste operator personal info (MUFG / マイナンバー / phone / personal Gmail / address).
3. Edit `CONSTITUTION.md` (it is hash-pinned; changes break propagation to children).
4. Copy `~/.openclaw/identity/` contents into any file here (PII isolation).
5. Add a profile without registering it in `shared/architecture.md` § profiles table.
6. Run `git commit` from a sub-agent context unless the operator explicitly approved (HARD RULE #0).
7. Skip the verify gate (HARD RULE #0.12) when claiming a profile is "live."

## What you SHOULD do

1. Read the spec section that the file derives from before editing.
2. Use placeholders sparingly — every file should be useful to a fresh LLM agent.
3. Keep tables (per HARD RULE 0.5: "出力は常にテーブル形式").
4. When in doubt about scope, ask the operator (per HARD RULE 0.10: "スペック100%明確になるまで実装禁止").
5. Cite the spec line numbers when claiming "this is what the system does."

## When operator says "spawn a new instance"

→ `templates/new-instance.md` (Daytona provision + CDP wallet derive + 10-profile copy + Constitution hash verify + colony ledger register).

## When operator says "add an 11th profile"

→ `templates/new-profile.md` (copy template + fill 6 standard files + register in `shared/architecture.md` + restart Hermes).

## When operator says "rotate API keys"

→ `api-keys-sop.md` (Bitwarden update → vault propagation → restart all profiles → verify with `bws secret list`).

## When operator says "the fleet is broken"

1. `hermes status` (= daemon up?)
2. `hermes profile list` (= 10 profiles registered?)
3. `~/.hermes/logs/daemon.err` last 100 lines
4. `profiles/fixer/runbook.md` (= the heal protocol)
5. `profiles/constitution/runbook.md` if hash mismatch suspected

---

**END OF CLAUDE.md.**
