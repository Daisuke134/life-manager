// test/testcall-amd-hangup-http-contract.test.js — spec §3 row 2d: the /test-call → voicemail →
// hangup route, driven through the REAL server.js over real HTTP with a fake transport.
//
// The unit tests either side of this one prove the pieces (client_state encodes a kind; a machine is
// hung up on). They cannot prove the thing that was actually broken: /test-call placed a call with no
// client_state at all, so the detection webhook decoded null, answered "no wake context" and returned
// BEFORE any hangup could happen. That failure lived entirely in the wiring, so it is tested here —
// one POST /test-call, then the detection webhook Telnyx would really send back, carrying the exact
// client_state the dial body went out with.
//
// The fake fetch THROWS on any host or path it was not told about, which is what makes "a test call
// never writes to Supabase" a physical property of this test rather than a claim: a PATCH at
// lm_wake_log would be an unexpected fetch and would fail the test.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const crypto = require("node:crypto");
const { decodeCallClientState } = require("../lib/telnyx-webhook.js");

const TEST_PHONE = "+99900000000";

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

// Telnyx signs `${timestamp}|${rawBody}` with ed25519 and publishes the public key as raw base64 —
// the same shape createTelnyxPublicKey() accepts, so this fixture exercises the production verifier
// instead of a bypass. Without a valid signature the route 403s and proves nothing.
function telnyxKeypair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  const spki = publicKey.export({ format: "der", type: "spki" });
  return { privateKey, publicKeyBase64: spki.subarray(spki.length - 32).toString("base64") };
}

