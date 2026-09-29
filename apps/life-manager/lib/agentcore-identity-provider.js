"use strict";

const crypto = require("node:crypto");

const ID = /^[a-z0-9][a-z0-9._:-]{0,199}$/i;
const REF = /^lm-identity:[A-Za-z0-9_-]{8,200}$/;
const KINDS = new Set(["api_key", "oauth2_m2m"]);

function id(value, label) {
  const text = String(value || "").trim();
  if (!ID.test(text)) throw new Error(`AgentCore Identity ${label} invalid`);
  return text;
}

function method(value, name) {
  if (!value || typeof value[name] !== "function") {
    throw new Error(`AgentCore Identity ${name} unavailable`);
  }
}

function identityInput(input = {}) {
  const tenantId = id(input.tenantId, "tenant");
  const provider = id(input.provider, "provider");
  if (input.principalKind !== "agent_owned") {
    throw new Error("AgentCore Identity principal must be agent_owned");
  }
  if (!KINDS.has(input.kind)) throw new Error("AgentCore Identity kind invalid");
  return { tenantId, provider, kind: input.kind };
}

function providerName(input) {
  const tenantHash = crypto.createHash("sha256").update(input.tenantId).digest("hex").slice(0, 16);
  return `lm-${tenantHash}-${input.provider}`.slice(0, 100);
}

function createAgentCoreIdentityProvider(options = {}) {
  if (options.region !== "ap-northeast-1") throw new Error("AgentCore Identity region must be Tokyo");
  for (const name of ["put", "read", "revoke", "revokeAndCloseDependents"]) method(options.store, name);
  for (const name of ["health", "create", "remove"]) method(options.controlClient, name);
  method(options.runtimeClient, "resolve");
  if (typeof options.refToken !== "function") throw new Error("AgentCore Identity ref token unavailable");

  const api = {
    async health() {
      const ok = await options.controlClient.health();
      return Object.freeze({ ok: ok === true, mode: "cloud", provider: "agentcore-identity" });
    },

    async authorize(input = {}) {
      const identity = identityInput(input);
      if (identity.kind === "api_key" && (typeof input.credential !== "string" || !input.credential)) {
        throw new Error("AgentCore Identity credential invalid");
      }
      if (identity.kind === "oauth2_m2m"
          && (!input.credential || typeof input.credential !== "object" || Array.isArray(input.credential))) {
        throw new Error("AgentCore Identity credential invalid");
      }
      const name = providerName(identity);
      const created = await options.controlClient.create({
        name,
        kind: identity.kind,
        credential: input.credential,
        tags: { tenant: crypto.createHash("sha256").update(identity.tenantId).digest("hex") },
      });
      if (!created || created.name !== name || typeof created.arn !== "string" || !created.arn) {
        throw new Error("AgentCore Identity create readback mismatch");
      }
      const token = String(options.refToken());
      if (!/^[A-Za-z0-9_-]{8,200}$/.test(token)) throw new Error("AgentCore Identity ref token invalid");
      const identityRef = `lm-identity:${token}`;
      await options.store.put({
        identity_ref: identityRef,
        tenant_id: identity.tenantId,
        provider: identity.provider,
        principal_kind: "agent_owned",
        kind: identity.kind,
        credential_provider_name: name,
        credential_provider_arn: created.arn,
      });
      return Object.freeze({
        identity_ref: identityRef,
        provider: identity.provider,
        kind: identity.kind,
        principal_kind: "agent_owned",
      });
    },

    async resolveRef(input = {}) {
      const tenantId = id(input.tenantId, "tenant");
      const identityRef = String(input.identityRef || "");
      if (!REF.test(identityRef)) throw new Error("AgentCore Identity ref invalid");
      const row = await options.store.read(tenantId, identityRef);
      if (!row || row.tenant_id !== tenantId || row.identity_ref !== identityRef
          || row.principal_kind !== "agent_owned" || !KINDS.has(row.kind)) {
        throw new Error("AgentCore Identity ref unavailable");
      }
      const workloadIdentityToken = String(input.workloadIdentityToken || "");
      if (!workloadIdentityToken) throw new Error("AgentCore Identity workload token invalid");
      return options.runtimeClient.resolve({
        workloadIdentityToken,
        credentialProviderName: row.credential_provider_name,
        kind: row.kind,
        scopes: Array.isArray(input.scopes) ? input.scopes : [],
      });
    },

    async revoke(input = {}) {
      const tenantId = id(input.tenantId, "tenant");
      const identityRef = String(input.identityRef || "");
      if (!REF.test(identityRef)) throw new Error("AgentCore Identity ref invalid");
      const row = await options.store.read(tenantId, identityRef);
      if (!row || row.tenant_id !== tenantId || row.principal_kind !== "agent_owned") {
        throw new Error("AgentCore Identity ref unavailable");
      }
      const removed = await options.controlClient.remove({
        name: row.credential_provider_name,
        kind: row.kind,
      });
      if (removed !== true) throw new Error("AgentCore Identity revoke readback mismatch");
      const closed = await options.store.revokeAndCloseDependents({
        tenantId,
        identityRef,
        terminalStatus: "not_applicable",
        reason: "agent_identity_revoked",
        externalEffect: "none",
      });
      if (!closed || closed.revoked !== true) throw new Error("AgentCore Identity revoke lost ref");
      return Object.freeze({ revoked: true, dependent_jobs_closed: Number(closed.closed) });
    },

    async migrateOnUse(input = {}, migration = {}) {
      const identity = identityInput(input);
      for (const name of ["readLegacy", "verifyReadOnly", "storeRef", "retireLegacy"]) method(migration, name);
      const legacy = await migration.readLegacy();
      if (!legacy || legacy.owner !== identity.tenantId || legacy.location !== "cloud"
          || (typeof legacy.credential !== "string" && typeof legacy.credential !== "object")) {
        throw new Error("legacy credential is not migratable");
      }
      const authorized = await api.authorize({ ...input, credential: legacy.credential });
      try {
        const resolved = await api.resolveRef({
          tenantId: identity.tenantId,
          identityRef: authorized.identity_ref,
          workloadIdentityToken: input.workloadIdentityToken,
          scopes: input.scopes,
        });
        if (await migration.verifyReadOnly(resolved) !== true) {
          throw new Error("AgentCore Identity migration verification failed");
        }
        await migration.storeRef(authorized);
        await migration.retireLegacy();
        return Object.freeze({ migrated: true, ...authorized });
      } catch (error) {
        const row = await options.store.read(identity.tenantId, authorized.identity_ref);
        if (row) {
          await options.controlClient.remove({ name: row.credential_provider_name, kind: row.kind });
          await options.store.revoke(identity.tenantId, authorized.identity_ref);
        }
        throw error;
      }
    },
  };
  return Object.freeze(api);
}

