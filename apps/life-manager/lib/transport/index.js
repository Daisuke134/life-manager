// lib/transport/index.js — #74 convergence: pick the calendar/mail transport by LIFE_TRANSPORT env.
// composio (default) = cloud managed-OAuth. gog (slice 5) = local BYOK CLI. The life-logic modules call
// getCalendar() and never touch a provider directly, so one JS codebase deploys cloud OR local.
"use strict";

const { makeComposioCalendar } = require("./calendar-composio.js");
const { makeUnipileCalendar } = require("./calendar-unipile.js");
const { makeUnipileMail } = require("./mail-unipile.js");
const { makeGogCalendar } = require("./calendar-gog.js");
const { makeGogMail } = require("./mail-gog.js");
const { makeCachedCalendar } = require("../calendar-cache.js");

// CommonJS keeps this module alive for the process lifetime, so repeated getCalendar() calls from
// separate life-logic modules share one wrapper. The cache itself remains intentionally in-memory.
const cachedCalendars = new Map();

// Resolve the transport kind, failing LOUD on an unrecognized LIFE_TRANSPORT rather than silently
// defaulting (a typo'd env must not quietly route a local BYOK box at the cloud provider).
function resolveKind(opts) {
  const kind = (process.env.LIFE_TRANSPORT || opts.kind || "composio").toLowerCase();
  if (kind !== "composio" && kind !== "gog") {
    throw new Error(`Unknown LIFE_TRANSPORT="${kind}" (expected "composio" or "gog")`);
  }
  return kind;
}

function resolveCalendarKind(opts) {
  const override = String(process.env.LIFE_CAL_TRANSPORT || "").trim().toLowerCase();
  if (!override) return resolveKind(opts);
  if (override !== "composio" && override !== "gog" && override !== "unipile") {
    throw new Error(`Unknown LIFE_CAL_TRANSPORT="${override}" (expected "composio", "gog", or "unipile")`);
  }
  return override;
}

function getCalendar(opts = {}) {
  const kind = resolveCalendarKind(opts);
  const unipileOpts = kind === "unipile" ? {
    ...opts,
    accountId: opts.accountId || opts.gmailAccountId,
    token: opts.token || opts.unipileToken || process.env.UNIPILE_TOKEN,
    dsn: opts.dsn || opts.unipileDsn || process.env.UNIPILE_DSN,
  } : opts;
  const inner = kind === "gog" ? makeGogCalendar(opts)
    : kind === "unipile" ? makeUnipileCalendar(unipileOpts)
      : makeComposioCalendar(opts);
  if ((process.env.LM_CAL_CACHE || "").toLowerCase() === "off") return inner;

  const identity = kind === "gog"
    ? [kind, opts.account !== undefined ? opts.account : (process.env.GOG_ACCOUNT || ""), opts.bin || process.env.GOG_BIN || "gog", opts.calId || "primary"]
    : kind === "unipile"
      ? [kind, unipileOpts.accountId || "", unipileOpts.token || "", unipileOpts.dsn || ""]
      : [kind, opts.apiKey || process.env.COMPOSIO_API_KEY || "", opts.expectedCalendarAccountId || ""];
  const key = JSON.stringify(identity);
  let cached = cachedCalendars.get(key);
  if (!cached) {
    cached = makeCachedCalendar(inner, opts);
    cachedCalendars.set(key, cached);
  }
  return cached;
}

function getMail(opts = {}) {
  return resolveKind(opts) === "gog" ? makeGogMail(opts) : makeUnipileMail(opts);
}

module.exports = { getCalendar, getMail };
