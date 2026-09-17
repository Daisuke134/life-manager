"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  FAMILIES,
  loadMentalCatalog,
  selectMentalQuote,
  validateQuote,
} = require("./mental-catalog.js");

test("catalog loads only the approved external source set", () => {
  const ja = loadMentalCatalog("ja");
  assert.ok(ja.length >= 8);
  assert.ok(ja.every((quote) => quote.sourceRepo && !/anicca/i.test(quote.sourceRepo)));
  assert.ok(ja.every((quote) => FAMILIES.includes(quote.family)));
});

test("English catalog is independently authored and uses the same external provenance", () => {
  const en = loadMentalCatalog("en");
  assert.equal(en.length, 8);
  assert.ok(en.every((quote) => quote.text && !/anicca/i.test(quote.sourceRepo)));
  assert.ok(en.some((quote) => quote.text === "Courage can be quiet and still be real."));
});

test("catalog selection is deterministic and honors explicit themes", () => {
  const input = {
    uid: "u1",
    localDay: "2026-09-17",
    window: "morning_orientation",
    family: "affirmation",
    profile: { themes: ["self-worth"], tones: ["gentle"], avoidThemes: [] },
    recentQuoteIds: [],
    locale: "ja",
  };
  const first = selectMentalQuote(input);
  const second = selectMentalQuote(input);
  assert.deepEqual(second, first);
  assert.ok(first.themes.includes("self-worth"));
});

test("recent and avoided catalog items cannot be selected", () => {
  const quotes = loadMentalCatalog("ja").filter((quote) => quote.family === "affirmation");
  const result = selectMentalQuote({
    uid: "u2", localDay: "2026-09-17", window: "morning_orientation", family: "affirmation",
    profile: { themes: [], tones: [], avoidThemes: ["medical"] },
    recentQuoteIds: quotes.map((quote) => quote.id), locale: "ja",
  });
  assert.equal(result, null);
});

test("catalog validation rejects claims that need personal evidence", () => {
  assert.throws(() => validateQuote({
    id: "bad", sourceRepo: "x", sourceCommit: "a", sourcePath: "b", license: "MIT",
    family: "affirmation", themes: [], tones: [], windows: [], riskFlags: ["guarantee"],
    text: "あなたは必ず成功する。", localized: { ja: "あなたは必ず成功する。" },
  }), /risk|guarantee|approved/i);
});
