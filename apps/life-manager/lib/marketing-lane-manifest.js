"use strict";

const { createHash, randomUUID } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { resolveDataRoot } = require("./runtime-paths.js");

const POSTIZ_INTEGRATIONS_URL = "https://api.postiz.com/public/v1/integrations";
const PLATFORMS = new Set(["instagram", "tiktok", "youtube"]);
const HOLD_PLATFORMS = new Set([...PLATFORMS, "x"]);
const LANE_STATES = new Set(["production-armed", "shadow", "default-off", "disabled"]);
const ACCOUNT = /^@?[A-Za-z0-9._-]{1,80}$/;
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const LOCALE = /^[a-z]{2}(?:-[A-Z]{2})?$/;
const PRODUCTS = new Set(["honne-ai", "anicca", "ebook-ja"]);

function invalid(message = "marketing lane manifest invalid") {
  throw new Error(message);
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${stableJson(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const child of Object.values(value)) deepFreeze(child);
  return Object.freeze(value);
}

function text(value, label, pattern = null) {
  const result = String(value == null ? "" : value).trim();
  if (!result || (pattern && !pattern.test(result))) invalid(`${label} invalid`);
  return result;
}

function aliasValue(value, aliases, label, normalize) {
  const values = aliases
    .filter((key) => value && value[key] !== undefined)
    .map((key) => normalize(value[key], label));
  if (values.length === 0) return undefined;
  if (values.some((candidate) => candidate !== values[0])) {
    invalid("marketing lane assignment ambiguous");
  }
  return values[0];
}

function rowsFrom(input) {
  if (Array.isArray(input)) return input;
  if (!input || typeof input !== "object") invalid();
  const candidates = ["integrations", "rows", "data", "lanes"]
    .filter((key) => Array.isArray(input[key]));
  if (candidates.length > 1) invalid("Postiz integration registry response ambiguous");
  if (candidates.length === 1) return input[candidates[0]];
  invalid("Postiz integration registry response invalid");
}

function normalizeIntegration(value, label = "integration id") {
  return text(value, label, IDENTIFIER);
}

function platformName(value) {
  const normalized = text(value, "marketing lane platform").toLowerCase();
  if (normalized === "instagram-standalone") return "instagram";
  return normalized;
}

function normalizeTenant(value, label = "marketing lane tenant") {
  return text(value, label, IDENTIFIER);
}

function normalizeProduct(value) {
  return text(value, "marketing lane product", IDENTIFIER);
}

function normalizeLocale(value) {
  return text(value, "marketing lane locale", LOCALE);
}

function normalizeAccount(value) {
  return text(value, "marketing lane account", ACCOUNT);
}

function normalizeProvider(value) {
  return text(value, "marketing lane provider").toLowerCase();
}

function normalizeDisabled(value) {
  if (typeof value !== "boolean") invalid("marketing lane disabled state invalid");
  return value;
}

function normalizeLaneState(value) {
  return text(value, "marketing lane state").toLowerCase();
}

function normalizeBoolean(value, label) {
  if (typeof value !== "boolean") invalid(`${label} invalid`);
  return value;
}

function normalizeDailyLimit(value, label = "marketing lane daily limit") {
  if (!Number.isSafeInteger(value) || value < 0) invalid(`${label} invalid`);
  return value;
}

function profileHandle(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const candidates = ["handle", "username", "profile", "name"]
      .filter((key) => value[key] !== undefined)
      .map((key) => profileHandle(value[key]));
    if (candidates.length === 0 || candidates.some((candidate) => candidate !== candidates[0])) {
      invalid("marketing lane profile ambiguous");
    }
    return candidates[0];
  }
  const result = text(value, "marketing lane profile");
  let handle = result;
  try {
    const parsed = new URL(result);
    if (
      parsed.protocol !== "https:"
      || !new Set(["instagram.com", "www.instagram.com", "tiktok.com", "www.tiktok.com", "youtube.com", "www.youtube.com"]).has(parsed.hostname)
      || parsed.search
      || parsed.hash
    ) invalid("marketing lane profile invalid");
    handle = parsed.pathname.replace(/^\/@?/, "").replace(/\/$/, "");
  } catch {
    // A Postiz profile is commonly returned as a handle rather than a URL.
  }
  if (!ACCOUNT.test(handle) || ["unknown", "historical", "ambiguous"].includes(handle.toLowerCase().replace(/^@/, ""))) invalid("marketing lane profile invalid");
  return handle.startsWith("@") ? handle : `@${handle}`;
}

