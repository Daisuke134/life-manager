"use strict";

const DAILY_DRIVER_CDP = "http://localhost:9222";
const PROVIDER_HOSTS = Object.freeze({
  luma: Object.freeze(["luma.com", "lu.ma"]),
  connpass: Object.freeze(["connpass.com"]),
  peatix: Object.freeze(["peatix.com"]),
  meetup: Object.freeze(["meetup.com"]),
  doorkeeper: Object.freeze(["doorkeeper.jp"]),
  eventbrite: Object.freeze(["eventbrite.com"]),
});

function hostMatches(hostname, roots) {
  return roots.some((root) => hostname === root || hostname.endsWith(`.${root}`));
}

function connectorEventUrl(provider, value) {
  let url;
  try {
    url = new URL(String(value == null ? "" : value).trim());
  } catch {
    throw new Error("Connector event URL invalid");
  }
  const roots = PROVIDER_HOSTS[String(provider || "")];
  const hostname = url.hostname.toLowerCase();
  if (
    !roots
    ||
    url.protocol !== "https:"
    || url.username
    || url.password
    || !hostMatches(hostname, roots)
  ) {
    throw new Error("Connector event URL invalid");
  }
  url.hash = "";
  return url.toString();
}

function safePath(value) {
  const path = String(value == null ? "" : value).trim();
  return path.startsWith("/") && path.length <= 500 ? path : "/";
}

function classifyLumaLogin(input = {}) {
  if (input.origin !== "https://luma.com") {
    throw new Error("Luma login origin invalid");
  }
  const path = safePath(input.path);
  const loginRequired = input.loginForm === true
    || input.signInMarker === true
    || /(?:^|\/)(?:login|log-in|signin|sign-in)(?:\/|$)/i.test(path);
  const status = loginRequired
    ? "login_required"
    : input.authenticatedMarker === true
      ? "authenticated"
      : "unknown";
  return Object.freeze({ status, origin: input.origin, path });
}

function isPrivateIpv4(hostname) {
  const parts = String(hostname).split(".").map(Number);
  if (
    parts.length !== 4
    || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)
  ) return false;
  return parts[0] === 10
    || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31)
    || (parts[0] === 192 && parts[1] === 168);
}

function resolvedDailyDriverEndpoint(value) {
  let url;
  try {
    url = new URL(String(value == null ? "" : value).trim());
  } catch {
    throw new Error("CloakBrowser resolved endpoint invalid");
  }
  const hostname = url.hostname.toLowerCase();
  if (
    url.protocol !== "http:"
    || url.username
    || url.password
    || url.port !== "9222"
    || url.pathname !== "/"
    || url.search
    || url.hash
    || (hostname !== "127.0.0.1" && hostname !== "localhost" && !isPrivateIpv4(hostname))
  ) {
    throw new Error("CloakBrowser resolved endpoint invalid");
  }
  return url.origin;
}

