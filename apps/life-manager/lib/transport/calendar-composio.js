// lib/transport/calendar-composio.js — CLOUD calendar transport (#74 convergence). Wraps the Composio
// managed-OAuth GOOGLECALENDAR_* tools behind the adapter interface every life-logic module will use,
// so the same JS runs cloud (this) or local (calendar-gog.js, slice 5). Behaviour-identical to the
// inline Composio calls it replaces — the live caller is unchanged.
"use strict";
const { recordCost } = require("../ledger.js");

const COMPOSIO_EXEC = "https://backend.composio.dev/api/v3/tools/execute";

async function exec(tool, uid, args, apiKey, fetchImpl, timeoutMs) {
  const signal = AbortSignal.timeout(timeoutMs);
  const r = await fetchImpl(`${COMPOSIO_EXEC}/${tool}`, {
    method: "POST",
    headers: { "x-api-key": apiKey, "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: uid, arguments: args }),
    signal,
  });
  return r.json();
}

function makeComposioCalendar({ apiKey, recordCall, fetchImpl = fetch, timeoutMs = 15000 } = {}) {
  const key = apiKey || process.env.COMPOSIO_API_KEY;
  const ledger = recordCall || ((uid, tool) => {
    if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) return false;
    return recordCost({ uid, kind: "composio_call", quantity: 1, unit: "call", estUsd: 0, meta: { tool } });
  });
  const execute = async (tool, uid, args) => {
    const result = await exec(tool, uid, args, key, fetchImpl, timeoutMs);
    await Promise.resolve(ledger(uid, tool)).catch(() => false);
    return result;
  };
  return {
    kind: "composio",
    ready: () => !!key,
    // Raw Google Calendar items (each consumer maps to its own shape) for [timeMin, timeMax] (ISO Z).
    async listEventsRaw(uid, { timeMin, timeMax, maxResults } = {}) {
      if (!key || !uid) return [];
      const args = { calendarId: "primary", singleEvents: true, orderBy: "startTime", timeMin, timeMax };
      if (maxResults) args.maxResults = maxResults;
      let j;
      try {
        j = await execute("GOOGLECALENDAR_EVENTS_LIST", uid, args);
      } catch { return []; }
      if (!j || !j.successful) return [];
      const d = j.data || {};
      return d.items || d.events || [];
    },
    async createEvent(uid, args) {
      if (!key) return { successful: false };
      try { return await execute("GOOGLECALENDAR_CREATE_EVENT", uid, args); } catch { return { successful: false }; }
    },
    async patchEvent(uid, args) {
      if (!key) return { successful: false };
      try { return await execute("GOOGLECALENDAR_PATCH_EVENT", uid, args); } catch { return { successful: false }; }
    },
  };
}

module.exports = { makeComposioCalendar };
