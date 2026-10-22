// lib/travel.js — cloud travel-time auto-fill. Keep a 26h origin lookback plus the next 7d of located events and
// insert a "[Travel]" block before each one so the wake call fires before they must LEAVE. Ports
// travel/travel_fill.py to the Railway service: Google Directions for the leave time, Composio for the
// gcal read + write. Origin: nearby previous event, otherwise a high-confidence agent choice from
// saved home, repeated Calendar locations, and same-day real events; home remains the fallback.
// Idempotent: never inserts a second [Travel] for an event that already has one.
"use strict";

const { createHash, randomUUID } = require("node:crypto");
const { isDeepStrictEqual } = require("node:util");
const { getCalendar } = require("./transport/index.js");
const { chooseRouter, parseTransitPlan, hasValidTransitEnvelope } = require("./transit.js");
const {
  makeRouteCache, makeSupabaseRouteStore, cacheFailure, timeBucket,
} = require("./route-cache.js");
const {
  makeSupabaseGeocodeStore, addressDigest, isValidGeocode, GEOCODE_SUCCESS_TTL_MS,
} = require("./geocode-cache.js");
const { interpretCalendarEvent } = require("./calendar-interpreter.js");
const { computeDoorDepartureMs } = require("./travel-timing.js");
const { recordUsageEvent, usageRuntimeEnv, runtimeTrace } = require("./usage-event.js");
const { deriveAnchors } = require("./care-anchors.js");

const GOOGLE_DIRECTIONS_EST_USD = 0.005; // list price per request after free cap, checked 2026-09-06
const GOOGLE_GEOCODING_EST_USD = 0.005;
const GOOGLE_ROUTES_PRO_EST_USD = 0.010;
const ROUTE_MODES = new Set(["transit", "google"]);
const FALLBACK_REASONS = new Set([
  "transit_no_route", "transit_provider_4xx", "transit_provider_5xx", "transit_network",
  "transit_timeout", "transit_invalid_response", "non_jp",
]);
const GEOCODE_NEGATIVE_TTL_MS = 30 * 60_000;
const GEOCODE_TRANSIENT_TTL_MS = 2 * 60_000;
const ROUTING_POLICY_VERSION = "travel-routing-policy-v1";
const OPAQUE_EVENT_VERSION = /^[a-f0-9]{64}$/;
const LIFE_MANAGER_TRAVEL_DESCRIPTION = "Auto-inserted by Life Manager — adjust if the route is wrong.";
const TRAVEL_ORIGIN_LOOKBACK_MS = 26 * 60 * 60_000;
const TRAVEL_RECEIPT_MARKER = "\n\nLife Manager travel receipt: ";

function travelHash(value) {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function sourceEventVersion(event) {
  return travelHash([event.id, event.etag, event.updated, event.sequence, event.status,
    event.start, event.end, event.summary, event.location, event.description, event.recurringEventId, event.originalStartTime]);
}

function eventVersionMeta(usage) {
  const eventVersion = usage && usage.eventVersion;
  return typeof eventVersion === "string" && OPAQUE_EVENT_VERSION.test(eventVersion)
    ? { event_version: eventVersion } : {};
}

function routeUsageMeta(usage) {
  return {
    ...(ROUTE_MODES.has(usage && usage.routeMode) ? { route_mode: usage.routeMode } : {}),
    ...(FALLBACK_REASONS.has(usage && usage.fallbackReason)
      ? { fallback_reason: usage.fallbackReason } : {}),
    ...eventVersionMeta(usage),
  };
}

function setTransitFallbackReason(diagnostics, reason) {
  if (diagnostics && typeof diagnostics === "object" && diagnostics.fallbackReason == null
      && FALLBACK_REASONS.has(reason)) diagnostics.fallbackReason = reason;
}

function providerFailureClass(response, providerStatus) {
  const status = Number(response && response.status);
  if (Number.isFinite(status) && status >= 400 && status < 500) return "provider_4xx";
  if (Number.isFinite(status) && status >= 500) return "provider_5xx";
  if (providerStatus && providerStatus !== "OK") return "no_route";
  return "network";
}

async function emitUsage(options, event) {
  const injected = options && options._recordUsageEvent;
  if (!injected && (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY)) return;
  const write = injected || recordUsageEvent;
  const runtimeEnv = options && options._usageRuntimeEnv;
  try { await write(event, runtimeEnv ? { runtimeEnv } : {}); } catch { /* observability must not break routing */ }
}

function noteProviderFailure(usage, failureClass) {
  if (!usage || typeof usage !== "object") return;
  if (!Array.isArray(usage.failureClasses)) usage.failureClasses = [];
  usage.failureClasses.push(String(failureClass || "no_route"));
}

function opaqueEndpointKey(value) {
  const normalized = String(value || "").normalize("NFKC").trim().replace(/\s+/g, " ").toLowerCase();
  return createHash("sha256").update(normalized).digest("hex");
}

function routeEventVersion({ eventId, anchorAtMs, src, dst, purpose, timezone, departureMode, anchorType }) {
  return createHash("sha256").update(JSON.stringify([
    String(eventId || ""), Number(anchorAtMs) || 0,
    opaqueEndpointKey(src), opaqueEndpointKey(dst), String(purpose || "go"),
    String(timezone || "UTC"), departureMode === true, String(anchorType || "arrival"), ROUTING_POLICY_VERSION,
  ])).digest("hex");
}

// C3 (FIND-002): a process-lifetime route-result cache so the 60s scheduler tick does NOT recompute a
// route it already has (~30 paid provider calls/event → 1). Keyed on (from_geo, to_geo, time_bucket).
const _memoryRouteCache = makeRouteCache({ store: new Map(), ttlMs: 10 * 60_000 });
let _productionRouteCache = null;
let _productionRouteCacheScope = "";

function routeCacheFor(options = {}) {
  if (options._routeCache) return options._routeCache;
  const supaUrl = options.supaUrl || process.env.SUPABASE_URL;
  const supaKey = options.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supaUrl || !supaKey) return _memoryRouteCache;
  const scope = `${supaUrl}|${String(supaKey).slice(-8)}`;
  if (!_productionRouteCache || _productionRouteCacheScope !== scope) {
    _productionRouteCache = makeRouteCache({
      store: makeSupabaseRouteStore({ supaUrl, supaKey, fetchImpl: options._cacheFetch || global.fetch }),
      ttlMs: 10 * 60_000,
    });
    _productionRouteCacheScope = scope;
  }
  return _productionRouteCache;
}

function isoNaiveUTC(ms) {
  // Timezone-agnostic: pass the UTC wall clock paired with timezone:"UTC" (set in createTravelBlock).
  // Google stores the correct ABSOLUTE instant and shows it in each user's own timezone — so this
  // works for a user in Tokyo, New York, or anywhere, with no hardcoded offset.
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "").replace("Z", "");
}
function isTravel(summary) {
  const s = summary || "";
  return s.startsWith("[Travel]") || s.includes("🚆 移動");
}

function hasDeparturePopupReminder(event) {
  return Boolean(event && event.reminders && event.reminders.useDefault === false
    && Array.isArray(event.reminders.overrides)
    && event.reminders.overrides.some((reminder) => reminder && reminder.method === "popup" && reminder.minutes === 0));
}

// PURE travel decision — base geometry plus a validated, optional origin candidate. It does NOT judge whether
// an event is "online": that is the AGENT's call (agentResolveLocation, ask.js), made via prompt+tools,
// never a hardcoded keyword regex (Dais 2026-06-23: ~/.claude/rules/building-effective-ai-agents.md —
// "no brittle if-else hardcoded logic; the model decides"). An online event surfaces here as an
// un-routable location → fillTravel asks the agent, which returns kind:"online" → skipped.
// Returns { insert: boolean, origin: string|null, reason: string }.
function travelDecision(ev, prev, home, originOverride) {
  const norm = (s) => (s || "").replace(/\s+/g, "").toLowerCase();
  if (!ev || isTravel(ev.summary) || !((ev.location || "").trim())) {
    return { insert: false, origin: null, reason: "helper-or-no-location" };
  }
  // Base origin = previous real event within [0,90] min, else home. fillTravel may supply a high-confidence
  // candidate selected by the agent for longer same-day gaps; helpers and invented addresses never qualify.
  const gap = prev && prev.endMs ? ev.startMs - prev.endMs : Infinity;
  const origin = typeof originOverride === "string" && originOverride.trim() ? originOverride.trim()
    : prev && prev.location && !isTravel(prev.summary) && gap >= 0 && gap <= 90 * 60000
      ? prev.location : home;
  if (!origin) return { insert: false, origin: null, reason: "no-origin" }; // home unknown → ask-loop handles it
  if (norm(origin) === norm(ev.location)) return { insert: false, origin, reason: "same-location" }; // home→home etc.
  return { insert: true, origin, reason: "travel-needed" };
}
function shortName(addr) {
  return (addr || "").split(/[,、]/)[0].slice(0, 18) || "?";
}

