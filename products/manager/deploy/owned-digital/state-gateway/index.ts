import { PROJECT_URL, verifyGithubToken } from "./auth.mjs";

type GatewayOptions = {
  verifyToken?: typeof verifyGithubToken;
  readEnv?: (name: string) => string | undefined;
  fetch?: typeof globalThis.fetch;
};
const runtime = globalThis as typeof globalThis & {
  Deno?: {
    env: { get(name: string): string | undefined };
    serve(handler: (request: Request) => Promise<Response>): unknown;
  };
};
const MAX_JSON_BYTES = 2 * 1024 * 1024;
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const HEX_SHA256 = /^[0-9a-f]{64}$/;
class TooLarge extends Error {}

function reply(status: number, value: unknown) {
  return Response.json(value, { status, headers: { "Cache-Control": "no-store" } });
}

async function boundedJson(message: { body: ReadableStream<Uint8Array> | null }) {
  if (!message.body) throw new Error("missing body");
  const reader = message.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    void reader.cancel().catch(() => {});
  }, 10000);
  try {
    while (true) {
      const part = await reader.read();
      if (timedOut) throw new Error("body unavailable");
      if (part.done) break;
      size += part.value.byteLength;
      if (size > MAX_JSON_BYTES) {
        void reader.cancel().catch(() => {});
        throw new TooLarge();
      }
      chunks.push(part.value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } finally {
    clearTimeout(timer);
    reader.releaseLock();
  }
}

function exactFields(value: unknown, fields: string[]): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    && Object.keys(value).length === fields.length
    && fields.every(name => Object.hasOwn(value, name));
}

function snapshotBytes(value: unknown) {
  if (typeof value !== "string" || value.length === 0 || value.length > 1398104
    || value.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(value)) {
    throw new Error("invalid snapshot");
  }
  const decoded = atob(value);
  if (decoded.length > 1048576 || btoa(decoded) !== value) throw new Error("invalid snapshot");
  return Uint8Array.from(decoded, character => character.charCodeAt(0));
}

function validateRequest(value: unknown) {
  const operation = (value as Record<string, unknown> | null)?.operation;
  const fields = operation === "checkpoint"
    ? ["operation", "nonce", "revision", "sha256", "snapshot"] : ["operation", "nonce"];
  if (!exactFields(value, fields) || !["acquire", "checkpoint", "release"].includes(String(operation))
    || typeof value.nonce !== "string" || !UUID_V4.test(value.nonce)) throw new Error("invalid request");
  if (operation === "checkpoint") {
    if (!Number.isSafeInteger(value.revision) || Number(value.revision) < 0
      || typeof value.sha256 !== "string" || !HEX_SHA256.test(value.sha256)) throw new Error("invalid CAS");
    snapshotBytes(value.snapshot);
  }
  return value;
}

async function validateState(value: unknown, owner: string | null) {
  if (!exactFields(value, ["revision", "sha256", "snapshot", "owner"])
    || !Number.isSafeInteger(value.revision) || Number(value.revision) < 0
    || typeof value.sha256 !== "string" || !HEX_SHA256.test(value.sha256)
    || value.owner !== owner) throw new Error("invalid state");
  const digest = await crypto.subtle.digest("SHA-256", snapshotBytes(value.snapshot));
  const actual = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  if (actual !== value.sha256) throw new Error("invalid state");
  return value;
}

export function createHandler(options: GatewayOptions = {}) {
  const verifyToken = options.verifyToken ?? verifyGithubToken;
  const readEnv = options.readEnv ?? (name => runtime.Deno?.env.get(name));
  const fetch = options.fetch ?? globalThis.fetch;
  return async (request: Request) => {
    if (request.method !== "POST") return reply(405, { error: "POST required" });
    let identity;
    try {
      const header = request.headers.get("authorization") ?? "";
      if (header.length > 16384 || !/^Bearer [A-Za-z0-9_.-]+$/.test(header)) throw new Error("missing token");
      identity = await verifyToken(header.slice(7));
    } catch { return reply(401, { error: "unauthorized" }); }
    if (request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json"
      || ![null, "identity"].includes(request.headers.get("content-encoding"))) {
      return reply(415, { error: "JSON required" });
    }
    let body;
    try { body = validateRequest(await boundedJson(request)); }
    catch (error) { return reply(error instanceof TooLarge ? 413 : 400, { error: "invalid request" }); }
    try {
      const projectUrl = readEnv("SUPABASE_URL");
      const serviceRole = readEnv("SUPABASE_SERVICE_ROLE_KEY");
      if (projectUrl !== PROJECT_URL || !serviceRole) throw new Error("configuration unavailable");
      const owner = `${identity.runId}:${identity.runAttempt}:${body.nonce}`;
      const response = await fetch(`${PROJECT_URL}/rest/v1/rpc/lm_manager_owned_checkpoint`, {
        method: "POST", redirect: "error", signal: AbortSignal.timeout(10000),
        headers: { "Content-Type": "application/json", apikey: serviceRole, Authorization: `Bearer ${serviceRole}` },
        body: JSON.stringify({ p_operation: body.operation, p_owner: owner,
          p_revision: body.revision ?? null, p_sha256: body.sha256 ?? null, p_snapshot: body.snapshot ?? null }),
      });
      if (!response.ok) {
        void response.body?.cancel().catch(() => {});
        if (response.status === 404) return reply(404, { error: "state unavailable" });
        if (response.status === 409) return reply(409, { error: "state conflict" });
        throw new Error("database unavailable");
      }
      const state = await validateState(await boundedJson(response), body.operation === "release" ? null : owner);
      return reply(200, state);
    } catch { return reply(503, { error: "service unavailable" }); }
  };
}

if (import.meta.main && runtime.Deno) runtime.Deno.serve(createHandler());
