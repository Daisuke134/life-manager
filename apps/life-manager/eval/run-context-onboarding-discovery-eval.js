"use strict";

const fs = require("node:fs");
const path = require("node:path");
const {
  askTick,
  handleAskCallback,
} = require("../lib/ask.js");
const { parseUpdate, routeCallbackData, answerCallbackQuery } = require("../lib/telegram.js");
const { computeStage, sendStage, onboardNudgeAll } = require("../lib/telegram-onboard.js");
const { backfillCalendarContext } = require("../lib/context-graph.js");
const { runDiscoveryForUser, DISCOVERY_WEEK_MS } = require("../lib/feature-discovery.js");
const { processLocationLateNotice, upsertLiveLocation } = require("../lib/late-notice.js");

const DATASET = path.join(__dirname, "context-onboarding-discovery-cases.jsonl");
const MIGRATION = path.join(__dirname, "../migrations/2026-07-22-core8f-context-provenance.sql");
const NOW = Date.parse("2026-07-21T00:00:00.000Z");

function response(status, body = null) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => typeof body === "string" ? body : JSON.stringify(body),
  };
}

function createPostgrestTelegramFixture() {
  const state = {
    asks: [{
      uid: "unrelated-user", event_id: "unrelated-event", semantic_key: "calendar_online:unrelated",
      question_type: "calendar_online", answer_value: "offline", answer_source: "telegram_callback",
      answer_provenance: { kind: "telegram_callback" }, answered_at: "2026-07-20T00:00:00.000Z",
    }],
    locations: [{
      uid: "unrelated-user", latitude: 1, longitude: 2, telegram_message_id: "other",
      observed_at: "2026-07-20T00:00:00.000Z", expires_at: "2026-07-23T00:00:00.000Z",
      source: "telegram_live_location",
    }],
    telegramMessages: [],
    callbackAnswers: [],
    contextReads: 0,
    nextMessageId: 8100,
  };

  const selectRows = (rows, url) => {
    const uid = url.searchParams.get("uid");
    const eventId = url.searchParams.get("event_id");
    const replyToken = url.searchParams.get("reply_token");
    return rows.filter((row) => (!uid || uid === `eq.${row.uid}`) &&
      (!eventId || eventId === `eq.${row.event_id}`) &&
      (!replyToken || replyToken === `eq.${row.reply_token}`));
  };

  async function fetchImpl(input, init = {}) {
    const url = new URL(String(input));
    const method = String(init.method || "GET").toUpperCase();
    if (url.hostname === "api.telegram.org") {
      const body = JSON.parse(init.body || "{}");
      if (/\/sendMessage$/.test(url.pathname)) {
        const message = { ...body, message_id: state.nextMessageId++ };
        state.telegramMessages.push(message);
        return response(200, { ok: true, result: message });
      }
      if (/\/answerCallbackQuery$/.test(url.pathname)) {
        state.callbackAnswers.push(body);
        return response(200, { ok: true, result: true });
      }
      return response(404, { ok: false });
    }

    if (url.pathname.endsWith("/rest/v1/lm_ask_log")) {
      if (method === "GET") {
        state.contextReads++;
        return response(200, selectRows(state.asks, url).map((row) => ({ ...row })));
      }
      if (method === "POST") {
        const row = JSON.parse(init.body || "{}");
        const duplicate = state.asks.some((existing) => existing.uid === row.uid &&
          (existing.event_id === row.event_id || (row.semantic_key && existing.semantic_key === row.semantic_key)));
        if (duplicate) return response(409, { code: "23505" });
        state.asks.push({ ...row });
        return response(201, null);
      }
      if (method === "PATCH") {
        const patch = JSON.parse(init.body || "{}");
        const rows = selectRows(state.asks, url).filter((row) =>
          url.searchParams.get("answered_at") !== "is.null" || !row.answered_at);
        rows.forEach((row) => Object.assign(row, patch));
        return /return=representation/.test(String((init.headers || {}).Prefer || ""))
          ? response(200, rows.map((row) => ({ ...row }))) : response(204, null);
      }
      if (method === "DELETE") {
        const doomed = new Set(selectRows(state.asks, url));
        state.asks = state.asks.filter((row) => !doomed.has(row));
        return response(204, null);
      }
    }

    if (url.pathname.endsWith("/rest/v1/lm_user_locations") && method === "POST") {
      const row = JSON.parse(init.body || "{}");
      state.locations = state.locations.filter((existing) => existing.uid !== row.uid);
      state.locations.push({ ...row });
      return response(201, null);
    }
    return response(404, []);
  }

  return { state, fetchImpl };
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
}

