// lib/transit.js — C2 (VCSDD life-manager-cost-connect-reliability): FREE Japan public-transit router
// via api.transit.ls8h.com, replacing Google Routes Pro (premium) for JP journeys to cut cost.
//
// This module is PURE decision + parse logic (the model/agent does no judgment here — JP-vs-not is a
// deterministic geo-bbox, per building-effective-ai-agents "regex/bbox for a fixed machine format = ok,
// judgment goes to the agent"). Network fetch + caching live in the caller (C3 lm_route_cache).
//
// Terms (transit.ls8h.com/terms): free, UNOFFICIAL, no SLA → the caller MUST cache + retry + fall back
// to Google; this module only shapes the response and picks the router.
"use strict";

// Japan bounding box (inclusive). Covers Okinawa (lat ~24, lon ~123) to Hokkaido/Nemuro (~45.5, ~146).
// /plan returns walk-only journeys even outside Japan (verified: NYC → 1 journey), so a returned
// journey is NOT proof of JP — the bbox is the authoritative gate.
const JP_BBOX = { latMin: 24, latMax: 46, lonMin: 122, lonMax: 146 };

function isJapanGeo(lat, lon) {
  return (
    typeof lat === "number" &&
    typeof lon === "number" &&
    lat >= JP_BBOX.latMin &&
    lat <= JP_BBOX.latMax &&
    lon >= JP_BBOX.lonMin &&
    lon <= JP_BBOX.lonMax
  );
}

// Pick the router: transit only when BOTH endpoints are inside Japan; any non-JP/mixed → Google.
function chooseRouter(fromGeo, toGeo) {
  const jp =
    fromGeo && toGeo && isJapanGeo(fromGeo.lat, fromGeo.lon) && isJapanGeo(toGeo.lat, toGeo.lon);
  return jp ? "transit" : "google";
}

function nullableNumber(value) {
  if (value == null || value === "" || (typeof value !== "number" && typeof value !== "string")) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
function nullableString(value) {
  return value == null || String(value) === "" ? null : String(value);
}
function dateKey(value) {
  const raw = String(value || "").trim().replace(/-/gu, "");
  if (!/^\d{8}$/u.test(raw)) return null;
  const year = Number(raw.slice(0, 4));
  const month = Number(raw.slice(4, 6));
  const day = Number(raw.slice(6, 8));
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? raw : null;
}
function validTimezone(value) {
  const zone = nullableString(value);
  if (!zone) return null;
  try { new Intl.DateTimeFormat("en", { timeZone: zone }).format(0); return zone; } catch { return null; }
}

function hasValidTransitEnvelope(plan) {
  const source = plan && typeof plan === "object" && !Array.isArray(plan) ? plan : {};
  return dateKey(source.date) != null && validTimezone(source.timezone) != null;
}

// Transit API times are wall-clock seconds from service-date midnight, not Unix seconds.
// Resolve that wall time in the provider timezone, including values beyond 24:00 and below 00:00.
function zonedWallInstant(date, seconds, timezone) {
  const key = dateKey(date);
  const total = nullableNumber(seconds);
  const zone = validTimezone(timezone);
  if (!key || total == null || !zone) return null;
  const wallMs = Date.UTC(Number(key.slice(0, 4)), Number(key.slice(4, 6)) - 1, Number(key.slice(6, 8))) + total * 1000;
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  let instant = wallMs;
  for (let pass = 0; pass < 3; pass += 1) {
    const parts = Object.fromEntries(formatter.formatToParts(new Date(instant))
      .filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
    const represented = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour), Number(parts.minute), Number(parts.second));
    instant = wallMs - (represented - instant);
  }
  return new Date(instant).toISOString();
}

function pickJourney(journeys, anchorType, anchorSecs) {
  let candidates = journeys.filter((journey) => journey && nullableNumber(journey.departureSecs) != null && nullableNumber(journey.arrivalSecs) != null);
  if (!candidates.length) return null;
  const anchor = nullableNumber(anchorSecs);
  if (anchorType === "arrival" && anchor != null) {
    candidates = candidates.filter((journey) => nullableNumber(journey.arrivalSecs) <= anchor)
      .sort((a, b) => nullableNumber(b.departureSecs) - nullableNumber(a.departureSecs));
  } else if (anchorType === "departure" && anchor != null) {
    candidates = candidates.filter((journey) => nullableNumber(journey.departureSecs) >= anchor)
      .sort((a, b) => nullableNumber(a.arrivalSecs) - nullableNumber(b.arrivalSecs));
  } else {
    candidates.sort((a, b) => nullableNumber(a.arrivalSecs) - nullableNumber(b.arrivalSecs));
  }
  return candidates[0] || null;
}

function normalizeFare(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const fare = { currency: nullableString(value.currency), ticket: nullableNumber(value.ticket), ic: nullableNumber(value.ic) };
  return fare.currency == null && fare.ticket == null && fare.ic == null ? null : fare;
}

