"use strict";

const { createHash } = require("node:crypto");

const { canonicalEventUrl } = require("./canonical-event-url.js");
const { isVerifiedLumaDateInventory } = require("./luma-date-inventory.js");
const { isVerifiedEventProviderDateInventory } = require("./event-provider-date-inventory.js");
const { assertVerifiedOutboundReceipt } = require("./outbound-success.js");

const VERIFIED = new WeakSet();

function invalid() { throw new Error("Connector calendar sync invalid"); }
function unavailable() { throw new Error("Connector calendar sync unavailable"); }

function safeId(value) {
  const text = String(value == null ? "" : value).trim();
  if (!text || text.length > 1_024 || /^-/.test(text) || /[\x00-\x1f\x7f]/.test(text)) invalid();
  return text;
}

function digest(value) {
  return createHash("sha256").update(String(value), "utf8").digest("hex");
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${stableJson(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
}

function googleCalendarEventUrl(url) {
  return url.protocol === "https:"
    && !url.username
    && !url.password
    && ["calendar.google.com", "www.google.com"].includes(url.hostname)
    && url.pathname === "/calendar/event"
    && Boolean(url.searchParams.get("eid"));
}

function providerEvent(value) {
  const id = safeId(value && value.id);
  let url;
  try { url = new URL(String(value && value.htmlLink || "")); } catch { unavailable(); }
  if (!googleCalendarEventUrl(url)) unavailable();
  return Object.freeze({ id, url: url.toString() });
}

function sourceEvent(input) {
  if (
    !(isVerifiedLumaDateInventory(input.dateInventory)
      || isVerifiedEventProviderDateInventory(input.dateInventory))
  ) invalid();
  const eventRef = String(input.eventRef == null ? "" : input.eventRef).trim();
  const events = input.dateInventory.days.flatMap((day) => day.events);
  const event = events.find((candidate) => candidate.event_ref === eventRef);
  if (!event) invalid();
  return event;
}

async function syncVerifiedRegistrationToGoogleCalendar(input = {}) {
  const calendar = input.calendar;
  if (
    !calendar
    || typeof calendar.findConnectorEvents !== "function"
    || typeof calendar.createConnectorEvent !== "function"
  ) invalid();
  const event = sourceEvent(input);
  let receipt;
  try { receipt = assertVerifiedOutboundReceipt(input.registrationReceipt, input.registrationJob); }
  catch { invalid(); }
  const receiptUrl = canonicalEventUrl(receipt.canonical_url);
  if (!receiptUrl || receiptUrl !== event.canonical_url) invalid();
  const calendarId = safeId(input.calendarId);
  const idempotencyValue = digest(event.canonical_url);
  const timeMin = new Date(Date.parse(event.starts_at) - 60_000).toISOString();
  const timeMax = new Date(Date.parse(event.ends_at) + 60_000).toISOString();
  let found;
  try {
    found = await calendar.findConnectorEvents({ calendarId, idempotencyValue, timeMin, timeMax });
  } catch { unavailable(); }
  if (!Array.isArray(found) || found.length > 1) unavailable();
  let provider;
  let status;
  if (found.length === 1) {
    provider = providerEvent(found[0]);
    status = "existing";
  } else {
    try {
      await calendar.createConnectorEvent({
        calendarId,
        idempotencyValue,
        title: event.title,
        startAt: event.starts_at,
        endAt: event.ends_at,
        location: event.venue_address || event.venue_name,
        canonicalUrl: event.canonical_url,
      });
    } catch { unavailable(); }
    try {
      found = await calendar.findConnectorEvents({ calendarId, idempotencyValue, timeMin, timeMax });
    } catch { unavailable(); }
    if (!Array.isArray(found) || found.length !== 1) unavailable();
    provider = providerEvent(found[0]);
    status = "created";
  }
  const core = {
    status,
    event_ref: event.event_ref,
    canonical_event_url: event.canonical_url,
    registration_receipt_ref: `runtime-receipt://outbound-event/${digest(receipt.attempt_ref + receipt.evidence_hash)}`,
    calendar_event_ref: `calendar-evidence://google/event/${digest(`${calendarId}\n${provider.id}`)}`,
    calendar_event_url: provider.url,
  };
  const result = Object.freeze({
    calendar_sync_id: `connector-calendar-sync:${digest(stableJson(core))}`,
    ...core,
  });
  VERIFIED.add(result);
  return result;
}

function isVerifiedConnectorCalendarSync(value) {
  return Boolean(value && typeof value === "object" && VERIFIED.has(value));
}

module.exports = {
  isVerifiedConnectorCalendarSync,
  syncVerifiedRegistrationToGoogleCalendar,
};
