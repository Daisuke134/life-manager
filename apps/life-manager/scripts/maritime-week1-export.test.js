"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

let buildMaritimeWeek1Packet = null;
try {
  ({ buildMaritimeWeek1Packet } = require("./maritime-week1-export.js"));
} catch (error) {
  if (error.code !== "MODULE_NOT_FOUND") throw error;
}

test("packet_uses_measured_counts_and_excludes_private_users", () => {
  assert.equal(typeof buildMaritimeWeek1Packet, "function", "T23.1 exporter must expose a packet builder");

  const status = {
    observed_at: "2026-10-21T07:01:43Z",
    public_product: {
      pilot_url: "https://life-call-production.up.railway.app/maritime?lang=en&access_token=private-token",
    },
    production: {
      life_call: { loaded_source_sha: "b".repeat(40) },
    },
    runtime_database_readback: {
      observed_at: "2026-10-21T06:50:17Z",
      identities: 1,
      enrollments: 0,
      executions: 0,
      pilot_participants: 0,
      manager_jobs: 0,
      external_work_events: 0,
      external_work_users: 0,
      verified_external_manager_users: 0,
      private_users: [{ uid: "lm_private_uid", email: "private@example.test" }],
    },
    verified_work_receipts: [{
      kind: "cycle",
      provider: "maritime",
      status: "completed",
      observed_at: "2026-10-21T06:00:00Z",
      proof_sha256: "a".repeat(64),
      uid: "lm_private_uid",
      email: "private@example.test",
      external_ref: "private-execution-reference",
    }],
    verified_costs: {
      measured: false,
      currency: "usd",
      amount_minor: 0,
      account: "private-account-reference",
    },
    submission: {
      project_submission_status: "entry_shared_in_channel; formal_submission_unconfirmed",
      formal_project_form_url: null,
      channel_entry_readback: {
        channel: "#competition-submissions",
        posted_at: "2026-10-21T05:09:07Z",
        permalink: "https://keikixmaritime.slack.com/archives/C0C9PEL45JA/p1792559347988839",
        author_handle: "keiodaisuke",
      },
      official_contact_inquiry: {
        recipient: "private@example.test",
        gmail_message_id: "private-message-id",
      },
    },
  };
  const requirements = {
    required_fields: null,
    required_fields_reason: "No official project form or required fields are published.",
  };

  const packet = buildMaritimeWeek1Packet({
    status,
    requirements,
    generatedAt: "2026-10-21T07:20:00Z",
  });

  assert.equal(packet.packet_status, "draft");
  assert.equal(packet.generated_at, "2026-10-21T07:20:00Z");
  assert.equal(packet.product_url, "https://life-call-production.up.railway.app/maritime?lang=en");
  assert.equal(packet.demo_url, null);
  assert.equal(packet.release_sha, "b".repeat(40));
  assert.equal(packet.official_required_fields, null);
  assert.deepEqual(packet.user_counts, {
    verified_external_manager_users: 0,
    external_work_events: 0,
    completed_external_work_users: 0,
    readback_at: "2026-10-21T06:50:17Z",
  });
  assert.deepEqual(packet.work_receipts, [{
    kind: "cycle",
    provider: "maritime",
    status: "completed",
    observed_at: "2026-10-21T06:00:00Z",
    proof_sha256: "a".repeat(64),
  }]);
  assert.equal(packet.costs, null);
  assert.doesNotMatch(packet.limitations.join(" "), /No completed hosted work receipt is verified\./);
  assert.deepEqual(packet.channel_entry_share, {
    channel: "#competition-submissions",
    posted_at: "2026-10-21T05:09:07Z",
    permalink: "https://keikixmaritime.slack.com/archives/C0C9PEL45JA/p1792559347988839",
  });
  assert.equal(packet.submission_receipt, null);
  assert.match(packet.limitations.join(" "), /formal submission receipt is unconfirmed/i);
  assert.match(packet.limitations.join(" "), /costs are unmeasured/i);

  const serialized = JSON.stringify(packet);
  for (const privateValue of [
    "private@example.test",
    "lm_private_uid",
    "private-execution-reference",
    "private-account-reference",
    "private-message-id",
    "access_token",
    "keiodaisuke",
  ]) assert.equal(serialized.includes(privateValue), false, `packet leaked ${privateValue}`);
});

test("non_completed_receipts_keep_missing_completed_work_caveat", () => {
  const packet = buildMaritimeWeek1Packet({
    status: {
      observed_at: "2026-10-21T08:20:00Z",
      runtime_database_readback: { verified_external_manager_users: 1 },
      verified_work_receipts: ["failed", "deferred", "effect_unknown"].map(status => ({
        provider: "maritime",
        kind: "cycle",
        status,
        observed_at: "2026-10-21T08:00:00Z",
        proof_sha256: "c".repeat(64),
      })),
    },
    requirements: { required_fields: ["project_name"] },
  });

  assert.deepEqual(packet.work_receipts.map(receipt => receipt.status), ["failed", "deferred", "effect_unknown"]);
  assert.match(packet.limitations.join(" "), /No completed hosted work receipt is verified\./);
});
