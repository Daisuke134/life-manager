"use strict";
// lib/steel-cdp-client.js — the self-hosted steel-browser rail (§10.0 裁定12).
//
// steel-browser runs as a SEPARATE Railway service in the same project as life-call. The OSS build
// ships no API auth, so it has NO public domain: it is reachable only over Railway private
// networking at steel-browser.railway.internal:8080. Nothing in this module may ever accept a
// public base URL by default.
//
// ─── ROUTES (verified against source, not memory) ────────────────────────────────────────────────
// steel-dev/steel-browser, api/src/steel-browser-plugin.ts:81
//     await fastify.register(sessionsRoutes, { prefix: "/v1" });
// steel-dev/steel-browser, api/src/modules/sessions/sessions.routes.ts
//     GET  /health                    → { status: "ok" } | 503 { status: "service_unavailable" }
//     POST /sessions                  → SessionDetails
//     GET  /sessions/:sessionId       → SessionDetails
//     POST /sessions/:sessionId/release → ReleaseSession
//     POST /sessions/release          → ReleaseSession   (release ALL)
// There is NO `DELETE /v1/sessions`: release is a POST. SessionDetails (sessions.schema.ts) carries
// `id`, `status` ∈ idle|live|released|failed, and `websocketUrl` — the CDP endpoint we connect to.
//
// ─── ONE SESSION AT A TIME ──────────────────────────────────────────────────────────────────────
// The OSS build holds a single activeSession, so every booking job must create a fresh session, use
// it, and release it. The executor's `finally` does the releasing; this module makes release cheap
// and also tears down the CDP socket, because a live socket against a released session is the same
// leak by another name.

const { validateSessionContext } = require("./browser-auth-session-store.js");
const {
  DEFAULT_STEEL_ENDPOINT,
  assertBrowserSessionEndpoint,
  createBrowserSessionConfig,
  normalizeBrowserEndpoint,
} = require("../../../runtime/browser/session-contract.cjs");
const STEEL_BASE_URL = DEFAULT_STEEL_ENDPOINT;

