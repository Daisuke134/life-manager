-- PostgREST schema introspection was canceled at the authenticator role's 8s
-- statement timeout. Allow catalog/schema-cache reads 15s, leave lock_timeout intact,
-- then recreate the PostgREST pool and rebuild the schema cache.
ALTER ROLE authenticator SET statement_timeout = '15s';

NOTIFY pgrst, 'reload config';
NOTIFY pgrst, 'reload schema';
