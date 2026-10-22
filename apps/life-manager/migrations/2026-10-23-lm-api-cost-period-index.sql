-- Bound tenant/period ledger reads without changing rows or access controls.
-- A normal index build briefly waits writers; fail/rollback instead of holding it open.
BEGIN;
SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '5s';
CREATE INDEX IF NOT EXISTS lm_api_cost_uid_ts_idx
  ON public.lm_api_cost (uid, ts);
COMMIT;
