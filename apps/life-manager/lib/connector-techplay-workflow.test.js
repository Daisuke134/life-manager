"use strict";

const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createTechPlayDiscoveryWorkflow } = require("./connector-techplay-workflow.js");

const NOW = new Date("2026-08-11T03:00:00.000Z");
const TOKYO = "東京都千代田区平河町2-7-2";

function binding(id) {
  return { event_ref: `techplay-event://event/${id}`, canonical_url: `https://techplay.jp/event/${id}` };
}

function detail(id, overrides = {}) {
  const row = binding(id);
  const { event: eventOverrides = {}, event_info_states: infoOverrides = {}, event_button_states: buttonOverrides = {}, ticket, attend_types, ...rest } = overrides;
  return {
    current_url: row.canonical_url,
    event: {
      id: Number(id), title: `Tokyo TECH PLAY ${id}`, started_at: 1787216400, ended_at: 1787220000,
      place: "TECH PLAY TOKYO", address: TOKYO, event_url: null, join_started_at: null, join_ended_at: null,
      ...eventOverrides,
    },
    event_info_states: {
      is_ended: false, event_format: "offline_only", show_event_button: true, apply_status: null,
      external_link_status: null, ...infoOverrides,
    },
    event_button_states: { button_display_type: "apply", event_url: null, ...buttonOverrides },
    attend_types: attend_types || [{ id: 12345, capacity: 20, entrance_fee: 0, entered: 0, is_full: false, is_joined: false, use_stripe: false, ...ticket }],
    ...rest,
  };
}

function inertiaHtml(payload) {
  return `<div id="app" data-page="${JSON.stringify(payload).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}"></div>`;
}

function workflowFor(rows, details, options = {}) {
  const audits = [];
  const reads = [];
  const workflow = createTechPlayDiscoveryWorkflow({
    now: () => new Date(NOW),
    readRss: async () => rows,
    readEventDetail: async (_page, url) => { reads.push(url); return details[url]; },
    onDiscoveryAudit: async (audit) => audits.push(audit),
    ...options,
  });
  return { workflow, audits, reads };
}

function readbackCandidate(id, ticketId = "12345") {
  const row = binding(id);
  return { ...row, provider: "techplay", title: `Tokyo TECH PLAY ${id}`, starts_at: "2026-08-20T09:00:00.000Z", ends_at: "2026-08-20T10:00:00.000Z", ticket_id: ticketId, registration_status: "available", ticket_price_status: "free", ticket_price_minor: 0 };
}

function pageAt(url) {
  return { current: url, url() { return this.current; } };
}

function responsePage(url, payload, options = {}) {
  const responseUrl = options.responseUrl === undefined ? url : options.responseUrl; const status = options.status === undefined ? 200 : options.status;
  return {
    current: url,
    url() { return this.current; },
    async goto(nextUrl) {
      this.current = options.redirectUrl === undefined ? nextUrl : options.redirectUrl;
      if (options.transportError) throw new Error("transport");
      return {
        url() { return responseUrl; }, status() { return status; },
        async text() {
          if (options.readError) throw new Error("read"); return inertiaHtml({ props: payload });
        },
      };
    },
  };
}

test("TECH PLAY discovers free Tokyo events and returns exact candidates", async () => {
  const row = binding("999180");
  const { workflow, audits, reads } = workflowFor([row], { [row.canonical_url]: detail("999180") });
  const result = await workflow.discoverCandidates({ page: {}, calendar: [] });
  assert.deepEqual(result.map(({ provider, event_ref, canonical_url, title, ticket_id, ticket_price_minor }) => ({ provider, event_ref, canonical_url, title, ticket_id, ticket_price_minor })), [{
    provider: "techplay", event_ref: row.event_ref, canonical_url: row.canonical_url,
    title: "Tokyo TECH PLAY 999180", ticket_id: "12345", ticket_price_minor: 0,
  }]);
  assert.deepEqual(reads, [row.canonical_url]);
  assert.deepEqual(audits, [{ discovered_count: 1, rss_count: 1,
    processed_count: 1, pending_count: 0, saturated_count: 0,
    within_window_count: 1, eligible_count: 1, calendar_free_count: 1, selected_count: 1 }]);
  assert.equal(Object.keys(audits[0]).some((key) => /title|url|ticket|identity|body|profile/i.test(key)), false);
});

