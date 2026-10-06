-- Store successful Google geocodes privately by tenant, provider, and keyed address digest.
-- RPC functions keep the private schema out of the PostgREST exposed-schema list.

CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS private.lm_geocode_cache (
  uid            text             NOT NULL,
  provider       text             NOT NULL,
  address_digest text             NOT NULL CHECK (address_digest ~ '^[a-f0-9]{64}$'),
  lat            double precision NOT NULL CHECK (lat >= -90 AND lat <= 90),
  lon            double precision NOT NULL CHECK (lon >= -180 AND lon <= 180),
  computed_at    timestamptz      NOT NULL,
  ttl_secs       integer          NOT NULL DEFAULT 86400 CHECK (ttl_secs = 86400),
  PRIMARY KEY (uid, provider, address_digest)
);

ALTER TABLE private.lm_geocode_cache ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE private.lm_geocode_cache FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.lm_geocode_cache_get(
  p_uid text,
  p_provider text,
  p_address_digest text
)
RETURNS TABLE(lat double precision, lon double precision, computed_at timestamptz, ttl_secs integer)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $function$
  SELECT cache.lat, cache.lon, cache.computed_at, cache.ttl_secs
  FROM private.lm_geocode_cache AS cache
  WHERE cache.uid = p_uid
    AND cache.provider = p_provider
    AND cache.address_digest = p_address_digest
    AND cache.computed_at + (cache.ttl_secs * interval '1 second') > now()
$function$;

CREATE OR REPLACE FUNCTION public.lm_geocode_cache_upsert(
  p_uid text,
  p_provider text,
  p_address_digest text,
  p_lat double precision,
  p_lon double precision,
  p_computed_at timestamptz,
  p_ttl_secs integer
)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $function$
  INSERT INTO private.lm_geocode_cache (uid, provider, address_digest, lat, lon, computed_at, ttl_secs)
  VALUES (p_uid, p_provider, p_address_digest, p_lat, p_lon, p_computed_at, p_ttl_secs)
  ON CONFLICT (uid, provider, address_digest) DO UPDATE
    SET lat = EXCLUDED.lat,
        lon = EXCLUDED.lon,
        computed_at = EXCLUDED.computed_at,
        ttl_secs = EXCLUDED.ttl_secs
$function$;

REVOKE ALL ON FUNCTION public.lm_geocode_cache_get(text, text, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.lm_geocode_cache_upsert(text, text, text, double precision, double precision,
  timestamptz, integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lm_geocode_cache_get(text, text, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.lm_geocode_cache_upsert(text, text, text, double precision, double precision,
  timestamptz, integer) TO service_role;

NOTIFY pgrst, 'reload schema';
