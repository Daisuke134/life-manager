"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  DEV_LOOP_LABEL,
  buildRecoverySelfBuildIssue,
  markerForRecoveryOutcome,
  processRecoveryOutcomeJournal,
} = require("./recovery-self-build-bridge.js");

const SHA = "a".repeat(40);

function outcome(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "recovery_outcome",
    intent_id: "b".repeat(32),
    loop_id: "affiliate-browser",
    owner_id: "affiliate-browser",
    occurrence_id: "affiliate-browser:run-1",
    release_sha: SHA,
    action: "reconcile_owner",
    failure_layer: "entrypoint",
    intent_reason: "owner_terminal_failure",
    state: "escalated",
    result: "escalated",
    attempt: 3,
    budget_consumed: false,
    before_event_id: "event-before",
    after_event_id: "event-after",
    command_exit_code: 1,
    readback: {
      event_id: "event-after",
      loop_id: "affiliate-browser",
      owner_id: "affiliate-browser",
      installed_release_sha: SHA,
      event_release_sha: SHA,
    },
    evidence_refs: ["lm-loop://affiliate-browser/run-1/summary.json"],
    next_action: "escalate_owner",
    next_eligible_at: null,
    observed_at: "2026-09-24T00:00:00.000Z",
    reason: "bounded_retry_budget_exhausted",
    ...overrides,
  };
}

function tempFiles(rows) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-recovery-self-build-"));
  const journalPath = path.join(root, "supervisor.jsonl");
  const cursorPath = path.join(root, "issued.jsonl");
  fs.writeFileSync(journalPath, rows.map((row) => `${JSON.stringify(row)}\n`).join(""), { mode: 0o600 });
  return { root, journalPath, cursorPath };
}

test("one terminal recovery outcome becomes a sanitized self-heal issue with exact provenance", () => {
  const value = outcome();
  const issue = buildRecoverySelfBuildIssue(value);

  assert.equal(issue.labels[0], DEV_LOOP_LABEL);
  assert.match(issue.title, /affiliate-browser/);
  assert.match(issue.body, /owner_id: affiliate-browser/);
  assert.match(issue.body, new RegExp(`release_sha: ${SHA}`));
  assert.match(issue.body, /occurrence_id: affiliate-browser:run-1/);
  assert.match(issue.body, /intent_reason: owner_terminal_failure/);
  assert.match(issue.body, /outcome_reason: bounded_retry_budget_exhausted/);
  assert.match(issue.body, /lm-loop:\/\/affiliate-browser\/run-1\/summary\.json/);
  assert.match(issue.body, /Add a retained regression fixture/);
  assert.match(issue.body, new RegExp(`<!-- ${markerForRecoveryOutcome(value)} -->`));
  assert.doesNotMatch(issue.body, /token|password|credential/i);
});

test("the bridge creates exactly one issue per intent and replay is zero", async () => {
  const value = outcome();
  const { journalPath, cursorPath } = tempFiles([
    { ...value, state: "queued", result: "queued" },
    value,
    value,
  ]);
  const calls = { create: 0, labels: [], markers: [] };
  const issueClient = {
    async ensureLabel(label) { calls.labels.push(label); },
    async findByMarker(marker) { calls.markers.push(marker); return null; },
    async create() {
      calls.create += 1;
      return { url: "https://github.com/Daisuke134/life-manager/issues/6000" };
    },
  };

  const first = await processRecoveryOutcomeJournal({ journalPath, cursorPath, issueClient });
  const second = await processRecoveryOutcomeJournal({ journalPath, cursorPath, issueClient });

  assert.equal(first.status, "issued");
  assert.equal(first.intent_id, value.intent_id);
  assert.equal(second.status, "no-op");
  assert.equal(second.reason, "no_unissued_terminal_outcome");
  assert.equal(calls.create, 1);
  assert.deepEqual(calls.labels, [DEV_LOOP_LABEL]);
  assert.deepEqual(calls.markers, [markerForRecoveryOutcome(value)]);
  const cursorRows = fs.readFileSync(cursorPath, "utf8").trim().split("\n").map(JSON.parse);
  assert.equal(cursorRows.length, 1);
  assert.equal(cursorRows[0].intent_id, value.intent_id);
  assert.equal(fs.statSync(cursorPath).mode & 0o777, 0o600);
});

