import { chmod, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import bs58 from "bs58";
import { Keypair, PublicKey } from "@solana/web3.js";

export const SERVICE = "solana-memecoin-copytrade-agent-wallet";
export const DEFAULT_SSOT = path.join(os.homedir(), ".local", "share", "anicca", "credentials.json");
const SECRET_KEYS = new Set(["privatekey", "private_key", "secretkey", "secret_key", "seed", "mnemonic", "secret"]);

async function readCredentials(ssotPath) {
  try {
    const raw = JSON.parse(await readFile(ssotPath, "utf8"));
    const document = Array.isArray(raw) ? { credentials: raw } : raw;
    if (!document || !Array.isArray(document.credentials)) throw new Error("credential_ssot_invalid");
    return document;
  } catch (error) {
    if (error?.code === "ENOENT") return { credentials: [] };
    if (error?.message === "credential_ssot_invalid") throw error;
    throw new Error("credential_ssot_unreadable");
  }
}

async function writeCredentials(ssotPath, document) {
  const directory = path.dirname(ssotPath);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  await chmod(directory, 0o700);
  const temporary = `${ssotPath}.${process.pid}.tmp`;
  await writeFile(temporary, `${JSON.stringify(document, null, 2)}\n`, { mode: 0o600 });
  await chmod(temporary, 0o600);
  await rename(temporary, ssotPath);
  await chmod(ssotPath, 0o600);
}

function walletView(keypair) {
  return Object.freeze({
    publicKey: keypair.publicKey.toBase58(),
    async signTransaction(transaction) {
      if (!transaction) throw new Error("transaction_invalid");
      if (typeof transaction.sign === "function") transaction.sign([keypair]);
      else if (typeof transaction.partialSign === "function") transaction.partialSign(keypair);
      else throw new Error("transaction_invalid");
      return transaction;
    },
  });
}

export async function loadOrCreateAgentWallet(ssotPath = DEFAULT_SSOT) {
  const document = await readCredentials(ssotPath);
  const existing = document.credentials.find((row) => row && row.service === SERVICE);
  if (existing) {
    if (typeof existing.private_key !== "string" || !existing.private_key) throw new Error("agent_wallet_credential_invalid");
    try {
      return walletView(Keypair.fromSecretKey(bs58.decode(existing.private_key)));
    } catch {
      throw new Error("agent_wallet_credential_invalid");
    }
  }

  const keypair = Keypair.generate();
  document.credentials.push({
    service: SERVICE,
    url: "https://solscan.io",
    username: keypair.publicKey.toBase58(),
    private_key: bs58.encode(keypair.secretKey),
    note: "agent-owned Solana wallet for read-only/paper/capped copy canary",
    updated_at: new Date().toISOString(),
  });
  await writeCredentials(ssotPath, document);
  return walletView(keypair);
}

function containsSecret(value) {
  if (!value || typeof value !== "object") return false;
  if (Array.isArray(value)) return value.some(containsSecret);
  return Object.entries(value).some(([key, nested]) => SECRET_KEYS.has(key.toLowerCase()) || containsSecret(nested));
}

export async function readTargets(configPath) {
  const raw = JSON.parse(await readFile(configPath, "utf8"));
  const targets = Array.isArray(raw) ? raw : raw?.targets;
  if (!Array.isArray(targets)) throw new Error("target_config_invalid");
  const seen = new Set();
  return targets.map((target) => {
    if (!target || typeof target !== "object" || containsSecret(target)) throw new Error("target_config_public_only");
    if (typeof target.address !== "string" || typeof target.label !== "string" || !target.label.trim()) {
      throw new Error("target_config_invalid");
    }
    let address;
    try { address = new PublicKey(target.address).toBase58(); } catch { throw new Error("target_address_invalid"); }
    if (seen.has(address)) throw new Error("target_address_duplicate");
    seen.add(address);
    return { address, label: target.label.trim() };
  });
}
