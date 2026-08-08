"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildFeedbackIssue,
  claimNextFeedback,
  createGhIssueClient,
  processNextFeedback,
} = require("./feedback-to-issue.js");


const ROW = Object.freeze({
  id: "1",
  source_ref: "tg:sha256:5d078e81db0e8eb547caf6f7d3daae62",
  summary: "Calendar panel button label is confusing; please say Connect Calendar.",
  labels: ["feedback", "calendar", "panel"],
});


test("issue contract exposes only the scrubbed summary and deterministic provenance marker", () => {
  const issue = buildFeedbackIssue(ROW);
  assert.equal(
    issue.title,
    "[feedback] Calendar panel button label is confusing; please say Connect Calendar.",
  );
  assert.deepEqual(issue.labels, ["lm:type:self-heal"]);
  assert.match(issue.body, /Privacy-safe feedback/);
  assert.match(issue.body, /Connect Calendar/);
  assert.match(issue.body, /<!-- lm-feedback:tg:sha256:5d078e81db0e8eb547caf6f7d3daae62 -->/);
  for (const forbidden of ["chat_id", "user_id", "telegram", "raw_text"]) {
    assert.equal(issue.body.includes(forbidden), false);
  }
});


test("issue contract accepts a closed production error row without weakening feedback compatibility", () => {
  const issue = buildFeedbackIssue({
    id: "2",
    source_ref: "err:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    summary: "Provider timeout in calendar (calendar-read-deadline).",
    labels: ["error", "provider-timeout"],
  });
  assert.equal(issue.title, "[error] Provider timeout in calendar (calendar-read-deadline).");
  assert.deepEqual(issue.labels, ["lm:type:self-heal"]);
  assert.match(issue.body, /<!-- lm-intake:err:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->/);
});


