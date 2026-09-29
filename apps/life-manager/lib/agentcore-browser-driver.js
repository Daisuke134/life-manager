"use strict";

const ID = /^[a-z0-9][a-z0-9._:-]{0,199}$/i;
const HASH = /^[a-f0-9]{64}$/;

function id(value, label) {
  const text = String(value || "").trim();
  if (!ID.test(text)) throw new Error(`AgentCore browser ${label} invalid`);
  return text;
}

function method(value, name) {
  if (!value || typeof value[name] !== "function") {
    throw new Error(`AgentCore browser ${name} unavailable`);
  }
}

function agentProfile(value, tenantId, provider) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("AgentCore browser profile unavailable");
  }
  if (value.tenant_id !== tenantId) throw new Error("AgentCore browser profile tenant mismatch");
  if (value.provider !== provider) throw new Error("AgentCore browser profile provider mismatch");
  if (value.principal_type !== "agent_owned") {
    throw new Error("AgentCore browser profile principal must be agent_owned");
  }
  return {
    tenantId,
    provider,
    profileId: id(value.profile_id, "profile"),
  };
}

function verifiedAction(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || value.verified !== true || !HASH.test(String(value.evidence_sha256 || ""))) {
    return null;
  }
  if (!value.result || typeof value.result !== "object" || Array.isArray(value.result)) {
    throw new Error("AgentCore browser action result invalid");
  }
  return value;
}

function createAgentCoreBrowserDriver(options = {}) {
  const provider = id(options.provider, "provider");
  const browserIdentifier = id(options.browserIdentifier, "identifier");
  method(options.profileStore, "read");
  for (const name of ["acquire", "attach", "release"]) method(options.lease, name);
  for (const name of ["startSession", "saveProfile", "stopSession"]) {
    method(options.providerClient, name);
  }
  method(options.reconciliationStore, "record");
  if (typeof options.clientToken !== "function") {
    throw new Error("AgentCore browser client token unavailable");
  }
  const sessionTimeoutSeconds = Number(options.sessionTimeoutSeconds || 900);
  if (!Number.isSafeInteger(sessionTimeoutSeconds)
      || sessionTimeoutSeconds < 60 || sessionTimeoutSeconds > 3_600) {
    throw new Error("AgentCore browser session timeout invalid");
  }

  return Object.freeze({
    async run(input = {}, action) {
      const tenantId = id(input.tenantId, "tenant");
      const jobId = id(input.jobId, "job");
      if (typeof action !== "function") throw new Error("AgentCore browser action unavailable");
      const profile = agentProfile(
        await options.profileStore.read(tenantId, provider),
        tenantId,
        provider,
      );
      const lease = await options.lease.acquire({ tenantId, ownerId: jobId });
      let session;
      try {
        const started = await options.providerClient.startSession({
          browserIdentifier,
          name: `lm-${tenantId}-${jobId}`.slice(0, 100),
          sessionTimeoutSeconds,
          viewPort: { width: 1440, height: 900 },
          profileConfiguration: { profileIdentifier: profile.profileId },
          clientToken: options.clientToken({ tenantId, jobId, phase: "start" }),
        });
        if (!started || started.browserIdentifier !== browserIdentifier
            || !ID.test(String(started.sessionId || ""))
            || !started.streams || !started.streams.automationStream
            || started.streams.automationStream.streamStatus !== "ENABLED"
            || !String(started.streams.automationStream.streamEndpoint || "").startsWith("wss://")) {
          throw new Error("AgentCore browser start response invalid");
        }
        session = await options.lease.attach({ ...lease, sessionId: started.sessionId });
        let actionValue;
        let actionError;
        try {
          actionValue = await action(Object.freeze({
            tenantId,
            jobId,
            sessionId: started.sessionId,
            automationEndpoint: started.streams.automationStream.streamEndpoint,
          }));
          const verified = verifiedAction(actionValue);
          if (verified) {
            const saved = await options.providerClient.saveProfile({
              profileIdentifier: profile.profileId,
              browserIdentifier,
              sessionId: started.sessionId,
              clientToken: options.clientToken({ tenantId, jobId, phase: "save" }),
            });
            if (!saved || saved.profileIdentifier !== profile.profileId
                || saved.browserIdentifier !== browserIdentifier
                || saved.sessionId !== started.sessionId) {
              throw new Error("AgentCore browser profile save readback mismatch");
            }
          }
        } catch (error) {
          actionError = error;
        }

        try {
          const stopped = await options.providerClient.stopSession({
            browserIdentifier,
            sessionId: started.sessionId,
            clientToken: options.clientToken({ tenantId, jobId, phase: "stop" }),
          });
          if (!stopped || stopped.browserIdentifier !== browserIdentifier
              || stopped.sessionId !== started.sessionId) {
            throw new Error("AgentCore browser stop readback mismatch");
          }
        } catch (error) {
          await options.reconciliationStore.record({
            tenant_id: tenantId,
            job_id: jobId,
            provider,
            browser_identifier: browserIdentifier,
            session_id: started.sessionId,
            profile_id: profile.profileId,
            reason: "provider_stop_failed",
          });
          const releaseError = new Error("AgentCore browser provider stop failed");
          releaseError.cause = error;
          throw releaseError;
        }

        const released = await options.lease.release({ ...session, sessionId: started.sessionId });
        if (!released) {
          await options.reconciliationStore.record({
            tenant_id: tenantId,
            job_id: jobId,
            provider,
            browser_identifier: browserIdentifier,
            session_id: started.sessionId,
            profile_id: profile.profileId,
            reason: "lease_release_failed",
          });
          throw new Error("AgentCore browser lease release failed");
        }
        if (actionError) throw actionError;
        const verified = verifiedAction(actionValue);
        if (!verified) throw new Error("AgentCore browser action was not verified");
        return Object.freeze({
          status: "completed",
          tenant_id: tenantId,
          job_id: jobId,
          profile_ref: `lm-resource://browser-profile/${tenantId}/${encodeURIComponent(profile.profileId)}`,
          session_ref: `lm-resource://browser-session/${tenantId}/${encodeURIComponent(started.sessionId)}`,
          evidence_sha256: verified.evidence_sha256,
          result: Object.freeze({ ...verified.result }),
        });
      } catch (error) {
        if (!session) await options.lease.release({ ...lease, sessionId: null });
        throw error;
      }
    },
  });
}

function createAwsAgentCoreBrowserClient(options = {}) {
  const region = String(options.region || "ap-northeast-1").trim();
  if (region !== "ap-northeast-1") throw new Error("AgentCore browser region must be Tokyo");
  const {
    BedrockAgentCoreClient,
    StartBrowserSessionCommand,
    SaveBrowserSessionProfileCommand,
    StopBrowserSessionCommand,
  } = require("@aws-sdk/client-bedrock-agentcore");
  const client = options.client || new BedrockAgentCoreClient({ region });
  if (typeof client.send !== "function") throw new Error("AgentCore browser AWS client unavailable");
  return Object.freeze({
    startSession: (input) => client.send(new StartBrowserSessionCommand(input)),
    saveProfile: (input) => client.send(new SaveBrowserSessionProfileCommand(input)),
    stopSession: (input) => client.send(new StopBrowserSessionCommand(input)),
  });
}

module.exports = {
  createAgentCoreBrowserDriver,
  createAwsAgentCoreBrowserClient,
};
