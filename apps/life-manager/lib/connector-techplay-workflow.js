"use strict";

const { createHash } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { zonedSlotInstant } = require("./honne-ja-shadow-schedule.js");

const TIME_ZONE = "Asia/Tokyo";
const RSS_URL = "https://rss.techplay.jp/event/w3c-rss-format/rss.xml";
const EVENT_REF = /^techplay-event:\/\/event\/[1-9][0-9]*$/;
const EVENT_URL = /^https:\/\/techplay\.jp\/event\/([1-9][0-9]*)$/;
const MAX_DETAIL_HTML_BYTES = 2_000_000;
const MAX_DATA_PAGE_BYTES = 1_500_000;
const MAX_DIV_TAGS = 10_000;
const SCHOOL_AGE_ONLY = /(?:小学生|中学生|高校生|小中学生|小中高生|elementary\s+school|junior\s+high|high\s+school)[^\n。]{0,24}(?:限定|のみ|対象|向け)|(?:限定|のみ|対象|for)[^\n。]{0,24}(?:小学生|中学生|高校生|小中学生|小中高生|elementary\s+school|junior\s+high|high\s+school)/i;
const SAFE_CODES = new Set([
  "TECHPLAY_LISTING_NAVIGATION_FAILED", "TECHPLAY_LISTING_READ_FAILED", "TECHPLAY_LISTING_RESULT_CONTRACT_FAILED",
  "TECHPLAY_DETAIL_NAVIGATION_FAILED", "TECHPLAY_DETAIL_READ_FAILED", "TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED",
  "TECHPLAY_DETAIL_IDENTITY_MISMATCH_FAILED", "TECHPLAY_CALENDAR_CONFLICT_CHECK_FAILED", "TECHPLAY_AUDIT_FAILED",
  "TECHPLAY_CURSOR_INVALID", "TECHPLAY_CURSOR_WRITE_FAILED",
  "TECHPLAY_APPLIED_REFS_INVALID",
]);
const CURSOR_FILE = "techplay-discovery-cursor.json";

function readCursor(file) {
  try {
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 32_768) throw stageError("TECHPLAY_CURSOR_INVALID");
    const value = JSON.parse(fs.readFileSync(file, "utf8"));
    const valid = (rows) => Array.isArray(rows) && rows.length <= 50
      && rows.every((ref) => typeof ref === "string" && EVENT_REF.test(ref))
      && new Set(rows).size === rows.length;
    const validRetry = Array.isArray(value && value.retry) && value.retry.length <= 100
      && value.retry.every((item) => item && typeof item === "object" && !Array.isArray(item)
        && Object.keys(item).sort().join(",") === "ends_at,event_ref"
        && EVENT_REF.test(String(item.event_ref || ""))
        && Number.isFinite(Date.parse(String(item.ends_at || ""))));
    if (!value || value.schema_version !== 2 || !valid(value.pending)
      || !valid(value.completed) || !validRetry
      || new Set([...value.pending, ...value.completed, ...value.retry.map((item) => item.event_ref)]).size
        !== value.pending.length + value.completed.length + value.retry.length) {
      throw stageError("TECHPLAY_CURSOR_INVALID");
    }
    return value;
  } catch (error) {
    if (error && error.code === "ENOENT") return { schema_version: 2, pending: [], completed: [], retry: [] };
    throw preserveSafe(error, "TECHPLAY_CURSOR_INVALID");
  }
}

function writeCursor(file, value) {
  const temporary = `${file}.${process.pid}.${Date.now()}.tmp`;
  try {
    fs.writeFileSync(temporary, `${JSON.stringify(value)}\n`, { flag: "wx", mode: 0o600 });
    fs.renameSync(temporary, file);
  } catch (error) {
    try { fs.unlinkSync(temporary); } catch { /* no temporary file to remove */ }
    throw preserveSafe(error, "TECHPLAY_CURSOR_WRITE_FAILED");
  }
}