async function listEvents7d(uid, apiKey, nowMs, calendar, gmailAccountId, { strict = false, expectedCalendarAccountId } = {}) {
  const cal = calendar || getCalendar({ apiKey, gmailAccountId, expectedCalendarAccountId });
  const items = await cal.listEventsRaw(uid, {
    timeMin: new Date(nowMs - TRAVEL_ORIGIN_LOOKBACK_MS).toISOString().replace(/\.\d{3}Z$/, "Z"),
    timeMax: new Date(nowMs + 7 * 86400 * 1000).toISOString().replace(/\.\d{3}Z$/, "Z"),
    ...(strict ? { strict: true } : {}),
    ...(expectedCalendarAccountId ? { expectedCalendarAccountId } : {}),
  });
  return items.filter((e) => !["no_call", "online"].includes(interpretCalendarEvent(e).decision)).map((e) => ({
    id: e.id || "",                                   // C-H1: stable per-event key for the atomic claim ledger
    summary: e.summary || "",
    location: e.location || "",
    sourceEventVersion: sourceEventVersion(e),
    ...(isTravel(e.summary) && (e.description === LIFE_MANAGER_TRAVEL_DESCRIPTION
      || String(e.description || "").startsWith(`${LIFE_MANAGER_TRAVEL_DESCRIPTION}${TRAVEL_RECEIPT_MARKER}`)
        && OPAQUE_EVENT_VERSION.test(String(e.description).slice(`${LIFE_MANAGER_TRAVEL_DESCRIPTION}${TRAVEL_RECEIPT_MARKER}`.length)))
      ? { lifeManagerGeneratedTravel: true } : {}),
    startIso: (e.start || {}).dateTime || "",
    timezone: (e.start || {}).timeZone || e.timeZone || e.timezone || "",
    reminders: e.reminders && typeof e.reminders === "object" ? {
      useDefault: e.reminders.useDefault === true,
      overrides: Array.isArray(e.reminders.overrides) ? e.reminders.overrides
        .filter((reminder) => reminder && typeof reminder === "object")
        .map((reminder) => ({ method: reminder.method || "",
          minutes: reminder.minutes == null ? null : Number(reminder.minutes) })) : [],
    } : null,
    startMs: Date.parse((e.start || {}).dateTime || ""),
    endMs: Date.parse((e.end || {}).dateTime || ""),
  })).filter((e) => Number.isFinite(e.startMs));
}

// ── #71 Routes API helpers (pure, unit-tested in travel-routes.test.js) ──────────────────────────
// DRIVE now uses Routes API computeRoutes with TRAFFIC_AWARE_OPTIMAL — REAL traffic, so the old ×1.4
// fudge is GONE. TRANSIT stays on legacy Directions: VERIFIED 2026-06-21 that Routes API TRANSIT
// returns no routes for our key/region (empty {} even between major stations), while legacy transit
// works. departureTime ≈ event start so we get the traffic the user will actually hit (never-late bias).
function parseDurationSeconds(s) {
  const m = /^(\d+)s$/.exec(String(s || "").trim());
  return m ? Number(m[1]) : null;
}
function minutesFromSeconds(sec) {
  if (!Number.isFinite(sec)) return null;
  return Math.max(5, Math.round(sec / 60));
}

// Shared provider acceptance contract for the production route fallback and readiness preflight.
// Either valid provider keeps routing operational; when both work, preserve the never-late max bias.
function acceptRouteResults({ legacyTransit, routesDrive }) {
  const providers = [
    ["legacy_transit", legacyTransit],
    ["routes_drive", routesDrive],
  ];
  const availableProviders = providers.filter(([, value]) => Number.isFinite(value)).map(([name]) => name);
  const degradedProviders = providers.filter(([, value]) => !Number.isFinite(value)).map(([name]) => name);
  const values = providers.map(([, value]) => value).filter(Number.isFinite);
  return {
    operational: values.length > 0,
    minutes: values.length ? Math.max(...values) : null,
    availableProviders,
    degradedProviders,
  };
}
function buildDriveBody(src, dst, departIso) {
  return {
    origin: { address: src }, destination: { address: dst },
    travelMode: "DRIVE", routingPreference: "TRAFFIC_AWARE_OPTIMAL", departureTime: departIso,
  };
}
function clampDepartIso(departAtMs, nowMs) {
  // Routes API rejects a departureTime in the past → floor to now+60s.
  const ms = Math.max(Number(departAtMs) || 0, (Number(nowMs) || 0) + 60000);
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
}

async function routesDriveMinutes(src, dst, mapsKey, departAtMs, nowMs, usage = {}) {
  const body = JSON.stringify(buildDriveBody(src, dst, clampDepartIso(departAtMs, nowMs)));
  const routeMeta = routeUsageMeta(usage);
  try {
    const r = await fetch("https://routes.googleapis.com/directions/v2:computeRoutes", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": mapsKey,
        "X-Goog-FieldMask": "routes.duration",
      },
      body,
    });
    if (!r.ok) {
      noteProviderFailure(usage, providerFailureClass(r));
      await emitUsage(usage.options, { tenantId: usage.tenantId || "anonymous", provider: "google_maps",
        feature: "routes_pro", outcome: "failure", failureClass: providerFailureClass(r),
        providerUnits: 1, providerUnit: "request", estimatedCostUsd: GOOGLE_ROUTES_PRO_EST_USD,
        meta: { ...routeMeta, sku: "Routes: Compute Routes Pro", pricing_basis: "list_price_after_free_cap" } });
      return null;
    }
    const j = await r.json();
    const sec = parseDurationSeconds((((j.routes || [])[0]) || {}).duration);
    if (sec == null) noteProviderFailure(usage, "no_route");
    await emitUsage(usage.options, { tenantId: usage.tenantId || "anonymous", provider: "google_maps",
      feature: "routes_pro", outcome: sec == null ? "failure" : "success",
      failureClass: sec == null ? "no_route" : null, providerUnits: 1, providerUnit: "request",
      estimatedCostUsd: GOOGLE_ROUTES_PRO_EST_USD,
      meta: { ...routeMeta, sku: "Routes: Compute Routes Pro", pricing_basis: "list_price_after_free_cap" } });
    return sec == null ? null : minutesFromSeconds(sec);
  } catch {
    noteProviderFailure(usage, "network");
    await emitUsage(usage.options, { tenantId: usage.tenantId || "anonymous", provider: "google_maps",
      feature: "routes_pro", outcome: "failure", failureClass: "network", providerUnits: 1,
      providerUnit: "request", estimatedCostUsd: GOOGLE_ROUTES_PRO_EST_USD,
      meta: { ...routeMeta, sku: "Routes: Compute Routes Pro", pricing_basis: "list_price_after_free_cap" } });
    return null;
  }
}

// arriveByMs: used for outbound (arrive-by event start). departAtMs: used for return legs (depart at
// event end). Only one should be non-null; if neither is a future time, falls back to departure_time="now".
async function legacyTransitMinutes(src, dst, mapsKey, arriveByMs, nowMs = Date.now(), departAtMs = null, usage = {}) {
  const p = new URLSearchParams({ origin: src, destination: dst, mode: "transit", key: mapsKey });
  const routeMeta = routeUsageMeta(usage);
  // NEVER-LATE: anchor transit to the EVENT, not "now". Future event → arrival_time = event start, so
  // the train time reflects the schedule the user will actually ride. Past/missing → fall back to now.
  // Return leg: departAtMs is set → use departure_time anchored to event end (FIND-004).
  if (Number.isFinite(departAtMs) && departAtMs > nowMs) {
    p.set("departure_time", String(Math.floor(departAtMs / 1000)));
  } else if (Number.isFinite(arriveByMs) && arriveByMs > nowMs) {
    p.set("arrival_time", String(Math.floor(arriveByMs / 1000)));
  } else {
    p.set("departure_time", "now");
  }
  try {
    const r = await fetch(`https://maps.googleapis.com/maps/api/directions/json?${p}`);
    const j = await r.json();
    const accepted = r.ok !== false && j.status === "OK" && j.routes && j.routes[0]
      && j.routes[0].legs && j.routes[0].legs[0];
    if (!accepted) noteProviderFailure(usage, providerFailureClass(r, j.status));
    await emitUsage(usage.options, {
      tenantId: usage.tenantId || "anonymous", provider: "google_maps", feature: "directions",
      outcome: accepted ? "success" : "failure",
      failureClass: accepted ? null : providerFailureClass(r, j.status),
      providerUnits: 1, providerUnit: "request", estimatedCostUsd: GOOGLE_DIRECTIONS_EST_USD,
      meta: { ...routeMeta, sku: "Directions", pricing_basis: "list_price_after_free_cap" },
    });
    if (!accepted) return null;
    return minutesFromSeconds(j.routes[0].legs[0].duration.value);
  } catch {
    noteProviderFailure(usage, "network");
    await emitUsage(usage.options, {
      tenantId: usage.tenantId || "anonymous", provider: "google_maps", feature: "directions",
      outcome: "failure", failureClass: "network", providerUnits: 1, providerUnit: "request",
      estimatedCostUsd: GOOGLE_DIRECTIONS_EST_USD,
      meta: { ...routeMeta, sku: "Directions", pricing_basis: "list_price_after_free_cap" },
    });
    return null;
  }
}

// Query BOTH transit (anchored to event start) and traffic-aware drive, then take the LARGER —
// never-late bias: we don't yet know the user's mode, so assume the slower so we never under-estimate.
// departAtMs ≈ event start. Returns null only if neither mode resolves (caller then asks). floor 5 min.
// TODO(#69/#70): per-user travel_mode preference → trust the chosen mode instead of max().
//
// departureMode: when true, the time arg is a DEPARTURE anchor (for return legs — FIND-004).
// Outbound (default false): transit uses arrival_time = event start (arrive-by).
// Return (true): transit uses departure_time = ev.endMs (depart-at, not arrive-by).
// The Google path (Routes Pro drive + legacy transit, never-late MAX bias). This is the FALLBACK now.
async function directionsMinutesGoogle(src, dst, mapsKey, departAtMs = Date.now(), nowMs = Date.now(), departureMode = false, usage = {}) {
  if (!mapsKey || !src || !dst) return null;
  const [transit, drive] = await Promise.all([
    departureMode
      ? legacyTransitMinutes(src, dst, mapsKey, null, nowMs, departAtMs, usage)
      : legacyTransitMinutes(src, dst, mapsKey, departAtMs, nowMs, null, usage),
    routesDriveMinutes(src, dst, mapsKey, departAtMs, nowMs, usage),
  ]);
  return acceptRouteResults({ legacyTransit: transit, routesDrive: drive }).minutes;
}