function profilePlatforms(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return ["handle", "username", "profile", "name"]
      .filter((key) => value[key] !== undefined)
      .flatMap((key) => profilePlatforms(value[key]));
  }
  const result = text(value, "marketing lane profile");
  try {
    const parsed = new URL(result);
    const hosts = {
      "instagram.com": "instagram",
      "www.instagram.com": "instagram",
      "tiktok.com": "tiktok",
      "www.tiktok.com": "tiktok",
      "youtube.com": "youtube",
      "www.youtube.com": "youtube",
    };
    if (parsed.protocol !== "https:" || !hosts[parsed.hostname] || parsed.search || parsed.hash) {
      invalid("marketing lane profile invalid");
    }
    return [hosts[parsed.hostname]];
  } catch (error) {
    if (error && error.message === "marketing lane profile invalid") throw error;
    return [];
  }
}

function canonicalIdentity(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid("marketing lane assignment invalid");
  const nested = value.integration && typeof value.integration === "object" ? value.integration : {};
  const identity = {
    integration_id: aliasValue({ ...value, integration_nested_id: nested.id }, ["integration_id", "integrationId", "id", "integration_nested_id"], "integration id", normalizeIntegration),
    tenant_id: aliasValue(value, ["tenant_id", "tenant", "tenantId"], "marketing lane tenant", normalizeTenant),
    product_id: aliasValue(value, ["product_id", "product", "productId"], "marketing lane product", normalizeProduct),
    locale: aliasValue(value, ["locale", "locale_id", "localeId"], "marketing lane locale", normalizeLocale),
    platform: aliasValue(value, ["platform", "platform_id", "providerIdentifier", "provider_identifier", "identifier"], "marketing lane platform", platformName),
    account: aliasValue(value, ["account", "account_id", "accountId"], "marketing lane account", normalizeAccount),
    profile: aliasValue(value, ["profile", "profile_handle", "profileHandle", "handle"], "marketing lane profile", profileHandle),
    provider: aliasValue(value, ["provider", "provider_name"], "marketing lane provider", normalizeProvider),
    disabled: aliasValue(value, ["disabled"], "marketing lane disabled state", normalizeDisabled),
    lane_state: aliasValue(value, ["lane_state", "state", "mode"], "marketing lane state", normalizeLaneState),
    production_armed: aliasValue(value, ["production_armed"], "marketing lane production_armed", (candidate) => normalizeBoolean(candidate, "marketing lane production_armed")),
    verified: aliasValue(value, ["verified"], "marketing lane verified", (candidate) => normalizeBoolean(candidate, "marketing lane verified")),
    disposition: aliasValue(value, ["disposition"], "marketing lane disposition", (candidate) => text(candidate, "marketing lane disposition", IDENTIFIER)),
    owner: aliasValue(value, ["owner"], "marketing lane owner", (candidate) => text(candidate, "marketing lane owner", IDENTIFIER)),
    renderer: aliasValue(value, ["renderer"], "marketing lane renderer", (candidate) => text(candidate, "marketing lane renderer", IDENTIFIER)),
    format: aliasValue(value, ["format"], "marketing lane format", (candidate) => text(candidate, "marketing lane format", IDENTIFIER)),
    approved_pack: aliasValue(value, ["approved_pack"], "marketing lane approved pack", (candidate) => text(candidate, "marketing lane approved pack", IDENTIFIER)),
    canary_state: aliasValue(value, ["canary_state"], "marketing lane canary state", (candidate) => text(candidate, "marketing lane canary state", IDENTIFIER)),
    target_daily_limit: aliasValue(value, ["target_daily_limit"], "marketing lane daily limit", normalizeDailyLimit),
  };
  return identity;
}

const IDENTITY_FIELDS = [
  "integration_id", "tenant_id", "product_id", "locale", "platform", "account",
  "profile", "provider", "disabled", "lane_state", "production_armed", "verified",
  "disposition", "renderer", "format", "approved_pack", "canary_state", "target_daily_limit",
  "owner",
];

function compareIdentities(left, right) {
  for (const field of IDENTITY_FIELDS) {
    if (left[field] !== undefined && right[field] !== undefined && left[field] !== right[field]) {
      invalid("marketing lane assignment ambiguous");
    }
  }
}

function assignmentMap(assignments) {
  if (!Array.isArray(assignments)) invalid("marketing lane assignments invalid");
  const result = new Map();
  for (const assignment of assignments) {
    if (!assignment || typeof assignment !== "object" || Array.isArray(assignment)) invalid("marketing lane assignment invalid");
    const identity = canonicalIdentity(assignment);
    const id = identity.integration_id;
    if (id === undefined) invalid("marketing lane assignment integration id required");
    if (result.has(id)) invalid("marketing lane assignment ambiguous");
    result.set(id, { assignment, identity });
  }
  return result;
}

