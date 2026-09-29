"use strict";

const crypto = require("node:crypto");
const { decideCostReservation } = require("./cloud-plan-policy.js");

function micros(value, label, positive = false) {
  if (!Number.isSafeInteger(value) || value < (positive ? 1 : 0)) {
    throw new Error(`${label} must use ${positive ? "positive" : "non-negative"} integer micros`);
  }
  return value;
}

function text(value, label, max = 500) {
  const result = String(value || "").trim();
  if (!result || result.length > max) throw new Error(`${label} invalid`);
  return result;
}

function monthStart(nowMs) {
  const date = new Date(nowMs);
  if (!Number.isFinite(date.getTime())) throw new Error("cloud cost clock invalid");
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1);
}

function normalizeUsage(value, tenantId, jobId) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("cloud usage invalid");
  const entry = Object.freeze({
    tenant_id: text(value.tenant_id, "usage tenant", 200),
    job_id: text(value.job_id, "usage job", 200),
    provider: text(value.provider, "usage provider", 100),
    resource: text(value.resource, "usage resource", 200),
    quantity: micros(value.quantity, "usage quantity", true),
    unit: text(value.unit, "usage unit", 50),
    cost_usd_micros: micros(value.cost_usd_micros, "usage cost"),
    provider_receipt_id: text(value.provider_receipt_id, "usage provider receipt", 500),
  });
  if (entry.tenant_id !== tenantId || entry.job_id !== jobId) {
    throw new Error("cloud usage tenant/job mismatch");
  }
  return entry;
}

function createMemoryCloudCostStore() {
  const reservations = new Map();
  const receipts = new Map();
  const key = (tenantId, jobId, attempt) => `${tenantId}\0${jobId}\0${attempt}`;
  return Object.freeze({
    async snapshot(tenantId, nowMs) {
      const start = monthStart(nowMs);
      let monthlyActual = 0;
      let monthlyActivation = 0;
      let activationAllTime = 0;
      let activeReserved = 0;
      for (const row of reservations.values()) {
        if (row.tenant_id !== tenantId) continue;
        activationAllTime += row.activation_credit_applied_usd_micros || 0;
        if (row.month_start_ms !== start) continue;
        if (row.status === "settled") {
          monthlyActual += row.actual_cost_usd_micros;
          monthlyActivation += row.activation_credit_applied_usd_micros;
        } else if (["active", "reconciling"].includes(row.status)) {
          activeReserved += row.reserved_usd_micros;
        }
      }
      return {
        settled_billable_usd_micros: monthlyActual - monthlyActivation,
        active_reserved_usd_micros: activeReserved,
        activation_credit_used_usd_micros: activationAllTime,
        usage_count: [...receipts.values()].filter((row) => row.tenant_id === tenantId).length,
      };
    },
    async reserve(row) {
      const scoped = key(row.tenant_id, row.job_id, row.attempt);
      const existing = reservations.get(scoped);
      if (existing) {
        if (existing.reserved_usd_micros !== row.reserved_usd_micros
            || existing.plan_version !== row.plan_version) throw new Error("cloud cost reservation collision");
        return { created: false, row: { ...existing } };
      }
      reservations.set(scoped, { ...row, status: "active", actual_cost_usd_micros: null, activation_credit_applied_usd_micros: 0 });
      return { created: true, row: { ...reservations.get(scoped) } };
    },
    async reconcile(identity) {
      const row = reservations.get(key(identity.tenant_id, identity.job_id, identity.attempt));
      if (!row || row.reservation_ref !== identity.reservation_ref) throw new Error("cloud cost reservation unavailable");
      if (row.status === "settled") throw new Error("cloud cost reservation already settled");
      row.status = "reconciling";
      return { ...row };
    },
    async settle(identity, usage, nowMs) {
      const row = reservations.get(key(identity.tenant_id, identity.job_id, identity.attempt));
      if (!row || row.reservation_ref !== identity.reservation_ref) throw new Error("cloud cost reservation unavailable");
      const total = usage.reduce((sum, item) => sum + item.cost_usd_micros, 0);
      if (!Number.isSafeInteger(total) || total > row.reserved_usd_micros) {
        throw new Error("cloud cost exceeds reservation");
      }
      if (row.status === "settled") {
        if (row.actual_cost_usd_micros !== total
            || usage.some((item) => {
              const existing = receipts.get(item.provider_receipt_id);
              return !existing || JSON.stringify(existing) !== JSON.stringify(item);
            })) throw new Error("cloud provider receipt collision");
        return { row: { ...row }, replay: true };
      }
      for (const item of usage) {
        const existing = receipts.get(item.provider_receipt_id);
        if (existing && JSON.stringify(existing) !== JSON.stringify(item)) {
          throw new Error("cloud provider receipt collision");
        }
      }
      const snapshot = await this.snapshot(row.tenant_id, nowMs);
      const planCredit = row.plan_version === "free-v1" ? 1_000_000 : 0;
      const activationApplied = Math.min(total, Math.max(0, planCredit - snapshot.activation_credit_used_usd_micros));
      for (const item of usage) receipts.set(item.provider_receipt_id, { ...item });
      row.status = "settled";
      row.actual_cost_usd_micros = total;
      row.activation_credit_applied_usd_micros = activationApplied;
      return { row: { ...row }, replay: false };
    },
  });
}

