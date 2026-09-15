"use strict";

// The graph is a read-only, tenant-scoped projection contract.  Provider ledgers
// and official receipts remain authoritative; nothing returned by this module
// grants permission to call a provider or to mutate an effect.

const GRAPH_VERSION = 1;
const NODE_KINDS = Object.freeze([
  "goal", "capability", "opportunity", "artifact", "effect",
  "receipt", "human_gate", "revenue", "resource",
]);
const EDGE_PREDICATES = Object.freeze([
  "requires", "produced_by", "sent_to", "proved_by", "earned",
  "blocked_by", "supersedes",
]);
const NODE_STATUSES = Object.freeze(["known", "stale", "unknown"]);
const PROVENANCE_KEYS = Object.freeze([
  "sourceFact", "authority", "observedAt", "confidence", "contentHash",
]);
const NODE_KEYS = Object.freeze(["id", "kind", "tenantId", "status", "provenance"]);
const EDGE_KEYS = Object.freeze(["id", "from", "to", "predicate", "provenance"]);
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SOURCE_FACT = /^[a-z][a-z0-9+.-]*:\/\/[^\s]{1,512}$/i;
const AUTHORITY = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function invalid(label) {
  throw new Error(`AgentGraph ${label} invalid`);
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid(label);
  const actual = Object.keys(value).sort();
  const keys = [...expected].sort();
  if (actual.length !== keys.length || actual.some((key, index) => key !== keys[index])) {
    invalid(label);
  }
}

function safeId(value, label) {
  if (typeof value !== "string" || !ID.test(value)) invalid(label);
  return value;
}

function instant(value, label) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))
    || !/[zZ]|[+-]\d\d:\d\d$/.test(value)) invalid(label);
  return new Date(value).toISOString();
}

function validateProvenance(value) {
  exactKeys(value, PROVENANCE_KEYS, "provenance");
  if (typeof value.sourceFact !== "string" || !SOURCE_FACT.test(value.sourceFact)) {
    invalid("sourceFact");
  }
  if (typeof value.authority !== "string" || !AUTHORITY.test(value.authority)) {
    invalid("authority");
  }
  const observedAt = instant(value.observedAt, "observedAt");
  if (typeof value.confidence !== "number" || !Number.isFinite(value.confidence)
    || value.confidence <= 0 || value.confidence > 1) invalid("confidence");
  if (typeof value.contentHash !== "string" || !SHA256.test(value.contentHash)) {
    invalid("contentHash");
  }
  return Object.freeze({ ...value, observedAt });
}

function validateNode(value) {
  exactKeys(value, NODE_KEYS, "node");
  safeId(value.id, "node id");
  if (!NODE_KINDS.includes(value.kind)) invalid("node kind");
  safeId(value.tenantId, "tenantId");
  if (!NODE_STATUSES.includes(value.status)) invalid("node status");
  const provenance = validateProvenance(value.provenance);
  return Object.freeze({ ...value, provenance });
}

function validateEdge(value) {
  exactKeys(value, EDGE_KEYS, "edge");
  safeId(value.id, "edge id");
  safeId(value.from, "edge from");
  safeId(value.to, "edge to");
  if (!EDGE_PREDICATES.includes(value.predicate)) invalid("edge predicate");
  const provenance = validateProvenance(value.provenance);
  return Object.freeze({ ...value, provenance });
}

function freezeArray(values) {
  return Object.freeze(values.map((value) => Object.freeze(value)));
}

function validateGraph(value) {
  exactKeys(value, ["version", "nodes", "edges"], "graph");
  if (value.version !== GRAPH_VERSION) invalid("version");
  if (!Array.isArray(value.nodes) || !Array.isArray(value.edges)
    || value.nodes.length > 10_000 || value.edges.length > 20_000) invalid("collections");

  const nodes = value.nodes.map(validateNode);
  const edges = value.edges.map(validateEdge);
  const nodeIds = new Set();
  const tenants = new Set();
  for (const item of nodes) {
    if (nodeIds.has(item.id)) invalid("duplicate node id");
    nodeIds.add(item.id);
    tenants.add(item.tenantId);
  }
  if (tenants.size > 1) invalid("tenant boundary");

  const edgeIds = new Set();
  for (const item of edges) {
    if (edgeIds.has(item.id)) invalid("duplicate edge id");
    edgeIds.add(item.id);
    if (!nodeIds.has(item.from) || !nodeIds.has(item.to)) invalid("dangling edge");
  }
  return Object.freeze({ version: GRAPH_VERSION, nodes: freezeArray(nodes), edges: freezeArray(edges) });
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

// Rebuild the read-only projection from append-only graph facts.  A fact is
// deliberately small and typed so callers cannot smuggle effect authority or
// credentials into the projection.  Repeated identical facts are harmless;
// conflicting records for one identity fail closed.
function projectLedgerFacts(facts) {
  if (!Array.isArray(facts) || facts.length > 30_000) invalid("facts");
  const nodes = new Map();
  const edges = new Map();
  for (const fact of facts) {
    exactKeys(fact, ["recordType", "value"], "fact");
    if (fact.recordType === "node") {
      const item = validateNode(fact.value);
      const previous = nodes.get(item.id);
      if (previous && stableStringify(previous) !== stableStringify(item)) invalid("conflicting node");
      nodes.set(item.id, item);
    } else if (fact.recordType === "edge") {
      const item = validateEdge(fact.value);
      const previous = edges.get(item.id);
      if (previous && stableStringify(previous) !== stableStringify(item)) invalid("conflicting edge");
      edges.set(item.id, item);
    } else {
      invalid("fact recordType");
    }
  }
  return validateGraph({
    version: GRAPH_VERSION,
    nodes: [...nodes.values()].sort((a, b) => a.id.localeCompare(b.id)),
    edges: [...edges.values()].sort((a, b) => a.id.localeCompare(b.id)),
  });
}

module.exports = {
  GRAPH_VERSION,
  NODE_KINDS,
  EDGE_PREDICATES,
  NODE_STATUSES,
  PROVENANCE_KEYS,
  validateProvenance,
  validateNode,
  validateEdge,
  validateGraph,
  projectLedgerFacts,
  // Explicit aliases keep the contract discoverable to callers that name the
  // records rather than the short validator names.
  validateGraphNode: validateNode,
  validateGraphEdge: validateEdge,
};