// C3: address→geo memo — the 60s scheduler tick must NOT re-geocode the same home/event address every
// time. Keyed by tenant/provider/address scope; successful entries also persist across process restarts.
const _geoMemo = new Map();
const _geoInFlight = new Map();

function geocodeStoreFor(options = {}) {
  if (Object.hasOwn(options, "_geocodeCacheStore")) return options._geocodeCacheStore || null;
  const supaUrl = options.supaUrl || process.env.SUPABASE_URL;
  const supaKey = options.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supaUrl || !supaKey) return null;
  return makeSupabaseGeocodeStore({
    supaUrl, supaKey, fetchImpl: options._cacheFetch || global.fetch,
  });
}

function geocodeMemoKey(tenantId, address, supaKey) {
  const digest = supaKey ? addressDigest({
    tenantId, provider: "google_maps", address, digestKey: supaKey,
  }) : null;
  return JSON.stringify([tenantId, "google_maps", digest || String(address)]);
}

async function emitGeocodeCacheHit(usage, tenantId) {
  await emitUsage(usage.options, {
    tenantId, provider: "google_maps", feature: "geocoding", outcome: "cache_hit",
    cacheHit: true, providerUnits: 0, providerUnit: "request", estimatedCostUsd: 0,
    meta: { sku: "Geocoding", ...eventVersionMeta(usage) },
  });
}

// C2: geocode a JP address ONCE via Google Geocoding (cheap, one-time; NOT the Routes-Pro cost driver).
// Returns {lat,lon} or null. Injected in tests via opts._geocode.
async function geocodeAddress(addr, mapsKey, usage = {}) {
  if (!addr || !mapsKey) return null;
  const tenantId = String(usage.tenantId || "anonymous");
  const options = usage.options || {};
  const supaKey = options.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  const store = geocodeStoreFor(options);
  const memoKey = geocodeMemoKey(tenantId, addr, store ? supaKey : null);
  const memo = _geoMemo.get(memoKey);
  if (memo && typeof memo === "object" && Object.hasOwn(memo, "value")) {
    const transient = ["network", "provider_5xx", "timeout"].includes(memo.failureClass);
    const ttl = memo.value ? GEOCODE_SUCCESS_TTL_MS
      : transient ? GEOCODE_TRANSIENT_TTL_MS : GEOCODE_NEGATIVE_TTL_MS;
    if (Date.now() - memo.computedAt < ttl) {
      if (memo.value) await emitGeocodeCacheHit(usage, tenantId);
      return memo.value;
    }
    _geoMemo.delete(memoKey);
  }
  if (_geoInFlight.has(memoKey)) return _geoInFlight.get(memoKey);

  const run = Promise.resolve().then(async () => {
    if (store) {
      const cached = await store.get(tenantId, "google_maps", addr);
      if (cached && isValidGeocode(cached.value)
          && Date.now() - cached.computedAt < cached.ttlMs) {
        const value = { lat: cached.value.lat, lon: cached.value.lon };
        _geoMemo.set(memoKey, { value, computedAt: cached.computedAt, failureClass: null });
        await emitGeocodeCacheHit(usage, tenantId);
        return value;
      }
    }
    try {
      const u = `https://maps.googleapis.com/maps/api/geocode/json?address=${encodeURIComponent(addr)}&key=${mapsKey}`;
      const response = await fetch(u);
      const j = await response.json();
      const loc = j && j.results && j.results[0] && j.results[0].geometry && j.results[0].geometry.location;
      const providerSucceeded = response && response.ok !== false && j && j.status === "OK";
      const candidate = providerSucceeded && loc ? { lat: loc.lat, lon: loc.lng } : null;
      const failureClass = !providerSucceeded || !loc ? providerFailureClass(response, j && j.status)
        : isValidGeocode(candidate) ? null : "invalid_coordinates";
      const value = failureClass ? null : candidate;
      await emitUsage(options, { tenantId, provider: "google_maps",
        feature: "geocoding", outcome: value ? "success" : "failure", failureClass,
        providerUnits: 1, providerUnit: "request", estimatedCostUsd: GOOGLE_GEOCODING_EST_USD,
        meta: { sku: "Geocoding", pricing_basis: "list_price_after_free_cap", ...eventVersionMeta(usage) } });
      const computedAt = Date.now();
      _geoMemo.set(memoKey, { value, computedAt, failureClass });
      if (value && store) await store.set(tenantId, "google_maps", addr, value, computedAt);
      return value;
    } catch {
      await emitUsage(options, { tenantId, provider: "google_maps",
        feature: "geocoding", outcome: "failure", failureClass: "network", providerUnits: 1,
        providerUnit: "request", estimatedCostUsd: GOOGLE_GEOCODING_EST_USD,
        meta: { sku: "Geocoding", pricing_basis: "list_price_after_free_cap", ...eventVersionMeta(usage) } });
      _geoMemo.set(memoKey, { value: null, computedAt: Date.now(), failureClass: "network" });
      return null;
    }
  });
  _geoInFlight.set(memoKey, run);
  try {
    return await run;
  } finally {
    if (_geoInFlight.get(memoKey) === run) _geoInFlight.delete(memoKey);
  }
}

// C2: real FREE JP transit fetch (api.transit.ls8h.com /plan). Injected in tests via opts._transitFetch.
// The event anchor is deliberately part of the query; a route computed at scheduler time is not a
// truthful substitute for the train the user will take at the calendar event.
async function transitFetchPlan(srcGeo, dstGeo, query = {}, diagnostics = {}) {
  try {
    const p = new URLSearchParams({
      from: `geo:${srcGeo.lat},${srcGeo.lon}`,
      to: `geo:${dstGeo.lat},${dstGeo.lon}`,
      date: String(query.date || ""),
      time: String(query.time || ""),
      type: String(query.type || "arrival"),
      numItineraries: String(query.numItineraries || 1),
    });
    const request = query.signal ? { signal: query.signal } : undefined;
    const response = await fetch(`https://api.transit.ls8h.com/api/v1/plan?${p}`, request);
    if (!response || typeof response.json !== "function") {
      setTransitFallbackReason(diagnostics, "transit_invalid_response");
      return null;
    }
    if (response.ok === false) {
      const status = Number(response.status);
      setTransitFallbackReason(diagnostics, status >= 400 && status < 500 ? "transit_provider_4xx"
        : status >= 500 ? "transit_provider_5xx" : "transit_invalid_response");
      return null;
    }
    try { return await response.json(); }
    catch {
      setTransitFallbackReason(diagnostics, "transit_invalid_response");
      return null;
    }
  } catch {
    setTransitFallbackReason(diagnostics, "transit_network");
    return null;
  }
}

const DEFAULT_ROUTE_TIMEZONE = "Asia/Tokyo";
const DEFAULT_TRANSIT_TIMEOUT_MS = 25_000;

function validRouteTimezone(value) {
  const zone = String(value || "").trim();
  if (!zone) return null;
  try {
    new Intl.DateTimeFormat("en", { timeZone: zone }).format(0);
    return zone;
  } catch { return null; }
}

