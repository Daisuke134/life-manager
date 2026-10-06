#!/usr/bin/env node
// call-bridge.test.js — C1 (VCSDD life-manager-cost-connect-reliability): barge-in unit test.
// Gemini Live native-audio emits serverContent.interrupted:true when the caller speaks over Charon
// (server-side VAD). routeGeminiMessage must surface this so server.js can flush Telnyx's queued
// playback ({event:"clear"}). RED today: routeGeminiMessage has no `interrupted` branch.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createHmac } = require("node:crypto");
const { EventEmitter } = require("node:events");
const {
  routeGeminiMessage,
  buildTelnyxMediaFrame,
  decideGeminiEnd,
  carrierActionForGeminiKind,
  makeGeminiEndHandler,
} = require("./call-bridge.cjs");

// Build a handler over mutable call-scoped state, capturing the effects the real server.js injects.
function wireEndHandler({ gotAudio = false, reconnects = 0, carrierOpen = true } = {}) {
  const s = { gotAudio, reconnects, carrierOpen, reconnectCalls: 0, closeCalls: 0 };
  const handler = makeGeminiEndHandler({
    getGotAudio: () => s.gotAudio,
    getReconnects: () => s.reconnects,
    incReconnects: () => { s.reconnects++; },
    carrierOpen: () => s.carrierOpen,
    onReconnect: () => { s.reconnectCalls++; },
    onClose: () => { s.closeCalls++; },
  });
  return { handler, s };
}

test("makeGeminiEndHandler: ws error THEN close for ONE socket → reconnect once, carrier NOT closed (iteration-6 bug guard)", () => {
  const { handler, s } = wireEndHandler({ gotAudio: false, reconnects: 0, carrierOpen: true });
  handler("err boom"); // ws `error` fires
  handler("closed");   // the PAIRED `close` fires — must be a no-op (ended flag)
  assert.equal(s.reconnectCalls, 1, "exactly one reconnect");
  assert.equal(s.closeCalls, 0, "the paired close must NOT hang up the call");
  assert.equal(s.reconnects, 1, "counter incremented once");
});

test("makeGeminiEndHandler: a reconnected socket that fails again (reconnects=1) ends the call, no 2nd retry", () => {
  const { handler, s } = wireEndHandler({ gotAudio: false, reconnects: 1, carrierOpen: true });
  handler("err boom2");
  handler("closed");
  assert.equal(s.reconnectCalls, 0, "no second reconnect (≤1 total)");
  assert.equal(s.closeCalls, 1, "call ends cleanly");
});

test("makeGeminiEndHandler: a drop AFTER audio started ends cleanly, never reconnects", () => {
  const { handler, s } = wireEndHandler({ gotAudio: true, reconnects: 0, carrierOpen: true });
  handler("closed");
  assert.equal(s.reconnectCalls, 0);
  assert.equal(s.closeCalls, 1);
});

test("routeGeminiMessage: serverContent.interrupted → {kind:'interrupted'}, no audio frame sent", () => {
  const state = { streamSid: "abc123", outFrames: 0, setupComplete: true };
  const sent = [];
  const spySend = (o) => sent.push(o);

  const r = routeGeminiMessage({ serverContent: { interrupted: true } }, state, spySend, buildTelnyxMediaFrame);

  assert.deepEqual(r, { kind: "interrupted", frames: 0 });
  assert.equal(sent.length, 0); // no audio (or any) frame forwarded to the carrier for an interrupt message
});

test("carrierActionForGeminiKind: interrupted → {event:'clear'}; anything else → null", () => {
  assert.deepEqual(carrierActionForGeminiKind("interrupted"), { event: "clear" });
  assert.equal(carrierActionForGeminiKind("audio"), null);
  assert.equal(carrierActionForGeminiKind("setupComplete"), null);
  assert.equal(carrierActionForGeminiKind("other"), null);
});

test("decideGeminiEnd: reconnect ONCE on a pre-audio transient failure, then end cleanly (no infinite loop)", () => {
  // First socket end, before any audio, carrier still up → reconnect.
  assert.equal(decideGeminiEnd({ gotAudio: false, reconnects: 0, carrierOpen: true }), "reconnect");
  // The paired ws error→close double-fire OR a second failure: reconnects already 1 → close (never a 2nd retry).
  assert.equal(decideGeminiEnd({ gotAudio: false, reconnects: 1, carrierOpen: true }), "close");
  // Drop AFTER audio started → the call was live; do NOT reconnect, end cleanly.
  assert.equal(decideGeminiEnd({ gotAudio: true, reconnects: 0, carrierOpen: true }), "close");
  // Carrier already gone → nothing to reconnect for.
  assert.equal(decideGeminiEnd({ gotAudio: false, reconnects: 0, carrierOpen: false }), "close");
});

