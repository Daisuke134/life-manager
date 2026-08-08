"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createLumaBrowserProvider,
  readSavedLumaPaymentMethodOnPage,
  submitLumaOnPage,
} = require("./luma-browser-provider.js");

function eventJson(offers = { price: 0, priceCurrency: "JPY", availability: "https://schema.org/InStock" }) {
  return [{
    "@type": "Event",
    name: "Tokyo Agent Night",
    startDate: "2026-08-04T19:00:00.000+09:00",
    endDate: "2026-08-04T21:00:00.000+09:00",
    eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
    eventStatus: "https://schema.org/EventScheduled",
    location: { "@type": "Place", name: "Tokyo" },
    offers,
  }];
}

function contract() {
  return {
    tenant_id: "dais-local",
    event_ref: "luma-event://event/tokyo-agent-night",
    canonical_url: "https://luma.com/tokyo-agent-night",
  };
}

function fixture(controls, offers) {
  const calls = [];
  const page = {
    async screenshot(options) {
      calls.push(["screenshot", options]);
      return Buffer.from("png-fixture");
    },
  };
  return {
    calls,
    page,
    dailyDriver: {
      async withLumaPage(url, task) {
        calls.push(["withLumaPage", url]);
        return task(page);
      },
    },
    readRawDetail: async (seenPage, url) => {
      assert.equal(seenPage, page);
      return { canonicalUrl: url, jsonLd: eventJson(offers), controls };
    },
    evidenceStore: {
      async record(input) {
        calls.push(["record", input]);
        return {
          external_receipt_ref: "provider-receipt://luma/proof-1",
          artifact_ref: "object://sha256/" + "a".repeat(64),
        };
      },
    },
  };
}

test("inspection separates login, absence, unavailability, and existing registration", async () => {
  const login = fixture(["ログイン", "参加登録"]);
  assert.deepEqual(
    await createLumaBrowserProvider(login).inspectRegistration(contract()),
    { state: "login_required" },
  );

  const available = fixture(["参加登録"]);
  assert.deepEqual(
    await createLumaBrowserProvider(available).inspectRegistration(contract()),
    { state: "absent" },
  );

  const full = fixture(["Sold Out"]);
  assert.deepEqual(
    await createLumaBrowserProvider(full).inspectRegistration(contract()),
    { state: "unavailable", reason: "full" },
  );

  const registered = fixture(["参加予定"]);
  const proof = await createLumaBrowserProvider({
    ...registered,
    now: () => "2026-08-01T10:00:00.000Z",
  }).inspectRegistration(contract());
  assert.deepEqual(proof, {
    state: "registered",
    external_receipt_ref: "provider-receipt://luma/proof-1",
    artifact_ref: "object://sha256/" + "a".repeat(64),
    canonical_url: "https://luma.com/tokyo-agent-night",
  });
  assert.equal(registered.calls.some(([name]) => name === "record"), true);
});

test("Japanese Luma My Ticket readback is an existing registration", async () => {
  const fx = fixture(["マイチケット"]);
  const provider = createLumaBrowserProvider(fx);

  const result = await provider.inspectRegistration(contract());

  assert.equal(result.state, "registered");
  assert.equal(fx.calls.some((call) => call[0] === "record"), true);
});

test("submit rechecks the page, performs one bounded action, and records readback evidence", async () => {
  const fx = fixture(["参加登録"]);
  const provider = createLumaBrowserProvider({
    ...fx,
    now: () => "2026-08-01T10:00:00.000Z",
    submitOnPage: async (page, input) => {
      assert.equal(page, fx.page);
      assert.equal(input.event_ref, contract().event_ref);
      fx.calls.push(["submitOnPage"]);
      return { status: "registered", effect_started: true };
    },
  });

  const proof = await provider.submitRegistration(contract());
  assert.equal(proof.canonical_url, contract().canonical_url);
  assert.deepEqual(fx.calls.map(([name]) => name), [
    "withLumaPage",
    "submitOnPage",
    "screenshot",
    "record",
  ]);
});

test("pre-submit form failure remains known while post-click uncertainty is unknown", async () => {
  const known = fixture(["参加登録"]);
  const providerKnown = createLumaBrowserProvider({
    ...known,
    submitOnPage: async () => {
      const error = new Error("required questions unavailable");
      error.unknownEffect = false;
      throw error;
    },
  });
  await assert.rejects(providerKnown.submitRegistration(contract()), (error) => {
    assert.equal(error.unknownEffect, false);
    return true;
  });

  const unknown = fixture(["参加登録"]);
  const providerUnknown = createLumaBrowserProvider({
    ...unknown,
    submitOnPage: async () => ({ status: "unknown", effect_started: true }),
  });
  await assert.rejects(providerUnknown.submitRegistration(contract()), (error) => {
    assert.equal(error.unknownEffect, true);
    return true;
  });
});

