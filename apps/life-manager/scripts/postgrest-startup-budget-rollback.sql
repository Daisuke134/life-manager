-- Restore the observed baseline after an unsuccessful startup-budget experiment.
-- A successful command is not proof that existing PostgREST sessions reconnected.
ALTER ROLE authenticator SET statement_timeout = '15s';
ALTER ROLE service_role RESET statement_timeout;

NOTIFY pgrst, 'reload config';
NOTIFY pgrst, 'reload schema';
