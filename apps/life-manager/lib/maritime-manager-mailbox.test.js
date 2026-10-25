"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createMaritimeManagerMailboxStore, createAgentMailMailboxProvider } = require("./maritime-manager-mailbox.js");
const { createMaritimeManagerDependencies } = require("./maritime-manager-dependencies.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const SUBJECT = "11111111-1111-4111-8111-111111111111";
const CLIENT_ID = `life-manager-${UID}`;

function response(payload, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function inbox(overrides = {}) {
  return { inbox_id: "inbox-tenant-a", email: "lm-agent-a@agentmail.to", client_id: CLIENT_ID,
    created_at: "2026-10-25T12:00:00.000Z", ...overrides };
}

test("AgentMail mailbox creation is tenant-keyed and idempotent, with no tenant email sent to the provider", async () => {
  const requests = [];
  const provider = createAgentMailMailboxProvider({ apiKey: "am-secret", fetchImpl: async (url, options) => {
    requests.push({ url, options });
    return response(inbox());
  } });

  const created = await provider.createInbox({ tenantId: UID });
  assert.deepEqual(created, { provider: "agentmail", tenantId: UID, inboxId: "inbox-tenant-a",
    email: "lm-agent-a@agentmail.to", clientId: CLIENT_ID });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "https://api.agentmail.to/v0/inboxes");
  assert.equal(requests[0].options.method, "POST");
  assert.equal(requests[0].options.redirect, "error");
  assert.equal(requests[0].options.headers.authorization, "Bearer am-secret");
  assert.equal(requests[0].options.headers["content-type"], "application/json");
  assert.deepEqual(JSON.parse(requests[0].options.body), { client_id: CLIENT_ID,
    display_name: "Life Manager verification" });
  assert.equal(JSON.stringify(requests[0]).includes("@"), false);
});

test("mailbox creation marks ambiguous network and provider failures as effect unknown", async () => {
  const provider = createAgentMailMailboxProvider({ apiKey: "am-secret", fetchImpl: async () => {
    throw new Error("socket closed after request dispatch");
  } });
  await assert.rejects(provider.createInbox({ tenantId: UID }), error => {
    assert.equal(error.code, "maritime_mailbox_create_effect_unknown");
    assert.equal(error.unknownEffect, true);
    assert.equal(String(error).includes("am-secret"), false);
    return true;
  });
});

test("mailbox creation rejects an unverified domain or mismatched idempotency receipt", async () => {
  for (const payload of [inbox({ email: "lm-agent-a@attacker.example" }), inbox({ client_id: "foreign" })]) {
    const provider = createAgentMailMailboxProvider({ apiKey: "am-secret", fetchImpl: async () => response(payload) });
    await assert.rejects(provider.createInbox({ tenantId: UID }), /maritime_mailbox_provider_receipt_invalid/);
  }
});

test("tenant mailbox store provisions once and reads it back bound to the Life Manager auth subject", async () => {
  let saved = null;
  const sql = [];
  const query = async (statement, values) => {
    sql.push({ statement, values });
    if (statement.includes("SELECT")) {
      return { rows: saved && saved.uid === values[0] && saved.auth_subject === values[1] ? [saved] : [] };
    }
    if (statement.includes("INSERT")) {
      if (!saved) saved = { uid: values[0], auth_subject: values[1], inbox_id: values[2], email: values[3],
        client_id: values[4], created_at: values[5] };
      return { rows: saved.uid === values[0] ? [saved] : [] };
    }
    throw new Error("unexpected query");
  };
  let creates = 0;
  const provider = { createInbox: async input => {
    creates += 1;
    assert.deepEqual(input, { tenantId: UID });
    return { provider: "agentmail", tenantId: UID, inboxId: "inbox-tenant-a",
      email: "lm-agent-a@agentmail.to", clientId: CLIENT_ID };
  }, readCapafyVerificationCode: async () => ({ status: "not_found" }) };
  const store = createMaritimeManagerMailboxStore({ query, provider, now: () => "2026-10-25T12:00:00.000Z" });

  const first = await store.ensure({ tenantId: UID, authSubject: SUBJECT });
  const replay = await store.ensure({ tenantId: UID, authSubject: SUBJECT });
  assert.deepEqual(first, { connected: true, provider: "agentmail", tenantId: UID,
    inboxId: "inbox-tenant-a", email: "lm-agent-a@agentmail.to", clientId: CLIENT_ID });
  assert.deepEqual(replay, first);
  assert.equal(creates, 1);
  assert.equal(sql.filter(item => item.statement.includes("INSERT")).length, 1);
  assert.ok(sql.every(item => !JSON.stringify(item.values).includes("am-secret")));
});

test("tenant mailbox cannot be reused across Life Manager identities", async () => {
  const store = createMaritimeManagerMailboxStore({
    query: async () => ({ rows: [{ uid: "lm_22222222-2222-4222-8222-222222222222", auth_subject: SUBJECT,
      inbox_id: "inbox-tenant-b", email: "lm-agent-b@agentmail.to", client_id: "other", created_at: "2026-10-25T12:00:00Z" }] }),
    provider: { createInbox: async () => { throw new Error("must not provision for wrong tenant binding"); },
      readCapafyVerificationCode: async () => ({ status: "not_found" }) },
  });
  await assert.rejects(store.read({ tenantId: UID, authSubject: SUBJECT }), /maritime_mailbox_binding_invalid/);
});

test("verification reader returns only a recent Capafy OTP and never returns message content", async () => {
  const requests = [];
  const provider = createAgentMailMailboxProvider({ apiKey: "am-secret", fetchImpl: async (url, options) => {
    requests.push({ url, options });
    if (requests.length === 1) return response({ messages: [
      { message_id: "stale", from: "security@capafy.ai", subject: "Login verification code", timestamp: "2026-10-25T11:00:00Z" },
      { message_id: "foreign", from: "security@attacker.example", subject: "Login verification code", timestamp: "2026-10-25T12:01:00Z" },
      { message_id: "current", from: "security@capafy.ai", subject: "Login verification code", timestamp: "2026-10-25T12:01:00Z" },
    ] });
    return response({ message_id: "current", timestamp: "2026-10-25T12:01:00Z",
      from: "Capafy Security <security@capafy.ai>", labels: ["inbox"],
      authentication_results: { spf: "pass", spf_domain: "capafy.ai", dkim: "fail", dkim_domain: "capafy.ai",
        dmarc: "pass", dmarc_domain: "capafy.ai" }, subject: "Login verification code",
      text: "Your Capafy login verification code is 004219. Do not share this code." });
  } });

  const store = createMaritimeManagerMailboxStore({
    query: async () => ({ rows: [{ uid: UID, auth_subject: SUBJECT, inbox_id: "inbox-tenant-a",
      email: "lm-agent-a@agentmail.to", client_id: CLIENT_ID, created_at: "2026-10-25T12:00:00Z" }] }),
    provider,
  });
  const result = await store.readCapafyVerificationCode({ tenantId: UID, authSubject: SUBJECT,
    afterMs: Date.parse("2026-10-25T12:00:00Z") });
  assert.deepEqual(result, { status: "code", code: "004219" });
  assert.equal(requests.length, 2);
  assert.match(requests[0].url, /\/v0\/inboxes\/inbox-tenant-a\/messages\?limit=20$/);
  assert.match(requests[1].url, /\/v0\/inboxes\/inbox-tenant-a\/messages\/current$/);
  assert.equal(JSON.stringify(requests[0].options.headers).includes("am-secret"), true);
  assert.equal(JSON.stringify(result).includes("Capafy"), false);
  assert.equal(JSON.stringify(result).includes("Do not share"), false);
});

test("verification reader rejects ambiguous codes and non-Capafy senders", async () => {
  for (const detail of [
    { from: "security@capafy.ai", subject: "Login verification code", text: "Code 004219 or 009911" },
    { from: "security@capafy.ai.attacker.example", subject: "Login verification code", text: "Your login verification code is 004219" },
    { from: "security@capafy.ai", labels: ["inbox", "unauthenticated"], subject: "Login verification code",
      text: "Your login verification code is 004219" },
    { from: "security@capafy.ai", labels: ["inbox"],
      authentication_results: { spf: "fail", spf_domain: "attacker.example", dkim: "fail",
        dkim_domain: "attacker.example", dmarc: "fail", dmarc_domain: "attacker.example" },
      subject: "Login verification code", text: "Your login verification code is 004219" },
    { from: "security@capafy.ai", labels: ["inbox"],
      authentication_results: { spf: "pass", spf_domain: "capafy.ai" },
      subject: "Login verification code", text: "Your login verification code is " + "9".repeat(32_769) },
  ]) {
    const provider = createAgentMailMailboxProvider({ apiKey: "am-secret", fetchImpl: async (url) =>
      url.endsWith("?limit=20") ? response({ messages: [{ message_id: "message-1",
        from: "security@capafy.ai", subject: "Login verification code", timestamp: "2026-10-25T12:01:00Z" }] })
        : response({ message_id: "message-1", timestamp: "2026-10-25T12:01:00Z", labels: ["inbox"],
          authentication_results: { spf: "pass", spf_domain: "capafy.ai", dkim: "fail", dkim_domain: "capafy.ai",
            dmarc: "pass", dmarc_domain: "capafy.ai" }, ...detail }) });
    const store = createMaritimeManagerMailboxStore({
      query: async () => ({ rows: [{ uid: UID, auth_subject: SUBJECT, inbox_id: "inbox-tenant-a",
        email: "lm-agent-a@agentmail.to", client_id: CLIENT_ID, created_at: "2026-10-25T12:00:00Z" }] }), provider,
    });
    assert.deepEqual(await store.readCapafyVerificationCode({ tenantId: UID, authSubject: SUBJECT,
      afterMs: Date.parse("2026-10-25T12:00:00Z") }), { status: "not_found" });
  }
});

test("verification reader rejects a Capafy address embedded only in an attacker display name", async () => {
  const provider = createAgentMailMailboxProvider({ apiKey: "am-secret", fetchImpl: async (url) =>
    url.endsWith("?limit=20") ? response({ messages: [{ message_id: "message-1",
      from: "Security security@capafy.ai Team <attacker@example.invalid>",
      subject: "Login verification code", timestamp: "2026-10-25T12:01:00Z" }] })
      : response({ from: "Security security@capafy.ai Team <attacker@example.invalid>",
        labels: ["inbox"], authentication_results: { spf: "pass", spf_domain: "example.invalid" },
        subject: "Login verification code", text: "Your login verification code is 004219" }) });
  const store = createMaritimeManagerMailboxStore({
    query: async () => ({ rows: [{ uid: UID, auth_subject: SUBJECT, inbox_id: "inbox-tenant-a",
      email: "lm-agent-a@agentmail.to", client_id: CLIENT_ID, created_at: "2026-10-25T12:00:00Z" }] }), provider,
  });
  assert.deepEqual(await store.readCapafyVerificationCode({ tenantId: UID, authSubject: SUBJECT,
    afterMs: Date.parse("2026-10-25T12:00:00Z") }), { status: "not_found" });
});

test("verification reader treats malformed lists and detail read errors as unavailable, not empty inboxes", async () => {
  for (const fetchImpl of [
    async () => response({}),
    async url => url.endsWith("?limit=20")
      ? response({ messages: [{ message_id: "message-1", from: "security@capafy.ai",
        subject: "Login verification code", timestamp: "2026-10-25T12:01:00Z" }] })
      : response({}, 503),
    async url => url.endsWith("?limit=20")
      ? response({ messages: [{ message_id: "message-1", from: "security@capafy.ai",
        subject: "Login verification code", timestamp: "2026-10-25T12:01:00Z" }] })
      : response({}),
  ]) {
    const provider = createAgentMailMailboxProvider({ apiKey: "am-secret", fetchImpl });
    await assert.rejects(provider.readCapafyVerificationCode({ inboxId: "inbox-tenant-a",
      afterMs: Date.parse("2026-10-25T12:00:00Z") }), /maritime_mailbox_read_unavailable/);
  }
});

test("Maritime dependencies expose mailbox storage through the shared tenant database", async () => {
  const calls = [];
  const dependencies = createMaritimeManagerDependencies({
    pgPool: { async query(statement, values) { calls.push({ statement, values }); return { rows: [] }; } },
    env: { LM_UID_SECRET: "fixture-only-secret", LM_AGENTMAIL_API_KEY: "am-test-key" },
  });

  assert.ok(dependencies.managerMailboxStore);
  assert.equal(typeof dependencies.managerMailboxStore.ensure, "function");
  assert.equal(typeof dependencies.managerMailboxStore.readCapafyVerificationCode, "function");
  assert.equal(typeof dependencies.managerMailboxStore.reserveCapafyChallenge, "function");
  assert.equal(typeof dependencies.managerMailboxStore.claimCapafyChallengeVerification, "function");
  assert.equal(typeof dependencies.managerMailboxStore.renewCapafyChallengeVerification, "function");
  assert.equal(await dependencies.managerMailboxStore.read({ tenantId: UID, authSubject: SUBJECT }), null);
  assert.match(calls[0].statement, /private\.lm_maritime_manager_mailboxes/);
  assert.deepEqual(calls[0].values, [UID, SUBJECT]);
});

test("tenant mailbox challenge lifecycle uses atomic tenant-bound compare-and-set updates", async () => {
  const calls = [], outcomes = [true, false, true, true, false, true, true, true, true];
  const store = createMaritimeManagerMailboxStore({
    query: async (statement, values) => {
      calls.push({ statement, values });
      return { rows: outcomes.shift() ? [{ uid: UID }] : [] };
    },
    provider: { createInbox: async () => inbox(), readCapafyVerificationCode: async () => ({ status: "not_found" }) },
  });
  const base = { tenantId: UID, authSubject: SUBJECT, attemptId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    startedAt: "2026-10-25T12:00:00.000Z", leaseExpiresAt: "2026-10-25T12:10:00.000Z" };
  assert.equal(await store.reserveCapafyChallenge(base), true);
  assert.equal(await store.reserveCapafyChallenge(base), false);
  assert.equal(await store.bindCapafyChallenge({ ...base, challengeId: "challenge-one",
    expiresAt: "2026-10-25T12:05:00.000Z" }), true);
  assert.equal(await store.claimCapafyChallengeVerification({ tenantId: UID, authSubject: SUBJECT,
    challengeId: "challenge-one", now: "2026-10-25T12:01:00.000Z" }), true);
  assert.equal(await store.claimCapafyChallengeVerification({ tenantId: UID, authSubject: SUBJECT,
    challengeId: "challenge-one", now: "2026-10-25T12:01:00.000Z" }), false);
  assert.equal(await store.renewCapafyChallengeVerification({ tenantId: UID, authSubject: SUBJECT,
    challengeId: "challenge-one", now: "2026-10-25T12:01:00.000Z",
    leaseExpiresAt: "2026-10-25T12:03:00.000Z" }), true);
  assert.equal(await store.releaseCapafyChallengeVerification({ tenantId: UID, authSubject: SUBJECT,
    challengeId: "challenge-one" }), true);
  assert.equal(await store.claimCapafyChallengeVerification({ tenantId: UID, authSubject: SUBJECT,
    challengeId: "challenge-one", now: "2026-10-25T12:02:00.000Z" }), true);
  assert.equal(await store.completeCapafyChallenge({ tenantId: UID, authSubject: SUBJECT,
    challengeId: "challenge-one" }), true);
  assert.equal(calls.length, 9);
  assert.ok(calls.every(({ statement, values }) => /WHERE uid=\$1 AND auth_subject=\$2/.test(statement)
    && values[0] === UID && values[1] === SUBJECT));
  assert.match(calls[0].statement, /capafy_challenge_verification_lease_expires_at=NULL/);
  assert.match(calls[0].statement, /capafy_challenge_status IS NULL[\s\S]*capafy_challenge_expires_at <=/);
  assert.match(calls[3].statement, /capafy_challenge_status='pending'[\s\S]*capafy_challenge_id=\$3/);
  assert.match(calls[3].statement, /capafy_challenge_expires_at >/);
  assert.match(calls[5].statement, /capafy_challenge_verification_lease_expires_at >/);
  assert.match(calls[5].statement, /capafy_challenge_expires_at >/);
  await assert.rejects(store.reserveCapafyChallenge({ ...base,
    leaseExpiresAt: "2026-10-25T12:10:00.001Z" }), /maritime_mailbox_input_invalid/);
});
