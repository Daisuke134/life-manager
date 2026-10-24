"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.resolve(__dirname, "../../..");
function install(...args) {
  return spawnSync("bash", [path.join(root, "install.sh"), ...args], {
    cwd: root, encoding: "utf8", env: { ...process.env, TELEGRAM_BOT_TOKEN: "", TELEGRAM_CHAT_ID: "" },
  });
}

test("list exposes every catalog product and the remaining missing local installers without effects", () => {
  const result = install("list");
  assert.equal(result.status, 0, result.stderr);
  const plan = JSON.parse(result.stdout);
  assert.equal(plan.loops.length, 18);
  assert.equal(plan.loops.filter((loop) => loop.command === null).length, 8);
  assert.equal(plan.starts_automatically, false);
  assert.deepEqual(plan.external_effects, []);
  assert.equal(plan.loops.find((loop) => loop.id === "gig-coconala").command[1], "coconala");
  assert.deepEqual(plan.loops.find((loop) => loop.id === "gig-lancers").command, ["./install.sh", "lancers"]);
  assert.deepEqual(plan.loops.find((loop) => loop.id === "gig-crowdworks").command, ["./install.sh", "crowdworks"]);
});

test("plan --all uses catalog IDs while retaining individual requirement gates", () => {
  const result = install("plan", "--all");
  assert.equal(result.status, 0, result.stderr);
  const plan = JSON.parse(result.stdout);
  assert.equal(plan.selected_loop_ids.length, 18);
  assert.ok(plan.loops.find((loop) => loop.id === "capafy").missing.includes("host_adapter"));
});

test("all cannot silently override a selected product", () => {
  const result = install("plan", "--all", "--loop", "connector");
  assert.notEqual(result.status, 0);
});
