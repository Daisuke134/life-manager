#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATION="$ROOT_DIR/migrations/20261025134600_maritime_manager_capafy_bindings.sql"
MAILBOX_MIGRATION="$ROOT_DIR/migrations/20261025225517_maritime_manager_mailboxes.sql"
DB_NAME="maritime_capafy_rls_test"
DOCKER_NAME="maritime-capafy-rls-$$"

cleanup() {
  docker rm -f "$DOCKER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run --rm -d \
  --name "$DOCKER_NAME" \
  -e POSTGRES_PASSWORD=maritime-capafy-test-only \
  -e POSTGRES_DB="$DB_NAME" \
  postgres:18-alpine >/dev/null

for _ in {1..100}; do
  LOGS="$(docker logs "$DOCKER_NAME" 2>&1)"
  READY_COUNT="$(printf '%s\n' "$LOGS" | grep -Fc 'database system is ready to accept connections' || true)"
  if [[ "$LOGS" == *'PostgreSQL init process complete; ready for start up.'* && "$READY_COUNT" -ge 2 ]]; then
    break
  fi
  sleep 0.2
done
docker exec "$DOCKER_NAME" psql -X -Atqc 'SELECT 1' -U postgres -d "$DB_NAME" >/dev/null
docker exec -i "$DOCKER_NAME" psql -X -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" >/dev/null <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN;

CREATE TABLE public.lm_maritime_manager_enrollments (
  uid text PRIMARY KEY,
  auth_subject uuid NOT NULL UNIQUE,
  UNIQUE (uid, auth_subject)
);
INSERT INTO public.lm_maritime_manager_enrollments(uid, auth_subject)
VALUES ('lm_11111111-1111-4111-8111-111111111111',
        '11111111-1111-4111-8111-111111111111');
SQL

# Reapplying the migration must preserve the cursor, policies and grants.
docker exec -i "$DOCKER_NAME" psql -X -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" < "$MIGRATION" >/dev/null
docker exec -i "$DOCKER_NAME" psql -X -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" < "$MIGRATION" >/dev/null
docker exec -i "$DOCKER_NAME" psql -X -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" < "$MAILBOX_MIGRATION" >/dev/null
docker exec -i "$DOCKER_NAME" psql -X -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" < "$MAILBOX_MIGRATION" >/dev/null

[[ "$(docker exec "$DOCKER_NAME" psql -X -Atqc "SELECT rolbypassrls FROM pg_roles WHERE rolname='service_role'" -U postgres -d "$DB_NAME")" == "f" ]]

docker exec -i "$DOCKER_NAME" psql -X -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" >/dev/null <<'SQL'
SET ROLE service_role;
DO $$
BEGIN
  IF (SELECT count(*) FROM private.lm_maritime_manager_capafy_recovery_cursor
      WHERE cursor_key = 'cycle_admission') <> 1 THEN
    RAISE EXCEPTION 'service_role could not read seeded recovery cursor';
  END IF;

  INSERT INTO private.lm_maritime_manager_capafy_bindings (
    uid, auth_subject, provider_subject, account_ref, ciphertext, iv, tag,
    autonomy_consent_version, policy_consent_version, terms_accepted_at, terms_url, privacy_url
  ) VALUES (
    'lm_11111111-1111-4111-8111-111111111111',
    '11111111-1111-4111-8111-111111111111',
    '019d3c7f-fe51-7c57-aa2e-8e1055bb36a5',
    'account://capafy/lm_11111111-1111-4111-8111-111111111111/019d3c7f-fe51-7c57-aa2e-8e1055bb36a5',
    decode('ff', 'hex'), decode(repeat('00', 12), 'hex'), decode(repeat('00', 16), 'hex'),
    'maritime-capafy-autonomy-v1', 'capafy-publisher-terms-privacy-v1',
    '2026-10-25T11:59:00Z', 'https://api.capafy.ai/terms-of-service',
    'https://api.capafy.ai/privacy-policy'
  );
  IF (SELECT count(*) FROM private.lm_maritime_manager_capafy_bindings
      WHERE uid = 'lm_11111111-1111-4111-8111-111111111111') <> 1 THEN
    RAISE EXCEPTION 'service_role could not read inserted Capafy binding';
  END IF;
  DELETE FROM private.lm_maritime_manager_capafy_bindings
    WHERE uid = 'lm_11111111-1111-4111-8111-111111111111';
  IF EXISTS (SELECT 1 FROM private.lm_maritime_manager_capafy_bindings) THEN
    RAISE EXCEPTION 'service_role could not delete Capafy binding';
  END IF;

  INSERT INTO private.lm_maritime_manager_mailboxes (
    uid, auth_subject, inbox_id, email, client_id
  ) VALUES (
    'lm_11111111-1111-4111-8111-111111111111',
    '11111111-1111-4111-8111-111111111111',
    'inbox-tenant-a', 'lm-agent-a@agentmail.to',
    'life-manager-lm_11111111-1111-4111-8111-111111111111'
  );
  IF (SELECT count(*) FROM private.lm_maritime_manager_mailboxes
      WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
        AND auth_subject = '11111111-1111-4111-8111-111111111111') <> 1 THEN
    RAISE EXCEPTION 'service_role could not read tenant verification mailbox';
  END IF;

  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_status = 'starting',
         capafy_challenge_attempt_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
         capafy_challenge_started_at = '2026-10-25T12:00:00Z',
         capafy_challenge_expires_at = '2026-10-25T12:10:00Z'
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND auth_subject = '11111111-1111-4111-8111-111111111111'
     AND capafy_challenge_status IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'could not reserve mailbox challenge'; END IF;

  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_status = 'starting',
         capafy_challenge_attempt_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
         capafy_challenge_started_at = '2026-10-25T12:00:00Z',
         capafy_challenge_expires_at = '2026-10-25T12:10:00Z'
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND auth_subject = '11111111-1111-4111-8111-111111111111'
     AND (capafy_challenge_status IS NULL OR capafy_challenge_expires_at <= '2026-10-25T12:00:00Z');
  IF FOUND THEN RAISE EXCEPTION 'second active mailbox challenge reservation was allowed'; END IF;

  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_status = 'pending', capafy_challenge_attempt_id = NULL,
         capafy_challenge_id = 'challenge-one', capafy_challenge_expires_at = '2026-10-25T12:05:00Z'
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND capafy_challenge_status = 'starting'
     AND capafy_challenge_attempt_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  IF NOT FOUND THEN RAISE EXCEPTION 'could not bind provider challenge to reserved attempt'; END IF;

  UPDATE private.lm_maritime_manager_mailboxes SET capafy_challenge_status = 'verifying'
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND capafy_challenge_status = 'pending' AND capafy_challenge_id = 'different-challenge'
     AND capafy_challenge_expires_at > '2026-10-25T12:01:00Z';
  IF FOUND THEN RAISE EXCEPTION 'unbound challenge was allowed to claim mailbox OTP'; END IF;

  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_status = 'verifying',
         capafy_challenge_verification_lease_expires_at = '2026-10-25T12:06:30Z'
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND capafy_challenge_status = 'pending' AND capafy_challenge_id = 'challenge-one'
     AND capafy_challenge_expires_at > '2026-10-25T12:04:30Z';
  IF NOT FOUND THEN RAISE EXCEPTION 'bound challenge could not claim verification'; END IF;
  UPDATE private.lm_maritime_manager_mailboxes SET capafy_challenge_status = 'verifying'
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND capafy_challenge_status = 'pending' AND capafy_challenge_id = 'challenge-one'
     AND capafy_challenge_expires_at > '2026-10-25T12:01:00Z';
  IF FOUND THEN RAISE EXCEPTION 'parallel verification claim was allowed'; END IF;

  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_status = 'starting',
         capafy_challenge_attempt_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
         capafy_challenge_id = NULL,
         capafy_challenge_started_at = '2026-10-25T12:05:30Z',
         capafy_challenge_expires_at = '2026-10-25T12:10:30Z',
         capafy_challenge_verification_lease_expires_at = NULL
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND (capafy_challenge_status IS NULL
       OR (capafy_challenge_status IN ('starting','pending')
         AND capafy_challenge_expires_at <= '2026-10-25T12:05:30Z')
       OR (capafy_challenge_status = 'verifying'
         AND capafy_challenge_verification_lease_expires_at <= '2026-10-25T12:05:30Z'));
  IF FOUND THEN RAISE EXCEPTION 'expired code allowed takeover of a live verification lease'; END IF;

  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_verification_lease_expires_at = '2026-10-25T12:07:00Z'
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND capafy_challenge_status = 'verifying' AND capafy_challenge_id = 'challenge-one'
     AND capafy_challenge_expires_at > '2026-10-25T12:05:30Z'
     AND capafy_challenge_verification_lease_expires_at > '2026-10-25T12:05:30Z';
  IF FOUND THEN RAISE EXCEPTION 'expired challenge renewed its verification lease'; END IF;

  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_status = 'starting',
         capafy_challenge_attempt_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
         capafy_challenge_id = NULL,
         capafy_challenge_started_at = '2026-10-25T12:07:00Z',
         capafy_challenge_expires_at = '2026-10-25T12:17:00Z',
         capafy_challenge_verification_lease_expires_at = NULL
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND (capafy_challenge_status IS NULL
       OR (capafy_challenge_status IN ('starting','pending')
         AND capafy_challenge_expires_at <= '2026-10-25T12:07:00Z')
       OR (capafy_challenge_status = 'verifying'
         AND capafy_challenge_verification_lease_expires_at <= '2026-10-25T12:07:00Z'));
  IF NOT FOUND THEN RAISE EXCEPTION 'challenge could not be reserved after verification lease expiry'; END IF;
  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_verification_lease_expires_at = '2026-10-25T12:09:00Z'
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND capafy_challenge_status = 'verifying' AND capafy_challenge_id = 'challenge-one'
     AND capafy_challenge_expires_at > '2026-10-25T12:07:00Z'
     AND capafy_challenge_verification_lease_expires_at > '2026-10-25T12:07:00Z';
  IF FOUND THEN RAISE EXCEPTION 'old verification renewed after ownership changed'; END IF;

  BEGIN
    UPDATE private.lm_maritime_manager_mailboxes
       SET capafy_challenge_status = 'pending', capafy_challenge_attempt_id = NULL,
           capafy_challenge_id = NULL, capafy_challenge_expires_at = NULL
     WHERE uid = 'lm_11111111-1111-4111-8111-111111111111';
    RAISE EXCEPTION 'nullable pending challenge was allowed by check constraint';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_status = 'pending', capafy_challenge_attempt_id = NULL,
         capafy_challenge_id = 'challenge-two', capafy_challenge_started_at = '2026-10-25T12:07:00Z',
         capafy_challenge_expires_at = '2026-10-25T12:12:00Z',
         capafy_challenge_verification_lease_expires_at = NULL
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND capafy_challenge_status = 'starting'
     AND capafy_challenge_attempt_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
  IF NOT FOUND THEN RAISE EXCEPTION 'new provider challenge could not be bound'; END IF;
  UPDATE private.lm_maritime_manager_mailboxes
     SET capafy_challenge_status = NULL, capafy_challenge_attempt_id = NULL,
         capafy_challenge_id = NULL, capafy_challenge_started_at = NULL,
         capafy_challenge_expires_at = NULL,
         capafy_challenge_verification_lease_expires_at = NULL
   WHERE uid = 'lm_11111111-1111-4111-8111-111111111111'
     AND capafy_challenge_status = 'pending' AND capafy_challenge_id = 'challenge-two';
  IF NOT FOUND THEN RAISE EXCEPTION 'completed mailbox challenge was not cleared'; END IF;

  BEGIN
    INSERT INTO private.lm_maritime_manager_mailboxes (
      uid, auth_subject, inbox_id, email, client_id
    ) VALUES (
      'lm_22222222-2222-4222-8222-222222222222',
      '22222222-2222-4222-8222-222222222222',
      'inbox-tenant-b', 'lm-agent-b@agentmail.to',
      'life-manager-lm_22222222-2222-4222-8222-222222222222'
    );
    RAISE EXCEPTION 'mailbox was allowed for a non-enrolled tenant';
  EXCEPTION WHEN foreign_key_violation THEN
    NULL;
  END;

  DELETE FROM private.lm_maritime_manager_mailboxes
    WHERE uid = 'lm_11111111-1111-4111-8111-111111111111';
  IF EXISTS (SELECT 1 FROM private.lm_maritime_manager_mailboxes) THEN
    RAISE EXCEPTION 'service_role could not delete verification mailbox';
  END IF;

  UPDATE private.lm_maritime_manager_capafy_recovery_cursor
     SET completed_at = '2026-10-25T12:00:00Z',
         tenant_id = 'lm_11111111-1111-4111-8111-111111111111',
         job_id = 'maritime-cycle:' || repeat('a', 64),
         updated_at = clock_timestamp()
   WHERE cursor_key = 'cycle_admission';
  IF NOT EXISTS (
    SELECT 1 FROM private.lm_maritime_manager_capafy_recovery_cursor
     WHERE cursor_key = 'cycle_admission'
       AND completed_at = '2026-10-25T12:00:00Z'
       AND tenant_id = 'lm_11111111-1111-4111-8111-111111111111'
       AND job_id = 'maritime-cycle:' || repeat('a', 64)
  ) THEN
    RAISE EXCEPTION 'service_role could not update and read recovery cursor';
  END IF;
END $$;
RESET ROLE;

DO $$
BEGIN
  IF has_table_privilege('anon', 'private.lm_maritime_manager_capafy_bindings', 'SELECT')
     OR has_table_privilege('authenticated', 'private.lm_maritime_manager_capafy_bindings', 'SELECT')
     OR has_table_privilege('anon', 'private.lm_maritime_manager_capafy_recovery_cursor', 'SELECT')
     OR has_table_privilege('authenticated', 'private.lm_maritime_manager_capafy_recovery_cursor', 'SELECT') THEN
    RAISE EXCEPTION 'browser role has private table privileges';
  END IF;
  IF has_schema_privilege('anon', 'private', 'USAGE')
     OR has_schema_privilege('authenticated', 'private', 'USAGE') THEN
    RAISE EXCEPTION 'browser role has private schema usage';
  END IF;
  IF has_table_privilege('anon', 'private.lm_maritime_manager_mailboxes', 'SELECT')
     OR has_table_privilege('authenticated', 'private.lm_maritime_manager_mailboxes', 'SELECT') THEN
    RAISE EXCEPTION 'browser role has private mailbox table privileges';
  END IF;
END $$;
SQL

for role in anon authenticated; do
  if docker exec "$DOCKER_NAME" psql -X -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" \
    -c "SET ROLE $role; SELECT count(*) FROM private.lm_maritime_manager_capafy_bindings;" >/dev/null 2>&1; then
    printf 'FAIL %s read private Capafy binding table\n' "$role" >&2
    exit 1
  fi
  if docker exec "$DOCKER_NAME" psql -X -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" \
    -c "SET ROLE $role; SELECT count(*) FROM private.lm_maritime_manager_capafy_recovery_cursor;" >/dev/null 2>&1; then
    printf 'FAIL %s read private recovery cursor\n' "$role" >&2
    exit 1
  fi
  if docker exec "$DOCKER_NAME" psql -X -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" \
    -c "SET ROLE $role; SELECT count(*) FROM private.lm_maritime_manager_mailboxes;" >/dev/null 2>&1; then
    printf 'FAIL %s read private tenant mailbox table\n' "$role" >&2
    exit 1
  fi
done

printf '%s\n' 'Capafy binding, mailbox and recovery-cursor RLS/grants, service_role operations and migration idempotency: ok'