test("dogfood product feedback preserves the required privacy-safe learning evidence in its issue", () => {
  const issue = buildFeedbackIssue({
    id: "1282",
    source_ref: "tg:sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    summary: "Feedback intake should create a product issue with measurable follow-through.",
    labels: ["feedback"],
    source_event_id: "dais-chat-2026-07-10-life-manager-tobe",
    user_segment: "dogfood",
    opportunity: "Life Manager must improve itself from Telegram feedback and production metrics.",
    desired_outcome: "product_velocity,self_improvement",
    evidence: "docs/superpowers/specs/2026-07-10-life-manager-autopilot-product-loop-design.md",
    proposed_assumption_test: "Send dogfood feedback through Telegram/intake and verify it creates or updates a GitHub issue.",
    success_metric: "issue_created_from_feedback=true; source_event_id_present=true; success_metric_present=true; evidence_present=true",
  });
  for (const field of [
    "source_event_id: dais-chat-2026-07-10-life-manager-tobe",
    "user_segment: dogfood",
    "opportunity: Life Manager must improve itself from Telegram feedback and production metrics.",
    "desired_outcome: product_velocity,self_improvement",
    "evidence: docs/superpowers/specs/2026-07-10-life-manager-autopilot-product-loop-design.md",
    "proposed_assumption_test: Send dogfood feedback through Telegram/intake and verify it creates or updates a GitHub issue.",
    "success_metric: issue_created_from_feedback=true; source_event_id_present=true; success_metric_present=true; evidence_present=true",
  ]) {
    assert.match(issue.body, new RegExp(field.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")));
  }
});


test("queue claim is concurrency-safe and reclaims only stale incomplete issues", async () => {
  const seen = [];
  const query = async (sql, params) => {
    seen.push({ sql, params });
    return { rows: [ROW] };
  };
  assert.deepEqual(await claimNextFeedback(query), ROW);
  assert.match(seen[0].sql, /FOR UPDATE SKIP LOCKED/i);
  assert.match(seen[0].sql, /issue_url IS NULL/i);
  assert.match(seen[0].sql, /updated_at < now\(\) -/i);
  assert.match(seen[0].sql, /SET status = 'issued'/i);
  assert.deepEqual(seen[0].params, []);
});


test("worker creates one D0-compatible issue and records its URL", async () => {
  const updates = [];
  const issueClient = {
    ensureLabel: async (label) => assert.equal(label, "lm:type:self-heal"),
    findByMarker: async () => null,
    create: async (issue) => {
      assert.deepEqual(issue.labels, ["lm:type:self-heal"]);
      return { url: "https://github.com/Daisuke134/life-manager/issues/1085" };
    },
  };
  const result = await processNextFeedback({
    claim: async () => ROW,
    query: async (sql, params) => {
      updates.push({ sql, params });
      return { rowCount: 1, rows: [] };
    },
    issueClient,
  });
  assert.deepEqual(result, {
    status: "issued",
    rowId: "1",
    issueUrl: "https://github.com/Daisuke134/life-manager/issues/1085",
    created: true,
  });
  assert.match(updates[0].sql, /UPDATE public\.lm_feedback_intake/i);
  assert.match(updates[0].sql, /issue_url = \$2/i);
  assert.deepEqual(updates[0].params, ["1", "https://github.com/Daisuke134/life-manager/issues/1085"]);
});


test("crash recovery reuses the marker-matched issue instead of creating a duplicate", async () => {
  let creates = 0;
  const result = await processNextFeedback({
    claim: async () => ROW,
    query: async () => ({ rowCount: 1, rows: [] }),
    issueClient: {
      ensureLabel: async () => {},
      findByMarker: async (marker) => {
        assert.equal(marker, "lm-feedback:tg:sha256:5d078e81db0e8eb547caf6f7d3daae62");
        return { url: "https://github.com/Daisuke134/life-manager/issues/1085" };
      },
      create: async () => { creates += 1; },
    },
  });
  assert.equal(creates, 0);
  assert.equal(result.created, false);
  assert.equal(result.issueUrl, "https://github.com/Daisuke134/life-manager/issues/1085");
});


test("GitHub failure releases the claim for a later retry", async () => {
  const updates = [];
  await assert.rejects(
    processNextFeedback({
      claim: async () => ROW,
      query: async (sql, params) => {
        updates.push({ sql, params });
        return { rowCount: 1, rows: [] };
      },
      issueClient: {
        ensureLabel: async () => {},
        findByMarker: async () => null,
        create: async () => { throw new Error("provider_failed"); },
      },
    }),
    /provider_failed/,
  );
  assert.match(updates[0].sql, /SET status = 'queued'/i);
  assert.deepEqual(updates[0].params, ["1"]);
});


test("GitHub adapter uses explicit repo/label argv and recovers by exact hidden marker", async () => {
  const calls = [];
  const fakeExec = (_file, args) => {
    calls.push(args);
    if (args[0] === "issue" && args[1] === "list") {
      return JSON.stringify([
        {
          url: "https://github.com/Daisuke134/life-manager/issues/1085",
          body: "<!-- lm-feedback:tg:sha256:5d078e81db0e8eb547caf6f7d3daae62 -->",
        },
      ]);
    }
    if (args[0] === "issue" && args[1] === "create") {
      return "https://github.com/Daisuke134/life-manager/issues/1086\n";
    }
    return "";
  };
  const client = createGhIssueClient({ execFileSync: fakeExec });
  await client.ensureLabel("lm:type:self-heal");
  const found = await client.findByMarker(
    "lm-feedback:tg:sha256:5d078e81db0e8eb547caf6f7d3daae62",
  );
  assert.equal(found.url, "https://github.com/Daisuke134/life-manager/issues/1085");
  const created = await client.create(buildFeedbackIssue(ROW));
  assert.equal(created.url, "https://github.com/Daisuke134/life-manager/issues/1086");
  assert.deepEqual(calls[0].slice(0, 5), [
    "label", "create", "lm:type:self-heal", "-R", "Daisuke134/life-manager",
  ]);
  assert.deepEqual(calls[1].slice(0, 4), [
    "issue", "list", "-R", "Daisuke134/life-manager",
  ]);
  assert.equal(calls[2].includes("--label"), true);
  assert.equal(calls[2].includes("lm:type:self-heal"), true);
});
