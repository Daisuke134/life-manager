"use strict";

const crypto = require("node:crypto");
const DEFAULT_ACTION_TIMEOUT_MS = 420_000;

function providerReceipt(value) {
  return {
    confirmed: value && value.confirmed === true,
    status: String((value && value.status) || "unknown").slice(0, 100),
    confirmation_id: value && value.confirmationId ? String(value.confirmationId).slice(0, 200) : null,
    current_url: value && value.currentUrl ? String(value.currentUrl).slice(0, 1000) : null,
    handoff_required: value && value.handoffRequired === true,
    handoff_reason: value && value.handoffReason ? String(value.handoffReason).slice(0, 100) : null,
  };
}

function authTraceMeta(release, outcome) {
  const meta = {};
  if (release && typeof release.origin === "string" && release.origin) {
    meta.origin = release.origin.slice(0, 1000);
  }
  if (release && ["agent_owned", "user_provided"].includes(release.principal_kind)) {
    meta.principal_kind = release.principal_kind;
  }
  const value = release && release[`auth_context_${outcome}`];
  if (typeof value === "boolean") meta[outcome] = value;
  if (outcome === "saved") {
    if (release && /^[a-f0-9]{64}$/.test(String(release.context_sha256 || ""))) {
      meta.context_sha256 = release.context_sha256;
    }
    if (release && Number.isSafeInteger(release.key_version) && release.key_version > 0) {
      meta.key_version = release.key_version;
    }
  }
  return meta;
}

function withTimeout(promise, timeoutMs, label) {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) return promise;
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      const error = new Error(`${label} timed out`);
      error.code = "BROWSER_TIMEOUT";
      reject(error);
    }, timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function telegramText(result) {
  if (result.status === "completed") {
    return `✅ Browser task completed\nSite: ${result.selected_url}\nProvider: ${result.provider_receipt.status}\nTrace: ${result.trace_id}`;
  }
  if (result.status === "possibly_completed") {
    return `⚠️ The browser action may have completed, but provider confirmation was not independently readable.\nTrace: ${result.trace_id}`;
  }
  if (result.status === "handoff_required") {
    return `🖐️ Browser task needs a human-only step (${result.provider_receipt.handoff_reason || "provider gate"}).\nTrace: ${result.trace_id}`;
  }
  return `❌ Browser task did not complete before any confirmed side effect.\nTrace: ${result.trace_id}`;
}