function invalid() { throw new Error("TECH PLAY workflow invalid"); }
function stageError(code) { const error = new Error("TECH PLAY workflow stage failed"); error.code = code; return error; }
function preserveSafe(error, fallback) { const code = String(error && error.code || ""); return stageError(SAFE_CODES.has(code) ? code : fallback); }

function localParts(value) {
  if (!(value instanceof Date) || !Number.isFinite(value.getTime())) invalid();
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(value).filter((part) => part.type !== "literal").map((part) => [part.type, Number(part.value)]));
  if (![parts.year, parts.month, parts.day].every(Number.isInteger)) invalid();
  return parts;
}

function candidateWindow(observed) {
  const parts = localParts(observed);
  const end = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + 14));
  return Object.freeze({
    start: Date.parse(zonedSlotInstant(parts, "00:00", TIME_ZONE)),
    end: Date.parse(zonedSlotInstant({ year: end.getUTCFullYear(), month: end.getUTCMonth() + 1, day: end.getUTCDate() }, "00:00", TIME_ZONE)),
  });
}

function exactUrl(value) {
  const raw = String(value == null ? "" : value).trim();
  const match = EVENT_URL.exec(raw);
  return match ? Object.freeze({ canonical_url: raw, id: match[1] }) : null;
}

function canonicalBinding(value) {
  const row = typeof value === "string" ? { canonical_url: value } : value;
  if (!row || typeof row !== "object" || Array.isArray(row)) return null;
  const parsed = exactUrl(row.canonical_url || row.href || row.url);
  if (!parsed) return null;
  const eventRef = `techplay-event://event/${parsed.id}`;
  if (row.event_ref != null && String(row.event_ref) !== eventRef) return null;
  if (row.event_id != null && String(row.event_id) !== parsed.id) return null;
  return Object.freeze({ event_ref: eventRef, canonical_url: parsed.canonical_url });
}

function exactCandidate(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || value.provider !== "techplay"
    || !EVENT_REF.test(String(value.event_ref || ""))) invalid();
  const binding = canonicalBinding(value);
  const ticketId = String(value.ticket_id || "");
  if (!binding || binding.event_ref !== value.event_ref || binding.canonical_url !== value.canonical_url
    || !String(value.title || "").trim() || !Number.isFinite(Date.parse(String(value.starts_at || "")))
    || !Number.isFinite(Date.parse(String(value.ends_at || ""))) || Date.parse(value.starts_at) >= Date.parse(value.ends_at)
    || typeof value.ticket_id !== "string" || !/^[1-9][0-9]*$/.test(ticketId) || value.registration_status !== "available"
    || value.ticket_price_status !== "free" || value.ticket_price_minor !== 0) invalid();
  return value;
}

function calendarIntervals(calendar) {
  return Array.isArray(calendar) ? calendar : calendar && Array.isArray(calendar.busy_intervals) ? calendar.busy_intervals : [];
}

function overlaps(candidate, busy) {
  if (!busy || busy.kind !== "timed") return false;
  const start = Date.parse(candidate.starts_at); const end = Date.parse(candidate.ends_at);
  const busyStart = Date.parse(busy.start_at); const busyEnd = Date.parse(busy.end_at);
  return [start, end, busyStart, busyEnd].every(Number.isFinite) && start < busyEnd && end > busyStart;
}

function exactCoverage(candidate, busy) {
  return overlaps(candidate, busy) && String(busy.connector_idempotency || "") === createHash("sha256")
    .update(candidate.canonical_url, "utf8").digest("hex");
}

function defaultCalendarFree(candidate, calendar) {
  return !calendarIntervals(calendar).some((busy) => overlaps(candidate, busy) && !exactCoverage(candidate, busy));
}

function assertPageUrl(page, expected, code) {
  if (page && typeof page.url === "function" && String(page.url()) !== expected) throw stageError(code);
}

