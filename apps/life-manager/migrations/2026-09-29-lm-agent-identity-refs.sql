-- A20: tenant-bound opaque references to agent-owned AgentCore Identity providers.
-- No API key, OAuth token, client secret, or human credential is stored here.

CREATE TABLE IF NOT EXISTS public.lm_agent_identity_refs (
  identity_ref text PRIMARY KEY CHECK (identity_ref ~ '^lm-identity:[A-Za-z0-9_-]{8,200}$'),
  tenant_id text NOT NULL CHECK (char_length(tenant_id) BETWEEN 1 AND 200),
  provider text NOT NULL CHECK (char_length(provider) BETWEEN 1 AND 200),
  principal_kind text NOT NULL CHECK (principal_kind = 'agent_owned'),
  kind text NOT NULL CHECK (kind IN ('api_key', 'oauth2_m2m')),
  credential_provider_name text NOT NULL CHECK (char_length(credential_provider_name) BETWEEN 1 AND 200),
  credential_provider_arn text NOT NULL CHECK (char_length(credential_provider_arn) BETWEEN 1 AND 1000),
  state text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'revoked')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  revoked_at timestamptz,
  UNIQUE (tenant_id, provider, kind),
  CHECK ((state = 'active' AND revoked_at IS NULL) OR (state = 'revoked' AND revoked_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS lm_agent_identity_refs_tenant_idx
  ON public.lm_agent_identity_refs(tenant_id, state);

ALTER TABLE public.lm_agent_identity_refs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lm_agent_identity_refs FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.lm_agent_identity_refs FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.lm_agent_identity_refs FROM authenticated';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.lm_agent_identity_refs TO service_role';
  END IF;
END
$$;
