"use strict";

const assert = require("node:assert/strict");
const vm = require("node:vm");
const { handlePanelApiRequest } = require("../lib/panel-api.js");
const { renderPanelPage } = require("../lib/panel-ui.js");
const { buildControlCenter } = require("../lib/user-command.js");
const {
  API_ORACLES,
  BROWSER_LOAD_ERROR_COPY,
  BROWSER_ORACLES,
  CHANNELS,
  EXPECTED_COUNTS,
  MALFORMED_CASES,
  POSITIVE_CASES,
  RECIPE_IDS,
  RECIPE_PATTERNS,
  buildRecipes,
} = require("./panel-privacy-contract.js");

const NOW_MS = Date.parse("2026-07-21T12:00:00.000Z");
const SCOPE = Object.freeze({ uid: "panel-contract-user", chatId: "panel-contract-chat", csrf: "panel-contract-csrf" });

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => structuredClone(body),
  };
}

function resultResponse() {
  return {
    status: 0,
    headers: {},
    body: "",
    ended: false,
    setHeader(name, value) {
      this.headers[String(name).toLowerCase()] = value;
    },
    writeHead(status, headers = {}) {
      this.status = status;
      for (const [name, value] of Object.entries(headers)) this.headers[String(name).toLowerCase()] = value;
    },
    end(body) {
      this.body = body || "";
      this.ended = true;
    },
  };
}

function sourceUser(source, hostileValue) {
  return {
    uid: SCOPE.uid,
    name: source === "control-center-identity" ? hostileValue : "Life Manager user",
    telegram_chat_id: SCOPE.chatId,
    phone: null,
    call_language: source === "settings-call-language" || source === "control-center-call-language"
      ? hostileValue
      : null,
    wake_policy: source === "settings-wake-policy" || source === "control-center-wake-policy"
      ? hostileValue
      : "travel-only",
    calendar_provider: null,
    gmail_account_id: null,
    payout_destination: null,
    agent_wallet_address: "0x477EeE969ccfdc0e959F38cE8B83e372FC0262ad",
  };
}

function sourcePreferences() {
  return {
    call_enabled: true,
    notifications_enabled: true,
    daily_automation_enabled: true,
    call_time_zone: "Asia/Tokyo",
  };
}

function controlStore(source, hostileValue) {
  const trace = [];
  const user = sourceUser(source, hostileValue);
  const preferences = sourcePreferences();
  return {
    trace,
    async readUser(scope) {
      trace.push("readUser");
      assert.deepEqual(scope, SCOPE);
      return structuredClone(user);
    },
    async readPreferences(scope) {
      trace.push("readPreferences");
      assert.deepEqual(scope, SCOPE);
      return structuredClone(preferences);
    },
    async readLocation(scope) {
      trace.push("readLocation");
      assert.deepEqual(scope, SCOPE);
      return null;
    },
  };
}

function panelFetch(source, hostileValue) {
  const user = sourceUser(source, hostileValue);
  const preferences = sourcePreferences();
  return async (input, init = {}) => {
    const url = new URL(input);
    if (url.pathname.endsWith("/lm_panel_preferences")) return jsonResponse([preferences]);
    if (url.pathname.endsWith("/lm_users")) return jsonResponse([user]);
    if (url.pathname.endsWith("/lm_wake_log")) return jsonResponse([]);
    if (url.pathname.endsWith("/lm_wake_miss")) return jsonResponse([]);
    if (url.pathname.endsWith("/lm_voice_allowance_ledger")) return jsonResponse([]);
    if (url.pathname.endsWith("/lm_api_cost")) return jsonResponse([]);
    if (url.pathname.endsWith("/lm_agent_earnings")) {
      return jsonResponse([{
        entry_key: "fixture-income",
        occurred_at: "2026-07-21T11:00:00.000Z",
        kind: "financial_external_income",
        amount_minor: 1000,
        currency: "USD",
        tx_hash: null,
        source: "x402_sale",
        meta: { provider_payload: source === "ledger-href" ? hostileValue : null },
      }]);
    }
    if (url.pathname.endsWith("/lm_financial_report_receipts")) return jsonResponse([]);
    if (url.pathname.endsWith("/lm_user_locations")) return jsonResponse([]);
    if (url.pathname.endsWith("/rpc/lm_panel_score_outcome_snapshot")) {
      assert.equal(init.method, "POST");
      return jsonResponse({
        overflow: false,
        rows_by_organ: { daily: [], physical: [], mental: [], financial: [] },
      });
    }
    throw new Error(`unexpected panel privacy fixture request: ${url.pathname}`);
  };
}