function createCloudCostLedger(options = {}) {
  const store = options.store;
  for (const method of ["reconcile", "settle"]) {
    if (!store || typeof store[method] !== "function") throw new Error(`cloud cost store ${method} unavailable`);
  }
  if (typeof store.reserveAtomic !== "function"
      && (typeof store.snapshot !== "function" || typeof store.reserve !== "function")) {
    throw new Error("cloud cost store reservation unavailable");
  }
  const now = typeof options.now === "function" ? options.now : Date.now;
  const refToken = typeof options.refToken === "function" ? options.refToken : crypto.randomUUID;
  return Object.freeze({
    async reserve(input = {}) {
      const tenantId = text(input.tenantId, "cloud cost tenant", 200);
      const jobId = text(input.jobId, "cloud cost job", 200);
      const attempt = micros(input.attempt, "cloud cost attempt", true);
      const estimated = micros(input.estimatedMaxUsdMicros, "estimated cost", true);
      const nowMs = Number(now());
      if (typeof store.reserveAtomic === "function") {
        return Object.freeze(await store.reserveAtomic({
          tenant_id: tenantId, job_id: jobId, attempt,
          plan_version: input.planVersion, tenant_status: input.tenantStatus,
          estimated_max_usd_micros: estimated,
          reservation_ref: `lm-cost:${text(refToken(), "cloud cost reservation token", 200)}`,
          now_ms: nowMs,
        }));
      }
      const snapshot = await store.snapshot(tenantId, nowMs);
      const activationTotal = input.planVersion === "free-v1" ? 1_000_000 : 0;
      const decision = decideCostReservation({
        planVersion: input.planVersion,
        tenantStatus: input.tenantStatus,
        settledBillableUsdMicros: snapshot.settled_billable_usd_micros,
        activeReservedUsdMicros: snapshot.active_reserved_usd_micros,
        estimatedMaxUsdMicros: estimated,
        activationCreditRemainingUsdMicros: Math.max(0, activationTotal - snapshot.activation_credit_used_usd_micros),
        costStateKnown: true,
      });
      if (decision.decision !== "allow") return decision;
      const reservationRef = `lm-cost:${text(refToken(), "cloud cost reservation token", 200)}`;
      const saved = await store.reserve({
        reservation_ref: reservationRef,
        tenant_id: tenantId,
        job_id: jobId,
        attempt,
        plan_version: input.planVersion,
        month_start_ms: monthStart(nowMs),
        reserved_usd_micros: estimated,
      });
      if (saved.created === false) return Object.freeze({ decision: "duplicate" });
      return Object.freeze({
        decision: "allow",
        reservation_ref: saved.row.reservation_ref,
        reserved_usd_micros: saved.row.reserved_usd_micros,
        replay_zero: false,
      });
    },
    async settle(input = {}) {
      const identity = {
        tenant_id: text(input.tenantId, "cloud cost tenant", 200),
        job_id: text(input.jobId, "cloud cost job", 200),
        attempt: micros(input.attempt, "cloud cost attempt", true),
        reservation_ref: text(input.reservationRef, "cloud cost reservation ref", 250),
      };
      if (!Array.isArray(input.usage) || input.usage.length === 0) {
        const row = await store.reconcile(identity);
        return Object.freeze({ status: "reconciling", reason: "cost_unknown", held_usd_micros: row.reserved_usd_micros });
      }
      const entries = input.usage.map((entry) => normalizeUsage(entry, identity.tenant_id, identity.job_id));
      const result = await store.settle(identity, entries, Number(now()));
      return Object.freeze({
        status: "settled",
        actual_cost_usd_micros: result.row.actual_cost_usd_micros,
        released_usd_micros: result.row.reserved_usd_micros - result.row.actual_cost_usd_micros,
        activation_credit_applied_usd_micros: result.row.activation_credit_applied_usd_micros,
        replay_zero: result.replay,
      });
    },
    async release(input = {}) {
      if (typeof store.release !== "function") throw new Error("cloud cost release unavailable");
      const released = await store.release(
        text(input.tenantId, "cloud cost tenant", 200),
        text(input.reservationRef, "cloud cost reservation ref", 250),
      );
      return Object.freeze({ released: released === true });
    },
  });
}

