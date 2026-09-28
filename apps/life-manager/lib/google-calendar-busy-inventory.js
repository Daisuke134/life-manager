"use strict";

const { createHash } = require("node:crypto");

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const VERIFIED = new WeakSet();
const PRIVATE = new WeakMap();

function invalid() { throw new Error("Google Calendar busy inventory invalid"); }
function unavailable() { throw new Error("Google Calendar busy inventory unavailable"); }

function exactInstant(value) {
  const text = String(value == null ? "" : value).trim();
  const ms = Date.parse(text);
  if (!Number.isFinite(ms) || !/[zZ]|[+-]\d\d:\d\d$/.test(text)) invalid();
  return new Date(ms).toISOString();
}

function dateKey(value) {
  const text = String(value == null ? "" : value).trim();
  if (!DATE.test(text) || new Date(`${text}T00:00:00Z`).toISOString().slice(0, 10) !== text) invalid();
  return text;
}

function safeIdentifier(value) {
  const text = String(value == null ? "" : value).trim();
  if (!text || text.length > 1_024 || /[\x00-\x1f\x7f]/.test(text)) invalid();
  return text;
}

function validTimeZone(value) {
  const timeZone = String(value == null ? "" : value).trim();
  try { new Intl.DateTimeFormat("en", { timeZone }).format(0); } catch { invalid(); }
  return timeZone;
}

function digest(value) {
  return createHash("sha256").update(String(value), "utf8").digest("hex");
}

function privateLocation(value) {
  const text = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
  return text && text.length <= 2_000 && !/[\x00-\x1f\x7f]/.test(text) ? text : null;
}

// A Life Manager travel block, verified 2026-08-16 on the live calendar (apps/life-manager/lib/travel.js
// createTravelBlock, lines ~225 and ~229):
//   summary     : "[Travel] 🚆 新宿区南元町15-27→KOPI KALYAN Tokyo（コピカリアン トーキョー）"
//   description : "Auto-inserted by Life Manager — adjust if the route is wrong."
// Both signals are required. Either one alone stays busy: a wrongly dropped REAL commitment causes a
// double-booking, which is far worse than Connector missing one candidate slot.
const LIFE_MANAGER_TRAVEL_SUMMARY_PREFIX = "[Travel] 🚆 ";
const LIFE_MANAGER_TRAVEL_DESCRIPTION = "Auto-inserted by Life Manager — adjust if the route is wrong.";

function isLifeManagerTravelBlock(event) {
  const summary = String(event.summary == null ? "" : event.summary);
  const description = String(event.description == null ? "" : event.description).trim();
  return summary.startsWith(LIFE_MANAGER_TRAVEL_SUMMARY_PREFIX) && description === LIFE_MANAGER_TRAVEL_DESCRIPTION;
}

// Google Calendar keeps a declined invite on the calendar owner's own events.list
// response (it does not disappear), so without this check every event Dais
// declined still blocked every Connector candidate that overlapped it. Only the
// owner's OWN response matters: an event Dais organizes/attends has either no
// attendees array (personal event, implicitly accepted) or an attendees array
// where his own entry ("self": true, matching Google's own convention) is
// missing/accepted/tentative — all of those stay busy. Only an explicit
// self-declined response frees the slot; another attendee declining (or any
// other responseStatus value on Dais's own entry) never does.
function isDeclinedByOwner(event) {
  const attendees = event.attendees;
  if (attendees == null) return false;
  if (!Array.isArray(attendees)) invalid();
  const own = attendees.find((attendee) => attendee && typeof attendee === "object" && attendee.self === true);
  return Boolean(own) && String(own.responseStatus || "").toLowerCase() === "declined";
}

function connectorMarker(event) {
  if (!Object.hasOwn(event, "extendedProperties")) return null;
  const extended = event.extendedProperties;
  if (!extended || typeof extended !== "object" || Array.isArray(extended)) invalid();
  if (!Object.hasOwn(extended, "private")) return null;
  const properties = extended.private;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) invalid();
  if (!Object.hasOwn(properties, "lm_connector_event")) return null;
  const marker = properties.lm_connector_event;
  if (typeof marker !== "string" || !/^[0-9a-f]{64}$/.test(marker)) invalid();
  return marker;
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