test("voice Gemini and Telnyx cost writers share one call runtime trace", async () => {
  const RealWebSocket = require("ws");
  const wsModulePath = require.resolve("ws");
  const wsModule = require.cache[wsModulePath];
  const originalWsExports = wsModule.exports;
  const serverPath = require.resolve("../server.js");
  const previousServerModule = require.cache[serverPath];
  const envKeys = [
    "GEMINI_API_KEY", "LM_CALL_SECRET", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
    "RAILWAY_SERVICE_NAME", "RAILWAY_GIT_COMMIT_SHA", "LIFE_MANAGER_LOOP_ID",
    "LIFE_MANAGER_OWNER_ID", "LIFE_MANAGER_RUN_ID", "LIFE_MANAGER_OCCURRENCE_ID",
    "LIFE_MANAGER_RELEASE_SHA",
  ];
  const originalEnv = Object.fromEntries(envKeys.map((key) => [key, process.env[key]]));
  const originalFetch = globalThis.fetch;
  const requests = [];
  let bridgeServer;
  let carrier;
  let resolveGeminiClosed;
  const geminiClosed = new Promise((resolve) => { resolveGeminiClosed = resolve; });
  class FakeGeminiSocket extends EventEmitter {
    constructor() { super(); this.readyState = RealWebSocket.CONNECTING; }
    send() {}
    close() {
      if (this.readyState === FakeGeminiSocket.CLOSED) return;
      this.readyState = FakeGeminiSocket.CLOSED;
      this.emit("close");
      resolveGeminiClosed();
    }
  }
  Object.assign(FakeGeminiSocket, {
    Server: RealWebSocket.Server,
    CONNECTING: RealWebSocket.CONNECTING,
    OPEN: RealWebSocket.OPEN,
    CLOSED: RealWebSocket.CLOSED,
  });

  try {
    process.env.GEMINI_API_KEY = "fake-gemini-key";
    process.env.LM_CALL_SECRET = "fake-call-signing-secret";
    process.env.SUPABASE_URL = "https://supa.test";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "fake-supabase-key";
    process.env.RAILWAY_SERVICE_NAME = "life-call";
    process.env.RAILWAY_GIT_COMMIT_SHA = "a".repeat(40);
    for (const key of envKeys.filter((key) => key.startsWith("LIFE_MANAGER_"))) delete process.env[key];
    globalThis.fetch = async (url, options) => {
      requests.push({ url: String(url), options });
      return { ok: true, status: 201, json: async () => ({}) };
    };
    wsModule.exports = FakeGeminiSocket;
    delete require.cache[serverPath];
    const { server } = require("../server.js");
    bridgeServer = server;
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", resolve);
    });

    const secret = process.env.LM_CALL_SECRET;
    const signature = createHmac("sha256", secret)
      .update(["", "", "", "gentle", "en", "", "voice-tenant", "", "", "", ""].join("\n"))
      .digest("base64url");
    const query = new URLSearchParams({ urgency: "gentle", lang: "en", wakeUid: "voice-tenant", sig: signature });
    carrier = new RealWebSocket(`ws://127.0.0.1:${server.address().port}/ws?${query}`);
    await new Promise((resolve, reject) => {
      carrier.once("error", reject);
      carrier.once("open", () => carrier.send(JSON.stringify({
        event: "start", start: { streamSid: "stream-fixture" },
      }), (error) => error ? reject(error) : resolve()));
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    const closed = new Promise((resolve) => carrier.once("close", resolve));
    carrier.close();
    await closed;
    await geminiClosed;

    const rows = requests
      .filter(({ url }) => url.endsWith("/rest/v1/lm_api_cost"))
      .map(({ options }) => JSON.parse(options.body));
    assert.deepEqual(rows.map((row) => row.kind).sort(), ["gemini_live", "provider_usage", "telnyx_call"]);
    const trace = rows[0].meta.runtime_trace;
    assert.ok(trace);
    assert.deepEqual(rows.map((row) => row.meta.runtime_trace), [trace, trace, trace]);
    assert.deepEqual(trace, {
      schema_version: 1,
      status: "partial",
      tenant_id: "voice-tenant",
      owner_id: "life-call-voice",
      run_id: trace.run_id,
      occurrence_id: `life-call-voice:${trace.run_id}`,
      release_sha: "a".repeat(40),
      missing_fields: ["loop_id"],
    });
    assert.match(trace.run_id, /^run-[0-9a-f-]{36}$/);
    const providerUsage = rows.find((row) => row.kind === "provider_usage");
    assert.equal(providerUsage.meta.outcome, "failure");
    assert.ok(providerUsage.est_usd > 0);
    assert.equal(providerUsage.meta.provider, "gemini");
    assert.equal(providerUsage.meta.operation, "live_api");
    assert.equal(providerUsage.meta.sku, "gemini-2.5-flash-native-audio-preview-09-2025");
    assert.equal(providerUsage.meta.currency, "USD");
    assert.equal(providerUsage.meta.actual_usd, null);
    assert.equal(providerUsage.meta.billing_status, "estimated");
    assert.equal(providerUsage.meta.pricing_version, "lm-gemini-live-duration-proxy-2026-10-06-v1");
    const legacyGemini = rows.find((row) => row.kind === "gemini_live");
    assert.equal(legacyGemini.meta.billing_status, "not_applicable");
    assert.equal(legacyGemini.meta.actual_usd, 0);
    const telnyx = rows.find((row) => row.kind === "telnyx_call");
    assert.equal(telnyx.meta.provider, "telnyx");
    assert.equal(telnyx.meta.operation, "voice_call");
    assert.equal(telnyx.meta.actual_usd, null);
    assert.equal(telnyx.meta.billing_status, "estimated");
    assert.equal(JSON.stringify(trace).includes("stream-fixture"), false);
  } finally {
    if (carrier && carrier.readyState !== RealWebSocket.CLOSED) carrier.terminate();
    if (bridgeServer && bridgeServer.listening) {
      await new Promise((resolve) => bridgeServer.close(resolve));
    }
    globalThis.fetch = originalFetch;
    for (const key of envKeys) {
      if (originalEnv[key] === undefined) delete process.env[key];
      else process.env[key] = originalEnv[key];
    }
    wsModule.exports = originalWsExports;
    if (previousServerModule) require.cache[serverPath] = previousServerModule;
    else delete require.cache[serverPath];
  }
});