function createPostgresCloudCostStore(options = {}) {
  const query = options.query;
  if (typeof query !== "function") throw new Error("cloud cost Postgres query unavailable");
  return Object.freeze({
    async reserveAtomic(input) {
      const rows = (await query(
        "SELECT * FROM public.reserve_lm_cloud_cost($1,$2,$3,$4,$5,$6,$7::timestamptz)",
        [input.tenant_id,input.job_id,input.attempt,input.plan_version,input.estimated_max_usd_micros,
          input.reservation_ref,new Date(input.now_ms).toISOString()],
      )).rows;
      if (rows.length !== 1) throw new Error("cloud cost reserve readback invalid");
      const row = rows[0];
      if (row.decision !== "allow") return { decision: row.decision };
      return {
        decision: "allow", reservation_ref: row.reservation_ref,
        reserved_usd_micros: Number(row.reserved_usd_micros), replay_zero: row.replay_zero === true,
      };
    },
    async reconcile(identity) {
      const rows = (await query(
        "SELECT * FROM public.reconcile_lm_cloud_cost($1,$2,$3,$4)",
        [identity.tenant_id,identity.job_id,identity.attempt,identity.reservation_ref],
      )).rows;
      if (rows.length !== 1) throw new Error("cloud cost reconcile readback invalid");
      return { reserved_usd_micros: Number(rows[0].held_usd_micros) };
    },
    async settle(identity, usage, nowMs) {
      const rows = (await query(
        "SELECT * FROM public.settle_lm_cloud_cost($1,$2,$3,$4,$5::jsonb,$6::timestamptz)",
        [identity.tenant_id,identity.job_id,identity.attempt,identity.reservation_ref,
          JSON.stringify(usage),new Date(nowMs).toISOString()],
      )).rows;
      if (rows.length !== 1) throw new Error("cloud cost settle readback invalid");
      return {
        row: {
          reserved_usd_micros: Number(rows[0].actual_cost_usd_micros)+Number(rows[0].released_usd_micros),
          actual_cost_usd_micros: Number(rows[0].actual_cost_usd_micros),
          activation_credit_applied_usd_micros: Number(rows[0].activation_credit_applied_usd_micros),
        },
        replay: rows[0].replay_zero === true,
      };
    },
    async release(tenantId, reservationRef) {
      const rows = (await query("SELECT public.release_lm_cloud_cost($1,$2) AS released", [tenantId,reservationRef])).rows;
      return rows.length === 1 && rows[0].released === true;
    },
  });
}

function usdMinorToMicros(value) {
  if (!value || value.currency !== "USD" || !Number.isSafeInteger(value.amount_minor) || value.amount_minor < 0) {
    throw new Error("unit economics requires non-negative USD minor records");
  }
  const microsValue = value.amount_minor * 10_000;
  if (!Number.isSafeInteger(microsValue)) throw new Error("unit economics amount overflow");
  return microsValue;
}

