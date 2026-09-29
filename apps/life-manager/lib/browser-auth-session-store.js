"use strict";

const { createCipheriv, createDecipheriv, createHash, randomBytes } = require("node:crypto");
const { isIP } = require("node:net");
const canonicalize = require("canonicalize");
const { parse: parseDomain } = require("tldts");

const MAX_CONTEXT_BYTES = 1024 * 1024;
const AUTH_CONTEXT_KEYS = new Set(["cookies", "localStorage", "sessionStorage", "indexedDB"]);
const PRINCIPAL_KINDS = new Set(["agent_owned", "user_provided"]);
const BROWSER_AUTH_CONTEXT_EXPIRED_CODE = "BROWSER_AUTH_CONTEXT_EXPIRED";
let defaultPool;

function invalid() {
  throw new Error("browser auth context invalid");
}

function nonEmptyString(value, max = 1000) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text || text.length > max) invalid();
  return text;
}

function normalizeAuthOrigin(value) {
  if (typeof value !== "string") throw new Error("browser auth origin invalid");
  let parsed;
  try { parsed = new URL(value); } catch { throw new Error("browser auth origin invalid"); }
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.origin === "null"
    || parsed.hostname.endsWith(".")) {
    throw new Error("browser auth origin invalid");
  }
  return parsed.origin;
}

function validateJson(value, depth = 0) {
  if (depth > 64 || value === undefined || typeof value === "function" || typeof value === "symbol" || typeof value === "bigint") invalid();
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) invalid();
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) validateJson(item, depth + 1);
    return;
  }
  if (typeof value !== "object" || (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)) invalid();
  for (const [key, item] of Object.entries(value)) {
    if (!key || key.length > 1000) invalid();
    validateJson(item, depth + 1);
  }
}

function canonicalContext(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null) invalid();
  const keys = Object.keys(value);
  if (keys.some((key) => !AUTH_CONTEXT_KEYS.has(key))) invalid();
  validateJson(value);
  const canonical = canonicalize(value);
  if (typeof canonical !== "string" || Buffer.byteLength(canonical, "utf8") > MAX_CONTEXT_BYTES) invalid();
  return canonical;
}

function validateSessionContext(value) {
  const canonical = canonicalContext(value);
  return JSON.parse(canonical);
}