function localCalendarDate(event, timezone) {
  if (!event || !Number.isFinite(event.startMs)) return null;
  const zone = validRouteTimezone(timezone) || validRouteTimezone(event.timezone) || DEFAULT_ROUTE_TIMEZONE;
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date(event.startMs)).filter((part) => part.type !== "literal")
    .map(({ type, value }) => [type, value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function sameLocalCalendarDay(left, right, timezone) {
  const zone = validRouteTimezone(timezone) || validRouteTimezone(right && right.timezone)
    || validRouteTimezone(left && left.timezone) || DEFAULT_ROUTE_TIMEZONE;
  const leftDate = localCalendarDate(left, zone);
  return Boolean(leftDate && leftDate === localCalendarDate(right, zone));
}

function previousLocatedCalendarEvents(events, event, timezone, sameDayOnly = false) {
  if (!event || !Number.isFinite(event.startMs)) return [];
  return (Array.isArray(events) ? events : [])
    .filter((candidate) => candidate && !isTravel(candidate.summary)
      && String(candidate.location || "").trim()
      && Number.isFinite(candidate.endMs) && candidate.endMs <= event.startMs
      && (!sameDayOnly || sameLocalCalendarDay(candidate, event, timezone)))
    .sort((left, right) => left.endMs - right.endMs);
}

function travelOriginCandidates(home, repeatedLocation, previousEvents) {
  const candidates = [];
  const add = (id, location, source) => {
    const value = String(location || "").trim();
    if (!value) return;
    const key = value.replace(/\s+/g, "").toLowerCase();
    if (candidates.some((candidate) => candidate.location.replace(/\s+/g, "").toLowerCase() === key)) return;
    candidates.push({ id, location: value, source });
  };
  add("home", home, "saved_home");
  add("repeated-location", repeatedLocation, "repeated_calendar_location");
  for (const [index, event] of [...(previousEvents || [])].reverse().entries()) {
    if (index >= 3) break;
    add(`previous-${index}`, event.location, "same_day_calendar");
  }
  return candidates;
}

function asEpochMs(value) {
  if (value instanceof Date) {
    const ms = value.getTime();
    return Number.isFinite(ms) ? ms : null;
  }
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim()) {
    const ms = Date.parse(value);
    return Number.isFinite(ms) ? ms : null;
  }
  return null;
}

function routeCallArgs(anchorAtMs, nowMs, departureMode, opts) {
  const options = opts && typeof opts === "object" ? { ...opts } : {};
  const resolvedNow = asEpochMs(nowMs) ?? Date.now();
  const resolvedAnchor = asEpochMs(anchorAtMs);
  const timezone = validRouteTimezone(options.timezone)
    || DEFAULT_ROUTE_TIMEZONE;
  return {
    anchorAtMs: resolvedAnchor,
    nowMs: resolvedNow,
    departureMode: departureMode === true,
    timezone,
    options,
  };
}

function parseGeoLiteral(value) {
  if (typeof value !== "string") return null;
  const match = /^geo:([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?),([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)$/.exec(value);
  if (!match) return null;
  const lat = Number(match[1]), lon = Number(match[2]);
  return Number.isFinite(lat) && lat >= -90 && lat <= 90
    && Number.isFinite(lon) && lon >= -180 && lon <= 180
    ? { lat, lon } : null;
}

function wallAnchor(epochMs, timezone, nowMs, departureMode) {
  // AC-11: an event in the past (or with no timestamp) is queried at the current wall time; future
  // events remain anchored to their own calendar instant.
  const requested = Number.isFinite(epochMs) && epochMs > nowMs ? epochMs : nowMs;
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(requested)).filter((part) => part.type !== "literal")
    .map((part) => [part.type, part.value]));
  const date = `${parts.year}${parts.month}${parts.day}`;
  const time = `${parts.hour}:${parts.minute}`;
  const anchorSecs = Number(parts.hour) * 3600 + Number(parts.minute) * 60 + Number(parts.second);
  return {
    date,
    time,
    anchorSecs,
    anchorAtMs: requested,
    type: departureMode ? "departure" : "arrival",
    numItineraries: 1,
  };
}

function googleRoute(value) {
  if (value == null) return null;
  if (typeof value === "number") {
    return Number.isFinite(value) ? { provider: "google", durationSeconds: value * 60, durationSecs: value * 60 } : null;
  }
  if (typeof value !== "object") return null;
  const duration = Number(value.durationSeconds ?? value.durationSecs ?? value.duration_seconds);
  if (!Number.isFinite(duration)) return null;
  return { ...value, provider: "google", durationSeconds: duration, durationSecs: duration };
}

function routeDurationSeconds(route) {
  if (route == null) return null;
  if (typeof route === "number") return Number.isFinite(route) ? route * 60 : null;
  if (typeof route !== "object") return null;
  const seconds = Number(route.durationSeconds ?? route.durationSecs ?? route.duration_seconds);
  return Number.isFinite(seconds) ? seconds : null;
}

// C2/C3 WIRE: return a provider-fact-preserving structured route. Transit is attempted first for
// Japan endpoints; unusable/error output calls the Google fallback once, sequentially. The cache
// stores the final route under a tenant + provider/anchor scoped key.
async function directionsRoute(src, dst, mapsKey, anchorAtMs = null, nowMs = Date.now(), departureMode = false, opts = {}) {
  const call = routeCallArgs(anchorAtMs, nowMs, departureMode, opts);
  const options = call.options;
  const geocode = options._geocode || geocodeAddress;
  const transitFetch = options._transitFetch || transitFetchPlan;
  const googleRouteFn = options._directionsRouteGoogle;
  const googleMinutesFn = options._directionsMinutesGoogle || directionsMinutesGoogle;
  const cache = routeCacheFor(options); // tests inject a fresh cache to avoid cross-test leakage
  const uid = options.uid ?? options.tenantId ?? options.userId ?? "anonymous";
  const purpose = options.purpose || (call.departureMode ? "return" : "go");
  const eventVersion = routeEventVersion({ eventId: options.eventId, anchorAtMs: call.anchorAtMs, src, dst, purpose,
    timezone: call.timezone, departureMode: call.departureMode,
    anchorType: call.departureMode ? "departure" : "arrival" });
  const routeId = randomUUID();
  const usageOptions = { ...options, _usageRuntimeEnv: usageRuntimeEnv(
    options._runtimeEnv || process.env,
    { fallbackOwnerId: "life-call-travel", fallbackRunId: `route-${routeId}` },
  ) };
  const allowanceState = options._allowanceState;
  const usage = { tenantId: uid, options: usageOptions, eventVersion };
  const routeUsage = { tenantId: uid, options: usageOptions, eventVersion, failureClasses: [] };
  const transitDiagnostics = { fallbackReason: null };
  const timeoutOption = options._transitTimeoutMs ?? options.transitTimeoutMs;
  const transitTimeoutMs = Number.isFinite(Number(timeoutOption)) && Number(timeoutOption) >= 0
    ? Number(timeoutOption) : DEFAULT_TRANSIT_TIMEOUT_MS;
  if (!mapsKey || !src || !dst) return null;
  // The durable event index is intentionally checked before geocoding. A coordinate-key-only lookup
  // would itself require two paid geocodes and could not serve an exhausted tenant's cached result.
  if (cache && typeof cache.getByEvent === "function" && options.eventId) {
    const cached = await cache.getByEvent(uid, eventVersion, purpose, (_value, entry) => emitUsage(usageOptions, {
      tenantId: uid, provider: "route_cache", feature: "travel_route", outcome: "cache_hit",
      failureClass: entry.failureClass, cacheHit: true, providerUnits: 0,
      providerUnit: "request", estimatedCostUsd: 0,
      meta: eventVersionMeta({ eventVersion }),
    }));
    if (cached && cached.hit === true) {
      if (allowanceState && cached.value == null) allowanceState.negativeCacheHit = true;
      return cached.value;
    }
  }
  if (allowanceState && !allowanceState.receipt && typeof options._reserveManagedAction === "function") {
    const receipt = await options._reserveManagedAction(uid, String(options.eventId), options.supaUrl, options.supaKey);
    allowanceState.receipt = receipt && receipt.reservationToken ? receipt : null;
    allowanceState.blocked = !receipt || receipt.allowed !== true;
    if (allowanceState.blocked) return null;
  }
  const srcLiteral = parseGeoLiteral(src);
  const dstLiteral = parseGeoLiteral(dst);
  const googleSrc = srcLiteral ? `${srcLiteral.lat},${srcLiteral.lon}` : src;
  const googleDst = dstLiteral ? `${dstLiteral.lat},${dstLiteral.lon}` : dst;
  const [srcGeo, dstGeo] = await Promise.all([
    srcLiteral || geocode(src, mapsKey, usage), dstLiteral || geocode(dst, mapsKey, usage),
  ]);
  const query = wallAnchor(call.anchorAtMs, call.timezone, call.nowMs, call.departureMode);
  const routeMode = srcGeo && dstGeo && chooseRouter(srcGeo, dstGeo) === "transit" ? "transit" : "google";
  const google = async () => {
    routeUsage.routeMode = routeMode;
    routeUsage.fallbackReason = routeMode === "google"
      ? (srcGeo && dstGeo ? "non_jp" : null)
      : transitDiagnostics.fallbackReason || "transit_invalid_response";
    try {
      const value = googleRouteFn
        ? await googleRouteFn(googleSrc, googleDst, mapsKey, query.anchorAtMs, call.nowMs, call.departureMode)
        : options._directionsMinutesGoogle
          ? await googleMinutesFn(googleSrc, googleDst, mapsKey, query.anchorAtMs, call.nowMs, call.departureMode, routeUsage)
          : await (call.departureMode
            ? legacyTransitMinutes(googleSrc, googleDst, mapsKey, null, call.nowMs, query.anchorAtMs, routeUsage)
            : legacyTransitMinutes(googleSrc, googleDst, mapsKey, query.anchorAtMs, call.nowMs, null, routeUsage));
      const route = googleRoute(value);
      return route || cacheFailure(routeUsage.failureClasses.at(-1) || "no_route");
    } catch { return cacheFailure("network"); }
  };
  const compute = async () => {
    if (routeMode === "transit") {
      let plan = null;
      const controller = typeof AbortController === "function" ? new AbortController() : null;
      let timer;
      const transitPromise = Promise.resolve()
        .then(() => transitFetch(srcGeo, dstGeo, {
          ...query, timezone: call.timezone, signal: controller && controller.signal,
        }, transitDiagnostics))
        .catch(() => {
          setTransitFallbackReason(transitDiagnostics, "transit_network");
          return null;
        });
      const timeoutPromise = new Promise((resolve) => {
        timer = setTimeout(() => {
          setTransitFallbackReason(transitDiagnostics, "transit_timeout");
          if (controller) controller.abort();
          resolve(null);
        }, transitTimeoutMs);
      });
      try { plan = await Promise.race([transitPromise, timeoutPromise]); }
      finally { clearTimeout(timer); }
      const parsed = plan && parseTransitPlan(plan, { anchorType: query.type, anchorSecs: query.anchorSecs });
      if (parsed && Number.isFinite(routeDurationSeconds(parsed))) return parsed;
      if (!transitDiagnostics.fallbackReason) {
        const unanchored = plan && parseTransitPlan(plan);
        const hasValidJourney = unanchored && unanchored.serviceDate && unanchored.timezone
          && Number.isFinite(routeDurationSeconds(unanchored));
        const noRoute = hasValidTransitEnvelope(plan) && Array.isArray(plan.journeys)
          && (plan.journeys.length === 0 || hasValidJourney);
        transitDiagnostics.fallbackReason = noRoute ? "transit_no_route" : "transit_invalid_response";
      }
    }
    return google(); // non-JP/unresolvable or Transit failure → exactly one Google fallback
  };
  const context = {
    provider: routeMode,
    mode: routeMode,
    timezone: call.timezone,
    serviceDate: query.date,
    anchorType: query.type,
    fromKey: srcGeo ? "" : opaqueEndpointKey(src),
    toKey: dstGeo ? "" : opaqueEndpointKey(dst),
    eventVersion,
    purpose,
  };
  const result = await cache.getOrCompute(uid, srcGeo || {}, dstGeo || {}, timeBucket(query.anchorAtMs), compute, context,
    (value, cacheEntry) => emitUsage(usageOptions, {
      tenantId: uid, provider: routeMode === "google" || (value && value.provider === "google")
        ? "google_maps" : "transit_api",
      feature: "travel_route", outcome: "cache_hit", failureClass: cacheEntry.failureClass,
      cacheHit: true,
      providerUnits: 0, providerUnit: "request", estimatedCostUsd: 0,
      meta: routeUsageMeta(routeUsage),
    }));
  if (result == null && allowanceState) allowanceState.providerFailure = true;
  if (result == null && options._deferAllowanceRelease !== true && allowanceState && allowanceState.receipt
      && typeof options._releaseManagedAction === "function") {
    await options._releaseManagedAction(uid, String(options.eventId), options.supaUrl, options.supaKey,
      { reservation: allowanceState.receipt });
    allowanceState.receipt = null;
  }
  return result;
}

// Existing callers consume integer minutes. Keep this as a thin adapter over the structured route so
// Calendar autofill retains its current contract while newer consumers can use provider facts.
async function directionsMinutes(src, dst, mapsKey, anchorAtMs = null, nowMs = Date.now(), departureMode = false, opts = {}) {
  const route = await directionsRoute(src, dst, mapsKey, anchorAtMs, nowMs, departureMode, opts);
  return minutesFromSeconds(routeDurationSeconds(route));
}

function planTravelBlock(leaveMs, arriveMs, fromName, toName, dstAddr, expectedCalendarAccountId) {
  const hours = Math.floor((arriveMs - leaveMs) / 3600000);
  const minutes = Math.round(((arriveMs - leaveMs) % 3600000) / 60000);
  const eventArgs = {
    summary: `[Travel] 🚆 ${shortName(fromName)}→${shortName(toName)}`,
    start_datetime: isoNaiveUTC(leaveMs),
    event_duration_hour: hours, event_duration_minutes: Math.min(59, minutes),
    calendar_id: "primary", timezone: "UTC", location: dstAddr,
    send_updates: "none", exclude_organizer: true, create_meeting_room: false,
    description: LIFE_MANAGER_TRAVEL_DESCRIPTION,
    ...(expectedCalendarAccountId ? {
      reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
    } : {}),
  };
  const startMs = Date.parse(`${eventArgs.start_datetime}Z`);
  const endMs = startMs + (hours * 60 + eventArgs.event_duration_minutes) * 60000;
  return { status: "unknown", args: eventArgs, summary: eventArgs.summary, startMs, endMs, destination: dstAddr,
    reminders: eventArgs.reminders || null };
}

function travelRequestFingerprint(event) {
  return travelHash([String(event.summary || ""), event.start?.dateTime ? Date.parse(event.start.dateTime) : event.startMs,
    event.end?.dateTime ? Date.parse(event.end.dateTime) : event.endMs,
    String(event.location ?? event.destination ?? "").replace(/\s+/g, "").toLowerCase(),
    hasDeparturePopupReminder(event)]);
}

function travelClaimUrl(uid, eventKey, supaUrl, leg) {
  const url = new URL(`${supaUrl.replace(/\/+$/, "")}/rest/v1/lm_travel_log`);
  url.searchParams.set("uid", `eq.${uid}`);
  url.searchParams.set("event_key", `eq.${eventKey}`);
  if (leg) url.searchParams.set("leg", `eq.${leg}`);
  return url;
}

async function readTravelClaims(uid, eventKey, supaUrl, supaKey) {
  if (!supaUrl || !supaKey) return [];
  try {
    const url = travelClaimUrl(uid, eventKey, supaUrl);
    url.searchParams.set("select", "uid,event_key,leg,calendar_write_receipt");
    url.searchParams.set("leg", "in.(go,return)");
    url.searchParams.set("limit", "3");
    const response = await fetch(url.toString(), { headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}` } });
    const rows = response.ok ? await response.json() : null;
    if (!Array.isArray(rows) || rows.length > 2 || rows.some((row) => row.uid !== uid || row.event_key !== eventKey
      || !["go", "return"].includes(row.leg)) || new Set(rows.map((row) => row.leg)).size !== rows.length) return null;
    return rows;
  } catch { return null; }
}

async function saveTravelWriteReceipt(uid, eventKey, receipt, supaUrl, supaKey, expectedPhase) {
  try {
    const url = travelClaimUrl(uid, eventKey, supaUrl, receipt.leg);
    url.searchParams.set("calendar_write_receipt->>request_id", `eq.${receipt.request_id}`);
    if (expectedPhase) url.searchParams.set("calendar_write_receipt->>phase", `eq.${expectedPhase}`);
    if (receipt.effect !== "verified") url.searchParams.set("calendar_write_receipt->>effect", "eq.unknown");
    const response = await fetch(url.toString(), {
      method: "PATCH", headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}`,
        "Content-Type": "application/json", Prefer: "return=representation" },
      body: JSON.stringify({ calendar_write_receipt: receipt }),
    });
    const rows = response.ok ? await response.json() : null;
    return Array.isArray(rows) && rows.length === 1 && rows[0].uid === uid && rows[0].event_key === eventKey
      && rows[0].leg === receipt.leg && isDeepStrictEqual(rows[0].calendar_write_receipt, receipt);
  } catch { return false; }
}