async function runGenericBrowserTask(job, deps) {
  if (!job || !job.id || !job.uid || !job.telegram_chat_id || !job.goal) {
    throw new Error("browser job invalid");
  }
  for (const name of [
    "appendTrace",
    "openSession",
    "discoverAndAct",
    "readProviderReceipt",
    "captureEvidence",
    "releaseSession",
    "sendTelegram",
    "sendTelegramEvidence",
    "finishJob",
  ]) {
    if (!deps || typeof deps[name] !== "function") throw new Error(`browser dependency missing: ${name}`);
  }

  const result = {
    trace_id: job.id,
    status: "failed",
    session_id: null,
    selected_url: null,
    selected_origin: null,
    selection_reason: null,
    action: null,
    provider_receipt: providerReceipt(null),
    telegram_message_id: null,
    evidence_message_id: null,
    evidence_sha256: null,
    steel_released: false,
    auth_marker_hash: job.auth_marker_hash || null,
    extracted_roles: null,
  };
  let session = null;
  let evidence = null;
  let sideEffectStarted = false;
  let selectedRecorded = false;
  let actionStartedRecorded = false;
  const actionTimeoutMs = Number(deps.actionTimeoutMs || DEFAULT_ACTION_TIMEOUT_MS);

  await deps.appendTrace(job.id, "claimed", {});
  try {
    session = await deps.openSession({
      uid: job.uid,
      ownerId: job.id,
      goal: job.goal,
      requiresLogin: job.requires_login === true,
      principalKind: job.principal_kind,
    });
    result.session_id = String(session.id);
    await deps.appendTrace(job.id, "discovery", { session_id: result.session_id });

    const recordSelected = async (selected = {}) => {
      result.selected_url = selected.selectedUrl ? String(selected.selectedUrl) : result.selected_url;
      result.selected_origin = selected.selectedOrigin ? String(selected.selectedOrigin) : result.selected_origin;
      result.selection_reason = selected.selectionReason
        ? String(selected.selectionReason).slice(0, 500)
        : result.selection_reason;
      if (!selectedRecorded) {
        selectedRecorded = true;
        await deps.appendTrace(job.id, "selected", {
          url: result.selected_url,
          origin: result.selected_origin,
          reason: result.selection_reason,
        });
      }
    };
    const recordActionStarted = async (started = {}) => {
      sideEffectStarted = true;
      result.action = started.action ? String(started.action).slice(0, 500) : result.action;
      if (!actionStartedRecorded) {
        actionStartedRecorded = true;
        await deps.appendTrace(job.id, "action_started", { action: result.action });
      }
    };
    const action = await withTimeout(deps.discoverAndAct(session, {
      goal: job.goal,
      locale: job.locale,
      uid: job.uid,
      actionKind: job.action_kind,
      onSelected: recordSelected,
      onActionStarted: recordActionStarted,
    }), actionTimeoutMs, "browser action");
    sideEffectStarted = action && action.sideEffectStarted === true;
    result.extracted_roles = action && Array.isArray(action.extractedRoles) ? action.extractedRoles : null;
    await recordSelected(action);
    result.action = action && action.action ? String(action.action).slice(0, 500) : null;
    if (sideEffectStarted) await recordActionStarted(action);
    await deps.appendTrace(job.id, "action_observed", { action: result.action });

    result.provider_receipt = providerReceipt(await deps.readProviderReceipt(session, action));
    await deps.appendTrace(job.id, "provider_readback", result.provider_receipt);
    try {
      evidence = await deps.captureEvidence(session);
      if (evidence && evidence.bytes) {
        result.evidence_sha256 = crypto.createHash("sha256").update(evidence.bytes).digest("hex");
      }
    } catch {
      evidence = null;
      result.evidence_sha256 = null;
    }
    result.status = result.provider_receipt.handoff_required
      ? "handoff_required"
      : result.provider_receipt.confirmed
        ? "completed"
        : "possibly_completed";
  } catch (error) {
    sideEffectStarted = sideEffectStarted || Boolean(error && error.sideEffectStarted);
    result.status = sideEffectStarted ? "possibly_completed" : "failed";
    console.error(
      `[browser-task] job=${job.id} side_effect_started=${sideEffectStarted} error=${String(error && error.message || error).slice(0, 500)}`,
    );
    if (session && sideEffectStarted) {
      try {
        evidence = await deps.captureEvidence(session);
        if (evidence && evidence.bytes) {
          result.evidence_sha256 = crypto.createHash("sha256").update(evidence.bytes).digest("hex");
        }
      } catch {
        evidence = null;
        result.evidence_sha256 = null;
      }
    }
  }

  try {
    const sent = await deps.sendTelegram(job.telegram_chat_id, telegramText(result));
    const messageId = sent && sent.ok === true && sent.result && sent.result.message_id;
    result.telegram_message_id = Number.isSafeInteger(messageId) && messageId > 0
      ? String(messageId)
      : null;
    await deps.appendTrace(job.id, "telegram_sent", { message_id: result.telegram_message_id });
  } catch {
    result.telegram_message_id = null;
  }

  if (evidence && evidence.bytes) {
    try {
      const sent = await deps.sendTelegramEvidence(
        job.telegram_chat_id,
        evidence,
        `Cloud browser provider screen\nTrace: ${result.trace_id}`,
      );
      const messageId = sent && sent.ok === true && sent.result && sent.result.message_id;
      result.evidence_message_id = Number.isSafeInteger(messageId) && messageId > 0
        ? String(messageId)
        : null;
    } catch {
      result.evidence_message_id = null;
    }
    await deps.appendTrace(job.id, "evidence_sent", {
      message_id: result.evidence_message_id,
      sha256: result.evidence_sha256,
    });
  }

  if (session && session.id && !result.provider_receipt.handoff_required) {
    try {
      const release = await deps.releaseSession(session.id, {
        providerReceipt: result.provider_receipt,
      });
      result.steel_released = Boolean(release && release.released);
      if (release && typeof release.auth_context_loaded === "boolean") {
        await deps.appendTrace(job.id, "auth_context_loaded", authTraceMeta(release, "loaded"));
      }
      if (result.provider_receipt.handoff_reason === "login"
        && release && typeof release.auth_context_invalidated === "boolean") {
        await deps.appendTrace(
          job.id,
          "auth_context_invalidated",
          authTraceMeta(release, "invalidated"),
        );
      } else if (release && typeof release.auth_context_saved === "boolean") {
        await deps.appendTrace(job.id, "auth_context_saved", authTraceMeta(release, "saved"));
      }
    } catch {
      result.steel_released = false;
    } finally {
      await deps.appendTrace(job.id, "steel_released", {
        session_id: result.session_id,
        released: result.steel_released,
      });
    }
  }
  await deps.finishJob(job.id, result);
  return result;
}

module.exports = { runGenericBrowserTask, DEFAULT_ACTION_TIMEOUT_MS };
