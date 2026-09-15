"use strict";

// Provider-neutral browser session boundary.  Steel is the current adapter, but the contract keeps
// endpoint, ownership, display mode, storage scope, and finite budgets above the provider client so
// a local Steel service and a cloud/self-hosted Steel service use the same rules.

const net = require("node:net");

const DEFAULT_STEEL_ENDPOINT = "http://steel-browser.railway.internal:8080";
const SESSION_CONTRACT_VERSION = 1;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SAFE_KEY = /^[A-Za-z][A-Za-z0-9._:-]{0,127}$/;
const SECRET_LIKE_KEY = /(?:token|secret|password|credential|authorization|api[_-]?key)/i;
const MODES = new Set(["headless", "headed"]);
const PURPOSES = new Set(["autonomous", "human_gate", "diagnostic"]);
const BACKENDS = new Set(["steel"]);

function invalid(message) {
  throw new Error(`browser session contract: ${message}`);
}

function stringValue(value, label, max = 200) {
  if (typeof value !== "string") invalid(`${label} invalid`);
  const text = value.trim();
  if (!text || text.length > max) invalid(`${label} invalid`);
  return text;
}

function safeIdentifier(value, label) {
  const text = stringValue(value, label, 128);
  if (!SAFE_ID.test(text)) invalid(`${label} invalid`);
  return text;
}

function privateIp(hostname) {
  const host = hostname.startsWith("[") && hostname.endsWith("]")
    ? hostname.slice(1, -1)
    : hostname;
  const family = net.isIP(host);
  if (family === 4) {
    const octets = host.split(".").map(Number);
    return octets[0] === 10
      || octets[0] === 127
      || (octets[0] === 169 && octets[1] === 254)
      || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31)
      || (octets[0] === 192 && octets[1] === 168);
  }
  if (family === 6) {
    const normalized = host.toLowerCase();
    return normalized === "::1" || normalized.startsWith("fc") || normalized.startsWith("fd")
      || normalized.startsWith("fe8") || normalized.startsWith("fe9")
      || normalized.startsWith("fea") || normalized.startsWith("feb");
  }
  return false;
}

function privateHostname(hostname) {
  const host = hostname.toLowerCase();
  return host === "localhost"
    || host.endsWith(".localhost")
    || host.endsWith(".local")
    || host.endsWith(".internal")
    || !host.includes(".");
}

function endpointUrl(value) {
  const text = stringValue(value, "endpoint", 500);
  let parsed;
  try { parsed = new URL(text); } catch { invalid("endpoint URL invalid"); }
  if (!["http:", "https:"].includes(parsed.protocol)
    || !parsed.hostname
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
    || (parsed.pathname !== "" && parsed.pathname !== "/")
    || parsed.hostname.endsWith(".")) {
    invalid("endpoint URL invalid");
  }
  return parsed;
}

function normalizeBrowserEndpoint(value, options = {}) {
  const parsed = endpointUrl(value);
  const isPrivate = privateIp(parsed.hostname) || privateHostname(parsed.hostname);
  if (!isPrivate) {
    if (options.allowPublicEndpoint !== true || parsed.protocol !== "https:") {
      invalid("private endpoint required (public HTTPS requires explicit opt-in)");
    }
  }
  return `${parsed.protocol}//${parsed.host}`;
}

function origin(value) {
  const text = stringValue(value, "storage origin", 300);
  let parsed;
  try { parsed = new URL(text); } catch { invalid("storage origin invalid"); }
  if (parsed.protocol !== "https:"
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
    || (parsed.pathname !== "" && parsed.pathname !== "/")) {
    invalid("storage origin invalid");
  }
  return parsed.origin;
}

function keyList(value, label, { required = false } = {}) {
  if (value == null) {
    if (required) invalid(`${label} required`);
    return [];
  }
  if (!Array.isArray(value) || value.length > 64) invalid(`${label} invalid`);
  const values = value.map((item) => {
    const key = stringValue(item, `${label} entry`, 128);
    if (!SAFE_KEY.test(key) || key === "*" || SECRET_LIKE_KEY.test(key)) {
      invalid(`${label} entry invalid`);
    }
    return key;
  });
  return [...new Set(values)].sort();
}

function normalizeStoragePolicy(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    invalid("storage policy invalid");
  }
  const allowed = new Set([
    "origins", "cookieNames", "localStorageKeys", "sessionStorageKeys",
    "cookie_names", "local_storage_keys", "session_storage_keys",
  ]);
  if (Object.keys(input).some((key) => !allowed.has(key))) invalid("storage policy key unsupported");
  const origins = input.origins;
  if (!Array.isArray(origins) || origins.length < 1 || origins.length > 8) {
    invalid("storage origins invalid");
  }
  const normalizedOrigins = [...new Set(origins.map(origin))].sort();
  return Object.freeze({
    origins: Object.freeze(normalizedOrigins),
    cookie_names: Object.freeze(keyList(input.cookieNames ?? input.cookie_names, "cookie names")),
    local_storage_keys: Object.freeze(keyList(input.localStorageKeys ?? input.local_storage_keys, "local storage keys")),
    session_storage_keys: Object.freeze(keyList(input.sessionStorageKeys ?? input.session_storage_keys, "session storage keys")),
  });
}

