"use strict";

const test = require("node:test");
const assert = require("node:assert");
const vm = require("node:vm");
const { roundedScoreValue } = require("./panel-score-semantics.js");

let renderPanelPage = null;
let renderScoreCards = null;
let renderPanelOnboardingPage = null;
try {
  ({ renderPanelPage, renderScoreCards, renderPanelOnboardingPage } = require("./panel-ui.js"));
} catch (error) {
  if (error.code !== "MODULE_NOT_FOUND") throw error;
}

const MONEY_OPPORTUNITY_ID = "a".repeat(64);
const MONEY_OPPORTUNITY_REF = `opportunity://tenant-a/${MONEY_OPPORTUNITY_ID}`;
const MONEY_JOB_REF = `runtime-job://tenant-a/goal%3A${MONEY_OPPORTUNITY_ID}`;
const OTHER_OPPORTUNITY_ID = "b".repeat(64);
const OTHER_OPPORTUNITY_REF = `opportunity://tenant-a/${OTHER_OPPORTUNITY_ID}`;
const OTHER_JOB_REF = `runtime-job://tenant-a/goal%3A${OTHER_OPPORTUNITY_ID}`;
const HUMAN_TASK_REF = `human-task://tenant-a/${"c".repeat(64)}`;
const MONEY_OBSERVED_AT = "2026-08-29T00:00:00.000Z";

