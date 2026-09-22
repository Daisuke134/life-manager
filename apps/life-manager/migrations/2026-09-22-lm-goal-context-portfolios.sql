-- Durable, immutable Goal Context and Goal Portfolio revisions for the authenticated
-- cloud slice. Rows contain references and validated goal documents, never provider
-- credentials or copied source data. Only service_role may read or write them.

CREATE TABLE IF NOT EXISTS public.lm_goal_contexts (
  tenant_id text NOT NULL REFERENCES public.lm_users(uid) ON DELETE CASCADE
    CHECK (char_length(tenant_id) BETWEEN 1 AND 200),
  revision integer NOT NULL CHECK (revision BETWEEN 1 AND 100),
  context jsonb NOT NULL CHECK (
    jsonb_typeof(context) = 'object'
    AND octet_length(context::text) <= 425000
    AND context->>'schema_version' = 'life-manager.goal-context.v1'
    AND context->>'tenant_id' = tenant_id
    AND CASE
      WHEN context->>'revision' ~ '^[1-9][0-9]*$'
      THEN (context->>'revision')::integer = revision
      ELSE false
    END
    AND jsonb_typeof(context->'fact_refs') = 'array'
    AND jsonb_array_length(context->'fact_refs') <= 100
    AND jsonb_typeof(context->'account_refs') = 'array'
    AND jsonb_array_length(context->'account_refs') <= 100
    AND jsonb_typeof(context->'consent_refs') = 'array'
    AND jsonb_array_length(context->'consent_refs') <= 100
    AND jsonb_typeof(context->'boundary_refs') = 'array'
    AND jsonb_array_length(context->'boundary_refs') <= 100
  ),
  context_sha256 text NOT NULL CHECK (context_sha256 ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, revision)
);

CREATE TABLE IF NOT EXISTS public.lm_goal_portfolios (
  tenant_id text NOT NULL CHECK (char_length(tenant_id) BETWEEN 1 AND 200),
  revision integer NOT NULL CHECK (revision BETWEEN 1 AND 100),
  portfolio jsonb NOT NULL CHECK (
    jsonb_typeof(portfolio) = 'object'
    AND octet_length(portfolio::text) <= 65536
    AND portfolio->>'schema_version' = 'life-manager.goal-portfolio.v1'
    AND portfolio->>'tenant_id' = tenant_id
    AND portfolio->>'origin' = 'life_manager'
    AND CASE
      WHEN portfolio->>'revision' ~ '^[1-9][0-9]*$'
      THEN (portfolio->>'revision')::integer = revision
      ELSE false
    END
    AND jsonb_typeof(portfolio->'goals') = 'array'
    AND jsonb_array_length(portfolio->'goals') BETWEEN 1 AND 3
  ),
  portfolio_sha256 text NOT NULL CHECK (portfolio_sha256 ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, revision),
  FOREIGN KEY (tenant_id, revision)
    REFERENCES public.lm_goal_contexts (tenant_id, revision) ON DELETE CASCADE
);

ALTER TABLE public.lm_goal_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lm_goal_portfolios ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.lm_goal_contexts FROM PUBLIC;
REVOKE ALL ON TABLE public.lm_goal_portfolios FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.lm_goal_contexts FROM anon';
    EXECUTE 'REVOKE ALL ON TABLE public.lm_goal_portfolios FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.lm_goal_contexts FROM authenticated';
    EXECUTE 'REVOKE ALL ON TABLE public.lm_goal_portfolios FROM authenticated';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT SELECT, INSERT ON TABLE public.lm_goal_contexts TO service_role';
    EXECUTE 'GRANT SELECT, INSERT ON TABLE public.lm_goal_portfolios TO service_role';
  END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.put_lm_goal_context(
  p_tenant_id text,
  p_chat_id text,
  p_revision integer,
  p_context jsonb,
  p_context_sha256 text
) RETURNS TABLE(
  tenant_id text,
  revision integer,
  context jsonb,
  context_sha256 text,
  created boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  existing public.lm_goal_contexts%ROWTYPE;
BEGIN
  IF p_tenant_id IS NULL OR char_length(p_tenant_id) NOT BETWEEN 1 AND 200
    OR p_chat_id IS NULL OR char_length(p_chat_id) NOT BETWEEN 1 AND 200
    OR p_revision IS NULL OR p_revision NOT BETWEEN 1 AND 100
    OR p_context IS NULL OR jsonb_typeof(p_context) <> 'object'
    OR p_context_sha256 !~ '^[a-f0-9]{64}$'
  THEN
    RAISE EXCEPTION 'goal context invalid';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.lm_users AS users
    WHERE users.uid = p_tenant_id
      AND users.telegram_chat_id::text = p_chat_id
  ) THEN
    RETURN;
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended('lm_goal_context:' || p_tenant_id || ':' || p_revision::text, 0)
  );
  SELECT rows.* INTO existing
  FROM public.lm_goal_contexts AS rows
  WHERE rows.tenant_id = p_tenant_id AND rows.revision = p_revision
  FOR UPDATE;

  IF FOUND THEN
    IF existing.context_sha256 <> p_context_sha256 OR existing.context <> p_context THEN
      RAISE EXCEPTION 'goal context collision';
    END IF;
    RETURN QUERY SELECT existing.tenant_id, existing.revision, existing.context,
      existing.context_sha256, false;
    RETURN;
  END IF;

  INSERT INTO public.lm_goal_contexts AS rows (
    tenant_id, revision, context, context_sha256
  ) VALUES (p_tenant_id, p_revision, p_context, p_context_sha256)
  RETURNING rows.* INTO existing;

  RETURN QUERY SELECT existing.tenant_id, existing.revision, existing.context,
    existing.context_sha256, true;
