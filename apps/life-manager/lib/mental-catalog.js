"use strict";

const fs = require("node:fs");
const path = require("node:path");

const CATALOG_PATH = path.join(__dirname, "../content/mental/catalog/ja.json");
const FAMILIES = Object.freeze(["affirmation", "manifestation", "mindfulness_inquiry"]);

function loadMentalCatalog(locale = "ja") {
  if (locale !== "ja") throw new Error("V1 catalog currently ships Japanese only");
  const rows = JSON.parse(fs.readFileSync(CATALOG_PATH, "utf8"));
  if (!Array.isArray(rows)) throw new Error("mental catalog must be an array");
  rows.forEach(validateQuote);
  return rows;
}

function validateQuote(quote) {
  if (!quote || typeof quote !== "object") throw new Error("catalog quote must be an object");
  if (!quote.id || !quote.sourceRepo || !/^[a-f0-9]{40}$/i.test(quote.sourceCommit)
      || !quote.sourcePath || quote.license !== "MIT") {
    throw new Error("catalog quote lacks approved provenance");
  }
  if (!FAMILIES.includes(quote.family)) throw new Error("catalog quote has unsupported family");
  if (!Array.isArray(quote.riskFlags) || quote.riskFlags.length) throw new Error("catalog quote has risk flags");
  if (!quote.text || quote.text.length > 80) throw new Error("catalog quote text invalid");
  if (/[?？]/.test(quote.text) && quote.family !== "mindfulness_inquiry") throw new Error("question outside inquiry family");
  if (/(必ず|絶対|治る|治癒|引き寄せ|宇宙が|神が)/.test(quote.text)) throw new Error("catalog quote contains unsafe certainty");
  return quote;
}

function selectMentalQuote({ uid, localDay, window, family, profile = {}, recentQuoteIds = [], locale = "ja" }) {
  const candidates = loadMentalCatalog(locale).filter((quote) => quote.family === family
    && quote.windows.includes(window)
    && !recentQuoteIds.includes(quote.id)
    && !(profile.avoidThemes || []).some((theme) => quote.themes.includes(theme)));
  if (!candidates.length) return null;
  const themes = new Set(profile.themes || []);
  const tones = new Set(profile.tones || []);
  const scored = candidates.map((quote) => ({
    quote,
    score: quote.themes.reduce((n, theme) => n + (themes.has(theme) ? 4 : 0), 0)
      + quote.tones.reduce((n, tone) => n + (tones.has(tone) ? 2 : 0), 0),
  })).sort((a, b) => b.score - a.score || `${uid}:${localDay}:${window}:${a.quote.id}`.localeCompare(`${uid}:${localDay}:${window}:${b.quote.id}`));
  return scored[0].quote;
}

module.exports = { FAMILIES, loadMentalCatalog, selectMentalQuote, validateQuote };
