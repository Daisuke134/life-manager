"use strict";

const DEFAULT_CONNECTOR_CDP_ENDPOINT = "http://localhost:9222";

function normalizeConnectorCdpEndpoint(value) {
  let parsed;
  try { parsed = new URL(String(value || "")); } catch { throw new Error("Connector browser endpoint invalid"); }
  if (
    parsed.protocol !== "http:"
    || !["127.0.0.1", "localhost", "[::1]"].includes(parsed.hostname)
    || !parsed.port
    || parsed.username || parsed.password || parsed.pathname !== "/"
    || parsed.search || parsed.hash
  ) throw new Error("Connector browser endpoint invalid");
  return parsed.origin;
}

const CONNECTOR_CDP_ENDPOINT = normalizeConnectorCdpEndpoint(
  process.env.CLOAK_CDP_BASE_URL || DEFAULT_CONNECTOR_CDP_ENDPOINT,
);
const CONNECTOR_CDP_WEBSOCKET_ORIGIN = CONNECTOR_CDP_ENDPOINT.replace(/^http:/, "ws:");

function unavailable(message) {
  throw new Error(message || "Connector browser target controller unavailable");
}

function exactTargetId(value) {
  const targetId = String(value || "");
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(targetId)) unavailable("Connector target ID invalid");
  return targetId;
}

function exactBrowserContextId(value) {
  const contextId = String(value || "").trim();
  if (!contextId) return null;
  if (!/^[A-Za-z0-9._-]{1,128}$/.test(contextId)) {
    unavailable("Connector browser context ID invalid");
  }
  return contextId;
}

function connectorPageWebsocketTargetId(value) {
  let parsed;
  try { parsed = new URL(String(value || "")); } catch { unavailable("Connector page websocket invalid"); }
  const match = /^\/devtools\/page\/([A-Za-z0-9._-]{3,128})$/.exec(parsed.pathname);
  if (
    parsed.protocol !== "ws:"
    || parsed.origin !== CONNECTOR_CDP_WEBSOCKET_ORIGIN
    || !match || parsed.username || parsed.password || parsed.search || parsed.hash
  ) unavailable("Connector page websocket invalid");
  return match[1];
}

function targetIdFromWebsocket(value) {
  return exactTargetId(connectorPageWebsocketTargetId(value));
}

function createConnectorBrowserTargetController(options = {}) {
  const browser = options.browser;
  const endpoint = String(options.endpoint || CONNECTOR_CDP_ENDPOINT);
  const browserContextId = exactBrowserContextId(
    options.browserContextId || process.env.CLOAK_BROWSER_CONTEXT_ID,
  );
  const wait = options.wait || ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
  const bindTimeoutMs = options.bindTimeoutMs == null ? 5_000 : options.bindTimeoutMs;
  if (endpoint !== CONNECTOR_CDP_ENDPOINT) unavailable("Connector browser endpoint invalid");
  if (!browser || typeof browser.contexts !== "function" || typeof browser.newBrowserCDPSession !== "function") {
    unavailable();
  }
  const contexts = browser.contexts();
  if (
    !Array.isArray(contexts)
    || contexts.length === 0
    || (!browserContextId && contexts.length !== 1)
  ) unavailable("Connector browser context unavailable");
  const defaultContext = browserContextId ? null : contexts[0];
  if (defaultContext && (
    typeof defaultContext.pages !== "function"
    || typeof defaultContext.newCDPSession !== "function"
  )) {
    unavailable("Connector browser context unavailable");
  }
  if (typeof wait !== "function" || !Number.isInteger(bindTimeoutMs) || bindTimeoutMs < 100 || bindTimeoutMs > 30_000) {
    unavailable();
  }

  function activeContexts() {
    return browserContextId ? browser.contexts() : [defaultContext];
  }

  async function targetInfoForPage(context, page) {
    const session = await context.newCDPSession(page);
    try {
      const result = await session.send("Target.getTargetInfo");
      const targetInfo = result && result.targetInfo;
      return {
        target_id: exactTargetId(targetInfo && targetInfo.targetId),
        browser_context_id: typeof (targetInfo && targetInfo.browserContextId) === "string"
          ? targetInfo.browserContextId : null,
      };
    } finally {
      if (session && typeof session.detach === "function") await session.detach();
    }
  }

  async function findPage(targetId, excludedPages = new Set()) {
    const deadline = Date.now() + bindTimeoutMs;
    do {
      const matches = [];
      for (const context of activeContexts()) {
        if (!context || typeof context.pages !== "function"
                || typeof context.newCDPSession !== "function") {
          continue;
        }
        const pages = context.pages();
        for (let index = pages.length - 1; index >= 0; index -= 1) {
          const page = pages[index];
          if (excludedPages.has(page)) continue;
          try {
            const targetInfo = await targetInfoForPage(context, page);
            if (targetInfo.target_id !== targetId) continue;
            if (browserContextId && targetInfo.browser_context_id !== browserContextId) {
              unavailable("Connector target is outside the leased browser context");
            }
            matches.push(page);
          } catch (error) {
            if (String(error && error.message).includes("outside the leased browser context")) {
              throw error;
            }
            // A disappearing unrelated page is not the owned target.
          }
        }
        if (matches.length > 0) break;
      }
      if (matches.length === 1) return matches[0];
      if (matches.length > 1) unavailable("Connector target page binding ambiguous");
      if (Date.now() >= deadline) break;
      await wait(25);
    } while (true);
    unavailable("Connector target page binding unavailable");
  }

  async function browserCall(method, params) {
    const session = await browser.newBrowserCDPSession();
    try {
      return await session.send(method, params);
    } finally {
      if (session && typeof session.detach === "function") await session.detach();
    }
  }

  return Object.freeze({
    async create() {
      const baselinePages = new Set(activeContexts().flatMap((context) => context.pages()));
      const params = { url: "about:blank" };
      if (browserContextId) params.browserContextId = browserContextId;
      const result = await browserCall("Target.createTarget", params);
      const targetId = exactTargetId(result && result.targetId);
      try {
        const page = await findPage(targetId, baselinePages);
        return Object.freeze({
          target_id: targetId,
          page_websocket: `${CONNECTOR_CDP_WEBSOCKET_ORIGIN}/devtools/page/${targetId}`,
          page,
        });
      } catch (error) {
        try { await browserCall("Target.closeTarget", { targetId }); } catch {}
        throw error;
      }
    },

    async probe(pageWebsocket) {
      const page = await findPage(targetIdFromWebsocket(pageWebsocket));
      try {
        return await page.evaluate(() => 1) === 1;
      } catch {
        return false;
      }
    },

    async close(value) {
      const targetId = exactTargetId(value);
      const inventory = await browserCall("Target.getTargets");
      if (!inventory || !Array.isArray(inventory.targetInfos)) {
        unavailable("Connector target inventory unavailable");
      }
      const targets = inventory.targetInfos.map((target) => ({
        ...target,
        targetId: exactTargetId(target && target.targetId),
      }));
      const matching = targets.filter((target) => target.targetId === targetId);
      if (matching.length === 0) return true;
      if (matching.length !== 1) unavailable("Connector target inventory ambiguous");
      if (browserContextId && matching[0].browserContextId !== browserContextId) {
        unavailable("Connector target is outside the leased browser context");
      }
      const result = await browserCall("Target.closeTarget", { targetId });
      return result && result.success === true;
    },
  });
}

module.exports = {
  CONNECTOR_CDP_ENDPOINT,
  CONNECTOR_CDP_WEBSOCKET_ORIGIN,
  connectorPageWebsocketTargetId,
  createConnectorBrowserTargetController,
};
