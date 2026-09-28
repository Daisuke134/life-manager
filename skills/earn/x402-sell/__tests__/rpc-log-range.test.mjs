import { test } from "node:test";
import assert from "node:assert/strict";

import { BASE_LOG_CHUNK_SIZE, chunkBlockRanges } from "../lib/rpc-log-range.mjs";

test("splits Base log queries within the current 2,000-block provider limit", () => {
  assert.equal(BASE_LOG_CHUNK_SIZE, 2_000);
  assert.deepEqual(chunkBlockRanges(100, 4_100), [
    [100, 2_099],
    [2_100, 4_099],
    [4_100, 4_100],
  ]);
});

test("rejects invalid block ranges instead of issuing an unsafe RPC query", () => {
  assert.throws(() => chunkBlockRanges(-1, 10), /block range invalid/);
  assert.throws(() => chunkBlockRanges(10, 9), /block range invalid/);
  assert.throws(() => chunkBlockRanges(0, 10, 0), /chunk size invalid/);
});
