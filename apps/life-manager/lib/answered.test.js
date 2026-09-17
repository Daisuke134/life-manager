"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { amdEnabled, shouldMarkAnswered } = require("./answered.js");
const { amdDialOptions } = require("./dial.js");
const { decodeWakeClientState, verifyTelnyxSignature } = require("./telnyx-webhook.js");

test("machine AMD result does not record answered", () => {
  assert.equal(shouldMarkAnswered({ amdEnabled: true, signal: "amd", result: "machine" }), false);
});

test("human AMD result records answered", () => {
  assert.equal(shouldMarkAnswered({ amdEnabled: true, signal: "amd", result: "human" }), true);
});

test("AMD enabled never treats media start as answered", () => {
  assert.equal(shouldMarkAnswered({ amdEnabled: true, signal: "media-start" }), false);
});

test("AMD disabled falls back to the legacy media-start approximation", () => {
  assert.equal(shouldMarkAnswered({ amdEnabled: false, signal: "media-start" }), true);
});

test("AMD is opt-in so an uncertain machine verdict cannot cut a paying caller by default", () => {
  assert.equal(amdEnabled({}), false);
  assert.equal(amdEnabled({ LM_AMD: "off" }), false);
  assert.equal(amdEnabled({ LM_AMD: "on" }), true);
});

test("not_sure is not a human-confirmed answer", () => {
  assert.equal(shouldMarkAnswered({ amdEnabled: true, signal: "amd", result: "not_sure" }), false);
});

test("AMD dial options request detection and correlate the webhook to the wake row", () => {
  const options = amdDialOptions(
    "wss://life.example/ws?wakeUid=user-1&wakeEventKey=event%3Afirm",
    { LM_AMD: "on" },
  );
  assert.equal(options.answering_machine_detection, "detect");
  assert.equal(options.webhook_url, "https://life.example/telnyx-events");
  assert.equal(options.webhook_url_method, "POST");
  assert.deepEqual(decodeWakeClientState(options.client_state), {
    wakeUid: "user-1",
    wakeEventKey: "event:firm",
  });
});

test("LM_AMD=off omits AMD dial options", () => {
  assert.deepEqual(amdDialOptions("wss://life.example/ws", { LM_AMD: "off" }), {});
});

test("Telnyx signature verifier accepts authentic fresh raw payload and rejects tampering", () => {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  const rawBody = Buffer.from('{"data":{"event_type":"call.machine.detection.ended"}}');
  const timestamp = "2000000000";
  const signed = Buffer.concat([Buffer.from(`${timestamp}|`), rawBody]);
  const signature = crypto.sign(null, signed, privateKey).toString("base64");
  const publicDer = publicKey.export({ format: "der", type: "spki" });
  const telnyxRawPublicKey = publicDer.subarray(publicDer.length - 32).toString("base64");

  assert.equal(verifyTelnyxSignature({
    rawBody, signature, timestamp, publicKey: telnyxRawPublicKey, nowMs: 2000000000 * 1000,
  }), true);
  assert.equal(verifyTelnyxSignature({
    rawBody: Buffer.from("tampered"), signature, timestamp,
    publicKey: telnyxRawPublicKey, nowMs: 2000000000 * 1000,
  }), false);
  assert.equal(verifyTelnyxSignature({
    rawBody, signature, timestamp, publicKey: telnyxRawPublicKey,
    nowMs: (2000000000 + 301) * 1000,
  }), false);
});