function normalizeLane(row, options, assignments) {
  if (!row || typeof row !== "object" || Array.isArray(row)) invalid();
  const rawIdentity = canonicalIdentity(row);
  const id = rawIdentity.integration_id;
  if (id === undefined) invalid("integration id invalid");
  const assignmentRecord = assignments.get(id);
  if (!assignmentRecord) invalid("marketing lane assignment missing");
  compareIdentities(rawIdentity, assignmentRecord.identity);
  if (row.verified !== true || assignmentRecord.assignment.verified !== true) {
    invalid("marketing lane route is not live-verified");
  }
  for (const candidate of [row, assignmentRecord.assignment]) {
    if (candidate.historical !== undefined && typeof candidate.historical !== "boolean") {
      invalid("marketing lane route is not live-verified");
    }
    const sourceValues = ["source", "profile_status"]
      .filter((key) => candidate[key] !== undefined)
      .map((key) => {
        if (typeof candidate[key] !== "string") invalid("marketing lane route is not live-verified");
        return candidate[key].trim().toLowerCase();
      });
    if (candidate.historical === true || sourceValues.some((source) => ["historical", "unknown", "ambiguous"].includes(source))) {
      invalid("marketing lane route is not live-verified");
    }
  }
  const tenantExplicit = rawIdentity.tenant_id ?? assignmentRecord.identity.tenant_id;
  const tenantId = tenantExplicit ?? normalizeTenant(options.tenantId);
  if (options.tenantId !== undefined && tenantExplicit !== undefined && tenantExplicit !== normalizeTenant(options.tenantId)) {
    invalid("marketing lane tenant ambiguous");
  }
  const productId = rawIdentity.product_id ?? assignmentRecord.identity.product_id;
  if (productId === undefined) invalid("marketing lane product invalid");
  if (!PRODUCTS.has(productId)) invalid("marketing lane product unknown");
  const locale = rawIdentity.locale ?? assignmentRecord.identity.locale;
  if (locale === undefined) invalid("marketing lane locale invalid");
  const platform = rawIdentity.platform ?? assignmentRecord.identity.platform;
  if (platform === undefined) invalid("marketing lane platform invalid");
  if (!PLATFORMS.has(platform)) invalid("marketing lane platform unknown");
  const provider = rawIdentity.provider ?? assignmentRecord.identity.provider;
  if (provider === undefined) invalid("marketing lane provider invalid");
  if (provider !== "postiz") invalid("marketing lane provider unknown");
  const account = rawIdentity.account ?? assignmentRecord.identity.account;
  if (account === undefined) invalid("marketing lane account invalid");
  if (["unknown", "historical", "ambiguous"].includes(account.toLowerCase().replace(/^@/, ""))) invalid("marketing lane account invalid");
  const profile = rawIdentity.profile ?? assignmentRecord.identity.profile;
  if (profile === undefined) invalid("marketing lane profile invalid");
  const disabled = rawIdentity.disabled ?? assignmentRecord.identity.disabled;
  if (disabled === undefined) invalid("marketing lane disabled state invalid");
  const requestedState = rawIdentity.lane_state ?? assignmentRecord.identity.lane_state;
  const laneState = requestedState == null
    ? (disabled ? "disabled" : "default-off")
    : requestedState;
  if (!LANE_STATES.has(laneState)) invalid("marketing lane state unknown");
  if ((disabled && laneState === "production-armed") || (!disabled && laneState === "disabled")) {
    invalid("marketing lane disabled state ambiguous");
  }
  if (platform === "youtube" && productId !== "anicca") invalid("Honne YouTube lane is forbidden");
  const profilePlatformsSeen = [row, assignmentRecord.assignment]
    .flatMap((candidate) => ["profile", "profile_handle", "profileHandle", "handle"]
      .filter((key) => candidate[key] !== undefined)
      .flatMap((key) => profilePlatforms(candidate[key])))
    .filter((candidate, index, values) => values.indexOf(candidate) === index);
  if (profilePlatformsSeen.some((profilePlatform) => profilePlatform !== platform)) {
    invalid("marketing lane profile/platform ambiguous");
  }
  const productionArmed = !disabled && laneState === "production-armed";
  for (const explicitProductionState of [rawIdentity.production_armed, assignmentRecord.identity.production_armed]) {
    if (explicitProductionState !== undefined && explicitProductionState !== productionArmed) {
      invalid("marketing lane production state invalid");
    }
  }
  const portfolioValues = ["disposition", "renderer", "format", "approved_pack", "canary_state", "target_daily_limit"]
    .map((field) => rawIdentity[field] ?? assignmentRecord.identity[field]);
  const hasPortfolioMetadata = portfolioValues.some((value) => value !== undefined);
  if (hasPortfolioMetadata && portfolioValues.some((value) => value === undefined)) {
    invalid("marketing target metadata incomplete");
  }
  if (hasPortfolioMetadata && (portfolioValues[0] !== "target" || portfolioValues[5] < 1)) {
    invalid("marketing target disposition invalid");
  }
  return {
    tenant_id: tenantId,
    product_id: productId,
    locale,
    platform,
    account,
    integration_id: id,
    provider,
    profile,
    disabled,
    lane_state: laneState,
    production_armed: productionArmed,
    ...(rawIdentity.owner ?? assignmentRecord.identity.owner ? {
      owner: rawIdentity.owner ?? assignmentRecord.identity.owner,
    } : {}),
    ...(hasPortfolioMetadata ? {
      disposition: portfolioValues[0],
      renderer: portfolioValues[1],
      format: portfolioValues[2],
      approved_pack: portfolioValues[3],
      canary_state: portfolioValues[4],
      target_daily_limit: portfolioValues[5],
    } : {}),
  };
}

