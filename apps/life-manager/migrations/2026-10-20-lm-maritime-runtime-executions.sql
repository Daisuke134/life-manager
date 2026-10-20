-- A dispatch checkpoint only. Terminal state and receipts remain in runtime jobs.
CREATE UNIQUE INDEX IF NOT EXISTS lm_maritime_manager_uid_agent
  ON public.lm_maritime_manager_enrollments (uid, agent_id);
CREATE TABLE IF NOT EXISTS public.lm_maritime_manager_executions (
  uid text NOT NULL,
  occurrence_id text NOT NULL CHECK (occurrence_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
  agent_id text NOT NULL,
  date_key date NOT NULL,
  release_sha text NOT NULL CHECK (release_sha ~ '^[0-9a-f]{40}$'),
  execution_id text CHECK (execution_id IS NULL OR execution_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'),
  claimed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (uid, occurrence_id),
  FOREIGN KEY (uid, agent_id) REFERENCES public.lm_maritime_manager_enrollments(uid, agent_id),
  UNIQUE (agent_id, execution_id)
);
ALTER TABLE public.lm_maritime_manager_executions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.lm_maritime_manager_executions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.lm_maritime_manager_executions TO service_role;

CREATE OR REPLACE FUNCTION public.claim_lm_maritime_manager_cycle_v1(
  p_uid text, p_occurrence_id text, p_agent_id text, p_release_sha text, p_date_key date
) RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
  WITH claimed AS (
    INSERT INTO public.lm_maritime_manager_executions(uid, occurrence_id, agent_id, release_sha, date_key)
      SELECT uid, p_occurrence_id, agent_id, p_release_sha, p_date_key
      FROM public.lm_maritime_manager_enrollments
      WHERE uid = p_uid AND agent_id = p_agent_id AND release_sha = p_release_sha
        AND status = 'active' AND paused_at IS NULL
      ON CONFLICT (uid, occurrence_id) DO NOTHING
      RETURNING uid
  ) SELECT EXISTS (SELECT 1 FROM claimed);
$$;
CREATE OR REPLACE FUNCTION public.bind_lm_maritime_manager_execution_v1(
  p_uid text, p_occurrence_id text, p_agent_id text, p_release_sha text, p_date_key date,
  p_execution_id text
) RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
  WITH bound AS (
    UPDATE public.lm_maritime_manager_executions SET execution_id = p_execution_id
      WHERE uid = p_uid AND occurrence_id = p_occurrence_id AND agent_id = p_agent_id
        AND release_sha = p_release_sha AND date_key = p_date_key
        AND p_execution_id IS NOT NULL
        AND (execution_id IS NULL OR execution_id = p_execution_id)
      RETURNING uid
  ) SELECT EXISTS (SELECT 1 FROM bound);
$$;
REVOKE ALL ON FUNCTION public.claim_lm_maritime_manager_cycle_v1(text,text,text,text,date) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.bind_lm_maritime_manager_execution_v1(text,text,text,text,date,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_lm_maritime_manager_cycle_v1(text,text,text,text,date) TO service_role;
GRANT EXECUTE ON FUNCTION public.bind_lm_maritime_manager_execution_v1(text,text,text,text,date,text) TO service_role;
