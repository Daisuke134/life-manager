"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  createAgentCoreIdentityProvider,
  createAwsAgentCoreIdentityClients,
} = require("./agentcore-identity-provider.js");

function fixture() {
  const rows = new Map();
  const calls = [];
  const store = {
    async put(row) { rows.set(row.identity_ref, { ...row, state: "active" }); },
    async read(tenantId, ref) {
      const row = rows.get(ref);
      return row && row.tenant_id === tenantId && row.state === "active" ? { ...row } : null;
    },
    async revoke(tenantId, ref) {
      const row = rows.get(ref);
      if (!row || row.tenant_id !== tenantId) return false;
      row.state = "revoked";
      return true;
    },
    async revokeAndCloseDependents(input) {
      calls.push(["close", input]);
      const row = rows.get(input.identityRef);
      if (!row || row.tenant_id !== input.tenantId) return { revoked: false, closed: 0 };
      row.state = "revoked";
      return { revoked: true, closed: 2 };
    },
  };
  const provider = createAgentCoreIdentityProvider({
    region: "ap-northeast-1",
    refToken: () => "opaque-token-1",
    store,
    controlClient: {
      async health() { return true; },
      async create(input) { calls.push(["create", input]); return { name: input.name, arn: "arn:identity:1" }; },
      async remove(input) { calls.push(["remove", input]); return true; },
    },
    runtimeClient: {
      async resolve(input) { calls.push(["resolve", input]); return { credential: "resolved-secret" }; },
    },
  });
  return { provider, calls, rows };
}

test("agent-owned authorization returns only an opaque tenant-bound ref", async () => {
  const { provider, calls } = fixture();
  const result = await provider.authorize({
    tenantId: "tenant-1",
    provider: "example-api",
    principalKind: "agent_owned",
    kind: "api_key",
    credential: "raw-api-secret",
  });
  assert.deepEqual(result, {
    identity_ref: "lm-identity:opaque-token-1",
    provider: "example-api",
    kind: "api_key",
    principal_kind: "agent_owned",
  });
  assert.doesNotMatch(JSON.stringify(result), /raw-api-secret|arn:identity/);
  assert.equal(calls[0][0], "create");
});

test("human principal and foreign tenant refs fail before AgentCore calls", async () => {
  const { provider, calls } = fixture();
  await assert.rejects(provider.authorize({
    tenantId: "tenant-1", provider: "x", principalKind: "user_provided",
    kind: "api_key", credential: "secret",
  }), /agent_owned/);
  const allowed = await provider.authorize({
    tenantId: "tenant-1", provider: "x", principalKind: "agent_owned",
    kind: "api_key", credential: "secret",
  });
  const before = calls.length;
  await assert.rejects(provider.resolveRef({
    tenantId: "tenant-2", identityRef: allowed.identity_ref, workloadIdentityToken: "workload-token",
  }), /identity ref unavailable/i);
  assert.equal(calls.length, before);
});

test("migration-on-use verifies read-only before storing the ref and retiring legacy secret", async () => {
  const { provider, calls } = fixture();
  const order = [];
  const output = await provider.migrateOnUse({
    tenantId: "tenant-1",
    provider: "old-api",
    principalKind: "agent_owned",
    kind: "api_key",
    workloadIdentityToken: "workload-token",
  }, {
    async readLegacy() { order.push("read"); return { credential: "old-secret", owner: "tenant-1", location: "cloud" }; },
    async verifyReadOnly(resolved) { order.push(`verify:${resolved.credential}`); return true; },
    async storeRef(ref) { order.push(`store:${ref.identity_ref}`); },
    async retireLegacy() { order.push("retire"); },
  });
  assert.equal(output.migrated, true);
  assert.deepEqual(order, [
    "read",
    "verify:resolved-secret",
    "store:lm-identity:opaque-token-1",
    "retire",
  ]);
  assert.deepEqual(calls.map(([name]) => name), ["create", "resolve"]);
});