async function reconcileTravelBlock(uid, ev, eventKey, leg, calendar, opts, receipt) {
  const unknown = { status: "unknown" };
  if (!receipt || receipt.schema_version !== 1 || receipt.leg !== leg
    || receipt.source_event_hash !== travelHash([uid, eventKey])
    || !OPAQUE_EVENT_VERSION.test(receipt.request_id || "")) return unknown;
  if (receipt.effect === "no_effect" && receipt.phase === "response" && receipt.command === "calendar.create"
    && ["provider_validation", "account_binding_unavailable", "web_automation_paused"].includes(receipt.error_class)) {
    return await unclaimTravel(uid, eventKey, leg, opts.supaUrl, opts.supaKey, receipt.request_id)
      ? { status: "released" } : unknown;
  }
  if (![receipt.source_event_version, receipt.request_fingerprint, receipt.account_ref_hash]
    .every((value) => OPAQUE_EVENT_VERSION.test(value || ""))
    || !["dispatching", "response", "readback"].includes(receipt.phase)) return unknown;
  const priorProof = receipt.effect === "verified" || receipt.effect === "created";
  const failed = async (errorClass, readback = "error") => {
    if (!priorProof) await saveTravelWriteReceipt(uid, eventKey, { ...receipt, phase: "readback", error_class: errorClass,
      readback, next_action: "owned_readback" }, opts.supaUrl, opts.supaKey);
    return { status: "unknown", error_class: errorClass };
  };
  const ownsHelper = (event) => event && event.status !== "cancelled" && isTravel(event.summary)
    && event.description === `${LIFE_MANAGER_TRAVEL_DESCRIPTION}${TRAVEL_RECEIPT_MARKER}${receipt.request_id}`
    && travelRequestFingerprint(event) === receipt.request_fingerprint
    && typeof event.id === "string" && /^[A-Za-z0-9_-]{1,1024}$/.test(event.id);
  const readOptions = { accountRefHash: receipt.account_ref_hash, supaUrl: opts.supaUrl, supaKey: opts.supaKey,
    ...(opts.expectedCalendarAccountId ? { expectedCalendarAccountId: opts.expectedCalendarAccountId } : {}) };
  let matches, source;
  try {
    if (receipt.provider_event_id) {
      const helper = await calendar.getOwnedEvent(uid, receipt.provider_event_id, readOptions);
      if (helper?.id !== receipt.provider_event_id || !ownsHelper(helper)) return failed("helper_mismatch");
      matches = [helper];
      source = await calendar.getOwnedEvent(uid, eventKey, readOptions);
      if (source?.id !== eventKey) return failed("owned_read_error");
    } else {
      const events = await calendar.listOwnedEvents(uid, { ...readOptions,
        timeMin: new Date(opts.nowMs - TRAVEL_ORIGIN_LOOKBACK_MS).toISOString(),
        timeMax: new Date(opts.nowMs + 7 * 86400000).toISOString() });
      matches = events.filter(ownsHelper);
      if (matches.length !== 1) return failed("helper_mismatch", matches.length ? "ambiguous" : "absent");
      const sources = events.filter((event) => event && event.id === eventKey);
      if (sources.length !== 1) return failed("owned_read_error", "absent");
      source = sources[0];
    }
  } catch {
    return failed("owned_read_error");
  }
  if (source.status === "cancelled") return failed("source_cancelled");
  const freshVersion = sourceEventVersion(source);
  if (freshVersion !== receipt.source_event_version || freshVersion !== ev.sourceEventVersion) return failed("source_changed");
  if (priorProof) return { status: "already_verified" };
  const verified = { ...receipt, phase: "readback", effect: "verified", provider_event_id: matches[0].id,
    evidence_ref: `calendar-event:${travelHash([uid, matches[0].id])}`, error_class: null, next_action: "none", readback: "exact_one" };
  const saved = await saveTravelWriteReceipt(uid, eventKey, verified, opts.supaUrl, opts.supaKey);
  return saved ? { status: "verified" } : unknown;
}

