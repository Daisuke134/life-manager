"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { connectorEventUrl } = require("./cloakbrowser-daily-driver.js");
const {
  CONNECTOR_CDP_ENDPOINT,
  connectorPageWebsocketTargetId,
  exactConnectorCdpEndpoint,
} = require("./connector-browser-target-controller.js");

function normalizedEventUrl(value) {
  let parsed;
  try { parsed = new URL(value); } catch { throw new Error("Connector tab owner requires a public event URL"); }
  const providers = ["luma", "connpass", "peatix", "meetup", "doorkeeper", "eventbrite"];
  if (!providers.some((provider) => {
    try { connectorEventUrl(provider, value); return true; } catch { return false; }
  })) throw new Error("Connector tab owner requires a public event URL");
  return `${parsed.origin}${parsed.pathname.replace(/\/$/, "") || "/"}`;
}

function validPageWebsocket(value, targetId, endpoint) {
  try { return connectorPageWebsocketTargetId(value, endpoint) === targetId; } catch { return false; }
}

function isMatchingEventUrl(value, canonicalUrl) {
  try {
    return normalizedEventUrl(value) === canonicalUrl;
  } catch {
    return false;
  }
}

async function defaultListTargets(endpoint) {
  const response = await fetch(`${endpoint}/json/list`, { signal: AbortSignal.timeout(5_000) });
  if (!response.ok) throw new Error(`Connector target inventory failed with HTTP ${response.status}`);
  const targets = await response.json();
  if (!Array.isArray(targets)) throw new Error("Connector target inventory must be an array");
  return targets;
}

function writePrivateJson(filePath, value) {
  const parent = path.dirname(filePath);
  fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
  const temporary = `${filePath}.${process.pid}.${crypto.randomUUID()}.tmp`;
  try {
    fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600, flag: "wx" });
    fs.renameSync(temporary, filePath);
    fs.chmodSync(filePath, 0o600);
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

