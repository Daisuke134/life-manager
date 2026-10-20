-- Bound one schema-cache recovery experiment: pg_timezone_names was repeatedly
-- cancelled at the authenticator's 15s timeout. Preserve service_role's previous
-- effective 15s explicitly; anon/authenticated and lock_timeout stay unchanged.
-- PostgREST role-map failure can still fall back to the login role's timeout.
ALTER ROLE service_role SET statement_timeout = '15s';
ALTER ROLE authenticator SET statement_timeout = '60s';

NOTIFY pgrst, 'reload config';
NOTIFY pgrst, 'reload schema';