async function createTravelBlock(uid, ev, eventKey, leg, write, cal, opts) {
  const durable = Boolean(opts.supaUrl && opts.supaKey && cal.kind === "composio");
  let receipt = durable ? {
    schema_version: 1, request_id: travelHash([uid, eventKey, leg, randomUUID()]),
    source_event_hash: travelHash([uid, eventKey]), source_event_version: ev.sourceEventVersion,
    leg, request_fingerprint: travelRequestFingerprint(write), account_ref_hash: null,
    phase: "claimed", command: "calendar.create", effect: "unknown", runtime_trace: opts.runtimeTrace,
    http_status: null, error_class: "not_dispatched", provider_event_id: null,
    readback: null, evidence_ref: null, retryable: false, next_action: "owned_readback",
  } : null;
  const claimed = await claimTravel(uid, eventKey, leg, opts.supaUrl, opts.supaKey, receipt);
  if (!claimed) {
    if (!durable) return { status: "unknown", duplicate: true };
    const rows = await readTravelClaims(uid, eventKey, opts.supaUrl, opts.supaKey);
    return { ...await reconcileTravelBlock(uid, ev, eventKey, leg, cal, opts,
      rows && rows.find((row) => row.leg === leg)?.calendar_write_receipt), duplicate: true };
  }
  if (receipt) write.args.description += `${TRAVEL_RECEIPT_MARKER}${receipt.request_id}`;
  const beforeDispatch = receipt ? async (binding) => {
    const dispatching = { ...receipt, ...binding, phase: "dispatching", error_class: null };
    if (!await saveTravelWriteReceipt(uid, eventKey, dispatching, opts.supaUrl, opts.supaKey, "claimed")) return false;
    receipt = dispatching;
    return true;
  } : null;
  let result;
  try {
    const operationOpts = {
      ...(opts.expectedCalendarAccountId ? { expectedCalendarAccountId: opts.expectedCalendarAccountId,
        allowWebInitialScan: opts.allowWebInitialScan === true } : {}),
      ...(receipt ? { beforeDispatch, travelWriteContext: receipt, supaUrl: opts.supaUrl, supaKey: opts.supaKey } : {}),
    };
    result = await cal.createEvent(uid, write.args, operationOpts);
  } catch { result = null; }
  let status = result?.effect === "no_effect" ? "no_effect"
    : result?.effect === "unknown" || result?.successful !== true ? "unknown" : "created";
  if (receipt) {
    const response = { ...receipt, ...(result?.writeReceipt || {}), phase: "response", effect: status,
      next_action: status === "created" ? "none" : status === "no_effect" ? "release_claim" : "owned_readback" };
    // A missing dispatch/response contract cannot authorize clearing a durable fence.
    if (!result?.writeReceipt || result.writeReceipt.error_class === "receipt_not_durable"
      || !await saveTravelWriteReceipt(uid, eventKey, response, opts.supaUrl, opts.supaKey)) status = "unknown";
    else receipt = response;
    if (status === "unknown") return reconcileTravelBlock(uid, ev, eventKey, leg, cal, opts, receipt);
  }
  return { status, ...(receipt ? { requestId: receipt.request_id } : {}) };
}

// Returns { inserted, verified, checked, skipped }. home = lm_users.home_address (may be null → first-of-day
// located events are skipped this run and should be handled by the ask-loop separately).
// _directionsMinutes: test seam — inject a stub so unit/integration tests avoid real network calls.
//   In production this is always undefined and the real directionsMinutes function is used.
// ATOMIC claim of a [Travel] leg (C-H1) — mirrors claimWake. INSERT relies on lm_travel_log
// UNIQUE(uid,event_key,leg): 201 = first claimer (create the block); 409 = another run already claimed.
// If supa is unconfigured, return true (don't block) — the in-memory gcal dedup still prevents obvious dups.
async function claimTravel(uid, eventKey, leg, supaUrl, supaKey, writeReceipt = null) {
  if (!supaUrl || !supaKey) return true;
  const r = await fetch(`${supaUrl}/rest/v1/lm_travel_log`, {
    method: "POST",
    headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}`, "Content-Type": "application/json", Prefer: "return=minimal" },
    body: JSON.stringify({ uid, event_key: eventKey, leg,
      ...(writeReceipt ? { calendar_write_receipt: writeReceipt } : {}) }),
  }).catch(() => null);
  return !!r && r.status === 201; // 201 inserted (claimed) | 409 duplicate (already created)
}
// Release only a proven no-effect attempt; unknown writes retain their claim for owned readback.
// Returns true only when the DELETE received a verified HTTP 2xx response.
async function unclaimTravel(uid, eventKey, leg, supaUrl, supaKey, requestId) {
  if (!supaUrl || !supaKey) return false;
  const url = travelClaimUrl(uid, eventKey, supaUrl, leg);
  if (requestId) {
    url.searchParams.set("calendar_write_receipt->>request_id", `eq.${requestId}`);
    url.searchParams.set("calendar_write_receipt->>effect", "eq.no_effect");
  }
  const response = await fetch(url.toString(), {
    method: "DELETE",
    headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}`, Prefer: "return=minimal" },
  }).catch(() => null);
  return !!response && Number.isInteger(response.status) && response.status >= 200 && response.status < 300;
}

function receiptText(value, maxLength) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= maxLength;
}

async function recordTravelTelegramReceipt(uid, eventKey, leg, messageId, supaUrl, supaKey, opts = {}) {
  const fetchImpl = opts && opts.fetchImpl !== undefined ? opts.fetchImpl : globalThis.fetch;
  if (!receiptText(uid, 256) || !receiptText(eventKey, 512)
    || (leg !== "telegram-t5" && leg !== "trial-upgrade")
    || !Number.isSafeInteger(messageId) || messageId <= 0) {
    return { ok: false, matched: 0, error: "invalid_args" };
  }
  const baseUrl = typeof supaUrl === "string" ? supaUrl.replace(/\/+$/, "") : "";
  if (!baseUrl.trim() || typeof supaKey !== "string" || !supaKey.trim()) {
    return { ok: false, matched: 0, error: "missing_config" };
  }
  if (typeof fetchImpl !== "function") return { ok: false, matched: 0, error: "network_error" };
  let response;
  try {
    response = await fetchImpl(`${baseUrl}/rest/v1/rpc/record_lm_travel_telegram_receipt`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: supaKey, Authorization: `Bearer ${supaKey}` },
      body: JSON.stringify({
        p_uid: uid, p_event_key: eventKey, p_leg: leg, p_telegram_message_id: messageId,
      }),
    });
  } catch {
    return { ok: false, matched: 0, error: "network_error" };
  }
  if (!response || response.ok === false
    || (Number.isInteger(response.status)
      ? response.status < 200 || response.status >= 300
      : response.ok !== true)) {
    return { ok: false, matched: 0, error: "http_error" };
  }
  let matched;
  try { matched = await response.json(); } catch { return { ok: false, matched: 0, error: "unreadable_response" }; }
  if (!Number.isInteger(matched) || matched < 0) return { ok: false, matched: 0, error: "invalid_result" };
  return { ok: true, matched };
}

