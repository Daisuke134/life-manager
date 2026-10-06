-- Web Calendar consent shares the existing state table while keeping its tenant scope distinct.
-- The raw provider state stays in the browser/OAuth redirect; only its SHA-256 digest is stored.
ALTER TABLE public.lm_panel_oauth_states
  ALTER COLUMN chat_id DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS lm_panel_oauth_states_live_web_uid_idx
  ON public.lm_panel_oauth_states (uid)
  WHERE chat_id IS NULL AND provider = 'calendar' AND used_at IS NULL;

CREATE OR REPLACE FUNCTION public.create_lm_web_calendar_oauth_state(
  p_state_hash text,
  p_uid text,
  p_provider text,
  p_expires_at timestamptz
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE eligible_uid text;
BEGIN
  IF p_state_hash IS NULL OR p_state_hash !~ '^[a-f0-9]{64}$'
     OR p_uid IS NULL OR p_uid = ''
     OR p_provider IS DISTINCT FROM 'calendar'
     OR p_expires_at IS NULL OR p_expires_at <= now() THEN
    RETURN false;
  END IF;

  SELECT uid INTO eligible_uid FROM public.lm_users
   WHERE uid = p_uid AND telegram_chat_id IS NULL
   FOR UPDATE;
  IF eligible_uid IS NULL THEN RETURN false; END IF;

  DELETE FROM public.lm_panel_oauth_states
   WHERE uid = p_uid
     AND chat_id IS NULL
     AND provider = p_provider
     AND (used_at IS NOT NULL OR expires_at <= now());

  BEGIN
    INSERT INTO public.lm_panel_oauth_states(state_hash, uid, chat_id, provider, expires_at)
    VALUES (p_state_hash, p_uid, NULL, p_provider, p_expires_at);
    RETURN true;
  EXCEPTION WHEN unique_violation THEN
    RETURN false;
  END;
END;
$$;

REVOKE ALL ON FUNCTION public.create_lm_web_calendar_oauth_state(text, text, text, timestamptz)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_lm_web_calendar_oauth_state(text, text, text, timestamptz)
  TO service_role;

CREATE OR REPLACE FUNCTION public.attach_lm_web_calendar_oauth_account(
  p_state_hash text,
  p_uid text,
  p_connected_account_id text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE changed integer;
BEGIN
  IF p_state_hash IS NULL OR p_state_hash !~ '^[a-f0-9]{64}$'
     OR p_connected_account_id IS NULL
     OR p_connected_account_id !~ '^[A-Za-z0-9_-]{3,128}$' THEN
    RETURN false;
  END IF;

  UPDATE public.lm_panel_oauth_states AS state
     SET connected_account_id = p_connected_account_id
   WHERE state.state_hash = p_state_hash
     AND state.uid = p_uid
     AND state.chat_id IS NULL
     AND state.provider = 'calendar'
     AND state.used_at IS NULL
     AND state.expires_at > now()
     AND state.connected_account_id IS NULL
     AND EXISTS (
       SELECT 1 FROM public.lm_users AS users
        WHERE users.uid = p_uid AND users.telegram_chat_id IS NULL
     );
  GET DIAGNOSTICS changed = ROW_COUNT;
  RETURN changed = 1;
END;
$$;

REVOKE ALL ON FUNCTION public.attach_lm_web_calendar_oauth_account(text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.attach_lm_web_calendar_oauth_account(text, text, text)
  TO service_role;

CREATE OR REPLACE FUNCTION public.claim_lm_web_calendar_oauth_account(
  p_state_hash text,
  p_uid text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE claimed_account_id text;
BEGIN
  IF p_state_hash IS NULL OR p_state_hash !~ '^[a-f0-9]{64}$'
     OR p_uid IS NULL OR p_uid = '' THEN
    RETURN NULL;
  END IF;

  UPDATE public.lm_panel_oauth_states AS state
     SET used_at = now()
   WHERE state.state_hash = p_state_hash
     AND state.uid = p_uid
     AND state.chat_id IS NULL
     AND state.provider = 'calendar'
     AND state.used_at IS NULL
     AND state.expires_at > now()
     AND state.connected_account_id IS NOT NULL
     AND EXISTS (
       SELECT 1 FROM public.lm_users AS users
        WHERE users.uid = p_uid AND users.telegram_chat_id IS NULL
     )
  RETURNING state.connected_account_id INTO claimed_account_id;
  RETURN claimed_account_id;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_lm_web_calendar_oauth_account(text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_lm_web_calendar_oauth_account(text, text)
  TO service_role;
