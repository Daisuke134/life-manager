"use strict";

const { lumaEventIdentity } = require("./luma-discovery.js");

const ATTENDANCE = new Map([
  ["https://schema.org/OfflineEventAttendanceMode", "in_person"],
  ["https://schema.org/OnlineEventAttendanceMode", "online"],
  ["https://schema.org/MixedEventAttendanceMode", "hybrid"],
]);
const EVENT_STATUS = new Map([
  ["https://schema.org/EventScheduled", "scheduled"],
  ["https://schema.org/EventCancelled", "cancelled"],
  ["https://schema.org/EventPostponed", "postponed"],
  ["https://schema.org/EventRescheduled", "rescheduled"],
]);
const VERIFIED = new WeakSet();

function bounded(value, max = 500) {
  const text = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
  return text && text.length <= max ? text : "";
}

function explicitDate(value) {
  const text = bounded(value, 100);
  if (!text || !/[zZ]|[+-][0-9]{2}:[0-9]{2}$/.test(text)) return null;
  const time = Date.parse(text);
  return Number.isFinite(time) ? new Date(time).toISOString() : null;
}

function normalizedControls(value) {
  if (!Array.isArray(value)) return new Set();
  return new Set(value.map((item) => bounded(item, 200).toLowerCase()).filter(Boolean));
}

function publicNames(value) {
  const rows = Array.isArray(value) ? value : value == null ? [] : [value];
  const result = [];
  for (const row of rows.slice(0, 100)) {
    const name = bounded(row && typeof row === "object" ? row.name : row, 300);
    if (name && !result.includes(name)) result.push(name);
  }
  return Object.freeze(result);
}