function panelCalendar(source, hostileValue) {
  return {
    async listEventsRaw(uid) {
      assert.equal(uid, SCOPE.uid);
      const sourceText = source === "timeline-text" ? hostileValue : "予定";
      return [{
        id: sourceText,
        summary: sourceText,
        description: sourceText,
        location: sourceText,
        start: { dateTime: "2026-07-21T14:00:00.000Z", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2026-07-21T15:00:00.000Z", timeZone: "Asia/Tokyo" },
      }];
    },
  };
}

function malformedCandidate(section) {
  if (section === "scores") return { organs: {} };
  if (section === "gates") return { gates: [{ id: "location", unlocked: "yes" }] };
  if (section === "settings") return { call_language: "fr" };
  if (section === "control-center") return { identity: { name: 7 } };
  throw new Error(`unknown malformed section: ${section}`);
}

function candidateTransform(section) {
  return (candidateSection, candidate) => candidateSection === section
    ? malformedCandidate(section)
    : candidate;
}

async function capturePanelResponse({
  section,
  source = "",
  hostileValue = "",
  malformed = false,
  responseCandidateTransform,
}) {
  const req = {
    url: `/api/panel/${section}`,
    method: "GET",
    headers: { cookie: "lm_panel_session=panel-contract-session" },
  };
  const res = resultResponse();
  const store = controlStore(source, hostileValue);
  const options = {
    supaUrl: "https://panel-contract.invalid",
    supaKey: "panel-contract-key",
    fetchImpl: panelFetch(source, hostileValue),
    calendar: panelCalendar(source, hostileValue),
    nowMs: NOW_MS,
    timeZone: "Asia/Tokyo",
    sessionScopeImpl: async () => SCOPE,
    commandStore: store,
    calendarStatus: async () => "MISSING",
    responseCandidateTransform: responseCandidateTransform
      || (malformed ? candidateTransform(section) : undefined),
  };

  if (section === "control-center") {
    const before = store.trace.length;
    await buildControlCenter(SCOPE, { ...options, store });
    assert.deepEqual(store.trace.slice(before), ["readUser", "readPreferences", "readLocation"]);
    store.trace.length = 0;
  }

  await handlePanelApiRequest(req, res, options);

  assert.equal(res.ended, true, `${section}: handlePanelApiRequest must end the captured response`);
  assert.match(String(res.headers["content-type"] || ""), /^application\/json\b/, `${section}: JSON response required`);
  if (section === "control-center") {
    assert.deepEqual(
      store.trace,
      ["readUser", "readPreferences", "readLocation"],
      "control-center must execute the real exported buildControlCenter path",
    );
  }
  return {
    status: res.status,
    headers: { ...res.headers },
    body: JSON.parse(res.body),
    capturedBy: "handlePanelApiRequest",
  };
}

function valueAt(root, path) {
  return path.reduce((value, key) => value == null ? undefined : value[key], root);
}

function assertNoSource(body, hostileValue, label) {
  if (!hostileValue) return;
  assert.equal(JSON.stringify(body).includes(hostileValue), false, `${label}: hostile source reached API response`);
}

function assertApiOracle(captured, oracleName, hostileValue, label) {
  assert.equal(captured.capturedBy, "handlePanelApiRequest", `${label}: response was not captured from the real handler`);
  const oracle = API_ORACLES[oracleName];
  assert.ok(oracle, `${label}: unknown API oracle`);
  assert.equal(captured.status, oracle.status, `${label}: HTTP status`);
  if (oracle.body) assert.deepEqual(captured.body, oracle.body, `${label}: exact error body`);
  else assert.deepEqual(valueAt(captured.body, oracle.path), oracle.equals, `${label}: ${oracle.path.join(".")}`);
  assertNoSource(captured.body, hostileValue, label);
}

function emittedPanelRuntime(captured, section) {
  const html = renderPanelPage();
  const match = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/);
  assert.ok(match, "panel page must emit a script");
  const boot = match[1].indexOf("Promise.allSettled(Object.keys(panelEndpoints)");
  assert.ok(boot > 0, "emitted panel load bootstrap must exist");
  const script = match[1].slice(0, boot);
  const sections = new Map();
  const sectionNode = { dataset: { state: "loading" }, innerHTML: "" };
  const bodyNode = { innerHTML: "" };
  sections.set(section, { sectionNode, bodyNode });
  const requested = [];
  const document = {
    addEventListener() {},
    getElementById() { return null; },
    querySelector(selector) {
      const name = /\[data-panel-section="([^"]+)"\]/.exec(selector)?.[1];
      if (!name || !sections.has(name)) return null;
      return selector.includes("[data-panel-body]") ? sections.get(name).bodyNode : sections.get(name).sectionNode;
    },
  };
  const sandbox = {
    Array,
    BigInt,
    Date,
    Intl,
    Math,
    Number,
    Object,
    Set,
    String,
    URL,
    console: { error() {}, log() {} },
    crypto: { randomUUID: () => "panel-contract-random-id" },
    document,
    fetch: async (url) => {
      requested.push(String(url));
      return {
        status: captured.status,
        ok: captured.status >= 200 && captured.status < 300,
        json: async () => structuredClone(captured.body),
      };
    },
    window: { location: { href: "", reload() {} } },
  };
  vm.runInNewContext(script, sandbox, { filename: "emitted-panel-script.js" });
  assert.equal(typeof sandbox.loadPanelSection, "function", "emitted loadPanelSection must be executable");
  assert.equal(typeof sandbox.markError, "function", "emitted markError must be executable");
  return {
    async load() {
      try {
        await sandbox.loadPanelSection(section);
      } catch {
        sandbox.markError(section);
      }
      assert.deepEqual(requested, [`/api/panel/${section}`], `${section}: emitted loader request`);
      return { state: sectionNode.dataset.state, html: bodyNode.innerHTML };
    },
  };
}

