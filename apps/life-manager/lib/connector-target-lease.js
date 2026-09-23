"use strict";

const { createBrowserTargetLease } = require("../../../runtime/browser/target-lease.cjs");
const { connectorPageWebsocketTargetId } = require("./connector-browser-target-controller.js");

function unavailable(message) {
  throw new Error(message || "Connector target lease unavailable");
}

function pageWebsocket(value, expectedTargetId) {
  const text = String(value || "");
  let actualTargetId;
  try { actualTargetId = connectorPageWebsocketTargetId(text); } catch {
    unavailable("Connector page websocket invalid");
  }
  if (actualTargetId !== expectedTargetId) unavailable("Connector page websocket invalid");
  return text;
}

function canonicalUrl(value) {
  let parsed;
  try { parsed = new URL(String(value || "")); } catch { unavailable("Connector canonical URL invalid"); }
  const providerHost = ["luma.com", "lu.ma", "connpass.com"].includes(parsed.hostname)
    || parsed.hostname.endsWith(".connpass.com");
  if (
    parsed.protocol !== "https:"
    || !providerHost
    || parsed.username || parsed.password || parsed.hash
  ) unavailable("Connector canonical URL invalid");
  parsed.hash = "";
  return parsed.toString();
}

function createConnectorTargetLease(options = {}) {
  return createBrowserTargetLease({
    ...options,
    validatePageWebsocket: pageWebsocket,
    validateCanonicalUrl: canonicalUrl,
  });
}

module.exports = { createConnectorTargetLease };
