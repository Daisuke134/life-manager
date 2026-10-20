"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
let createMaritimeManagerStore;
try { ({ createMaritimeManagerStore } = require("./maritime-manager-store.js")); }
catch (error) { if (error.code !== "MODULE_NOT_FOUND") throw error; }
const SUBJECT_A = "11111111-1111-4111-8111-111111111111";
const SUBJECT_B = "22222222-2222-4222-8222-222222222222";
const UID_A = `lm_${SUBJECT_A}`;
const UID_B = `lm_${SUBJECT_B}`;
const SHA = "a".repeat(40);
function input(uid = UID_A, subject = SUBJECT_A) {
  return { uid, authSubject: subject, email: "person@example.invalid", timezone: "Asia/Tokyo",
    source: "referral", consentVersion: "maritime-retention-v1", releaseSha: SHA };
}
function fixture() {
  assert.equal(typeof createMaritimeManagerStore, "function", "enrollment store must exist");
  const rows = new Map(); const requests = [];
  const fetchImpl = async (url, opts = {}) => {
    const u = new URL(url); const body = JSON.parse(opts.body || "null");
    requests.push({ url: u, method: opts.method || "GET", body });
    const response = (data, status = 200) => new Response(JSON.stringify(data), { status });
    if (u.pathname.endsWith("/rpc/claim_lm_maritime_manager_provision_v1")) {
      const row = rows.get(body.p_uid);
      const claim = !!row && row.status === "pending" && !row.paused_at;
      if (claim) row.status = "provisioning";
      return response(claim);
    }
    if (u.pathname.endsWith("/rpc/bind_lm_maritime_manager_agent_v1")) {
      const row = rows.get(body.p_uid);
      if (!row || row.auth_subject !== body.p_auth_subject
        || (row.agent_id && row.agent_id !== body.p_agent_id)
        || [...rows.values()].some(r => r.uid !== body.p_uid && r.agent_id === body.p_agent_id)) return response(false);
      row.agent_id = body.p_agent_id; row.release_sha = body.p_release_sha;
      row.status = row.paused_at ? "paused" : "active";
      return response(true);
    }
    if (opts.method === "POST") {
      if (rows.has(body.uid)) return response([]);
      if ([...rows.values()].some(r => r.auth_subject === body.auth_subject)) return response({}, 409);
      const row = { ...body, auth_subject: body.auth_subject.toLowerCase(), status: "pending", agent_id: null, paused_at: null };
      rows.set(body.uid, row); return response([row]);
    }
    const uid = u.searchParams.get("uid")?.replace(/^eq\./, ""); const row = rows.get(uid);
    if (opts.method === "PATCH" && row) Object.assign(row, body);
    return response(row ? [row] : []);
  };
  return { rows, requests, store: createMaritimeManagerStore({ supaUrl: "https://database.invalid",
    supaKey: "fixture-private-key", fetchImpl, now: () => "2026-10-20T00:00:00.000Z" }) };
}

test("enrollment_is_idempotent_and_tenant_scoped", async () => {
  const { store, rows } = fixture();
  const a = await store.enroll(input()); const again = await store.enroll(input());
  assert.equal(rows.size, 1); assert.equal(a.uid, UID_A); assert.deepEqual(again, a);
  await assert.rejects(store.enroll(input(UID_A, SUBJECT_B)), /identity_mismatch/);
  assert.equal(rows.get(UID_A).auth_subject, SUBJECT_A);
});
test("only_one_concurrent_provision_claim_succeeds", async () => {
  const { store } = fixture(); await store.enroll(input());
  const claims = await Promise.all([store.claimProvision(UID_A), store.claimProvision(UID_A)]);
  assert.deepEqual(claims, [true, false]);
});
test("a_foreign_subject_or_agent_binding_is_rejected", async () => {
  const { store } = fixture(); await store.enroll(input()); await store.enroll(input(UID_B, SUBJECT_B));
  await store.claimProvision(UID_A); await store.claimProvision(UID_B);
  await store.bindAgent({ uid: UID_A, authSubject: SUBJECT_A, agentId: "agent-a", releaseSha: SHA });
  await assert.rejects(store.bindAgent({ uid: UID_B, authSubject: SUBJECT_A, agentId: "agent-b", releaseSha: SHA }), /binding_rejected/);
  await assert.rejects(store.bindAgent({ uid: UID_B, authSubject: SUBJECT_B, agentId: "agent-a", releaseSha: SHA }), /binding_rejected/);
  assert.equal((await store.read(UID_B)).agent_id, null);
});
test("pause_before_provision_blocks_claim_and_late_binding_never_reactivates", async () => {
  const { store } = fixture(); await store.enroll(input()); await store.pause(UID_A);
  assert.equal(await store.claimProvision(UID_A), false);
  await store.bindAgent({ uid: UID_A, authSubject: SUBJECT_A, agentId: "late-agent", releaseSha: SHA });
  const row = await store.read(UID_A); assert.equal(row.status, "paused"); assert.equal(row.agent_id, "late-agent");
});
test("invalid_identity_and_unconfigured_storage_do_not_dispatch", async () => {
  const { store, requests } = fixture();
  await assert.rejects(store.enroll({ ...input(), uid: "other&uid=eq.victim" }), /input_invalid/);
  await assert.rejects(store.enroll({ ...input(), timezone: "Invalid/Zone" }), /input_invalid/);
  assert.equal(requests.length, 0);
  await assert.rejects(createMaritimeManagerStore({ env: {} }).read(UID_A), /unconfigured/);
});

test("uppercase_auth_subject_matches_postgres_uuid_canonical_form", async () => {
  const { store } = fixture();
  const subject = "aabbccdd-1111-4111-8111-111111111111";
  const uid = `lm_${subject}`;
  const row = await store.enroll({ ...input(uid, subject.toUpperCase()) });
  assert.equal(row.auth_subject, subject);
  await store.claimProvision(uid);
  const bound = await store.bindAgent({ uid, authSubject: subject.toUpperCase(), agentId: "agent-upper", releaseSha: SHA });
  assert.equal(bound.agent_id, "agent-upper");
});