test("submits the live Japanese one-click registration control", async () => {
  const calls = [];
  const control = {
    first() { return this; },
    async count() { return 1; },
    async isVisible() { return true; },
    async click() { calls.push("click"); },
  };
  const page = {
    getByRole(role, options) {
      assert.equal(role, "button");
      assert.equal(options.exact, true);
      assert.equal(options.name.test("ワンクリックで参加登録"), true);
      return control;
    },
    async waitForTimeout() {},
    async evaluate() { return { registered: true }; },
  };

  assert.deepEqual(await submitLumaOnPage(page), {
    status: "registered",
    effect_started: true,
  });
  assert.deepEqual(calls, ["click"]);
});

test("required form input after the registration click remains retryable before Apply submit", async () => {
  const register = {
    first() { return this; },
    async count() { return 1; },
    async isVisible() { return true; },
    async click() {},
  };
  const requiredInput = {
    async inputValue() { return ""; },
  };
  const dialog = {
    last() { return this; },
    async count() { return 1; },
    async isVisible() { return true; },
    locator(selector) {
      assert.equal(selector, "input[required], textarea[required], select[required]");
      return {
        async count() { return 1; },
        nth() { return requiredInput; },
      };
    },
  };
  const page = {
    getByRole(role) {
      return role === "dialog" ? dialog : register;
    },
    async waitForTimeout() {},
    async evaluate() { return { registered: false }; },
  };

  await assert.rejects(submitLumaOnPage(page), (error) => {
    assert.equal(error.code, "LUMA_FORM_INPUT_REQUIRED");
    assert.equal(error.unknownEffect, false);
    return true;
  });
});

test("paid registration cannot click without a matching verified spend authorization", async () => {
  const paidOffer = { price: 2500, priceCurrency: "JPY", availability: "https://schema.org/InStock" };
  const blocked = fixture(["参加登録"], paidOffer);
  let blockedSubmits = 0;
  const blockedProvider = createLumaBrowserProvider({
    ...blocked,
    submitOnPage: async () => { blockedSubmits += 1; },
  });
  await assert.rejects(blockedProvider.submitRegistration(contract()), (error) => {
    assert.equal(error.code, "LUMA_SPEND_AUTHORIZATION_UNAVAILABLE");
    assert.equal(error.unknownEffect, false);
    return true;
  });
  assert.equal(blockedSubmits, 0);

  const allowed = fixture(["参加登録"], paidOffer);
  const decision = Object.freeze({ opaque: "verified-by-policy-module" });
  let authorizedInput;
  const allowedProvider = createLumaBrowserProvider({
    ...allowed,
    authorizeSpendEffect(input) { authorizedInput = input; return { mode: "saved" }; },
    submitOnPage: async () => ({ status: "registered", effect_started: true }),
  });
  await allowedProvider.submitRegistration(contract(), decision);
  assert.equal(authorizedInput.decision, decision);
  assert.equal(authorizedInput.eventDetail.ticket_price_minor, 2500);
  assert.equal(authorizedInput.eventDetail.ticket_currency, "JPY");
});

test("saved payment inspection returns only a browser-side hash", async () => {
  const binding = "sha256:" + "b".repeat(64);
  const page = {
    async evaluate(task) {
      assert.equal(typeof task, "function");
      return { status: "saved", provider_binding: binding };
    },
  };
  assert.deepEqual(await readSavedLumaPaymentMethodOnPage(page), {
    status: "saved", provider_binding: binding,
  });
  await assert.rejects(readSavedLumaPaymentMethodOnPage({
    async evaluate() { return { status: "saved", provider_binding: "card-number" }; },
  }), (error) => {
    assert.equal(error.code, "LUMA_SAVED_PAYMENT_UNAVAILABLE");
    assert.equal(error.unknownEffect, false);
    return true;
  });

  const fx = fixture(["参加登録"]);
  let seenUrl;
  const provider = createLumaBrowserProvider({
    ...fx,
    dailyDriver: {
      async withLumaPage(url, task) {
        seenUrl = url;
        return task(page);
      },
    },
  });
  assert.deepEqual(await provider.inspectSavedPaymentMethod(), {
    status: "saved", provider_binding: binding,
  });
  assert.equal(seenUrl, "https://luma.com/settings/payment");
});
