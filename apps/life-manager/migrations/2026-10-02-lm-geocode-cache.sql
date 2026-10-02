CREATE TABLE IF NOT EXISTS public.lm_geocode_cache (
  address_key text PRIMARY KEY,
  lat numeric,
  lon numeric,
  provider text NOT NULL,
  status text NOT NULL CHECK (status IN ('success', 'negative')),
  computed_at timestamptz NOT NULL DEFAULT now(),
  ttl_secs integer NOT NULL CHECK (ttl_secs > 0)
);

REVOKE ALL ON TABLE public.lm_geocode_cache FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.lm_geocode_cache TO service_role;
