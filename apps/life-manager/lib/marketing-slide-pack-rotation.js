"use strict";

// Selects the next approved-and-unposted slide pack for a native-carousel
// (Larry) lane/slot, biased toward hook/format families that scored above
// median on recorded creative metrics (explore/exploit, same shape as
// selectHook() in marketing-video-generation-adapter.js).
//
// ponytail: pure function over caller-supplied snapshots of
// candidates/history/metrics -- no I/O, no locking. Two schedulers racing
// the same slot could pick the same candidate; that is fine because the
// publish job's own job_id/effect_key dedup (buildMarketingNativeCarouselPublicationJob)
// is what actually prevents a double post -- this function only chooses
// *which* pack to try. Add a claim/lock if concurrent schedulers for the
// same lane become real.

function daysBetween(aIso, bIso) {
  return Math.abs(Date.parse(aIso) - Date.parse(bIso)) / 86400000;
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function familyScores(metrics) {
  const byFamily = new Map();
  for (const row of metrics) {
    if (!row || typeof row.familyId !== "string" || !row.familyId || !Number.isFinite(row.score)) continue;
    if (!byFamily.has(row.familyId)) byFamily.set(row.familyId, []);
    byFamily.get(row.familyId).push(row.score);
  }
  const avg = new Map();
  for (const [family, scores] of byFamily) avg.set(family, scores.reduce((a, b) => a + b, 0) / scores.length);
  return avg;
}

// candidates: [{ packRef, mediaRefs, captionRef, approvalRef, familyId, createdAt }]
// postedHistory: [{ packRef, postedAt }] (derive from the lane's publication distribution.jsonl)
// metrics: [{ familyId, score }] (derive from marketing-creative-metrics.js rows joined to a pack's familyId)
function selectSlidePack({ candidates, postedHistory = [], metrics = [], minDaysBetweenRepeat = 7, now }) {
  if (!Array.isArray(candidates)) throw new Error("slide pack candidates are invalid");
  if (!Array.isArray(postedHistory)) throw new Error("slide pack posted history is invalid");
  if (!Array.isArray(metrics)) throw new Error("slide pack metrics are invalid");
  if (!(Number(minDaysBetweenRepeat) >= 0)) throw new Error("slide pack minDaysBetweenRepeat is invalid");
  const nowIso = String(now || new Date().toISOString());
  if (!Number.isFinite(Date.parse(nowIso))) throw new Error("slide pack rotation clock is invalid");

  const lastPostedByPack = new Map();
  for (const row of postedHistory) {
    if (!row || typeof row.packRef !== "string" || !row.postedAt) continue;
    const current = lastPostedByPack.get(row.packRef);
    if (!current || current < row.postedAt) lastPostedByPack.set(row.packRef, row.postedAt);
  }

  const scoreByFamily = familyScores(metrics);
  const med = median([...scoreByFamily.values()]);

  const ranked = candidates
    .filter((candidate) => candidate && typeof candidate.packRef === "string" && candidate.packRef)
    .filter((candidate) => {
      const lastPosted = lastPostedByPack.get(candidate.packRef);
      return !lastPosted || daysBetween(lastPosted, nowIso) >= Number(minDaysBetweenRepeat);
    })
    .map((candidate) => {
      const score = scoreByFamily.has(candidate.familyId) ? scoreByFamily.get(candidate.familyId) : null;
      const underperforming = med != null && score != null && score < med;
      const everPosted = lastPostedByPack.has(candidate.packRef);
      const lastPosted = lastPostedByPack.get(candidate.packRef) || candidate.createdAt || "";
      return { candidate, underperforming, everPosted, lastPosted };
    })
    .sort((left, right) => {
      if (left.underperforming !== right.underperforming) return left.underperforming ? 1 : -1;
      if (left.everPosted !== right.everPosted) return left.everPosted ? 1 : -1;
      if (left.lastPosted !== right.lastPosted) return left.lastPosted < right.lastPosted ? -1 : 1;
      return left.candidate.packRef < right.candidate.packRef ? -1 : 1;
    });

  return ranked.length ? ranked[0].candidate : null;
}

module.exports = { selectSlidePack };
