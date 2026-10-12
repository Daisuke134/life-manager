"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  inspectLumaEvent,
  isVerifiedLumaEventDetail,
  normalizeLumaEventDetail,
} = require("./luma-event-detail.js");

function fixture(overrides = {}) {
  return {
    canonicalUrl: "https://luma.com/h8157e6c",
    jsonLd: [{
      "@type": "Event",
      name: "HYPER COASTER BEER RUN",
      startDate: "2026-08-02T09:30:00.000+09:00",
      endDate: "2026-08-02T12:00:00.000+09:00",
      eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
      eventStatus: "https://schema.org/EventScheduled",
      location: {
        "@type": "Place",
        name: "コースター・クラフトビール＆キッチン",
        address: {
          "@type": "PostalAddress",
          streetAddress: "1-2-3 Jingumae",
          addressLocality: "Shibuya",
          addressRegion: "Tokyo",
          addressCountry: "JP",
        },
      },
      description: "AI builders and founders meet for demos and conversation.",
      organizer: [{ "@type": "Organization", name: "Tokyo Builders" }],
      attendee: [{ "@type": "Person", name: "Public Guest" }],
      offers: [{
        "@type": "Offer", name: "General Admission", price: 0, priceCurrency: "usd",
        availability: "https://schema.org/InStock", url: "https://luma.com/h8157e6c",
      }],
    }],
    controls: ["ログイン", "参加登録", "ホストに連絡"],
    ...overrides,
  };
}

test("normalizes scheduled in-person detail and separates login from RSVP availability", () => {
  const detail = normalizeLumaEventDetail(fixture());
  assert.deepEqual(detail, {
    provider: "luma",
    canonical_url: "https://luma.com/h8157e6c",
    event_ref: "luma-event://event/h8157e6c",
    title: "HYPER COASTER BEER RUN",
    starts_at: "2026-08-02T00:30:00.000Z",
    ends_at: "2026-08-02T03:00:00.000Z",
    attendance_mode: "in_person",
    venue_name: "コースター・クラフトビール＆キッチン",
    venue_address: "1-2-3 Jingumae, Shibuya, Tokyo, JP",
    description: "AI builders and founders meet for demos and conversation.",
    organizer_names: ["Tokyo Builders"],
    participant_descriptors: ["Public Guest"],
    participant_visibility: "public_metadata",
    event_status: "scheduled",
    auth_status: "login_required",
    rsvp_status: "available",
    capacity_status: "availability_control_only",
    ticket_price_status: "free",
    ticket_price_minor: 0,
    ticket_currency: "USD",
    ticket_name: "General Admission",
    ticket_availability: "available",
    ticket_url: "https://luma.com/h8157e6c",
  });
  assert.equal(isVerifiedLumaEventDetail(detail), true);
  assert.equal(isVerifiedLumaEventDetail(structuredClone(detail)), false);
});

test("normalizes exact original-currency offers and chooses the cheapest available ticket", () => {
  const source = fixture();
  const detail = normalizeLumaEventDetail({
    ...source,
    jsonLd: [{
      ...source.jsonLd[0],
      offers: [
        { "@type": "Offer", name: "Sold", price: "1000", priceCurrency: "JPY", availability: "https://schema.org/SoldOut", url: "https://luma.com/h8157e6c" },
        { "@type": "Offer", name: "Standard", price: "2500", priceCurrency: "jpy", availability: "https://schema.org/InStock", url: "https://luma.com/h8157e6c" },
        { "@type": "Offer", name: "Supporter", price: "5000", priceCurrency: "JPY", availability: "https://schema.org/InStock", url: "https://luma.com/h8157e6c" },
      ],
    }],
  });
  assert.equal(detail.ticket_price_status, "paid");
  assert.equal(detail.ticket_price_minor, 2500);
  assert.equal(detail.ticket_currency, "JPY");
  assert.equal(detail.ticket_name, "Standard");
  assert.equal(detail.ticket_availability, "available");
});

test("missing or malformed offers remain unknown and never become free", () => {
  const source = fixture();
  const missing = normalizeLumaEventDetail({ ...source, jsonLd: [{ ...source.jsonLd[0], offers: undefined }] });
  assert.equal(missing.ticket_price_status, "unknown");
  assert.equal(missing.ticket_price_minor, null);
  assert.equal(missing.ticket_currency, null);
  const malformed = normalizeLumaEventDetail({
    ...source,
    jsonLd: [{ ...source.jsonLd[0], offers: [{ price: "12.345", priceCurrency: "USD", availability: "https://schema.org/InStock" }] }],
  });
  assert.equal(malformed.ticket_price_status, "unknown");
  assert.equal(malformed.ticket_price_minor, null);
});

test("keeps online events visible but marks them as not in-person", () => {
  const online = fixture({
    jsonLd: [{
      ...fixture().jsonLd[0],
      eventAttendanceMode: "https://schema.org/OnlineEventAttendanceMode",
      location: { "@type": "VirtualLocation", name: "Online" },
    }],
    controls: ["Register"],
  });

  assert.equal(normalizeLumaEventDetail(online).attendance_mode, "online");
  assert.equal(normalizeLumaEventDetail(online).rsvp_status, "available");
  assert.equal(normalizeLumaEventDetail(online).auth_status, "unknown");
});

