"use strict";

const crypto = require("node:crypto");

const { goalSynthesisRefs, validateGoalContext } = require("./goal-context.js");
const { validateGoalPortfolio } = require("./goal-portfolio.js");
const { createGeneralAgentWorkLoopAdapter } = require("./general-agent-work-adapter.js");
const { buildRuntimeJob } = require("./runtime-job-store.js");

const RUNTIME_STATUSES = new Set(["queued", "running", "reconciling", "dead_letter"]);
const JOB_ID = /^goal:([a-z0-9][a-z0-9._-]{0,199}):r([1-9][0-9]*)$/iu;

function invalid(message = "cloud goal store invalid") {
  throw new Error(message);
}

function database(opts) {
  if (!opts || typeof opts.query !== "function") throw new Error("cloud goal store unavailable");
  return opts.query;
}

function identifier(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text || text.length > 200) throw new Error(`${label} invalid`);
  return text;
}

function scopeIdentity(scope) {
  return {
    uid: identifier(scope && scope.uid, "cloud goal tenant"),
    chatId: identifier(scope && scope.chatId, "cloud goal chat"),
  };
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
}

function digest(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function objectValue(value, label) {
  let parsed = value;
  if (typeof value === "string") {
    try { parsed = JSON.parse(value); } catch { throw new Error(`${label} invalid`); }
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} invalid`);
  }
  return parsed;
}

function oneOrNone(result, label) {
  const rows = result && result.rows;
  if (!Array.isArray(rows) || rows.length > 1) throw new Error(`${label} invalid`);
  return rows[0] || null;
}

function storedContext(row, tenantId) {
  const value = validateGoalContext(objectValue(row && row.context, "stored goal context"), tenantId);
  const canonical = canonicalJson(value);
  if (row.context_sha256 !== digest(canonical) || row.revision !== value.revision) {
    throw new Error("stored goal context invalid");
  }
  return value;
}

function authorizedRefs(context) {
  const refs = goalSynthesisRefs(context);
  return [...refs.factRefs, ...refs.evidenceRefs, ...refs.boundaryRefs];
}

function storedPortfolio(row, tenantId) {
  const context = storedContext({
    context: row && row.context,
    context_sha256: row && row.context_sha256,
    revision: row && row.revision,
  }, tenantId);
  const value = validateGoalPortfolio(
    objectValue(row && row.portfolio, "stored goal portfolio"),
    { tenantId, authorizedRefs: authorizedRefs(context) },
  );
  const canonical = canonicalJson(value);
  if (row.portfolio_sha256 !== digest(canonical) || row.revision !== value.revision) {
    throw new Error("stored goal portfolio invalid");
  }
  return value;
}

function validateGoalJob(row, tenantId, jobId) {
  const job = buildRuntimeJob(row);
  const identity = JOB_ID.exec(jobId);
  if (!identity
    || job.tenant_id !== tenantId || job.job_id !== jobId
    || job.loop_id !== "life-manager.manager" || job.capability !== "general-agent.work"
    || job.effect_class !== "none" || job.effect_key !== null || job.max_attempts !== 1
    || Object.keys(job.input_refs).length !== 1 || !job.input_refs.goal_ref
    || job.input_refs.goal_ref !== `goal-portfolio://${tenantId}/${identity[1]}?revision=${identity[2]}`) {
    throw new Error("cloud goal projection invalid");
  }
  return job;
}

