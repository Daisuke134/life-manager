// lib/comp-window.test.js — RED for the demo comp window.
//
// WHY: onboarding hard-stops at a $29 paywall (telegram-onboard computeStage → "pay") and the
// scheduler cohort filter drops every unpaid row (user-selector: paid=is.true), so a stranger who
// scans the demo QR gets zero calls/travel/asks. LM_COMP_UNTIL is a TIME-BOXED, READ-TIME override:
// it never writes lm_users.paid (lib/billing.js stays the single writer) and it dies on its own at
// the timestamp, so a forgotten env var cannot become a permanent free tier.
"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { compActive, compUntilMs, compBootLog } = require("./comp-window.js"); // missing → RED

const UNTIL = "2026-07-27T12:00:00.000Z";
const UNTIL_MS = Date.parse(UNTIL);

test("absent LM_COMP_UNTIL → inactive", () => {
  assert.equal(compActive({}, UNTIL_MS - 1), false);
  assert.equal(compActive({ LM_COMP_UNTIL: "" }, UNTIL_MS - 1), false);
  assert.equal(compUntilMs({}), null);
});

test("invalid ISO → inactive (never fail open on a typo)", () => {
  for (const raw of ["yes", "tomorrow", "2026-13-45T99:99:99Z", "true", "0"]) {
    assert.equal(compActive({ LM_COMP_UNTIL: raw }, UNTIL_MS - 1), false, `raw=${raw}`);
    assert.equal(compUntilMs({ LM_COMP_UNTIL: raw }), null, `raw=${raw}`);
  }
});

test("gate opens before the timestamp and closes AT it (boundary is exclusive)", () => {
  const env = { LM_COMP_UNTIL: UNTIL };
  assert.equal(compActive(env, UNTIL_MS - 1), true);
  assert.equal(compActive(env, UNTIL_MS), false); // expired exactly on the boundary
  assert.equal(compActive(env, UNTIL_MS + 1), false);
  assert.equal(compActive(env, UNTIL_MS - 86400000), true);
});

test("the value is parsed once per distinct raw string, and re-parsed when it changes", () => {
  assert.equal(compUntilMs({ LM_COMP_UNTIL: UNTIL }), UNTIL_MS);
  assert.equal(compUntilMs({ LM_COMP_UNTIL: UNTIL }), UNTIL_MS); // memo hit, same answer
  assert.equal(compUntilMs({ LM_COMP_UNTIL: "2026-08-01T00:00:00.000Z" }), Date.parse("2026-08-01T00:00:00.000Z"));
  assert.equal(compUntilMs({ LM_COMP_UNTIL: UNTIL }), UNTIL_MS); // and back again
  assert.equal(compUntilMs({ LM_COMP_UNTIL: `  ${UNTIL}  ` }), UNTIL_MS); // surrounding whitespace tolerated
});

test("boot banner is emitted only while active, and names the expiry", () => {
  assert.equal(compBootLog({}, UNTIL_MS - 1), null);
  assert.equal(compBootLog({ LM_COMP_UNTIL: "nope" }, UNTIL_MS - 1), null);
  assert.equal(compBootLog({ LM_COMP_UNTIL: UNTIL }, UNTIL_MS), null); // expired → silent
  assert.equal(compBootLog({ LM_COMP_UNTIL: UNTIL }, UNTIL_MS - 1), `[comp] LM_COMP_UNTIL active until ${UNTIL}`);
});

test("server.js logs the banner once at boot", () => {
  const src = fs.readFileSync(path.join(__dirname, "../server.js"), "utf8");
  assert.ok(/require\(["']\.\/lib\/comp-window\.js["']\)/.test(src), "server.js must import the comp window");
  assert.ok(/compBootLog\(process\.env\)/.test(src), "server.js must evaluate compBootLog(process.env) at boot");
});