function cookieDomain(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase().replace(/^\.+/, "");
  if (!normalized || normalized.endsWith(".") || /[:/@?#]/.test(normalized)) return null;
  try {
    const parsed = new URL(`https://${normalized}`);
    return parsed.hostname.toLowerCase();
  } catch {
    return null;
  }
}

function safePublicHostname(hostname) {
  const ipCandidate = hostname.startsWith("[") && hostname.endsWith("]")
    ? hostname.slice(1, -1)
    : hostname;
  if (isIP(ipCandidate)) return false;
  const parsed = parseDomain(hostname, {
    allowPrivateDomains: true,
    detectIp: true,
    detectSpecialUse: true,
  });
  const publicRegistrable = parsed.isIcann === true && parsed.isPrivate !== true;
  const privateRegistrableChild = parsed.isPrivate === true
    && parsed.domain === hostname
    && parsed.publicSuffix !== hostname;
  return Boolean(
    parsed.domain
    && parsed.isIp !== true
    && parsed.isSpecialUse !== true
    && parsed.publicSuffix !== hostname
    && (publicRegistrable || privateRegistrableChild)
  );
}

function cookieAppliesToHostname(cookie, hostname) {
  if (!cookie || typeof cookie !== "object" || Array.isArray(cookie)) return false;
  if (Object.prototype.hasOwnProperty.call(cookie, "partitionKey")) return false;
  const domain = cookieDomain(cookie.domain);
  if (!domain || !safePublicHostname(hostname) || !safePublicHostname(domain)) return false;
  if (domain === hostname) return true;
  if (cookie.hostOnly !== false || !hostname.endsWith(`.${domain}`)) return false;
  const target = parseDomain(hostname, {
    allowPrivateDomains: true,
    detectIp: true,
    detectSpecialUse: true,
  });
  const candidate = parseDomain(domain, {
    allowPrivateDomains: true,
    detectIp: true,
    detectSpecialUse: true,
  });
  return Boolean(
    candidate.domain
    && target.domain
    && candidate.domain === target.domain
    && candidate.publicSuffix !== domain
    && candidate.isIp !== true
    && candidate.isPrivate !== true
    && candidate.isSpecialUse !== true
  );
}

function cookieIsExpired(cookie, nowMs = Date.now()) {
  return typeof cookie.expires === "number"
    && Number.isFinite(cookie.expires)
    && cookie.expires > 0
    && cookie.expires * 1000 <= nowMs;
}

function expired() {
  const error = new Error("browser auth context expired");
  error.code = BROWSER_AUTH_CONTEXT_EXPIRED_CODE;
  throw error;
}

function scopeStorage(storage, origin) {
  if (!storage || typeof storage !== "object" || Array.isArray(storage)
    || Object.getPrototypeOf(storage) !== Object.prototype && Object.getPrototypeOf(storage) !== null) {
    invalid();
  }
  return Object.prototype.hasOwnProperty.call(storage, origin)
    ? { [origin]: storage[origin] }
    : {};
}

function scopeSessionContextToOrigin(value, originValue) {
  const origin = normalizeAuthOrigin(originValue);
  const hostname = new URL(origin).hostname;
  if (!safePublicHostname(hostname)) invalid();
  const context = validateSessionContext(value);
  const scoped = {};
  let applicableCookies = [];
  if (Object.prototype.hasOwnProperty.call(context, "cookies")) {
    if (!Array.isArray(context.cookies)) invalid();
    applicableCookies = context.cookies.filter((cookie) => cookieAppliesToHostname(cookie, hostname));
    scoped.cookies = applicableCookies.filter((cookie) => !cookieIsExpired(cookie));
  }
  for (const key of ["localStorage", "sessionStorage", "indexedDB"]) {
    if (Object.prototype.hasOwnProperty.call(context, key)) {
      scoped[key] = scopeStorage(context[key], origin);
    }
  }
  const hasData = Object.entries(scoped).some(([key, item]) => (
    key === "cookies" ? item.length > 0 : Array.isArray(item) ? item.length > 0 : Object.keys(item).length > 0
  ));
  if (!hasData) {
    if (applicableCookies.length > 0 && applicableCookies.every((cookie) => cookieIsExpired(cookie))) {
      expired();
    }
    invalid();
  }
  return validateSessionContext(scoped);
}

function principalKind(value) {
  if (!PRINCIPAL_KINDS.has(value)) invalid();
  return value;
}

function authIdentity(input) {
  const uid = nonEmptyString(input && input.uid, 200);
  const origin = normalizeAuthOrigin(input && input.origin);
  const kind = principalKind(input && (input.principalKind === undefined ? input.principal_kind : input.principalKind));
  return { uid, origin, principalKind: kind };
}

function encryptionKey(keyHex) {
  if (typeof keyHex !== "string" || !/^[a-fA-F0-9]{64}$/.test(keyHex)) invalid();
  const key = Buffer.from(keyHex, "hex");
  if (key.length !== 32) invalid();
  return key;
}

function aad({ uid, origin, principalKind }) {
  return Buffer.from(`${uid}\n${origin}\n${principalKind}\n1`, "utf8");
}

function sealBrowserContext(input, keyHex) {
  const identity = authIdentity(input);
  const context = scopeSessionContextToOrigin(input && input.context, identity.origin);
  const plaintext = canonicalContext(context);
  const key = encryptionKey(keyHex);
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  cipher.setAAD(aad(identity));
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  return {
    ciphertext: ciphertext.toString("base64url"),
    iv: iv.toString("base64url"),
    auth_tag: cipher.getAuthTag().toString("base64url"),
    context_sha256: createHash("sha256").update(plaintext, "utf8").digest("hex"),
    key_version: 1,
  };
}

function fromBase64url(value) {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]+$/.test(value)) invalid();
  return Buffer.from(value, "base64url");
}

function openBrowserContext(row, keyHex) {
  try {
    const identity = authIdentity(row);
    if (!row || row.key_version !== 1 || !/^[a-f0-9]{64}$/.test(String(row.context_sha256 || ""))) invalid();
    const key = encryptionKey(keyHex);
    const iv = fromBase64url(row.iv);
    const tag = fromBase64url(row.auth_tag);
    if (iv.length !== 12 || tag.length !== 16) invalid();
    const decipher = createDecipheriv("aes-256-gcm", key, iv);
    decipher.setAAD(aad(identity));
    decipher.setAuthTag(tag);
    const plaintext = Buffer.concat([decipher.update(fromBase64url(row.ciphertext)), decipher.final()]).toString("utf8");
    if (createHash("sha256").update(plaintext, "utf8").digest("hex") !== row.context_sha256) invalid();
    const context = JSON.parse(plaintext);
    if (canonicalContext(context) !== plaintext) invalid();
    return scopeSessionContextToOrigin(context, identity.origin);
  } catch (error) {
    if (error && error.code === BROWSER_AUTH_CONTEXT_EXPIRED_CODE) throw error;
    invalid();
  }
}