test("missing public attendee metadata remains explicitly unavailable without invention", () => {
  const source = fixture();
  const detail = normalizeLumaEventDetail({
    ...source,
    jsonLd: [{ ...source.jsonLd[0], attendee: undefined }],
  });
  assert.deepEqual(detail.participant_descriptors, []);
  assert.equal(detail.participant_visibility, "unavailable");
  assert.equal(detail.organizer_names[0], "Tokyo Builders");
  assert.match(detail.venue_address, /Shibuya/);
});

test("classifies registered, closed, waitlist, full, approval, and unknown controls exactly", () => {
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["参加予定"] })).rsvp_status, "registered");
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["マイチケット"] })).rsvp_status, "registered");
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["承認待ち"] })).rsvp_status, "registered");
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["参加登録受付終了"] })).rsvp_status, "closed");
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["Registration Closed"] })).rsvp_status, "closed");
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["Join Waitlist"] })).rsvp_status, "waitlist");
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["Sold Out"] })).rsvp_status, "full");
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["Request to Join"] })).rsvp_status, "available");
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["参加リクエスト"] })).rsvp_status, "available");
  assert.equal(normalizeLumaEventDetail(fixture({ controls: ["ホストに連絡"] })).rsvp_status, "unknown");
});

test("host approval remains a gate when Luma also shows Request to Join", () => {
  assert.equal(normalizeLumaEventDetail(fixture({
    controls: ["Approval Required", "Request to Join"],
  })).rsvp_status, "approval_required");
  assert.equal(normalizeLumaEventDetail(fixture({
    controls: ["承認が必要", "参加リクエスト"],
  })).rsvp_status, "approval_required");
});

test("raw reader captures a non-button registration-closed notice", async () => {
  const page = {
    async evaluate(callback, canonicalUrl) {
      const originalDocument = global.document;
      global.document = {
        querySelectorAll(selector) {
          if (selector === 'script[type="application/ld+json"]') return [];
          if (selector === 'button, a[role="button"], input[type="submit"]') return [];
          if (selector === "div, span, p") return [{ innerText: "参加登録受付終了" }];
          return [];
        },
      };
      try { return callback(canonicalUrl); }
      finally { global.document = originalDocument; }
    },
  };
  const { readRawLumaEventDetail } = require("./luma-event-detail.js");
  const raw = await readRawLumaEventDetail(page, "https://luma.com/tokyo-one");
  assert.deepEqual(raw.controls, ["参加登録受付終了"]);
});

test("raw reader captures a non-button approval requirement next to its request control", async () => {
  const page = {
    async evaluate(callback, canonicalUrl) {
      const originalDocument = global.document;
      global.document = {
        querySelectorAll(selector) {
          if (selector === 'script[type="application/ld+json"]') return [];
          if (selector === 'button, a[role="button"], input[type="submit"]') {
            return [{ innerText: "Request to Join" }];
          }
          if (selector === "div, span, p") return [{ innerText: "Approval Required" }];
          return [];
        },
      };
      try { return callback(canonicalUrl); }
      finally { global.document = originalDocument; }
    },
  };
  const { readRawLumaEventDetail } = require("./luma-event-detail.js");
  const raw = await readRawLumaEventDetail(page, "https://luma.com/tokyo-one");
  assert.deepEqual(raw.controls, ["Request to Join", "Approval Required"]);
});

test("hybrid event with a sold-out venue ticket is full even when online registration remains", () => {
  const detail = normalizeLumaEventDetail(fixture({
    controls: [
      "会場参加 売り切れ 無料",
      "オンライン参加 無料",
      "参加登録",
    ],
  }));

  assert.equal(detail.rsvp_status, "full");
});

test("Japanese one-click registration is available", () => {
  assert.equal(normalizeLumaEventDetail(fixture({
    controls: ["ワンクリックで参加登録"],
  })).rsvp_status, "available");
});

test("rejects malformed provider detail instead of inventing date or venue", () => {
  assert.equal(normalizeLumaEventDetail(fixture({ jsonLd: [] })), null);
  assert.equal(normalizeLumaEventDetail(fixture({
    jsonLd: [{ ...fixture().jsonLd[0], startDate: "tomorrow" }],
  })), null);
  assert.equal(normalizeLumaEventDetail(fixture({
    canonicalUrl: "https://example.com/event",
  })), null);
});

test("event inspection uses the shared daily-driver and normalizes the provider readback", async () => {
  const calls = [];
  const page = { id: "owned-page" };
  const dailyDriver = {
    async withLumaPage(url, task) {
      calls.push(["withLumaPage", url]);
      return task(page);
    },
  };
  const detail = await inspectLumaEvent({
    dailyDriver,
    canonicalUrl: "https://luma.com/h8157e6c",
    readRawDetail: async (seenPage) => {
      assert.equal(seenPage, page);
      return fixture();
    },
  });

  assert.deepEqual(calls, [["withLumaPage", "https://luma.com/h8157e6c"]]);
  assert.equal(detail.event_ref, "luma-event://event/h8157e6c");
  assert.equal(detail.attendance_mode, "in_person");
});