function decodeHtmlEntities(value) {
  return String(value).replace(/&(?:quot|amp|lt|gt|apos|#39|#x27|#(\d+)|#x([0-9a-f]+));/gi, (entity, decimal, hexadecimal) => {
    const lower = entity.toLowerCase();
    if (lower === "&quot;") return '"';
    if (lower === "&amp;") return "&";
    if (lower === "&lt;") return "<";
    if (lower === "&gt;") return ">";
    if (lower === "&apos;" || lower === "&#39;" || lower === "&#x27;") return "'";
    const codePoint = Number(decimal ? decimal : `0x${hexadecimal}`);
    return Number.isInteger(codePoint) && codePoint > 0 && codePoint <= 0x10FFFF ? String.fromCodePoint(codePoint) : entity;
  });
}

function inertiaPayloadFromHtml(html) {
  if (typeof html !== "string" || html.length === 0 || html.length > MAX_DETAIL_HTML_BYTES) return null;
  const tags = [...html.matchAll(/<div\b[^>]*>/gi)];
  if (tags.length > MAX_DIV_TAGS) return null;
  let encoded = null;
  for (const match of tags) {
    const tag = match[0];
    const id = tag.match(/\bid\s*=\s*(["'])(.*?)\1/i);
    const data = tag.match(/\bdata-page\s*=\s*(["'])(.*?)\1/i);
    if (!id || id[2] !== "app" || !data) continue;
    if (encoded !== null) return null;
    encoded = data[2];
  }
  if (encoded === null || encoded.length > MAX_DATA_PAGE_BYTES) return null;
  try { return JSON.parse(decodeHtmlEntities(encoded)); } catch { return null; }
}

function sanitizeInertiaPayload(source) {
  const props = source && source.props;
  const event = props && props.event;
  const info = props && props.event_info_states;
  const button = props && props.event_button_states;
  const tickets = props && props.attend_types;
  if (!props || !event || !info || !button || !Array.isArray(tickets)) return null;
  return {
    current_url: String(props.currentUrl || "").trim(),
    event: {
      id: event.id, title: event.title, started_at: event.started_at, ended_at: event.ended_at,
      place: event.place, address: event.address, event_url: event.event_url,
      join_started_at: event.join_started_at, join_ended_at: event.join_ended_at,
      recruitment_start_at: event.recruitment_start_at, recruitment_end_at: event.recruitment_end_at,
      description: event.description,
    },
    event_info_states: {
      is_ended: info.is_ended, event_format: info.event_format, apply_status: info.apply_status,
      show_event_button: info.show_event_button, external_link_status: info.external_link_status,
    },
    event_button_states: { button_display_type: button.button_display_type, event_url: button.event_url, visible: button.visible },
    attend_types: tickets.map((ticket) => ({
      id: ticket && ticket.id, capacity: ticket && ticket.capacity, entrance_fee: ticket && ticket.entrance_fee,
      entered: ticket && ticket.entered, is_full: ticket && ticket.is_full,
      is_joined: ticket && ticket.is_joined, use_stripe: ticket && ticket.use_stripe,
    })),
  };
}

async function defaultReadRss(page) {
  if (!page || typeof page.goto !== "function" || typeof page.evaluate !== "function") invalid();
  try { await page.goto(RSS_URL, { waitUntil: "domcontentloaded", timeout: 30_000 }); assertPageUrl(page, RSS_URL, "TECHPLAY_LISTING_NAVIGATION_FAILED"); }
  catch (error) { if (error && error.code) throw error; throw stageError("TECHPLAY_LISTING_NAVIGATION_FAILED"); }
  try {
    return await page.evaluate(() => [...document.querySelectorAll("item")].map((item) => ({
      canonical_url: String(item.querySelector("link")?.textContent || item.querySelector("link")?.getAttribute("href") || "").trim(),
    })));
  } catch { throw stageError("TECHPLAY_LISTING_READ_FAILED"); }
}

async function defaultReadEventDetail(page, canonicalUrl) {
  if (!page || typeof page.goto !== "function") invalid();
  let response;
  try { response = await page.goto(canonicalUrl, { waitUntil: "domcontentloaded", timeout: 30_000 }); assertPageUrl(page, canonicalUrl, "TECHPLAY_DETAIL_NAVIGATION_FAILED"); }
  catch (error) { if (error && error.code) throw error; throw stageError("TECHPLAY_DETAIL_NAVIGATION_FAILED"); }
  if (!response || typeof response.text !== "function") throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
  let responseUrl = "";
  try { responseUrl = typeof response.url === "function" ? String(response.url()) : String(response.url || ""); }
  catch { throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED"); }
  if (responseUrl !== canonicalUrl) throw stageError("TECHPLAY_DETAIL_NAVIGATION_FAILED");
  let status;
  try { status = typeof response.status === "function" ? response.status() : response.status; }
  catch { throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED"); }
  if (status !== 200) throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
  let html;
  try { html = await response.text(); }
  catch { throw stageError("TECHPLAY_DETAIL_READ_FAILED"); }
  const source = inertiaPayloadFromHtml(html);
  const payload = sanitizeInertiaPayload(source);
  if (!payload || !payload.current_url) throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
  return payload;
}

function payloadParts(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
  const payload = raw.props && typeof raw.props === "object" && !Array.isArray(raw.props) ? raw.props : raw;
  if (!payload.event || typeof payload.event !== "object" || Array.isArray(payload.event)) throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
  const currentUrl = raw.current_url ?? raw.currentUrl ?? payload.current_url ?? payload.currentUrl;
  if (currentUrl == null || !String(currentUrl).trim()) throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
  return { payload, currentUrl: String(currentUrl).trim() };
}

function unixMillis(value) {
  const number = typeof value === "number" ? value : (typeof value === "string" && /^\d+$/.test(value.trim()) ? Number(value) : NaN);
  return Number.isSafeInteger(number) && number > 0 ? number * 1000 : NaN;
}

function recruitmentOpen(event, nowMs) {
  const startValue = event.join_started_at ?? event.recruitment_start_at;
  const endValue = event.join_ended_at ?? event.recruitment_end_at;
  if (startValue == null && endValue == null) return true;
  const start = unixMillis(startValue); const end = unixMillis(endValue);
  return Number.isFinite(start) && Number.isFinite(end) && start < end && nowMs >= start && nowMs < end;
}

function ticketIsEligible(ticket) {
  if (!ticket || typeof ticket !== "object" || Array.isArray(ticket)) return false;
  const id = typeof ticket.id === "number" ? ticket.id : (typeof ticket.id === "string" && /^\d+$/.test(ticket.id) ? Number(ticket.id) : NaN);
  const capacity = typeof ticket.capacity === "number" ? ticket.capacity : NaN;
  const entered = typeof ticket.entered === "number" ? ticket.entered : NaN;
  return Number.isSafeInteger(id) && id > 0 && Number.isFinite(capacity) && capacity > 0
    && Number.isFinite(entered) && entered >= 0 && entered <= capacity
    && ticket.entrance_fee === 0 && ticket.is_full === false && ticket.is_joined === false && ticket.use_stripe === false;
}

function normalizeDetail(binding, raw, observed) {
  const parts = payloadParts(raw);
  const { payload, currentUrl } = parts;
  const event = payload.event;
  const expectedId = binding.event_ref.split("/").pop();
  if (currentUrl && currentUrl !== binding.canonical_url) throw stageError("TECHPLAY_DETAIL_IDENTITY_MISMATCH_FAILED");
  if (event.id == null) throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
  if (String(event.id) !== expectedId) throw stageError("TECHPLAY_DETAIL_IDENTITY_MISMATCH_FAILED");
  const title = String(event.title || "").trim();
  const starts = unixMillis(event.started_at); const ends = unixMillis(event.ended_at);
  if (!title || !Number.isFinite(starts) || !Number.isFinite(ends) || starts >= ends) return null;
  const info = payload.event_info_states; const button = payload.event_button_states;
  const tickets = payload.attend_types;
  if (!info || !button || !Array.isArray(tickets)) throw stageError("TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED");
  if (tickets.length !== 1) return null;
  const applyStatus = info.apply_status;
  const applyStatusOpen = applyStatus == null || /^(?:apply|available|open)$/i.test(String(applyStatus));
  const text = `${title} ${String(event.description || "")}`;
  const candidate = Object.freeze({
    provider: "techplay", event_ref: binding.event_ref, canonical_url: binding.canonical_url, title,
    starts_at: new Date(starts).toISOString(), ends_at: new Date(ends).toISOString(),
    registration_status: "available", ticket_id: String(tickets[0].id), ticket_price_status: "free", ticket_price_minor: 0,
  });
  const eligible = event.event_url === null && button.event_url === null && button.button_display_type === "apply"
    && button.visible !== false
    && applyStatusOpen
    && info.show_event_button === true && info.is_ended === false && info.event_format === "offline_only"
    && info.external_link_status == null && /(?:Tokyo|東京)/i.test(`${event.place || ""} ${event.address || ""}`)
    && !SCHOOL_AGE_ONLY.test(text) && ends > observed.getTime() && recruitmentOpen(event, observed.getTime())
    && ticketIsEligible(tickets[0]);
  return { candidate, starts, ends, eligible };
}

function exactPositiveId(value) {
  if (typeof value === "number") return Number.isSafeInteger(value) && value > 0 ? String(value) : null;
  if (typeof value === "string" && /^[1-9][0-9]*$/.test(value)) return value;
  return null;
}

function readbackActionable(event, info, button, ticket, observedMs) {
  const applyStatus = info.apply_status;
  const applyOpen = applyStatus == null || /^(?:apply|available|open)$/i.test(String(applyStatus));
  const ends = unixMillis(event.ended_at);
  return event.event_url === null && button.event_url === null
    && button.button_display_type === "apply" && button.visible !== false && applyOpen
    && info.show_event_button === true && info.is_ended === false
    && info.event_format === "offline_only" && info.external_link_status == null
    && Number.isFinite(ends) && ends > observedMs && recruitmentOpen(event, observedMs)
    && ticketIsEligible(ticket);
}

function readbackStatus(selected, raw, observedMs) {
  let parts;
  try { parts = payloadParts(raw); } catch { return null; }
  if (parts.currentUrl !== selected.canonical_url) return null;
  const { payload } = parts;
  const event = payload.event; const info = payload.event_info_states;
  const button = payload.event_button_states; const tickets = payload.attend_types;
  if (!event || typeof event !== "object" || Array.isArray(event)
    || !info || typeof info !== "object" || Array.isArray(info)
    || !button || typeof button !== "object" || Array.isArray(button)
    || !Array.isArray(tickets) || tickets.length !== 1) return null;
  if (exactPositiveId(event.id) !== selected.event_ref.split("/").pop()) return null;
  const ticket = tickets[0];
  if (!ticket || typeof ticket !== "object" || Array.isArray(ticket)
    || exactPositiveId(ticket.id) !== selected.ticket_id || typeof ticket.is_joined !== "boolean") return null;
  if (ticket.is_joined === true) return "registered";
  return readbackActionable(event, info, button, ticket, observedMs) ? "absent" : null;
}

function createTechPlayDiscoveryWorkflow(options = {}) {
  const now = options.now || (() => new Date());
  const readRss = options.readRss || options.readRssFeed || options.readListingBindings || options.readListing || defaultReadRss;
  const readEventDetail = options.readEventDetail || defaultReadEventDetail;
  const isCalendarFree = options.isCalendarFree || defaultCalendarFree;
  const onDiscoveryAudit = options.onDiscoveryAudit || (() => {});
  const appliedEventRefs = options.appliedEventRefs || (async () => []);
  const maxDetailsPerWake = options.maxDetailsPerWake == null ? null : options.maxDetailsPerWake;
  const stateDir = options.stateDir;
  if (maxDetailsPerWake !== null && (!Number.isInteger(maxDetailsPerWake)
    || maxDetailsPerWake < 1 || maxDetailsPerWake > 50 || typeof stateDir !== "string"
    || !path.isAbsolute(stateDir))) invalid();
  const cursorFile = maxDetailsPerWake === null ? null : path.join(stateDir, CURSOR_FILE);
  if ([now, readRss, readEventDetail, isCalendarFree, onDiscoveryAudit, appliedEventRefs]
    .some((value) => typeof value !== "function")) invalid();
  return Object.freeze({
    async discoverCandidates({ page, calendar, remainingWakeMs, completionReserveMs }) {
      if ((remainingWakeMs != null || completionReserveMs != null)
        && (typeof remainingWakeMs !== "function" || !Number.isInteger(completionReserveMs)
          || completionReserveMs < 1)) invalid();
      const observed = now();
      if (!(observed instanceof Date) || !Number.isFinite(observed.getTime())) invalid();
      let rows;
      try { rows = await readRss(page, observed); } catch (error) { throw preserveSafe(error, "TECHPLAY_LISTING_READ_FAILED"); }
      rows = Array.isArray(rows) ? rows : rows && Array.isArray(rows.rows) ? rows.rows : null;
      if (!rows || rows.length > 50) throw stageError("TECHPLAY_LISTING_RESULT_CONTRACT_FAILED");
      const window = candidateWindow(observed); const bindings = []; const seen = new Set();
      for (const row of rows) {
        const binding = canonicalBinding(row);
        if (!binding || seen.has(binding.event_ref)) continue;
        seen.add(binding.event_ref); bindings.push(binding);
      }
      let cursor = null;
      let selectedBindings = bindings.map((binding) => ({ binding, source: "pending" }));
      if (cursorFile) {
        cursor = readCursor(cursorFile);
        const available = new Set(bindings.map((binding) => binding.event_ref));
        const appliedRows = await appliedEventRefs();
        if (!Array.isArray(appliedRows) || appliedRows.length > 10_000
          || appliedRows.some((ref) => typeof ref !== "string" || !EVENT_REF.test(ref))
          || new Set(appliedRows).size !== appliedRows.length) {
          throw stageError("TECHPLAY_APPLIED_REFS_INVALID");
        }
        const applied = new Set(appliedRows);
        let completed = cursor.completed.filter((ref) => available.has(ref));
        const pending = cursor.pending.filter((ref) => available.has(ref) && !applied.has(ref));
        const retry = cursor.retry.filter((item) => Date.parse(item.ends_at) > observed.getTime()
          && !applied.has(item.event_ref));
        if (pending.length === 0) completed = [];
        for (const ref of appliedRows) {
          if (available.has(ref) && !completed.includes(ref)) completed.push(ref);
        }
        const known = new Set([...pending, ...completed, ...retry.map((item) => item.event_ref)]);
        for (const binding of bindings) {
          if (!known.has(binding.event_ref)) pending.push(binding.event_ref);
        }
        cursor = { schema_version: 2, pending, completed, retry };
        const byRef = new Map(bindings.map((binding) => [binding.event_ref, binding]));
        const retryBudget = pending.length > 0
          ? Math.min(retry.length, 1, maxDetailsPerWake - 1) : Math.min(retry.length, maxDetailsPerWake);
        selectedBindings = [
          ...retry.slice(0, retryBudget).map((item) => ({
            binding: byRef.get(item.event_ref) || canonicalBinding({
              event_ref: item.event_ref,
              canonical_url: `https://techplay.jp/event/${item.event_ref.split("/").pop()}`,
            }), source: "retry",
          })),
          ...pending.slice(0, maxDetailsPerWake - retryBudget)
            .map((ref) => ({ binding: byRef.get(ref), source: "pending" })),
        ];
      }
      let processedCount = 0;
      let saturatedCount = 0;
      const markProcessed = (binding, source, eligible, endsAt) => {
        processedCount += 1;
        if (!cursor) return;
        cursor[source].shift();
        cursor[eligible ? "retry" : "completed"].push(eligible
          ? { event_ref: binding.event_ref, ends_at: endsAt } : binding.event_ref);
        writeCursor(cursorFile, cursor);
      };
      const exactCovered = []; const unprocessed = []; let withinWindowCount = 0; let eligibleCount = 0;
      for (const { binding, source } of selectedBindings) {
        if (remainingWakeMs && remainingWakeMs() <= completionReserveMs + 60_000) break;
        let raw;
        try { raw = await readEventDetail(page, binding.canonical_url); } catch (error) { throw preserveSafe(error, "TECHPLAY_DETAIL_READ_FAILED"); }
        try { assertPageUrl(page, binding.canonical_url, "TECHPLAY_DETAIL_NAVIGATION_FAILED"); }
        catch (error) { throw preserveSafe(error, "TECHPLAY_DETAIL_NAVIGATION_FAILED"); }
        let normalized;
        try { normalized = normalizeDetail(binding, raw, observed); } catch (error) {
          if (["TECHPLAY_DETAIL_IDENTITY_MISMATCH_FAILED", "TECHPLAY_DETAIL_RESULT_CONTRACT_FAILED"].includes(String(error && error.code || ""))) throw error;
          markProcessed(binding, source, false); continue;
        }
        if (!normalized || normalized.starts < window.start || normalized.starts >= window.end
          || normalized.ends >= window.end) { markProcessed(binding, source, false); continue; }
        withinWindowCount += 1;
        if (!normalized.eligible) { markProcessed(binding, source, false); continue; }
        eligibleCount += 1;
        let calendarFree;
        try { calendarFree = await isCalendarFree(normalized.candidate, calendar); } catch { throw stageError("TECHPLAY_CALENDAR_CONFLICT_CHECK_FAILED"); }
        if (!calendarFree) { markProcessed(binding, source, false); continue; }
        if (cursor && source === "pending" && cursor.retry.length >= 100) {
          saturatedCount = 1;
          break;
        }
        (calendarIntervals(calendar).some((busy) => exactCoverage(normalized.candidate, busy)) ? exactCovered : unprocessed).push(normalized.candidate);
        markProcessed(binding, source, true, normalized.candidate.ends_at);
      }
      const selectedCount = exactCovered.length + unprocessed.length;
      const retainedNotInRss = cursor ? cursor.retry.filter((item) => !seen.has(item.event_ref)).length : 0;
      try { await onDiscoveryAudit(Object.freeze({ discovered_count: rows.length + retainedNotInRss,
        rss_count: rows.length,
        saturated_count: saturatedCount,
        processed_count: processedCount,
        pending_count: cursor ? cursor.pending.length + cursor.retry.length : 0,
        within_window_count: withinWindowCount, eligible_count: eligibleCount,
        calendar_free_count: selectedCount, selected_count: selectedCount })); }
      catch (error) { throw preserveSafe(error, "TECHPLAY_AUDIT_FAILED"); }
      return Object.freeze([...exactCovered, ...unprocessed]);
    },
    async runDirectAction({ page, candidate }) {
      exactCandidate(candidate); void page;
      return Object.freeze({ status: "failed", safe_reason: "techplay_direct_requires_harness" });
    },
    async readProviderState({ page, candidate }) {
      const selected = exactCandidate(candidate);
      let observed;
      try { observed = now(); } catch { return Object.freeze({ status: "unavailable" }); }
      if (!(observed instanceof Date) || !Number.isFinite(observed.getTime())) return Object.freeze({ status: "unavailable" });
      if (!page || typeof page.url !== "function") return Object.freeze({ status: "unavailable" });
      let before;
      try { before = String(page.url()); } catch { return Object.freeze({ status: "unavailable" }); }
      if (before !== selected.canonical_url) return Object.freeze({ status: "unavailable" });
      let raw;
      try { raw = await readEventDetail(page, selected.canonical_url); } catch { return Object.freeze({ status: "unavailable" }); }
      let after;
      try { after = String(page.url()); } catch { return Object.freeze({ status: "unavailable" }); }
      if (after !== selected.canonical_url) return Object.freeze({ status: "unavailable" });
      const status = readbackStatus(selected, raw, observed.getTime());
      return Object.freeze({ status: status || "unavailable" });
    },
  });
}

module.exports = { createTechPlayDiscoveryWorkflow };
