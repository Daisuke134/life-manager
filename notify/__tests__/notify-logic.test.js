// notify-logic.test.js — unit tests for pure functions in notify.js
// node --test skills/life/notify/__tests__/notify-logic.test.js

const { test } = require("node:test");
const assert = require("node:assert");

// Require only the exported pure functions (not the CLI entrypoint side effects)
const {
  isTravelBlock,
  isLateRisk,
  detectLateRiskEvents,
  estimateMinutesLate,
  buildAttendeeDraft,
  buildApprovalEmail,
  extractApproval,
} = require("../notify");

// ── isTravelBlock ─────────────────────────────────────────────────────────────

test("isTravelBlock returns true for [Travel] prefixed events", () => {
  assert.strictEqual(isTravelBlock("[Travel] dentist"), true);
  assert.strictEqual(isTravelBlock("[Travel] Team Sync"), true);
});

test("isTravelBlock returns false for normal events", () => {
  assert.strictEqual(isTravelBlock("dentist appointment"), false);
  assert.strictEqual(isTravelBlock(""), false);
  assert.strictEqual(isTravelBlock(undefined), false);
});

// ── isLateRisk ────────────────────────────────────────────────────────────────

test("isLateRisk returns true when past travelStart + grace", () => {
  const travelStartMs = Date.now() - 600_000; // 10 min ago (past the 5-min grace window)
  assert.strictEqual(isLateRisk({ travelStartMs, nowMs: Date.now() }), true);
});

test("isLateRisk returns false when travel block is in the future", () => {
  const travelStartMs = Date.now() + 600_000; // 10 min from now
  assert.strictEqual(isLateRisk({ travelStartMs, nowMs: Date.now() }), false);
});

test("isLateRisk returns false at exact boundary (nowMs === travelStartMs)", () => {
  const travelStartMs = Date.now();
  assert.strictEqual(isLateRisk({ travelStartMs, nowMs: travelStartMs }), false);
});

// ── detectLateRiskEvents ──────────────────────────────────────────────────────

test("detectLateRiskEvents flags event when paired travel block has started", () => {
  const nowMs = Date.now();
  const travelStartMs = nowMs - 600_000; // 10 min ago → late risk
  const eventStartMs = nowMs + 600_000;   // 10 min from now

  const events = [
    {
      id: "t1",
      summary: "[Travel] Team Sync",
      start: { dateTime: new Date(travelStartMs).toISOString() },
      end:   { dateTime: new Date(nowMs).toISOString() },
    },
    {
      id: "e1",
      summary: "Team Sync",
      start: { dateTime: new Date(eventStartMs).toISOString() },
      end:   { dateTime: new Date(eventStartMs + 3_600_000).toISOString() },
      attendees: [{ email: "boss@example.com" }],
    },
  ];

  const risks = detectLateRiskEvents(events, nowMs);
  assert.strictEqual(risks.length, 1);
  assert.strictEqual(risks[0].event.summary, "Team Sync");
  assert.strictEqual(risks[0].isLate, true);
});

test("detectLateRiskEvents returns empty when travel block is future", () => {
  const nowMs = Date.now();
  const travelStartMs = nowMs + 900_000; // future

  const events = [
    {
      id: "t2",
      summary: "[Travel] Lunch",
      start: { dateTime: new Date(travelStartMs).toISOString() },
      end:   { dateTime: new Date(travelStartMs + 1_800_000).toISOString() },
    },
    {
      id: "e2",
      summary: "Lunch",
      start: { dateTime: new Date(travelStartMs + 1_800_000).toISOString() },
      end:   { dateTime: new Date(travelStartMs + 5_400_000).toISOString() },
    },
  ];

  assert.strictEqual(detectLateRiskEvents(events, nowMs).length, 0);
});

test("detectLateRiskEvents skips all-day events", () => {
  const nowMs = Date.now();
  const events = [{ id: "e3", summary: "Holiday", start: { date: "2026-06-17" } }];
  assert.strictEqual(detectLateRiskEvents(events, nowMs).length, 0);
});

test("detectLateRiskEvents only flags events with a matching [Travel] block", () => {
  const nowMs = Date.now();
  const events = [
    {
      id: "e4",
      summary: "Doctor",
      start: { dateTime: new Date(nowMs + 1_800_000).toISOString() },
      end:   { dateTime: new Date(nowMs + 5_400_000).toISOString() },
      attendees: [{ email: "clinic@example.com" }],
    },
  ];
  assert.strictEqual(detectLateRiskEvents(events, nowMs).length, 0);
});