test("Task 7B: Telegram-native onboarding page is server-state driven and safe at 375px", () => {
  assert.equal(typeof renderPanelOnboardingPage, "function");
  const html = renderPanelOnboardingPage({ csrf: 'csrf-<>&"\'' });
  assert.match(html, /data-panel-onboarding/);
  assert.match(html, /data-csrf="csrf-&lt;&gt;&amp;&quot;&#39;"/);
  assert.match(html, /\/api\/panel\/onboarding/);
  assert.match(html, /\/api\/panel\/onboarding\/calendar\/start/);
  assert.match(html, /\/api\/panel\/onboarding\/calendar\/status/);
  assert.match(html, /@media\s*\(max-width:\s*375px\)/);
  assert.match(html, /replaceChildren\(/);
  assert.match(html, /\.textContent\s*=/);
  assert.match(html, /\.value\s*=/);
  assert.doesNotMatch(html, /\.innerHTML\s*=/);
  assert.doesNotMatch(html, /localStorage|sessionStorage|Sign in with Google|Supabase auth|\/auth\//i);
  assert.match(html, /credentials:\s*["']same-origin["']/);
  assert.match(html, /idempotency-key/);
  assert.match(html, /x-lm-csrf/);
  assert.doesNotMatch(html, /paymentLink|buy\.stripe\.com|無料期間|月額プラン/);
  assert.match(html, /電話通知（任意）/);
  assert.match(html, /10分前と5分前/);
  assert.match(html, /自宅の住所/);
  assert.doesNotMatch(html, /現在.*ライブ位置情報/);
  assert.match(html, /window\.location\.(?:assign|replace)\(/);
  const order = ["name", "calendar", "home", "notifications", "phone", "call", "dashboard"];
  let previous = -1;
  for (const step of order) {
    const position = html.indexOf(`case "${step}"`);
    assert.ok(position > previous, `${step} must be dispatched from server step order`);
    previous = position;
  }
  assert.match(html, /phone\.skip/);
  assert.match(html, /call\.skip/);
  assert.doesNotMatch(html, /payment\.skip|payment\.open/);
  assert.match(html, /primary-action/);
  assert.match(html, /overflow-wrap:\s*anywhere/);
});

test("Task 7B: onboarding UI never interpolates server copy into markup and keeps static labels escaped", () => {
  const html = renderPanelOnboardingPage({ csrf: "safe-token" });
  assert.doesNotMatch(html, /\.insertAdjacentHTML\(/);
  assert.match(html, /createElement\(["'](?:input|button|a|label|p|span)["']\)/);
  assert.match(html, /textContent\s*=/);
  assert.match(html, /new URL\(value\)/);
  assert.doesNotMatch(html, /buy\.stripe\.com/);
});

class OnboardingFakeNode {
  constructor(tagName, parent = null) {
    this.tagName = tagName.toUpperCase();
    this.parentNode = parent;
    this.children = [];
    this.dataset = {};
    this.className = "";
    this.attributes = {};
    this.textContent = "";
    this.value = "";
  }

  append(...nodes) { for (const node of nodes) { node.parentNode = this; this.children.push(node); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  addEventListener() {}
  setAttribute(name, value) { this.attributes[name] = String(value); }
  matches(selector) {
    if (selector === "[data-panel-onboarding]") return this.dataset.panelOnboarding !== undefined;
    const dataAction = /^\[data-onboarding-action\]$/.test(selector);
    if (dataAction) return this.dataset.onboardingAction !== undefined;
    if (selector === "input") return this.tagName === "INPUT";
    return false;
  }
  querySelector(selector) {
    if (selector === "[data-onboarding-title]" && this.dataset.onboardingTitle !== undefined) return this;
    if (selector === "[data-onboarding-copy]" && this.dataset.onboardingCopy !== undefined) return this;
    if (selector === "[data-onboarding-form]" && this.dataset.onboardingForm !== undefined) return this;
    if (selector === "[data-onboarding-actions]" && this.dataset.onboardingActions !== undefined) return this;
    if (selector === "[data-onboarding-status]" && this.dataset.onboardingStatus !== undefined) return this;
    if (this.matches(selector)) return this;
    for (const child of this.children) { const found = child.querySelector(selector); if (found) return found; }
    return null;
  }
  closest(selector) { let node = this; while (node) { if (node.matches(selector)) return node; node = node.parentNode; } return null; }
}

function onboardingFakeDocument() {
  const root = new OnboardingFakeNode("main"); root.dataset.panelOnboarding = ""; root.dataset.csrf = "csrf";
  const title = new OnboardingFakeNode("h1"); title.dataset.onboardingTitle = "";
  const copy = new OnboardingFakeNode("p"); copy.dataset.onboardingCopy = "";
  const form = new OnboardingFakeNode("div"); form.dataset.onboardingForm = "";
  const actions = new OnboardingFakeNode("div"); actions.dataset.onboardingActions = "";
  const status = new OnboardingFakeNode("p"); status.dataset.onboardingStatus = "";
  root.append(title, copy, form, actions, status);
  return { root, document: { querySelector: (selector) => root.querySelector(selector), createElement: (tag) => new OnboardingFakeNode(tag) } };
}

async function runOnboardingInline(state) {
  const html = renderPanelOnboardingPage({ csrf: "csrf" });
  const script = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const fake = onboardingFakeDocument();
  const response = { status: 200, ok: true, json: async () => state };
  vm.runInNewContext(script, {
    document: fake.document,
    fetch: async () => response,
    URL,
    Promise,
    Date,
    Math,
    Object,
    String,
    globalThis: {},
    window: { location: { reload() {}, assign() {} } },
  });
  await new Promise((resolve) => setImmediate(resolve));
  return fake;
}

test("Task 7B: every server-provided step has one primary action and only phone/call have skips", async () => {
  const states = [
    { step: "name", name: "A" },
    { step: "calendar" },
    { step: "home", homeAddress: "home" },
    { step: "notifications" },
    { step: "phone", phone: "" },
    { step: "call" },
    { step: "payment", paymentLink: "https://buy.stripe.com/test_life_manager?client_reference_id=server" },
    { step: "dashboard", paid: false },
    { step: "dashboard", paid: true },
  ];
  for (const state of states) {
    const fake = await runOnboardingInline(state);
    const actions = fake.root.querySelector("[data-onboarding-actions]").children;
    const expectedPrimary = state.step === "payment" ? 1 : 1;
    assert.equal(actions.filter((node) => node.className.includes("primary-action")).length, expectedPrimary, state.step);
    const secondary = actions.filter((node) => node.className.includes("secondary-action"));
    const expectedSecondary = ["phone", "call"].includes(state.step);
    assert.equal(secondary.length, expectedSecondary ? 1 : 0, state.step);
    if (state.step === "dashboard" && state.paid === true) assert.equal(actions[0].href, "/panel");
  }
});

test("Task 7B: inline onboarding renderer ignores forged identity/payment fields and uses server step only", async () => {
  const fake = await runOnboardingInline({ step: "phone", phone: "", paid: true, uid: "forged", tg: "forged", paymentLink: "https://evil.example/collect" });
  const actions = fake.root.querySelector("[data-onboarding-actions]").children;
  assert.equal(actions.filter((node) => node.className.includes("primary-action")).length, 1);
  assert.equal(actions.some((node) => node.href), false);
  const visible = [];
  const walk = (node) => { visible.push(node.textContent, node.value, node.href || "", node.dataset.onboardingAction || ""); for (const child of node.children) walk(child); };
  walk(fake.root);
  assert.doesNotMatch(visible.join("\n"), /forged|evil\.example/);
});

test("Task 3: ready dashboard shows value and next event without trial or checkout", async () => {
  const fake = await runOnboardingInline({
    step: "dashboard",
    paid: false,
    trialExpiresAt: "2026-08-31T12:00:00.000Z",
    trialActive: true,
    nextEvent: { summary: "<img src=x onerror=alert(1)>", startAt: "2026-08-28T14:00:00.000Z" },
    paymentLink: "https://buy.stripe.com/test_life_manager?client_reference_id=server",
  });
  const actions = fake.root.querySelector("[data-onboarding-actions]").children;
  assert.equal(actions.filter((node) => node.className.includes("primary-action")).length, 1);
  assert.equal(actions.filter((node) => node.className.includes("secondary-action")).length, 0);
  const visible = [];
  const walk = (node) => { visible.push(node.textContent, node.value, node.href || ""); for (const child of node.children) walk(child); };
  walk(fake.root);
  const text = visible.join("\n");
  assert.match(text, /準備できました/);
  assert.match(text, /移動時間を確保/);
  assert.match(text, /出発前にTelegramで経路/);
  assert.doesNotMatch(text, /無料期間|月額プラン|2026-08-31T12:00:00\.000Z|buy\.stripe\.com/);
  assert.match(text, /<img src=x onerror=alert\(1\)>/);
  assert.match(text, /2026-08-28T14:00:00\.000Z/);

  const withoutCheckout = await runOnboardingInline({ step: "dashboard", paid: false, trialActive: true });
  assert.equal(withoutCheckout.root.querySelector("[data-onboarding-actions]").children.length, 1);
});

test("Task 3: ready copy never exposes legacy paid/trial state", async () => {
  const visibleText = async (state) => {
    const fake = await runOnboardingInline(state);
    const visible = [];
    const walk = (node) => { visible.push(node.textContent, node.value, node.href || ""); for (const child of node.children) walk(child); };
    walk(fake.root);
    return { fake, text: visible.join("\n") };
  };

  const paid = await visibleText({ step: "dashboard", paid: true, trialActive: false, trialExpiresAt: "2026-08-31T12:00:00.000Z" });
  assert.match(paid.text, /移動時間を確保/);
  assert.match(paid.text, /出発前にTelegramで経路/);
  assert.doesNotMatch(paid.text, /有料プラン|無料期間|2026-08-31/);

  const ended = await visibleText({ step: "dashboard", paid: false, trialActive: false, paymentLink: "https://buy.stripe.com/test_life_manager?client_reference_id=server" });
  assert.match(ended.text, /移動時間を確保/);
  assert.doesNotMatch(ended.text, /無料期間|停止中|月額プラン|buy\.stripe\.com/);
  const endedActions = ended.fake.root.querySelector("[data-onboarding-actions]").children;
  assert.equal(endedActions.length, 1);
  assert.equal(endedActions[0].className, "primary-action");
  assert.equal(endedActions[0].href, "/panel");
});

function safeIntegerFinancialOrgans() {
  const ref = "outcome:10000000-0000-4000-8000-000000000001";
  const period = (kind) => ({ kind, start_at: "2026-07-08T12:00:00.000Z", end_at: "2026-07-15T12:00:00.000Z" });
  return {
    daily: { status: "insufficient_data", value: null, period: period("rolling_7_days"), numerator: 0, denominator: 0, reason: "No DAILY outcomes.", source_outcome_ids: [], components: { timezone: "UTC", excluded_unknown_count: 0, eligible_events: 0, resolved_events: 0, required_succeeded: 0, required_failed: 0, required_pending: 0, context_unnecessary: 0, optional_ignored: 0 } },
    physical: { status: "insufficient_data", value: null, period: period("rolling_30_days"), numerator: 0, denominator: 0, reason: "No PHYSICAL outcomes.", source_outcome_ids: [], components: { timezone: "UTC", excluded_unknown_count: 0, detected_needs: 0, confirmed_booking: 0, confirmed_completion: 0, unresolved_needs: 0, search_candidate_unconfirmed: 0 } },
    mental: { status: "insufficient_data", value: null, period: period("rolling_7_days"), numerator: 0, denominator: 0, reason: "No MENTAL outcomes.", source_outcome_ids: [], components: { timezone: "UTC", excluded_unknown_count: 0, deduplicated_triggers: 0, delivered_within_cap: 0, suppression_honored: 0, correction_persisted: 0, cap_overflow: 0, unresolved_triggers: 0 } },
    financial: { status: "measured", value: 10, period: period("calendar_month"), numerator: 945755921642804, denominator: 9007199253740991, reason: "Verified net income.", source_outcome_ids: [ref], components: { timezone: "UTC", excluded_unknown_count: 0, currency: "USD", gross_income_minor: 9007199253740991, realized_loss_minor: 8061443332098187, fee_minor: 0, user_transfer_minor: 0, excluded_rows: 0, net_clamped: false } },
  };
}

function emittedScoreRenderer() {
  const script = renderPanelPage().match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const start = script.indexOf("const SCORE_LABELS");
  const end = script.indexOf("const renderScores = renderScoreCards;") + "const renderScores = renderScoreCards;".length;
  const sandbox = { Intl, Date, Object, Array, Number, String, BigInt, Set, Math };
  vm.runInNewContext(`${script.slice(start, end)}\nglobalThis.__renderScores = renderScoreCards;`, sandbox);
  return sandbox.__renderScores;
}

function emittedMoneyPrinterRenderer() {
  const script = renderPanelPage().match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const start = script.indexOf("const moneyLaneLabels");
  const end = script.indexOf("const renderers = Object.freeze");
  const sandbox = { Object, Array, Number, String, BigInt, Set, Math, URL };
  sandbox.escapeHtml = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
  sandbox.displayRecord = (value) => Boolean(value && typeof value === "object" && !Array.isArray(value));
  sandbox.displayExactKeys = (value, expected) => sandbox.displayRecord(value)
    && Object.keys(value).sort().join(",") === expected.slice().sort().join(",");
  sandbox.displayContainsSensitiveValue = () => false;
  sandbox.displaySafeText = (value, allowEmpty) => typeof value === "string" && (allowEmpty || value.trim().length > 0);
  vm.runInNewContext(`${script.slice(start, end)}\nglobalThis.__renderMoneyPrinter = renderMoneyPrinter;\nglobalThis.__validateMoneyPrinterData = validateMoneyPrinterData;`, sandbox);
  return { render: sandbox.__renderMoneyPrinter, validate: sandbox.__validateMoneyPrinterData };
}

function emittedMoneyPrinterWorkroom() {
  const script = renderPanelPage().match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const start = script.indexOf("const moneyLaneLabels");
  const end = script.indexOf("const renderers = Object.freeze");
  const sandbox = { Object, Array, Number, String, BigInt, Set, Math, URL, Date, Promise, encodeURIComponent };
  sandbox.escapeHtml = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
  sandbox.displayRecord = (value) => Boolean(value && typeof value === "object" && !Array.isArray(value));
  sandbox.displayExactKeys = (value, expected) => sandbox.displayRecord(value)
    && Object.keys(value).sort().join(",") === expected.slice().sort().join(",");
  sandbox.displayContainsSensitiveValue = () => false;
  sandbox.displaySafeText = (value, allowEmpty) => typeof value === "string" && (allowEmpty || value.trim().length > 0);
  vm.runInNewContext(`${script.slice(start, end)}
    globalThis.__validateMoneyWorkroom = typeof validateMoneyWorkroom === "function" ? validateMoneyWorkroom : null;
    globalThis.__loadMoneyWorkroom = typeof loadMoneyWorkroom === "function" ? loadMoneyWorkroom : null;`, sandbox);
  return { validate: sandbox.__validateMoneyWorkroom, load: sandbox.__loadMoneyWorkroom, sandbox };
}

function emittedMoneyOpportunitySubmit() {
  const script = renderPanelPage({ csrf: "page-csrf" }).match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const start = script.indexOf("async function submitMoneyOpportunity");
  const end = script.indexOf("\n    function commandForAction", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = { Promise, Object, String, controlCsrf: "page-csrf", crypto: { randomUUID: () => "request-uuid" } };
  vm.runInNewContext(`${script.slice(start, end)}\nglobalThis.__submitMoneyOpportunity = submitMoneyOpportunity;`, sandbox);
  return { submit: sandbox.__submitMoneyOpportunity, sandbox };
}

function moneyWorkroomData(overrides = {}) {
  return {
    opportunity_id: MONEY_OPPORTUNITY_ID,
    title: "Selected workroom",
    value_minor: "50000",
    currency: "JPY",
    source_url: "https://public.example/opportunity",
    status: "WORKING",
    job_ref: MONEY_JOB_REF,
    activity: [
      { kind: "opportunity", ref: MONEY_OPPORTUNITY_REF, status: "WORKING", observed_at: MONEY_OBSERVED_AT },
      { kind: "work", ref: MONEY_JOB_REF, status: "running", observed_at: MONEY_OBSERVED_AT },
    ],
    ...overrides,
  };
}

test("PANEL-8h: panel shell identifies the product only as Life Manager", () => {
  const html = renderPanelPage();
  assert.equal(html.match(/<title>([^<]+)<\/title>/)?.[1], "Life Manager");
  assert.equal(html.match(/<p class="wordmark">([^<]+)<\/p>/)?.[1], "Life Manager / life operations");
  assert.equal(html.match(/<h1>([^<]+)<\/h1>/)?.[1], "Life Manager");
  assert.doesNotMatch(html, /\bAnicca\b/i);
});

test("LM-33c: panel renders the five mirror sections in spec order", () => {
  assert.equal(typeof renderPanelPage, "function");
  const html = renderPanelPage();
  assert.match(html, /<html lang="ja">/);
  assert.match(html, /<meta name="viewport" content="width=device-width,initial-scale=1">/);

  const sections = ["timeline", "scores", "ledger", "gates", "settings"];
  let previous = -1;
  for (const section of sections) {
    const position = html.indexOf(`data-panel-section="${section}"`);
    assert.ok(position > previous, `${section} must exist after the previous section`);
    previous = position;
  }
});

test("Money Printer panel renders one six-lane control room", () => {
  const html = renderPanelPage();
  assert.match(html, /data-panel-section="money-printer"/);
  assert.match(html, /\/api\/panel\/money-printer/);
  assert.match(html, /data-money-human-task/);
  assert.match(html, /\/api\/panel\/money-printer\/browser/);
  assert.match(html, /I completed it/);
  assert.match(html, /Cannot complete/);
  for (const label of ["Paid & verified", "Agents working", "Needs You", "Opportunity value", "Found", "Working", "Waiting", "Done", "Paid"]) {
    assert.match(html, new RegExp(label));
  }
});

test("Money Printer panel renders one visible WebMCP call status region outside the board body", () => {
  const html = renderPanelPage();
  const regions = html.match(/<p class="money-webmcp-status"[^>]*data-money-webmcp-status/g) || [];
  assert.equal(regions.length, 1);
  assert.match(html, /<p class="money-webmcp-status"[^>]*data-money-webmcp-status[^>]*aria-live="polite"><\/p>/);
  assert.doesNotMatch(html, /WebMCP ready/);
  const moneySection = html.match(/<section class="panel-section" data-panel-section="money-printer"[\s\S]*?<\/section>/)?.[0] || "";
  assert.match(moneySection, /data-panel-body[^>]*>[\s\S]*?<\/div>\s*<p class="money-webmcp-status"/);
});

test("Money Printer WebMCP call status accepts only exact allowlisted events and survives refresh", async () => {
  const html = renderPanelPage();
  const script = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const start = script.indexOf("let moneyPrinterRefresh = Promise.resolve();");
  const end = script.indexOf("\n    function commandForAction", start);
  assert.ok(start >= 0 && end > start);

  const listeners = {};
  const status = { textContent: "" };
  const document = {
    addEventListener(name, callback) { listeners[name] = callback; },
    querySelector(selector) {
      assert.equal(selector, "[data-money-webmcp-status]");
      return status;
    },
  };
  let reloads = 0;
  vm.runInNewContext(script.slice(start, end), {
    Promise,
    console: { error() {} },
    document,
    displayExactKeys(value, expected) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return false;
      const actual = Object.keys(value).sort();
      const wanted = expected.slice().sort();
      return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
    },
    loadPanelSection: async (name) => {
      assert.equal(name, "money-printer");
      reloads += 1;
    },
  });
  assert.equal(typeof listeners["money-printer:webmcp-call"], "function");
  assert.equal(status.textContent, "");

  const dispatch = (detail) => listeners["money-printer:webmcp-call"]({ detail });
  dispatch({ tool: "inspect_money_printer", status: "running" });
  assert.equal(status.textContent, "inspect_money_printer · running");
  for (const invalid of [
    { tool: "inspect_money_printer", status: "succeeded", extra: "ignore" },
    { tool: "unknown_tool", status: "running" },
    { tool: "inspect_money_printer", status: "unknown" },
    null,
    ["inspect_money_printer", "failed"],
  ]) {
    dispatch(invalid);
    assert.equal(status.textContent, "inspect_money_printer · running");
  }
  dispatch({ tool: "record_human_answer", status: "succeeded" });
  assert.equal(status.textContent, "record_human_answer · succeeded");

  const refresh = { detail: {} };
  listeners["money-printer:refresh"](refresh);
  await refresh.detail.promise;
  assert.equal(reloads, 1);
  assert.equal(status.textContent, "record_human_answer · succeeded");
});

test("Money Printer renderer validates currency maps and sorts their display", () => {
  const { render, validate } = emittedMoneyPrinterRenderer();
  const card = { opportunity_ref: MONEY_OPPORTUNITY_REF, title: "Opportunity", status: "DISCOVERED", value_minor: "50000", currency: "JPY", source_url: null };
  const data = {
    observed_at: "2026-08-29T00:00:00.000Z",
    metrics: { agents_working: 1, needs_you: 0, opportunity_value: { USD: "1000", JPY: "50000" }, paid_verified: { USD: "1000", JPY: "50000" } },
    columns: { found: [card], working: [], needs_you: [], waiting: [], done: [], paid: [] },
    activity: [],
  };
  assert.doesNotThrow(() => validate(data));
  assert.match(render(data), /JPY 50000 \+ USD 1000/);
  assert.match(render({ ...data, metrics: { ...data.metrics, opportunity_value: {}, paid_verified: {} } }), /<strong>0<\/strong>/);
  assert.throws(() => render({ ...data, metrics: { ...data.metrics, opportunity_value: { JPY: 50000 } } }), /invalid money printer payload/);
});

test("Money Printer cards emit escaped buttons and retain a workroom placeholder", () => {
  const { render } = emittedMoneyPrinterRenderer();
  const data = {
    observed_at: MONEY_OBSERVED_AT,
    metrics: { agents_working: 0, needs_you: 0, opportunity_value: {}, paid_verified: {} },
    columns: { found: [{ opportunity_ref: MONEY_OPPORTUNITY_REF, title: "<img src=x onerror=alert(1)>", status: "DISCOVERED", value_minor: "50000", currency: "JPY", source_url: null }], working: [], needs_you: [], waiting: [], done: [], paid: [] },
    activity: [],
  };
  const html = render(data);
  assert.match(html, /<button class="money-card" type="button"/);
  assert.match(html, new RegExp(`data-money-opportunity-id="${MONEY_OPPORTUNITY_ID}"`));
  assert.match(html, /data-money-workroom/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html, /<img src=x onerror=alert/);
});

test("Money Printer visible intake posts one exact opportunity and refreshes the same board", async () => {
  const html = renderPanelPage({ csrf: "page-csrf" });
  assert.match(html, /data-money-opportunity-form/);
  assert.match(html, /Add opportunity/);
  const { submit, sandbox } = emittedMoneyOpportunitySubmit();
  const fields = {
    source_url: { value: " https://work.example/job " },
    title: { value: " Paid work " },
    goal_statement: { value: " Complete the application " },
    value_minor: { value: " 50000 " },
    currency: { value: " USD " },
  };
  const button = { disabled: false };
  const status = { textContent: "" };
  let resets = 0;
  const form = {
    elements: { namedItem: (name) => fields[name] || null },
    querySelector: (selector) => selector === 'button[type="submit"]' ? button : status,
    reset() { resets += 1; },
  };
  const calls = [];
  sandbox.fetch = async (path, init) => {
    calls.push({ path, init });
    return { ok: true, status: 200, json: async () => ({ opportunity_id: MONEY_OPPORTUNITY_ID, job_ref: MONEY_JOB_REF, status: "DISCOVERED" }) };
  };
  let reloads = 0;
  sandbox.loadPanelSection = async (name) => { assert.equal(name, "money-printer"); reloads += 1; };

  await submit(form);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, "/api/panel/money-printer/opportunity");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.credentials, "same-origin");
  assert.equal(calls[0].init.headers["x-lm-csrf"], "page-csrf");
  assert.equal(calls[0].init.headers["idempotency-key"], "request-uuid");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    source_url: "https://work.example/job",
    title: "Paid work",
    goal_statement: "Complete the application",
    value_minor: "50000",
    currency: "USD",
  });
  assert.equal(resets, 1);
  assert.equal(reloads, 1);
  assert.equal(status.textContent, "Opportunity added");
  assert.equal(button.disabled, false);
});

test("Money Printer workroom validator rejects foreign or invalid payloads", () => {
  const { validate } = emittedMoneyPrinterWorkroom();
  assert.equal(typeof validate, "function");
  assert.doesNotThrow(() => validate(moneyWorkroomData(), MONEY_OPPORTUNITY_REF));
  for (const invalid of [
    { ...moneyWorkroomData(), opportunity_id: "b".repeat(64) },
    { ...moneyWorkroomData(), job_ref: `runtime-job://tenant-b/goal%3A${MONEY_OPPORTUNITY_ID}` },
    { ...moneyWorkroomData(), activity: [{ ...moneyWorkroomData().activity[0], private_ref: "must-not-pass" }] },
  ]) {
    assert.throws(() => validate(invalid, MONEY_OPPORTUNITY_REF), /invalid workroom payload/);
  }
});

test("Money Printer workroom validator accepts nullable currency and source URL", () => {
  const { validate } = emittedMoneyPrinterWorkroom();
  assert.doesNotThrow(() => validate({ ...moneyWorkroomData(), currency: null, source_url: null }, MONEY_OPPORTUNITY_REF));
});

test("Money Printer workroom validator rejects mixed workrooms and malformed activity refs", () => {
  const { validate } = emittedMoneyPrinterWorkroom();
  const activity = (kind, ref, extra = {}) => ({ kind, ref, status: "running", observed_at: MONEY_OBSERVED_AT, ...extra });
  for (const invalid of [
    { ...moneyWorkroomData(), activity: [activity("opportunity", OTHER_OPPORTUNITY_REF)] },
    { ...moneyWorkroomData(), activity: [activity("work", OTHER_JOB_REF)] },
    { ...moneyWorkroomData(), activity: [activity("human_task", HUMAN_TASK_REF)] },
    { ...moneyWorkroomData(), activity: [activity("work", "runtime-job://tenant-a/goal%GG")] },
    { ...moneyWorkroomData(), activity: [activity("artifact", "artifact://tenant-a/artifact-1")] },
  ]) {
    assert.throws(() => validate(invalid, MONEY_OPPORTUNITY_REF), /invalid workroom payload/);
  }
});

test("Money Printer card loader fetches one same-origin workroom and renders safe activity", async () => {
  const { load, sandbox } = emittedMoneyPrinterWorkroom();
  assert.equal(typeof load, "function");
  const workroom = { innerHTML: "", querySelector: () => null };
  const section = { querySelector: (selector) => { assert.equal(selector, "[data-money-workroom]"); return workroom; } };
  const button = {
    dataset: { moneyOpportunityId: MONEY_OPPORTUNITY_ID, moneyOpportunityRef: MONEY_OPPORTUNITY_REF },
    closest: (selector) => { assert.equal(selector, '[data-panel-section="money-printer"]'); return section; },
  };
  const calls = [];
  sandbox.fetch = async (path, init) => {
    calls.push({ path, init });
    return { ok: true, status: 200, json: async () => moneyWorkroomData() };
  };

  await load(button);

  assert.deepEqual(calls, [{
    path: `/api/panel/money-printer/workroom?opportunity_id=${MONEY_OPPORTUNITY_ID}`,
    init: { method: "GET", credentials: "same-origin", headers: { Accept: "application/json" } },
  }]);
  assert.match(workroom.innerHTML, /Selected workroom/);
  assert.match(workroom.innerHTML, /WORKING/);
  assert.match(workroom.innerHTML, /opportunity/);
  assert.match(workroom.innerHTML, /runtime-job:\/\/tenant-a\/goal%3A/);
});

test("Money Printer card loader keeps the latest workroom response when an older request resolves late", async () => {
  const { load, sandbox } = emittedMoneyPrinterWorkroom();
  assert.equal(typeof load, "function");
  const workroom = { innerHTML: "", querySelector: () => null };
  const section = { querySelector: (selector) => { assert.equal(selector, "[data-money-workroom]"); return workroom; } };
  const button = (opportunityRef, opportunityId) => ({
    dataset: { moneyOpportunityId: opportunityId, moneyOpportunityRef: opportunityRef },
    closest: (selector) => { assert.equal(selector, '[data-panel-section="money-printer"]'); return section; },
  });
  const pending = [];
  sandbox.fetch = async (path, init) => new Promise((resolve) => pending.push({ path, init, resolve }));
  const first = load(button(MONEY_OPPORTUNITY_REF, MONEY_OPPORTUNITY_ID));
  const second = load(button(OTHER_OPPORTUNITY_REF, OTHER_OPPORTUNITY_ID));
  assert.equal(pending.length, 2);
  pending[1].resolve({ ok: true, status: 200, json: async () => moneyWorkroomData({
    opportunity_id: OTHER_OPPORTUNITY_ID,
    job_ref: OTHER_JOB_REF,
    title: "B workroom",
    activity: [
      { kind: "opportunity", ref: OTHER_OPPORTUNITY_REF, status: "WORKING", observed_at: MONEY_OBSERVED_AT },
      { kind: "work", ref: OTHER_JOB_REF, status: "running", observed_at: MONEY_OBSERVED_AT },
    ],
  }) });
  await second;
  assert.match(workroom.innerHTML, /B workroom/);
  pending[0].resolve({ ok: true, status: 200, json: async () => moneyWorkroomData() });
  await first;
  assert.match(workroom.innerHTML, /B workroom/);
  assert.doesNotMatch(workroom.innerHTML, /<h3>Selected workroom<\/h3>/);
});

test("Money Printer panel embeds focused WebMCP tools with only page CSRF for the write header", () => {
  const html = renderPanelPage({ csrf: "csrf-value" });
  const scripts = [...html.matchAll(/<script>\s*([\s\S]*?)\s*<\/script>/g)].map((match) => match[1]);
  const webmcp = scripts.find((script) => script.includes("document.modelContext.registerTool"));
  assert.ok(webmcp);
  assert.match(webmcp, /document\.modelContext\.registerTool\(/);
  assert.match(webmcp, /\/api\/panel\/money-printer/);
  assert.match(webmcp, /add_opportunity/);
  assert.match(webmcp, /inspect_workroom/);
  assert.match(webmcp, /csrf-value/);
  assert.match(webmcp, /x-lm-csrf/);
  assert.match(webmcp, /idempotency-key/);
  assert.doesNotMatch(webmcp, /authorization|bearer/i);
});

test("WebMCP judge guest uses the same Money Printer section without owner controls", () => {
  const html = renderPanelPage({ csrf: "csrf-value", guest: true });
  assert.match(html, /data-guest-mode/);
  assert.match(html, /Judge guest — isolated workroom/);
  assert.match(html, /real cloud agent/);
  assert.match(html, /data-panel-section="money-printer"/);
  assert.match(html, /\/api\/panel\/money-printer/);
  const main = html.match(/<main class="panel-grid">[\s\S]*?<\/main>/)?.[0] || "";
  const endpointBlock = html.match(/const panelEndpoints = Object\.freeze\(\{[\s\S]*?\}\);/)?.[0] || "";
  for (const section of ["timeline", "scores", "ledger", "gates", "settings", "control-center"]) {
    assert.doesNotMatch(main, new RegExp(`data-panel-section="${section}"`));
  }
  for (const endpoint of ["timeline", "scores", "ledger", "gates", "settings", "control-center"]) {
    assert.doesNotMatch(endpointBlock, new RegExp(`/api/panel/${endpoint}`));
  }
  assert.doesNotMatch(html, /action="\/panel\/logout"|>Logout</);
  assert.doesNotMatch(html, /PERSONAL CONTROL CENTER|あなたの状態と接続だけを表示しています/);
});

test("PANEL-0: panel includes a real control center and keeps read APIs same-origin", () => {
  assert.equal(typeof renderPanelPage, "function");
  const html = renderPanelPage();
  assert.match(html, /data-panel-section="control-center"/);
  assert.match(html, /id="connection-cards"/);
  assert.match(html, /id="settings-controls"/);
  assert.match(html, /<button\b/i);
  assert.match(html, /credentials:\s*["']same-origin["']/);
  for (const endpoint of ["timeline", "scores", "ledger", "gates", "settings"]) {
    assert.match(html, new RegExp(`/api/panel/${endpoint}`));
  }
  assert.match(html, /insufficient data/);
  assert.match(html, /まだ収支の記録はありません/);
});

test("PANEL-8h: emitted renderers accept only projected timeline and ledger DTO fields", () => {
  const html = renderPanelPage();
  assert.match(html, /validateTimelineData\(data\)/);
  assert.match(html, /data\.items/);
  assert.match(html, /validateLedgerData\(data\)/);
  assert.match(html, /data\.financial\.items\.concat\(data\.api_cost\.items\)/);
  assert.match(html, /displaySafeLink\(entry\.link\)/);
  assert.doesNotMatch(html, /data\.events|data\.calls|financial\.entries/);
  assert.doesNotMatch(html, /url\.protocol === "http:"/);
});

test("PANEL-8h: emitted loader applies closed validators and shared secret patterns before display", () => {
  const html = renderPanelPage();
  for (const validator of [
    "validateTimelineData",
    "validateLedgerData",
    "validateGatesData",
    "validateSettingsData",
    "validateControlCenterData",
  ]) {
    assert.match(html, new RegExp(`${validator}\\(data\\)`));
  }
  assert.match(html, /displaySecretPatterns/);
  assert.match(html, /displayContainsSensitiveValue\(data\)/);
  assert.match(html, /if \(!response\.ok\) throw new Error\(name \+ " unavailable"\)/);
  assert.match(html, /money-printer:refresh/);
  assert.match(html, /loadPanelSection\("money-printer"\)/);
  assert.doesNotMatch(html, /response\.statusText|response\.text\(\)|JSON\.stringify\(data\)/);
});

function emittedLedgerBrowser() {
  const html = renderPanelPage();
  const script = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const sharedStart = script.indexOf("const panelEndpoints = Object.freeze(");
  const sharedEnd = script.indexOf("function validateTimelineData(data)", sharedStart);
  const ledgerStart = script.indexOf("function validLedgerItem(item)");
  const ledgerEnd = script.indexOf("function validateGatesData(data)", ledgerStart);
  const renderStart = script.indexOf("function renderLedger(data)");
  const renderEnd = script.indexOf("const gateLabels", renderStart);
  const loadStart = script.indexOf("async function loadPanelSection(name)");
  const loadEnd = script.indexOf("let moneyPrinterRefresh", loadStart);
  assert.ok(sharedStart >= 0 && sharedEnd > sharedStart);
  assert.ok(ledgerStart >= 0 && ledgerEnd > ledgerStart);
  assert.ok(renderStart >= 0 && renderEnd > renderStart);
  assert.ok(loadStart >= 0 && loadEnd > loadStart);

  let responseBody = null;
  let rendered = null;
  const requests = [];
  const sandbox = {
    URL,
    fetch: async (path, options) => {
      requests.push({ path, options });
      return { ok: true, status: 200, json: async () => responseBody };
    },
    markLoaded: (name, body) => { rendered = { name, body }; },
    window: { location: { reload() {} } },
  };
  const source = [
    script.slice(sharedStart, sharedEnd),
    script.slice(ledgerStart, ledgerEnd),
    script.slice(renderStart, renderEnd),
    "const renderers = Object.freeze({ ledger: renderLedger });",
    script.slice(loadStart, loadEnd),
    "globalThis.__validateLedgerData = validateLedgerData; globalThis.__loadPanelSection = loadPanelSection;",
  ].join("\n");
  vm.runInNewContext(source, sandbox);
  return {
    validate: (data) => sandbox.__validateLedgerData(data),
    async load(data) {
      responseBody = data;
      rendered = null;
      await sandbox.__loadPanelSection("ledger");
      return { ...rendered, request: requests.at(-1) };
    },
  };
}

function task2LedgerDto() {
  return {
    api_cost: {
      no_data: true,
      total: "金額不明",
      estimate_status: "unknown",
      unknown_estimate_entries: 0,
      actual_status: "unknown",
      unknown_actual_entries: 0,
      items: [],
      periods: {
        daily: {
          status: "available",
          period_start: "2026-10-06T15:00:00.000Z",
          period_end: "2026-10-07T15:00:00.000Z",
          counts: {
            event_count: 9,
            request_count: 2,
            cache_hit_count: 1,
            cache_miss_count: 8,
            estimated_event_count: 5,
            settled_event_count: 6,
            unknown_estimate_event_count: 4,
            unknown_actual_event_count: 3,
            not_applicable_count: 0,
          },
          groups: [
            {
              loop_id: "test.loop", owner_id: "test-owner", trace_status: "linked",
              linked_trace_event_count: 2, partial_trace_event_count: 0, unlinked_trace_event_count: 0,
              distinct_run_count: 1, distinct_occurrence_count: 1, distinct_release_count: 1,
              latest_trace: { run_id: "run-test", occurrence_id: "test.loop:occ-1", release_sha: "a".repeat(40) },
              provider: "OpenAI", sku: "gpt-test", operation: "responses", unit: "request",
              event_count: 2, request_count: 2, cache_hit_count: 0, cache_miss_count: 2,
              provider_units: "2", estimated_cost_usd: "0.00000001", settled_cost_usd: "0.000000005",
              estimate_status: "estimated", actual_status: "settled",
              unknown_estimate_event_count: 0, unknown_actual_event_count: 0, not_applicable_count: 0,
            },
            {
              loop_id: "test.loop", owner_id: "test-owner", trace_status: "partial",
              linked_trace_event_count: 0, partial_trace_event_count: 2, unlinked_trace_event_count: 0,
              distinct_run_count: 2, distinct_occurrence_count: 2, distinct_release_count: 0,
              latest_trace: { run_id: "run-partial", occurrence_id: "test.loop:occ-2", release_sha: null },
              provider: "DeepSeek", sku: "flash-test", operation: "completion", unit: "tokens",
              event_count: 2, request_count: 0, cache_hit_count: 0, cache_miss_count: 2,
              provider_units: "256", estimated_cost_usd: null, settled_cost_usd: "0.0000005",
              estimate_status: "unknown", actual_status: "settled",
              unknown_estimate_event_count: 2, unknown_actual_event_count: 0, not_applicable_count: 0,
            },
            {
              loop_id: "test.loop", owner_id: "test-owner", trace_status: "partial",
              linked_trace_event_count: 1, partial_trace_event_count: 1, unlinked_trace_event_count: 2,
              distinct_run_count: 1, distinct_occurrence_count: 1, distinct_release_count: 1,
              latest_trace: { run_id: "run-mixed", occurrence_id: "test.loop:occ-3", release_sha: "b".repeat(40) },
              provider: "Google", sku: "grounded-test", operation: "ground", unit: "grounded_prompt",
              event_count: 4, request_count: 0, cache_hit_count: 1, cache_miss_count: 3,
              provider_units: "10.5", estimated_cost_usd: "0.0000000123", settled_cost_usd: "0.00000009",
              estimate_status: "partial", actual_status: "partial",
              unknown_estimate_event_count: 1, unknown_actual_event_count: 2, not_applicable_count: 0,
            },
            {
              loop_id: "unattributed", owner_id: "unattributed", trace_status: "unlinked",
              linked_trace_event_count: 0, partial_trace_event_count: 0, unlinked_trace_event_count: 1,
              distinct_run_count: 0, distinct_occurrence_count: 0, distinct_release_count: 0,
              latest_trace: null,
              provider: "Anthropic", sku: "unknown-test", operation: "completion", unit: "seconds_proxy",
              event_count: 1, request_count: 0, cache_hit_count: 0, cache_miss_count: 1,
              provider_units: "5.2", estimated_cost_usd: null, settled_cost_usd: null,
              estimate_status: "unknown", actual_status: "unknown",
              unknown_estimate_event_count: 1, unknown_actual_event_count: 1, not_applicable_count: 0,
            },
          ],
        },
        monthly: {
          status: "verified_empty",
          period_start: "2026-10-01T15:00:00.000Z",
          period_end: "2026-10-07T15:00:00.000Z",
          counts: {
            event_count: 0,
            request_count: 0,
            cache_hit_count: 0,
            cache_miss_count: 0,
            estimated_event_count: 0,
            settled_event_count: 0,
            unknown_estimate_event_count: 0,
            unknown_actual_event_count: 0,
            not_applicable_count: 0,
          },
          groups: [],
        },
      },
    },
    financial: { no_data: true, items: [] },
    reports: { daily: null, weekly: null },
  };
}

function emittedPanelActionCommand() {
  const script = renderPanelPage().match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const start = script.indexOf("function commandForAction(action, button)");
  const end = script.indexOf("async function runControlAction(button)", start);
  assert.ok(start >= 0 && end > start);
  const sandbox = { window: { location: {} } };
  vm.runInNewContext(`${script.slice(start, end)}\nglobalThis.__commandForAction = commandForAction;`, sandbox);
  return sandbox.__commandForAction;
}

test("PANEL-A5: browser accepts the Task 2 ledger DTO and renders separate daily/monthly cost tables", async () => {
  const browser = emittedLedgerBrowser();
  const result = await browser.load(task2LedgerDto());

  assert.equal(result.name, "ledger");
  assert.equal(result.request.path, "/api/panel/ledger");
  assert.equal(result.request.options.credentials, "same-origin");
  assert.equal(result.request.options.headers.Accept, "application/json");
  assert.match(result.body, /data-api-cost-period="daily"/);
  assert.match(result.body, /data-api-cost-period="monthly"/);
  assert.equal((result.body.match(/<table/g) || []).length, 2);
  for (const label of ["今日", "今月", "OpenAI", "gpt-test", "responses", "request", "DeepSeek", "Google", "Anthropic"]) {
    assert.ok(result.body.includes(label), `rendered ledger should include ${label}`);
  }
  assert.match(result.body, /USD 0\.00000001/);
  assert.match(result.body, /USD 0\.000000005/);
  assert.match(result.body, /推定 一部未確認/);
  assert.match(result.body, /確定 一部未確認/);
  assert.match(result.body, /確定済み/);
  assert.match(result.body, /未確認/);
  assert.match(result.body, /記録なし（照会済み）/);
  assert.doesNotMatch(result.body, /USD 0\.00000000(?![0-9])/);
  assert.match(result.body, /警告閾値: 未設定（A6で設定予定）/);
});

test("PANEL-A5: browser renders normalized unknown SKU as 未確認", async () => {
  const browser = emittedLedgerBrowser();
  const dto = task2LedgerDto();
  dto.api_cost.periods.daily.groups[3].sku = "unknown";

  const result = await browser.load(dto);

  assert.match(result.body, /<td>Anthropic<\/td><td>未確認<\/td><td>completion<\/td>/);
  assert.doesNotMatch(result.body, /<td>Anthropic<\/td><td>unknown<\/td>/);
});

test("PANEL-A5: generated browser accepts auth-json and rejects auth.json trace IDs", () => {
  const browser = emittedLedgerBrowser();
  const dto = task2LedgerDto();
  const group = dto.api_cost.periods.daily.groups[0];
  group.loop_id = "auth-json";
  group.latest_trace.run_id = "run-auth-json";
  group.latest_trace.occurrence_id = "auth-json:occ-1";

  assert.doesNotThrow(() => browser.validate(dto));

  const unsafe = structuredClone(dto);
  unsafe.api_cost.periods.daily.groups[0].loop_id = "auth.json";
  assert.throws(() => browser.validate(unsafe), /invalid ledger payload/);
});

test("PANEL-A5: browser renders loop/owner grouping and newest trace", async () => {
  const browser = emittedLedgerBrowser();
  const dto = task2LedgerDto();
  const groups = dto.api_cost.periods.daily.groups;
  groups[0] = {
    ...groups[0], loop_id: "managed.loop", owner_id: "owner-alpha", trace_status: "linked",
    linked_trace_event_count: 2, partial_trace_event_count: 0, unlinked_trace_event_count: 0,
    distinct_run_count: 1, distinct_occurrence_count: 1, distinct_release_count: 1,
    latest_trace: { run_id: "run-current", occurrence_id: "managed.loop:occ-1", release_sha: "a".repeat(40) },
  };
  groups[1] = {
    ...groups[1], loop_id: "managed.loop", owner_id: "owner-partial", trace_status: "partial",
    linked_trace_event_count: 0, partial_trace_event_count: 2, unlinked_trace_event_count: 0,
    distinct_run_count: 2, distinct_occurrence_count: 2, distinct_release_count: 0,
    latest_trace: { run_id: "run-partial", occurrence_id: "managed.loop:occ-2", release_sha: null },
  };
  groups[2] = {
    ...groups[2], loop_id: "managed.loop", owner_id: "owner-mixed", trace_status: "partial",
    linked_trace_event_count: 1, partial_trace_event_count: 1, unlinked_trace_event_count: 2,
    distinct_run_count: 1, distinct_occurrence_count: 1, distinct_release_count: 1,
    latest_trace: { run_id: "run-mixed", occurrence_id: "managed.loop:occ-3", release_sha: "b".repeat(40) },
  };
  groups[3] = {
    ...groups[3], loop_id: "unattributed", owner_id: "unattributed", trace_status: "unlinked",
    linked_trace_event_count: 0, partial_trace_event_count: 0, unlinked_trace_event_count: 1,
    distinct_run_count: 0, distinct_occurrence_count: 0, distinct_release_count: 0,
    latest_trace: null,
  };

  const result = await browser.load(dto);

  assert.match(result.body, /<th>Loop<\/th><th>Owner<\/th>/);
  assert.match(result.body, /managed\.loop/);
  assert.match(result.body, /owner-alpha/);
  assert.match(result.body, /run-current/);
  assert.match(result.body, /managed\.loop:occ-1/);
  assert.match(result.body, /a{40}/);
  assert.match(result.body, /run ID 1件・occurrence ID 1件・release SHA 1件/);
  assert.match(result.body, /run ID 2件・occurrence ID 2件・release SHA 0件/);
  assert.match(result.body, /<td>managed\.loop<\/td><td>owner-partial<\/td>/);
  assert.match(result.body, /一部未確認/);
  assert.match(result.body, /未紐付け/);
  assert.match(result.body, /unattributed/);
  assert.match(result.body, /トレース未確認/);

  const unsafe = structuredClone(dto);
  unsafe.api_cost.periods.daily.groups[0].latest_trace.run_id = "<img src=x onerror=alert(1)>";
  assert.throws(() => browser.validate(unsafe), /invalid ledger payload/);
});

test("PANEL-A5: unavailable summaries stay unknown and the unset warning threshold leaves travel/Calendar actions available", async () => {
  const browser = emittedLedgerBrowser();
  const dto = task2LedgerDto();
  dto.api_cost.periods.daily = {
    ...dto.api_cost.periods.daily,
    status: "unavailable",
    counts: null,
    groups: null,
  };
  const result = await browser.load(dto);
  assert.match(result.body, /集計を取得できません/);
  assert.match(result.body, /金額と利用量は未確認です/);
  assert.doesNotMatch(result.body, /data-api-cost-period="daily"[\s\S]*?event_count[^<]*0/);
  assert.match(result.body, /警告閾値: 未設定（A6で設定予定）/);

  const commandForAction = emittedPanelActionCommand();
  assert.deepEqual(commandForAction("connect-calendar", {}), { type: "connection.start", provider: "calendar" });
  assert.deepEqual(commandForAction("wake_policy", { value: "travel-only" }), {
    type: "setting.set", setting: "wake_policy", value: "travel-only",
  });
  assert.match(renderPanelPage(), /data-panel-section="timeline"/);
});

test("PANEL-A5: browser ledger validator rejects malformed summary keys, states, and cost values", () => {
  const browser = emittedLedgerBrowser();
  for (const mutate of [
    (dto) => { dto.api_cost.periods.daily.unprojected = true; },
    (dto) => { dto.api_cost.periods.daily.status = "zero_by_default"; },
    (dto) => { dto.api_cost.periods.daily.groups[0].estimated_cost_usd = "NaN"; },
    (dto) => { dto.api_cost.periods.daily.groups[0].actual_status = "unknown"; },
  ]) {
    const invalid = structuredClone(task2LedgerDto());
    mutate(invalid);
    assert.throws(() => browser.validate(invalid), /invalid ledger payload/);
  }
});

test("PANEL-8h: money-printer refresh rejects failed reloads and recovers on the next refresh", async () => {
  const html = renderPanelPage();
  const script = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
  const start = script.indexOf("let moneyPrinterRefresh = Promise.resolve();");
  const end = script.indexOf("\n    function commandForAction", start);
  assert.ok(start >= 0 && end > start);

  let listener = null;
  let phase = "success";
  let loads = 0;
  const errors = [];
  vm.runInNewContext(script.slice(start, end), {
    Promise,
    console: { error() {} },
    document: {
      addEventListener(name, callback) {
        if (name === "money-printer:webmcp-call") return;
        assert.equal(name, "money-printer:refresh");
        listener = callback;
      },
    },
    loadPanelSection: async (name) => {
      assert.equal(name, "money-printer");
      loads += 1;
      if (phase === "fail") throw new Error("reload failed");
    },
    markError: (name) => errors.push(name),
  });
  assert.equal(typeof listener, "function");

  const first = { detail: {} };
  listener(first);
  await first.detail.promise;
  assert.equal(loads, 1);

  phase = "fail";
  const failed = { detail: {} };
  listener(failed);
  await assert.rejects(failed.detail.promise, /reload failed/);
  assert.equal(loads, 2);
  assert.deepEqual(errors, ["money-printer"]);

  phase = "success";
  const recovered = { detail: {} };
  listener(recovered);
  await recovered.detail.promise;
  assert.equal(loads, 3);
});

test("PANEL-0: visible actions have semantic delegated handlers", () => {
  const html = renderPanelPage();
  assert.match(html, /addEventListener\("click"/);
  assert.match(html, /addEventListener\("change"/);
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /min-height:\s*44px/);
  assert.doesNotMatch(html, /<span[^>]+data-action=/);
  for (const action of ["connect-calendar", "toggle-calls", "toggle-notifications", "toggle-daily", "toggle-delegation", "instructions-location", "instructions-wallet", "instructions-call"]) {
    assert.match(html, new RegExp(`case ["']${action}["']`));
  }
});

test("PANEL-0: Calendar renders native Disconnect and Reconnect controls", () => {
  const html = renderPanelPage();
  assert.match(html, /connection\.disconnect/);
  assert.match(html, /disconnect-calendar/);
  assert.match(html, /Reconnect calendar/);
  assert.match(html, /case "disconnect-calendar": return \{ type: "connection\.disconnect", provider: "calendar" \}/);
});

test("#1085: Calendar connect action is rendered as Connect Calendar", () => {
  const html = renderPanelPage();
  assert.match(html, /item && item\.actionLabel === "Reconnect calendar" \? "Reconnect calendar" : "Connect Calendar"/);
  assert.doesNotMatch(html, /item && item\.actionLabel === "Reconnect calendar" \? "Reconnect calendar" : "Connect calendar"/);
});

test("LM-33c: panel CSS collapses to one column without horizontal overflow at 375px", () => {
  assert.equal(typeof renderPanelPage, "function");
  const html = renderPanelPage();
  assert.match(html, /@media\s*\(max-width:\s*640px\)/);
  assert.match(html, /grid-template-columns:\s*1fr/);
  assert.match(html, /overflow-x:\s*hidden/);
  assert.match(html, /overflow-wrap:\s*anywhere/);
});

test("LM-33c: panel provides an inline favicon without an extra failing request", () => {
  assert.equal(typeof renderPanelPage, "function");
  assert.match(renderPanelPage(), /<link rel="icon" href="data:image\/svg\+xml,/);
});

test("PANEL-8g: score cards render all four outcome organs, exact insufficient data, reasons, periods, components, and linkage", () => {
  const html = renderPanelPage();
  assert.match(html, />4 organ スコア</);
  for (const name of ["daily", "physical", "mental", "financial"]) assert.match(html, new RegExp(`${name}: ["']${name.toUpperCase()}["']`));
  assert.match(html, /insufficient data/);
  assert.match(html, /organ\.reason/);
  assert.match(html, /organ\.period/);
  assert.match(html, /organ\.numerator/);
  assert.match(html, /organ\.denominator/);
  assert.match(html, /organ\.components/);
  assert.match(html, /source_outcome_ids/);
  assert.doesNotMatch(html, /organ\.score|organ\.no_data|organ\.calls|organ\.answered|organ\.ledger_entries/);
});

test("PANEL-8g: malformed score payloads fail the score section closed without NaN or raw JSON", () => {
  const html = renderPanelPage();
  assert.match(html, /validScoreOrgan/);
  assert.match(html, /throw new Error\(["']invalid score payload["']\)/);
  assert.doesNotMatch(html, /JSON\.stringify\(organ/);
  assert.doesNotMatch(html, />NaN</);
});

test("PANEL-8g: executable score renderer shows measured, insufficient, invalid, reason, period, components, and source count", () => {
  assert.equal(typeof renderScoreCards, "function");
  const period = (kind) => ({ kind, start_at: "2026-07-08T12:00:00.000Z", end_at: "2026-07-15T12:00:00.000Z" });
  const html = renderScoreCards({ organs: {
    daily: { status: "measured", value: 50, period: period("rolling_7_days"), numerator: 1, denominator: 2, reason: "Resolved one of two.", source_outcome_ids: ["outcome:10000000-0000-4000-8000-000000000001"], components: { timezone: "UTC", excluded_unknown_count: 0, eligible_events: 2, resolved_events: 1, required_succeeded: 1, required_failed: 1, required_pending: 0, context_unnecessary: 0, optional_ignored: 0 } },
    physical: { status: "insufficient_data", value: null, period: period("rolling_30_days"), numerator: 0, denominator: 0, reason: "No overdue needs.", source_outcome_ids: [], components: { timezone: "UTC", excluded_unknown_count: 0, detected_needs: 0, confirmed_booking: 0, confirmed_completion: 0, unresolved_needs: 0, search_candidate_unconfirmed: 0 } },
    mental: { status: "invalid_data", value: null, period: period("rolling_7_days"), numerator: null, denominator: null, reason: "Invalid mental data.", source_outcome_ids: [], components: { timezone: "UTC", excluded_unknown_count: 0, deduplicated_triggers: 0, delivered_within_cap: 0, suppression_honored: 0, correction_persisted: 0, cap_overflow: 0, unresolved_triggers: 0 } },
    financial: { status: "measured", value: 70, period: period("calendar_month"), numerator: 700, denominator: 1000, reason: "Net verified income.", source_outcome_ids: ["outcome:10000000-0000-4000-8000-000000000001"], components: { timezone: "UTC", excluded_unknown_count: 0, currency: "USD", gross_income_minor: 1000, realized_loss_minor: 200, fee_minor: 100, user_transfer_minor: 0, excluded_rows: 0, net_clamped: false } },
  } });
  assert.match(html, /50<small>\/100/);
  assert.match(html, /insufficient data/);
  assert.match(html, /invalid data/);
  assert.match(html, /Resolved one of two\./);
  assert.match(html, /rolling 7 days/);
  assert.match(html, /対応できた予定/);
  assert.doesNotMatch(html, /resolved events/);
  assert.match(html, /根拠 1件/);
  assert.equal((html.match(/data-score-organ=/g) || []).length, 4);
});

test("PANEL-8g: executable score renderer rejects a missing organ instead of rendering NaN or a fake score", () => {
  assert.equal(typeof renderScoreCards, "function");
  assert.throws(() => renderScoreCards({ organs: {} }), /invalid score payload/);
});

test("PANEL-8g: executable score renderer rejects malformed period kinds and non-UUID source references", () => {
  const invalid = { status: "insufficient_data", value: null, period: { kind: "anything", start_at: "2026-07-08T12:00:00.000Z", end_at: "2026-07-15T12:00:00.000Z" }, numerator: 0, denominator: 0, reason: "No outcomes.", source_outcome_ids: ["outcome:------------------------------------"], components: { timezone: "UTC" } };
  assert.throws(() => renderScoreCards({ organs: { daily: invalid, physical: invalid, mental: invalid, financial: invalid } }), /invalid score payload/);
});

test("PANEL-8g: executable score renderer rejects contradictory ratios, duplicate refs, incomplete components, non-ISO periods, and extra organs", () => {
  const ref = "outcome:10000000-0000-4000-8000-000000000001";
  const periods = { daily: "rolling_7_days", physical: "rolling_30_days", mental: "rolling_7_days", financial: "calendar_month" };
  const components = {
    daily: { timezone: "UTC", excluded_unknown_count: 0, eligible_events: 1, resolved_events: 1, required_succeeded: 1, required_failed: 0, required_pending: 0, context_unnecessary: 0, optional_ignored: 0 },
    physical: { timezone: "UTC", excluded_unknown_count: 0, detected_needs: 1, confirmed_booking: 1, confirmed_completion: 0, unresolved_needs: 0, search_candidate_unconfirmed: 0 },
    mental: { timezone: "UTC", excluded_unknown_count: 0, deduplicated_triggers: 1, delivered_within_cap: 1, suppression_honored: 0, correction_persisted: 0, cap_overflow: 0, unresolved_triggers: 0 },
    financial: { timezone: "UTC", excluded_unknown_count: 0, currency: "USD", gross_income_minor: 100, realized_loss_minor: 0, fee_minor: 0, user_transfer_minor: 0, excluded_rows: 0, net_clamped: false },
  };
  const organ = (name) => ({ status: "measured", value: 100, period: { kind: periods[name], start_at: "2026-07-08T12:00:00.000Z", end_at: "2026-07-15T12:00:00.000Z" }, numerator: name === "financial" ? 100 : 1, denominator: name === "financial" ? 100 : 1, reason: "Measured.", source_outcome_ids: [ref], components: components[name] });
  const valid = { daily: organ("daily"), physical: organ("physical"), mental: organ("mental"), financial: organ("financial") };
  assert.doesNotThrow(() => renderScoreCards({ organs: valid }));
  assert.throws(() => renderScoreCards({ organs: valid, extra: true }), /invalid score payload/);
  for (const mutate of [
    (organs) => { organs.daily = { ...organs.daily, numerator: 0 }; },
    (organs) => { organs.daily = { ...organs.daily, source_outcome_ids: [ref, ref] }; },
    (organs) => { organs.mental = { ...organs.mental, components: { timezone: "UTC" } }; },
    (organs) => { organs.daily = { ...organs.daily, period: { ...organs.daily.period, start_at: 0 } }; },
    (organs) => { organs.daily = { ...organs.daily, period: { ...organs.daily.period, start_at: "2026-02-30T12:00:00.000Z" } }; },
    (organs) => { organs.extra = organs.daily; },
  ]) {
    const organs = structuredClone(valid);
    mutate(organs);
    assert.throws(() => renderScoreCards({ organs }), /invalid score payload/);
  }
});

test("PANEL-8g: score renderer accepts the integer-safe FINANCIAL ratio emitted by the server core", () => {
  const organs = safeIntegerFinancialOrgans();
  assert.equal(roundedScoreValue(organs.financial.numerator, organs.financial.denominator), 10);
  assert.doesNotThrow(() => renderScoreCards({ organs }));
});

test("PANEL-8g: emitted browser score renderer accepts the integer-safe FINANCIAL core value", () => {
  const organs = safeIntegerFinancialOrgans();
  assert.equal(roundedScoreValue(organs.financial.numerator, organs.financial.denominator), 10);
  assert.doesNotThrow(() => emittedScoreRenderer()({ organs }));
});
