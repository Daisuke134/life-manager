"use strict";

const V1_FAMILIES = new Set(["affirmation", "manifestation", "mindfulness_inquiry"]);
const V1_WINDOWS = ["morning_orientation", "midday_awareness", "evening_direction"];

function evaluateCanaryRows(rows, nowMs = Date.now()) {
  const list = Array.isArray(rows) ? rows : [];
  const v1 = list.filter((row) => V1_FAMILIES.has(row && row.family));
  const legacy = list.length - v1.length;
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
  const pass = v1.length > 0 && maxDaily <= 3 && (minGap === null || minGap >= 3 * 60 * 60 * 1000)
    && familyRepeatCount === 0 && templateRepeatCount === 0;
  return {
    observed_at: new Date(nowMs).toISOString(),
    v1_count: v1.length,
    legacy_count: legacy,
    daily_counts: dailyCounts,
    max_daily_count: maxDaily,
    min_gap_ms: minGap,
    family_repeats: familyRepeatCount,
    template_repeats: templateRepeatCount,
    windows,
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
  process.stdout.write(`${JSON.stringify(evaluateCanaryRows(rows))}\n`);
}

if (require.main === module) main().catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });

module.exports = { evaluateCanaryRows, readCanaryRows };
