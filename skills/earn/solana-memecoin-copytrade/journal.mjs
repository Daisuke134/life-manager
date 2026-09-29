import { appendFile, chmod, mkdir, readFile } from "node:fs/promises";
import path from "node:path";

const SECRET_KEYS = new Set(["privatekey", "private_key", "secretkey", "secret_key", "seed", "mnemonic", "secret"]);
const TERMINAL_STATUSES = new Set(["paper", "verified", "rejected", "skipped", "failed"]);

function containsSecret(value) {
  if (!value || typeof value !== "object") return false;
  if (Array.isArray(value)) return value.some(containsSecret);
  return Object.entries(value).some(([key, nested]) => SECRET_KEYS.has(key.toLowerCase()) || containsSecret(nested));
}

async function prepare(journalPath) {
  const directory = path.dirname(journalPath);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  await chmod(directory, 0o700);
}

export async function append(journalPath, row) {
  if (!row || typeof row !== "object" || Array.isArray(row) || typeof row.kind !== "string" || !row.kind) {
    throw new Error("journal_row_invalid");
  }
  if (containsSecret(row)) throw new Error("journal_secret_field");
  await prepare(journalPath);
  const record = { ...row, recordedAt: row.recordedAt || new Date().toISOString() };
  await appendFile(journalPath, `${JSON.stringify(record)}\n`, { mode: 0o600 });
  await chmod(journalPath, 0o600);
  return record;
}

export async function readRows(journalPath) {
  let raw;
  try { raw = await readFile(journalPath, "utf8"); } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
  return raw.split("\n").filter(Boolean).map((line) => {
    try {
      const row = JSON.parse(line);
      if (!row || typeof row !== "object" || containsSecret(row)) throw new Error("journal_row_invalid");
      return row;
    } catch {
      throw new Error("journal_row_invalid");
    }
  });
}

export async function openIntent(journalPath) {
  const rows = await readRows(journalPath);
  const intents = rows.filter((row) => row.kind === "intent" && typeof row.intentId === "string");
  return intents.filter((intent) => !rows.some((row) => row.intentId === intent.intentId
    && row.kind === "receipt" && TERMINAL_STATUSES.has(row.status)));
}

export async function seenSourceSignature(journalPath, signature) {
  if (typeof signature !== "string" || !signature) return false;
  const rows = await readRows(journalPath);
  return rows.some((row) => row.sourceSignature === signature
    || row.source_signature === signature || row.signature === signature);
}
