"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { runGenericBrowserTask, DEFAULT_ACTION_TIMEOUT_MS } = require("./generic-browser-task.js");

const JOB = Object.freeze({
  id: "job-1",
  uid: "u-1",
  telegram_chat_id: "42",
  goal: "Find a suitable free public online AI event and register contact@aniccaai.com",
  locale: "en",
});

const AUTH_JOB = Object.freeze({
  ...JOB,
  goal: "Open https://auth.example/account",
  action_kind: "browser_auth_continuity_readback",
  requires_login: true,
  principal_kind: "user_provided",
});

test("default browser timeout covers live discovery plus CUA form interaction", () => {
  assert.equal(DEFAULT_ACTION_TIMEOUT_MS, 420_000);
});

function fixture(overrides = {}) {
  const events = [];
  const deps = {
    appendTrace: async (_id, stage, meta) => {
      events.push({ stage, meta });
    },
    openSession: async () => {
      events.push({ stage: "open" });
      return { id: "steel-session-1", websocketUrl: "ws://steel-browser.railway.internal:8080/" };
    },
    discoverAndAct: async (_session, context) => {
      events.push({ stage: "driver_action" });
      await context.onSelected({
        selectedUrl: "https://events.example/ai",
        selectedOrigin: "https://events.example",
        selectionReason: "free, public, online, and matches the delegated request",
      });
      await context.onActionStarted({ action: "registered agent-owned email" });
      return {
        selectedUrl: "https://events.example/ai",
        selectedOrigin: "https://events.example",
        selectionReason: "free, public, online, and matches the delegated request",
        action: "registered agent-owned email",
        sideEffectStarted: true,
      };
    },
    readProviderReceipt: async () => {
      events.push({ stage: "driver_readback" });
      return {
        confirmed: true,
        status: "registered",
        confirmationId: "reg-123",
        currentUrl: "https://events.example/ai/confirmed",
      };
    },
    captureEvidence: async () => {
      events.push({ stage: "driver_evidence" });
      return { mimeType: "image/png", bytes: Buffer.from("cloud-png") };
    },
    releaseSession: async (id) => {
      events.push({ stage: "release", id });
      return { released: true };
    },
    sendTelegram: async (_chatId, text) => {
      events.push({ stage: "telegram", text });
      return { ok: true, result: { message_id: 9001 } };
    },
    sendTelegramEvidence: async (_chatId, evidence, caption) => {
      events.push({ stage: "telegram_evidence", evidence, caption });
      return { ok: true, result: { message_id: 9002 } };
    },
    finishJob: async (_id, terminal) => {
      events.push({ stage: "finish", terminal });
    },
    ...overrides,
  };
  return { deps, events };
}

test("discovers an unregistered site, acts once, independently reads back, reports, then releases", async () => {
  const { deps, events } = fixture();
  const result = await runGenericBrowserTask(JOB, deps);

  assert.equal(result.status, "completed");
  assert.equal(result.session_id, "steel-session-1");
  assert.equal(result.selected_url, "https://events.example/ai");
  assert.equal(result.provider_receipt.confirmation_id, "reg-123");
  assert.equal(result.telegram_message_id, "9001");
  assert.equal(result.evidence_message_id, "9002");
  assert.equal(result.steel_released, true);
  assert.deepEqual(
    events.map((event) => event.stage),
    [
      "claimed",
      "open",
      "discovery",
      "driver_action",
      "selected",
      "action_started",
      "action_observed",
      "driver_readback",
      "provider_readback",
      "driver_evidence",
      "telegram",
      "telegram_sent",
      "telegram_evidence",
      "evidence_sent",
      "release",
      "steel_released",
      "finish",
    ],
  );
});

test("the durable action kind reaches the cloud driver without entering a trace or receipt", async () => {
  let observed;
  const { deps } = fixture({
    discoverAndAct: async (_session, context) => {
      observed = context.actionKind;
      return {
        selectedUrl: "https://auth.example/account",
        selectedOrigin: "https://auth.example",
        selectionReason: "explicit provider account page",
        action: "read current authenticated provider page",
        sideEffectStarted: false,
      };
    },
  });
  const result = await runGenericBrowserTask(AUTH_JOB, deps);
  assert.equal(observed, "browser_auth_continuity_readback");
  assert.doesNotMatch(JSON.stringify(result), /action_kind|actionKind/);
});

test("a login or challenge page becomes not_applicable and releases the session", async () => {
  let releases = 0;
  const { deps } = fixture({
    discoverAndAct: async () => ({
      selectedUrl: "https://events.example/login",
      selectedOrigin: "https://events.example",
      selectionReason: "provider requires a human principal",
      action: "none",
      sideEffectStarted: false,
    }),
    readProviderReceipt: async () => ({
      confirmed: false,
      status: "login required",
      confirmationId: null,
      currentUrl: "https://events.example/login",
      handoffRequired: true,
      handoffReason: "login",
    }),
    releaseSession: async () => {
      releases += 1;
      return { released: true };
    },
  });
  const result = await runGenericBrowserTask(JOB, deps);
  assert.equal(result.status, "not_applicable");
  assert.equal(result.reason, "requires_human_principal");
  assert.equal(result.external_effect, "none");
  assert.equal(result.provider_receipt.handoff_required, true);
  assert.equal(result.provider_receipt.handoff_reason, "login");
  assert.equal(result.steel_released, true);
  assert.equal(releases, 1);
});