function createConnectorTabOwner(options = {}) {
  const endpoint = exactConnectorCdpEndpoint(
    options.endpoint == null ? CONNECTOR_CDP_ENDPOINT : options.endpoint,
  );
  const listTargets = options.listTargets == null
    ? () => defaultListTargets(endpoint) : options.listTargets;
  const targetLease = options.targetLease == null ? null : options.targetLease;
  const ownerToken = options.ownerToken == null ? () => crypto.randomUUID() : options.ownerToken;
  const now = options.now == null ? () => new Date() : options.now;
  if (typeof listTargets !== "function") throw new Error("listTargets is required");
  if (targetLease && typeof targetLease.claim !== "function") {
    throw new Error("Connector target lease unavailable");
  }

  return Object.freeze({
    async captureBaseline() {
      const targets = await listTargets();
      if (!Array.isArray(targets)) throw new Error("Connector target inventory must be an array");
      return Object.freeze(targets
        .filter((target) => target && target.type === "page" && typeof target.id === "string")
        .map((target) => target.id));
    },
    async claim({ canonicalUrl, baselineTargetIds = [], receiptPath } = {}) {
      const normalizedCanonicalUrl = normalizedEventUrl(canonicalUrl);
      const baseline = new Set(baselineTargetIds.map(String));
      const targets = await listTargets();
      if (!Array.isArray(targets)) throw new Error("Connector target inventory must be an array");
      const matches = targets.filter((target) => (
        target
        && target.type === "page"
        && typeof target.id === "string"
        && !baseline.has(target.id)
        && isMatchingEventUrl(target.url, normalizedCanonicalUrl)
        && validPageWebsocket(target.webSocketDebuggerUrl, target.id, endpoint)
      ));
      if (matches.length !== 1) {
        throw new Error(`Expected exactly one owned event page; observed ${matches.length}`);
      }
      const target = matches[0];
      if (targetLease) {
        const fence = await targetLease.claim({
          targetId: target.id,
          pageWebsocket: target.webSocketDebuggerUrl,
          canonicalUrl: normalizedCanonicalUrl,
        });
        if (
          !fence || fence.schema_version !== 1
          || fence.target_id !== target.id
          || fence.page_websocket !== target.webSocketDebuggerUrl
          || fence.canonical_url !== normalizedCanonicalUrl
          || typeof fence.owner_token !== "string" || fence.owner_token.length === 0
          || !Number.isInteger(fence.generation) || fence.generation < 1
          || !Number.isFinite(Date.parse(fence.claimed_at))
        ) throw new Error("Connector target lease unavailable");
        const receipt = Object.freeze({
          schema_version: 1,
          endpoint,
          owner_token: fence.owner_token,
          generation: fence.generation,
          target_id: fence.target_id,
          page_websocket: fence.page_websocket,
          baseline_target_ids: [...baseline],
          canonical_url: fence.canonical_url,
          observed_at: fence.claimed_at,
        });
        if (receiptPath !== undefined) writePrivateJson(receiptPath, receipt);
        return receipt;
      }
      const token = ownerToken();
      if (typeof token !== "string" || token.length === 0) throw new Error("Owner token is required");
      const receipt = Object.freeze({
        schema_version: 1,
        endpoint,
        owner_token: token,
        target_id: target.id,
        page_websocket: target.webSocketDebuggerUrl,
        baseline_target_ids: [...baseline],
        canonical_url: normalizedCanonicalUrl,
        observed_at: now().toISOString(),
      });
      if (receiptPath !== undefined) writePrivateJson(receiptPath, receipt);
      return receipt;
    },
    async claimExact({ canonicalUrl, targetId, pageWebsocket, receiptPath } = {}) {
      if (!targetLease) throw new Error("Connector target lease unavailable");
      const normalizedCanonicalUrl = normalizedEventUrl(canonicalUrl);
      const exactTargetId = String(targetId || "");
      if (!/^[A-Za-z0-9_-]{1,128}$/.test(exactTargetId)
        || !validPageWebsocket(pageWebsocket, exactTargetId, endpoint)) {
        throw new Error("Connector exact target unavailable");
      }
      const fence = await targetLease.claim({
        targetId: exactTargetId,
        pageWebsocket,
        canonicalUrl: normalizedCanonicalUrl,
      });
      if (
        !fence || fence.schema_version !== 1
        || fence.target_id !== exactTargetId
        || fence.page_websocket !== pageWebsocket
        || fence.canonical_url !== normalizedCanonicalUrl
        || typeof fence.owner_token !== "string" || fence.owner_token.length === 0
        || !Number.isInteger(fence.generation) || fence.generation < 1
        || !Number.isFinite(Date.parse(fence.claimed_at))
      ) throw new Error("Connector target lease unavailable");
      const receipt = Object.freeze({
        schema_version: 1,
        endpoint,
        owner_token: fence.owner_token,
        generation: fence.generation,
        target_id: fence.target_id,
        page_websocket: fence.page_websocket,
        baseline_target_ids: [],
        canonical_url: fence.canonical_url,
        observed_at: fence.claimed_at,
      });
      if (receiptPath !== undefined) writePrivateJson(receiptPath, receipt);
      return receipt;
    },
    heartbeat(fence) {
      if (!targetLease || typeof targetLease.heartbeat !== "function") {
        throw new Error("Connector target lease unavailable");
      }
      return targetLease.heartbeat(fence);
    },
    probe(fence) {
      if (!targetLease || typeof targetLease.probe !== "function") {
        throw new Error("Connector target lease unavailable");
      }
      return targetLease.probe(fence);
    },
    release(fence) {
      if (!targetLease || typeof targetLease.release !== "function") {
        throw new Error("Connector target lease unavailable");
      }
      return targetLease.release(fence);
    },
    reapStale(input) {
      if (!targetLease || typeof targetLease.reapStale !== "function") {
        throw new Error("Connector target lease unavailable");
      }
      return targetLease.reapStale(input);
    },
  });
}

module.exports = {
  CONNECTOR_CDP_ENDPOINT,
  createConnectorTabOwner,
};