function createCloudGoalStore(opts = {}) {
  const query = database(opts);

  async function loadContextRow(scope, revision = null) {
    const id = scopeIdentity(scope);
    return oneOrNone(await query(`
      SELECT context_row.tenant_id, context_row.revision, context_row.context,
             context_row.context_sha256
      FROM public.lm_goal_contexts AS context_row
      JOIN public.lm_users AS user_row ON user_row.uid = context_row.tenant_id
      WHERE context_row.tenant_id = $1
        AND user_row.telegram_chat_id::text = $2
        AND ($3::integer IS NULL OR context_row.revision = $3)
      ORDER BY context_row.revision DESC LIMIT 1
    `, [id.uid, id.chatId, revision]), "cloud goal context read");
  }

  async function loadContextForTenant(tenantId, revision = null) {
    const id = identifier(tenantId, "cloud goal tenant");
    return oneOrNone(await query(`
      SELECT context_row.tenant_id, context_row.revision, context_row.context,
             context_row.context_sha256
      FROM public.lm_goal_contexts AS context_row
      WHERE context_row.tenant_id = $1
        AND ($2::integer IS NULL OR context_row.revision = $2)
      ORDER BY context_row.revision DESC LIMIT 1
    `, [id, revision]), "cloud goal context read");
  }

  return Object.freeze({
    async putContext(scope, input) {
      const id = scopeIdentity(scope);
      const context = validateGoalContext(input, id.uid);
      const raw = canonicalJson(context);
      const sha256 = digest(raw);
      const row = oneOrNone(await query(`
        SELECT * FROM public.put_lm_goal_context($1,$2,$3,$4::jsonb,$5)
      `, [id.uid, id.chatId, context.revision, raw, sha256]), "cloud goal context write");
      if (!row) throw new Error("cloud goal scope mismatch");
      if (typeof row.created !== "boolean") throw new Error("stored goal context invalid");
      const saved = storedContext(row, id.uid);
      if (row.context_sha256 !== sha256) throw new Error("cloud goal context collision");
      return Object.freeze({ created: row.created === true, context: saved });
    },

    async loadContext(scope) {
      const id = scopeIdentity(scope);
      const row = await loadContextRow(id);
      return row ? storedContext(row, id.uid) : null;
    },

    async loadTenant(scope) {
      const id = scopeIdentity(scope);
      const user = oneOrNone(await query(`
        SELECT user_row.uid, user_row.telegram_chat_id::text AS telegram_chat_id,
               coalesce(user_row.paid, false) AS paid
        FROM public.lm_users AS user_row
        WHERE user_row.uid = $1 AND user_row.telegram_chat_id::text = $2
        LIMIT 1
      `, [id.uid, id.chatId]), "cloud goal tenant read");
      if (!user) return null;
      const contextRow = await loadContextRow(id);
      const context = contextRow ? storedContext(contextRow, id.uid) : null;
      if (!context) return null;
      const refs = goalSynthesisRefs(context);
      return Object.freeze({
        uid: id.uid,
        telegram_chat_id: id.chatId,
        paid: user.paid === true,
        fact_refs: refs.factRefs,
        evidence_refs: refs.evidenceRefs,
        boundary_refs: refs.boundaryRefs,
      });
    },

    async loadGoalPortfolio(tenantId) {
      const id = identifier(tenantId, "cloud goal tenant");
      const row = oneOrNone(await query(`
        SELECT portfolio_row.tenant_id, portfolio_row.revision, portfolio_row.portfolio,
               portfolio_row.portfolio_sha256, context_row.context,
               context_row.context_sha256
        FROM public.lm_goal_portfolios AS portfolio_row
        JOIN public.lm_goal_contexts AS context_row
          ON context_row.tenant_id = portfolio_row.tenant_id
         AND context_row.revision = portfolio_row.revision
        WHERE portfolio_row.tenant_id = $1
        ORDER BY portfolio_row.revision DESC LIMIT 1
      `, [id]), "cloud goal portfolio read");
      return row ? storedPortfolio(row, id) : null;
    },

    async saveGoalPortfolio(input) {
      const tenantId = identifier(input && input.tenant_id, "cloud goal tenant");
      const revision = input && input.revision;
      const contextRow = await loadContextForTenant(tenantId, revision);
      if (!contextRow) throw new Error("cloud goal context unavailable");
      const context = storedContext(contextRow, tenantId);
      const portfolio = validateGoalPortfolio(input, {
        tenantId,
        authorizedRefs: authorizedRefs(context),
      });
      const raw = canonicalJson(portfolio);
      const sha256 = digest(raw);
      const row = oneOrNone(await query(`
        SELECT * FROM public.put_lm_goal_portfolio($1,$2,$3::jsonb,$4)
      `, [tenantId, portfolio.revision, raw, sha256]), "cloud goal portfolio write");
      if (!row) throw new Error("cloud goal context unavailable");
      if (typeof row.created !== "boolean") throw new Error("stored goal portfolio invalid");
      const saved = storedPortfolio({ ...row, context, context_sha256: contextRow.context_sha256 }, tenantId);
      if (row.portfolio_sha256 !== sha256) throw new Error("cloud goal portfolio collision");
      return Object.freeze({ created: row.created === true, portfolio: saved });
    },

    async readProjection(input = {}) {
      const tenantId = identifier(input.tenantId, "cloud goal tenant");
      const jobId = identifier(input.jobId, "cloud goal job");
      const row = oneOrNone(await query(`
        SELECT jobs.job_id, jobs.tenant_id, jobs.loop_id, jobs.capability,
               jobs.effect_class, jobs.effect_key, jobs.input_refs,
               jobs.max_attempts, jobs.status, receipt_row.receipt,
               receipt_row.attempt AS receipt_attempt
        FROM public.lm_runtime_jobs AS jobs
        LEFT JOIN LATERAL (
          SELECT receipts.receipt, receipts.attempt
          FROM public.lm_runtime_job_receipts AS receipts
          WHERE receipts.tenant_id = jobs.tenant_id AND receipts.job_id = jobs.job_id
          ORDER BY receipts.attempt DESC LIMIT 1
        ) AS receipt_row ON true
        WHERE jobs.tenant_id = $1 AND jobs.job_id = $2
        LIMIT 1
      `, [tenantId, jobId]), "cloud goal projection read");
      if (!row) return null;
      const job = validateGoalJob(row, tenantId, jobId);
      let status = row.status;
      let receiptRef = null;
      if (row.receipt != null) {
        if (row.status !== "completed" || !Number.isInteger(row.receipt_attempt)
          || row.receipt_attempt < 1) invalid("cloud goal projection invalid");
        const receipt = objectValue(row.receipt, "cloud goal receipt");
        if (!createGeneralAgentWorkLoopAdapter().verify(receipt, job)) {
          throw new Error("cloud goal projection invalid");
        }
        status = receipt.status;
        receiptRef = `runtime-receipt://${tenantId}/${encodeURIComponent(jobId)}/${row.receipt_attempt}`;
      } else if (!RUNTIME_STATUSES.has(row.status)) {
        throw new Error("cloud goal projection invalid");
      }
      return Object.freeze({
        tenant_id: tenantId,
        goal_ref: job.input_refs.goal_ref,
        job_ref: `runtime-job://${tenantId}/${encodeURIComponent(jobId)}`,
        status,
        receipt_ref: receiptRef,
      });
    },
  });
}

module.exports = { createCloudGoalStore };
