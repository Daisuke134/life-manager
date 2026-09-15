"use strict";

const net = require("node:net");
const { z } = require("zod");
const { makeSteelCdpClient, STEEL_BASE_URL } = require("./steel-cdp-client.js");
const {
  BROWSER_AUTH_CONTEXT_EXPIRED_CODE,
  scopeSessionContextToOrigin,
  readBrowserAuthSession: defaultReadBrowserAuthSession,
  upsertBrowserAuthSession: defaultUpsertBrowserAuthSession,
  invalidateBrowserAuthSession: defaultInvalidateBrowserAuthSession,
} = require("./browser-auth-session-store.js");
const {
  assertBrowserSessionEndpoint,
  normalizeBrowserEndpoint,
} = require("../../../runtime/browser/session-contract.cjs");

const MODEL = "google/gemini-2.5-flash";
const AGENT_MODEL = "google/gemini-2.5-computer-use-preview-10-2025";
const AGENT_SYSTEM_PROMPT = "Operate the remote cloud browser carefully. Use only truthful supplied identity data, never invent personal data, and stop at login, CAPTCHA, 2FA, KYC, or payment.";
const SEARCH_URL = "https://www.google.com/";
const selectionSchema = z.object({
  selectedSiteName: z.string(),
  selectionReason: z.string(),
  isSpecificActionPage: z.boolean(),
});

const actionSchema = z.object({
  actionSummary: z.string(),
});

const receiptSchema = z.object({
  confirmed: z.boolean(),
  status: z.string(),
  confirmationId: z.string().nullable(),
  providerText: z.string(),
  activeRegistrationForm: z.boolean().optional(),
  activeAuthenticationForm: z.boolean().optional(),
});

const listingSchema = z.object({
  roles: z.array(z.object({
    title: z.string(),
    description: z.string(),
    pay: z.string(),
  })),
});

function pageUrl(page) {
  if (!page) return "";
  if (typeof page.url === "function") return String(page.url());
  return String(page.url || "");
}

function replaceIdentity(value, agentEmail) {
  const text = String(value || "");
  if (!agentEmail) return text;
  return text.split(agentEmail).join("the agent-owned email");
}

function publicPageUrl(page, agentEmail) {
  const raw = replaceIdentity(pageUrl(page), agentEmail);
  try {
    const parsed = new URL(raw);
    parsed.username = "";
    parsed.password = "";
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return "";
  }
}

function isSpecificActionUrl(value) {
  try {
    const url = new URL(value);
    if (/^(?:www\.)?(?:google|bing)\./i.test(url.hostname)) return false;
    if (/^\/(?:d\/|search(?:\/|$)|discover(?:\/|$)|events?\/?$)/i.test(url.pathname)) return false;
    return url.pathname.split("/").filter(Boolean).length >= 1;
  } catch {
    return false;
  }
}

function explicitPublicHttpsUrl(goal) {
  const match = String(goal || "").match(/https?:\/\/[^\s<>"']+/i);
  if (!match) return null;
  const raw = match[0].replace(/[),.;!?]+$/, "");
  return publicHttpsUrl(raw).toString();
}

function publicHttpsUrl(raw, options = {}) {
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("runtime target must be a public HTTPS URL");
  }
  const host = url.hostname.toLowerCase();
  const unbracketedHost = host.startsWith("[") && host.endsWith("]")
    ? host.slice(1, -1)
    : host;
  if (
    url.protocol !== "https:" ||
    !host ||
    (options.rejectCredentials === true && (url.username || url.password)) ||
    host === "localhost" ||
    host.endsWith(".local") ||
    host.endsWith(".internal") ||
    net.isIP(unbracketedHost) !== 0
  ) {
    throw new Error("runtime target must be a public HTTPS URL");
  }
  url.username = "";
  url.password = "";
  url.hash = "";
  return url;
}

function safeProtectedMarker(value, agentEmail) {
  const marker = replaceIdentity(value, agentEmail).trim();
  if (
    marker.length < 2 ||
    marker.length > 80 ||
    /[\u0000-\u001f\u007f]/.test(marker) ||
    /https?:\/\/|www\.|@|(?:token|cookie|password|secret|session|authorization)\s*[:=]/i.test(marker)
  ) {
    return null;
  }
  return marker;
}

