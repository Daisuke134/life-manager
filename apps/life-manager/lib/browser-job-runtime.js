"use strict";

const {
  claimBrowserJob,
  appendBrowserTrace,
  finishBrowserJob,
} = require("./browser-job-store.js");
const { runGenericBrowserTask } = require("./generic-browser-task.js");
const { evaluateBrowserPrincipal } = require("./browser-principal-policy.js");
const { makeStagehandSteelDriver } = require("./stagehand-steel-driver.js");
const { createOpportunity } = require("./money-printer-opportunity.js");
const { sendMessage, sendPhoto } = require("./telegram.js");
let defaultDriver = null;

async function cardExtractedRoles(job, result, deps) {
  if (!deps.opportunityStore || !Array.isArray(result.extracted_roles) || !result.selected_url) return;
  const nowIso = new Date(deps.nowMs || Date.now()).toISOString();
  for (const [index, role] of result.extracted_roles.entries()) {
    if (!role || typeof role.title !== "string" || !role.title.trim()) continue;
    const sourceUrl = new URL(result.selected_url);
    sourceUrl.searchParams.set("lm_role", String(index));
    try {
      await createOpportunity({
        tenantId: job.uid,
        sourceUrl: sourceUrl.toString(),
        title: role.title,
        goalStatement: role.description && role.description.trim() ? role.description : role.title,
        valueMinor: 0,
        currency: "USD",
        observedAt: nowIso,
      }, deps.opportunityStore);
    } catch (error) {
      console.error(`[browser-job] find-work card failed job=${job.id} role=${index} ${String(error && error.message || error)}`);
    }
  }
}

function driverFor(deps) {
  if (deps.driver) return deps.driver;
  const makeDriver = deps.makeDriver || makeStagehandSteelDriver;
  const created = () => makeDriver({
    apiKey: deps.geminiKey || process.env.GEMINI_API_KEY,
    agentEmail: deps.agentEmail || process.env.LM_AGENT_BROWSER_EMAIL,
    agentName: deps.agentName || process.env.LM_AGENT_BROWSER_NAME,
  });
  if (deps.makeDriver) return created();
  if (!defaultDriver) defaultDriver = created();
  return defaultDriver;
}

async function runNextBrowserJob(deps = {}) {
  const heldDriver = deps.driver || (!deps.makeDriver && defaultDriver);
  if (heldDriver && typeof heldDriver.hasHeldSession === "function" && heldDriver.hasHeldSession()) {
    if (typeof heldDriver.releaseExpiredSessions === "function") {
      await heldDriver.releaseExpiredSessions();
    }
    if (heldDriver.hasHeldSession()) return { status: "handoff_waiting" };
  }
  const claim = deps.claimJob || (() => claimBrowserJob(deps));
  const job = await claim();
  if (!job) return { status: "idle" };
  const append = deps.appendTrace || ((id, stage, meta) => appendBrowserTrace(id, stage, meta, deps));
  const finish = deps.finishJob || ((id, result) => finishBrowserJob(id, result, deps));
  const principal = evaluateBrowserPrincipal(job);
  if (!principal.allowed) {
    const terminal = {
      trace_id: job.id,
      status: principal.status,
      reason: principal.reason,
      external_effect: principal.external_effect,
      provider_receipt: {
        confirmed: false,
        status: principal.reason,
        confirmation_id: null,
        current_url: null,
        handoff_required: false,
        handoff_reason: null,
      },
      session_id: null,
      telegram_message_id: null,
    };
    await append(job.id, "principal_excluded", { reason: principal.reason });
    await finish(job.id, terminal);
    return terminal;
  }
  const driver = driverFor(deps);
  const send = deps.sendMessage || sendMessage;
  const sendEvidence = deps.sendPhoto || sendPhoto;
  const telegramToken = deps.telegramToken || process.env.LM_TELEGRAM_BOT_TOKEN;
  const result = await runGenericBrowserTask(job, {
    appendTrace: append,
    openSession: driver.openSession.bind(driver),
    discoverAndAct: driver.discoverAndAct.bind(driver),
    readProviderReceipt: driver.readProviderReceipt.bind(driver),
    captureEvidence: driver.captureEvidence.bind(driver),
    releaseSession: driver.releaseSession.bind(driver),
    sendTelegram: (chatId, text) => send(telegramToken, chatId, text),
    sendTelegramEvidence: (chatId, evidence, caption) =>
      sendEvidence(telegramToken, chatId, evidence.bytes, caption),
    finishJob: finish,
  });
  await cardExtractedRoles(job, result, deps);
  return result;
}

async function completeBrowserHandoff(sessionId, answer, deps = {}) {
  void sessionId;
  void answer;
  void deps;
  throw new Error("browser human handoff disabled");
}

function startBrowserJobLoop(options = {}) {
  const enabled = options.enabled === true;
  const intervalMs = Number.isInteger(options.intervalMs) ? options.intervalMs : 2_000;
  const setTimeoutImpl = options.setTimeoutImpl || setTimeout;
  const clearTimeoutImpl = options.clearTimeoutImpl || clearTimeout;
  const runOnce = options.runOnce || (() => runNextBrowserJob(options));
  let timer = null;
  let running = false;
  let closed = false;

  const runNow = async () => {
    if (!enabled || closed) return { status: "disabled" };
    if (running) return { status: "overlap_skipped" };
    running = true;
    try {
      return await runOnce();
    } catch (error) {
      console.error(`[browser-job] ${String(error && error.message || error)}`);
      return { status: "error" };
    } finally {
      running = false;
    }
  };

  const schedule = () => {
    if (!enabled || closed) return;
    timer = setTimeoutImpl(async () => {
      await runNow();
      schedule();
    }, intervalMs);
  };
  schedule();
  return {
    enabled,
    runNow,
    close() {
      closed = true;
      if (timer != null) clearTimeoutImpl(timer);
    },
  };
}

module.exports = {
  completeBrowserHandoff,
  runNextBrowserJob,
  startBrowserJobLoop,
};
