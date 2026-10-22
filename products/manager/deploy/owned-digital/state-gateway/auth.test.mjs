import assert from "node:assert/strict";
import { before, test } from "node:test";
import { generateKeyPair, SignJWT } from "jose";
import { createHash } from "node:crypto";
import { createHandler } from "./index.ts";
import { verifyGithubToken } from "./auth.mjs";

const audience = "https://ulhsqqkyejzvqgoyjwte.supabase.co/functions/v1/manager-owned-state";
const issuer = "https://token.actions.githubusercontent.com";
const sha = "a".repeat(40);
let keys;
before(async () => { keys = await generateKeyPair("RS256"); });

async function signed(overrides = {}, { algorithm = "RS256", signingKey } = {}) {
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iss: issuer, aud: audience, sub: "repo:Daisuke134/life-manager:ref:refs/heads/main",
    exp: now + 300, iat: now, nbf: now - 1, jti: "unit-oidc-token",
    repository: "Daisuke134/life-manager", repository_id: "1248111245",
    repository_owner_id: "140220114", ref: "refs/heads/main", ref_type: "branch",
    workflow_ref: "Daisuke134/life-manager/.github/workflows/manager-phase06-service.yml@refs/heads/main",
    event_name: "workflow_dispatch", runner_environment: "github-hosted",
    sha, workflow_sha: sha, run_id: "123456", run_attempt: "1", ...overrides,
  };
  for (const key of Object.keys(payload)) if (payload[key] === undefined) delete payload[key];
  return new SignJWT(payload).setProtectedHeader({ alg: algorithm, kid: "test-key" })
    .sign(signingKey ?? keys.privateKey);
}

test("signed trusted main workflow yields only verified run identity", async () => {
  assert.deepEqual(await verifyGithubToken(await signed(), keys.publicKey), {
    runId: "123456", runAttempt: "1", sourceSha: sha,
  });
});

test("schedule is an allowed wake event", async () => {
  const result = await verifyGithubToken(await signed({ event_name: "schedule" }), keys.publicKey);
  assert.equal(result.runId, "123456");
});

test("different RSA signer cannot authorize a run", async () => {
  const other = await generateKeyPair("RS256");
  await assert.rejects(verifyGithubToken(await signed({}, { signingKey: other.privateKey }), keys.publicKey));
});

for (const [name, changes] of [
  ["issuer", { iss: "https://attacker.invalid" }],
  ["audience", { aud: "other-state-gateway" }],
  ["repository", { repository: "attacker/life-manager" }],
  ["immutable repository id", { repository_id: "1248111246" }],
  ["immutable owner id", { repository_owner_id: "140220115" }],
  ["research ref", { ref: "refs/heads/research/test" }],
  ["tag ref type", { ref_type: "tag" }],
  ["other workflow", { workflow_ref: "Daisuke134/life-manager/.github/workflows/other.yml@refs/heads/main" }],
  ["pull request event", { event_name: "pull_request" }],
  ["pull request target event", { event_name: "pull_request_target" }],
  ["self hosted runner", { runner_environment: "self-hosted" }],
  ["short source sha", { sha: "abcd" }],
  ["mismatched workflow sha", { workflow_sha: "b".repeat(40) }],
  ["missing source sha", { sha: undefined }],
  ["nonstring run id", { run_id: 123456 }],
  ["nonpositive run attempt", { run_attempt: "0" }],
  ["missing subject", { sub: undefined }],
  ["missing token id", { jti: undefined }],
  ["missing expiry", { exp: undefined }],
  ["missing issued at", { iat: undefined }],
  ["missing not-before", { nbf: undefined }],
  ["expired token", { exp: Math.floor(Date.now() / 1000) - 60 }],
  ["not yet valid", { nbf: Math.floor(Date.now() / 1000) + 60 }],
  ["stale issued at", { iat: Math.floor(Date.now() / 1000) - 600 }],
]) {
  test(`rejects ${name}`, async () => {
    await assert.rejects(verifyGithubToken(await signed(changes), keys.publicKey));
  });
}

test("HS256 cannot switch the configured RSA trust algorithm", async () => {
  const token = await signed({}, { algorithm: "HS256", signingKey: new Uint8Array(32).fill(7) });
  await assert.rejects(verifyGithubToken(token, keys.publicKey));
});

const nonce = "e83be31d-a863-43b3-802b-40be9edee813";
const snapshot = Buffer.from("SQLite format 3\0unit checkpoint").toString("base64");
const snapshotSha = createHash("sha256").update(Buffer.from(snapshot, "base64")).digest("hex");
const state = { revision: 3, sha256: snapshotSha, snapshot, owner: `123456:1:${nonce}` };
function gateway(fetch) {
  return createHandler({
    verifyToken: token => verifyGithubToken(token, keys.publicKey),
    readEnv: name => ({ SUPABASE_URL: "https://ulhsqqkyejzvqgoyjwte.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "private-database-credential" })[name],
    fetch,
  });
}
async function request(body, { token, method = "POST", type = "application/json" } = {}) {
  return new Request(audience, { method, headers: {
    authorization: `Bearer ${token ?? await signed()}`, "content-type": type,
  }, body: method === "POST" ? JSON.stringify(body) : undefined });
}

test("authenticated acquire binds database owner to verified run and UUID nonce", async () => {
  let calls = 0;
  const handler = gateway(async (url, options) => {
    calls++;
    assert.equal(url, "https://ulhsqqkyejzvqgoyjwte.supabase.co/rest/v1/rpc/lm_manager_owned_checkpoint");
    assert.equal(options.redirect, "error");
    assert.equal(options.headers.Authorization, "Bearer private-database-credential");
    assert.deepEqual(JSON.parse(options.body), {
      p_operation: "acquire", p_owner: state.owner, p_revision: null, p_sha256: null, p_snapshot: null,
    });
    return Response.json(state);
  });
  const response = await handler(await request({ operation: "acquire", nonce }));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), state);
  assert.equal(calls, 1);
});

