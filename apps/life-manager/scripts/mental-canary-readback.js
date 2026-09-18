"use strict";

const V1_FAMILIES = new Set(["affirmation", "manifestation", "mindfulness_inquiry"]);
const V1_WINDOWS = ["morning_orientation", "midday_awareness", "evening_direction"];

function summarizeV1Rows(v1) {
  const dailyCounts = {};
  const familiesByDay = new Map();
  const windows = Object.fromEntries(V1_WINDOWS.map((window) => [window, 0]));
  const templateCounts = new Map();
  const times = [];
  for (const row of v1) {
    const day = String(row.local_day || "");
    dailyCounts[day] = (dailyCounts[day] || 0) + 1;
    if (!familiesByDay.has(day)) familiesByDay.set(day, new Set());
    familiesByDay.get(day).add(String(row.family));
    if (Object.prototype.hasOwnProperty.call(windows, row.window)) windows[row.window] += 1;
    const template = String(row.template_id || "");
    templateCounts.set(template, (templateCounts.get(template) || 0) + 1);
    const sent = Date.parse(row.sent_at);
    if (Number.isFinite(sent)) times.push(sent);
  }
  times.sort((a, b) => a - b);
  let minGap = null;
  for (let i = 1; i < times.length; i += 1) {
    const gap = times[i] - times[i - 1];
    minGap = minGap === null ? gap : Math.min(minGap, gap);
  }
  const familyRepeatCount = [...familiesByDay.entries()].reduce((count, [day, set]) => {
    const dayRows = v1.filter((row) => String(row.local_day || "") === day);
    return count + Math.max(0, dayRows.length - set.size);
  }, 0);
  const templateRepeatCount = [...templateCounts.values()].reduce((count, value) => count + Math.max(0, value - 1), 0);
  const maxDaily = Object.values(dailyCounts).reduce((max, value) => Math.max(max, value), 0);
  return { dailyCounts, maxDaily, minGap, familyRepeatCount, templateRepeatCount, windows };
}

function evaluateCanaryRows(rows, nowMs = Date.now(), options = {}) {
  const list = Array.isArray(rows) ? rows : [];
  const v1 = list.filter((row) => V1_FAMILIES.has(row && row.family));
  const legacy = list.length - v1.length;
  const baselineAtMs = options.baselineAtMs == null ? null : Number(options.baselineAtMs);
  if (baselineAtMs !== null && !Number.isFinite(baselineAtMs)) throw new Error("canary baseline invalid");
  const canaryRows = baselineAtMs === null
    ? v1
    : v1.filter((row) => Number.isFinite(Date.parse(row.sent_at)) && Date.parse(row.sent_at) >= baselineAtMs);
  const preCanaryRows = baselineAtMs === null
    ? []
    : v1.filter((row) => Number.isFinite(Date.parse(row.sent_at)) && Date.parse(row.sent_at) < baselineAtMs);
  const allSummary = summarizeV1Rows(v1);
  const canarySummary = summarizeV1Rows(canaryRows);
  const preCanarySummary = summarizeV1Rows(preCanaryRows);
  const pass = canaryRows.length > 0 && canarySummary.maxDaily <= 3
    && (canarySummary.minGap === null || canarySummary.minGap >= 3 * 60 * 60 * 1000)
    && canarySummary.familyRepeatCount === 0 && canarySummary.templateRepeatCount === 0;
  return {
    observed_at: new Date(nowMs).toISOString(),
    v1_count: v1.length,
    legacy_count: legacy,
    daily_counts: allSummary.dailyCounts,
    max_daily_count: allSummary.maxDaily,
    min_gap_ms: allSummary.minGap,
    family_repeats: allSummary.familyRepeatCount,
    template_repeats: canarySummary.templateRepeatCount,
    windows: allSummary.windows,
    canary_v1_count: canaryRows.length,
    canary_daily_counts: canarySummary.dailyCounts,
    canary_max_daily_count: canarySummary.maxDaily,
    canary_min_gap_ms: canarySummary.minGap,
    canary_family_repeats: canarySummary.familyRepeatCount,
    pre_canary_template_repeats: preCanarySummary.templateRepeatCount,
    canary_start_at: baselineAtMs === null ? null : new Date(baselineAtMs).toISOString(),
    pass,
    telegram_content_readback: "required",
  };
}

async function readCanaryRows({ supaUrl, supaKey, uid, nowMs = Date.now(), fetchImpl = globalThis.fetch } = {}) {
  if (!supaUrl || !supaKey || !uid) throw new Error("canary readback configuration unavailable");
  const since = new Date(nowMs - 14 * 24 * 60 * 60 * 1000).toISOString();
  const query = `uid=eq.${encodeURIComponent(uid)}&sent_at=gte.${encodeURIComponent(since)}`
    + "&select=sent_at,family,template_id,local_day,window,telegram_message_id&order=sent_at.asc";
  const response = await fetchImpl(`${String(supaUrl).replace(/\/$/, "")}/rest/v1/lm_mental_send_log?${query}`, {
    headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}` },
  });
  if (!response.ok) throw new Error(`canary readback failed (${response.status})`);
  const rows = await response.json();
  if (!Array.isArray(rows)) throw new Error("canary readback returned invalid rows");
  return rows;
}

async function main() {
  const uid = String(process.env.LM_MENTAL_V1_ALLOWED_UIDS || process.env.LM_TENANT_UID || "").split(",")[0].trim();
  const rows = await readCanaryRows({ supaUrl: process.env.SUPABASE_URL, supaKey: process.env.SUPABASE_SERVICE_ROLE_KEY, uid });
  const baselineRaw = String(process.env.LM_MENTAL_CANARY_START_AT || "").trim();
  const baselineAtMs = baselineRaw ? Date.parse(baselineRaw) : null;
  if (baselineRaw && !Number.isFinite(baselineAtMs)) throw new Error("LM_MENTAL_CANARY_START_AT invalid");
  process.stdout.write(`${JSON.stringify(evaluateCanaryRows(rows, Date.now(), { baselineAtMs }))}\n`);
}

if (require.main === module) main().catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });

module.exports = { evaluateCanaryRows, readCanaryRows };