function boundedInteger(value, label, minimum, maximum, fallback) {
  const number = value == null ? fallback : value;
  if (!Number.isInteger(number) || number < minimum || number > maximum) invalid(`${label} invalid`);
  return number;
}

function normalizeScope(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) invalid("scope invalid");
  return Object.freeze({
    tenant_id: safeIdentifier(input.tenantId ?? input.tenant_id, "tenant id"),
    owner_id: safeIdentifier(input.ownerId ?? input.owner_id, "owner id"),
    provider: safeIdentifier(input.provider, "provider"),
  });
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
}

function createBrowserSessionConfig(input = {}) {
  if (!input || typeof input !== "object" || Array.isArray(input)) invalid("config invalid");
  const backend = input.backend == null ? "steel" : stringValue(input.backend, "backend", 40);
  if (!BACKENDS.has(backend)) invalid("backend unsupported");
  const allowPublicEndpoint = input.allowPublicEndpoint === true
    || (input.allowPublicEndpoint == null && process.env.LIFE_MANAGER_BROWSER_ALLOW_PUBLIC_ENDPOINT === "1");
  const endpoint = normalizeBrowserEndpoint(
    input.endpoint || process.env.LIFE_MANAGER_BROWSER_ENDPOINT || DEFAULT_STEEL_ENDPOINT,
    { allowPublicEndpoint },
  );
  const mode = input.mode == null ? "headless" : stringValue(input.mode, "mode", 40);
  const purpose = input.purpose == null ? "autonomous" : stringValue(input.purpose, "purpose", 40);
  if (!MODES.has(mode)) invalid("mode unsupported");
  if (!PURPOSES.has(purpose)) invalid("purpose unsupported");
  if (mode === "headed" && !["human_gate", "diagnostic"].includes(purpose)) {
    invalid("headed mode is only allowed for human_gate or diagnostic");
  }
  const limits = input.limits && typeof input.limits === "object" && !Array.isArray(input.limits)
    ? input.limits
    : {};
  const storage = normalizeStoragePolicy(input.storage);
  return deepFreeze({
    schema_version: SESSION_CONTRACT_VERSION,
    backend,
    endpoint,
    allow_public_endpoint: allowPublicEndpoint,
    mode,
    purpose,
    headless: mode === "headless",
    scope: normalizeScope(input.scope),
    storage,
    limits: {
      max_pages: boundedInteger(limits.maxPages ?? limits.max_pages, "max pages", 1, 8, 1),
      timeout_ms: boundedInteger(limits.timeoutMs ?? limits.timeout_ms, "timeout", 1_000, 300_000, 30_000),
      idle_timeout_ms: boundedInteger(limits.idleTimeoutMs ?? limits.idle_timeout_ms, "idle timeout", 1_000, 900_000, 60_000),
    },
  });
}

function endpointParts(value) {
  const parsed = endpointUrl(value);
  return { hostname: parsed.hostname.toLowerCase(), port: parsed.port || (parsed.protocol === "https:" ? "443" : "80") };
}

function assertBrowserSessionEndpoint(session, endpoint, options = {}) {
  const normalizedEndpoint = normalizeBrowserEndpoint(endpoint, options);
  const id = safeIdentifier(session && session.id, "session id");
  const websocket = stringValue(session && session.websocketUrl, "session websocket", 500);
  let parsed;
  try { parsed = new URL(websocket); } catch { invalid("session websocket invalid"); }
  if (!["ws:", "wss:"].includes(parsed.protocol)
    || !parsed.hostname
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash) {
    invalid("session websocket invalid");
  }
  const expected = endpointParts(normalizedEndpoint);
  const actual = {
    hostname: parsed.hostname.toLowerCase(),
    port: parsed.port || (parsed.protocol === "wss:" ? "443" : "80"),
  };
  if (expected.hostname !== actual.hostname || expected.port !== actual.port) {
    invalid("session websocket endpoint host mismatch");
  }
  return Object.freeze({ id, websocket_url: websocket });
}

function assertBrowserSession(session, config) {
  if (!config || config.schema_version !== SESSION_CONTRACT_VERSION || typeof config.endpoint !== "string") {
    invalid("session config invalid");
  }
  return assertBrowserSessionEndpoint(session, config.endpoint, {
    allowPublicEndpoint: config.allow_public_endpoint === true,
  });
}

module.exports = {
  DEFAULT_STEEL_ENDPOINT,
  SESSION_CONTRACT_VERSION,
  assertBrowserSession,
  assertBrowserSessionEndpoint,
  createBrowserSessionConfig,
  normalizeBrowserEndpoint,
  normalizeStoragePolicy,
};
