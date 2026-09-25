#!/usr/bin/env node
"use strict";

// Read-only discovery CLI. Answers "what did the provider show, and why did
// each event pass or fail?" for a single wake-shaped discovery pass, without
// registering for anything. See skills/connector/test/discover.test.js for
// the pure-function coverage (arg parsing, row/table formatting, totals).

const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const { loadConnectorEnv } = require("./lib/load-connector-env.js");
const { createLumaScriptFirstWorkflow } = require("../../apps/life-manager/lib/connector-luma-workflow.js");
const { createConnpassScriptFirstWorkflow } = require("../../apps/life-manager/lib/connector-connpass-workflow.js");
const { createProductionCalendarReader } = require("../../apps/life-manager/lib/connector-minimal-production.js");

const TOKYO_TZ = "Asia/Tokyo";
const BROWSER_GUARD_BIN = path.resolve(__dirname, "../browser/browser-guard.sh");
const BROWSER_IDENTITY = "interactive:dais";

function invalid(message) {
  throw new Error(message || "Connector discover unavailable");
}

function validBrowserBaseUrl(value) {
  let parsed;
  try { parsed = new URL(String(value || "")); } catch { invalid("browser endpoint invalid"); }
  if (
    parsed.protocol !== "http:"
    || !["127.0.0.1", "localhost", "[::1]"].includes(parsed.hostname)
    || !parsed.port || parsed.pathname !== "/"
    || parsed.username || parsed.password || parsed.search || parsed.hash
  ) invalid("browser endpoint invalid");
  return parsed.origin;
}

// ---------------------------------------------------------------------------
// Pure functions (covered by skills/connector/test/discover.test.js — no
// browser, no network, no filesystem).
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const list = Array.isArray(argv) ? argv : [];
  let provider = null;
  let json = false;
  for (let i = 0; i < list.length; i += 1) {
    const token = list[i];
    if (token === "--json") { json = true; continue; }
    if (token === "--provider") { i += 1; provider = list[i]; continue; }
    invalid(`Unknown argument: ${token}`);
  }
  if (provider !== "luma" && provider !== "connpass") {
    invalid("Usage: discover.js --provider luma|connpass [--json]");
  }
  return Object.freeze({ provider, json });
}

