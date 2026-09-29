// inngest/functions.js — six Inngest durable functions replacing in-process setInterval loops.
//
// Architecture (per the verified Inngest 2-arg API):
//   sweep-wake   cron `* * * * *`       → list all paid users → fan-out lm/wake.user per user
//   wake-user    event lm/wake.user     → re-fetch user by uid → wakeUserOnce(u, nowMs)   — concurrency per uid
//   sweep-travel cron `*/30 * * * *`    → fan-out lm/travel.user per user
//   travel-user  event lm/travel.user   → re-fetch user by uid → travelUserOnce(u)        — concurrency per uid
//   sweep-ask    cron `*/20 * * * *`    → fan-out lm/ask.user per user
//   ask-user     event lm/ask.user      → re-fetch user by uid → askUserOnce(u)           — concurrency per uid
//
// SINGLE-WRITER: when LIFE_RUN_LOOPS is unset or not "false", the in-process loops own the writes
// and the Inngest sweeper handlers return a no-op immediately (they never call sendEvent).
// When LIFE_RUN_LOOPS="false", the in-process loops are OFF and the sweepers do the fan-out.
// All 6 functions remain registered so Inngest cloud always sees the manifest.
//
// PII PROTECTION: sweepers fan-out ONLY { uid } (not the full user row with phone/tokens).
// Per-user functions re-fetch the full row via getUserByUid before calling the per-user fn.
//
// Factory functions (makeSweep*Handler / make*UserHandler) accept injected deps as parameters
// so tests can inject stubs without touching real Supabase/Telnyx/Maps.
// The exported `functions` array wires the real implementations from scheduler.js.
"use strict";

const { inngest } = require("./client.js");
const {
  wakeUserOnce,
  travelUserOnce,
  askUserOnce,
  listPaidUsers,
  getUserByUid,
} = require("../scheduler.js");
const { inProcessLoopsOn } = require("../lib/maybe-start-loops.js");
const { runInvestmentDryRun } = require("../lib/investment-dry-run.js");
const { createProductionCloudRuntimeDispatcher } = require("../lib/cloud-runtime-dispatcher.js");

// ── Single-writer guard ───────────────────────────────────────────────────────
// The startup module owns this predicate. Sweepers no-op whenever in-process loops own writes,
// including the standalone fallback used when neither Inngest nor an explicit role is present.

// ── Handler factories (testable with injected stubs) ──────────────────────────

/**
 * makeSweepWakeHandler(listUsers, { getEnv }) → async ({step}) => void
 *
 * When the in-process loops are ON (LIFE_RUN_LOOPS unset/"true"), returns a no-op immediately
 * (no sendEvent) so the Inngest sweeper never double-writes with the in-process loop.
 * When loops are OFF (LIFE_RUN_LOOPS="false"), fans out one { uid } event per user.
 *
 * @param {Function} listUsers   async () => Array<{uid,...}>
 * @param {{ getEnv?: () => object }} [opts]
 */
function makeSweepWakeHandler(listUsers, opts) {
  const getEnv = (opts && opts.getEnv) || (() => process.env);
  return async ({ step }) => {
    if (inProcessLoopsOn(getEnv())) return; // single-writer: in-process loops own it
    const users = await step.run("list", listUsers);
    if (!users || !users.length) return; // FIND-103: no users → no empty fan-out
    await step.sendEvent(
      "fan",
      users.map((u) => ({ name: "lm/wake.user", data: { uid: u.uid } }))
    );
  };
}

/**
 * makeSweepTravelHandler(listUsers, opts) → async ({step}) => void
 */
function makeSweepTravelHandler(listUsers, opts) {
  const getEnv = (opts && opts.getEnv) || (() => process.env);
  return async ({ step }) => {
    if (inProcessLoopsOn(getEnv())) return;
    const users = await step.run("list", listUsers);
    if (!users || !users.length) return; // FIND-103: no users → no empty fan-out
    await step.sendEvent(
      "fan",
      users.map((u) => ({ name: "lm/travel.user", data: { uid: u.uid } }))
    );
  };
}

/**
 * makeSweepAskHandler(listUsers, opts) → async ({step}) => void
 */
function makeSweepAskHandler(listUsers, opts) {
  const getEnv = (opts && opts.getEnv) || (() => process.env);
  return async ({ step }) => {
    if (inProcessLoopsOn(getEnv())) return;
    const users = await step.run("list", listUsers);
    if (!users || !users.length) return; // FIND-103: no users → no empty fan-out
    await step.sendEvent(
      "fan",
      users.map((u) => ({ name: "lm/ask.user", data: { uid: u.uid } }))
    );
  };
}

/**
 * makeWakeUserHandler(wakeOnce, getUser) → async ({event, step}) => void
 *
 * Re-fetches the full user row by uid (FIND-004 PII) before calling wakeOnce.
 * If uid is unknown (getUserByUid returns null) → no-op, no throw.
 *
 * @param {Function} wakeOnce  async (u, nowMs) => void
 * @param {Function} getUser   async (uid) => user|null
 */
