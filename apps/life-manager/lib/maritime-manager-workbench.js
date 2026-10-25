"use strict";

const UID = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const QUERY = `
  WITH ranked AS (
    SELECT row_to_json(jobs) AS job, receipts.receipt,
      COALESCE(jobs.completed_at, jobs.updated_at) AS observed_at,
      ROW_NUMBER() OVER (PARTITION BY jobs.capability
        ORDER BY COALESCE(jobs.completed_at, jobs.updated_at) DESC, jobs.job_id DESC) AS capability_rank
    FROM public.lm_runtime_jobs AS jobs
    LEFT JOIN public.lm_runtime_job_receipts AS receipts
      ON receipts.job_id = jobs.job_id
      AND receipts.tenant_id = jobs.tenant_id
      AND receipts.attempt = jobs.attempt
      AND receipts.outcome IN ('completed', 'reconciled_present')
    WHERE jobs.tenant_id = $1
      AND jobs.capability IN ('maritime.manager.cycle', 'maritime.manager.report')
      AND jobs.status IN ('completed', 'reconciling', 'dead_letter')
  )
  SELECT job, receipt, observed_at FROM ranked
  WHERE (job->>'capability' = 'maritime.manager.cycle' AND capability_rank <= $2)
     OR (job->>'capability' = 'maritime.manager.report' AND capability_rank = 1)
  ORDER BY observed_at DESC, job->>'job_id' DESC
`;

function observationTime(value) {
  const time = value instanceof Date ? value.toISOString() : new Date(value).toISOString();
  if (!Number.isFinite(Date.parse(time))) throw new Error("maritime_workbench_invalid");
  return time;
}

async function readMaritimeManagerWorkbench({ uid, limit = 10 } = {}, { query } = {}) {
  if (typeof uid !== "string" || !UID.test(uid) || !Number.isInteger(limit) || limit < 1 || limit > 20
    || typeof query !== "function") throw new Error("maritime_workbench_unconfigured");
  const result = await query(QUERY, [uid, limit]);
  const rows = result?.rows;
  if (!Array.isArray(rows) || rows.length > limit + 1) throw new Error("maritime_workbench_invalid");
  const history = [];
  let latestEmailReport = null;
  const seen = new Set();
  const runtime = require("./maritime-manager-runtime.js");
  const cycleAdapter = runtime.createMaritimeManagerLoopAdapter();
  const reportAdapter = runtime.createMaritimeManagerReportAdapter();
  let cyclesSeen = 0, reportsSeen = 0;

  for (const row of rows) {
    const job = row?.job;
    if (!job || job.tenant_id !== uid || !["completed", "reconciling", "dead_letter"].includes(job.status)
      || !["maritime.manager.cycle", "maritime.manager.report"].includes(job.capability)
      || typeof job.job_id !== "string" || seen.has(job.job_id)) throw new Error("maritime_workbench_invalid");
    seen.add(job.job_id);
    const observedAt = observationTime(row.observed_at);

    if (job.capability === "maritime.manager.cycle") {
      cyclesSeen++;
      if (cyclesSeen > limit) throw new Error("maritime_workbench_invalid");
      let status = "confirming";
      let artifactCount = 0;
      if (job.status === "dead_letter") status = "failed";
      else if (job.status === "completed" && cycleAdapter.verify(row.receipt, job)) {
        status = row.receipt.status === "completed" ? "verified_work" : "no_work";
        artifactCount = row.receipt.artifact_refs.length;
      }
      history.push({ kind: "work", status, observedAt, artifactCount });
      continue;
    }

    reportsSeen++;
    if (reportsSeen > 1) throw new Error("maritime_workbench_invalid");
    if (latestEmailReport === null) {
      latestEmailReport = job.status === "dead_letter"
        ? { status: "failed", observedAt }
        : job.status === "completed" && reportAdapter.verify(row.receipt, job)
        ? { status: "sent", sentAt: observationTime(row.receipt.sent_at), periodKey: row.receipt.period_key }
        : { status: "confirming", observedAt };
    }
  }

  return Object.freeze({ schemaVersion: 1, history: Object.freeze(history), latestEmailReport });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

function renderMaritimeWorkbench({ language = "en", workbench = null, unavailable = false } = {}) {
  const ja = String(language).toLowerCase().startsWith("ja");
  const copy = ja ? {
    title: "Life Manager の状況",
    unavailable: "実行状況を取得できません。再読み込みしてもう一度ご確認ください。",
    none: "確認済みの仕事はまだ記録されていません。結果が確認でき次第、ここに表示します。",
    work: "確認済みの仕事", files: "件の成果物", noWork: "実行できる仕事は見つかりませんでした。",
    confirming: "実行結果を確認中です。確認できるまでは完了として扱いません。", failed: "この実行は完了しませんでした。",
    report: "メールレポート", noReport: "確認済みメールレポートはまだありません。", sent: "確認済みメールレポート送信済み", reportPending: "メールレポートの送信結果を確認中です。",
    reportFailed: "メールレポートを確認できませんでした。", income: "この実行履歴だけでは、Life Managerによる収益を確認できません。",
    refresh: "状況を更新",
  } : {
    title: "Life Manager status",
    unavailable: "Activity status is unavailable. Reload to check again.",
    none: "No verified work has been recorded yet. Results will appear here after they are confirmed.",
    work: "Verified work", files: "files", noWork: "No eligible work was found for this run.",
    confirming: "Result confirmation is pending. This run is not marked complete until verified.", failed: "This run did not complete.",
    report: "Email report", noReport: "No verified email report has been sent yet.", sent: "Verified email report sent", reportPending: "Email report delivery is being checked.",
    reportFailed: "Email report delivery could not be verified.", income: "This activity feed does not verify income earned by Life Manager.",
    refresh: "Refresh status",
  };
  const esc = escapeHtml;
  const history = Array.isArray(workbench?.history) ? workbench.history : [];
  const statusText = item => item.status === "verified_work" ? copy.work
    : item.status === "no_work" ? copy.noWork : item.status === "failed" ? copy.failed : copy.confirming;
  const rows = history.length ? history.map(item => {
    const count = Number.isInteger(item.artifactCount) && item.artifactCount > 0
      ? `<span>${item.artifactCount} ${esc(copy.files)}</span>` : "";
    return `<li><strong>${esc(statusText(item))}</strong>${count}<time datetime="${esc(item.observedAt)}">${esc(item.observedAt)}</time></li>`;
  }).join("") : `<li>${esc(copy.none)}</li>`;
  const report = workbench?.latestEmailReport;
  const reportText = report?.status === "sent" ? `${copy.sent}: ${report.sentAt}`
    : report?.status === "failed" ? copy.reportFailed : report ? copy.reportPending : copy.noReport;
  const body = unavailable ? `<p role="status">${esc(copy.unavailable)}</p>` : `<ul>${rows}</ul>
    <h3>${esc(copy.report)}</h3><p>${esc(reportText)}</p><p>${esc(copy.income)}</p>`;
  return `<section class="workbench" aria-labelledby="workbench-title"><h2 id="workbench-title">${esc(copy.title)}</h2>${body}
    <button type="button" data-action="refresh-workbench">${esc(copy.refresh)}</button></section>`;
}

module.exports = { readMaritimeManagerWorkbench, renderMaritimeWorkbench };