// ── estimateMinutesLate ───────────────────────────────────────────────────────

test("estimateMinutesLate clamps to 5 when diff < 5", () => {
  const nowMs = Date.now();
  const travelStartMs = nowMs - 120_000; // 2 min ago
  assert.strictEqual(estimateMinutesLate({ travelStartMs, nowMs }), 5);
});

test("estimateMinutesLate rounds to nearest 5", () => {
  const nowMs = Date.now();
  const travelStartMs = nowMs - 7 * 60_000; // 7 min ago → rounds to 5
  assert.strictEqual(estimateMinutesLate({ travelStartMs, nowMs }), 5);
});

// ── buildAttendeeDraft ────────────────────────────────────────────────────────

test("buildAttendeeDraft includes event name and minutes late", () => {
  const result = buildAttendeeDraft({ eventSummary: "Team Sync", minutesLate: 10 });
  assert.ok(result.includes("Team Sync"));
  assert.ok(result.includes("10"));
});

// ── buildApprovalEmail ────────────────────────────────────────────────────────

test("buildApprovalEmail sends to owner (not to attendees directly)", () => {
  const result = buildApprovalEmail({
    ownerEmail: "dais@example.com",
    eventSummary: "Dentist",
    attendees: [{ email: "clinic@example.com" }],
    draftBody: "I'll be 10 min late.",
    draftId: "draft-abc",
  });
  assert.strictEqual(result.to, "dais@example.com");
  assert.ok(result.body.includes("I'll be 10 min late."));
  assert.ok(result.body.includes("clinic@example.com"));
  assert.ok(result.subject.includes("Dentist"));
});

test("buildApprovalEmail includes draft ID for traceability", () => {
  const result = buildApprovalEmail({
    ownerEmail: "owner@example.com",
    eventSummary: "Solo",
    attendees: [],
    draftBody: "遅れます",
    draftId: "draft-xyz",
  });
  assert.ok(result.body.includes("draft-xyz"));
});

// ── extractApproval ───────────────────────────────────────────────────────────

test("extractApproval returns true for OK variants", () => {
  assert.strictEqual(extractApproval("OK"), true);
  assert.strictEqual(extractApproval("ok"), true);
  assert.strictEqual(extractApproval("Ok!"), true);
  assert.strictEqual(extractApproval("  OK  "), true);
  assert.strictEqual(extractApproval("ok, send it"), true);
});

test("extractApproval returns true for はい", () => {
  assert.strictEqual(extractApproval("はい"), true);
  assert.strictEqual(extractApproval("はい、送ってください"), true);
});

test("extractApproval returns false for non-approvals", () => {
  assert.strictEqual(extractApproval("no"), false);
  assert.strictEqual(extractApproval("wait"), false);
  assert.strictEqual(extractApproval(""), false);
  assert.strictEqual(extractApproval("send tomorrow instead"), false);
});

// ── gog-transport approval helpers (life-notify patch rev3) ────────────────────

const os = require("node:os");
const fsp = require("node:fs");
const pathp = require("node:path");
const { approvalToken, tokenFromSubject, appendPending, findPending, markSent } = require("../notify");

test("approvalToken -> tokenFromSubject round-trips through a Re: subject", () => {
  const tok = approvalToken("LunchTest:bob@example.com");
  assert.match(tok, /^AN-[0-9A-F]{8}$/);
  const subject = `Re: [Anicca] Late alert for "LunchTest" — reply OK to notify [${tok}]`;
  assert.strictEqual(tokenFromSubject(subject), tok);
});

test("tokenFromSubject returns null when no token present", () => {
  assert.strictEqual(tokenFromSubject("Re: random subject"), null);
  assert.strictEqual(tokenFromSubject(""), null);
});

test("findPending/markSent: find before send, null after (idempotency)", () => {
  // Isolate the JSONL path for the test via a temp HOME.
  const tmp = fsp.mkdtempSync(pathp.join(os.tmpdir(), "notify-test-"));
  const prevHome = process.env.HOME;
  process.env.HOME = tmp;            // pendingPath() derives from HOME at call time
  try {
    const tok = "AN-DEADBEEF";
    appendPending({ token: tok, to: "bob@example.com", subject: "s", body: "b", sent: false, ts: 1 });
    const found = findPending(tok);
    assert.ok(found && found.to === "bob@example.com");   // found while sent:false
    markSent(tok);
    assert.strictEqual(findPending(tok), null);           // flipped sent:true -> not re-findable
  } finally {
    process.env.HOME = prevHome;
    fsp.rmSync(tmp, { recursive: true, force: true });
  }
});
