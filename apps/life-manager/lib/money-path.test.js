// lib/money-path.test.js — C5/C6 RED. The money-path monitor: extract the Stripe link from the /lm JS
// chunk (inlined by force-static), assert it == the registry known-good LM $29/mo link, and gate
// rollback with debounce (>=2 consecutive FAIL), a flap guard (never roll back into a target that also
// fails), and Telegram dedup (one message per incident). Pure logic; network fetch lives in the caller.
"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  extractStripeLink,
  assertMoneyPath,
  RollbackController,
} = require("./money-path.js"); // missing → RED

const GOOD = "https://buy.stripe.com/cNifZhgcC3h44yYeMK2880X"; // LM $29/mo (registry known-good)
const BAD = "https://buy.stripe.com/00w9ATf8yaJwghG6ge2880v"; // ¥700k AI供養 (the real 2026-07-03 bug)

test("extractStripeLink: pulls buy.stripe.com/<slug> out of a chunk string", () => {
  const chunk = `})}let m="/x",x="${GOOD}",p=/re/;`;
  assert.equal(extractStripeLink(chunk), GOOD);
  assert.equal(extractStripeLink("no link here"), null);
});

test("assertMoneyPath: PASS when bundle link == registry, FAIL on the ¥700k bug", () => {
  const registry = { stripe_lm_url: GOOD };
  assert.equal(assertMoneyPath({ chunk: `x="${GOOD}"` }, registry).ok, true);
  const bad = assertMoneyPath({ chunk: `x="${BAD}"` }, registry);
  assert.equal(bad.ok, false);
  assert.match(bad.reason, /stripe/i);
});

test("RollbackController: debounce — needs >=2 consecutive FAIL before rollback", () => {
  const rc = new RollbackController();
  assert.equal(rc.onResult(false).rollback, false); // 1st fail: wait
  assert.equal(rc.onResult(false).rollback, true); // 2nd consecutive fail: roll back
});

test("RollbackController: a PASS resets the debounce counter", () => {
  const rc = new RollbackController();
  rc.onResult(false);
  rc.onResult(true); // recovered
  assert.equal(rc.onResult(false).rollback, false); // single fail again → wait
});

test("RollbackController: flap guard — do not roll back into a target that also fails", () => {
  const rc = new RollbackController();
  rc.onResult(false);
  const d = rc.onResult(false, { lastGoodPasses: false });
  assert.equal(d.rollback, false);
  assert.equal(d.escalate, true); // escalate instead of flapping into another bad build
});

test("RollbackController: Telegram dedup — ONE alert per incident, re-armed after recovery", () => {
  const rc = new RollbackController();
  rc.onResult(false);
  const a = rc.onResult(false, { lastGoodPasses: false }); // incident opens
  const b = rc.onResult(false, { lastGoodPasses: false }); // still failing
  assert.equal(a.notify, true);
  assert.equal(b.notify, false); // deduped
  rc.onResult(true); // recovery re-arms
  rc.onResult(false);
  assert.equal(rc.onResult(false, { lastGoodPasses: false }).notify, true);
});

test("assertMoneyPath: FAIL when a rogue 2nd stripe link is present (¥700k class) — FIND-003", () => {
  const registry = { stripe_lm_url: GOOD };
  const two = `a="${GOOD}";b="${BAD}";`; // good FIRST, rogue second
  const r = assertMoneyPath({ chunk: two }, registry);
  assert.equal(r.ok, false);
  assert.match(r.reason, /ambiguous|mismatch/);
});

test("RollbackController: rollback fires ONCE per incident, not every cycle — FIND-004", () => {
  const rc = new RollbackController();
  rc.onResult(false);
  assert.equal(rc.onResult(false).rollback, true); // 2nd fail → restore
  assert.equal(rc.onResult(false).rollback, false); // 3rd fail → do NOT restore again
  assert.equal(rc.onResult(false).rollback, false); // 4th fail → still no repeat
  rc.onResult(true); // recovery re-arms
  rc.onResult(false);
  assert.equal(rc.onResult(false).rollback, true); // new incident → restore once
});