test("local, human, foreign, or failed verification credentials are never retired", async () => {
  for (const legacy of [
    { credential: "x", owner: "tenant-1", location: "local" },
    { credential: "x", owner: "tenant-2", location: "cloud" },
  ]) {
    const { provider, calls } = fixture();
    let retired = 0;
    await assert.rejects(provider.migrateOnUse({
      tenantId: "tenant-1", provider: "x", principalKind: "agent_owned", kind: "api_key",
      workloadIdentityToken: "workload-token",
    }, {
      readLegacy: async () => legacy,
      verifyReadOnly: async () => true,
      storeRef: async () => {},
      retireLegacy: async () => { retired += 1; },
    }), /legacy credential/);
    assert.equal(retired, 0);
    assert.equal(calls.length, 0);
  }
  const { provider } = fixture();
  let retired = 0;
  await assert.rejects(provider.migrateOnUse({
    tenantId: "tenant-1", provider: "x", principalKind: "agent_owned", kind: "api_key",
    workloadIdentityToken: "workload-token",
  }, {
    readLegacy: async () => ({ credential: "x", owner: "tenant-1", location: "cloud" }),
    verifyReadOnly: async () => false,
    storeRef: async () => {},
    retireLegacy: async () => { retired += 1; },
  }), /verification/);
  assert.equal(retired, 0);
});

test("revoke removes provider access and closes dependent jobs without asking", async () => {
  const { provider, calls } = fixture();
  const created = await provider.authorize({
    tenantId: "tenant-1", provider: "x", principalKind: "agent_owned",
    kind: "api_key", credential: "secret",
  });
  const result = await provider.revoke({ tenantId: "tenant-1", identityRef: created.identity_ref });
  assert.deepEqual(result, { revoked: true, dependent_jobs_closed: 2 });
  assert.deepEqual(calls.map(([name]) => name), ["create", "remove", "close"]);
  assert.doesNotMatch(JSON.stringify(result), /ask|approve|resume/i);
});

test("AWS adapter maps API key and M2M OAuth to official AgentCore commands", async () => {
  const controlCalls = [];
  const runtimeCalls = [];
  const clients = createAwsAgentCoreIdentityClients({
    region: "ap-northeast-1",
    control: {
      async send(command) {
        controlCalls.push([command.constructor.name, command.input]);
        if (command.constructor.name.startsWith("List")) return { items: [] };
        if (command.constructor.name.startsWith("Create")) {
          return { name: command.input.name, credentialProviderArn: "arn:created" };
        }
        return {};
      },
    },
    runtime: {
      async send(command) {
        runtimeCalls.push([command.constructor.name, command.input]);
        return command.constructor.name.includes("ApiKey")
          ? { apiKey: "api-secret" }
          : { accessToken: "oauth-secret" };
      },
    },
  });
  assert.equal(await clients.controlClient.health(), true);
  await clients.controlClient.create({ name: "api-provider", kind: "api_key", credential: "secret", tags: {} });
  await clients.controlClient.create({
    name: "oauth-provider", kind: "oauth2_m2m",
    credential: { vendor: "CustomOauth2", config: { customOauth2ProviderConfig: {} } }, tags: {},
  });
  assert.deepEqual(await clients.runtimeClient.resolve({
    kind: "api_key", workloadIdentityToken: "workload", credentialProviderName: "api-provider", scopes: [],
  }), { credential: "api-secret" });
  assert.deepEqual(await clients.runtimeClient.resolve({
    kind: "oauth2_m2m", workloadIdentityToken: "workload", credentialProviderName: "oauth-provider", scopes: ["read"],
  }), { credential: "oauth-secret" });
  assert.deepEqual(controlCalls.map(([name]) => name), [
    "ListApiKeyCredentialProvidersCommand",
    "CreateApiKeyCredentialProviderCommand",
    "CreateOauth2CredentialProviderCommand",
  ]);
  assert.deepEqual(runtimeCalls.map(([name]) => name), [
    "GetResourceApiKeyCommand",
    "GetResourceOauth2TokenCommand",
  ]);
  assert.equal(runtimeCalls[1][1].oauth2Flow, "M2M");
});