function priceMinor(value, currency) {
  const text = String(value == null ? "" : value).trim();
  const exponent = new Set(["JPY", "KRW"]).has(currency) ? 0 : 2;
  const pattern = exponent === 0 ? /^\d+$/ : /^\d+(?:\.\d{1,2})?$/;
  if (!pattern.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  try {
    const minor = BigInt(whole) * (10n ** BigInt(exponent))
      + BigInt((fraction + "0".repeat(exponent)).slice(0, exponent) || "0");
    return minor <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(minor) : null;
  } catch { return null; }
}

function offerAvailability(value) {
  const token = String(value == null ? "" : value).split("/").at(-1).toLowerCase();
  if (["instock", "limitedavailability", "onlineonly", "preorder"].includes(token)) return "available";
  if (["soldout", "outofstock", "discontinued"].includes(token)) return "unavailable";
  return "unknown";
}

function ticketPrice(event, canonicalUrl) {
  const source = Array.isArray(event.offers) ? event.offers : event.offers ? [event.offers] : [];
  const rows = source.slice(0, 100).map((offer) => {
    if (!offer || typeof offer !== "object" || Array.isArray(offer)) return null;
    const currency = bounded(offer.priceCurrency, 3).toUpperCase();
    if (!/^[A-Z]{3}$/.test(currency)) return null;
    const minor = priceMinor(offer.price, currency);
    if (minor === null) return null;
    const identity = lumaEventIdentity(offer.url || canonicalUrl);
    return Object.freeze({
      minor,
      currency,
      name: bounded(offer.name, 300),
      availability: offerAvailability(offer.availability),
      url: identity ? identity.canonicalUrl : null,
    });
  }).filter(Boolean);
  const pool = rows.filter((row) => row.availability === "available");
  const choices = pool.length > 0 ? pool : rows;
  if (choices.length === 0) return Object.freeze({
    ticket_price_status: "unknown", ticket_price_minor: null, ticket_currency: null,
    ticket_name: null, ticket_availability: "unknown", ticket_url: null,
  });
  const free = choices.find((row) => row.minor === 0);
  const currencies = new Set(choices.map((row) => row.currency));
  const selected = free || (currencies.size === 1
    ? choices.reduce((left, right) => right.minor < left.minor ? right : left)
    : null);
  if (!selected) return Object.freeze({
    ticket_price_status: "unknown", ticket_price_minor: null, ticket_currency: null,
    ticket_name: null, ticket_availability: "unknown", ticket_url: null,
  });
  return Object.freeze({
    ticket_price_status: selected.minor === 0 ? "free" : "paid",
    ticket_price_minor: selected.minor,
    ticket_currency: selected.currency,
    ticket_name: selected.name || null,
    ticket_availability: selected.availability,
    ticket_url: selected.url,
  });
}

function venueAddress(location) {
  const address = location && location.address;
  if (typeof address === "string") return bounded(address, 1_000);
  if (!address || typeof address !== "object" || Array.isArray(address)) return "";
  const country = address.addressCountry && typeof address.addressCountry === "object"
    ? address.addressCountry.name
    : address.addressCountry;
  return [
    address.streetAddress,
    address.addressLocality,
    address.addressRegion,
    address.postalCode,
    country,
  ].map((part) => bounded(part, 300)).filter(Boolean).join(", ");
}

function includesAny(controls, values) {
  return values.some((value) => controls.has(value));
}

function rsvpStatus(controls) {
  if (includesAny(controls, [
    "参加予定",
    "登録済み",
    "マイチケット",
    "my ticket",
    "you're going",
    "you’re going",
    "going",
    "承認待ち",
    "pending approval",
    "approval pending",
  ])) {
    return "registered";
  }
  if (includesAny(controls, [
    "参加登録受付終了",
    "registration closed",
    "registration has ended",
    "registration is closed",
    "rsvp closed",
  ])) return "closed";
  const inPersonTickets = [...controls].filter((value) => (
    /(?:会場参加|現地参加|in[ -]?person|on[ -]?site)/i.test(value)
  ));
  if (
    inPersonTickets.length > 0
    && inPersonTickets.every((value) => /(?:売り切れ|満席|sold out)/i.test(value))
  ) {
    return "full";
  }
  if (includesAny(controls, ["sold out", "満席"])) return "full";
  if (includesAny(controls, ["join waitlist", "キャンセル待ちに登録", "キャンセル待ち"])) {
    return "waitlist";
  }
  if (includesAny(controls, ["approval required", "承認が必要"])) {
    return "approval_required";
  }
  if (includesAny(controls, ["request to join", "参加リクエスト", "参加をリクエスト", "承認をリクエスト"])) {
    return "available";
  }
  if (includesAny(controls, ["ワンクリックで参加登録", "ワンクリック申し込み"])) {
    return "available";
  }
  if (includesAny(controls, ["register", "参加登録", "sign up", "rsvp"])) return "available";
  return "unknown";
}

function normalizeLumaEventDetail(input = {}) {
  const identity = lumaEventIdentity(input.canonicalUrl);
  const rows = Array.isArray(input.jsonLd) ? input.jsonLd : [];
  const event = rows.find((row) => row && row["@type"] === "Event");
  if (!identity || !event) return null;
  const title = bounded(event.name, 300);
  const startsAt = explicitDate(event.startDate);
  const endsAt = explicitDate(event.endDate);
  const attendanceMode = ATTENDANCE.get(event.eventAttendanceMode);
  const eventStatus = EVENT_STATUS.get(event.eventStatus) || "unknown";
  const venueName = bounded(event.location && event.location.name, 500);
  if (
    !title
    || !startsAt
    || !endsAt
    || Date.parse(endsAt) <= Date.parse(startsAt)
    || !attendanceMode
    || !venueName
  ) {
    return null;
  }
  const controls = normalizedControls(input.controls);
  const organizerNames = publicNames(event.organizer);
  const participantDescriptors = publicNames(event.attendee);
  const price = ticketPrice(event, identity.canonicalUrl);
  const authStatus = includesAny(controls, ["ログイン", "sign in", "log in"])
    ? "login_required"
    : "unknown";
  const detail = Object.freeze({
    provider: "luma",
    canonical_url: identity.canonicalUrl,
    event_ref: `luma-event://event/${identity.slug}`,
    title,
    starts_at: startsAt,
    ends_at: endsAt,
    attendance_mode: attendanceMode,
    venue_name: venueName,
    venue_address: venueAddress(event.location),
    description: bounded(event.description, 20_000),
    organizer_names: organizerNames,
    participant_descriptors: participantDescriptors,
    participant_visibility: participantDescriptors.length > 0 ? "public_metadata" : "unavailable",
    event_status: eventStatus,
    auth_status: authStatus,
    rsvp_status: rsvpStatus(controls),
    capacity_status: "availability_control_only",
    ...price,
  });
  VERIFIED.add(detail);
  return detail;
}

function isVerifiedLumaEventDetail(value) {
  return Boolean(value && typeof value === "object" && VERIFIED.has(value));
}

async function readRawLumaEventDetail(page, canonicalUrl) {
  if (!page || typeof page.evaluate !== "function") {
    throw new Error("Luma event page unavailable");
  }
  return page.evaluate((eventUrl) => {
    const rows = [];
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const parsed = JSON.parse(script.textContent || "null");
        const values = Array.isArray(parsed) ? parsed : parsed && parsed["@graph"] || [parsed];
        for (const value of values) {
          if (!value || value["@type"] !== "Event") continue;
          rows.push({
            "@type": "Event",
            name: value.name,
            startDate: value.startDate,
            endDate: value.endDate,
            eventAttendanceMode: value.eventAttendanceMode,
            eventStatus: value.eventStatus,
            description: value.description,
            organizer: (Array.isArray(value.organizer) ? value.organizer : [value.organizer])
              .filter(Boolean).slice(0, 100).map((row) => ({ name: row && row.name || row })),
            attendee: (Array.isArray(value.attendee) ? value.attendee : [value.attendee])
              .filter(Boolean).slice(0, 100).map((row) => ({ name: row && row.name || row })),
            offers: (Array.isArray(value.offers) ? value.offers : [value.offers])
              .filter(Boolean).slice(0, 100).map((offer) => ({
                "@type": offer && offer["@type"],
                name: offer && offer.name,
                price: offer && offer.price,
                priceCurrency: offer && offer.priceCurrency,
                availability: offer && offer.availability,
                url: offer && offer.url,
              })),
            location: value.location && {
              "@type": value.location["@type"],
              name: value.location.name,
              address: value.location.address && typeof value.location.address === "object" ? {
                streetAddress: value.location.address.streetAddress,
                addressLocality: value.location.address.addressLocality,
                addressRegion: value.location.address.addressRegion,
                postalCode: value.location.address.postalCode,
                addressCountry: value.location.address.addressCountry && typeof value.location.address.addressCountry === "object"
                  ? { name: value.location.address.addressCountry.name }
                  : value.location.address.addressCountry,
              } : value.location.address,
            },
          });
        }
      } catch {
        // Malformed provider metadata is ignored and fails closed during normalization.
      }
    }
    const controls = [...document.querySelectorAll(
      'button, a[role="button"], input[type="submit"]',
    )].map((element) => (
      element.innerText || element.value || element.getAttribute("aria-label") || ""
    )).map((value) => value.replace(/\s+/g, " ").trim()).filter(Boolean);
    const statusNotices = [...document.querySelectorAll("div, span, p")]
      .map((element) => String(element.innerText || element.textContent || "").replace(/\s+/g, " ").trim())
      .filter((value) => /^(?:参加登録受付終了|registration closed|registration has ended|registration is closed|rsvp closed|承認待ち|pending approval|approval pending|approval required|承認が必要)$/i.test(value));
    return {
      canonicalUrl: eventUrl,
      jsonLd: rows,
      controls: [...new Set([...controls, ...statusNotices])].slice(0, 100),
    };
  }, canonicalUrl);
}

async function inspectLumaEvent(options = {}) {
  const dailyDriver = options.dailyDriver;
  const canonicalUrl = String(options.canonicalUrl || "").trim();
  const readRawDetail = options.readRawDetail || readRawLumaEventDetail;
  if (!dailyDriver || typeof dailyDriver.withLumaPage !== "function") {
    throw new Error("Luma daily-driver unavailable");
  }
  const detail = await dailyDriver.withLumaPage(canonicalUrl, async (page) => (
    normalizeLumaEventDetail(await readRawDetail(page, canonicalUrl))
  ));
  if (!detail) throw new Error("Luma provider detail unavailable");
  return detail;
}

module.exports = {
  inspectLumaEvent,
  isVerifiedLumaEventDetail,
  normalizeLumaEventDetail,
  readRawLumaEventDetail,
};