function makeWakeUserHandler(wakeOnce, getUser) {
  return async ({ event, step }) => {
    const uid = event.data && event.data.uid;
    if (!uid) return;
    const u = await step.run("fetch", () => (getUser || getUserByUid)(uid));
    if (!u) return;
    // FIND-102: memoize the timestamp in its own step so an Inngest retry reuses the ORIGINAL
    // handler time (Date.now() inside the side-effecting step would drift on replay).
    const nowMs = await step.run("now", () => Date.now());
    await step.run("wake", () => wakeOnce(u, nowMs));
  };
}

/**
 * makeTravelUserHandler(travelOnce, getUser) → async ({event, step}) => void
 */
function makeTravelUserHandler(travelOnce, getUser) {
  return async ({ event, step }) => {
    const uid = event.data && event.data.uid;
    if (!uid) return;
    const u = await step.run("fetch", () => (getUser || getUserByUid)(uid));
    if (!u) return;
    await step.run("travel", () => travelOnce(u));
  };
}

/**
 * makeAskUserHandler(askOnce, getUser) → async ({event, step}) => void
 */
function makeAskUserHandler(askOnce, getUser) {
  return async ({ event, step }) => {
    const uid = event.data && event.data.uid;
    if (!uid) return;
    const u = await step.run("fetch", () => (getUser || getUserByUid)(uid));
    if (!u) return;
    await step.run("ask", () => askOnce(u));
  };
}

function makeInvestmentDryRunHandler(runOnce = runInvestmentDryRun) {
  return async ({ step }) => step.run("investment-dry-run", () => runOnce());
}

function makeCloudJobHandler(dispatch) {
  if (typeof dispatch !== "function") throw new Error("cloud job dispatcher unavailable");
  return async ({ event, step }) => {
    const data = event && event.data;
    return step.run("dispatch-cloud-job", () => dispatch(data));
  };
}

let productionCloudDispatcher;
function dispatchProductionCloudJob(data) {
  if (!productionCloudDispatcher) {
    productionCloudDispatcher = createProductionCloudRuntimeDispatcher();
  }
  return productionCloudDispatcher.dispatch(data);
}

// ── Wired Inngest functions (real scheduler.js per-user fns) ──────────────────

const sweepWake = inngest.createFunction(
  {
    id: "sweep-wake",
    triggers: [{ cron: "* * * * *" }],
  },
  makeSweepWakeHandler(listPaidUsers)
);

const wakeUser = inngest.createFunction(
  {
    id: "wake-user",
    triggers: [{ event: "lm/wake.user" }],
    concurrency: { key: "event.data.uid", limit: 1 },
  },
  makeWakeUserHandler(wakeUserOnce, getUserByUid)
);

const sweepTravel = inngest.createFunction(
  {
    id: "sweep-travel",
    triggers: [{ cron: "*/30 * * * *" }],
  },
  makeSweepTravelHandler(listPaidUsers)
);

const travelUser = inngest.createFunction(
  {
    id: "travel-user",
    triggers: [{ event: "lm/travel.user" }],
    concurrency: { key: "event.data.uid", limit: 1 },
  },
  makeTravelUserHandler(travelUserOnce, getUserByUid)
);

const sweepAsk = inngest.createFunction(
  {
    id: "sweep-ask",
    triggers: [{ cron: "*/20 * * * *" }],
  },
  makeSweepAskHandler(listPaidUsers)
);

const askUser = inngest.createFunction(
  {
    id: "ask-user",
    triggers: [{ event: "lm/ask.user" }],
    concurrency: { key: "event.data.uid", limit: 1 },
  },
  makeAskUserHandler(askUserOnce, getUserByUid)
);

const investmentCloudDryRun = inngest.createFunction(
  { id: "investment-cloud-dry-run", triggers: [{ cron: "*/5 * * * *" }] },
  makeInvestmentDryRunHandler()
);

const cloudJob = inngest.createFunction(
  {
    id: "cloud-job",
    triggers: [{ event: "lm/cloud.job" }],
    concurrency: { key: "event.data.tenant_id", limit: 1 },
  },
  makeCloudJobHandler(dispatchProductionCloudJob),
);

const functions = [
  sweepWake,
  wakeUser,
  sweepTravel,
  travelUser,
  sweepAsk,
  askUser,
  investmentCloudDryRun,
  cloudJob,
];

module.exports = {
  functions,
  // exported factory functions for test injection
  makeSweepWakeHandler,
  makeSweepTravelHandler,
  makeSweepAskHandler,
  makeWakeUserHandler,
  makeTravelUserHandler,
  makeAskUserHandler,
  makeInvestmentDryRunHandler,
  makeCloudJobHandler,
  // exported for tests
  inProcessLoopsOn,
};