async function fillTravel(uid, { apiKey, mapsKey, geminiKey, home, timezone, nowMs = Date.now(), bufferMin = 5, calendar, supaUrl, supaKey, telegramChatId, telegramToken, imessageSenderId, imessageSend, notificationsEnabled, _directionsRoute, _directionsMinutes, _routeCache, _reserveManagedAction, _completeManagedAction, _releaseManagedAction, _agentResolveLocation, _agentResolveTravelOrigin, _readTravelOriginAskState, _askTravelOrigin, _recordUsageEvent, gmailAccountId, expectedCalendarAccountId, allowWebInitialScan = false } = {}) {
  const directionsFn = _directionsMinutes || directionsMinutes;
  const routeFn = _directionsRoute || (!_directionsMinutes ? directionsRoute : null);
  const cal = calendar || getCalendar({ apiKey, gmailAccountId, expectedCalendarAccountId });
  const events = (await listEvents7d(uid, apiKey, nowMs, cal, gmailAccountId, {
    strict: Boolean(expectedCalendarAccountId), expectedCalendarAccountId,
  })).sort((left, right) => left.startMs - right.startMs);
  const repeatedLocation = deriveAnchors({
    homeAddress: home,
    calendarEvents: events.filter((event) => !isTravel(event.summary)).map(({ location, startMs }) => ({ location, startMs })),
  }).work;
  let inserted = 0, verified = 0, checked = 0, skipped = 0, originQuestionsAsked = 0;
  const outboundReports = [];
  const reconciliationErrors = {};
  const noteReconciliationError = ({ error_class: errorClass }) => {
    if (!errorClass) return false;
    reconciliationErrors[errorClass] = (reconciliationErrors[errorClass] || 0) + 1;
    return true;
  };
  const writeOptions = { nowMs, supaUrl, supaKey, expectedCalendarAccountId, allowWebInitialScan,
    runtimeTrace: runtimeTrace({ tenantId: uid }, usageRuntimeEnv(process.env, { fallbackOwnerId: "life-call-calendar" })) };
  const releaseAllowance = async (eventKey, state) => {
    if (!state || !state.receipt || typeof _releaseManagedAction !== "function") return;
    await _releaseManagedAction(uid, eventKey, supaUrl, supaKey, { reservation: state.receipt });
    state.receipt = null;
  };
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    if (isTravel(ev.summary) || !ev.location) continue;
    // Past events stay in `events` as same-day origin context, but must never trigger provider work.
    if (Number.isFinite(ev.endMs) && ev.endMs <= nowMs) continue;
    checked++;
    // A verified user preference is authoritative. If it is malformed, use the event's own IANA
    // zone when available, then the product's JST default; never let an invalid preference poison the
    // provider wall-clock query.
    const routeTimezone = validRouteTimezone(timezone) || validRouteTimezone(ev.timezone) || DEFAULT_ROUTE_TIMEZONE;
    // C-H1: atomic claim key per (event, leg). Prefer the gcal event id (stable + unique). Fallback to
    // startMs:summary (NOT startMs alone — two different same-user events can share a start time, FIND-001).
    const evKey = String(ev.id || `${ev.startMs}:${ev.summary || ""}`);
    let priorClaims = cal.kind === "composio" ? await readTravelClaims(uid, evKey, supaUrl, supaKey) : [];
    const retainedClaims = [];
    let reconciliationFailed = false;
    for (const row of priorClaims || []) {
      const reconciliation = await reconcileTravelBlock(uid, ev, evKey, row.leg, cal, writeOptions, row.calendar_write_receipt);
      if (noteReconciliationError(reconciliation)) reconciliationFailed = true;
      if (reconciliation.status === "verified") verified++;
      if (reconciliation.status !== "released") retainedClaims.push(row);
    }
    if (reconciliationFailed) { skipped++; continue; }
    if (priorClaims !== null) priorClaims = retainedClaims;
    const priorGo = priorClaims && priorClaims.some((row) => row.leg === "go");
    const priorReturn = priorClaims && priorClaims.some((row) => row.leg === "return");
    const goReconciliationPending = priorGo && !["created", "verified"].includes(
      priorClaims.find((row) => row.leg === "go")?.calendar_write_receipt?.effect);
    let eventAllowanceBlocked = false;
    let originQuestionPending = false;

    // ── OUTBOUND LEG ──────────────────────────────────────────────────────────────────────────────
    // Single source of truth for the skip/insert decision (home→home, no-origin, online, etc.).
    // Use if/else (NOT continue) so the RETURN LEG below always runs regardless of outbound fate.
    // FIND-005: the outbound continue statements must NEVER skip the return-leg evaluation.
    // An exact existing block already has the route, so repair its reminder before origin resolution.
    const duplicateBlocks = events.filter((e) => isTravel(e.summary) && e.endMs
      && e.endMs >= ev.startMs - 2 * 60000 && e.endMs <= ev.startMs + 60000
      && String(e.location || "").replace(/\s+/g, "").toLowerCase()
        === String(ev.location || "").replace(/\s+/g, "").toLowerCase());
    const existingDuplicate = duplicateBlocks.length === 1 ? duplicateBlocks[0] : null;
    if (expectedCalendarAccountId && priorClaims !== null && !goReconciliationPending && existingDuplicate && existingDuplicate.id
      && existingDuplicate.lifeManagerGeneratedTravel === true
      && !hasDeparturePopupReminder(existingDuplicate) && typeof cal.patchEvent === "function") {
      try {
        await cal.patchEvent(uid, {
          calendar_id: "primary",
          event_id: existingDuplicate.id,
          reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
          send_updates: "none",
        }, { expectedCalendarAccountId, allowWebInitialScan: allowWebInitialScan === true });
      } catch { /* exact Calendar readback below decides whether the idempotent patch took effect */ }
      try {
        const reread = await listEvents7d(uid, apiKey, nowMs, cal, gmailAccountId, {
          strict: Boolean(expectedCalendarAccountId), expectedCalendarAccountId,
        });
        const verifiedMatches = reread.filter((event) => event.id === existingDuplicate.id && isTravel(event.summary)
          && Number.isFinite(event.endMs)
          && event.endMs >= ev.startMs - 2 * 60000 && event.endMs <= ev.startMs + 60000
          && String(event.location || "").replace(/\s+/g, "").toLowerCase()
            === String(ev.location || "").replace(/\s+/g, "").toLowerCase()
          && hasDeparturePopupReminder(event));
        if (verifiedMatches.length === 1) verified++;
      } catch { /* do not create a duplicate when strict readback is unavailable */ }
    }

    const earlierEvents = events.slice(0, i);
    const previous = previousLocatedCalendarEvents(earlierEvents, ev, routeTimezone).at(-1) || null;
    const sameDayEvents = previousLocatedCalendarEvents(earlierEvents, ev, routeTimezone, true);
    const previousGap = previous ? ev.startMs - previous.endMs : Infinity;
    const hasDirectPreviousOrigin = previous && previousGap >= 0 && previousGap <= 90 * 60000;
    const originCandidates = travelOriginCandidates(home, repeatedLocation, sameDayEvents);
    let originOverride = null;
    const hasNonHomeSameDayEvent = sameDayEvents.some((event) => String(event.location || "").replace(/\s+/g, "").toLowerCase()
      !== String(home || "").replace(/\s+/g, "").toLowerCase());
    if (!priorGo && ev.startMs > nowMs && !hasDirectPreviousOrigin && hasNonHomeSameDayEvent
      && (originCandidates.length > 1 || !String(home || "").trim() && originCandidates.length > 0)) {
      try {
        const readAskState = _readTravelOriginAskState || require("./ask.js").readTravelOriginAskState;
        const askState = await readAskState(uid, evKey, { supaUrl, supaKey });
        if (askState && askState.kind === "answered" && askState.location) {
          originOverride = askState.location;
        } else if (askState && askState.kind === "pending") {
          originQuestionPending = true;
        } else if (askState && askState.kind === "unavailable") {
          // Without a durable ask state, we cannot prove that there is no answer to use.
          originQuestionPending = true;
        } else {
          if (geminiKey) {
            try {
              const resolveOrigin = _agentResolveTravelOrigin || require("./ask.js").agentResolveTravelOrigin;
              const resolution = await resolveOrigin(ev, {
                candidates: originCandidates,
                scheduledEvents: sameDayEvents.slice(-5).map((event) => ({
                  summary: event.summary || "",
                  location: event.location || "",
                  startIso: event.startIso || new Date(event.startMs).toISOString(),
                  endIso: new Date(event.endMs).toISOString(),
                })),
                timezone: routeTimezone,
                geminiKey,
                uid,
                recordUsageEvent: _recordUsageEvent,
              });
              const selected = resolution && resolution.kind === "selected"
                ? originCandidates.find((candidate) => candidate.id === resolution.candidateId) : null;
              if (selected) originOverride = selected.location;
            } catch { /* an abstention falls through to the linked-message question */ }
          }
          if (!originOverride) {
            const askOrigin = _askTravelOrigin || require("./ask.js").askTravelOriginOnce;
            try {
              const result = await askOrigin(uid, ev, evKey, originCandidates, {
                supaUrl, supaKey, telegramChatId, telegramToken, imessageSenderId, imessageSend,
                notificationsEnabled,
              });
              if (result && result.kind === "pending") originQuestionPending = true;
              if (result && result.sent === true) originQuestionsAsked++;
            } catch {
              // The send/read outcome is uncertain. Hold outbound routing so the user is not asked twice
              // and a guessed-home route is not inserted while a reply may be in flight.
              originQuestionPending = true;
            }
          }
        }
      } catch {
        // An unreadable ask state cannot distinguish unanswered from answered; do not guess a departure.
        originQuestionPending = true;
      }
    }
    // An event already in progress cannot need an outbound route; preserve its independent return leg.
    const outboundEligible = Number.isFinite(ev.startMs) && ev.startMs > nowMs;
    const decision = priorGo ? { insert: false, origin: null, reason: "already-claimed" }
      : originQuestionPending
      ? { insert: false, origin: null, reason: "origin-question-pending" }
      : outboundEligible
      ? travelDecision(ev, previous, home, originOverride)
      : { insert: false, origin: null, reason: "event-already-started" };
    let outboundInserted = false;
    let resolvedDest = ev.location; // tracks the agent-resolved venue for the return leg

    if (!decision.insert) {
      skipped++;
    } else {
      const origin = decision.origin;
      if (duplicateBlocks.length) {
        skipped++;
        // outbound block already exists — fall through to return-leg so it can backfill a missing return block
      } else {
        let dest = ev.location;
        const allowanceState = {};
        const routeOpts = { uid, timezone: routeTimezone, supaUrl, supaKey, eventId: evKey, purpose: "go",
          _allowanceState: allowanceState, _reserveManagedAction, _releaseManagedAction,
          _deferAllowanceRelease: true, _routeCache };
        if ((_directionsRoute || _directionsMinutes) && typeof _reserveManagedAction === "function") {
          const receipt = await _reserveManagedAction(uid, evKey, supaUrl, supaKey);
          allowanceState.receipt = receipt && receipt.reservationToken ? receipt : null;
          allowanceState.blocked = !receipt || receipt.allowed !== true;
          eventAllowanceBlocked = allowanceState.blocked;
        }
        let route = null;
        if (!allowanceState.blocked && routeFn) {
          try { route = await routeFn(origin, dest, mapsKey, ev.startMs, nowMs, false, routeOpts); }
          catch { route = null; }
          if (routeDurationSeconds(route) == null) route = null;
        }
        let mins = routeFn || allowanceState.blocked ? null
          : await directionsFn(origin, dest, mapsKey, ev.startMs, nowMs, false, routeOpts);
        // A negative route hit skipped the allowance reservation; reserve before a paid venue resolve.
        // The ask.js memo (24 h per event version) is what stops replays, not the route's negative TTL —
        // otherwise one transient Gemini failure would leave the event without travel for a day.
        if (route == null && mins == null && geminiKey && !allowanceState.blocked
            && allowanceState.negativeCacheHit && !allowanceState.receipt
            && typeof _reserveManagedAction === "function"
            && !require("./ask.js").memoizedLocation(ev, uid)) {
          const receipt = await _reserveManagedAction(uid, evKey, supaUrl, supaKey);
          allowanceState.receipt = receipt && receipt.reservationToken ? receipt : null;
          allowanceState.blocked = !receipt || receipt.allowed !== true;
        }
        if (route == null && mins == null && geminiKey && !allowanceState.blocked) {
          // The location is a room name / unroutable string (e.g. "情報科学大講義室[L1]（IS）"). Let the
          // agent web-search the REAL venue address so a must-travel event still gets a block instead of a
          // silent skip — never-late beats clean code. (Lazy require avoids any load-order coupling.)
          try {
            const agentResolveLocation = _agentResolveLocation || require("./ask.js").agentResolveLocation;
            const res = await agentResolveLocation(ev, {
              home, mapsKey, geminiKey, uid, recordUsageEvent: _recordUsageEvent,
            });
            if (res && res.kind === "online") {
              skipped++;
              await releaseAllowance(evKey, allowanceState);
              continue; // truly online — no outbound OR return block needed; skip entire iteration
            }
            if (res && res.kind === "filled" && res.location) {
              dest = res.location;
              if (routeFn) {
                try { route = await routeFn(origin, dest, mapsKey, ev.startMs, nowMs, false, routeOpts); }
                catch { route = null; }
                if (routeDurationSeconds(route) == null) route = null;
              }
              mins = routeFn ? null : await directionsFn(origin, dest, mapsKey, ev.startMs, nowMs, false, routeOpts);
            }
          } catch { /* fall through to null-mins skip below */ }
        }
        if (route == null && mins == null) {
          skipped++;
          await releaseAllowance(evKey, allowanceState);
          // Cannot route outbound — still evaluate return leg in case it is independently resolvable
        } else {
          const arriveMs = ev.startMs;
          const leaveMs = route ? computeDoorDepartureMs(arriveMs, route, { bufferMin }) : arriveMs - (mins + bufferMin) * 60000;
          if (leaveMs < nowMs) {
            skipped++; // REQ-18: past GO leave time → no outbound block; return leg still evaluated below
            await releaseAllowance(evKey, allowanceState);
          } else {
            {
              const plan = planTravelBlock(leaveMs, arriveMs, origin, dest, dest, expectedCalendarAccountId);
              const write = await createTravelBlock(uid, ev, evKey, "go", plan, cal, writeOptions);
              if (noteReconciliationError(write)) {
                if (write.duplicate) await releaseAllowance(evKey, allowanceState);
                skipped++; continue;
              }
              if (write.status === "created") {
                inserted++;
                outboundInserted = true;
                if (typeof _completeManagedAction === "function") {
                  await _completeManagedAction(uid, evKey, supaUrl, supaKey,
                    { reservation: allowanceState.receipt });
                }
                const sameAsHome = home && String(origin).replace(/\s+/g, "").toLowerCase() ===
                  String(home).replace(/\s+/g, "").toLowerCase();
                outboundReports.push({
                  eventId: evKey,
                  summary: ev.summary || "予定",
                  startMs: ev.startMs,
                  startIso: ev.startIso,
                  origin: sameAsHome ? "自宅" : shortName(origin),
                  leaveMs,
                  arriveMs,
                });
              } else if (write.status === "verified") {
                verified++;
                if (typeof _completeManagedAction === "function") {
                  await _completeManagedAction(uid, evKey, supaUrl, supaKey,
                    { reservation: allowanceState.receipt });
                }
              } else if (write.status === "no_effect") {
                skipped++;
                await unclaimTravel(uid, evKey, "go", supaUrl, supaKey, write.requestId);
                await releaseAllowance(evKey, allowanceState);
              } else {
                skipped++;
                if (write.duplicate) await releaseAllowance(evKey, allowanceState);
              }
            }
          }
        }
        resolvedDest = dest; // capture agent-resolved address for the return-leg directions call
      }
    }

    // ── RETURN LEG (REQ-15, FIND-001, FIND-003, FIND-004, FIND-005) ──────────────────────────────
    if (priorReturn) { skipped++; continue; }
    // Evaluated INDEPENDENTLY of the outbound leg's fate. The three former `continue` points above
    // (decision.insert=false, outbound dedup, past-leaveMs) no longer prevent this code from running.
    //
    // Return-leg past-guard (mirrors REQ-18 for the return leg — FIND-005):
    // Skip only if ev.endMs itself is already in the past (the event is already over).
    // An event whose outbound leave-time is past but endMs is still future still gets a return block.
    if (Number.isFinite(ev.endMs) && ev.endMs <= nowMs) {
      skipped++;
      continue; // event already ended — no "head home" block needed
    }

    // returnDecision is PURE; pass events[i+1] as the "next" hint.
    const retDecision = returnDecision(ev, events[i + 1], home);
    if (!retDecision.insert) {
      skipped++;
      continue;
    }
    // Array-window dedup: scan events[] for any [Travel] return block already in the window after
    // ev.endMs. Catches both the adjacent case and the non-adjacent case (FIND-003/FIND-006):
    // a block that already exists but is NOT events[i+1] (e.g. another event sits between them).
    const retDup = events.some(
      (e) => isTravel(e.summary) && e.startMs && e.startMs >= ev.endMs && e.startMs < ev.endMs + 3 * 3600000,
    );
    if (retDup) { skipped++; continue; }
    // Compute return travel time: DEPARTURE anchored to ev.endMs (FIND-004 — departureMode=true).
    // resolvedDest is the agent-resolved venue address from the outbound leg (or ev.location if
    // outbound was skipped due to dedup/no-origin — returnDecision already checked venue non-empty).
    const venue = resolvedDest;
    if (!home) { skipped++; continue; }
    if (eventAllowanceBlocked) { skipped++; continue; }
    const returnAllowanceState = {};
    if ((_directionsRoute || _directionsMinutes) && typeof _reserveManagedAction === "function") {
      const receipt = await _reserveManagedAction(uid, evKey, supaUrl, supaKey);
      returnAllowanceState.receipt = receipt && receipt.reservationToken ? receipt : null;
      returnAllowanceState.blocked = !receipt || receipt.allowed !== true;
    }
    const retMins = returnAllowanceState.blocked ? null
      : await directionsFn(venue, home, mapsKey, ev.endMs, nowMs, /* departureMode= */ true, {
      uid, timezone: routeTimezone, supaUrl, supaKey, eventId: evKey, purpose: "return",
      _allowanceState: returnAllowanceState, _reserveManagedAction, _releaseManagedAction,
      _routeCache,
    });
    if (retMins == null) {
      skipped++;
      await releaseAllowance(evKey, returnAllowanceState);
      continue;
    }
    const retLeaveMs = ev.endMs;                           // depart immediately after event ends
    const retArriveMs = retLeaveMs + retMins * 60000;
    {
      const plan = planTravelBlock(retLeaveMs, retArriveMs, venue, home, home, expectedCalendarAccountId);
      const write = await createTravelBlock(uid, ev, evKey, "return", plan, cal, writeOptions);
      if (noteReconciliationError(write)) {
        if (write.duplicate) await releaseAllowance(evKey, returnAllowanceState);
        skipped++; continue;
      }
      if (write.status === "created") {
        inserted++;
        if (typeof _completeManagedAction === "function") {
          await _completeManagedAction(uid, evKey, supaUrl, supaKey,
            { reservation: returnAllowanceState.receipt });
        }
      } else if (write.status === "verified") {
        verified++;
        if (typeof _completeManagedAction === "function") {
          await _completeManagedAction(uid, evKey, supaUrl, supaKey,
            { reservation: returnAllowanceState.receipt });
        }
      } else if (write.status === "no_effect") {
        skipped++;
        await unclaimTravel(uid, evKey, "return", supaUrl, supaKey, write.requestId);
        await releaseAllowance(evKey, returnAllowanceState);
      } else {
        skipped++;
        if (write.duplicate) await releaseAllowance(evKey, returnAllowanceState);
      }
    }
    void outboundInserted; // suppress unused warning — used for semantic clarity only
  }
  return { inserted, verified, checked, skipped, originQuestionsAsked, outboundReports,
    ...(Object.keys(reconciliationErrors).length ? { reconciliationErrors } : {}) };
}