function database(opts = {}) {
  if (typeof opts.query === "function") return { query: opts.query };
  const connectionString = String(opts.connectionString || process.env.LM_FEEDBACK_DATABASE_URL || "").trim();
  if (!connectionString) throw new Error("browser auth session store unavailable");
  if (!defaultPool) {
    const Pool = opts.Pool || require("pg").Pool;
    defaultPool = new Pool({ connectionString, max: 4 });
  }
  return { query: defaultPool.query.bind(defaultPool) };
}

function sessionKey(input, opts) {
  return input && input.keyHex || opts && opts.keyHex || process.env.LM_BROWSER_SESSION_KEY;
}

function optionalTimestamp(value) {
  if (value == null) return null;
  if (typeof value !== "string" || value.length > 100) invalid();
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) invalid();
  return timestamp.toISOString();
}

function authRecord(row, identity, context) {
  if (!row || typeof row !== "object" || row.uid !== identity.uid
    || row.origin !== identity.origin || row.principal_kind !== identity.principalKind
    || !/^[a-f0-9]{64}$/.test(String(row.context_sha256 || ""))
    || row.key_version !== 1) {
    throw new Error("browser auth session row invalid");
  }
  return Object.freeze({
    uid: identity.uid,
    origin: identity.origin,
    principal_kind: identity.principalKind,
    state: row.state,
    expires_at: row.expires_at || null,
    last_verified_at: row.last_verified_at || null,
    created_at: row.created_at || null,
    updated_at: row.updated_at || null,
    context_sha256: row.context_sha256,
    key_version: row.key_version,
    context,
  });
}

async function readBrowserAuthSession(input, opts = {}) {
  const identity = authIdentity(input);
  const { query } = database(opts);
  const rows = (await query(`
    SELECT * FROM public.lm_browser_auth_sessions
    WHERE uid = $1 AND origin = $2 AND principal_kind = $3
      AND state = 'active'
      AND (expires_at IS NULL OR expires_at > clock_timestamp())
    LIMIT 1
  `, [identity.uid, identity.origin, identity.principalKind])).rows;
  if (rows.length === 0) return null;
  if (rows.length !== 1) throw new Error("browser auth session read returned multiple rows");
  return authRecord(rows[0], identity, openBrowserContext(rows[0], sessionKey(input, opts)));
}

async function upsertBrowserAuthSession(input, opts = {}) {
  const identity = authIdentity(input);
  const context = scopeSessionContextToOrigin(input && input.context, identity.origin);
  const sealed = sealBrowserContext({ ...identity, context }, sessionKey(input, opts));
  const expiresAt = optionalTimestamp(input && input.expiresAt);
  const lastVerifiedAt = optionalTimestamp(input && input.lastVerifiedAt);
  const { query } = database(opts);
  const rows = (await query(`
    INSERT INTO public.lm_browser_auth_sessions (
      uid, origin, principal_kind, ciphertext, iv, auth_tag, context_sha256,
      key_version, state, expires_at, last_verified_at
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'active',$9,$10)
    ON CONFLICT (uid, origin, principal_kind) DO UPDATE
    SET ciphertext = EXCLUDED.ciphertext,
        iv = EXCLUDED.iv,
        auth_tag = EXCLUDED.auth_tag,
        context_sha256 = EXCLUDED.context_sha256,
        key_version = EXCLUDED.key_version,
        state = 'active',
        expires_at = EXCLUDED.expires_at,
        last_verified_at = EXCLUDED.last_verified_at,
        updated_at = clock_timestamp()
    RETURNING *
  `, [
    identity.uid,
    identity.origin,
    identity.principalKind,
    sealed.ciphertext,
    sealed.iv,
    sealed.auth_tag,
    sealed.context_sha256,
    sealed.key_version,
    expiresAt,
    lastVerifiedAt,
  ])).rows;
  if (rows.length !== 1) throw new Error("browser auth session upsert lost row");
  return authRecord(rows[0], identity, context);
}