test("a /test-call that reaches voicemail is hung up on, and writes nothing", async () => {
  const keys = telnyxKeypair();
  process.env.LM_UID_SECRET = "fixture-uid-secret";
  process.env.LM_CALL_SECRET = "fixture-call-secret";
  process.env.SUPABASE_URL = "https://fixture.supabase.co";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "fixture-service-role";
  process.env.PUBLIC_WSS = "wss://life-call-fixture.up.railway.app";
  process.env.TELNYX_API_KEY = "fixture-telnyx-key";
  process.env.TELNYX_CONNECTION_ID = "fixture-connection";
  process.env.TELNYX_PHONE_NUMBER = TEST_PHONE;
  process.env.TELNYX_PUBLIC_KEY = keys.publicKeyBase64;
  process.env.LM_AMD = "on";
  process.env.LIFE_RUN_LOOPS = "false";

  const originalCreateServer = http.createServer;
  const originalFetch = global.fetch;
  let productionServer;
  http.createServer = (handler) => {
    productionServer = originalCreateServer(handler);
    return productionServer;
  };

  const dialBodies = [];
  const hangups = [];
  global.fetch = async (input, init = {}) => {
    const url = new URL(String(input));
    const method = String(init.method || "GET").toUpperCase();
    if (url.hostname === "fixture.supabase.co") {
      if (url.pathname === "/rest/v1/lm_users" && method === "GET") {
        return response(200, [{ phone: TEST_PHONE, call_language: "ja", name: "Fixture", gmail_account_id: null }]);
      }
      // Any other Supabase traffic on this route is the bug this design exists to prevent.
      throw new Error(`a test call must not touch Supabase: ${method} ${url.pathname}`);
    }
    if (url.hostname === "api.telnyx.com") {
      if (url.pathname === "/v2/balance") return response(200, { data: { balance: "10.00" } });
      if (url.pathname === "/v2/calls" && method === "POST") {
        dialBodies.push(JSON.parse(init.body));
        return response(200, { data: { call_control_id: "v2:fixture-ccid" } });
      }
      if (/^\/v2\/calls\/.+\/actions\/hangup$/.test(url.pathname) && method === "POST") {
        hangups.push(url.pathname);
        return response(200, { data: { result: "ok" } });
      }
      throw new Error(`unexpected telnyx call ${method} ${url.pathname}`);
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  };

  try {
    const serverPath = require.resolve("../server.js");
    delete require.cache[serverPath];
    require(serverPath);
    assert.ok(productionServer, "the production HTTP server must be captured");
    await new Promise((resolve) => productionServer.listen(0, "127.0.0.1", resolve));
    const origin = `http://127.0.0.1:${productionServer.address().port}`;

    const post = (path, body, headers = {}) => new Promise((resolve, reject) => {
      const raw = Buffer.from(body, "utf8");
      const request = http.request(`${origin}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json", "content-length": raw.length, ...headers },
      }, (res) => {
        let text = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => { text += chunk; });
        res.on("end", () => resolve({ status: res.statusCode, text }));
      });
      request.on("error", reject);
      request.end(raw);
    });

    // A detection webhook exactly as Telnyx sends it, signed with the fixture key.
    const detection = (payload) => {
      const body = JSON.stringify({ data: { event_type: "call.machine.detection.ended", payload } });
      const timestamp = String(Math.floor(Date.now() / 1000));
      const signature = crypto.sign(null, Buffer.concat([Buffer.from(`${timestamp}|`, "utf8"), Buffer.from(body, "utf8")]), keys.privateKey);
      return post("/telnyx-events", body, {
        "telnyx-signature-ed25519": signature.toString("base64"),
        "telnyx-timestamp": timestamp,
      });
    };

    // 1. The dashboard button. The uid signature is the same HMAC the /lm page already holds.
    const uid = "lm_fixture_uid";
    const sig = crypto.createHmac("sha256", process.env.LM_UID_SECRET).update(uid).digest("base64url");
    const placed = await post("/test-call", JSON.stringify({ uid, sig }));
    assert.equal(placed.status, 200);
    assert.equal(dialBodies.length, 1);

    // The test-call still carries a correlated client_state for the signed detection webhook.
    const clientState = dialBodies[0].client_state;
    assert.ok(clientState, "a /test-call dial body must carry a client_state");
    assert.deepEqual(decodeCallClientState(clientState), { kind: "test", testUid: uid });
    assert.equal(dialBodies[0].answering_machine_detection, "detect");

    // 3. The stream URL is signed by signCtx over a FIXED ordered array that the /ws bridge verifies
    //    with the same array. Carrying the kind in a new query item would silently change what that
    //    signature covers on one end only, so the query must stay exactly what it was.
    const streamQuery = [...new URL(dialBodies[0].stream_url).searchParams.keys()].sort();
    assert.deepEqual(streamQuery,
      ["dateTime", "lang", "location", "name", "sig", "summary", "urgency", "wakeEventKey", "wakeUid"],
      "buildStreamUrl's signed query must not gain items");

    // An AMD machine guess is recorded but never cuts off a possible human caller.
    const machine = await detection({ result: "machine", call_control_id: "v2:fixture-ccid", client_state: clientState });
    assert.equal(machine.status, 200);
    assert.equal(machine.text, "test noop");
    assert.deepEqual(hangups, []);

    // 5. A human who pressed "Call me now" and picked up is left alone.
    const human = await detection({ result: "human", call_control_id: "v2:fixture-ccid", client_state: clientState });
    assert.equal(human.status, 200);
    assert.equal(human.text, "test noop");
    assert.equal(hangups.length, 0, "a human must never be hung up on");

    // 6. A result we could not read is a parse failure, not an AMD verdict; nobody gets cut off.
    const unreadable = await detection({ result: "", call_control_id: "v2:fixture-ccid", client_state: clientState });
    assert.equal(unreadable.status, 200);
    assert.equal(unreadable.text, "test noop");
    assert.equal(hangups.length, 0);

    // 7. A call that is neither ours nor decodable still takes the old honest path — the test branch
    //    must not have widened into a catch-all that hangs up on strangers' calls.
    const foreign = await detection({ result: "machine", call_control_id: "v2:fixture-ccid", client_state: "" });
    assert.equal(foreign.status, 200);
    assert.equal(foreign.text, "no wake context");
    assert.equal(hangups.length, 0);
  } finally {
    global.fetch = originalFetch;
    http.createServer = originalCreateServer;
    if (productionServer) await new Promise((resolve) => productionServer.close(resolve));
  }
});
