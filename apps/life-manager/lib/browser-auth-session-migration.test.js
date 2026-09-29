"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SQL = fs.readFileSync(path.join(
  __dirname,
  "../migrations/2026-07-28-lm-browser-auth-sessions.sql",
), "utf8");
const IDENTITY_SQL = fs.readFileSync(path.join(
  __dirname,
  "../migrations/2026-09-29-lm-agent-identity-refs.sql",
), "utf8");

test("browser auth sessions are service-only, tenant-bound encrypted rows", () => {
  assert.match(SQL, /CREATE TABLE IF NOT EXISTS public\.lm_browser_auth_sessions/i);
  assert.match(SQL, /PRIMARY KEY \(uid, origin, principal_kind\)/i);
  assert.match(SQL, /principal_kind text NOT NULL CHECK \(principal_kind IN \('agent_owned', 'user_provided'\)\)/i);
  for (const column of ["ciphertext", "iv", "auth_tag", "context_sha256", "key_version"]) {
    assert.match(SQL, new RegExp(`${column}\\s+(?:text|integer)\\s+NOT NULL`, "i"));
  }
  assert.match(SQL, /ALTER TABLE public\.lm_browser_auth_sessions ENABLE ROW LEVEL SECURITY/i);
  assert.match(SQL, /REVOKE ALL ON TABLE public\.lm_browser_auth_sessions FROM PUBLIC/i);
  for (const role of ["anon", "authenticated", "service_role"]) {
    assert.match(SQL, new RegExp(`FROM pg_roles WHERE rolname = '${role}'`, "i"));
  }
  assert.match(SQL, /REVOKE ALL ON TABLE public\.lm_browser_auth_sessions FROM anon/i);
  assert.match(SQL, /REVOKE ALL ON TABLE public\.lm_browser_auth_sessions FROM authenticated/i);
  assert.match(SQL, /GRANT SELECT, INSERT, UPDATE ON TABLE public\.lm_browser_auth_sessions TO service_role/i);
  assert.doesNotMatch(SQL, /CREATE POLICY|GRANT .* TO (?:anon|authenticated)/i);
});

test("AgentCore Identity refs are service-only agent-owned metadata with no secret values", () => {
  assert.match(IDENTITY_SQL, /CREATE TABLE IF NOT EXISTS public\.lm_agent_identity_refs/i);
  assert.match(IDENTITY_SQL, /principal_kind text NOT NULL CHECK \(principal_kind = 'agent_owned'\)/i);
  assert.match(IDENTITY_SQL, /kind text NOT NULL CHECK \(kind IN \('api_key', 'oauth2_m2m'\)\)/i);
  assert.match(IDENTITY_SQL, /ALTER TABLE public\.lm_agent_identity_refs ENABLE ROW LEVEL SECURITY/i);
  assert.match(IDENTITY_SQL, /REVOKE ALL ON TABLE public\.lm_agent_identity_refs FROM PUBLIC/i);
  assert.doesNotMatch(IDENTITY_SQL, /api_key_value|access_token|refresh_token|client_secret|credential_value/i);
});
