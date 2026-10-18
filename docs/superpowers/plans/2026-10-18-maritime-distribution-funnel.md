# Maritime Distribution Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task.

**Goal:** Build a default-off, consent-gated Telegram acquisition path for Life Manager's Maritime competition pilot and measure its real-use funnel without storing message content.

**Architecture:** Reuse the existing Life Manager Node server, Telegram tenant identity, Maritime transport, and append-only `lm_web_funnel_events`. A server-rendered campaign page redirects to a validated Telegram deep link; a service-role-only pseudonymous participant store records consent and milestones with an atomic cohort cap.

**Tech Stack:** Node.js CommonJS, built-in `node:test`, Supabase PostgREST/Postgres migration, existing Next.js landing source.

**Spec:** `docs/superpowers/specs/2026-10-16-maritime-pilot-design.md`, with TODO order owned by `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`.

## Global Constraints

- Public entry, CTA, and Maritime provider calls remain default-off.
- Preserve current data, tool-policy, API key, UID secret, and 3-user allowlist gates.
- A public cohort requires explicit consent and has a validated cap of 25 by default, configurable up to 1,000.
- Use HMAC participant IDs; never persist Telegram text, Maritime responses, Telegram IDs, or profile details in new funnel rows.
- Do not apply migrations, alter production configuration, provision Maritime VMs, or contact users in this source task.

## Review Focus

- Unknown or malformed source tags cannot become redirect targets or scriptable HTML.
- Web-linked Telegram tenants can use the Maritime route without creating a duplicate legacy tenant.
- `/pilot` before consent writes no receipt, calls no provider, and stores no prompt fingerprint.
- Duplicate Telegram delivery cannot consume another cohort slot or create duplicate milestone events.
- Consent revocation immediately blocks later `/pilot` calls while preserving the audit record.

---

### Task 1: Public pilot gate and participant state

**Files:** `apps/life-manager/lib/transport/maritime-pilot.js`, `apps/life-manager/lib/transport/maritime-pilot.test.js`, new `apps/life-manager/lib/maritime-distribution.js`, its focused test, and a new SQL migration.

**Interfaces:** Transport exposes `isPublicEntryEnabled()` and allows a non-allowlisted UID only when the existing global gates, public flag, consent check, and enrollment cap all pass. The distribution store exposes source parsing, participant read/accept/revoke, anonymous page/click recording, and one-time response/7-day-return milestone methods.

- [x] Write tests for a validated public cap/default-off gate, deep-link parsing, consent/cap transitions, and content-free milestone events.
- [x] Run the focused tests and verify expected failures.
- [x] Implement participant table/RPC and distribution store; extend the existing funnel event allowlist.
- [x] Run the focused tests and verify the gates, idempotency, and privacy assertions pass.
- [ ] Commit `feat: add Maritime cohort tracking` and push this branch before Task 2.

### Task 2: Telegram and HTTP acquisition path

**Files:** `apps/life-manager/server.js`, `apps/life-manager/lib/slash-command.js`, and `apps/life-manager/test/telegram-slash-http-contract.test.js`.

**Interfaces:** `GET /maritime` serves the campaign page only when public pilot readiness passes; `GET /maritime/start` redirects only to the validated bot deep link. `/start maritime_<source>` claims or reuses the existing user tenant and displays the data notice without Calendar OAuth. `/maritime_accept` persists consent; `/maritime_stop` revokes it. `/pilot` checks consent before creating its idempotency receipt or calling Maritime.

- [ ] Add failing HTTP contract coverage for disabled/ready public routes, a new and web-linked Telegram actor, no Calendar start, pre-consent rejection, and post-consent chat.
- [ ] Run the focused contract test and verify expected failures.
- [ ] Implement the routes and tenant-aware command path with no prompt/response logging.
- [ ] Run the focused contract test and verify existing `/start` and `/pilot` behavior remains intact.
- [ ] Commit `feat: add Maritime Telegram acquisition path` and push this branch before Task 3.

### Task 3: Existing Life Manager page CTA and acceptance

**Files:** `apps/landing/app/lm/LmBody.tsx` and the source currently supplying `@/lib/launchStrings` if it exists; otherwise keep the CTA copy local to the component. Update both Maritime specs.

- [ ] Add the second Telegram CTA behind `NEXT_PUBLIC_MARITIME_PILOT_CTA=1`; default build output keeps the existing Calendar CTA only.
- [ ] Run `node --test apps/life-manager/lib/transport/maritime-pilot.test.js apps/life-manager/lib/maritime-distribution.test.js apps/life-manager/test/telegram-slash-http-contract.test.js`, plus the landing's available type/build check if its project manifest is present.
- [ ] Run `git diff --check`, inspect the complete diff, and update the canonical SSOT cursor/evidence.
- [ ] Commit `feat: add Maritime distribution CTA` and push this branch for PR/CI.
