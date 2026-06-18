"use strict";
// Life Manager transport adapter — the ONE place local & cloud differ.
//   LIFE_TRANSPORT=gog       (local)  → user's own gog CLI + keychain
//   LIFE_TRANSPORT=composio  (cloud)  → Composio OAuth, keys we manage (wired in #49)
// Consumers call calendar.*/mail.* ONLY. They never spawn gog themselves.
const { execFileSync } = require("node:child_process");

// LOCAL implementation: wraps the verified `gog` CLI shapes (gog 0.17.0).
function gogTransport({ bin = process.env.GOG_BIN || "gog", account, keyring = "", calId = "primary" } = {}) {
  const env = () => ({ ...process.env, GOG_KEYRING_PASSWORD: keyring, GOG_ACCOUNT: account });
  // every gog call ends with --account <account>. NOTE: this is argv-EQUIVALENT, not byte-identical:
  // the adapter appends --account last uniformly, whereas current call sites place it mid-argv on
  // `calendar list` and `gmail send`. gog flags are order-independent — VERIFIED on gog 0.17.0:
  //   `gog calendar events list -j --from today --all-pages --max 1 --account <acct>` → exit 0 + valid JSON.
  const run = (args, timeout = 60000) =>
    execFileSync(bin, [...args, "--account", account], { env: env(), encoding: "utf8", timeout });
  return {
    calendar: {
      // from default "today"; to = "YYYY-MM-DD" (optional). Returns raw gog event items[].
      list({ from = "today", to, max = 250 } = {}) {
        const args = ["calendar", "events", "list", "-j", "--from", from, "--all-pages", "--max", String(max)];
        if (to) args.push("--to", to);
        const d = JSON.parse(run(args));
        return Array.isArray(d) ? d : (d.events || d.items || []);
      },
      // gog calendar update needs <calendarId> <eventId> (two positionals) — verified.
      updateLocation(eventId, location) {
        run(["calendar", "update", calId, eventId, "--location", location, "-j"], 30000);
        return true;
      },
    },
    mail: {
      send({ to, subject, body }) {
        const out = run(["gmail", "send", "--to", to, "--subject", subject, "--body", body, "--json"], 30000);
        try { const j = JSON.parse(out); return j.id || j.messageId || ""; } catch { return ""; }
      },
      search(query) {
        const d = JSON.parse(run(["gmail", "search", query, "-j"], 30000));
        return (d.threads || d.messages || d || []).map((t) => ({ id: t.id, subject: t.subject || "" }));
      },
      getBody(id) {
        const d = JSON.parse(run(["gmail", "get", id, "-j"], 30000));
        const subject = (d.headers && (d.headers.subject || d.headers.Subject)) || d.subject || "";
        return { subject, body: d.body || "" };
      },
    },
  };
}

// CLOUD implementation: same interface, OAuth per user. Wired in the web-app workstream (#49).
function composioTransport() {
  const nyi = () => { throw new Error("composio transport not wired yet (#49 web app)"); };
  return { calendar: { list: nyi, updateLocation: nyi }, mail: { send: nyi, search: nyi, getBody: nyi } };
}

function makeTransport(cfg = {}) {
  const kind = (process.env.LIFE_TRANSPORT || cfg.kind || "gog").toLowerCase();
  return kind === "composio" ? composioTransport(cfg) : gogTransport(cfg);
}

module.exports = { makeTransport, gogTransport, composioTransport };