// PURE return-leg decision — mirrors travelDecision geometry for the post-event leg (venue→home).
// Deterministic geometry = a TOOL-layer helper; NO LLM judgment, no keyword regex for decisions.
// Returns { insert: boolean, origin: string|null, reason: string }.
function returnDecision(ev, next, home) {
  const norm = (s) => (s || "").replace(/\s+/g, "").toLowerCase();
  // Guard: ev must exist, have an endMs, not be a [Travel] block, and have a real venue.
  if (!ev) return { insert: false, origin: null, reason: "no-event" };
  if (!Number.isFinite(ev.endMs)) return { insert: false, origin: null, reason: "no-end-time" };
  if (isTravel(ev.summary)) return { insert: false, origin: null, reason: "travel-block" };
  const venue = (ev.location || "").trim();
  if (!venue) return { insert: false, origin: null, reason: "no-location" };
  // Home must be known.
  if (!home || !(home || "").trim()) return { insert: false, origin: null, reason: "no-home" };
  // Same-location guard (reuses the identical norm() predicate from travelDecision).
  if (norm(venue) === norm(home)) return { insert: false, origin: venue, reason: "same-location" };
  // Dedup: if the immediately following slot already holds a [Travel] return block, don't insert again.
  if (next && isTravel(next.summary) && next.startMs <= ev.endMs + 60000) {
    return { insert: false, origin: venue, reason: "already-has-return-block" };
  }
  // Back-to-back check: if next exists, starts within ≤90min, AND has a real venue, the user travels
  // venue→next-venue (not home), so no return block is needed.
  const nextVenue = (next ? (next.location || "") : "").trim();
  const gap = next && Number.isFinite(next.startMs) ? next.startMs - ev.endMs : Infinity;
  if (nextVenue && gap >= 0 && gap <= 90 * 60000) {
    return { insert: false, origin: venue, reason: "next-back-to-back-venue" };
  }
  return { insert: true, origin: venue, reason: "return-needed" };
}

module.exports = {
  fillTravel, directionsRoute, directionsMinutes, listEvents7d, isTravel, travelDecision, returnDecision, claimTravel, unclaimTravel,
  hasDeparturePopupReminder,
  recordTravelTelegramReceipt,
  // #71 pure helpers (unit-tested)
  parseDurationSeconds, minutesFromSeconds, buildDriveBody, clampDepartIso, acceptRouteResults,
  transitFetchPlan, wallAnchor, DEFAULT_TRANSIT_TIMEOUT_MS,
  parseGeoLiteral, geocodeAddress,
};
