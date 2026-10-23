-- Private mutable state, outside Git/artifacts. No row is seeded by this
-- migration. Missing state fails closed; bootstrap/backup restore is an
-- operator procedure requiring provider reconciliation before any send.
CREATE TABLE public.lm_manager_owned_state (
  stream text PRIMARY KEY CHECK (stream = 'manager-owned-digital-v1'),
  revision bigint NOT NULL CHECK (revision BETWEEN 0 AND 9007199254740991),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  snapshot text NOT NULL CHECK (
    length(snapshot) BETWEEN 4 AND 1398104
    AND octet_length(decode(snapshot, 'base64')) BETWEEN 1 AND 1048576
    AND snapshot = replace(replace(encode(decode(snapshot, 'base64'), 'base64'), E'\n', ''), E'\r', '')
    AND sha256 = encode(sha256(decode(snapshot, 'base64')), 'hex')
  ),
  owner text CHECK (owner ~ '^[1-9][0-9]{0,19}:[1-9][0-9]{0,19}:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'),
  lease_until timestamptz,
  recovery_required boolean NOT NULL DEFAULT false,
  CHECK ((owner IS NULL) = (lease_until IS NULL))
);
ALTER TABLE public.lm_manager_owned_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lm_manager_owned_state FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lm_manager_owned_state FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, UPDATE ON TABLE public.lm_manager_owned_state TO service_role;

CREATE FUNCTION public.lm_manager_owned_checkpoint(
  p_operation text, p_owner text, p_revision bigint, p_sha256 text, p_snapshot text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_state public.lm_manager_owned_state%ROWTYPE;
  v_bytes bytea;
BEGIN
  IF p_operation IS NULL OR p_operation NOT IN ('acquire', 'checkpoint', 'release')
    OR p_owner IS NULL
    OR p_owner !~ '^[1-9][0-9]{0,19}:[1-9][0-9]{0,19}:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    RAISE SQLSTATE 'PT400' USING MESSAGE = 'invalid request';
  END IF;
  IF p_operation <> 'checkpoint' AND
    (p_revision IS NOT NULL OR p_sha256 IS NOT NULL OR p_snapshot IS NOT NULL) THEN
    RAISE SQLSTATE 'PT400' USING MESSAGE = 'invalid request';
  END IF;
  IF p_operation = 'checkpoint' THEN
    IF p_revision IS NULL OR p_revision NOT BETWEEN 0 AND 9007199254740990
      OR p_sha256 IS NULL OR p_sha256 !~ '^[0-9a-f]{64}$'
      OR p_snapshot IS NULL OR length(p_snapshot) NOT BETWEEN 4 AND 1398104
      OR p_snapshot !~ '^[A-Za-z0-9+/]*={0,2}$' THEN
      RAISE SQLSTATE 'PT400' USING MESSAGE = 'invalid checkpoint';
    END IF;
    BEGIN
      v_bytes := decode(p_snapshot, 'base64');
    EXCEPTION WHEN OTHERS THEN
      RAISE SQLSTATE 'PT400' USING MESSAGE = 'invalid checkpoint';
    END;
    IF octet_length(v_bytes) NOT BETWEEN 1 AND 1048576
      OR p_snapshot <> replace(replace(encode(v_bytes, 'base64'), E'\n', ''), E'\r', '')
      OR p_sha256 <> encode(sha256(v_bytes), 'hex') THEN
      RAISE SQLSTATE 'PT400' USING MESSAGE = 'invalid checkpoint';
    END IF;
  END IF;

  SELECT * INTO v_state FROM public.lm_manager_owned_state
  WHERE stream = 'manager-owned-digital-v1' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE SQLSTATE 'PT404' USING MESSAGE = 'state unavailable';
  END IF;
  IF v_state.recovery_required AND p_operation IN ('acquire', 'checkpoint') THEN
    RAISE SQLSTATE 'PT409' USING MESSAGE = 'recovery required';
  END IF;
  IF p_operation = 'acquire' THEN
    -- An expired owner loses write authority, never its saved UNKNOWN intents.
    IF v_state.owner IS NOT NULL AND v_state.lease_until > clock_timestamp() THEN
      RAISE SQLSTATE 'PT409' USING MESSAGE = 'state conflict';
    END IF;
    UPDATE public.lm_manager_owned_state
    SET owner = p_owner, lease_until = clock_timestamp() + interval '15 minutes'
    WHERE stream = v_state.stream RETURNING * INTO v_state;
  ELSIF p_operation = 'checkpoint' THEN
    IF v_state.owner IS DISTINCT FROM p_owner
      OR v_state.lease_until IS NULL OR v_state.lease_until <= clock_timestamp()
      OR v_state.revision <> p_revision THEN
      RAISE SQLSTATE 'PT409' USING MESSAGE = 'state conflict';
    END IF;
    UPDATE public.lm_manager_owned_state
    SET revision = revision + 1, sha256 = p_sha256, snapshot = p_snapshot,
      lease_until = clock_timestamp() + interval '15 minutes'
    WHERE stream = v_state.stream RETURNING * INTO v_state;
  ELSE
    IF v_state.owner IS DISTINCT FROM p_owner THEN
      RAISE SQLSTATE 'PT409' USING MESSAGE = 'state conflict';
    END IF;
    UPDATE public.lm_manager_owned_state
    SET owner = NULL, lease_until = NULL
    WHERE stream = v_state.stream RETURNING * INTO v_state;
  END IF;
  RETURN jsonb_build_object('revision', v_state.revision, 'sha256', v_state.sha256,
    'snapshot', v_state.snapshot, 'owner', v_state.owner);
END;
$$;
REVOKE ALL ON FUNCTION public.lm_manager_owned_checkpoint(text,text,bigint,text,text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.lm_manager_owned_checkpoint(text,text,bigint,text,text)
  TO service_role;
