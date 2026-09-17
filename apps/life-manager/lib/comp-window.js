// lib/comp-window.js — LM_COMP_UNTIL: a time-boxed, read-time comp for live demos.
//
// WHY: onboarding hard-stops at the $29 subscription (telegram-onboard computeStage → "pay") and the
// scheduler cohort filter selects `paid=is.true` only (user-selector), so a stranger who scans the
// demo QR gets a paywall and then zero calls/travel/asks. LM_COMP_UNTIL lets those users through for
// a bounded window.
//
// TWO INVARIANTS, both deliberate:
//   1. READ-TIME ONLY. Nothing here writes lm_users.paid — lib/billing.js (the Stripe webhook) stays
//      the single writer. A comped user is never mistaken for a paying customer in the ledger, and
//      revoking the comp is `unset the env var`, not a data repair.
//   2. FAIL CLOSED. Absent, blank, or unparseable → inactive; expired → inactive. A typo like
//      LM_COMP_UNTIL=true must not become a permanent free tier.
//
// Set it to an ISO timestamp, e.g. LM_COMP_UNTIL=2026-07-29T00:00:00Z
"use strict";

// Parsed once per distinct raw value: this is read on every stage computation and every scheduler
// query build, and Date.parse on a hot path is pure waste.
const CACHE = { raw: undefined, until: null };

// Date.parse is far too permissive for a kill switch: "0" and "1" parse as the years 2000 and 2001,
// so a stray boolean-ish value would silently read as a (long expired, but still nonsense) date.
// Demand a real ISO calendar date up front and let Date.parse validate the rest.
const ISO_DATE = /^\d{4}-\d{2}-\d{2}([T ]|$)/;

// PURE: (env) -> epoch ms | null. null means "no comp configured / not parseable".
function compUntilMs(env) {
  const source = env || {};
  const raw = source.LM_COMP_UNTIL == null ? "" : String(source.LM_COMP_UNTIL).trim();
  if (raw !== CACHE.raw) {
    const parsed = ISO_DATE.test(raw) ? Date.parse(raw) : NaN;
    CACHE.raw = raw;
    CACHE.until = Number.isFinite(parsed) ? parsed : null;
  }
  return CACHE.until;
}

// PURE: (env, nowMs) -> boolean. The boundary is exclusive — at the instant of the timestamp the
// comp is already over, so "until 12:00" means the last comped request is at 11:59:59.999.
function compActive(env, nowMs) {
  const until = compUntilMs(env);
  if (until === null) return false;
  const now = Number.isFinite(nowMs) ? nowMs : Date.now();
  return now < until;
}

// PURE: (env, nowMs) -> string | null. null when the comp is off, so the caller logs nothing and a
// normal boot stays quiet. Callers log this exactly once per process.
function compBootLog(env, nowMs) {
  if (!compActive(env, nowMs)) return null;
  return `[comp] LM_COMP_UNTIL active until ${new Date(compUntilMs(env)).toISOString()}`;
}

module.exports = { compActive, compUntilMs, compBootLog };