test("TECH PLAY resumes bounded detail discovery across fresh wakes without starving later RSS rows", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-discovery-cursor-"));
  const rows = ["999180", "999181", "999182", "999183", "999184"].map(binding);
  const details = Object.fromEntries(rows.map((row) => [row.canonical_url, detail(row.event_ref.split("/").pop())]));
  try {
    const first = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2 });
    assert.deepEqual((await first.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((row) => row.event_ref), rows.slice(0, 2).map((row) => row.event_ref));
    assert.deepEqual(first.reads, rows.slice(0, 2).map((row) => row.canonical_url));
    assert.equal(first.audits[0].processed_count, 2);
    assert.equal(first.audits[0].pending_count, 5);
    const cursorFile = path.join(stateDir, "techplay-discovery-cursor.json");
    assert.equal(fs.statSync(cursorFile).mode & 0o777, 0o600);
    assert.deepEqual(Object.keys(JSON.parse(fs.readFileSync(cursorFile, "utf8"))).sort(),
      ["completed", "pending", "retry", "schema_version"]);
    assert.doesNotMatch(fs.readFileSync(cursorFile, "utf8"), /https?:\/\/|title|email|auth/i);

    const second = workflowFor([...rows].reverse(), details, { stateDir, maxDetailsPerWake: 2 });
    assert.deepEqual((await second.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((row) => row.event_ref), [rows[0].event_ref, rows[2].event_ref]);

    const third = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2 });
    assert.deepEqual((await third.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((row) => row.event_ref), [rows[1].event_ref, rows[3].event_ref]);

    const fourth = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2 });
    assert.deepEqual((await fourth.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((row) => row.event_ref), [rows[0].event_ref, rows[4].event_ref]);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("TECH PLAY restarts the scan when remaining RSS rows disappear", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-discovery-shrink-"));
  const rows = ["999180", "999181", "999182"].map(binding);
  const details = Object.fromEntries(rows.map((row) => [row.canonical_url, detail(row.event_ref.split("/").pop())]));
  try {
    const first = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2 });
    assert.equal((await first.workflow.discoverCandidates({ page: {}, calendar: [] })).length, 2);
    const second = workflowFor(rows.slice(0, 2), details, { stateDir, maxDetailsPerWake: 2 });
    assert.deepEqual((await second.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((row) => row.event_ref), rows.slice(0, 2).map((row) => row.event_ref));
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("TECH PLAY keeps the failed detail and advances past earlier verified rows", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-discovery-retry-"));
  const rows = ["999180", "999181", "999182"].map(binding);
  const details = Object.fromEntries(rows.map((row) => [row.canonical_url, detail(row.event_ref.split("/").pop())]));
  try {
    const first = workflowFor(rows, details, {
      stateDir, maxDetailsPerWake: 2,
      readEventDetail: async (_page, url) => {
        if (url === rows[1].canonical_url) throw new Error("transport unavailable");
        return details[url];
      },
    });
    await assert.rejects(first.workflow.discoverCandidates({ page: {}, calendar: [] }),
      (error) => error.code === "TECHPLAY_DETAIL_READ_FAILED");
    const second = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2 });
    assert.deepEqual((await second.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((row) => row.event_ref), rows.slice(0, 2).map((row) => row.event_ref));
    assert.deepEqual(second.reads, rows.slice(0, 2).map((row) => row.canonical_url));
    const third = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2 });
    assert.deepEqual((await third.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((row) => row.event_ref), [rows[0].event_ref, rows[2].event_ref]);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("TECH PLAY re-presents a candidate after a later detail fails before the caller receives it", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-candidate-retry-"));
  const rows = ["999180", "999181"].map(binding);
  const details = Object.fromEntries(rows.map((row) => [row.canonical_url, detail(row.event_ref.split("/").pop())]));
  try {
    const first = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2,
      readEventDetail: async (_page, url) => {
        if (url === rows[1].canonical_url) throw new Error("transport unavailable");
        return details[url];
      },
    });
    await assert.rejects(first.workflow.discoverCandidates({ page: {}, calendar: [] }),
      (error) => error.code === "TECHPLAY_DETAIL_READ_FAILED");
    const second = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2 });
    assert.deepEqual((await second.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((row) => row.event_ref), rows.map((row) => row.event_ref));
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("TECH PLAY re-presents a candidate after the audit fails before return", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-audit-retry-"));
  const row = binding("999180");
  const details = { [row.canonical_url]: detail("999180") };
  try {
    const first = workflowFor([row], details, { stateDir, maxDetailsPerWake: 1,
      onDiscoveryAudit: async () => { throw new Error("audit unavailable"); },
    });
    await assert.rejects(first.workflow.discoverCandidates({ page: {}, calendar: [] }),
      (error) => error.code === "TECHPLAY_AUDIT_FAILED");
    const second = workflowFor([row], details, { stateDir, maxDetailsPerWake: 1 });
    assert.deepEqual((await second.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((candidate) => candidate.event_ref), [row.event_ref]);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("TECH PLAY keeps a known actionable candidate after the rolling RSS evicts it", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-rss-eviction-"));
  const row = binding("999180");
  const details = { [row.canonical_url]: detail("999180") };
  try {
    const first = workflowFor([row], details, { stateDir, maxDetailsPerWake: 1 });
    assert.equal((await first.workflow.discoverCandidates({ page: {}, calendar: [] })).length, 1);
    const second = workflowFor([], details, { stateDir, maxDetailsPerWake: 1 });
    assert.deepEqual((await second.workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((candidate) => candidate.event_ref), [row.event_ref]);
    assert.equal(second.audits[0].discovered_count, 1);
    assert.equal(second.audits[0].rss_count, 0);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("TECH PLAY reserves most of each bounded wake for previously uninspected RSS rows", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-fair-scan-"));
  const rows = ["999180", "999181", "999182", "999183", "999184", "999185", "999186", "999187"].map(binding);
  const details = Object.fromEntries(rows.map((row) => [row.canonical_url, detail(row.event_ref.split("/").pop())]));
  try {
    const first = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 4 });
    assert.equal((await first.workflow.discoverCandidates({ page: {}, calendar: [] })).length, 4);
    const second = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 4 });
    await second.workflow.discoverCandidates({ page: {}, calendar: [] });
    assert.deepEqual(second.reads.slice(1), rows.slice(4, 7).map((row) => row.canonical_url));
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("TECH PLAY keeps returning retained candidates when retry capacity is full", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-retry-full-"));
  const row = binding("999180");
  const retry = Array.from({ length: 100 }, (_, index) => ({
    event_ref: binding(String(100000 + index)).event_ref,
    ends_at: "2026-08-20T10:00:00.000Z",
  }));
  fs.writeFileSync(path.join(stateDir, "techplay-discovery-cursor.json"),
    `${JSON.stringify({ schema_version: 2, pending: [], completed: [], retry })}\n`, { mode: 0o600 });
  const firstRetry = binding("100000");
  const details = { [row.canonical_url]: detail("999180"),
    [firstRetry.canonical_url]: detail("100000") };
  try {
    const { workflow, audits } = workflowFor([row], details, { stateDir, maxDetailsPerWake: 2 });
    const result = await workflow.discoverCandidates({ page: {}, calendar: [] });
    assert.deepEqual(result.map((candidate) => candidate.event_ref), [firstRetry.event_ref]);
    const stored = JSON.parse(fs.readFileSync(path.join(stateDir, "techplay-discovery-cursor.json"), "utf8"));
    assert.equal(stored.retry.length, 100);
    assert.equal(stored.retry.some((item) => item.event_ref === row.event_ref), false);
    assert.equal(stored.pending.includes(row.event_ref), true);
    assert.equal(audits[0].saturated_count, 1);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("TECH PLAY retires officially applied refs before admitting a new RSS candidate", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-applied-retirement-"));
  const row = binding("999180");
  const retry = Array.from({ length: 100 }, (_, index) => ({
    event_ref: binding(String(100000 + index)).event_ref,
    ends_at: "2026-08-20T10:00:00.000Z",
  }));
  fs.writeFileSync(path.join(stateDir, "techplay-discovery-cursor.json"),
    `${JSON.stringify({ schema_version: 2, pending: [], completed: [], retry })}\n`, { mode: 0o600 });
  try {
    const { workflow, audits } = workflowFor([row], { [row.canonical_url]: detail("999180") }, {
      stateDir, maxDetailsPerWake: 4,
      appliedEventRefs: async () => retry.map((item) => item.event_ref),
    });
    assert.deepEqual((await workflow.discoverCandidates({ page: {}, calendar: [] }))
      .map((candidate) => candidate.event_ref), [row.event_ref]);
    const stored = JSON.parse(fs.readFileSync(path.join(stateDir, "techplay-discovery-cursor.json"), "utf8"));
    assert.deepEqual(stored.retry.map((item) => item.event_ref), [row.event_ref]);
    assert.equal(audits[0].saturated_count, 0);
  } finally { fs.rmSync(stateDir, { recursive: true, force: true }); }
});

test("TECH PLAY stops before the action reserve and leaves uninspected rows queued", async () => {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "techplay-wake-budget-"));
  const rows = ["999180", "999181"].map(binding);
  const details = Object.fromEntries(rows.map((row) => [row.canonical_url, detail(row.event_ref.split("/").pop())]));
  let remaining = 190_000;
  try {
    const first = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2 });
    assert.deepEqual(await first.workflow.discoverCandidates({ page: {}, calendar: [],
      remainingWakeMs: () => remaining, completionReserveMs: 160_000,
    }), []);
    assert.deepEqual(first.reads, []);
    assert.equal(first.audits[0].processed_count, 0);
    assert.equal(first.audits[0].pending_count, 2);

    remaining = 300_000;
    const second = workflowFor(rows, details, { stateDir, maxDetailsPerWake: 2,
      readEventDetail: async (_page, url) => { remaining = 200_000; return details[url]; },
    });
    assert.deepEqual((await second.workflow.discoverCandidates({ page: {}, calendar: [],
      remainingWakeMs: () => remaining, completionReserveMs: 160_000,
    })).map((row) => row.event_ref), [rows[0].event_ref]);
    assert.equal(second.audits[0].processed_count, 1);
    assert.equal(second.audits[0].pending_count, 2);
  } finally {
    fs.rmSync(stateDir, { recursive: true, force: true });
  }
});

test("TECH PLAY puts exact connector coverage first and blocks unrelated overlap", async () => {
  const covered = binding("999181");
  const blocked = binding("999182");
  const unprocessed = binding("999208");
  const calendar = [
    { kind: "timed", start_at: "2026-08-20T19:30:00+09:00", end_at: "2026-08-20T19:45:00+09:00", connector_idempotency: "other" },
    { kind: "timed", start_at: "2026-08-20T18:00:00+09:00", end_at: "2026-08-20T19:00:00+09:00", connector_idempotency: createHash("sha256").update(covered.canonical_url).digest("hex") },
  ];
  const { workflow } = workflowFor([covered, blocked, unprocessed], {
    [covered.canonical_url]: detail("999181"),
    [blocked.canonical_url]: detail("999182", { event: { started_at: 1787220000, ended_at: 1787223600 } }),
    [unprocessed.canonical_url]: detail("999208", { event: { started_at: 1787223600, ended_at: 1787227200 } }),
  });
  assert.deepEqual((await workflow.discoverCandidates({ page: {}, calendar })).map((row) => row.event_ref), [covered.event_ref, unprocessed.event_ref]);
});

test("TECH PLAY rejects mismatched detail identity and unsafe rows", async () => {
  const mismatch = binding("999183");
  const unsafe = [
    ["paid", binding("999184"), detail("999184", { ticket: { entrance_fee: 100 } })],
    ["external", binding("999185"), detail("999185", { event: { event_url: "https://outside.example/event" } })],
    ["online", binding("999186"), detail("999186", { event_info_states: { event_format: "online_only" } })],
    ["closed", binding("999187"), detail("999187", { event_button_states: { button_display_type: "closed" } })],
    ["hidden-apply", binding("999201"), detail("999201", { event_button_states: { visible: false } })],
    ["full", binding("999188"), detail("999188", { ticket: { is_full: true } })],
    ["ambiguous-free-tickets", binding("999189"), detail("999189", { attend_types: [{ id: 1, capacity: 2, entrance_fee: 0, entered: 0, is_full: false, is_joined: false, use_stripe: false }, { id: 2, capacity: 2, entrance_fee: 0, entered: 0, is_full: false, is_joined: false, use_stripe: false }] })],
    ["school-age-only", binding("999191"), detail("999191", { event: { title: "小学生・中学生対象のTECH PLAY" } })],
  ];
  const rows = unsafe.map(([, row]) => row).concat(mismatch);
  const details = Object.fromEntries(unsafe.map(([, row, value]) => [row.canonical_url, value]));
  details[mismatch.canonical_url] = detail("999999");
  const { workflow } = workflowFor(rows, details);
  await assert.rejects(workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_DETAIL_IDENTITY_MISMATCH_FAILED");
  const safeRows = unsafe.map(([, row]) => row);
  const safe = workflowFor(safeRows, details);
  assert.deepEqual(await safe.workflow.discoverCandidates({ page: {}, calendar: [] }), []);
});

test("TECH PLAY skips recruitment-not-open, out-of-window, joined, and Stripe rows", async () => {
  const cases = [
    ["recruitment-not-open", detail("999197", { event: { join_started_at: 1788000000, join_ended_at: 1788100000 } })],
    ["out-of-window", detail("999198", { event: { started_at: 1788422400, ended_at: 1788426000 } })],
    ["end-at-window-boundary", detail("999206", { event: { started_at: 1787580000, ended_at: 1787583600 } })],
    ["joined", detail("999199", { ticket: { is_joined: true } })],
    ["stripe", detail("999200", { ticket: { use_stripe: true } })],
  ];
  const rows = cases.map(([, value]) => ({ canonical_url: value.current_url }));
  const { workflow } = workflowFor(rows, Object.fromEntries(cases.map(([, value]) => [value.current_url, value])));
  assert.deepEqual(await workflow.discoverCandidates({ page: {}, calendar: [] }), []);
});

test("TECH PLAY requires exact detail current URL and raises a base contract error", async () => {
  const missing = binding("999201");
  const missingPayload = detail("999201");
  delete missingPayload.current_url;
  const missingWorkflow = workflowFor([missing], { [missing.canonical_url]: missingPayload });
  await assert.rejects(missingWorkflow.workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");

  const mismatch = binding("999202");
  const mismatchPayload = detail("999202", { current_url: "https://techplay.jp/event/999203" });
  const mismatchWorkflow = workflowFor([mismatch], { [mismatch.canonical_url]: mismatchPayload });
  await assert.rejects(mismatchWorkflow.workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_DETAIL_IDENTITY_MISMATCH_FAILED");

  const absent = binding("999203");
  const absentWorkflow = workflowFor([absent], { [absent.canonical_url]: {} });
  await assert.rejects(absentWorkflow.workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");

  const incomplete = binding("999204");
  const incompletePayload = { current_url: incomplete.canonical_url, event: detail("999204").event };
  const incompleteWorkflow = workflowFor([incomplete], { [incomplete.canonical_url]: incompletePayload });
  await assert.rejects(incompleteWorkflow.workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");

  const missingId = binding("999207");
  const missingIdPayload = detail("999207");
  delete missingIdPayload.event.id;
  const missingIdWorkflow = workflowFor([missingId], { [missingId.canonical_url]: missingIdPayload });
  await assert.rejects(missingIdWorkflow.workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
});

test("TECH PLAY deduplicates exact IDs and bounds RSS rows at fifty", async () => {
  const row = binding("999192");
  const { workflow, reads } = workflowFor([row, row, { href: `${row.canonical_url}?utm=1` }], { [row.canonical_url]: detail("999192") });
  assert.equal((await workflow.discoverCandidates({ page: {}, calendar: [] })).length, 1);
  assert.deepEqual(reads, [row.canonical_url]);
  const tooMany = workflowFor(Array.from({ length: 51 }, (_, i) => binding(String(100000 + i))), {});
  await assert.rejects(tooMany.workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_LISTING_RESULT_CONTRACT_FAILED");
});

test("TECH PLAY rejects malformed URL identity variants", async () => {
  const variants = [
    "https://techplay.jp/event/999193?x=1", "https://techplay.jp/event/999193#fragment", "https://techplay.jp/event/999193/",
    "https://TECHPLAY.jp/event/999193", "https://www.techplay.jp/event/999193", "https://user:pass@techplay.jp/event/999193", "https://techplay.jp:443/event/999193",
  ];
  const { workflow } = workflowFor(variants.map((canonical_url) => ({ canonical_url })), {});
  assert.deepEqual(await workflow.discoverCandidates({ page: {}, calendar: [] }), []);
});

test("TECH PLAY maps transport and Calendar failures to safe stage errors", async () => {
  const row = binding("999194");
  const listing = createTechPlayDiscoveryWorkflow({ readRss: async () => { throw new Error("network"); } });
  await assert.rejects(listing.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_LISTING_READ_FAILED");
  const detailFailure = workflowFor([row], {}, { readEventDetail: async () => { throw new Error("network"); } });
  await assert.rejects(detailFailure.workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_DETAIL_READ_FAILED");
  const calendarFailure = workflowFor([row], { [row.canonical_url]: detail("999194") }, { isCalendarFree: async () => { throw new Error("calendar"); } });
  await assert.rejects(calendarFailure.workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_CALENDAR_CONFLICT_CHECK_FAILED");
  const auditFailure = workflowFor([row], { [row.canonical_url]: detail("999194") }, { onDiscoveryAudit: async () => { throw new Error("audit"); } });
  await assert.rejects(auditFailure.workflow.discoverCandidates({ page: {}, calendar: [] }), (error) => error.code === "TECHPLAY_AUDIT_FAILED");
});

test("TECH PLAY direct action fails safely and readback remains unavailable", async () => {
  const row = { ...binding("999195"), provider: "techplay", title: "Free", starts_at: "2026-08-20T09:00:00.000Z", ends_at: "2026-08-20T10:00:00.000Z", ticket_id: "12345", registration_status: "available", ticket_price_status: "free", ticket_price_minor: 0 };
  const workflow = createTechPlayDiscoveryWorkflow();
  assert.deepEqual(await workflow.runDirectAction({ page: { click: async () => { throw new Error("must not click"); } }, candidate: row }), { status: "failed", safe_reason: "techplay_direct_requires_harness" });
  assert.deepEqual(await workflow.readProviderState({ page: {}, candidate: row }), { status: "unavailable" });
  for (const invalidTicketId of ["0", "-1", "12.5", "ticket"]) {
    await assert.rejects(workflow.runDirectAction({ page: {}, candidate: { ...row, ticket_id: invalidTicketId } }));
  }
  await assert.rejects(workflow.runDirectAction({ page: {}, candidate: { ...row, ticket_id: 12345 } }));
});

test("TECH PLAY parent readback proves only the exact canonical joined or actionable ticket", async () => {
  const row = binding("999210");
  const candidate = readbackCandidate("999210");
  const joined = createTechPlayDiscoveryWorkflow({ now: () => new Date(NOW), readEventDetail: async () => detail("999210", { ticket: { is_joined: true } }) });
  assert.deepEqual(await joined.readProviderState({ page: pageAt(row.canonical_url), candidate }), { status: "registered" });
  const absent = createTechPlayDiscoveryWorkflow({ now: () => new Date(NOW), readEventDetail: async () => detail("999210") });
  assert.deepEqual(await absent.readProviderState({ page: pageAt(row.canonical_url), candidate }), { status: "absent" });
});

test("TECH PLAY absent readback requires a currently open event and valid factory clock", async () => {
  const row = binding("999214");
  const candidate = readbackCandidate("999214");
  const cases = [["future recruitment", detail("999214", { event: { join_started_at: 1788000000, join_ended_at: 1788100000 } })], ["ended event", detail("999214", { event: { ended_at: Math.floor(NOW.getTime() / 1000) - 1 } })]];
  for (const [name, payload] of cases) {
    const workflow = createTechPlayDiscoveryWorkflow({ now: () => new Date(NOW), readEventDetail: async () => payload });
    assert.deepEqual(await workflow.readProviderState({ page: pageAt(row.canonical_url), candidate }), { status: "unavailable" }, name);
  }
  for (const invalidNow of [() => "invalid", () => { throw new Error("clock"); }]) {
    const workflow = createTechPlayDiscoveryWorkflow({ now: invalidNow, readEventDetail: async () => detail("999214") }); assert.deepEqual(await workflow.readProviderState({ page: pageAt(row.canonical_url), candidate }), { status: "unavailable" }, "invalid now");
  }
});

test("TECH PLAY default parent readback returns status-only registered and absent results", async () => {
  const row = binding("999215");
  const candidate = readbackCandidate("999215");
  const joinedPayload = { ...detail("999215", { ticket: { is_joined: true } }), currentUrl: row.canonical_url };
  const joined = createTechPlayDiscoveryWorkflow({ now: () => new Date(NOW) });
  const joinedResult = await joined.readProviderState({ page: responsePage(row.canonical_url, joinedPayload), candidate });
  assert.deepEqual(joinedResult, { status: "registered" });
  assert.deepEqual(Object.keys(joinedResult), ["status"]);
  const absentPayload = { ...detail("999215"), currentUrl: row.canonical_url };
  const absent = createTechPlayDiscoveryWorkflow({ now: () => new Date(NOW) });
  const absentResult = await absent.readProviderState({ page: responsePage(row.canonical_url, absentPayload), candidate });
  assert.deepEqual(absentResult, { status: "absent" });
  assert.deepEqual(Object.keys(absentResult), ["status"]);
  assert.equal(JSON.stringify(absentResult).includes("Tokyo TECH PLAY"), false);
});

test("TECH PLAY parent readback fails closed for join/confirm, identity, ticket, state, and action ambiguity", async () => {
  const candidate = readbackCandidate("999211");
  const secondTicket = { id: 54321, capacity: 20, entrance_fee: 0, entered: 0, is_full: false, is_joined: true, use_stripe: false };
  const cases = [
    ["join", detail("999211", { current_url: "https://techplay.jp/event/join/999211", ticket: { is_joined: true } })],
    ["confirm", detail("999211", { current_url: "https://techplay.jp/event/join/999211/confirm", ticket: { is_joined: true } })],
    ["event", detail("999211", { event: { id: 999212 }, ticket: { is_joined: true } })],
    ["ticket", detail("999211", { ticket: { id: 54321, is_joined: true } })],
    ["duplicate", detail("999211", { attend_types: [detail("999211").attend_types[0], secondTicket] })],
    ["malformed", detail("999211", { ticket: { is_joined: "true" } })],
    ["closed", detail("999211", { event_button_states: { button_display_type: "closed" } })],
    ["hidden", detail("999211", { event_button_states: { visible: false } })],
  ];
  for (const [name, payload] of cases) {
    const workflow = createTechPlayDiscoveryWorkflow({ readEventDetail: async () => payload });
    assert.deepEqual(await workflow.readProviderState({ page: pageAt(candidate.canonical_url), candidate }), { status: "unavailable" }, name);
  }
  const wrongCurrent = createTechPlayDiscoveryWorkflow({ readEventDetail: async () => detail("999211") });
  assert.deepEqual(await wrongCurrent.readProviderState({ page: pageAt("https://techplay.jp/event/999299"), candidate }), { status: "unavailable" }, "current URL");
  const missingPage = createTechPlayDiscoveryWorkflow({ readEventDetail: async () => detail("999211") });
  assert.deepEqual(await missingPage.readProviderState({ page: {}, candidate }), { status: "unavailable" }, "missing page URL");
});

test("TECH PLAY parent readback rejects response, navigation, read, and pre/post page drift", async () => {
  const row = binding("999213");
  const candidate = readbackCandidate("999213");
  const payload = detail("999213", { ticket: { is_joined: true } });
  const cases = [
    ["response URL", { responseUrl: "https://techplay.jp/event/999214" }],
    ["status", { status: 500 }],
    ["redirect", { redirectUrl: "https://techplay.jp/event/999214" }],
    ["transport", { transportError: true }],
    ["read", { readError: true }],
  ];
  for (const [name, options] of cases) {
    const workflow = createTechPlayDiscoveryWorkflow();
    assert.deepEqual(await workflow.readProviderState({ page: responsePage(row.canonical_url, payload, options), candidate }), { status: "unavailable" }, name);
  }
  const driftPage = pageAt(row.canonical_url);
  const drift = createTechPlayDiscoveryWorkflow({ readEventDetail: async () => { driftPage.current = "https://techplay.jp/event/join/999213"; return payload; } });
  assert.deepEqual(await drift.readProviderState({ page: driftPage, candidate }), { status: "unavailable" }, "post-read page drift");
});

test("TECH PLAY default readers navigate exact RSS/detail URLs and minimize Inertia fields", async () => {
  const row = binding("999196");
  const fullPayload = { props: { csrfToken: "secret", auth: { profile: "secret" }, currentUrl: row.canonical_url, event: detail("999196").event, event_info_states: detail("999196").event_info_states, event_button_states: detail("999196").event_button_states, attend_types: detail("999196").attend_types } };
  const response = { url() { return row.canonical_url; }, status() { return 200; }, async text() { return inertiaHtml(fullPayload); } };
  const page = { current: "", calls: [], results: [], async goto(url) { this.calls.push(["goto", url]); this.current = url; return url === row.canonical_url ? response : null; }, url() { return this.current; }, async evaluate(fn) {
    this.calls.push(["evaluate", this.current]);
    const previousDocument = global.document; const previousLocation = global.location;
    const item = { querySelector() { return { textContent: row.canonical_url }; } };
    global.location = { href: this.current };
    global.document = this.current === "https://rss.techplay.jp/event/w3c-rss-format/rss.xml"
      ? { querySelectorAll() { return [item]; } }
      : { querySelector() { return null; } };
    try { const result = await fn(); this.results.push(result); return result; } finally {
      if (previousDocument === undefined) delete global.document; else global.document = previousDocument;
      if (previousLocation === undefined) delete global.location; else global.location = previousLocation;
    }
  } };
  const workflow = createTechPlayDiscoveryWorkflow({ now: () => new Date(NOW) });
  const result = await workflow.discoverCandidates({ page, calendar: [] });
  assert.equal(result.length, 1);
  assert.deepEqual(page.calls.map(([kind, url]) => [kind, url]), [
    ["goto", "https://rss.techplay.jp/event/w3c-rss-format/rss.xml"], ["evaluate", "https://rss.techplay.jp/event/w3c-rss-format/rss.xml"],
    ["goto", row.canonical_url],
  ]);
  assert.deepEqual(Object.keys(result[0]).sort(), ["canonical_url", "ends_at", "event_ref", "provider", "registration_status", "starts_at", "ticket_id", "ticket_price_minor", "ticket_price_status", "title"]);
  assert.equal(JSON.stringify(result).includes("secret"), false);
});

test("TECH PLAY default detail reader fails closed for malformed, oversized, and missing response payloads", async () => {
  const row = binding("999205");
  for (const response of [
    { url() { return row.canonical_url; }, status() { return 500; }, async text() { return inertiaHtml(detail("999205")); } },
    { url() { return row.canonical_url; }, status() { return 200; }, async text() { return ""; } },
    { url() { return row.canonical_url; }, status() { return 200; }, async text() { return `<div id="app" data-page="${"x".repeat(2_100_000)}"></div>`; } },
  ]) {
    const page = { current: "", async goto(url) { this.current = url; return url === row.canonical_url ? response : null; }, url() { return this.current; }, async evaluate() { return []; } };
    const workflow = createTechPlayDiscoveryWorkflow({ now: () => new Date(NOW), readRss: async () => [row] });
    await assert.rejects(workflow.discoverCandidates({ page, calendar: [] }), (error) => error.code === "TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
  }
});
