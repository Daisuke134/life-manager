-- Durable AgentCore cloud state. lm_runtime_jobs remains the only job queue/state machine.
-- These tables contain tenant-scoped provider references and immutable usage receipts, never secrets.

BEGIN;

CREATE TABLE IF NOT EXISTS public.lm_plan_entitlements (
  plan_version text PRIMARY KEY CHECK (plan_version ~ '^[a-z0-9][a-z0-9-]*-v[0-9]+$'),
  plan text NOT NULL CHECK (plan IN ('free', 'founding_pro')),
  limits_json jsonb NOT NULL CHECK (
    jsonb_typeof(limits_json) = 'object'
    AND octet_length(limits_json::text) <= 4096
  ),
  effective_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS public.lm_cloud_tenants (
  tenant_id text PRIMARY KEY CHECK (char_length(tenant_id) BETWEEN 1 AND 200),
  region text NOT NULL CHECK (region = 'ap-northeast-1'),
  release_sha text NOT NULL CHECK (release_sha ~ '^[a-f0-9]{40}$'),
  status text NOT NULL CHECK (status IN ('active', 'inactive', 'manual_hold')),
  plan_version text NOT NULL REFERENCES public.lm_plan_entitlements(plan_version),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS public.lm_cloud_runtime_leases (
  tenant_id text PRIMARY KEY REFERENCES public.lm_cloud_tenants(tenant_id),
  job_id text NOT NULL,
  attempt integer NOT NULL CHECK (attempt > 0),
  runtime_session_id text NOT NULL UNIQUE CHECK (char_length(runtime_session_id) BETWEEN 1 AND 500),
  lease_owner text NOT NULL CHECK (char_length(lease_owner) BETWEEN 1 AND 200),
  lease_expires_at timestamptz NOT NULL,
  generation integer NOT NULL CHECK (generation > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (job_id, tenant_id)
    REFERENCES public.lm_runtime_jobs (job_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS lm_cloud_runtime_leases_expiry_idx
  ON public.lm_cloud_runtime_leases(lease_expires_at);

CREATE TABLE IF NOT EXISTS public.lm_cloud_browser_profiles (
  tenant_id text NOT NULL REFERENCES public.lm_cloud_tenants(tenant_id),
  provider text NOT NULL CHECK (char_length(provider) BETWEEN 1 AND 100),
  profile_id text NOT NULL CHECK (char_length(profile_id) BETWEEN 1 AND 500),
  principal_type text NOT NULL CHECK (principal_type = 'agent_owned'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, provider),
  UNIQUE (provider, profile_id)
);

CREATE TABLE IF NOT EXISTS public.lm_cloud_usage_ledger (
  tenant_id text NOT NULL REFERENCES public.lm_cloud_tenants(tenant_id),
  job_id text NOT NULL,
  provider text NOT NULL CHECK (char_length(provider) BETWEEN 1 AND 100),
  resource text NOT NULL CHECK (char_length(resource) BETWEEN 1 AND 200),
  quantity bigint NOT NULL CHECK (quantity > 0),
  unit text NOT NULL CHECK (char_length(unit) BETWEEN 1 AND 50),
  cost_usd_micros bigint NOT NULL CHECK (cost_usd_micros >= 0),
  provider_receipt_id text PRIMARY KEY CHECK (char_length(provider_receipt_id) BETWEEN 1 AND 500),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (job_id, tenant_id)
    REFERENCES public.lm_runtime_jobs (job_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS lm_cloud_usage_tenant_job_idx
  ON public.lm_cloud_usage_ledger(tenant_id, job_id, created_at);

CREATE OR REPLACE FUNCTION public.reject_lm_cloud_usage_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
  RAISE EXCEPTION 'cloud usage rows are immutable';
END
$$;

DROP TRIGGER IF EXISTS lm_cloud_usage_immutable ON public.lm_cloud_usage_ledger;
CREATE TRIGGER lm_cloud_usage_immutable
BEFORE UPDATE OR DELETE ON public.lm_cloud_usage_ledger
FOR EACH ROW EXECUTE FUNCTION public.reject_lm_cloud_usage_mutation();

ALTER TABLE public.lm_plan_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lm_cloud_tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lm_cloud_runtime_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lm_cloud_browser_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lm_cloud_usage_ledger ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.lm_plan_entitlements FROM PUBLIC;
REVOKE ALL ON TABLE public.lm_cloud_tenants FROM PUBLIC;
REVOKE ALL ON TABLE public.lm_cloud_runtime_leases FROM PUBLIC;
REVOKE ALL ON TABLE public.lm_cloud_browser_profiles FROM PUBLIC;
REVOKE ALL ON TABLE public.lm_cloud_usage_ledger FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.lm_plan_entitlements, public.lm_cloud_tenants, public.lm_cloud_runtime_leases, public.lm_cloud_browser_profiles, public.lm_cloud_usage_ledger FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.lm_plan_entitlements, public.lm_cloud_tenants, public.lm_cloud_runtime_leases, public.lm_cloud_browser_profiles, public.lm_cloud_usage_ledger FROM authenticated';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT SELECT ON TABLE public.lm_plan_entitlements TO service_role';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.lm_cloud_tenants TO service_role';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.lm_cloud_runtime_leases TO service_role';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.lm_cloud_browser_profiles TO service_role';
    EXECUTE 'GRANT SELECT, INSERT ON TABLE public.lm_cloud_usage_ledger TO service_role';
  END IF;
END
$$;

COMMIT;