function createCloakBrowserDailyDriver(options = {}) {
  const endpoint = String(options.endpoint || DAILY_DRIVER_CDP).trim();
  const connectOverCDP = options.connectOverCDP;
  const resolveEndpoint = options.resolveEndpoint || (async () => endpoint);
  const tabOwner = options.tabOwner || null;
  const createTargetOwnership = options.createTargetOwnership || null;
  const tabOwnerReceiptPath = options.tabOwnerReceiptPath;
  if (endpoint !== DAILY_DRIVER_CDP) {
    throw new Error("CloakBrowser daily-driver endpoint invalid");
  }
  if (typeof connectOverCDP !== "function") {
    throw new Error("CloakBrowser daily-driver connector unavailable");
  }
  if (typeof resolveEndpoint !== "function") {
    throw new Error("CloakBrowser daily-driver resolver unavailable");
  }
  if (createTargetOwnership && typeof createTargetOwnership !== "function") {
    throw new Error("Connector target ownership unavailable");
  }
  if (tabOwner && (
    typeof tabOwner.captureBaseline !== "function"
    || typeof tabOwner.claim !== "function"
  )) throw new Error("Connector tab owner unavailable");

  let browserPromise = null;
  let targetOwnershipPromise = null;
  async function liveBrowser(connectionEndpoint) {
    if (browserPromise) {
      const current = await browserPromise;
      if (typeof current.isConnected !== "function" || current.isConnected()) return current;
      browserPromise = null;
    }
    browserPromise = Promise.resolve(connectOverCDP(connectionEndpoint)).catch((error) => {
      browserPromise = null;
      throw error;
    });
    return browserPromise;
  }

  async function targetOwnership(browser) {
    if (!createTargetOwnership) return null;
    if (!targetOwnershipPromise) {
      targetOwnershipPromise = Promise.resolve(createTargetOwnership(browser)).then((rail) => {
        if (
          !rail || typeof rail !== "object"
          || !rail.controller || typeof rail.controller.create !== "function"
          || typeof rail.controller.close !== "function"
          || !rail.owner || typeof rail.owner.claimExact !== "function"
          || typeof rail.owner.heartbeat !== "function"
          || typeof rail.owner.probe !== "function"
          || typeof rail.owner.release !== "function"
        ) throw new Error("Connector target ownership unavailable");
        return rail;
      }).catch((error) => {
        targetOwnershipPromise = null;
        throw error;
      });
    }
    return targetOwnershipPromise;
  }

  async function withEventPage(provider, value, task) {
      const url = connectorEventUrl(provider, value);
      if (typeof task !== "function") {
        throw new Error("CloakBrowser daily-driver task unavailable");
      }
      const connectionEndpoint = resolvedDailyDriverEndpoint(await resolveEndpoint(endpoint));
      const browser = await liveBrowser(connectionEndpoint);
      const contexts = browser && typeof browser.contexts === "function"
        ? browser.contexts()
        : [];
      if (!Array.isArray(contexts) || contexts.length !== 1) {
        throw new Error("CloakBrowser shared context unavailable");
      }
      const context = contexts[0];
      const existingPages = typeof context.pages === "function" ? context.pages() : [];
      const ownership = await targetOwnership(browser);
      if (ownership) {
        const target = await ownership.controller.create();
        let receipt = null;
        try {
          receipt = await ownership.owner.claimExact({
            canonicalUrl: url,
            targetId: target.target_id,
            pageWebsocket: target.page_websocket,
            receiptPath: tabOwnerReceiptPath,
          });
          if (await ownership.owner.probe(receipt) !== true) {
            throw new Error("Connector owned target renderer unavailable");
          }
          await ownership.owner.heartbeat(receipt);
          await target.page.goto(url, {
            waitUntil: "domcontentloaded",
            timeout: 30_000,
          });
          const result = await task(target.page, Object.freeze({
            endpoint,
            existing_page_count: Array.isArray(existingPages) ? existingPages.length : 0,
            tab_owner_receipt: receipt,
          }));
          await ownership.owner.heartbeat(receipt);
          return result;
        } finally {
          if (receipt) await ownership.owner.release(receipt);
          else await ownership.controller.close(target.target_id);
        }
      }
      const baselineTargetIds = tabOwner ? await tabOwner.captureBaseline() : null;
      if (typeof context.newPage !== "function") {
        throw new Error("CloakBrowser shared context unavailable");
      }
      const page = await context.newPage();
      try {
        await page.goto(url, {
          waitUntil: "domcontentloaded",
          timeout: 30_000,
        });
        const tabOwnerReceipt = tabOwner ? await tabOwner.claim({
          canonicalUrl: url,
          baselineTargetIds,
          receiptPath: tabOwnerReceiptPath,
        }) : null;
        return await task(page, Object.freeze({
          endpoint,
          existing_page_count: Array.isArray(existingPages) ? existingPages.length : 0,
          ...(tabOwnerReceipt ? { tab_owner_receipt: tabOwnerReceipt } : {}),
        }));
      } finally {
        if (page && typeof page.close === "function") await page.close();
      }
  }

  return Object.freeze({
    withEventPage,
    withLumaPage(value, task) { return withEventPage("luma", value, task); },
  });
}

module.exports = {
  DAILY_DRIVER_CDP,
  classifyLumaLogin,
  connectorEventUrl,
  createCloakBrowserDailyDriver,
  resolvedDailyDriverEndpoint,
};