// The page-side probe. Runs in the provider's page and returns the field descriptor shape
// care-booking-executor.js reasons about: {selector, label, name, type, required, maxLength}. The
// label is the text a human reads — <label for>, a wrapping <label>, aria-label, or the placeholder —
// because that is what the deterministic matcher matches on.
//
// Deliberately selector-POOR: every query it makes is a plain tag list, and every refinement is done
// in JS. That is not a style preference. A selector STRING that is composed separately from the
// element it is meant to describe can silently stop describing it — the old submit fallback returned
// 'form button[type="submit"], …' even when the control it had just found was a <button> with no
// type, so the executor clicked whatever else matched, or nothing. Every selector below is a path
// computed FROM the element that was found (cssPath), so it cannot drift from it.
const READ_FORM_EXPRESSION = `(() => {
  // The booking vocabulary, kept in sync with KIND_PATTERNS in care-booking-executor.js. Used ONLY to
  // score which form on the page is the booking form — the real matching still happens in the
  // executor, where the LLM-assist seam lives.
  const VOCAB = /メール|mail|e-?mail|電話|tel|phone|携帯|日時|希望日|予約日|来院日|date|time|氏名|名前|お名前|name/i;
  const TYPED_KINDS = ["email", "tel", "date", "time", "datetime-local"];
  const REQUIRED_MARK = /必須|required/i;
  const SKIP_TYPES = ["hidden", "submit", "button", "image", "reset"];
  const typeOf = (el) => String(el.type || el.getAttribute("type") || "").toLowerCase();

  const cssPath = (el) => {
    if (el.id) return "#" + CSS.escape(el.id);
    const parts = [];
    let node = el;
    while (node && node.tagName && node.tagName.toLowerCase() !== "html") {
      if (node.id) { parts.unshift("#" + CSS.escape(node.id)); break; }
      let part = node.tagName.toLowerCase();
      const parent = node.parentElement;
      if (parent) {
        const same = [...parent.children].filter((c) => c.tagName === node.tagName);
        if (same.length > 1) part += ":nth-of-type(" + (same.indexOf(node) + 1) + ")";
      }
      parts.unshift(part);
      node = parent;
    }
    return parts.join(" > ");
  };

  const labels = [...document.querySelectorAll("label")];
  const labelFor = (el) => (el.id ? labels.find((l) => (l.htmlFor || l.getAttribute("for") || "") === el.id) : null) || null;
  const labelOf = (el) => {
    const explicit = labelFor(el);
    if (explicit && explicit.textContent.trim()) return explicit.textContent.trim();
    let node = el.parentElement;
    for (let depth = 0; node && depth < 4; depth += 1, node = node.parentElement) {
      if (node.tagName.toLowerCase() === "label" && node.textContent.trim()) return node.textContent.trim();
    }
    return (el.getAttribute("aria-label") || el.getAttribute("placeholder") || "").trim();
  };

  // 必須 is almost never the HTML required attribute on a Japanese form — it is a ⟨span class="req"⟩
  // in the label or a class on the row. A requirement we can SEE is a requirement, and treating it as
  // one is what makes the "never submit a form whose required fields you cannot fill" rule bite.
  const markedRequired = (el) => {
    const explicit = labelFor(el);
    if (explicit && (REQUIRED_MARK.test(explicit.textContent || "") || REQUIRED_MARK.test(explicit.className || ""))) return true;
    let node = el.parentElement;
    for (let depth = 0; node && depth < 3; depth += 1, node = node.parentElement) {
      // Stop as soon as the container holds more than this one control: past that point the 必須 we
      // would find belongs to somebody ELSE's field, and inventing a requirement is as dishonest as
      // ignoring one.
      if ([...node.querySelectorAll("input, select, textarea")].length > 1) break;
      if (REQUIRED_MARK.test(node.textContent || "") || REQUIRED_MARK.test(node.className || "")) return true;
    }
    return false;
  };

  const describe = (el) => {
    const tag = el.tagName.toLowerCase();
    const max = Number(el.maxLength);
    return {
      selector: cssPath(el),
      label: labelOf(el),
      name: el.name || el.getAttribute("name") || null,
      type: tag === "textarea" ? "textarea" : tag === "select" ? "select" : (typeOf(el) || "text"),
      required: el.required === true || el.getAttribute("aria-required") === "true" || markedRequired(el),
      maxLength: Number.isFinite(max) && max > 0 ? max : null,
    };
  };

  const fieldsOf = (scope) => [...scope.querySelectorAll("input, select, textarea")]
    .filter((el) => !SKIP_TYPES.includes(typeOf(el)))
    .map(describe);

  const submitOf = (scope) => [...scope.querySelectorAll("button, input")].find((el) => {
    const type = typeOf(el);
    if (type === "submit") return true;
    return el.tagName.toLowerCase() === "button" && !type;
  }) || null;

  // A provider page carries a site search box and a login panel alongside the booking form, and the
  // FIRST <form> in the document is usually one of those. Picking it is a coin flip that ends as
  // "no fields I can map" on a page that had a perfectly fillable booking form two forms down.
  const scopes = document.forms && document.forms.length ? [...document.forms] : (document.body ? [document.body] : []);
  let best = null;
  for (const scope of scopes) {
    const fields = fieldsOf(scope);
    const score = fields.filter((f) => VOCAB.test((f.label || "") + " " + (f.name || "")) || TYPED_KINDS.includes(f.type)).length;
    if (!best || score > best.score) best = { score, fields, submit: submitOf(scope) };
  }
  if (!best) return { submitSelector: null, fields: [], formsScanned: 0, mappedFieldCount: 0 };
  return {
    submitSelector: best.submit ? cssPath(best.submit) : null,
    fields: best.fields,
    formsScanned: scopes.length,
    mappedFieldCount: best.score,
  };
})()`;

const READBACK_EXPRESSION = `({ text: document.body ? document.body.innerText.slice(0, 4000) : "", url: location.href })`;

function fillExpression(selector, value) {
  return `(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error("field not found: " + ${JSON.stringify(selector)});
    const setter = Object.getOwnPropertyDescriptor(el.constructor.prototype, "value");
    if (setter && setter.set) setter.set.call(el, ${JSON.stringify(value)}); else el.value = ${JSON.stringify(value)};
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  })()`;
}

// The one page-side error that means "the click was PROVABLY never dispatched". care-booking-executor
// keys its zero-submits honest_failure on exactly this text (SUBMIT_NEVER_DISPATCHED), so it is named
// here rather than written inline: a paraphrase on this side would silently turn a clean failure into
// a possibly_booked, which is the outcome that permanently blocks the honest retry.
const SUBMIT_NOT_FOUND_MESSAGE = "submit control not found";

function submitExpression(selector) {
  return `(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) throw new Error(${JSON.stringify(SUBMIT_NOT_FOUND_MESSAGE)});
    el.click();
    return true;
  })()`;
}

async function readJson(response) {
  if (typeof response.json === "function") return response.json();
  return JSON.parse(await response.text());
}

// The real CDP connection is injected (`connectCdp`) so the protocol wiring can be swapped or
// stubbed without this module smuggling a websocket import into every test that touches booking.
function sessionOptions(options) {
  const value = options && typeof options === "object" && !Array.isArray(options)
    ? options
    : {};
  const contract = value.browserSession || value.sessionContract || null;
  const { browserSession: _browserSession, sessionContract: _sessionContract, ...steelOptions } = value;
  return { contract, steelOptions };
}

