-- Preserve the existing provider usage ledger while closing its mutation boundary.
CREATE OR REPLACE FUNCTION public.lm_api_cost_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
  RAISE EXCEPTION 'lm_api_cost is append-only';
END;
$$;

DROP TRIGGER IF EXISTS lm_api_cost_guard ON public.lm_api_cost;
CREATE TRIGGER lm_api_cost_guard
  BEFORE UPDATE OR DELETE ON public.lm_api_cost
  FOR EACH ROW EXECUTE FUNCTION public.lm_api_cost_guard();

DROP TRIGGER IF EXISTS lm_api_cost_truncate_guard ON public.lm_api_cost;
CREATE TRIGGER lm_api_cost_truncate_guard
  BEFORE TRUNCATE ON public.lm_api_cost
  FOR EACH STATEMENT EXECUTE FUNCTION public.lm_api_cost_guard();

ALTER TABLE public.lm_api_cost ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lm_api_cost FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON TABLE public.lm_api_cost TO service_role;
REVOKE UPDATE ON TABLE public.lm_api_cost FROM service_role;
REVOKE DELETE ON TABLE public.lm_api_cost FROM service_role;
REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE public.lm_api_cost FROM service_role;

REVOKE ALL ON SEQUENCE public.lm_api_cost_id_seq FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE public.lm_api_cost_id_seq TO service_role;
