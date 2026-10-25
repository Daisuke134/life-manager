"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { main } = require("./mobile-effect-result.js");

test("slot-already-attempted result records no new provider effect", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "mobile-effect-result-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const capture = path.join(directory, "runner-output.jsonl");
  const hint = path.join(directory, "result-hint.json");
  const ownerId = "life-manager-anicca-en-affirmation-tiktok";
  const occurrenceId = `${ownerId}:slot-held`;
  fs.writeFileSync(capture, `${JSON.stringify({
    status: "slot_already_attempted",
    reason: "slot_already_attempted",
  })}\n`, { mode: 0o600 });

  main([capture, "--require-origin-occurrence"], {
    LIFE_MANAGER_LOOP_ID: ownerId,
    LIFE_MANAGER_OCCURRENCE_ID: occurrenceId,
    LIFE_MANAGER_RESULT_HINT_PATH: hint,
  });

  assert.deepEqual(JSON.parse(fs.readFileSync(hint, "utf8")), {
    schema_version: 1,
    kind: "life_manager_no_effect_result",
    status: "verified_no_effect",
    effect: 0,
    owner_id: ownerId,
    occurrence_id: occurrenceId,
    reason: "slot_already_attempted",
  });
});

test("reconciled publication binds the current result without replacing the original effect occurrence", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "mobile-effect-result-reconciled-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const capture = path.join(directory, "runner-output.jsonl");
  const hint = path.join(directory, "result-hint.json");
  const ownerId = "life-manager-anicca-en-widget-instagram";
  const occurrenceId = `${ownerId}:reconcile-2`;
  fs.writeFileSync(capture, `${JSON.stringify({
    publication: {
      created: false,
      provider_effect_created: false,
      origin_occurrence_id: `${ownerId}:publish-1`,
      result_occurrence_id: occurrenceId,
      provider_reconciled: true,
      provider_post_id: "postiz-existing-reel-1",
    },
  })}\n`, { mode: 0o600 });

  main([capture, "--require-origin-occurrence"], {
    LIFE_MANAGER_LOOP_ID: ownerId,
    LIFE_MANAGER_OCCURRENCE_ID: occurrenceId,
    LIFE_MANAGER_RESULT_HINT_PATH: hint,
  });

  assert.deepEqual(JSON.parse(fs.readFileSync(hint, "utf8")), {
    schema_version: 1,
    kind: "life_manager_effect_result",
    status: "verified_effect",
    effect: 1,
    owner_id: ownerId,
    occurrence_id: occurrenceId,
    provider: "postiz",
    provider_receipt_id: "postiz-existing-reel-1",
    effect_status: "reconciled",
  });
});