END
$$;

CREATE OR REPLACE FUNCTION public.put_lm_goal_portfolio(
  p_tenant_id text,
  p_revision integer,
  p_portfolio jsonb,
  p_portfolio_sha256 text
) RETURNS TABLE(
  tenant_id text,
  revision integer,
  portfolio jsonb,
  portfolio_sha256 text,
  created boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  existing public.lm_goal_portfolios%ROWTYPE;
BEGIN
  IF p_tenant_id IS NULL OR char_length(p_tenant_id) NOT BETWEEN 1 AND 200
    OR p_revision IS NULL OR p_revision NOT BETWEEN 1 AND 100
    OR p_portfolio IS NULL OR jsonb_typeof(p_portfolio) <> 'object'
    OR p_portfolio_sha256 !~ '^[a-f0-9]{64}$'
  THEN
    RAISE EXCEPTION 'goal portfolio invalid';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.lm_goal_contexts AS contexts
    WHERE contexts.tenant_id = p_tenant_id AND contexts.revision = p_revision
  ) THEN
    RETURN;
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended('lm_goal_portfolio:' || p_tenant_id || ':' || p_revision::text, 0)
  );
  SELECT rows.* INTO existing
  FROM public.lm_goal_portfolios AS rows
  WHERE rows.tenant_id = p_tenant_id AND rows.revision = p_revision
  FOR UPDATE;

  IF FOUND THEN
    IF existing.portfolio_sha256 <> p_portfolio_sha256 OR existing.portfolio <> p_portfolio THEN
      RAISE EXCEPTION 'goal portfolio collision';
    END IF;
    RETURN QUERY SELECT existing.tenant_id, existing.revision, existing.portfolio,
      existing.portfolio_sha256, false;
    RETURN;
  END IF;

  INSERT INTO public.lm_goal_portfolios AS rows (
    tenant_id, revision, portfolio, portfolio_sha256
  ) VALUES (p_tenant_id, p_revision, p_portfolio, p_portfolio_sha256)
  RETURNING rows.* INTO existing;

  RETURN QUERY SELECT existing.tenant_id, existing.revision, existing.portfolio,
    existing.portfolio_sha256, true;
END
$$;

REVOKE ALL ON FUNCTION public.put_lm_goal_context(text, text, integer, jsonb, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.put_lm_goal_portfolio(text, integer, jsonb, text) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON FUNCTION public.put_lm_goal_context(text, text, integer, jsonb, text) FROM anon';
    EXECUTE 'REVOKE ALL ON FUNCTION public.put_lm_goal_portfolio(text, integer, jsonb, text) FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON FUNCTION public.put_lm_goal_context(text, text, integer, jsonb, text) FROM authenticated';
    EXECUTE 'REVOKE ALL ON FUNCTION public.put_lm_goal_portfolio(text, integer, jsonb, text) FROM authenticated';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.put_lm_goal_context(text, text, integer, jsonb, text) TO service_role';
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.put_lm_goal_portfolio(text, integer, jsonb, text) TO service_role';
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS lm_runtime_jobs_goal_ref_idx
  ON public.lm_runtime_jobs (tenant_id, (input_refs->>'goal_ref'))
  WHERE loop_id = 'life-manager.manager' AND capability = 'general-agent.work';