function satisfies(actual, expected) {
  if (expected && typeof expected === "object" && !Array.isArray(expected)) {
    return Object.keys(expected).every((key) => satisfies(actual && actual[key], expected[key]));
  }
  return JSON.stringify(stable(actual)) === JSON.stringify(stable(expected));
}

function forbiddenRealtimeQuestion(text) {
  return /^(?:出た|もう出た|まだ|まだ出ていない|まだ出てない)[？?]$/u.test(String(text || "").trim());
}

async function evaluateJourney() {
  const fixture = createPostgrestTelegramFixture();
  const { state, fetchImpl } = fixture;
  const unrelatedBefore = JSON.parse(JSON.stringify({
    asks: state.asks.filter((row) => row.uid === "unrelated-user"),
    locations: state.locations.filter((row) => row.uid === "unrelated-user"),
  }));
  const originalFetch = global.fetch;
  global.fetch = fetchImpl;
  try {
    const onboardingMessages = [];
    const stage = await sendStage("tg-token", "100", null, "https://aniccaai.com", {
      sendMessage: async (_token, _chatId, text, extra) => {
        onboardingMessages.push({ text, extra });
        return { ok: true };
      },
    });
    let contextWrites = 0;
    await backfillCalendarContext("new-user", {
      geminiKey: "gemini", supaUrl: "https://fixture.invalid", supaKey: "service",
      calendar: { ready: () => true, listEventsRaw: async () => [] },
      remember: async () => { contextWrites++; return true; }, log: () => {},
    });

    const existingOnboardingMessages = [];
    await onboardNudgeAll({
      token: "tg-token", base: "https://aniccaai.com", supaUrl: "https://fixture.invalid", supaKey: "service",
      linkedRows: async () => [{
        uid: "u1", telegram_chat_id: "100", name: "Existing", calendar_provider: "composio_gcal",
        phone: "+810000000000", paid: true, gmail_account_id: "mail-1", gmail_skipped: false,
        tg_onboard_stage: "done",
      }],
      sendStage: async (...args) => existingOnboardingMessages.push(args),
      backfillCalendarContext: async () => { throw new Error("done user must not repeat context onboarding"); },
      setStage: async () => { throw new Error("done user must not repeat stage persistence"); },
    });

    const event = {
      id: "event-core8f-1", recurringEventId: "series-core8f", summary: "田中さんMTG",
      start: { dateTime: "2026-07-22T15:00:00+09:00" },
    };
    const unresolvedGemini = async (body) => body.tools && body.tools[0] && body.tools[0].google_search
      ? { candidates: [{ content: { parts: [{ text: "No reliable venue." }] } }] }
      : { candidates: [{ content: { parts: [{ functionCall: { name: "submit_candidate", args: {
        found: false, candidate: "", source: "web_search",
      } } }] } }] };
    const askOptions = {
      composioKey: "calendar", supaUrl: "https://fixture.invalid", supaKey: "service",
      geminiKey: "gemini", nowMs: NOW, telegramChatId: "100", telegramToken: "tg-token",
      fetchImpl, listEvents: async () => [event], recall: async () => null,
      resolve: async () => ({ kind: "ask" }), geminiRaw: unresolvedGemini,
      mail: { ready: () => false, searchInbox: async () => { throw new Error("mail must stay off"); } },
    };
    const beforeAsk = state.telegramMessages.length;
    await askTick("u1", askOptions);
    const firstAskMessages = state.telegramMessages.slice(beforeAsk);
    const questionMessage = firstAskMessages[0] || {};
    const buttons = (((questionMessage.reply_markup || {}).inline_keyboard || [])[0] || []);

    let callbackResult = { ignored: true };
    const callbackData = buttons[0] && buttons[0].callback_data;
    if (callbackData) {
      const parsed = parseUpdate({ callback_query: {
        id: "callback-core8f", from: { id: 100 }, data: callbackData,
        message: { message_id: questionMessage.message_id, chat: { id: 100 } },
      } });
      await answerCallbackQuery("tg-token", parsed.callbackQueryId, "Received");
      callbackResult = await routeCallbackData(parsed.data, { ask: (data) => handleAskCallback(data, {
        uid: "u1", chatId: parsed.chatId, actorId: parsed.userId, messageId: parsed.messageId,
        callbackQueryId: parsed.callbackQueryId, telegramToken: "tg-token",
        supaUrl: "https://fixture.invalid", supaKey: "service", fetchImpl,
      }) });
    }
    const answerRow = state.asks.find((row) => row.uid === "u1" && row.answer_value);
    const beforeUnauthorizedCallbacks = JSON.stringify(stable(state.asks));
    if (callbackData) {
      await handleAskCallback(callbackData, {
        uid: "u1", chatId: "100", actorId: "100", telegramToken: "tg-token",
        supaUrl: "https://fixture.invalid", supaKey: "service", fetchImpl,
      });
      await handleAskCallback(callbackData, {
        uid: "unrelated-user", chatId: "999", actorId: "999", telegramToken: "tg-token",
        supaUrl: "https://fixture.invalid", supaKey: "service", fetchImpl,
      });
    }
    const unauthorizedMutations = JSON.stringify(stable(state.asks)) === beforeUnauthorizedCallbacks ? 0 : 1;

    const beforeRepeat = state.telegramMessages.length;
    await askTick("u1", askOptions);
    const afterRepeat = state.telegramMessages.length;
    await askTick("u1", {
      ...askOptions,
      listEvents: async () => [{ ...event, id: "event-core8f-2", start: { dateTime: "2026-07-29T15:00:00+09:00" } }],
    });
    const afterSeries = state.telegramMessages.length;

    const discoveryMessages = [];
    let savedDiscovery = null;
    const lockedUser = {
      uid: "u1", telegram_chat_id: "100", notifications_enabled: true,
      last_discovery_at: null, last_discovery_gate: null, payout_destination: null,
    };
    const discovery = await runDiscoveryForUser(lockedUser, NOW, {
      token: "tg-token", getLiveLocation: async () => null,
      sendMessage: async (_token, _chat, text, extra) => {
        discoveryMessages.push({ text, extra }); return { ok: true };
      },
      saveDiscovery: async (_uid, at, gate) => { savedDiscovery = { at, gate }; return true; },
    });
    let lateActions = 0;
    await processLocationLateNotice({
      user: { uid: "u1", telegram_chat_id: "100" }, location: null, nowMs: NOW,
      events: [{ id: "late-1", summary: "予定", location: "会場", startMs: NOW + 60_000 }],
    }, {
      routeMinutes: async () => { lateActions++; return 10; },
      claimEvent: async () => { lateActions++; return true; },
      sendLateNotice: async () => { lateActions++; return { sent: true }; },
      sendMessage: async () => { lateActions++; return { ok: true }; },
    });
    const throttledMessages = [];
    const throttled = await runDiscoveryForUser({
      ...lockedUser, last_discovery_at: new Date(savedDiscovery.at).toISOString(), last_discovery_gate: savedDiscovery.gate,
    }, NOW + DISCOVERY_WEEK_MS - 1, {
      getLiveLocation: async () => { throw new Error("throttled discovery must not inspect gates"); },
      sendMessage: async (...args) => { throttledMessages.push(args); return { ok: true }; },
    });

    const locationUpdate = parseUpdate({ edited_message: {
      message_id: 7001, date: Math.floor(NOW / 1000), edit_date: Math.floor((NOW + 1_000) / 1000),
      chat: { id: 100 }, from: { id: 100 },
      location: { latitude: 35.0, longitude: 139.0, live_period: 86_400 },
    } });
    const persistedLocation = await upsertLiveLocation("u1", locationUpdate, {
      supaUrl: "https://fixture.invalid", supaKey: "service", fetchImpl, nowMs: NOW + 2_000,
    });
    const locationRow = state.locations.find((row) => row.uid === "u1") || {};

    const unlockedMessages = [];
    await runDiscoveryForUser({
      ...lockedUser, payout_destination: { type: "wallet", address: "fixture" }, last_discovery_at: null,
    }, NOW + 2_000, {
      getLiveLocation: async () => locationRow,
      sendMessage: async (_token, _chat, text, extra) => {
        unlockedMessages.push({ text, extra }); return { ok: true };
      },
    });

    const allMessages = onboardingMessages.concat(firstAskMessages, discoveryMessages, unlockedMessages);
    const forbiddenCount = allMessages.filter((message) => forbiddenRealtimeQuestion(message.text)).length;
    const locationDiscoveryMessages = unlockedMessages.filter((message) =>
      JSON.stringify(message.extra || {}).includes("discovery:how:location")).length;
    const unrelatedAfter = {
      asks: state.asks.filter((row) => row.uid === "unrelated-user"),
      locations: state.locations.filter((row) => row.uid === "unrelated-user"),
    };

    let migration = "";
    if (fs.existsSync(MIGRATION)) migration = fs.readFileSync(MIGRATION, "utf8");
    const actual = {
      "new-user-no-fabricated-context": { stage: stage || computeStage(null), contextWrites },
      "existing-user-no-repeat-onboarding": {
        onboardingMessages: existingOnboardingMessages.length,
        contextRowsRead: state.contextReads > 0,
      },
      "ambiguous-calendar-closed-question": {
        messageCount: firstAskMessages.length, text: questionMessage.text || "",
        inline: buttons.length > 0, choiceCount: buttons.length,
        choiceLabels: buttons.map((button) => button.text),
      },
      "telegram-callback-typed-provenance": {
        handled: callbackResult && callbackResult.ok === true,
        callbackReceiptCount: state.callbackAnswers.length,
        questionType: answerRow && answerRow.question_type,
        answerValue: answerRow && answerRow.answer_value,
        answerSource: answerRow && answerRow.answer_source,
        typedProvenance: Boolean(answerRow && answerRow.answer_provenance &&
          answerRow.answer_provenance.kind === "telegram_callback" && answerRow.semantic_key),
      },
      "same-event-repeat-dedup": { additionalQuestions: afterRepeat - beforeRepeat },
      "later-series-semantic-dedup": { additionalQuestions: afterSeries - afterRepeat },
      "location-locked-due": {
        discoveryMessages: discoveryMessages.length, gate: discovery.gate,
        lateActions, forbiddenRealtimeQuestions: forbiddenCount,
      },
      "location-locked-throttled": { discoveryMessages: throttledMessages.length, reason: throttled.reason },
      "location-update-provenance": {
        persisted: persistedLocation, source: locationRow.source,
        telegramMessageId: locationRow.telegram_message_id,
      },
      "location-unlocked": { locationDiscoveryMessages, forbiddenRealtimeQuestions: forbiddenCount },
      "unrelated-tenant-unchanged": {
        unchanged: JSON.stringify(stable(unrelatedBefore)) === JSON.stringify(stable(unrelatedAfter)),
        unauthorizedMutations,
      },
      "additive-provenance-schema": {
        exists: Boolean(migration), additive: !/\b(?:DROP|TRUNCATE)\b/i.test(migration),
        tenantKeyed: /uid\s*,\s*semantic_key/i.test(migration),
        semanticUnique: /UNIQUE[\s\S]*uid\s*,\s*semantic_key|CREATE UNIQUE INDEX[\s\S]*uid\s*,\s*semantic_key/i.test(migration),
        rls: /ENABLE ROW LEVEL SECURITY/i.test(migration),
      },
    };

    const cases = fs.readFileSync(DATASET, "utf8").trim().split("\n").map(JSON.parse);
    const results = cases.map((testCase) => ({
      id: testCase.id,
      expected: testCase.expected,
      actual: actual[testCase.id],
      pass: satisfies(actual[testCase.id], testCase.expected),
    }));
    return { total: results.length, passed: results.filter((item) => item.pass).length, results };
  } finally {
    global.fetch = originalFetch;
  }
}

async function main() {
  const outcome = await evaluateJourney();
  const score = (outcome.passed / outcome.total * 100).toFixed(1);
  console.log(`Context/onboarding/discovery eval: ${outcome.passed}/${outcome.total} (${score}%) judge=deterministic`);
  for (const failure of outcome.results.filter((item) => !item.pass)) {
    console.log(`FAIL ${failure.id}: expected=${JSON.stringify(failure.expected)} actual=${JSON.stringify(failure.actual)}`);
  }
  process.exitCode = outcome.passed === outcome.total ? 0 : 1;
}

if (require.main === module) main().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });

module.exports = { evaluateJourney, satisfies };
