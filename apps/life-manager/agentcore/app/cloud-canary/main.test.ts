import test from "node:test";
import assert from "node:assert/strict";

import { buildReadOnlyProbe, requestSchema } from "./main.js";

const VALID_REQUEST = Object.freeze({
  tenant_id: "tenant-cl00",
  job_id: "job-cl00",
  release_sha: "a".repeat(40),
  probe: "read_only" as const,
});

test("accepts only a reference-only read-only task capsule", () => {
  assert.deepEqual(requestSchema.parse(VALID_REQUEST), VALID_REQUEST);

  for (const invalid of [
    { ...VALID_REQUEST, tenant_id: "" },
    { ...VALID_REQUEST, job_id: "" },
    { ...VALID_REQUEST, release_sha: "main" },
    { ...VALID_REQUEST, probe: "write" },
    { ...VALID_REQUEST, password: "human-secret" },
  ]) {
    assert.equal(requestSchema.safeParse(invalid).success, false);
  }
});

test("builds a zero-effect probe from AgentCore session and filesystem identity", () => {
  const result = buildReadOnlyProbe(
    VALID_REQUEST,
    { sessionId: "runtime-session-cl00" },
    { hostname: "microvm-cl00", workingDirectory: "/app" },
  );

  assert.deepEqual(result, {
    tenant_id: "tenant-cl00",
    job_id: "job-cl00",
    release_sha: "a".repeat(40),
    probe: "read_only",
    effect: "none",
    runtime_session_id: "runtime-session-cl00",
    isolation: {
      hostname: "microvm-cl00",
      working_directory: "/app",
    },
  });
});

test("rejects a missing AgentCore runtime session identity", () => {
  assert.throws(
    () => buildReadOnlyProbe(
      VALID_REQUEST,
      { sessionId: "" },
      { hostname: "microvm-cl00", workingDirectory: "/app" },
    ),
    /runtime session/i,
  );
});
