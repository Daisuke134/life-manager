"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  GRAPH_VERSION,
  NODE_KINDS,
  EDGE_PREDICATES,
  validateProvenance,
  validateNode,
  validateEdge,
  validateGraph,
} = require("./agent-graph.js");

const HASH = "a".repeat(64);
const OBSERVED_AT = "2026-09-15T00:00:00.000Z";

function provenance(overrides = {}) {
  return {
    sourceFact: "ledger://tenant-1/fact-1",
    authority: "life-manager-ledger",
    observedAt: OBSERVED_AT,
    confidence: 1,
    contentHash: HASH,
    ...overrides,
  };
}

function node(overrides = {}) {
  return {
    id: "goal-1",
    kind: "goal",
    tenantId: "tenant-1",
    status: "known",
    provenance: provenance(),
    ...overrides,
  };
}

function edge(overrides = {}) {
  return {
    id: "edge-1",
    from: "goal-1",
    to: "capability-1",
    predicate: "requires",
    provenance: provenance(),
    ...overrides,
  };
}

test("GRAPH-01 exposes the closed node and edge vocabularies", () => {
  assert.equal(GRAPH_VERSION, 1);
  assert.deepEqual(NODE_KINDS, [
    "goal", "capability", "opportunity", "artifact", "effect",
    "receipt", "human_gate", "revenue", "resource",
  ]);
  assert.deepEqual(EDGE_PREDICATES, [
    "requires", "produced_by", "sent_to", "proved_by", "earned",
    "blocked_by", "supersedes",
  ]);
});

test("a node and edge require complete provenance and validate", () => {
  assert.deepEqual(validateProvenance(provenance()), provenance());
  assert.deepEqual(validateNode(node()), node());
  assert.deepEqual(validateEdge(edge()), edge());
});

test("unknown predicates and missing provenance fail closed", () => {
  assert.throws(() => validateEdge(edge({ predicate: "depends_on" })), /predicate/i);
  assert.throws(() => validateEdge(edge({ provenance: undefined })), /provenance/i);
  assert.throws(() => validateNode(node({ provenance: undefined })), /provenance/i);
  assert.throws(() => validateProvenance(provenance({ contentHash: "short" })), /contentHash/i);
});

test("the graph rejects duplicate IDs, dangling edges, and cross-tenant joins", () => {
  assert.throws(() => validateGraph({
    version: GRAPH_VERSION,
    nodes: [node(), node({ id: "goal-1", kind: "capability" })],
    edges: [edge()],
  }), /duplicate/i);

  assert.throws(() => validateGraph({
    version: GRAPH_VERSION,
    nodes: [node()],
    edges: [edge()],
  }), /missing|unknown|dangling/i);

  assert.throws(() => validateGraph({
    version: GRAPH_VERSION,
    nodes: [node(), node({ id: "capability-1", kind: "capability", tenantId: "tenant-2" })],
    edges: [edge()],
  }), /tenant/i);
});

test("graph validation returns a frozen, effect-authority-free projection", () => {
  const graph = validateGraph({
    version: GRAPH_VERSION,
    nodes: [node(), node({ id: "capability-1", kind: "capability" })],
    edges: [edge()],
  });
  assert.equal(graph.version, GRAPH_VERSION);
  assert.equal(graph.nodes.length, 2);
  assert.equal(graph.edges.length, 1);
  assert.equal(Object.isFrozen(graph), true);
  assert.equal(Object.hasOwn(graph, "authorizeEffect"), false);
  assert.equal(Object.hasOwn(graph, "credentials"), false);
});