test("an existing marked issue is recorded without creating a duplicate", async () => {
  const value = outcome();
  const { journalPath, cursorPath } = tempFiles([value]);
  let created = false;
  const result = await processRecoveryOutcomeJournal({
    journalPath,
    cursorPath,
    issueClient: {
      async ensureLabel() {},
      async findByMarker() {
        return { url: "https://github.com/Daisuke134/life-manager/issues/5999" };
      },
      async create() { created = true; throw new Error("must not create"); },
    },
  });

  assert.equal(result.status, "issued");
  assert.equal(result.created, false);
  assert.equal(created, false);
});

test("malformed, nonterminal and effect-held rows never become code repair issues", async () => {
  const { journalPath, cursorPath } = tempFiles([
    outcome({ intent_id: "unsafe path", state: "escalated" }),
    outcome({ intent_id: "c".repeat(32), state: "repaired", result: "repaired" }),
    outcome({ intent_id: "d".repeat(32), state: "held", result: "held" }),
  ]);
  let called = false;
  const result = await processRecoveryOutcomeJournal({
    journalPath,
    cursorPath,
    issueClient: {
      async ensureLabel() { called = true; },
      async findByMarker() { called = true; },
      async create() { called = true; },
    },
  });

  assert.deepEqual(result, { status: "no-op", reason: "no_unissued_terminal_outcome" });
  assert.equal(called, false);
});

test("an owner outside the dev agent's repair scope is never filed as a code-repair issue", async () => {
  // life-manager-anicca-* mobile publish owners live under skills/ with no registry-granted repair
  // scope (see dev-merge-guard.js repairScopeForOwner / classifyChangedPath): the dev agent cannot
  // edit them, so escalating to lm:type:self-heal would be a code-repair issue nobody can act on.
  const value = outcome({
    loop_id: "life-manager-anicca-post",
    owner_id: "life-manager-anicca-post",
    occurrence_id: "life-manager-anicca-post:run-1",
  });
  const registry = { loops: {
    "life-manager-anicca-post": {
      effect_class: "publish", provider_route: "deterministic",
      entrypoint: "skills/earn/mobile-publish/scripts/post-owner",
      cadence: { start_interval_seconds: 30 },
    },
  } };
  const { journalPath, cursorPath } = tempFiles([value]);
  let called = false;
  const result = await processRecoveryOutcomeJournal({
    journalPath, cursorPath, registry,
    issueClient: {
      async ensureLabel() { called = true; },
      async findByMarker() { called = true; },
      async create() { called = true; },
    },
  });

  assert.equal(result.status, "skipped_out_of_scope");
  assert.equal(result.intent_id, value.intent_id);
  assert.equal(result.outcome, "escalate_owner_out_of_scope");
  assert.equal(called, false);

  const cursorRows = fs.readFileSync(cursorPath, "utf8").trim().split("\n").map(JSON.parse);
  assert.equal(cursorRows.length, 1);
  assert.equal(cursorRows[0].intent_id, value.intent_id);
  assert.equal(cursorRows[0].outcome, "escalate_owner_out_of_scope");

  // Replay is zero: a second pass over the same journal must not re-attempt filing.
  const second = await processRecoveryOutcomeJournal({
    journalPath, cursorPath, registry,
    issueClient: {
      async ensureLabel() { called = true; },
      async findByMarker() { called = true; },
      async create() { called = true; },
    },
  });
  assert.equal(second.status, "no-op");
  assert.equal(called, false);
});

test("an in-scope deterministic owner is filed as a code-repair issue as before", async () => {
  const value = outcome();
  const registry = { loops: {
    "affiliate-browser": {
      effect_class: "none", provider_route: "deterministic",
      entrypoint: "skills/affiliate/affiliate",
      cadence: { start_interval_seconds: 30 },
    },
  } };
  const { journalPath, cursorPath } = tempFiles([value]);
  const result = await processRecoveryOutcomeJournal({
    journalPath,
    cursorPath,
    registry,
    issueClient: {
      async ensureLabel() {},
      async findByMarker() { return null; },
      async create() { return { url: "https://github.com/Daisuke134/life-manager/issues/6001" }; },
    },
  });

  assert.equal(result.status, "issued");
  assert.equal(result.intent_id, value.intent_id);
});