function normalizeBusyEvent(event, calendars, seen) {
  if (!event || typeof event !== "object" || Array.isArray(event)) invalid();
  const calendarId = safeIdentifier(event.CalendarID ?? event.calendarId ?? event.calendar_id);
  const eventId = safeIdentifier(event.id);
  if (!calendars.has(calendarId)) invalid();
  const identity = `${calendarId}\n${eventId}`;
  if (seen.has(identity)) invalid();
  seen.add(identity);
  if (String(event.status || "").toLowerCase() === "cancelled") return null;
  if (String(event.transparency || "").toLowerCase() === "transparent") return null;
  if (isLifeManagerTravelBlock(event)) return null;
  if (isDeclinedByOwner(event)) return null;
  const connectorIdempotency = connectorMarker(event);
  const calendarRef = `calendar-evidence://google/calendar/${digest(calendarId)}`;
  const eventRef = `calendar-evidence://google/event/${digest(identity)}`;
  if (event.start && event.end && event.start.dateTime != null && event.end.dateTime != null) {
    const startAt = exactInstant(event.start.dateTime);
    const endAt = exactInstant(event.end.dateTime);
    if (Date.parse(endAt) <= Date.parse(startAt)) invalid();
    return Object.freeze({
      kind: "timed",
      ...(connectorIdempotency ? { connector_idempotency: connectorIdempotency } : {}),
      calendar_ref: calendarRef,
      event_ref: eventRef,
      start_at: startAt,
      end_at: endAt,
    });
  }
  if (event.start && event.end && event.start.date != null && event.end.date != null) {
    const startDate = dateKey(event.start.date);
    const endDate = dateKey(event.end.date);
    if (endDate <= startDate) invalid();
    return Object.freeze({
      kind: "all_day",
      ...(connectorIdempotency ? { connector_idempotency: connectorIdempotency } : {}),
      calendar_ref: calendarRef,
      event_ref: eventRef,
      start_date: startDate,
      end_date: endDate,
    });
  }
  invalid();
}

async function inspectGoogleCalendarBusyInventory(options = {}) {
  const calendar = options.calendar;
  if (
    !calendar
    || typeof calendar.listCalendarsRaw !== "function"
    || typeof calendar.listAllEventsRaw !== "function"
  ) invalid();
  const timeMin = exactInstant(options.timeMin);
  const timeMax = exactInstant(options.timeMax);
  const observedAt = exactInstant(options.now);
  const timeZone = validTimeZone(options.timeZone);
  if (Date.parse(timeMax) <= Date.parse(timeMin)) invalid();
  let rawCalendars;
  let rawEvents;
  try {
    rawCalendars = await calendar.listCalendarsRaw({ strict: true });
    rawEvents = await calendar.listAllEventsRaw("dais-local", {
      timeMin: options.timeMin,
      timeMax: options.timeMax,
      maxResults: 2500,
      strict: true,
    });
  } catch { unavailable(); }
  if (!Array.isArray(rawCalendars) || !Array.isArray(rawEvents)) invalid();
  const calendars = new Set();
  for (const item of rawCalendars) {
    if (!item || typeof item !== "object" || Array.isArray(item)) invalid();
    const id = safeIdentifier(item.id);
    if (calendars.has(id)) invalid();
    calendars.add(id);
  }
  const seen = new Set();
  const busyIntervals = [];
  const privateByEventRef = new Map();
  for (const event of rawEvents) {
    const interval = normalizeBusyEvent(event, calendars, seen);
    if (interval) {
      busyIntervals.push(interval);
      privateByEventRef.set(interval.event_ref, Object.freeze({ location: privateLocation(event.location) }));
    }
  }
  const core = {
    provider: "google-calendar",
    transport: "gog",
    time_zone: timeZone,
    time_min: timeMin,
    time_max: timeMax,
    observed_at: observedAt,
    calendar_count: calendars.size,
    source_event_count: rawEvents.length,
    busy_event_count: busyIntervals.length,
    excluded_event_count: rawEvents.length - busyIntervals.length,
    busy_intervals: Object.freeze(busyIntervals),
  };
  const snapshot = Object.freeze({
    busy_inventory_id: `google-calendar-busy-inventory:${digest(stableJson(core))}`,
    ...core,
  });
  VERIFIED.add(snapshot);
  PRIVATE.set(snapshot, privateByEventRef);
  return snapshot;
}

function isVerifiedGoogleCalendarBusyInventory(value) {
  return Boolean(value && typeof value === "object" && VERIFIED.has(value));
}

function privateGoogleCalendarBusyContext(snapshot, eventRef) {
  if (!isVerifiedGoogleCalendarBusyInventory(snapshot)) invalid();
  const context = PRIVATE.get(snapshot).get(String(eventRef));
  if (!context) invalid();
  return context;
}

module.exports = {
  inspectGoogleCalendarBusyInventory,
  isVerifiedGoogleCalendarBusyInventory,
  privateGoogleCalendarBusyContext,
};