function createAwsAgentCoreIdentityClients(options = {}) {
  const region = String(options.region || "ap-northeast-1");
  if (region !== "ap-northeast-1") throw new Error("AgentCore Identity region must be Tokyo");
  const controlSdk = require("@aws-sdk/client-bedrock-agentcore-control");
  const runtimeSdk = require("@aws-sdk/client-bedrock-agentcore");
  const control = options.control || new controlSdk.BedrockAgentCoreControlClient({ region });
  const runtime = options.runtime || new runtimeSdk.BedrockAgentCoreClient({ region });
  return Object.freeze({
    controlClient: {
      async health() {
        await control.send(new controlSdk.ListApiKeyCredentialProvidersCommand({ maxResults: 1 }));
        return true;
      },
      async create(input) {
        const command = input.kind === "api_key"
          ? new controlSdk.CreateApiKeyCredentialProviderCommand({
            name: input.name, apiKey: input.credential, apiKeySecretSource: "MANAGED", tags: input.tags,
          })
          : new controlSdk.CreateOauth2CredentialProviderCommand({
            name: input.name,
            credentialProviderVendor: input.credential.vendor,
            oauth2ProviderConfigInput: input.credential.config,
            tags: input.tags,
          });
        const output = await control.send(command);
        return { name: output.name, arn: output.credentialProviderArn };
      },
      async remove(input) {
        const command = input.kind === "api_key"
          ? new controlSdk.DeleteApiKeyCredentialProviderCommand({ name: input.name })
          : new controlSdk.DeleteOauth2CredentialProviderCommand({ name: input.name });
        await control.send(command);
        return true;
      },
    },
    runtimeClient: {
      async resolve(input) {
        if (input.kind === "api_key") {
          const output = await runtime.send(new runtimeSdk.GetResourceApiKeyCommand({
            workloadIdentityToken: input.workloadIdentityToken,
            resourceCredentialProviderName: input.credentialProviderName,
          }));
          return { credential: output.apiKey };
        }
        const output = await runtime.send(new runtimeSdk.GetResourceOauth2TokenCommand({
          workloadIdentityToken: input.workloadIdentityToken,
          resourceCredentialProviderName: input.credentialProviderName,
          scopes: input.scopes,
          oauth2Flow: "M2M",
        }));
        if (output.authorizationUrl || !output.accessToken) {
          throw new Error("AgentCore Identity human OAuth flow forbidden");
        }
        return { credential: output.accessToken };
      },
    },
  });
}

module.exports = { createAgentCoreIdentityProvider, createAwsAgentCoreIdentityClients };
