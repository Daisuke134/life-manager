'use strict';
const { createHmac, createHash } = require('node:crypto');
const { maritimeArtifactRefsValid } = require('../maritime-manager-runtime.js');
const { verifyMaritimeWakeToken } = require('../maritime-manager-wake.js');
const { validateMaritimeScheduleSnapshot } = require('../maritime-manager-schedules.js');
const UID = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const SHA = /^[0-9a-f]{40}$/;
const OCCURRENCE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
class TransportError extends Error {
  constructor(code, unknownEffect = true) { super(`maritime_manager_transport_${code}`); this.code = this.message.toUpperCase(); this.unknownEffect = unknownEffect; }
}
function valid(value, pattern) {
  if (typeof value !== 'string' || !pattern.test(value)) throw new TransportError('input_invalid', false);
  return value;
}
function createMaritimeManagerTransport({ env = {}, fetchImpl = globalThis.fetch, client, managerStore, getWakeBinding, loadSdk } = {}) {
  const apiKey = env.MARITIME_API_KEY;
  const uidSecret = env.LM_MARITIME_MANAGER_ID_SECRET;
  let sdkPromise;
  function configured() {
    if (typeof apiKey !== 'string' || !/^mk_[A-Za-z0-9_-]+$/.test(apiKey) || typeof uidSecret !== 'string' || uidSecret.length < 32
      || !managerStore || ['read', 'claimProvision', 'bindAgent'].some(key => typeof managerStore[key] !== 'function')) {
      throw new TransportError('unconfigured', false);
    }
  }
  async function safe(operation) {
    try { configured(); return await operation(); }
    catch (error) { if (error instanceof TransportError) throw error; throw new TransportError('provider_unavailable'); }
  }
  async function sdk() {
    if (client) return client;
    if (!sdkPromise) sdkPromise = (async () => {
      const options = { apiKey, maxRetries: 0 };
      if (loadSdk) return loadSdk(options);
      const module = await import('maritime-sdk');
      const Maritime = module.default || module.Maritime;
      return new Maritime(options);
    })();
    return sdkPromise;
  }
  async function request(path, method = 'GET', body, absent = false) {
    const response = await fetchImpl(`https://api.maritime.sh${path}`, { method, redirect: 'error', signal: AbortSignal.timeout(20000),
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    if (absent && response?.status === 404) return [];
    if (response?.ok !== true) throw new TransportError('provider_unavailable');
    return response.json();
  }
  async function enrollment(uid, agentId, releaseSha, active = false) {
    valid(uid, UID);
    const row = await managerStore.read(uid);
    if (!row || row.uid !== uid || !['pending', 'provisioning', 'active', 'paused', 'effect_unknown'].includes(row.status)
      || (agentId !== undefined && row.agent_id !== agentId) || (releaseSha !== undefined && row.release_sha !== releaseSha)) {
      throw new TransportError('binding_invalid');
    }
    if (active && (row.status === 'paused' || row.paused_at)) throw new TransportError('paused', false);
    if (active && row.status !== 'active') throw new TransportError('inactive', false);
    return { ...row };
  }
  async function wakeGuest(uid, agentId, releaseSha, active = false) {
    const maritime = await sdk();
    await enrollment(uid, agentId, releaseSha, active);
    if (typeof maritime.agents.start !== 'function') throw new TransportError('unconfigured', false);
    // Official lifecycle start is idempotent. Exec itself does not auto-wake custom VMs.
    const result = await maritime.agents.start(agentId);
    if (result?.id !== agentId || result.status !== 'active') throw new TransportError('guest_wake_unconfirmed');
  }
  function provisionIdentity(input) {
    const uid = valid(input?.uid, UID); const releaseSha = valid(input.releaseSha, SHA);
    const uploadS3Key = valid(input.uploadS3Key, /^[A-Za-z0-9][A-Za-z0-9_./-]{0,1023}$/);
    const archiveSha256 = valid(input.archiveSha256, /^[0-9a-f]{64}$/);
    const externalId = 'lm-manager-' + createHmac('sha256', uidSecret).update(`agent:v1:${uid}`).digest('hex').slice(0,32);
    return Object.freeze({ uid, releaseSha, uploadS3Key, archiveSha256, externalId });
  }
  async function lookup(identity) {
    const rows = await request(`/api/v1/end-users/${identity.externalId}/agents`, 'GET', undefined, true);
    if (!Array.isArray(rows) || rows.length > 1) throw new TransportError('binding_invalid');
    return rows[0] || null;
  }
  async function recoverAgent(identity, row, candidate) {
    if (!candidate || typeof candidate.id !== 'string' || !ID.test(candidate.id)
      || candidate.externalId !== identity.externalId || candidate.framework !== 'custom'
      || !['active', 'sleeping', 'deploying', 'error', 'stopped'].includes(candidate.status)
      || (row.agent_id && row.agent_id !== candidate.id)) throw new TransportError('binding_invalid');
    if (['active', 'sleeping'].includes(candidate.status)) {
      const maritime = await sdk();
      const official = await maritime.agents.get(candidate.id);
      if (!official || official.id !== candidate.id || official.externalId !== identity.externalId || official.framework !== 'custom'
        || !['active', 'sleeping'].includes(official.status)) throw new TransportError('binding_invalid');
      const variables = await maritime.agents.listEnv(candidate.id);
      if (!Array.isArray(variables)) throw new TransportError('binding_invalid');
      for (const [key, value] of [['LM_RUNTIME_TENANT_ID', identity.uid], ['LM_RELEASE_SHA', identity.releaseSha], ['LM_SOURCE_ARCHIVE_SHA256', identity.archiveSha256]]) {
        const matches = variables.filter(variable => variable.key === key);
        if (matches.length !== 1 || matches[0].value !== value || matches[0].isSecret !== false) throw new TransportError('binding_invalid');
      }
      if (row.status === 'pending') {
        await managerStore.claimProvision(identity.uid);
        row = await enrollment(identity.uid, undefined, identity.releaseSha);
      }
      const bound = await managerStore.bindAgent({ uid: identity.uid, authSubject: row.auth_subject,
        agentId: candidate.id, releaseSha: identity.releaseSha });
      if (!bound || bound.uid !== identity.uid || bound.agent_id !== candidate.id || bound.release_sha !== identity.releaseSha) {
        throw new TransportError('binding_invalid');
      }
      return { agentId: candidate.id, status: official.status };
    }
    return { agentId: candidate.id, status: candidate.status };
  }
  return Object.freeze({
    ensureAgent(input) { return safe(async () => {
      const identity = provisionIdentity(input);
      let row = await enrollment(identity.uid, undefined, identity.releaseSha);
      const existing = await lookup(identity);
      if (existing) return recoverAgent(identity, row, existing);
      if (row.status === 'paused' || row.paused_at) throw new TransportError('paused', false);
      if (row.status !== 'pending' || row.agent_id) throw new TransportError('provision_unconfirmed');
      if (typeof getWakeBinding !== 'function') throw new TransportError('unconfigured', false);
      const wake = await getWakeBinding({ uid: identity.uid, releaseSha: identity.releaseSha });
      let url;
      try { url = new URL(wake?.url); } catch { throw new TransportError('relay_invalid', false); }
      if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash
        || url.pathname !== '/api/internal/maritime/wake' || typeof wake.token !== 'string' || !wake.token || /[\r\n\0]/.test(wake.token)) {
        throw new TransportError('relay_invalid', false);
      }
      const token = wake.token;
      const claimed = await managerStore.claimProvision(identity.uid);
      row = await enrollment(identity.uid, undefined, identity.releaseSha);
      if (row.status === 'paused' || row.paused_at) throw new TransportError('paused', false);
      if (claimed !== true) {
        const raced = await lookup(identity);
        if (!raced) throw new TransportError('provision_unconfirmed');
        return recoverAgent(identity, row, raced);
      }
      if (row.status !== 'provisioning' || row.agent_id) throw new TransportError('binding_invalid');
      const candidate = await request(`/api/v1/end-users/${identity.externalId}/agents`, 'POST', {
        name: identity.externalId, externalId: identity.externalId, framework: 'custom', uploadS3Key: identity.uploadS3Key, healthCheckPath: '/health', hasWebUi: false,
        useMaritimeLlm: true, initialEnvVars: [
          { key: 'LM_RUNTIME_TENANT_ID', value: identity.uid, isSecret: false },
          { key: 'LM_RELEASE_SHA', value: identity.releaseSha, isSecret: false },
          { key: 'LM_SOURCE_ARCHIVE_SHA256', value: identity.archiveSha256, isSecret: false },
          { key: 'LM_WAKE_RELAY_URL', value: url.toString(), isSecret: false },
          { key: 'LM_WAKE_RELAY_TOKEN', value: token, isSecret: true },
        ],
      });
      return recoverAgent(identity, row, candidate);
    }); },
    readAgent(input) { return safe(async () => {
      const identity = provisionIdentity(input);
      const row = await enrollment(identity.uid, undefined, identity.releaseSha);
      const candidate = await lookup(identity);
      if (!candidate) throw new TransportError('provision_unconfirmed');
      return recoverAgent(identity, row, candidate);
    }); },
    configureWake(input) { return safe(async () => {
      const uid = valid(input?.uid, UID); const agentId = valid(input.agentId, ID);
      const releaseSha = valid(input.releaseSha, SHA);
      await enrollment(uid, agentId, releaseSha, true);
      if (typeof getWakeBinding !== 'function') throw new TransportError('unconfigured', false);
      const wake = await getWakeBinding({ uid, agentId, releaseSha });
      const identity = verifyMaritimeWakeToken(wake?.token, uidSecret);
      if (!identity || identity.uid !== uid || identity.agentId !== agentId || identity.releaseSha !== releaseSha) {
        throw new TransportError('relay_invalid', false);
      }
      const maritime = await sdk();
      if (typeof maritime.agents.setEnv !== 'function' || typeof maritime.agents.reloadEnv !== 'function') {
        throw new TransportError('unconfigured', false);
      }
      await enrollment(uid, agentId, releaseSha, true);
      await wakeGuest(uid, agentId, releaseSha, true);
      await maritime.agents.setEnv(agentId, 'LM_WAKE_RELAY_TOKEN', wake.token, { secret: true });
      await enrollment(uid, agentId, releaseSha, true);
      const result = await maritime.agents.reloadEnv(agentId);
      if (result?.id !== agentId || !['active', 'sleeping', 'deploying'].includes(result.status)) {
        throw new TransportError('reload_unconfirmed');
      }
      return { agentId, status: result.status };
    }); },
    dispatchCycle(input) { return safe(async () => {
      const uid = valid(input?.uid, UID); const agentId = valid(input.agentId, ID);
      const occurrenceId = valid(input.occurrenceId, OCCURRENCE); const releaseSha = valid(input.releaseSha, SHA);
      const dateKey = input.dateKey;
      if (typeof dateKey !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(dateKey)
        || !Number.isFinite(Date.parse(dateKey)) || new Date(dateKey).toISOString().slice(0,10) !== dateKey) throw new TransportError('input_invalid', false);
      await enrollment(uid, agentId, releaseSha, true);
      const execution = await request(`/api/agents/${agentId}/exec`, 'POST', {
        command: ['node', '/app/apps/life-manager/maritime/run-cycle.js', '--tenant', uid, '--occurrence', occurrenceId, '--date', dateKey],
        detached: true, timeout: 3720,
      });
      if (typeof execution?.executionId !== 'string' || !ID.test(execution.executionId)) throw new TransportError('execution_unconfirmed');
      return { executionId: execution.executionId };
    }); },
    readExecution(input) { return safe(async () => {
      const uid = valid(input?.uid, UID), agentId = valid(input.agentId, ID), executionId = valid(input.executionId, ID);
      const row = await enrollment(uid, agentId);
      const result = await request(`/api/agents/${agentId}/exec/${executionId}`);
      if (result?.executionId !== executionId || !['running', 'completed', 'timed_out', 'cancelled', 'failed'].includes(result.status)) {
        throw new TransportError('execution_invalid');
      }
      if (result.status === 'running') {
        // Maintain only an already accepted, active tenant execution; never re-POST it.
        if (row.status === 'active' && !row.paused_at) {
          try { await wakeGuest(uid, agentId, undefined, true); }
          catch (error) {
            if (!(error instanceof TransportError) || !['MARITIME_MANAGER_TRANSPORT_PAUSED', 'MARITIME_MANAGER_TRANSPORT_INACTIVE'].includes(error.code)) throw error;
          }
        }
        return { status: result.status };
      }
      if (!Number.isInteger(result.exitCode) || typeof result.stdout !== 'string') throw new TransportError('execution_invalid');
      return { status: result.status, exitCode: result.exitCode, stdout: result.stdout };
    }); },
    cancelExecution(input) { return safe(async () => {
      const uid = valid(input?.uid, UID), agentId = valid(input.agentId, ID), executionId = valid(input.executionId, ID);
      const row = await enrollment(uid, agentId);
      if (row.status !== 'paused' || !row.paused_at) throw new TransportError('cancel_requires_pause', false);
      const result = await request(`/api/agents/${agentId}/exec/${executionId}`, 'DELETE');
      if (result?.executionId !== executionId || !['completed', 'timed_out', 'cancelled', 'failed'].includes(result.status)
        || !Number.isInteger(result.exitCode)) throw new TransportError('execution_cancel_unconfirmed');
      return { executionId, status: result.status, exitCode: result.exitCode };
    }); },
    readCycleReceipt(input) { return safe(async () => {
      const uid = valid(input?.uid, UID); const agentId = valid(input.agentId, ID); const occurrence = valid(input.occurrenceId, OCCURRENCE);
      await enrollment(uid, agentId);
      await wakeGuest(uid, agentId);
      const bytes = await (await sdk()).agents.files.download(agentId, `/data/${uid}/receipts/${occurrence}/cycle.json`);
      if (!(bytes instanceof Uint8Array) || bytes.byteLength > 262144) throw new TransportError('receipt_invalid');
      const envelope = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
      if (envelope?.result?.tenantId !== uid || envelope.result.occurrenceId !== occurrence) throw new TransportError('binding_invalid');
      return envelope;
    }); },
    readArtifact(input) { return safe(async () => {
      const uid = valid(input?.uid, UID); const agentId = valid(input.agentId, ID);
      const artifactRef = input.artifactRef; const maxBytes = 20 * 1024 * 1024;
      if (!maritimeArtifactRefsValid([artifactRef], true)) throw new TransportError('artifact_invalid', false);
      await enrollment(uid, agentId);
      await wakeGuest(uid, agentId);
      const execution = await request(`/api/agents/${agentId}/exec`, 'POST', {
        command: ['python3', '/app/apps/life-manager/maritime/artifact-proof.py', '--tenant', uid, '--artifact', artifactRef],
        detached: false, timeout: 20,
      });
      if (execution?.status !== 'completed' || execution.exitCode !== 0 || typeof execution.stdout !== 'string'
        || execution.stdout.length > 262144) throw new TransportError('artifact_proof_unavailable', false);
      let proof;
      try { proof = JSON.parse(execution.stdout); } catch { throw new TransportError('artifact_proof_invalid', false); }
      if (proof?.tenantId !== uid || proof.artifactRef !== artifactRef || !Number.isSafeInteger(proof.size)
        || proof.size < 0 || proof.size > maxBytes || !/^[0-9a-f]{64}$/.test(proof.sha256 || '')) {
        throw new TransportError('artifact_proof_invalid', false);
      }
      const path = `/data/${uid}/build/${artifactRef.slice('artifact://'.length)}`;
      const response = await fetchImpl(`https://api.maritime.sh/api/agents/${agentId}/files/download?path=${encodeURIComponent(path)}`, {
        method: 'GET', redirect: 'error', signal: AbortSignal.timeout(20000), headers: { Authorization: `Bearer ${apiKey}` },
      });
      const reader = response?.body?.getReader();
      if (!reader) throw new TransportError('artifact_unavailable', false);
      let ended = false;
      try {
        if (!response.ok || Number(response.headers?.get('content-length')) > maxBytes) throw new TransportError('artifact_unavailable', false);
        const chunks = []; let total = 0; const digest = createHash('sha256');
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) { ended = true; break; }
          total += chunk.value.byteLength;
          if (total > maxBytes || total > proof.size) throw new TransportError('artifact_changed', false);
          digest.update(chunk.value); chunks.push(chunk.value);
        }
        if (total !== proof.size || digest.digest('hex') !== proof.sha256) throw new TransportError('artifact_changed', false);
        return Buffer.concat(chunks, total);
      } finally { if (!ended) { try { await reader.cancel(); } catch {} } }
    }); },
    readWakeConfiguration(input) { return safe(async () => {
      const uid = valid(input?.uid, UID), agentId = valid(input.agentId, ID), releaseSha = valid(input.releaseSha, SHA);
      const activeOnly = input.activeOnly === true;
      await enrollment(uid, agentId, releaseSha, activeOnly);
      if (typeof getWakeBinding !== 'function') throw new TransportError('unconfigured', false);
      const wake = await getWakeBinding({ uid, agentId, releaseSha });
      const identity = verifyMaritimeWakeToken(wake?.token, uidSecret);
      if (!identity || identity.uid !== uid || identity.agentId !== agentId || identity.releaseSha !== releaseSha) throw new TransportError('relay_invalid', false);
      await wakeGuest(uid, agentId, releaseSha, activeOnly);
      const execution = await (await sdk()).agents.exec(agentId,
        'node /app/apps/life-manager/maritime/runtime-status.js', { detached: false, timeout: 10 });
      if (execution?.status !== 'completed' || execution.exitCode !== 0 || typeof execution.stdout !== 'string'
        || Buffer.byteLength(execution.stdout) > 65536) throw new TransportError('runtime_readback_unavailable');
      let result;
      try { result = JSON.parse(execution.stdout); } catch { throw new TransportError('runtime_readback_invalid'); }
      if (result?.health?.ok !== true || result.health.releaseSha !== releaseSha
        || result.health.relayBindingHash !== createHash('sha256').update(wake.token).digest('hex')) return { ready: false };
      try { validateMaritimeScheduleSnapshot({ schema_version: 1, tenantId: uid, releaseSha, paused: false, schedules: result.schedules }, uid, releaseSha); }
      catch { return { ready: false }; }
      return { ready: true, schedules: result.schedules };
    }); },
    writeScheduleSnapshot(input) { return safe(async () => {
      const uid = valid(input?.uid, UID); const agentId = valid(input.agentId, ID);
      const snapshot = structuredClone(input.snapshot);
      const row = await enrollment(uid, agentId);
      try {
        validateMaritimeScheduleSnapshot(snapshot, uid, row.release_sha);
        const paused = row.status === 'paused' || Boolean(row.paused_at);
        if (snapshot.paused !== paused || (paused ? snapshot.schedules.length !== 0
          : row.status !== 'active' || !snapshot.schedules.some(entry => entry.id === `lm-report:${uid}`))) throw new Error();
      } catch { throw new TransportError('schedule_invalid', false); }
      await wakeGuest(uid, agentId);
      await (await sdk()).agents.files.write(agentId, `/data/${uid}/maritime-schedules.json`, JSON.stringify(snapshot));
      return { ok: true };
    }); },
  });
}
module.exports = { createMaritimeManagerTransport };
