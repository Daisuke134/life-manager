"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  DAILY_DRIVER_CDP,
  classifyLumaLogin,
  createCloakBrowserDailyDriver,
} = require("./cloakbrowser-daily-driver.js");

function fixture({ contexts = 1 } = {}) {
  const calls = [];
  const existingPage = { id: "existing-page" };
  const ownedPage = {
    async goto(url, options) {
      calls.push(["goto", url, options]);
    },
    async close() {
      calls.push(["close-owned-page"]);
    },
  };
  const context = {
    pages() {
      calls.push(["read-existing-pages"]);
      return [existingPage];
    },
    async newPage() {
      calls.push(["new-page"]);
      return ownedPage;
    },
  };
  const browser = {
    contexts() {
      calls.push(["contexts"]);
      return Array.from({ length: contexts }, () => context);
    },
    async close() {
      calls.push(["close-browser"]);
    },
  };
  return {
    calls,
    existingPage,
    ownedPage,
    async connectOverCDP(endpoint) {
      calls.push(["connect", endpoint]);
      return browser;
    },
  };
}

test("uses only the live :9222 shared context and closes only its own page", async () => {
  const fx = fixture();
  const driver = createCloakBrowserDailyDriver({
    connectOverCDP: fx.connectOverCDP,
  });

  const result = await driver.withLumaPage(
    "https://luma.com/tokyo-ai",
    async (page, metadata) => {
      assert.equal(page, fx.ownedPage);
      assert.deepEqual(metadata, {
        endpoint: DAILY_DRIVER_CDP,
        existing_page_count: 1,
      });
      return { status: "read-only" };
    },
  );

  assert.deepEqual(result, { status: "read-only" });
  assert.deepEqual(fx.calls, [
    ["connect", "http://localhost:9222"],
    ["contexts"],
    ["read-existing-pages"],
    ["new-page"],
    ["goto", "https://luma.com/tokyo-ai", {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    }],
    ["close-owned-page"],
  ]);
});

test("refuses another CDP port, non-Luma origins, credentials, and multiple contexts", async () => {
  assert.throws(
    () => createCloakBrowserDailyDriver({
      connectOverCDP: async () => {},
      endpoint: "http://127.0.0.1:9223",
    }),
    /daily-driver endpoint/i,
  );

  const fx = fixture();
  const driver = createCloakBrowserDailyDriver({ connectOverCDP: fx.connectOverCDP });
  await assert.rejects(
    driver.withLumaPage("https://example.com/event", async () => {}),
    /event URL/i,
  );
  await assert.rejects(
    driver.withLumaPage("https://user:secret@luma.com/event", async () => {}),
    /event URL/i,
  );

  const multiple = fixture({ contexts: 2 });
  const unsafe = createCloakBrowserDailyDriver({ connectOverCDP: multiple.connectOverCDP });
  await assert.rejects(
    unsafe.withLumaPage("https://luma.com/event", async () => {}),
    /shared context/i,
  );
});

test("always closes its own page after a task failure without closing the browser", async () => {
  const fx = fixture();
  const driver = createCloakBrowserDailyDriver({ connectOverCDP: fx.connectOverCDP });

  await assert.rejects(
    driver.withLumaPage("https://lu.ma/tokyo-ai", async () => {
      throw new Error("fixture task failed");
    }),
    /fixture task failed/,
  );
  assert.equal(fx.calls.filter(([name]) => name === "close-owned-page").length, 1);
  assert.equal(fx.calls.some(([name]) => name === "close-browser"), false);
});

test("reuses one live CDP connection across sequential Luma pages", async () => {
  const fx = fixture();
  const driver = createCloakBrowserDailyDriver({ connectOverCDP: fx.connectOverCDP });

  await driver.withLumaPage("https://luma.com/event-a", async () => ({}));
  await driver.withLumaPage("https://luma.com/event-b", async () => ({}));

  assert.equal(fx.calls.filter(([name]) => name === "connect").length, 1);
  assert.equal(fx.calls.filter(([name]) => name === "new-page").length, 2);
  assert.equal(fx.calls.filter(([name]) => name === "close-owned-page").length, 2);
  assert.equal(fx.calls.some(([name]) => name === "close-browser"), false);
});

test("captures the target baseline before opening and passes one owned-tab receipt to the task", async () => {
  const fx = fixture();
  const calls = fx.calls;
  const receipt = Object.freeze({ target_id: "OWNED" });
  const driver = createCloakBrowserDailyDriver({
    connectOverCDP: fx.connectOverCDP,
    tabOwner: {
      async captureBaseline() {
        calls.push(["capture-baseline"]);
        return ["BASELINE"];
      },
      async claim(input) {
        calls.push(["claim", input]);
        return receipt;
      },
    },
    tabOwnerReceiptPath: "/private/evidence/tab-owner.json",
  });

  await driver.withLumaPage("https://luma.com/event-a", async (_page, metadata) => {
    assert.equal(metadata.tab_owner_receipt, receipt);
  });

  assert.ok(calls.findIndex(([name]) => name === "capture-baseline") < calls.findIndex(([name]) => name === "new-page"));
  assert.deepEqual(calls.find(([name]) => name === "claim"), ["claim", {
    canonicalUrl: "https://luma.com/event-a",
    baselineTargetIds: ["BASELINE"],
    receiptPath: "/private/evidence/tab-owner.json",
  }]);
});

