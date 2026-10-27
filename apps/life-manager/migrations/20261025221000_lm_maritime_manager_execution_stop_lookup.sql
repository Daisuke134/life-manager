CREATE INDEX IF NOT EXISTS lm_maritime_manager_execution_stop_lookup
  ON public.lm_maritime_manager_executions
  (uid, agent_id, release_sha, claimed_at DESC, occurrence_id ASC);