async function assertBrowserOracle(captured, section, oracleName, hostileValue, label) {
  const oracle = BROWSER_ORACLES[oracleName];
  assert.ok(oracle, `${label}: unknown browser oracle`);
  const browser = await emittedPanelRuntime(captured, section).load();
  assert.equal(browser.state, oracle.state, `${label}: browser section state`);
  if (oracle.includes) assert.match(browser.html, new RegExp(escapeRegExp(oracle.includes)), `${label}: required browser copy`);
  if (oracle.excludes) assert.equal(browser.html.includes(oracle.excludes), false, `${label}: forbidden browser markup`);
  assert.equal(browser.html.includes(hostileValue), false, `${label}: hostile source reached emitted browser`);
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function assertContractShape() {
  assert.equal(RECIPE_IDS.length, 19);
  assert.equal(new Set(RECIPE_IDS).size, 19);
  assert.deepEqual(Object.keys(RECIPE_PATTERNS), RECIPE_IDS);
  for (const recipe of buildRecipes()) {
    assert.match(recipe.value, RECIPE_PATTERNS[recipe.id], `${recipe.id}: pinned semantic shape`);
  }
  assert.deepEqual(CHANNELS.map((channel) => channel.id), [
    "api-timeline-text",
    "api-ledger-href",
    "api-settings-call-language",
    "api-settings-wake-policy",
    "api-control-center-call-language",
    "api-control-center-wake-policy",
    "browser-timeline-text",
    "browser-ledger-href",
    "browser-control-center-identity",
  ]);
  assert.deepEqual(MALFORMED_CASES.map((testCase) => testCase.section), [
    "scores",
    "gates",
    "settings",
    "control-center",
  ]);
  assert.deepEqual(EXPECTED_COUNTS, { api: 177, browser: 63 });
}

function assertSettingsNull(body) {
  assert.deepEqual(body, {
    call_language: null,
    call_schedule: {
      time_zone: "Asia/Tokyo",
      minutes_before: [10, 5],
      wake_policy: "travel-only",
    },
    connections: {
      calendar: false,
      gmail: false,
      telegram: true,
    },
  });
}

function assertControlCenterNull(body) {
  assert.equal(body.identity.name, "Life Manager user");
  assert.equal(body.settings.call_language, null);
  assert.deepEqual(Object.keys(body).sort(), [
    "connections",
    "context",
    "controls",
    "csrf",
    "identity",
    "settings",
  ]);
}

async function runPanelPrivacyApiEval() {
  assertContractShape();
  let api = 0;
  const failures = [];

  async function check(label, assertion) {
    try {
      await assertion();
    } catch (error) {
      failures.push({ label, error });
    }
  }

  for (const recipe of buildRecipes()) {
    for (const channel of CHANNELS) {
      await check(`${recipe.id}/${channel.id}`, async () => {
        const captured = await capturePanelResponse({
          section: channel.section,
          source: channel.source,
          hostileValue: recipe.value,
        });
        assertApiOracle(captured, channel.apiOracle, recipe.value, `${recipe.id}/${channel.id}`);
        api += 1;
      });
    }
  }

  for (const positive of POSITIVE_CASES) {
    await check(positive.id, async () => {
      const captured = await capturePanelResponse({
        section: positive.section,
        source: positive.source,
      });
      assert.equal(captured.status, 200, `${positive.id}: HTTP status`);
      if (positive.section === "settings") assertSettingsNull(captured.body);
      else assertControlCenterNull(captured.body);
      api += 1;
    });
  }

  for (const malformed of MALFORMED_CASES) {
    await check(malformed.id, async () => {
      const captured = await capturePanelResponse({
        section: malformed.section,
        malformed: true,
      });
      assert.equal(captured.status, 422, `${malformed.id}: HTTP status`);
      assert.deepEqual(captured.body, {
        error: "section_unavailable",
        section: malformed.section,
      }, `${malformed.id}: exact section error`);
      api += 1;
    });
  }

  if (failures.length) {
    const representatives = new Map();
    for (const { label, error } of failures) {
      const contractPart = label.includes("/") ? label.slice(label.indexOf("/") + 1) : label;
      if (!representatives.has(contractPart)) representatives.set(contractPart, `${label}: ${error.message}`);
    }
    throw new Error(
      `Panel privacy API RED: ${failures.length}/${EXPECTED_COUNTS.api} cases failed; `
      + `passed assertions api=${api}/${EXPECTED_COUNTS.api}\n${[...representatives.values()].join("\n")}`,
    );
  }

  assert.equal(api, EXPECTED_COUNTS.api);
  return Object.freeze({ api, recipes: RECIPE_IDS.length, channels: CHANNELS.length });
}

async function runPanelPrivacyEval() {
  assertContractShape();
  const counters = { api: 0, browser: 0 };
  const failures = [];
  let executedCases = 0;

  async function check(label, assertion) {
    executedCases += 1;
    try {
      await assertion();
    } catch (error) {
      failures.push({ label, error });
    }
  }

  for (const recipe of buildRecipes()) {
    for (const channel of CHANNELS) {
      await check(`${recipe.id}/${channel.id}`, async () => {
        const captured = await capturePanelResponse({
          section: channel.section,
          source: channel.source,
          hostileValue: recipe.value,
        });
        assertApiOracle(captured, channel.apiOracle, recipe.value, `${recipe.id}/${channel.id}`);
        counters.api += 1;
        if (channel.browserOracle) {
          await assertBrowserOracle(
            captured,
            channel.section,
            channel.browserOracle,
            recipe.value,
            `${recipe.id}/${channel.id}`,
          );
          counters.browser += 1;
        }
      });
    }
  }

  for (const positive of POSITIVE_CASES) {
    await check(positive.id, async () => {
      const captured = await capturePanelResponse({
        section: positive.section,
        source: positive.source,
      });
      assert.equal(captured.status, 200, `${positive.id}: HTTP status`);
      if (positive.section === "settings") assertSettingsNull(captured.body);
      else assertControlCenterNull(captured.body);
      counters.api += 1;
      const browser = await emittedPanelRuntime(captured, positive.section).load();
      assert.equal(browser.state, "loaded", `${positive.id}: browser section state`);
      assert.equal(browser.html.includes(positive.browserIncludes), true, `${positive.id}: null placeholder`);
      counters.browser += 1;
    });
  }

  for (const malformed of MALFORMED_CASES) {
    await check(malformed.id, async () => {
      const captured = await capturePanelResponse({
        section: malformed.section,
        malformed: true,
      });
      assert.equal(captured.status, 422, `${malformed.id}: HTTP status`);
      assert.deepEqual(captured.body, {
        error: "section_unavailable",
        section: malformed.section,
      }, `${malformed.id}: exact section error`);
      counters.api += 1;
      const browser = await emittedPanelRuntime(captured, malformed.section).load();
      assert.equal(browser.state, "error", `${malformed.id}: browser section state`);
      assert.equal(browser.html, `<p class="error">${BROWSER_LOAD_ERROR_COPY}</p>`, `${malformed.id}: fixed load error`);
      counters.browser += 1;
    });
  }

  if (failures.length) {
    const representatives = new Map();
    for (const { label, error } of failures) {
      const contractPart = label.includes("/") ? label.slice(label.indexOf("/") + 1) : label;
      if (!representatives.has(contractPart)) representatives.set(contractPart, `${label}: ${error.message}`);
    }
    const details = [...representatives.values()].join("\n");
    throw new Error(
      `Panel privacy contract RED: ${failures.length}/${executedCases} cases failed; `
      + `passed assertions api=${counters.api}/${EXPECTED_COUNTS.api} browser=${counters.browser}/${EXPECTED_COUNTS.browser}\n${details}`,
    );
  }

  assert.deepEqual(counters, EXPECTED_COUNTS);
  return Object.freeze({ ...counters, recipes: RECIPE_IDS.length, channels: CHANNELS.length });
}

module.exports = {
  capturePanelResponse,
  emittedPanelRuntime,
  runPanelPrivacyApiEval,
  runPanelPrivacyEval,
};