test("classifies Luma login without exposing page text or cookie values", () => {
  assert.deepEqual(classifyLumaLogin({
    origin: "https://luma.com",
    path: "/home",
    loginForm: false,
    authenticatedMarker: true,
    signInMarker: false,
  }), {
    status: "authenticated",
    origin: "https://luma.com",
    path: "/home",
  });
  assert.deepEqual(classifyLumaLogin({
    origin: "https://luma.com",
    path: "/signin",
    loginForm: true,
    authenticatedMarker: false,
    signInMarker: true,
  }), {
    status: "login_required",
    origin: "https://luma.com",
    path: "/signin",
  });
  assert.deepEqual(classifyLumaLogin({
    origin: "https://luma.com",
    path: "/home",
    loginForm: false,
    authenticatedMarker: false,
    signInMarker: false,
  }), {
    status: "unknown",
    origin: "https://luma.com",
    path: "/home",
  });
});

test("Docker may resolve the same :9222 owner to a private host IP but never another port", async () => {
  const fx = fixture();
  const driver = createCloakBrowserDailyDriver({
    connectOverCDP: fx.connectOverCDP,
    resolveEndpoint: async () => "http://192.168.5.2:9222",
  });
  await driver.withLumaPage("https://luma.com/event-a", async () => ({}));
  assert.deepEqual(fx.calls[0], ["connect", "http://192.168.5.2:9222"]);

  const badPort = createCloakBrowserDailyDriver({
    connectOverCDP: fx.connectOverCDP,
    resolveEndpoint: async () => "http://192.168.5.2:9223",
  });
  await assert.rejects(
    badPort.withLumaPage("https://luma.com/event-a", async () => ({})),
    /resolved endpoint/i,
  );

  const publicHost = createCloakBrowserDailyDriver({
    connectOverCDP: fx.connectOverCDP,
    resolveEndpoint: async () => "http://8.8.8.8:9222",
  });
  await assert.rejects(
    publicHost.withLumaPage("https://luma.com/event-a", async () => ({})),
    /resolved endpoint/i,
  );
});

test("uses a parent-created fenced target and releases it only after task readback", async () => {
  const fx = fixture();
  const calls = fx.calls;
  const receipt = Object.freeze({
    target_id: "PARENT_TARGET",
    owner_token: "connector-owner-token",
    generation: 1,
  });
  const driver = createCloakBrowserDailyDriver({
    connectOverCDP: fx.connectOverCDP,
    createTargetOwnership(browser) {
      calls.push(["create-target-ownership", browser === undefined ? "missing" : "browser"]);
      return {
        controller: {
          async create() {
            calls.push(["create-target"]);
            return {
              target_id: "PARENT_TARGET",
              page_websocket: "ws://localhost:9222/devtools/page/PARENT_TARGET",
              page: fx.ownedPage,
            };
          },
          async close(targetId) { calls.push(["controller-close", targetId]); return true; },
        },
        owner: {
          async claimExact(input) { calls.push(["claim-exact", input]); return receipt; },
          async heartbeat(input) { calls.push(["heartbeat", input]); return receipt; },
          async probe(input) { calls.push(["probe", input]); return true; },
          async release(input) { calls.push(["release", input]); return true; },
        },
      };
    },
    tabOwnerReceiptPath: "/private/evidence/tab-owner.json",
  });

  await driver.withLumaPage("https://luma.com/event-a", async (page, metadata) => {
    calls.push(["task-readback"]);
    assert.equal(page, fx.ownedPage);
    assert.equal(metadata.tab_owner_receipt, receipt);
  });

  assert.equal(calls.some(([name]) => name === "new-page"), false);
  assert.equal(calls.some(([name]) => name === "close-owned-page"), false);
  assert.ok(calls.findIndex(([name]) => name === "create-target") < calls.findIndex(([name]) => name === "claim-exact"));
  assert.ok(calls.findIndex(([name]) => name === "claim-exact") < calls.findIndex(([name]) => name === "goto"));
  assert.ok(calls.findIndex(([name]) => name === "task-readback") < calls.findIndex(([name]) => name === "release"));
  assert.equal(calls.filter(([name]) => name === "heartbeat").length, 2);
  assert.deepEqual(calls.find(([name]) => name === "claim-exact"), ["claim-exact", {
    canonicalUrl: "https://luma.com/event-a",
    targetId: "PARENT_TARGET",
    pageWebsocket: "ws://localhost:9222/devtools/page/PARENT_TARGET",
    receiptPath: "/private/evidence/tab-owner.json",
  }]);
});

test("uses the same parent-owned rail for a fixed Connpass host and rejects provider mismatch", async () => {
  const fx = fixture();
  const driver = createCloakBrowserDailyDriver({ connectOverCDP: fx.connectOverCDP });
  await driver.withEventPage(
    "connpass", "https://tokyo-builders.connpass.com/event/101/?ref=connector",
    async (page) => { assert.equal(page, fx.ownedPage); },
  );
  assert.deepEqual(fx.calls.find(([name]) => name === "goto").slice(0, 2), [
    "goto", "https://tokyo-builders.connpass.com/event/101/?ref=connector",
  ]);
  await assert.rejects(
    driver.withEventPage("connpass", "https://meetup.com/group/events/101", async () => {}),
    /event URL/i,
  );
  await assert.rejects(
    driver.withEventPage("unknown", "https://example.com/event", async () => {}),
    /event URL/i,
  );
});