test("a timeout after browser execution starts is possibly_completed and releases Steel", async () => {
  let releases = 0;
  const { deps } = fixture({
    actionTimeoutMs: 5,
    discoverAndAct: async (_session, context) => {
      await context.onActionStarted({ action: "delegated action" });
      return new Promise(() => {});
    },
    releaseSession: async () => {
      releases += 1;
      return { released: true };
    },
  });
  const result = await runGenericBrowserTask(JOB, deps);
  assert.equal(result.status, "possibly_completed");
  assert.equal(releases, 1);
});

test("Telegram rejection does not erase the provider receipt or skip release and finish", async () => {
  let finished;
  let releases = 0;
  const { deps } = fixture({
    sendTelegram: async () => { throw new Error("Telegram rejected"); },
    releaseSession: async () => {
      releases += 1;
      return { released: true };
    },
    finishJob: async (_id, terminal) => { finished = terminal; },
  });
  const result = await runGenericBrowserTask(JOB, deps);
  assert.equal(result.status, "completed");
  assert.equal(result.telegram_message_id, null);
  assert.equal(releases, 1);
  assert.equal(finished.status, "completed");
});

test("a Telegram photo API rejection records null, never the string false", async () => {
  const { deps } = fixture({
    sendTelegramEvidence: async () => ({ ok: false, description: "photo dimensions invalid" }),
  });
  const result = await runGenericBrowserTask(JOB, deps);
  assert.equal(result.status, "completed");
  assert.equal(result.evidence_message_id, null);
});

test("a provider narration without independent confirmation is never completed", async () => {
  const { deps } = fixture({
    readProviderReceipt: async () => ({
      confirmed: false,
      status: "unknown",
      confirmationId: null,
      currentUrl: "https://events.example/ai",
    }),
  });
  const result = await runGenericBrowserTask(JOB, deps);
  assert.equal(result.status, "possibly_completed");
  assert.equal(result.provider_receipt.confirmed, false);
});

test("a post-action failure is possibly_completed, is never retried, and still releases Steel", async () => {
  let actionCalls = 0;
  let releases = 0;
  const error = new Error("provider page closed after click");
  error.sideEffectStarted = true;
  const { deps } = fixture({
    discoverAndAct: async () => {
      actionCalls += 1;
      throw error;
    },
    releaseSession: async () => {
      releases += 1;
      return { released: true };
    },
  });

  const result = await runGenericBrowserTask(JOB, deps);
  assert.equal(result.status, "possibly_completed");
  assert.equal(actionCalls, 1);
  assert.equal(releases, 1);
  assert.equal(result.evidence_message_id, "9002");
  assert.match(result.evidence_sha256, /^[a-f0-9]{64}$/);
});

test("a pre-action failure is an honest failure and every opened Steel session is released", async () => {
  let releases = 0;
  const { deps } = fixture({
    discoverAndAct: async () => {
      throw new Error("search unavailable");
    },
    releaseSession: async () => {
      releases += 1;
      return { released: true };
    },
  });
  const result = await runGenericBrowserTask(JOB, deps);
  assert.equal(result.status, "failed");
  assert.equal(releases, 1);
});

test("a login gate closes without human continuation and releases the live session", async () => {
  let telegramMessage = "";
  let releases = 0;
  const { deps, events } = fixture({
    discoverAndAct: async () => ({
      selectedUrl: "https://auth.example/login",
      selectedOrigin: "https://auth.example",
      selectionReason: "provider requires a human principal",
      action: "none",
      sideEffectStarted: false,
    }),
    readProviderReceipt: async () => ({
      confirmed: false,
      status: "login required",
      currentUrl: "https://auth.example/login",
      handoffRequired: true,
      handoffReason: "login",
    }),
    sendTelegram: async (_chatId, text) => {
      telegramMessage = text;
      return { ok: true, result: { message_id: 9001 } };
    },
    releaseSession: async (_id, options) => {
      releases += 1;
      return { released: true, options };
    },
  });

  const result = await runGenericBrowserTask(AUTH_JOB, deps);

  assert.equal(result.status, "not_applicable");
  assert.equal(result.provider_receipt.handoff_reason, "login");
  assert.match(telegramMessage, /excluded: requires a human principal/i);
  assert.equal(releases, 1);
  assert.equal(result.steel_released, true);
  assert.equal(events.some((event) => event.stage === "auth_context_invalidated"), false);
});

test("an auth context save failure preserves provider outcome and release without leaking its error", async () => {
  const rawSaveError = "raw-export-save-error";
  let releases = 0;
  const { deps, events } = fixture({
    releaseSession: async () => {
      releases += 1;
      return {
        released: true,
        origin: "https://auth.example",
        principal_kind: "user_provided",
        auth_context_loaded: true,
        auth_context_saved: false,
        auth_context_invalidated: false,
        context_sha256: null,
        key_version: null,
        error: rawSaveError,
      };
    },
  });

  const result = await runGenericBrowserTask(AUTH_JOB, deps);

  assert.equal(result.status, "completed");
  assert.equal(result.provider_receipt.confirmed, true);
  assert.equal(releases, 1);
  assert.equal(result.steel_released, true);
  assert.deepEqual(
    events.find((event) => event.stage === "auth_context_saved"),
    {
      stage: "auth_context_saved",
      meta: {
        origin: "https://auth.example",
        principal_kind: "user_provided",
        saved: false,
      },
    },
  );
  assert.doesNotMatch(JSON.stringify({ result, events }), new RegExp(rawSaveError));
});