async function invalidateBrowserAuthSession(input, opts = {}) {
  const identity = authIdentity(input);
  const { query } = database(opts);
  const rows = (await query(`
    UPDATE public.lm_browser_auth_sessions
    SET state = 'invalidated', updated_at = clock_timestamp()
    WHERE uid = $1 AND origin = $2 AND principal_kind = $3 AND state = 'active'
    RETURNING uid
  `, [identity.uid, identity.origin, identity.principalKind])).rows;
  if (rows.length > 1) throw new Error("browser auth session invalidation returned multiple rows");
  return rows.length === 1;
}

function createAgentIdentityRefStore(opts = {}) {
  const { query } = database(opts);
  return Object.freeze({
    async put(row) {
      if (!row || row.principal_kind !== "agent_owned") invalid();
      const rows = (await query(`
        INSERT INTO public.lm_agent_identity_refs (
          identity_ref, tenant_id, provider, principal_kind, kind,
          credential_provider_name, credential_provider_arn, state
        ) VALUES ($1,$2,$3,'agent_owned',$4,$5,$6,'active')
        ON CONFLICT (tenant_id, provider, kind) DO UPDATE
        SET identity_ref = EXCLUDED.identity_ref,
            credential_provider_name = EXCLUDED.credential_provider_name,
            credential_provider_arn = EXCLUDED.credential_provider_arn,
            state = 'active', revoked_at = NULL
        RETURNING identity_ref
      `, [
        row.identity_ref, row.tenant_id, row.provider, row.kind,
        row.credential_provider_name, row.credential_provider_arn,
      ])).rows;
      if (rows.length !== 1) throw new Error("agent identity ref put lost row");
    },
    async read(tenantId, identityRef) {
      const rows = (await query(`
        SELECT identity_ref, tenant_id, provider, principal_kind, kind,
               credential_provider_name, credential_provider_arn, state
        FROM public.lm_agent_identity_refs
        WHERE tenant_id = $1 AND identity_ref = $2 AND state = 'active'
        LIMIT 1
      `, [tenantId, identityRef])).rows;
      if (rows.length > 1) throw new Error("agent identity ref read returned multiple rows");
      return rows[0] || null;
    },
    async revoke(tenantId, identityRef) {
      const rows = (await query(`
        UPDATE public.lm_agent_identity_refs
        SET state = 'revoked', revoked_at = clock_timestamp()
        WHERE tenant_id = $1 AND identity_ref = $2 AND state = 'active'
        RETURNING identity_ref
      `, [tenantId, identityRef])).rows;
      if (rows.length > 1) throw new Error("agent identity ref revoke returned multiple rows");
      return rows.length === 1;
    },
    async revokeAndCloseDependents(input) {
      const rows = (await query(`
        WITH revoked_ref AS (
          UPDATE public.lm_agent_identity_refs
          SET state = 'revoked', revoked_at = clock_timestamp()
          WHERE tenant_id = $1 AND identity_ref = $2 AND state = 'active'
          RETURNING identity_ref
        ), closed_jobs AS (
          UPDATE public.lm_runtime_jobs
          SET status = CASE
              WHEN status = 'running' AND effect_class <> 'none' THEN 'reconciling'
              ELSE 'dead_letter'
            END,
            lease_owner = NULL,
            lease_expires_at = NULL,
            last_error_code = $3,
            updated_at = clock_timestamp()
          WHERE tenant_id = $1
            AND input_refs @> jsonb_build_object('identity_ref', $2::text)
            AND status IN ('queued', 'running')
            AND EXISTS (SELECT 1 FROM revoked_ref)
          RETURNING job_id
        ), deleted_leases AS (
          DELETE FROM public.lm_cloud_runtime_leases
          WHERE tenant_id = $1 AND job_id IN (SELECT job_id FROM closed_jobs)
          RETURNING job_id
        )
        SELECT EXISTS(SELECT 1 FROM revoked_ref) AS revoked,
               (SELECT count(*)::integer FROM closed_jobs) AS closed,
               (SELECT count(*)::integer FROM deleted_leases) AS leases_deleted
      `, [input.tenantId, input.identityRef, "AGENT_IDENTITY_REVOKED"])).rows;
      if (rows.length !== 1) throw new Error("agent identity revoke transaction lost result");
      return { revoked: rows[0].revoked === true, closed: Number(rows[0].closed) };
    },
  });
}

module.exports = {
  BROWSER_AUTH_CONTEXT_EXPIRED_CODE,
  normalizeAuthOrigin,
  validateSessionContext,
  scopeSessionContextToOrigin,
  sealBrowserContext,
  openBrowserContext,
  readBrowserAuthSession,
  upsertBrowserAuthSession,
  invalidateBrowserAuthSession,
  createAgentIdentityRefStore,
};
