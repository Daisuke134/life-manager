"use strict";

const { projectMentalProfile } = require("./mental-profile.js");

function base(url) { return String(url).replace(/\/$/, ""); }
function headers(key) { return { apikey: key, Authorization: `Bearer ${key}` }; }

async function readMentalProfile(uid, nowMs, supa, fetchImpl = globalThis.fetch) {
  const url = supa && (supa.url || supa.supaUrl);
  const key = supa && (supa.key || supa.supaKey);
  if (!url || !key) return { themes: [], tones: [], avoidThemes: [], goals: [], weights: {} };
  const query = `uid=eq.${encodeURIComponent(uid)}&select=uid,kind,tag,weight,basis,explicit,source_ref_hash,observed_at,expires_at,superseded_by&order=observed_at.desc`;
  const response = await fetchImpl(`${base(url)}/rest/v1/lm_mental_profile_tags?${query}`, { headers: headers(key) }).catch(() => null);
  if (!response || !response.ok) throw new Error(`mental profile lookup failed (${response ? response.status : "no response"})`);
  const rows = await response.json().catch(() => null);
  if (!Array.isArray(rows)) throw new Error("mental profile lookup returned no rows array");
  return projectMentalProfile(rows, nowMs);
}

module.exports = { readMentalProfile };
