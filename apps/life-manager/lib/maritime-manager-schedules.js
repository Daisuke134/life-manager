'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { zoneOffsetHours, localDay } = require('./user-tz.js');
const { zonedSlotInstant } = require('./honne-ja-shadow-schedule.js');
function invalid() { throw new Error('maritime_schedule_invalid'); }
function identity(tenantId, releaseSha) {
  if (typeof tenantId !== 'string' || !/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(tenantId)
    || typeof releaseSha !== 'string' || !/^[0-9a-f]{40}$/.test(releaseSha)) invalid();
}
function instant(value, canonical = true) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    || !Number.isFinite(Date.parse(value)) || (canonical && new Date(value).toISOString() !== value)) invalid();
  return new Date(value).toISOString();
}
function projectMaritimeSchedules({ tenantId, releaseSha, status, pausedAt = null, nextEligibleAt, timezone, nowMs }) {
  identity(tenantId, releaseSha);
  if (!Number.isFinite(nowMs) || !['pending', 'provisioning', 'effect_unknown', 'active', 'paused'].includes(status)) invalid();
  const offset = zoneOffsetHours(timezone, nowMs);
  if (offset === null) invalid();
  if (pausedAt !== null) instant(pausedAt, false);
  const nextCycle = nextEligibleAt === null ? null : instant(nextEligibleAt, false);
  const paused = status === 'paused' || pausedAt !== null;
  const snapshot = { schema_version: 1, tenantId, releaseSha, paused, schedules: [] };
  if (paused || status !== 'active') return snapshot;
  if (nextEligibleAt !== null) snapshot.schedules.push({ id: `lm-cycle:${tenantId}`, nextRunAt: nextCycle, prompt: 'lm:cycle', enabled: true });
  const day = localDay(nowMs, offset);
  let nextReport;
  // Reuse the existing wall-clock inversion, including the DST round-trip check.
  // The third day covers a timezone that skips an entire local calendar day.
  for (let add = 0; add < 3; add++) {
    const date = new Date(`${day}T00:00:00.000Z`); date.setUTCDate(date.getUTCDate() + add);
    try {
      const at = zonedSlotInstant({ year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate() }, '19:00', timezone);
      if (Date.parse(at) > nowMs) { nextReport = at; break; }
    } catch { /* A non-existent local day is not a valid report occurrence. */ }
  }
  if (!nextReport) invalid();
  snapshot.schedules.push({ id: `lm-report:${tenantId}`, nextRunAt: nextReport, prompt: 'lm:report', enabled: true });
  return snapshot;
}
function validateSnapshot(snapshot, tenantId, releaseSha) {
  if (!snapshot || snapshot.schema_version !== 1 || snapshot.tenantId !== tenantId || snapshot.releaseSha !== releaseSha
    || typeof snapshot.paused !== 'boolean' || !Array.isArray(snapshot.schedules) || snapshot.schedules.length > 2) invalid();
  const seen = new Set();
  for (const entry of snapshot.schedules) {
    const kind = entry?.id === `lm-cycle:${tenantId}` ? 'cycle' : entry?.id === `lm-report:${tenantId}` ? 'report' : null;
    if (!kind || seen.has(kind) || entry.prompt !== `lm:${kind}` || entry.enabled !== true
      || Object.keys(entry).some(key => !['id', 'nextRunAt', 'prompt', 'enabled'].includes(key))) invalid();
    instant(entry.nextRunAt); seen.add(kind);
  }
  return snapshot.paused ? [] : snapshot.schedules;
}
function readMaritimeSchedules({ tenantId, releaseSha, dataRoot = '/data' }) {
  identity(tenantId, releaseSha);
  let fd;
  try {
    const root = fs.realpathSync(dataRoot);
    const home = path.join(root, tenantId);
    if (fs.lstatSync(home).isSymbolicLink() || fs.realpathSync(home) !== home) invalid();
    fd = fs.openSync(path.join(home, 'maritime-schedules.json'), fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.size > 32768) invalid();
    return validateSnapshot(JSON.parse(fs.readFileSync(fd, 'utf8')), tenantId, releaseSha);
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    invalid();
  } finally { if (fd !== undefined) fs.closeSync(fd); }
}
module.exports = { projectMaritimeSchedules, readMaritimeSchedules };