function collectReadOnlyDomSnapshot(input = {}, environment) {
  const documentRef = environment && environment.document || document;
  const getStyle = environment && environment.getComputedStyle
    ? environment.getComputedStyle
    : window.getComputedStyle.bind(window);
  const visible = (element) => {
    if (!element) return false;
    const style = getStyle(element);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      Number.parseFloat(style.opacity) === 0
    ) {
      return false;
    }
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const visibleMatches = (selector) =>
    Array.from(documentRef.querySelectorAll(selector)).slice(0, 100).some(visible);
  const bodyText = String(documentRef.body && documentRef.body.innerText || "").slice(0, 20_000);
  const formText = Array.from(documentRef.querySelectorAll("form"))
    .slice(0, 50)
    .filter(visible)
    .map((form) => String(form.innerText || "").slice(0, 1_000))
    .join(" ");
  const visibleText = `${bodyText} ${formText}`;
  const inputs = Array.from(documentRef.querySelectorAll("input"))
    .slice(0, 100)
    .filter(visible)
    .map((element) => ({
      type: String(element.type || "").toLowerCase().slice(0, 20),
      inputMode: String(element.inputMode || "").toLowerCase().slice(0, 20),
      autocomplete: String(element.autocomplete || "").toLowerCase().slice(0, 40),
      maxLength: Number.isInteger(element.maxLength)
        ? Math.max(-1, Math.min(element.maxLength, 100))
        : -1,
    }));
  const authActionVisible = Array.from(documentRef.querySelectorAll(
    'button, a[href], [role="button"], input[type="submit"], input[type="button"], form[action]',
  ))
    .slice(0, 100)
    .filter(visible)
    .some((element) => {
      const attribute = (name) => {
        try {
          return String(element.getAttribute?.(name) || "");
        } catch {
          return "";
        }
      };
      const labelCandidates = Array.from(new Set([
        element.innerText,
        attribute("aria-label"),
        attribute("title"),
        ["submit", "button"].includes(String(element.type || "").toLowerCase())
          ? element.value
          : "",
      ].map((value) => String(value || "").replace(/\s+/g, " ").trim())
        .filter(Boolean)));
      const destination = [
        attribute("href"),
        attribute("action"),
        element.href,
        element.action,
      ].filter(Boolean).join(" ");
      const loginDestination =
        /(?:^|\/)(?:login|log-in|signin|sign-in)(?:[/?#]|$)/i.test(destination);
      const exactAuthAction = labelCandidates.some((candidate) =>
        !/\b(?:security|settings)\b/i.test(candidate) &&
        /^(?:(?:sign\s*in|log\s*in|login)(?:\s+with\s+(?:google|apple|microsoft|github|facebook|sso|email))?|continue\s+with\s+(?:google|apple|microsoft|github|facebook|sso|email)|email\s+me\s+(?:a\s+)?(?:link|magic\s+link)|magic\s+link|send\s+(?:me\s+)?(?:a\s+)?(?:code|magic\s+link|sign[- ]?in\s+link))$/i.test(
          candidate,
        ));
      return loginDestination || exactAuthAction;
    });
  const protectedActionVisible = Array.from(documentRef.querySelectorAll(
    'button, a[href], [role="button"], input[type="submit"], input[type="button"]',
  ))
    .slice(0, 100)
    .filter(visible)
    .some((element) => {
      const label = String(
        element.innerText ||
        element.getAttribute?.("aria-label") ||
        element.value ||
        "",
      ).replace(/\s+/g, " ").trim();
      return /^(?:(?:create|new|add|manage|edit)\s+[a-z0-9][a-z0-9 &_-]{0,60}|dashboard|account|profile|settings|my\s+[a-z0-9][a-z0-9 &_-]{0,60}|sign out|log out|ログアウト)$/i.test(
        label,
      );
    });
  return {
    inputs,
    authActionVisible,
    protectedActionVisible,
    textFlags: {
      auth: /\b(?:log\s*in|sign\s*in|authenticate|authentication required)\b/i.test(visibleText),
      otp: /\b(?:verification code|security code|one[- ]time code|otp|enter (?:the )?(?:(?:six|6)[- ]digit )?code|(?:six|6)[- ]digit code)\b/i.test(visibleText),
      captcha: visibleMatches(
        'iframe[src*="captcha" i], [class*="captcha" i], [id*="captcha" i], [data-sitekey]',
      ) || /\bcaptcha\b/i.test(visibleText),
      challenge: /\b(?:security challenge|verify you are human|challenge required)\b/i.test(visibleText),
      kyc: /\b(?:kyc|identity verification|verify your identity)\b/i.test(visibleText),
      payment: /\b(?:payment required|checkout|credit card|card details|billing details)\b/i.test(visibleText),
    },
    markerPresent: bodyText.toLocaleLowerCase().includes(
      String(input.marker || "").toLocaleLowerCase(),
    ),
  };
}

function classifyReadOnlyDomSnapshot(snapshot = {}) {
  const source = snapshot && typeof snapshot === "object" ? snapshot : {};
  const inputs = Array.isArray(source.inputs) ? source.inputs.slice(0, 100) : [];
  const flags = typeof source.textFlags === "object" && source.textFlags
    ? source.textFlags
    : {};
  const passwordVisible = inputs.some((input) => input && input.type === "password");
  const emailVisible = inputs.some((input) =>
    input &&
    (input.type === "email" ||
      input.autocomplete === "email" ||
      input.autocomplete === "username"));
  const oneTimeCodeVisible = inputs.some((input) =>
    input && input.autocomplete === "one-time-code");
  const singleDigitInputs = inputs.filter((input) =>
    input &&
    input.type === "text" &&
    input.inputMode === "numeric" &&
    input.maxLength === 1).length;
  const otpVisible = oneTimeCodeVisible ||
    (singleDigitInputs >= 4 && flags.otp === true) ||
    flags.otp === true;
  const captchaVisible = flags.captcha === true;
  return {
    passwordVisible,
    otpVisible,
    authVisible: passwordVisible || otpVisible ||
      source.authActionVisible === true ||
      (flags.auth === true && emailVisible),
    challengeVisible: captchaVisible || flags.challenge === true,
    captchaVisible,
    kycVisible: flags.kyc === true,
    paymentVisible: flags.payment === true,
    markerPresent: source.markerPresent === true,
    protectedActionVisible: source.protectedActionVisible === true,
  };
}

function privateSession(session, endpoint, allowPublicEndpoint = false) {
  try {
    assertBrowserSessionEndpoint(session, endpoint, { allowPublicEndpoint });
  } catch {
    throw new Error(
      "Stagehand requires a Railway-private Steel CDP session on the configured private endpoint",
    );
  }
  return session;
}

function websocketBase(endpoint) {
  const parsed = new URL(endpoint);
  parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
  return `${parsed.protocol}//${parsed.host}/`;
}

function cdpHeaders(endpoint) {
  const parsed = new URL(endpoint);
  return parsed.hostname.endsWith(".railway.internal")
    ? { Host: `localhost:${parsed.port || (parsed.protocol === "https:" ? "443" : "80")}` }
    : undefined;
}

function makeStagehandSteelDriver(options = {}) {
  const steelClient = options.steelClient || makeSteelCdpClient();
  const allowPublicEndpoint = options.allowPublicEndpoint === true
    || process.env.LIFE_MANAGER_BROWSER_ALLOW_PUBLIC_ENDPOINT === "1";
  const steelEndpoint = normalizeBrowserEndpoint(
    steelClient.baseUrl || STEEL_BASE_URL,
    { allowPublicEndpoint },
  );
  const steelWebsocketBase = websocketBase(steelEndpoint);
  const steelCdpHeaders = cdpHeaders(steelEndpoint);
  const Stagehand = options.Stagehand || require("@browserbasehq/stagehand").Stagehand;
  const apiKey = String(options.apiKey || process.env.GEMINI_API_KEY || "").trim();
  const agentEmail = String(options.agentEmail || process.env.LM_AGENT_BROWSER_EMAIL || "").trim();
  const agentName = String(options.agentName || process.env.LM_AGENT_BROWSER_NAME || "").trim();
  if (!apiKey) throw new Error("Stagehand Gemini API key unavailable");
  const readBrowserAuthSession = options.readBrowserAuthSession || defaultReadBrowserAuthSession;
  const upsertBrowserAuthSession = options.upsertBrowserAuthSession || defaultUpsertBrowserAuthSession;
  const invalidateBrowserAuthSession =
    options.invalidateBrowserAuthSession || defaultInvalidateBrowserAuthSession;
  const now = typeof options.now === "function" ? options.now : Date.now;
  const sessions = new Map();
  const authSessions = new Map();

  return {
    hasHeldSession() { return sessions.size > 0; },
    async releaseExpiredSessions() {
      let released = 0;
      for (const [id, open] of [...sessions]) {
        if (!open || !Number.isFinite(open.heldAt) || open.heldAt + 10 * 60 * 1000 > now()) continue;
        await this.releaseSession(id, { providerReceipt: { handoffReason: "expired" } });
        released += 1;
      }
      return released;
    },
    async readHeldReceipt(sessionId) {
      const id = String(sessionId || "");
      if (!sessions.has(id)) throw new Error("Stagehand handoff session unavailable");
      return this.readProviderReceipt({
        id,
        websocketUrl: steelWebsocketBase,
      });
    },
    async openSession(input = {}) {
      let auth = null;
      let context;
      if (input && input.requiresLogin === true) {
        const explicitUrl = explicitPublicHttpsUrl(input.goal);
        if (explicitUrl) {
          const identity = {
            uid: input.uid,
            origin: new URL(explicitUrl).origin,
            principalKind: input.principalKind,
          };
          try {
            const record = await readBrowserAuthSession(identity);
            auth = {
              ...identity,
              loaded: Boolean(record),
              invalidationAttempted: false,
              invalidated: false,
            };
            if (record) context = scopeSessionContextToOrigin(record.context, identity.origin);
          } catch (error) {
            if (!error || error.code !== BROWSER_AUTH_CONTEXT_EXPIRED_CODE) throw error;
            auth = {
              ...identity,
              loaded: false,
              invalidationAttempted: true,
              invalidated: await invalidateBrowserAuthSession(identity) === true,
            };
          }
        }
      }
      const createOptions = { blockAds: true };
      if (context !== undefined) createOptions.sessionContext = context;
      const created = await steelClient.createRawSession(createOptions);
      let session;
      try {
        session = privateSession(created, steelEndpoint, allowPublicEndpoint);
      } catch (error) {
        if (created && created.id) {
          try { await steelClient.releaseSession(String(created.id)); } catch { /* preserve validation */ }
        }
        throw error;
      }
      if (auth) authSessions.set(String(session.id), auth);
      return session;
    },

    async discoverAndAct(sessionInput, context = {}) {
      const session = privateSession(sessionInput, steelEndpoint, allowPublicEndpoint);
      const goal = String(context.goal || "").trim();
      if (!goal) throw new Error("generic browser goal unavailable");
      const stagehand = new Stagehand({
        env: "LOCAL",
        disablePino: true,
        verbose: 0,
        localBrowserLaunchOptions: {
          cdpUrl: session.websocketUrl,
          ...(steelCdpHeaders ? { cdpHeaders: steelCdpHeaders } : {}),
        },
        model: {
          modelName: MODEL,
          apiKey,
        },
      });
      await stagehand.init();
      const page = await stagehand.context.awaitActivePage();
      sessions.set(String(session.id), { stagehand, page, heldAt: now() });
      await page.goto(SEARCH_URL);
      const explicitUrl = explicitPublicHttpsUrl(goal);
      const readOnlyAuth = Boolean(
        explicitUrl && context.actionKind === "browser_auth_continuity_readback",
      );
      const listRoles = Boolean(explicitUrl && context.actionKind === "explore_listings");

      const discoveryTask = [
        "Search the live web for websites that can satisfy this delegated goal:",
        goal,
        "Compare at least two relevant live websites before selecting one.",
        "The selected website must come from this run's web discovery; do not assume a preconfigured site.",
        "Navigate to the best matching provider page, but do not perform or submit the requested action yet.",
      ].join("\n");
      let executionStarted = false;
      try {
        const discoveryAgent = explicitUrl ? null : stagehand.agent({
            model: MODEL,
            executionModel: MODEL,
          });
        const actionAgent = readOnlyAuth || listRoles ? null : stagehand.agent({
            mode: "cua",
            model: AGENT_MODEL,
            systemPrompt: AGENT_SYSTEM_PROMPT,
          });
        if (explicitUrl) await page.goto(explicitUrl);
        else await discoveryAgent.execute(discoveryTask);
        if (listRoles) {
          const selectedUrl = publicPageUrl(page, agentEmail);
          if (!selectedUrl) throw new Error("browser listing readback carried no public page");
          const selected = {
            selectedUrl,
            selectedOrigin: new URL(selectedUrl).origin,
            selectionReason: "Explicit explore-listings URL.",
          };
          if (typeof context.onSelected === "function") await context.onSelected(selected);
          const listing = await stagehand.extract(
            "List the paid roles or job listings currently visible on this page. For each, return its title, a short description, and its pay if shown (empty string if not shown). Do not log in, register, or submit anything.",
            listingSchema,
          );
          const extractedRoles = (listing.roles || []).slice(0, 20).map((role) => ({
            title: replaceIdentity(role.title, agentEmail).slice(0, 300),
            description: replaceIdentity(role.description, agentEmail).slice(0, 2000),
            pay: replaceIdentity(role.pay || "", agentEmail).slice(0, 100),
          }));
          return {
            ...selected,
            action: `Listed ${extractedRoles.length} roles.`,
            sideEffectStarted: false,
            extractedRoles,
          };
        }
        let selection;
        let selectedUrl;
        if (readOnlyAuth) {
          selectedUrl = publicPageUrl(page, agentEmail);
          if (!selectedUrl) throw new Error("browser auth readback carried no public page");
          selection = {
            selectionReason: "Explicit authenticated provider readback URL.",
          };
        } else {
          for (let attempt = 0; attempt < 3; attempt += 1) {
            selection = await stagehand.extract(
              "From the current page and browsing path, identify the selected site and explain why it matched the delegated goal. Set isSpecificActionPage=true only if this is one specific event/provider detail page where the requested action can be started; search results, directories, category pages, maps, and home pages are false.",
              selectionSchema,
            );
            selectedUrl = publicPageUrl(page, agentEmail);
            if (selection.isSpecificActionPage === true && isSpecificActionUrl(selectedUrl)) break;
            if (explicitUrl || attempt === 2) {
              throw new Error("browser discovery did not reach a specific action page");
            }
            await discoveryAgent.execute([
              "You are still on a search, directory, category, or listing page.",
              "Open one specific candidate's provider detail/action page now.",
              "Do not submit, register, purchase, or perform the requested external action yet.",
            ].join("\n"));
          }
        }
        const parsed = new URL(selectedUrl);
        const selected = {
          selectedUrl,
          selectedOrigin: parsed.origin,
          selectionReason: replaceIdentity(selection.selectionReason, agentEmail).slice(0, 500),
        };
        if (typeof context.onSelected === "function") await context.onSelected(selected);
        if (readOnlyAuth) {
          return {
            ...selected,
            action: "Read current authenticated provider page.",
            sideEffectStarted: false,
            readOnlyAuth: true,
            readOnlyExpectedOrigin: new URL(explicitUrl).origin,
          };
        }

        const actionTask = [
          "On the currently selected provider page, perform exactly one explicit, zero-cost, non-binding external action inside this delegated goal:",
          goal,
          "Do not search for or switch to another provider.",
          "Do not spend money, accept paid terms, enter a contract, make a legal attestation, perform KYC, bypass a login/challenge/CAPTCHA/2FA,",
          "or invent any personal value or factual claim. Stop honestly if any of those are required.",
          "After the action, remain on the provider page that displays its result.",
          agentEmail
            ? `When the goal refers to the agent-owned email, use this exact runtime-only address: ${agentEmail}`
            : "If the goal requires an email address, stop because no agent-owned address is available.",
          agentName
            ? `When a name is required for the agent-owned identity, use this exact runtime-only name: ${agentName}`
            : "If the goal requires a name, stop because no agent-owned name is available.",
          agentName
            ? `When a required company or organization field refers to the agent-owned identity, use: ${agentName}`
            : "If a company or organization is required, stop because none is available.",
          "When a required role or job title refers to the agent-owned identity, use: AI agent",
          "Leave optional social-profile fields blank.",
          "Decline optional marketing or data-sharing consent. If the form requires consent and offers no decline/no choice, stop honestly.",
        ].join("\n");
        executionStarted = true;
        if (typeof context.onActionStarted === "function") {
          await context.onActionStarted({ action: "one delegated zero-cost browser action" });
        }
        await actionAgent.execute(actionTask);
        if (explicitUrl) await page.waitForTimeout(15_000);
        const observation = await stagehand.extract(
          "Summarize the single delegated action attempted on the current provider page. Do not claim it succeeded.",
          actionSchema,
        );
        return {
          ...selected,
          action: replaceIdentity(observation.actionSummary, agentEmail).slice(0, 500),
          sideEffectStarted: true,
        };
      } catch (error) {
        const failure = error instanceof Error ? error : new Error(String(error));
        failure.sideEffectStarted = executionStarted;
        throw failure;
      }
    },

    async readProviderReceipt(sessionInput, action = {}) {
      const session = privateSession(sessionInput, steelEndpoint, allowPublicEndpoint);
      const open = sessions.get(String(session.id));
      const restoredAuth = authSessions.get(String(session.id));
      if (!open) throw new Error("Stagehand session unavailable for provider readback");
      if (action && Array.isArray(action.extractedRoles)) {
        return {
          confirmed: true,
          status: "listed",
          confirmationId: null,
          currentUrl: publicPageUrl(open.page, agentEmail),
          handoffRequired: false,
          handoffReason: null,
        };
      }
      const readOnlyAuth = action && action.readOnlyAuth === true;
      const extracted = await open.stagehand.extract(
        readOnlyAuth
          ? [
              "Read only the current authenticated provider continuity page.",
              "Report confirmed=true only when provider-authored account or protected content is visible and no login, verification-code, OTP, or 2FA form is active.",
              "Do not require registration, booking, purchase, or other action-success language for this read-only authentication check.",
              "Set activeAuthenticationForm=true when any login or authentication form is active.",
              "Return its authentication status and, as providerText, copy one exact contiguous visible phrase of 2-80 characters from the page.",
              "Do not summarize, combine, prefix, suffix, or paraphrase that visible phrase.",
            ].join(" ")
          : [
              "Read only the current provider-authored result page.",
              "Report confirmed=true only when the page explicitly says the requested action succeeded.",
              "Set activeRegistrationForm=true only when a visible registration form can still be submitted.",
              "Set activeAuthenticationForm=true only when a visible login, verification-code, OTP, or 2FA form is active.",
              "An Add to Calendar completion control with no active registration/authentication form may coexist with optional email verification used only to manage an already-completed registration.",
              "A pending, check-email, error, login, challenge, payment, active registration form, or active authentication form is otherwise not confirmed.",
              "Return its status, confirmation identifier if present, and copy a short exact provider-authored status phrase. Do not infer success from the attempted action.",
            ].join(" "),
        receiptSchema,
      );
      const status = replaceIdentity(extracted.status || "unknown", agentEmail).slice(0, 100);
      const providerText = replaceIdentity(extracted.providerText, agentEmail).slice(0, 500);
      const handoffText = `${status} ${providerText}`;
      const activeRegistrationForm = extracted.activeRegistrationForm === true;
      const activeAuthenticationForm = extracted.activeAuthenticationForm === true;
      const explicitSuccess = /\b(?:you(?:'|’)re in|registration confirmed|registered|booking confirmed|rsvp confirmed|success)\b/i.test(
        providerText,
      );
      const terminalActionCompletion = [
        /\b(?:booking|appointment|reservation)\s+confirmed\b/i,
        /\b(?:message|inquiry|request)\s+(?:sent|received)\b/i,
        /\breceived your (?:inquiry|application|submission|request)\b/i,
        /\b(?:application|submission)\s+(?:submitted|received)\b/i,
        /\bthank you for (?:contacting|your (?:inquiry|application|submission))\b/i,
      ].some((pattern) => pattern.test(providerText));
      const managementCompletion = /\badd to calendar\b/i.test(handoffText)
        && /\bverify email\b/i.test(handoffText)
        && !activeRegistrationForm
        && !activeAuthenticationForm;
      const strongCompletion = explicitSuccess || terminalActionCompletion || managementCompletion;
      const hardFailure = /\b(?:failed|error|not confirmed|not sent|not submitted|not received|unsuccessful|rejected|declined)\b|失敗|未完了/i.test(
        handoffText,
      );
      const pendingWithoutCompletion = /\bpending\b/i.test(handoffText) && !strongCompletion;
      const negated = hardFailure || pendingWithoutCompletion;
      const blockingVerification = !strongCompletion &&
        /\b(?:verify|check(?:\s+your)?\s+email|email\s+verification(?:\s+required)?|confirm\s+your\s+email)\b|確認してください/i.test(
          handoffText,
        );
      const handoffReason = activeAuthenticationForm
        ? /\b(?:2fa|two-factor|one-time password|otp|verification code)\b/i.test(handoffText)
          ? "2fa"
          : "login"
        : activeRegistrationForm
          ? "registration"
        : /\b(?:captcha|challenge)\b/i.test(handoffText)
        ? "challenge"
        : /\b(?:2fa|two-factor|one-time password|otp)\b/i.test(handoffText)
          ? "2fa"
          : /\bkyc\b|identity verification/i.test(handoffText)
            ? "kyc"
            : /\b(?:payment|purchase|checkout|credit card|card details|billing)\b|支払|決済|購入/i.test(handoffText)
              ? "payment"
              : /\b(?:login|log in|sign in)\b/i.test(handoffText)
              ? "login"
                : null;
      if (readOnlyAuth) {
        const marker = safeProtectedMarker(extracted.providerText, agentEmail);
        let finalUrl = null;
        try {
          finalUrl = publicHttpsUrl(pageUrl(open.page), { rejectCredentials: true });
        } catch {
          // An unsafe final page can never prove authenticated continuity.
        }
        const expectedOrigin = String(action.readOnlyExpectedOrigin || "");
        const originMatches = Boolean(
          finalUrl && expectedOrigin && finalUrl.origin === expectedOrigin,
        );
        let dom = null;
        if (finalUrl && originMatches && marker) {
          try {
            dom = await open.page.evaluate(collectReadOnlyDomSnapshot, { marker });
          } catch {
            dom = null;
          }
        }
        const signals = classifyReadOnlyDomSnapshot(dom);
        const loginPath = Boolean(finalUrl && /\/(?:login|log-in|signin|sign-in)(?:\/|$)/i.test(
          finalUrl.pathname,
        ));
        const independentReason = signals.paymentVisible
          ? "payment"
          : signals.kycVisible
            ? "kyc"
            : signals.challengeVisible || signals.captchaVisible
              ? "challenge"
              : signals.otpVisible
                ? "2fa"
                : signals.passwordVisible || signals.authVisible || loginPath
                  ? "login"
                  : null;
        const passiveLoginCopy =
          handoffReason === "login" &&
          activeAuthenticationForm !== true &&
          independentReason === null &&
          originMatches &&
          Boolean(marker) &&
          signals.markerPresent &&
          !negated &&
          !blockingVerification;
        const modelHandoffReason = passiveLoginCopy ? null : handoffReason;
        const independentProtectedContent =
          independentReason === null &&
          originMatches &&
          Boolean(marker) &&
          signals.markerPresent &&
          !negated &&
          !blockingVerification;
        const restoredProtectedContent =
          restoredAuth && restoredAuth.loaded === true &&
          independentReason === null &&
          originMatches &&
          signals.protectedActionVisible &&
          !negated &&
          !blockingVerification;
        const modelConfirmed =
          extracted.confirmed === true ||
          passiveLoginCopy ||
          independentProtectedContent ||
          restoredProtectedContent;
        const readOnlyReason = modelHandoffReason || independentReason ||
          (!originMatches ||
          (!(marker && signals.markerPresent) && !restoredProtectedContent) ||
          !modelConfirmed
            ? "login"
            : null);
        const confirmed = readOnlyReason === null;
        return {
          confirmed,
          status: confirmed
            ? "authenticated"
            : `${readOnlyReason || "login"}_required`,
          confirmationId: null,
          currentUrl: finalUrl && originMatches ? publicPageUrl(open.page, agentEmail) : null,
          handoffRequired: readOnlyReason !== null,
          handoffReason: readOnlyReason,
        };
      }
      return {
        confirmed: (extracted.confirmed === true || strongCompletion) &&
          !negated &&
          !blockingVerification &&
          !activeRegistrationForm &&
          !activeAuthenticationForm &&
          providerText.length > 0,
        status,
        confirmationId: extracted.confirmationId ? String(extracted.confirmationId).slice(0, 200) : null,
        currentUrl: publicPageUrl(open.page, agentEmail),
        handoffRequired: handoffReason != null,
        handoffReason,
      };
    },

    async captureEvidence(sessionInput) {
      const session = privateSession(sessionInput, steelEndpoint, allowPublicEndpoint);
      const open = sessions.get(String(session.id));
      if (!open) throw new Error("Stagehand session unavailable for evidence capture");
      return {
        mimeType: "image/png",
        bytes: await open.page.screenshot({ type: "png", fullPage: false }),
      };
    },

    async releaseSession(sessionId, releaseOptions = {}) {
      const id = String(sessionId || "");
      const open = sessions.get(id);
      const auth = authSessions.get(id);
      sessions.delete(id);
      authSessions.delete(id);

      let authContextSaved = false;
      let authContextInvalidated = false;
      let contextSha256 = null;
      let keyVersion = null;
      if (auth) {
        const providerReceipt = releaseOptions && releaseOptions.providerReceipt || {};
        const handoffReason = String(
          providerReceipt.handoff_reason || providerReceipt.handoffReason || "",
        ).toLowerCase();
        try {
          if (handoffReason === "login") {
            authContextInvalidated = auth.invalidationAttempted === true
              ? auth.invalidated === true
              : await invalidateBrowserAuthSession({
                uid: auth.uid,
                origin: auth.origin,
                principalKind: auth.principalKind,
              }) === true;
          } else {
            const context = scopeSessionContextToOrigin(
              await steelClient.getSessionContext(id),
              auth.origin,
            );
            const saved = await upsertBrowserAuthSession({
              uid: auth.uid,
              origin: auth.origin,
              principalKind: auth.principalKind,
              context,
            });
            authContextSaved = true;
            if (saved && /^[a-f0-9]{64}$/.test(String(saved.context_sha256 || ""))) {
              contextSha256 = saved.context_sha256;
            }
            if (saved && Number.isSafeInteger(saved.key_version) && saved.key_version > 0) {
              keyVersion = saved.key_version;
            }
          }
        } catch {
          authContextSaved = false;
          authContextInvalidated = false;
          contextSha256 = null;
          keyVersion = null;
        }
      }

      if (open && open.stagehand && typeof open.stagehand.close === "function") {
        try { await open.stagehand.close(); } catch { /* Steel release below owns the real slot */ }
      }
      const released = await steelClient.releaseSession(id);
      const receipt = { released: released === true };
      if (!auth) return receipt;
      return {
        ...receipt,
        origin: auth.origin,
        principal_kind: auth.principalKind,
        auth_context_loaded: auth.loaded,
        auth_context_saved: authContextSaved,
        auth_context_invalidated: authContextInvalidated,
        context_sha256: contextSha256,
        key_version: keyVersion,
      };
    },
  };
}

module.exports = {
  classifyReadOnlyDomSnapshot,
  collectReadOnlyDomSnapshot,
  makeStagehandSteelDriver,
  MODEL,
  AGENT_MODEL,
  SEARCH_URL,
};
