import { test } from "node:test";
import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { loadOrCreateAgentWallet, readTargets, SERVICE } from "./wallet.mjs";
import { append, openIntent, readRows, seenSourceSignature } from "./journal.mjs";

async function tempRoot() {
  return mkdtemp(path.join(os.tmpdir(), "sol-copy-wallet-journal-"));
}

test("wallet creates once, preserves credentials, and returns no private key", async () => {
  const root = await tempRoot();
  const ssot = path.join(root, "anicca", "credentials.json");
  const first = await loadOrCreateAgentWallet(ssot);
  const second = await loadOrCreateAgentWallet(ssot);

  assert.equal(first.publicKey, second.publicKey);
  assert.equal(typeof first.signTransaction, "function");
  assert.equal("secretKey" in first, false);
  assert.equal((await stat(path.dirname(ssot))).mode & 0o777, 0o700);
  assert.equal((await stat(ssot)).mode & 0o777, 0o600);
  const stored = JSON.parse(await readFile(ssot, "utf8"));
  assert.equal(stored.credentials.filter((row) => row.service === SERVICE).length, 1);
});

test("wallet preserves an unrelated credential row", async () => {
  const root = await tempRoot();
  const ssot = path.join(root, "anicca", "credentials.json");
  await mkdir(path.dirname(ssot), { recursive: true, mode: 0o700 });
  await writeFile(ssot, JSON.stringify({ credentials: [{ service: "other", username: "kept" }] }));
  await chmod(path.dirname(ssot), 0o700);
  await chmod(ssot, 0o600);

  await loadOrCreateAgentWallet(ssot);

  const stored = JSON.parse(await readFile(ssot, "utf8"));
  assert.deepEqual(stored.credentials.find((row) => row.service === "other"), {
    service: "other",
    username: "kept",
  });
});

test("targets accept public addresses and reject private material", async () => {
  const root = await tempRoot();
  const config = path.join(root, "targets.json");
  await writeFile(config, JSON.stringify({ targets: [{ address: "11111111111111111111111111111111", label: "system" }] }));

  assert.deepEqual(await readTargets(config), [{ address: "11111111111111111111111111111111", label: "system" }]);

  await writeFile(config, JSON.stringify({ targets: [{ address: "11111111111111111111111111111111", private_key: "never" }] }));
  await assert.rejects(readTargets(config), /public.only|private/i);
});

test("journal records intent before effect and resolves open intent by receipt", async () => {
  const root = await tempRoot();
  const journal = path.join(root, "state", "journal.jsonl");

  await append(journal, { kind: "intent", intentId: "i1", sourceSignature: "sig-1" });
  assert.equal((await openIntent(journal)).length, 1);
  await append(journal, { kind: "receipt", intentId: "i1", status: "paper" });

  assert.deepEqual((await readRows(journal)).map((row) => row.kind), ["intent", "receipt"]);
  assert.equal((await openIntent(journal)).length, 0);
});

test("journal deduplicates a source signature across wakes", async () => {
  const root = await tempRoot();
  const journal = path.join(root, "state", "journal.jsonl");

  assert.equal(await seenSourceSignature(journal, "sig-1"), false);
  await append(journal, { kind: "scout", sourceSignature: "sig-1" });
  assert.equal(await seenSourceSignature(journal, "sig-1"), true);
  assert.equal(await seenSourceSignature(journal, "sig-2"), false);
});