function normalizeHold(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || value.verified !== true) {
    invalid("marketing hold is not live-verified");
  }
  const hold = {
    integration_id: normalizeIntegration(value.integration_id ?? value.id),
    platform: platformName(value.platform),
    account: normalizeAccount(value.account),
    provider: normalizeProvider(value.provider),
    provider_disabled: normalizeDisabled(value.provider_disabled),
    ...(value.owner === undefined ? {} : { owner: text(value.owner, "marketing hold owner", IDENTIFIER) }),
    disposition: text(value.disposition, "marketing hold disposition", IDENTIFIER),
    target_daily_limit: normalizeDailyLimit(value.target_daily_limit, "marketing hold daily limit"),
  };
  const validSkip = hold.disposition === "skip"
    && hold.platform === "youtube"
    && hold.account.toLowerCase() === "@anicca-jp";
  if (!HOLD_PLATFORMS.has(hold.platform) || hold.provider !== "postiz"
    || (!validSkip && hold.disposition !== "hold") || hold.target_daily_limit !== 0) {
    invalid("marketing hold disposition invalid");
  }
  return hold;
}

function createMarketingLaneManifest(input, options = {}) {
  const rows = rowsFrom(input);
  if (rows.length === 0) invalid("marketing lane manifest has no integrations");
  const inputTenantId = input && !Array.isArray(input)
    ? aliasValue(input, ["tenant_id", "tenant", "tenantId"], "marketing lane tenant", normalizeTenant)
    : undefined;
  const optionTenantId = options.tenantId === undefined
    ? undefined
    : normalizeTenant(options.tenantId);
  if (inputTenantId !== undefined && optionTenantId !== undefined && inputTenantId !== optionTenantId) {
    invalid("marketing lane tenant ambiguous");
  }
  const tenantId = optionTenantId ?? inputTenantId;
  if (tenantId == null) invalid("marketing lane tenant is required");
  const assignmentInput = options.assignments !== undefined
    ? options.assignments
    : (input && !Array.isArray(input) ? input.assignments : undefined);
  if (assignmentInput === undefined) invalid("marketing lane assignments required");
  const assignments = assignmentMap(assignmentInput);
  const lanes = rows.map((row) => normalizeLane(row, { tenantId }, assignments));
  const holdInput = input && !Array.isArray(input) && input.holds !== undefined ? input.holds : [];
  if (!Array.isArray(holdInput)) invalid("marketing holds invalid");
  const holds = holdInput.map(normalizeHold);
  const identities = new Set();
  const integrations = new Set();
  const observedAssignments = new Set();
  for (const lane of lanes) {
    const identity = [lane.tenant_id, lane.product_id, lane.locale, lane.platform, lane.account].join("\n");
    if (identities.has(identity) || integrations.has(lane.integration_id)) invalid("marketing lane route ambiguous");
    identities.add(identity);
    integrations.add(lane.integration_id);
    if (assignments.has(lane.integration_id)) observedAssignments.add(lane.integration_id);
  }
  for (const id of assignments.keys()) {
    if (!observedAssignments.has(id)) invalid("marketing lane assignment missing");
  }
  const portfolio = holds.length > 0 || lanes.some((lane) => lane.disposition !== undefined);
  if (portfolio && (holds.length === 0 || lanes.some((lane) => lane.disposition !== "target"))) {
    invalid("marketing portfolio incomplete");
  }
  for (const hold of holds) {
    if (integrations.has(hold.integration_id)) invalid("marketing portfolio integration ambiguous");
    integrations.add(hold.integration_id);
  }
  lanes.sort((left, right) => [
    left.product_id, left.locale, left.platform, left.account, left.integration_id,
  ].join("\n").localeCompare([
    right.product_id, right.locale, right.platform, right.account, right.integration_id,
  ].join("\n")));
  holds.sort((left, right) => [left.platform, left.account, left.integration_id].join("\n").localeCompare([right.platform, right.account, right.integration_id].join("\n")));
  const core = { schema_version: portfolio ? 2 : 1, tenant_id: String(tenantId), lanes, ...(portfolio ? { holds } : {}) };
  const manifest = {
    ...core,
    manifest_id: `marketing-lane-manifest:${createHash("sha256").update(stableJson(core), "utf8").digest("hex")}`,
  };
  return deepFreeze(manifest);
}

