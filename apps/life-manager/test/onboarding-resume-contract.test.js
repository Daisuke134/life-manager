"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const LANDING = path.resolve(__dirname, "../../landing");
const ONBOARD_HANDLER = path.join(LANDING, "netlify/functions/lm-onboard.js");
const LM_BODY = path.join(LANDING, "app/lm/LmBody.tsx");
const LM_CLIENT = path.join(LANDING, "app/lm/LmClient.tsx");

function loadHandler() {
  const source = fs.readFileSync(ONBOARD_HANDLER, "utf8");
  const module = { exports: {} };
  const localRequire = createRequire(ONBOARD_HANDLER);
  new Function("exports", "require", "module", "__filename", "__dirname", source)(
    module.exports, localRequire, module, ONBOARD_HANDLER, path.dirname(ONBOARD_HANDLER));
  return { handler: module.exports.handler, source };
}

test("Task 8: every retired lm-onboard action is JSON 410 with zero external effects", async () => {
  const { handler } = loadHandler();
  const originalFetch = global.fetch;
  let fetchCalls = 0;
  global.fetch = async () => { fetchCalls++; throw new Error("retired onboarding must not fetch"); };
  try {
    for (const action of ["google-start", "google-callback", "exchange", "save", "telegram-link"]) {
      const result = await handler({
        httpMethod: action === "exchange" || action === "save" || action === "telegram-link" ? "POST" : "GET",
        queryStringParameters: { action, return: "https://evil.example/", state: "forged" },
        body: "not-json-authority-payload",
      });
      assert.equal(result.statusCode, 410, action);
      assert.match(result.headers["Content-Type"], /application\/json/i, action);
      assert.deepEqual(JSON.parse(result.body), { error: "legacy_onboarding_retired" }, action);
    }
  } finally {
    global.fetch = originalFetch;
  }
  assert.equal(fetchCalls, 0);
});

test("Task 8: unknown lm-onboard actions remain non-effectful JSON responses", async () => {
  const { handler } = loadHandler();
  const originalFetch = global.fetch;
  let fetchCalls = 0;
  global.fetch = async () => { fetchCalls++; throw new Error("unknown onboarding action must not fetch"); };
  try {
    const result = await handler({ httpMethod: "POST", queryStringParameters: { action: "future-action" }, body: "not-json" });
    assert.equal(result.statusCode, 400);
    assert.deepEqual(JSON.parse(result.body), { error: "unknown_action" });
  } finally {
    global.fetch = originalFetch;
  }
  assert.equal(fetchCalls, 0);
});

test("Task 8: retired handler has no credential/provider/parser authority surface", () => {
  const { source } = loadHandler();
  assert.doesNotMatch(source, /process\.env|JSON\.parse|fetch\s*\(/);
  assert.doesNotMatch(source, /SUPABASE|COMPOSIO|LM_UID_SECRET|client_reference_id|paid/i);
});

test("Task 13: /lm CTA opens the Web Calendar connection in the same tab", () => {
  const source = fs.readFileSync(LM_BODY, "utf8");
  assert.match(source, /const WEB_APP_CTA_URL\s*=\s*['"]https:\/\/life-call-production\.up\.railway\.app\/lm\?start_calendar=1['"]/);
  assert.match(source, /href=\{WEB_APP_CTA_URL\}/);
  assert.match(source, /t\.primaryCta/);
  const primaryLink = source.match(/<a\s+href=\{WEB_APP_CTA_URL\}([\s\S]*?)>/);
  assert.ok(primaryLink, "primary Web CTA exists");
  assert.doesNotMatch(primaryLink[1], /target="_blank"/);
  assert.doesNotMatch(source, /TG_DEEPLINK|LifeManagerBotbot|t\.soonCta/);
  assert.match(source, /useLaunchLocale/);
  assert.match(source, /launchStrings/);
  assert.match(source, /t\.publicTitle/);
  assert.match(source, /t\.publicBody/);
  for (const forbidden of [
    /LmClient/, /useEffect/, /useState/, /window\.location/, /URLSearchParams/, /searchParams\.get\(['"]tg['"]\)/,
    /lm-onboard/, /calendar-connect/, /localStorage|sessionStorage/, /signInWithGoogle|Supabase/i,
    /test-call|TEST_CALL_URL|client_reference_id/, /JSON\.stringify/, /uid|sig|tg=/i,
  ]) assert.doesNotMatch(source, forbidden);
});

test("Task 8: legacy browser onboarding client is retired instead of remaining a shadow authority", () => {
  assert.equal(fs.existsSync(LM_CLIENT), false);
});