function makeSteelCdpClient({
  baseUrl = process.env.LIFE_MANAGER_BROWSER_ENDPOINT || STEEL_BASE_URL,
  fetchImpl,
  connectCdp,
  sessionConfig,
} = {}) {
  const allowPublicEndpoint = Boolean(
    sessionConfig && sessionConfig.allowPublicEndpoint === true,
  ) || process.env.LIFE_MANAGER_BROWSER_ALLOW_PUBLIC_ENDPOINT === "1";
  const normalizedBaseUrl = normalizeBrowserEndpoint(baseUrl, { allowPublicEndpoint });
  const configuredSession = sessionConfig
    ? createBrowserSessionConfig({ ...sessionConfig, endpoint: normalizedBaseUrl })
    : null;
  const doFetch = fetchImpl || globalThis.fetch;
  const connect = connectCdp || require("./cdp-connection.js").connectCdp;
  let connection = null;

  function resolveSessionContract(value) {
    if (value == null) return configuredSession;
    if (value && value.schema_version === 1) {
      if (value.endpoint !== normalizedBaseUrl) {
        throw new Error("browser session contract endpoint mismatch");
      }
      return value;
    }
    return createBrowserSessionConfig({
      ...value,
      endpoint: normalizedBaseUrl,
    });
  }

  async function page() {
    if (!connection) throw new Error("no steel session — createSession() first");
    return connection;
  }

  async function launch(options = {}) {
    const resolved = sessionOptions(options);
    const steelOptions = resolved.steelOptions;
    if (Object.hasOwn(steelOptions, "persist") || Object.hasOwn(steelOptions, "userDataDir")) {
      throw new Error("persistent Steel profiles are forbidden");
    }
    const response = await doFetch(`${normalizedBaseUrl}/v1/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blockAds: true, ...steelOptions }),
    });
    if (!response || !response.ok) {
      throw new Error(`steel session launch failed (${response ? response.status : "no response"})`);
    }
    const details = await readJson(response);
    if (!details || !details.id || !details.websocketUrl) {
      throw new Error("steel session response carried no CDP endpoint");
    }
    return { id: details.id, websocketUrl: details.websocketUrl };
  }

  async function releaseRemoteSession(sessionId) {
    const id = typeof sessionId === "string" ? sessionId.trim() : "";
    if (!/^[A-Za-z0-9._-]{1,200}$/.test(id)) throw new Error("Steel session id unavailable");
    let firstError = null;
    try {
      const response = await doFetch(`${normalizedBaseUrl}/v1/sessions/${encodeURIComponent(id)}/release`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (response && response.ok) return true;
      firstError = new Error(`steel session release failed (${response ? response.status : "no response"})`);
    } catch (error) {
      firstError = error instanceof Error ? error : new Error(`steel session release failed: ${String(error)}`);
    }
    try {
      const all = await doFetch(`${normalizedBaseUrl}/v1/sessions/release`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (all && all.ok) return true;
    } catch { /* report the original per-session error */ }
    throw firstError;
  }

  async function checkedLaunch(options = {}) {
    const resolved = sessionOptions(options);
    const sessionContract = resolveSessionContract(resolved.contract);
    const session = await launch(resolved.steelOptions);
    try {
      // Endpoint binding is mandatory even when a caller does not need the richer
      // tenant/storage contract.  Returning an unbound CDP socket would let a stale
      // or misconfigured launch drive another browser service.
      assertBrowserSessionEndpoint(session, sessionContract ? sessionContract.endpoint : normalizedBaseUrl, {
        allowPublicEndpoint: sessionContract
          ? sessionContract.allow_public_endpoint === true
          : allowPublicEndpoint,
      });
    } catch (error) {
      const failure = error instanceof Error ? error : new Error(String(error));
      failure.sessionId = session.id;
      failure.sessionReleased = await releaseRemoteSession(session.id).then(() => true, () => false);
      throw failure;
    }
    return session;
  }

  return {
    baseUrl: normalizedBaseUrl,
    sessionContract: configuredSession,
    async assertLiveSession(sessionId) {
      const id = typeof sessionId === "string" ? sessionId.trim() : "";
      if (!/^[A-Za-z0-9._-]{1,200}$/.test(id)) throw new Error("Steel live session invalid");
      const response = await doFetch(`${normalizedBaseUrl}/v1/sessions/${encodeURIComponent(id)}`);
      if (!response || !response.ok) throw new Error("Steel live session unavailable");
      const details = await readJson(response);
      if (!details || details.id !== id || details.status !== "live") {
        throw new Error("Steel live session unavailable");
      }
      return true;
    },
    async getInteractiveDebugger(sessionId, publicCastUrl) {
      let target;
      try { target = new URL(publicCastUrl); } catch { throw new Error("Steel debugger public URL invalid"); }
      const pathMatch = target.pathname.match(/^\/api\/panel\/money-printer\/browser\/cast\/([A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43})$/);
      if (target.protocol !== "wss:" || target.username || target.password
        || target.search || target.hash || !pathMatch) {
        throw new Error("Steel debugger public URL invalid");
      }
      await this.assertLiveSession(sessionId);
      const response = await doFetch(`${normalizedBaseUrl}/v1/sessions/debug?interactive=true&showControls=true`);
      if (!response || !response.ok) throw new Error("Steel debugger unavailable");
      const html = await response.text();
      const privateCast = "ws://steel-browser.railway.internal:8080/v1/sessions/cast";
      if (typeof html !== "string" || Buffer.byteLength(html) > 128 * 1024
        || html.split(privateCast).length !== 2) throw new Error("Steel debugger invalid");
      const safe = html.replace(privateCast, target.toString());
      if (/railway\.internal|ws:\/\//i.test(safe)) throw new Error("Steel debugger invalid");
      return safe;
    },
    async health() {
      const response = await doFetch(`${normalizedBaseUrl}/v1/health`);
      return Boolean(response && response.ok);
    },
    // Stagehand owns the CDP connection for generic natural-language tasks. This creates the same
    // private Steel session but deliberately does not attach the deterministic booking CDP client.
    async createRawSession(options = {}) {
      return checkedLaunch(options);
    },
    async getSessionContext(sessionId) {
      const id = typeof sessionId === "string" ? sessionId.trim() : "";
      if (!id || id.length > 200) throw new Error("steel session id unavailable");
      const response = await doFetch(
        `${normalizedBaseUrl}/v1/sessions/${encodeURIComponent(id)}/context`,
        { method: "GET" },
      );
      if (!response || !response.ok) {
        throw new Error(
          `steel session context export failed (${response ? response.status : "no response"})`,
        );
      }
      return validateSessionContext(await readJson(response));
    },
    async createSession(options = {}) {
      const details = await checkedLaunch(options);
      // The id is captured BEFORE the connect, because a connect that throws leaves a session running
      // on the far side that nobody holds a handle to — and the OSS build has exactly one slot, so an
      // orphan blocks every later booking for every user until the service restarts.
      const createdId = details.id;
      try {
        connection = await connect(details.websocketUrl);
      } catch (error) {
        const failure = error instanceof Error ? error : new Error(String(error));
        if (createdId) {
          failure.sessionId = createdId;
          failure.sessionReleased = await this.releaseSession(createdId).then(() => true, () => false);
        }
        throw failure;
      }
      return { id: createdId, websocketUrl: details.websocketUrl };
    },
    async navigate(_sessionId, url) {
      return (await page()).navigate(url);
    },
    async readForm(_sessionId) {
      return (await page()).evaluate(READ_FORM_EXPRESSION);
    },
    async fill(_sessionId, selector, value) {
      return (await page()).evaluate(fillExpression(selector, value));
    },
    async submit(_sessionId, selector) {
      return (await page()).evaluate(submitExpression(selector));
    },
    async readConfirmation(_sessionId) {
      return (await page()).evaluate(READBACK_EXPRESSION);
    },
    // The post-submit page load, bounded. Exposed here because only the executor knows WHEN a load is
    // worth waiting for (right after the one click it is allowed to make).
    async waitForLoad(_sessionId, timeoutMs) {
      const open = await page();
      if (typeof open.waitForLoad !== "function") return { loaded: false, navigated: false };
      return open.waitForLoad(timeoutMs);
    },
    // POST /v1/sessions/release — frees whatever the single-session build is currently holding. The
    // blunt instrument, for when we know a session exists but not which id it has.
    async releaseAll() {
      const open = connection;
      connection = null;
      if (open && typeof open.close === "function") {
        try { await open.close(); } catch { /* the HTTP release below is what actually frees the slot */ }
      }
      const response = await doFetch(`${normalizedBaseUrl}/v1/sessions/release`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      return Boolean(response && response.ok);
    },
    async releaseSession(sessionId) {
      const open = connection;
      connection = null;
      if (open && typeof open.close === "function") {
        try { await open.close(); } catch { /* the HTTP release below is what actually frees the slot */ }
      }
      // A session we failed to release by id still occupies the only slot there is. Release-ALL is
      // safe precisely because the build is single-session: there is no other tenant's session to
      // take down with it, and leaving the slot stuck is strictly worse than freeing it bluntly.
      return releaseRemoteSession(sessionId);
    },
  };
}

module.exports = { makeSteelCdpClient, STEEL_BASE_URL, READ_FORM_EXPRESSION, SUBMIT_NOT_FOUND_MESSAGE };