function normalizeStop(value) {
  const stop = value && typeof value === "object" ? value : {};
  return { name: nullableString(stop.name), platform: nullableString(stop.platformCode === undefined ? stop.platform : stop.platformCode) };
}

function normalizeStep(leg, date, timezone) {
  const value = leg && typeof leg === "object" ? leg : {};
  const kind = value.kind === "walk" || value.kind === "transit" ? value.kind : null;
  const departureSecs = nullableNumber(value.departureSecs);
  const arrivalSecs = nullableNumber(value.arrivalSecs);
  const serviceValue = value.service !== undefined && value.service !== null ? value.service : value.routeName;
  return {
    kind,
    mode: kind === "walk" ? "walk" : ["rail", "subway", "bus", "walk"].includes(value.mode) ? value.mode : null,
    service: nullableString(serviceValue),
    trainType: nullableString(value.trainType),
    headsign: nullableString(value.headsign),
    from: normalizeStop(value.from),
    to: normalizeStop(value.to),
    departAt: zonedWallInstant(date, departureSecs, timezone),
    arriveAt: zonedWallInstant(date, arrivalSecs, timezone),
  };
}

// Parse an /api/v1/plan response into a structured, provider-fact-preserving route. The second argument
// carries the event anchor; omitting it keeps the existing duration adapter's behavior intact.
// Returns null when there are no viable journeys so the caller can fall back to Google.
function parseTransitPlan(plan, anchor = {}) {
  const source = plan && typeof plan === "object" ? plan : {};
  const journeys = Array.isArray(source.journeys) ? source.journeys : [];
  if (journeys.length === 0) return null;
  const options = anchor && typeof anchor === "object" ? anchor : {};
  const date = dateKey(source.date);
  const timezone = validTimezone(source.timezone);
  const requestedAnchorType = options.anchorType === "arrival" || options.anchorType === "departure" ? options.anchorType : null;
  const routeAnchorType = requestedAnchorType || (source.type === "arrival" || source.type === "departure" ? source.type : null);
  const anchorSecs = nullableNumber(options.anchorSecs);
  const anchored = routeAnchorType != null && anchorSecs != null;
  if (anchored && (!date || !timezone)) return null;
  const best = pickJourney(journeys, routeAnchorType, options.anchorSecs);
  if (!best) return null;

  // The provider's journey duration already includes egress (arrivalSecs is door-side arrival); only
  // access walk is added for the legacy never-late duration projection.
  const providerDuration = nullableNumber(best.durationSecs);
  const departureSecs = nullableNumber(best.departureSecs);
  const arrivalSecs = nullableNumber(best.arrivalSecs);
  const derivedDuration = providerDuration == null || providerDuration < 0
    ? (departureSecs != null && arrivalSecs != null && arrivalSecs >= departureSecs ? arrivalSecs - departureSecs : null)
    : providerDuration;
  const accessWalkSeconds = nullableNumber(best.accessWalkSecs);
  const egressWalkSeconds = nullableNumber(best.egressWalkSecs);
  const durationSeconds = derivedDuration == null ? null : derivedDuration + (accessWalkSeconds || 0);
  const legs = Array.isArray(best.legs) ? best.legs : [];
  const steps = legs.map((leg) => normalizeStep(leg, date, timezone));
  const fare = normalizeFare(best.fare);
  const hasPlatform = steps.some((step) => step.from.platform != null || step.to.platform != null);

  return {
    provider: "transit",
    computedAt: nullableString(source.computedAt !== undefined ? source.computedAt : source.computed_at),
    serviceDate: date,
    timezone,
    anchorType: routeAnchorType,
    anchorAt: zonedWallInstant(date, anchorSecs, timezone),
    departureAt: zonedWallInstant(date, departureSecs, timezone),
    arrivalAt: zonedWallInstant(date, arrivalSecs, timezone),
    durationSeconds,
    accessWalkSeconds,
    egressWalkSeconds,
    transferCount: nullableNumber(best.transferCount),
    fare,
    steps,
    availability: {
      platform: hasPlatform,
      fare: fare != null,
      stationExit: false,
    },

    // Existing callers consume this projection; keep its names and semantics while the structured route
    // above becomes the source for new callers.
    durationSecs: durationSeconds,
    inVehicleSecs: providerDuration,
    accessWalkSecs: accessWalkSeconds || 0,
    egressWalkSecs: egressWalkSeconds,
    legs: legs.map((leg) => ({
      kind: leg && leg.kind,
      mode: leg && leg.mode,
      routeName: leg && (leg.routeName !== undefined ? leg.routeName : leg.service),
      from: leg && leg.from && leg.from.name,
      to: leg && leg.to && leg.to.name,
    })),
  };
}

module.exports = { isJapanGeo, chooseRouter, parseTransitPlan, hasValidTransitEnvelope, JP_BBOX };