function tokyoParts(iso) {
  const instant = new Date(String(iso));
  if (!Number.isFinite(instant.getTime())) invalid("Connector discover date invalid");
  const dateText = new Intl.DateTimeFormat("en-CA", {
    timeZone: TOKYO_TZ, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(instant);
  const timeText = new Intl.DateTimeFormat("en-GB", {
    timeZone: TOKYO_TZ, hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(instant);
  return Object.freeze({ date: dateText, time: timeText });
}

function formatTokyoRange(startsAtIso, endsAtIso) {
  const start = tokyoParts(startsAtIso);
  const end = tokyoParts(endsAtIso);
  return Object.freeze({ date: start.date, start: start.time, end: end.time });
}

// Mirrors defaultCalendarFree()'s overlap condition in
// apps/life-manager/lib/{connector-luma-workflow,connector-connpass-workflow}.js
// byte-for-byte (that predicate is not exported, and is itself already
// duplicated verbatim across those two files). Used only as the discover
// CLI's isCalendarFree override, so filtering stays identical to production
// while also exposing WHICH busy interval blocked a candidate.
// ponytail: tiny duplicated predicate because production exports no hook for
// "which interval blocked this" — upgrade by exporting one from the
// production workflow module if a second caller ever needs this.
function findBlockingInterval(candidate, calendar) {
  const intervals = Array.isArray(calendar)
    ? calendar
    : (calendar && Array.isArray(calendar.busy_intervals) ? calendar.busy_intervals : []);
  const start = Date.parse(candidate.starts_at);
  const end = Date.parse(candidate.ends_at);
  return intervals.find((busy) => busy && busy.kind === "timed"
    && start < Date.parse(busy.end_at) && end > Date.parse(busy.start_at)) || null;
}

// spyEntries = candidates the workflow actually ran the calendar-free check
// against (i.e. already in-window and free/open — the workflow exposes no
// hook earlier than that, so events rejected before this stage show up only
// in `totals`, never as a row). registeredExisting = Connpass candidates
// that bypass the check entirely because they are already registered.
function buildRows({ spyEntries = [], registeredExisting = [] } = {}) {
  const rows = [];
  for (const entry of spyEntries) {
    const { candidate, passed, blocking } = entry;
    const range = formatTokyoRange(candidate.starts_at, candidate.ends_at);
    rows.push(Object.freeze({
      date: range.date,
      start: range.start,
      end: range.end,
      free_open: "pass",
      calendar_free: passed ? "pass" : "fail",
      blocked_by: passed || !blocking ? null : formatTokyoRange(blocking.start_at, blocking.end_at),
      title: String(candidate.title || ""),
      canonical_url: String(candidate.canonical_url || ""),
    }));
  }
  for (const candidate of registeredExisting) {
    const range = formatTokyoRange(candidate.starts_at, candidate.ends_at);
    rows.push(Object.freeze({
      date: range.date,
      start: range.start,
      end: range.end,
      free_open: "registered",
      calendar_free: "n/a",
      blocked_by: null,
      title: String(candidate.title || ""),
      canonical_url: String(candidate.canonical_url || ""),
    }));
  }
  rows.sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? -1 : 1;
    if (a.start !== b.start) return a.start < b.start ? -1 : 1;
    return 0;
  });
  return Object.freeze(rows);
}

// Same five fields a wake's onDiscoveryAudit callback records, in the same
// order, so a human can diff this CLI's totals line against an audit row.
function buildTotals(audit) {
  const source = audit && typeof audit === "object" ? audit : {};
  const field = (name) => (Number.isInteger(source[name]) ? source[name] : 0);
  return Object.freeze({
    observed_count: field("observed_count"),
    normalized_count: field("normalized_count"),
    window_count: field("window_count"),
    free_open_count: field("free_open_count"),
    calendar_free_count: field("calendar_free_count"),
  });
}

function renderOutput({ provider, rows, totals, json }) {
  if (json) return JSON.stringify({ provider, rows, totals }, null, 2);
  const header = ["DATE", "START", "END", "FREE/OPEN", "CAL_FREE", "BLOCKED_BY", "TITLE", "URL"];
  const lines = [`provider: ${provider}`, header.join(" | ")];
  for (const row of rows) {
    const blocked = row.blocked_by ? `${row.blocked_by.date} ${row.blocked_by.start}-${row.blocked_by.end}` : "-";
    lines.push([row.date, row.start, row.end, row.free_open, row.calendar_free, blocked, row.title, row.canonical_url].join(" | "));
  }
  if (rows.length === 0) lines.push("(no candidate reached the free/open + in-window stage that the calendar-free check observes)");
  lines.push("");
  lines.push(`totals: observed=${totals.observed_count} normalized=${totals.normalized_count} `
    + `window=${totals.window_count} free_open=${totals.free_open_count} calendar_free=${totals.calendar_free_count}`);
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Impure I/O: browser lease, calendar read, page-driven discovery.
// ---------------------------------------------------------------------------

function acquireBrowserLease(guardBin) {
  try {
    const stdout = execFileSync(guardBin, ["acquire", BROWSER_IDENTITY], { encoding: "utf8" });
    return validBrowserBaseUrl(stdout.trim());
  } catch (error) {
    const status = error && typeof error.status === "number" ? error.status : null;
    if (status === 9) {
      process.stderr.write(`Browser busy: ${BROWSER_IDENTITY} lease is already held. Skipping this run.\n`);
      process.exit(9);
    }
    if (status === 10) {
      process.stderr.write(`Browser unavailable: ${BROWSER_IDENTITY} identity did not resolve (profile not running / CDP unreachable).\n`);
      process.exit(10);
    }
    throw error;
  }
}

function releaseBrowserLease(guardBin) {
  try { execFileSync(guardBin, ["release", BROWSER_IDENTITY], { stdio: "ignore" }); } catch { /* best-effort */ }
}

function resolveConnectorEnv() {
  const configured = String(process.env.LM_CONNECTOR_SHARED_ENV_FILE || "").trim();
  const sharedFile = configured || path.join(os.homedir(), ".openclaw", ".env");
  return loadConnectorEnv(sharedFile);
}

async function runDiscovery({ provider, page, calendar }) {
  const spyEntries = [];
  const isCalendarFree = (candidate, busy) => {
    const blocking = findBlockingInterval(candidate, busy);
    const passed = blocking === null;
    spyEntries.push(Object.freeze({ candidate, passed, blocking }));
    return passed;
  };
  let audit = null;
  const onDiscoveryAudit = (value) => { audit = value; };
  const workflow = provider === "luma"
    ? createLumaScriptFirstWorkflow({ isCalendarFree, onDiscoveryAudit })
    : createConnpassScriptFirstWorkflow({ isCalendarFree, onDiscoveryAudit });
  const result = await workflow.discoverCandidates({ page, calendar });
  const registeredExisting = provider === "connpass"
    ? result.filter((candidate) => candidate.registration_status === "registered")
    : [];
  return { spyEntries, registeredExisting, audit };
}

async function main(argv, { stdout = process.stdout } = {}) {
  const args = parseArgs(argv);
  const env = resolveConnectorEnv();

  const baseUrl = acquireBrowserLease(BROWSER_GUARD_BIN);
  let released = false;
  const release = () => {
    if (released) return;
    released = true;
    releaseBrowserLease(BROWSER_GUARD_BIN);
  };
  const onSignal = (code) => { release(); process.exit(code); };
  process.on("SIGINT", () => onSignal(130));
  process.on("SIGTERM", () => onSignal(143));
  process.on("exit", release);

  let page = null;
  try {
    // playwright-core lives only in apps/life-manager/node_modules; resolve
    // it via that relative path rather than adding a dependency here.
    const { chromium } = require("../../apps/life-manager/node_modules/playwright-core");
    const browser = await chromium.connectOverCDP(baseUrl);
    const contexts = browser.contexts();
    if (!Array.isArray(contexts) || contexts.length !== 1) invalid("Connector discover browser context unavailable");
    page = await contexts[0].newPage();

    const calendarReader = createProductionCalendarReader({
      gogBin: env.GOG_BIN,
      account: env.GOG_ACCOUNT || env.LM_CONNECTOR_LUMA_EMAIL,
      keyring: env.GOG_KEYRING_PASSWORD,
    });
    const calendar = await calendarReader.readCalendarGaps();

    const { spyEntries, registeredExisting, audit } = await runDiscovery({
      provider: args.provider, page, calendar,
    });
    const rows = buildRows({ spyEntries, registeredExisting });
    const totals = buildTotals(audit);
    stdout.write(`${renderOutput({ provider: args.provider, rows, totals, json: args.json })}\n`);
  } finally {
    if (page && typeof page.close === "function") {
      try { await page.close(); } catch { /* page already gone */ }
    }
    release();
  }
}

if (require.main === module) {
  main(process.argv.slice(2)).catch((error) => {
    process.stderr.write(`${(error && error.message) || "Connector discover unavailable"}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  parseArgs,
  formatTokyoRange,
  findBlockingInterval,
  buildRows,
  buildTotals,
  renderOutput,
  validBrowserBaseUrl,
};