test("checkpoint forwards only validated CAS fields", async () => {
  const handler = gateway(async (_url, options) => {
    assert.deepEqual(JSON.parse(options.body), {
      p_operation: "checkpoint", p_owner: state.owner,
      p_revision: 2, p_sha256: snapshotSha, p_snapshot: snapshot,
    });
    return Response.json(state);
  });
  assert.equal((await handler(await request({ operation: "checkpoint", nonce,
    revision: 2, sha256: snapshotSha, snapshot }))).status, 200);
});

test("release returns the retained snapshot with null owner", async () => {
  const response = await gateway(async () => Response.json({ ...state, owner: null }))(
    await request({ operation: "release", nonce }),
  );
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ...state, owner: null });
});

for (const [name, body] of [
  ["unknown operation", { operation: "initialize", nonce }],
  ["owner override", { operation: "acquire", nonce, owner: "other-owner" }],
  ["CAS fields on acquire", { operation: "acquire", nonce, revision: 2 }],
  ["missing nonce", { operation: "acquire" }],
  ["not UUIDv4", { operation: "acquire", nonce: "arbitrary" }],
  ["missing checkpoint revision", { operation: "checkpoint", nonce, sha256: snapshotSha, snapshot }],
  ["negative revision", { operation: "checkpoint", nonce, revision: -1, sha256: snapshotSha, snapshot }],
  ["unsafe integer", { operation: "checkpoint", nonce, revision: 2 ** 53, sha256: snapshotSha, snapshot }],
  ["invalid digest", { operation: "checkpoint", nonce, revision: 2, sha256: "aa", snapshot }],
  ["noncanonical base64", { operation: "checkpoint", nonce, revision: 2, sha256: snapshotSha, snapshot: `${snapshot}\n` }],
  ["oversized raw snapshot", { operation: "checkpoint", nonce, revision: 2, sha256: snapshotSha, snapshot: Buffer.alloc(1048577).toString("base64") }],
  ["null body", null],
  ["array body", []],
]) {
  test(`HTTP rejects ${name} before database access`, async () => {
    let accessed = false;
    const response = await gateway(async () => { accessed = true; return Response.json(state); })(await request(body));
    assert.equal(response.status, 400);
    assert.equal(accessed, false);
  });
}

test("unauthenticated request never reads project credential or reaches database", async () => {
  let accessed = false;
  const handler = createHandler({
    verifyToken: token => verifyGithubToken(token, keys.publicKey),
    readEnv: () => { accessed = true; return "secret"; },
    fetch: async () => { accessed = true; return Response.json(state); },
  });
  const response = await handler(await request({ operation: "acquire", nonce }, { token: await signed({ ref: "refs/heads/fork" }) }));
  assert.equal(response.status, 401);
  assert.equal(accessed, false);
  assert.doesNotMatch(await response.text(), /secret|private-database|repository/);
});

test("request body is bounded even without content-length", async () => {
  let accessed = false;
  const response = await gateway(async () => { accessed = true; return Response.json(state); })(
    await request({ operation: "acquire", nonce, extra: "x".repeat(2097152) }),
  );
  assert.equal(response.status, 413);
  assert.equal(accessed, false);
});

test("non-JSON media type is rejected", async () => {
  assert.equal((await gateway(async () => Response.json(state))(
    await request({ operation: "acquire", nonce }, { type: "text/plain" }),
  )).status, 415);
});

test("GET has no state read endpoint", async () => {
  assert.equal((await gateway(async () => Response.json(state))(
    await request(null, { method: "GET" }),
  )).status, 405);
});

test("wrong project URL cannot redirect service credentials", async () => {
  let accessed = false;
  const handler = createHandler({ verifyToken: token => verifyGithubToken(token, keys.publicKey),
    readEnv: name => name === "SUPABASE_URL" ? "https://wrong-project.supabase.co" : "private-key",
    fetch: async () => { accessed = true; return Response.json(state); } });
  const response = await handler(await request({ operation: "acquire", nonce }));
  assert.equal(response.status, 503);
  assert.equal(accessed, false);
});

for (const [name, upstream, status] of [
  ["missing stream", () => Response.json({ message: "private SQL details" }, { status: 404 }), 404],
  ["CAS conflict", () => Response.json({ message: "private SQL details" }, { status: 409 }), 409],
  ["database failure", () => Response.json({ message: "private SQL details" }, { status: 500 }), 503],
  ["lost response", () => { throw new Error("private credential detail"); }, 503],
  ["malformed response", () => Response.json({ ...state, extra: "private SQL details" }), 503],
  ["owner mismatch", () => Response.json({ ...state, owner: "other-run" }), 503],
  ["digest mismatch", () => Response.json({ ...state, sha256: "b".repeat(64) }), 503],
]) {
  test(`HTTP ${name} fails closed without private error details`, async () => {
    const response = await gateway(async () => upstream())(await request({ operation: "acquire", nonce }));
    assert.equal(response.status, status);
    assert.doesNotMatch(await response.text(), /private|SQL|credential|detail/);
  });
}
