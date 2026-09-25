// anicca-agent-economy REQ-201 / PROP-201g (Phase 2a, RED phase) — Tier 0 structural check.
//
// BINDING acceptance criterion (resolves FIND-101): every slot currently `status: "live"` in
// skills/registry.json must carry an explicit `"risk": "safe"` / `"risk": "capital"` field, OR an
// `"alwaysAvailable": true` field, matching behavioral-spec.md REQ-201's classification table exactly.
//
// Historical Phase 2a context: the original live slots lacked these fields. The current fixture is
// intentionally read from the live registry so additions cannot silently bypass the classification gate.
import { test } from "node:test";
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REGISTRY_PATH = path.resolve(__dirname, "../../../skills/registry.json");

// behavioral-spec.md REQ-201's classification table plus the two subsequently-added live utility slots.
const EXPECTED_CLASSIFICATION = {
  "resource-resolver": { alwaysAvailable: true },
  "x-repost": { risk: "safe" },
  "report": { alwaysAvailable: true },
  "cook": { alwaysAvailable: true },
  "self/spawn": { risk: "safe" },
  "self/spawn-child": { risk: "safe" },
  "self/issue-dev": { risk: "safe" },
  "self/coordinate": { risk: "safe" },
  "economy/ubi": { risk: "safe" },
  "economy/lending": { risk: "safe" },
  "x402_sell": { risk: "safe" },
  "earn/taskmarket": { risk: "safe" },
  "yield": { risk: "capital" },
  "earn/sol-trade": { risk: "capital" },
  "earn/polymarket-trade": { risk: "capital" },
};

async function loadRegistry() {
  const raw = await fs.readFile(REGISTRY_PATH, "utf8");
  return JSON.parse(raw);
}

function liveSlotNamesOf(registry) {
  const slots = registry && registry.slots;
  if (!slots || typeof slots !== "object") return [];
  return Object.keys(slots).filter((name) => slots[name] && slots[name].status === "live");
}

test("PROP-201g: every currently-live registry.json slot matches the current classification table (15)", async () => {
  const registry = await loadRegistry();
  const live = liveSlotNamesOf(registry);
  assert.equal(live.length, 15, `expected exactly 15 live slots per the current classification table, found ${live.length}: ${JSON.stringify(live)}`);
});

test("★PROP-201g★ every currently-live registry.json slot carries an explicit risk/alwaysAvailable field matching the classification table", async () => {
  const registry = await loadRegistry();
  const live = liveSlotNamesOf(registry);
  const untagged = [];
  const mismatched = [];

  for (const name of live) {
    const slot = registry.slots[name];
    const expected = EXPECTED_CLASSIFICATION[name];
    const hasRisk = slot.risk === "safe" || slot.risk === "capital";
    const hasAlwaysAvailable = slot.alwaysAvailable === true;
    if (!hasRisk && !hasAlwaysAvailable) {
      untagged.push(name);
      continue;
    }
    if (!expected) continue; // a slot added after this spec was written -- not this test's concern
    if (expected.alwaysAvailable && slot.alwaysAvailable !== true) mismatched.push(`${name}: expected alwaysAvailable=true, got ${JSON.stringify(slot.alwaysAvailable)}`);
    if (expected.risk && slot.risk !== expected.risk) mismatched.push(`${name}: expected risk=${expected.risk}, got ${JSON.stringify(slot.risk)}`);
  }

  assert.deepEqual(untagged, [], `every currently-live slot MUST carry an explicit risk/alwaysAvailable field -- untagged (would fall back to the forward-compat default, which this spec says must not be relied on for TODAY's slots): ${JSON.stringify(untagged)}`);
  assert.deepEqual(mismatched, [], `classification must match behavioral-spec.md's table exactly: ${JSON.stringify(mismatched)}`);
});

test("PROP-201g: every slot named in behavioral-spec.md's classification table is actually present and 'live' in registry.json (table isn't stale)", async () => {
  const registry = await loadRegistry();
  const live = new Set(liveSlotNamesOf(registry));
  const missing = Object.keys(EXPECTED_CLASSIFICATION).filter((name) => !live.has(name));
  assert.deepEqual(missing, [], `classification table names slots not found as 'live' in registry.json: ${JSON.stringify(missing)}`);
});
