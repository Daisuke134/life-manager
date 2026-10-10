"use strict";

// An offline planning projection, never admission to execute a provider effect.
const { normalizeProduct } = require("./mobile-product-registry.js");
const { projectFinancialRecord } = require("./financial-record-contract.js");
const CHECKS = ["core_flow", "quota", "entitlement", "copy", "privacy"];
const METRICS = ["visits", "successful_uses", "invoices_paid", "revenue_minor", "refunds_minor", "costs_minor"];
const MAX_AGE = 7 * 24 * 60 * 60 * 1000;
const ID = /^[a-z0-9][a-z0-9._-]{0,127}$/;
function requireValue(condition, label) { if (!condition) throw new Error(`Web App Factory ${label} invalid`); }
function fields(value, allowed, label) {
  requireValue(value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).every(key => allowed.includes(key)), `${label} fields`);
}
function rows(value, label) {
  requireValue(Array.isArray(value) && value.length <= 1000, label);
  return value;
}
function id(value, label) { requireValue(typeof value === "string" && ID.test(value), label); return value; }
function instant(value) {
  if (typeof value !== "string" || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?(?:Z|[+-]\d\d:\d\d)$/.test(value)) return NaN;
  return Date.parse(value);
}
function url(value) {
  let parsed;
  try { parsed = new URL(value); } catch { throw new Error("Web App Factory URL invalid"); }
  requireValue(parsed.protocol === "https:" && !parsed.username && !parsed.password
    && !parsed.search && !parsed.hash && !/[\\\s]/.test(value), "URL");
  return parsed.href;
}
function repositoryIdentity(value) {
  const parsed = new URL(url(value));
  // GitHub owner/repository names are case insensitive; .git and a trailing
  // slash do not create a different repository. Other hosts retain exact paths.
  if (parsed.hostname === "github.com") {
    const pathname = parsed.pathname.replace(/\/+$/, "").replace(/\.git$/i, "");
    requireValue(/^\/[^/]+\/[^/]+$/.test(pathname) && !pathname.includes("%"), "repository URL");
    return `https://github.com${pathname.toLowerCase()}`;
  }
  return parsed.href;
}
function path(value) {
  requireValue(typeof value === "string" && /^[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*$/.test(value)
    && !value.split("/").some(part => [".", ".."].includes(part)), "owned path");
  return value.toLowerCase();
}
function overlaps(a, b) { return a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`); }
function whole(value) { return Number.isSafeInteger(value) && value >= 0; }
function unique(values, label) { requireValue(new Set(values).size === values.length, `duplicate ${label}`); }

function evaluateWebAppFactory(input, { now } = {}) {
  fields(input, ["schema_version", "product", "assignment", "period", "demand", "qa", "marketing_claims", "distribution", "metrics", "financial_records", "additional_spend_minor", "unit_economics"], "input");
  requireValue(input.schema_version === 1, "schema_version");
  requireValue(input.additional_spend_minor === undefined || input.additional_spend_minor === 0, "zero budget");
  const nowMs = instant(now);
  requireValue(Number.isFinite(nowMs), "now");
  const product = input.product;
  fields(product, ["product_id", "display_name", "url", "source", "source_owner"], "product");
  id(product.product_id, "product_id");
  requireValue(typeof product.display_name === "string" && product.display_name.length > 0
    && product.display_name.length <= 120 && !/[\x00-\x1f\x7f]/.test(product.display_name), "display_name");
  fields(product.source, ["git_remote", "revision", "access"], "source");
  const source = normalizeProduct({ product_id: product.product_id, origin: "imported",
    source: { ...product.source, git_remote: url(product.source.git_remote) } }).source;
  const productUrl = url(product.url);
  const repositoryId = repositoryIdentity(source.git_remote);

  function proof(evidence, { production = true, revision = false } = {}) {
    if (evidence == null) return false;
    fields(evidence, ["product_id", "ref", "observed_at", "scope", "revision"], "evidence");
    const observed = instant(evidence.observed_at);
    return evidence.product_id === product.product_id
      && typeof evidence.ref === "string" && /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._:/-]{1,512}$/.test(evidence.ref)
      && ["offline", "provider_readback"].includes(evidence.scope)
      && (!production || evidence.scope === "provider_readback")
      && (!revision || evidence.revision === source.revision)
      && Number.isFinite(observed) && observed <= nowMs && nowMs - observed <= MAX_AGE;
  }

  const assignment = input.assignment;
  fields(assignment, ["owner", "worktree", "paths", "resource_ids", "lease", "inventory_complete", "claims"], "assignment");
  const owner = id(assignment.owner, "owner");
  requireValue(typeof assignment.worktree === "string" && assignment.worktree.startsWith("/")
    && assignment.worktree.length < 1024 && !/[\x00-\x1f]/.test(assignment.worktree)
    && !assignment.worktree.split("/").some(part => part === ".."), "worktree");
  const paths = rows(assignment.paths, "paths").map(path);
  requireValue(paths.length > 0, "paths"); unique(paths, "paths");
  const resources = rows(assignment.resource_ids, "resources").map(value => id(value, "resource"));
  unique(resources, "resources");
  const blockers = [];
  if (product.source_owner !== owner) blockers.push("source_owner_unconfirmed");
  if (assignment.inventory_complete !== true) blockers.push("coordination_inventory_incomplete");
  const lease = assignment.lease;
  if (lease != null) fields(lease, ["owner", "worktree", "expires_at"], "lease");
  if (!lease || lease.owner !== owner || lease.worktree !== assignment.worktree
    || !Number.isFinite(instant(lease.expires_at)) || instant(lease.expires_at) <= nowMs) blockers.push("worktree_lease_unconfirmed");
  for (const claim of rows(assignment.claims, "claims")) {
    fields(claim, ["owner", "repository", "paths", "resource_ids"], "claim");
    id(claim.owner, "claim owner");
    const repository = repositoryIdentity(claim.repository);
    const claimedPaths = rows(claim.paths, "claim paths").map(path);
    const claimedResources = rows(claim.resource_ids, "claim resources").map(value => id(value, "claim resource"));
    if (claim.owner === owner) continue;
    if ((repository === repositoryId && paths.some(a => claimedPaths.some(b => overlaps(a, b))))
      || resources.some(resource => claimedResources.includes(resource))) blockers.push("foreign_owner_conflict");
  }
  const ownership = { state: blockers.length ? "blocked" : "verified", owner, blockers: [...new Set(blockers)],
    execution_authority: false };

  const demand = rows(input.demand || [], "demand");
  for (const row of demand) {
    fields(row, ["kind", "evidence"], "demand");
    requireValue(["competitor", "problem_signal"].includes(row.kind), "demand kind");
  }
  const supportedDemand = demand.filter(row => proof(row.evidence));
  const demandReady = supportedDemand.some(competitor => competitor.kind === "competitor"
    && supportedDemand.some(signal => signal.kind === "problem_signal"
      && signal.evidence.ref !== competitor.evidence.ref));
  const qaRows = rows(input.qa || [], "qa");
  unique(qaRows.map(row => row.check), "QA");
  for (const row of qaRows) {
    fields(row, ["check", "status", "evidence"], "qa");
    requireValue(CHECKS.includes(row.check) && ["pass", "fail", "unknown"].includes(row.status), "QA check/status");
  }
  const qa = CHECKS.map(check => {
    const row = qaRows.find(item => item.check === check);
    const valid = row && proof(row.evidence, { production: false, revision: true });
    return { check, status: valid ? row.status : "unknown",
      production_verified: Boolean(valid && row.status === "pass" && proof(row.evidence, { revision: true })) };
  });
  const offlineVerified = qa.every(row => row.status === "pass");
  const productionVerified = qa.every(row => row.production_verified);
  const claims = rows(input.marketing_claims || [], "marketing claims");
  unique(claims.map(row => row.id), "marketing claims");
  const assessedClaims = claims.map(row => {
    fields(row, ["id", "evidence"], "marketing claim");
    return { id: id(row.id, "claim id"), state: proof(row.evidence, { revision: true }) ? "verified" : "unknown" };
  });
  const marketingReady = productionVerified && assessedClaims.length > 0 && assessedClaims.every(row => row.state === "verified");
  const economics = input.unit_economics;
  if (economics != null) fields(economics, ["price_minor", "price_currency", "max_variable_cost_minor", "cost_currency", "evidence"], "unit economics");
  const unitEconomicsReady = Boolean(economics && whole(economics.price_minor) && whole(economics.max_variable_cost_minor)
    && typeof economics.price_currency === "string" && /^[A-Z]{3}$/.test(economics.price_currency)
    && economics.price_currency === economics.cost_currency && economics.price_currency === input.period?.currency
    && economics.price_minor >= economics.max_variable_cost_minor && proof(economics.evidence, { revision: true }));
  const distribution = rows(input.distribution || [], "distribution").map(row => {
    fields(row, ["channel", "resource_id", "owner", "permission", "cost_minor"], "distribution");
    const reasons = [];
    if (!["owned_site", "owned_social", "permitted_community"].includes(row.channel)) reasons.push("channel_not_supported");
    if (row.cost_minor !== 0) reasons.push("cost_not_zero");
    if (row.permission !== "granted") reasons.push("permission_unconfirmed");
    if (row.owner !== owner || !resources.includes(row.resource_id)) reasons.push("resource_unowned");
    if (ownership.state !== "verified") reasons.push("ownership_blocked");
    if (!demandReady) reasons.push("demand_unverified");
    if (!marketingReady) reasons.push("marketing_unverified");
    if (!unitEconomicsReady) reasons.push("unit_economics_unverified");
    return { channel: typeof row.channel === "string" && ID.test(row.channel) ? row.channel : "unknown",
      resource_id: id(row.resource_id, "distribution resource"), state: reasons.length ? "blocked" : "draft_ready", reasons, execute: false };
  });

  const period = input.period;
  fields(period, ["start", "end", "currency"], "period");
  requireValue(Number.isFinite(instant(period.start)) && Number.isFinite(instant(period.end))
    && instant(period.start) < instant(period.end) && instant(period.end) <= nowMs, "period");
  requireValue(typeof period.currency === "string" && /^[A-Z]{3}$/.test(period.currency), "currency");
  const snapshots = input.metrics || {};
  fields(snapshots, METRICS, "metrics");
  const metrics = Object.fromEntries(METRICS.map(name => {
    const row = snapshots[name];
    if (row != null) fields(row, ["status", "value", "complete", "period_start", "period_end", "currency", "evidence"], "metric");
    const verified = Boolean(row && row.status === "verified" && whole(row.value) && row.complete === true
      && instant(row.period_start) === instant(period.start) && instant(row.period_end) === instant(period.end)
      && (!name.endsWith("_minor") || row.currency === period.currency) && proof(row.evidence)
      && instant(row.evidence.observed_at) >= instant(period.end));
    return [name, { status: verified ? "verified" : "unknown", value: verified ? row.value : null,
      evidence_ref: verified ? row.evidence.ref : null }];
  }));
  const financialRecords = rows(input.financial_records || [], "financial records").map(projectFinancialRecord);
  // Deliberately no inferred completeness, product attribution, or second CFO ledger.
  const money = ["revenue_minor", "refunds_minor", "costs_minor"].map(name => metrics[name].value);
  const net = money.every(value => value !== null) ? BigInt(money[0]) - BigInt(money[1]) - BigInt(money[2]) : null;
  requireValue(net === null || (net <= BigInt(Number.MAX_SAFE_INTEGER) && net >= BigInt(Number.MIN_SAFE_INTEGER)), "net contribution overflow");
  let nextTask;
  if (ownership.state !== "verified") nextTask = "resolve_ownership";
  else if (!demandReady) nextTask = "validate_demand";
  else if (qa.some(row => row.status === "fail")) nextTask = "repair_product";
  else if (!offlineVerified) nextTask = "verify_product_offline";
  else if (!productionVerified) nextTask = "verify_product_readback";
  else if (!marketingReady) nextTask = "prepare_factual_marketing";
  else if (!unitEconomicsReady) nextTask = "verify_unit_economics";
  else if (!distribution.some(row => row.state === "draft_ready")) nextTask = "resolve_distribution_permission";
  else nextTask = "prepare_distribution";
  return {
    schema_version: "web.app.factory.plan.v1", observed_at: new Date(nowMs).toISOString(),
    evidence_trust: "operator_attested", receipts_authenticated: false,
    product: { product_id: product.product_id, display_name: product.display_name, url: productUrl, source },
    ownership, demand_verified: demandReady, qa: { checks: qa, offline_verified: offlineVerified },
    production_verified: productionVerified, claims: assessedClaims, marketing_ready: marketingReady,
    unit_economics_verified: unitEconomicsReady, distribution, period: { ...period }, metrics,
    net_contribution_minor: net === null ? null : Number(net), financial_records_validated: financialRecords.length,
    next_task: nextTask, external_effects: false, additional_spend_minor: 0,
    lifecycle: { loop_id: "self-build", state: "setup_required", runtime_registered: false,
      requested_task: nextTask, requires_atomic_owner_lease: true },
  };
}
module.exports = { evaluateWebAppFactory };