function buildCloudUnitEconomicsReport(input = {}) {
  const tenantId = text(input.tenantId, "unit economics tenant", 200);
  const month = String(input.monthStart || "");
  if (!/^\d{4}-\d{2}-01$/.test(month)) throw new Error("unit economics month invalid");
  if (!Array.isArray(input.records) || !Array.isArray(input.usage)) throw new Error("unit economics inputs invalid");
  const unsettled = micros(input.unsettledReservations, "unsettled reservations");
  let subscription = 0;
  let internalRevenue = 0;
  let refunds = 0;
  let stripeFees = 0;
  let userIncome = 0;
  const costs = new Map();
  for (const record of input.records) {
    if (!record || record.verification && record.verification.status !== "verified") continue;
    const amount = usdMinorToMicros(record);
    const provider = String(record.source && record.source.provider || "unknown");
    const externalRef = String(record.source && record.source.external_ref || "");
    if (record.scope === "personal" && record.kind === "personal_income") userIncome += amount;
    else if (record.scope === "business" && record.kind === "business_revenue") {
      if (provider === "stripe") subscription += amount;
      else internalRevenue += amount;
    } else if (record.scope === "business" && record.kind === "business_cost"
        && provider === "stripe" && /^refund[-_:]/i.test(externalRef)) refunds += amount;
    else if (record.scope === "business" && record.kind === "fee" && provider === "stripe") stripeFees += amount;
    else if (record.scope === "business" && ["business_cost", "fee", "tax"].includes(record.kind)) {
      const key = `financial:${provider}:${record.kind}`;
      costs.set(key, (costs.get(key) || 0) + amount);
    }
  }
  let shared = 0;
  for (const item of input.usage) {
    const provider = text(item.provider, "unit economics cost provider", 100);
    const resource = text(item.resource, "unit economics cost resource", 200);
    const amount = micros(Number(item.cost_usd_micros), "unit economics cost");
    if (provider === "anicca-shared") shared += amount;
    else {
      const key = `${provider}:${resource}`;
      costs.set(key, (costs.get(key) || 0) + amount);
    }
  }
  const variableCosts = [...costs.entries()].map(([key, cost]) => {
    const [provider, ...resource] = key.split(":");
    return { provider, resource: resource.join(":"), cost_usd_micros: cost };
  }).sort((a, b) => a.provider.localeCompare(b.provider) || a.resource.localeCompare(b.resource));
  const variable = variableCosts.reduce((sum, row) => sum + row.cost_usd_micros, 0);
  const known = unsettled === 0;
  return Object.freeze({
    tenant_id: tenantId,
    month_start: month,
    currency: "USD",
    cost_state: known ? "settled" : "unknown",
    subscription_collected_usd_micros: subscription,
    internal_company_revenue_usd_micros: internalRevenue,
    refunds_usd_micros: refunds,
    stripe_fees_usd_micros: stripeFees,
    variable_costs: Object.freeze(variableCosts.map(Object.freeze)),
    variable_cost_usd_micros: variable,
    allocated_shared_cost_usd_micros: shared,
    contribution_usd_micros: known
      ? subscription + internalRevenue - refunds - stripeFees - variable - shared
      : null,
    user_income_usd_micros: userIncome,
  });
}

function allocateSharedCost(totalUsdMicros, tenantIds) {
  const total = micros(totalUsdMicros, "shared cost");
  if (!Array.isArray(tenantIds) || tenantIds.length === 0) throw new Error("shared cost tenants invalid");
  const tenants = [...new Set(tenantIds.map((value) => text(value, "shared cost tenant", 200)))].sort();
  if (tenants.length !== tenantIds.length) throw new Error("shared cost tenants duplicate");
  const base = Math.floor(total / tenants.length);
  const remainder = total % tenants.length;
  return Object.freeze(tenants.map((tenantId, index) => Object.freeze({
    tenant_id: tenantId,
    cost_usd_micros: base + (index < remainder ? 1 : 0),
  })));
}

module.exports = {
  createCloudCostLedger,
  createMemoryCloudCostStore,
  createPostgresCloudCostStore,
  buildCloudUnitEconomicsReport,
  allocateSharedCost,
};