function isMarketingLaneManifest(value) {
  try {
    if (!value || ![1, 2].includes(value.schema_version) || !Array.isArray(value.lanes) || !value.manifest_id) return false;
    const rows = value.lanes.map((lane) => ({ ...lane, verified: true }));
    const holds = value.schema_version === 2 && Array.isArray(value.holds)
      ? value.holds.map((hold) => ({ ...hold, verified: true }))
      : undefined;
    const rebuilt = createMarketingLaneManifest(
      { tenant_id: value.tenant_id, integrations: rows, ...(holds ? { holds } : {}) },
      { tenantId: value.tenant_id, assignments: rows.map((lane) => ({ ...lane })) },
    );
    return rebuilt.manifest_id === value.manifest_id && stableJson(rebuilt.lanes) === stableJson(value.lanes);
  } catch {
    return false;
  }
}

function serializeMarketingLaneManifest(value) {
  if (!isMarketingLaneManifest(value)) invalid();
  return stableJson(value);
}

function writeMarketingLaneManifest(value, options = {}) {
  if (!isMarketingLaneManifest(value)) invalid();
  if (options.dataDir == null && options.env == null) {
    invalid("marketing lane manifest data root is required");
  }
  let root;
  if (options.dataDir != null && options.env != null) {
    const explicitRoot = resolveDataRoot({ LM_DATA_DIR: options.dataDir });
    const envRoot = resolveDataRoot(options.env);
    if (explicitRoot !== envRoot) invalid("marketing lane manifest data roots ambiguous");
    root = envRoot;
  } else {
    root = resolveDataRoot(options.env || { LM_DATA_DIR: options.dataDir });
  }
  const file = path.join(root, "marketing", "lane-manifest.json");
  const directory = path.dirname(file);
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const temporary = `${file}.tmp-${process.pid}-${randomUUID()}`;
  const descriptor = fs.openSync(temporary, "wx", 0o600);
  try {
    fs.writeSync(descriptor, `${serializeMarketingLaneManifest(value)}\n`);
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  fs.renameSync(temporary, file);
  fs.chmodSync(file, 0o600);
  const directoryDescriptor = fs.openSync(directory, fs.constants.O_RDONLY);
  try { fs.fsyncSync(directoryDescriptor); } finally { fs.closeSync(directoryDescriptor); }
  return file;
}

async function fetchPostizIntegrationRegistry(options = {}) {
  const accessToken = String(options.accessToken || "").trim();
  if (!accessToken) invalid("Postiz integration registry fetch blocked: access token unavailable");
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== "function") invalid("Postiz integration registry fetch blocked: fetch unavailable");
  if (options.endpoint !== undefined && options.endpoint !== POSTIZ_INTEGRATIONS_URL) {
    invalid("Postiz integration registry fetch blocked: endpoint invalid");
  }
  let response;
  try {
    response = await fetchImpl(POSTIZ_INTEGRATIONS_URL, {
      method: "GET",
      headers: { Authorization: accessToken, Accept: "application/json" },
    });
  } catch {
    invalid("Postiz integration registry fetch failed: request unavailable");
  }
  if (!response || !response.ok) invalid(`Postiz integration registry fetch failed: HTTP ${response && response.status || "unknown"}`);
  let body;
  try { body = typeof response.json === "function" ? await response.json() : JSON.parse(await response.text()); }
  catch { invalid("Postiz integration registry response invalid"); }
  rowsFrom(body);
  return body;
}

module.exports = {
  POSTIZ_INTEGRATIONS_URL,
  createMarketingLaneManifest,
  fetchPostizIntegrationRegistry,
  isMarketingLaneManifest,
  serializeMarketingLaneManifest,
  writeMarketingLaneManifest,
};
