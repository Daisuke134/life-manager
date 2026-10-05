-- Keep Web travel controls scoped to the exact NULL-Telegram user and selected Calendar binding.
ALTER TABLE public.lm_panel_preferences
  ADD COLUMN IF NOT EXISTS calendar_disconnect_pending boolean NOT NULL DEFAULT false;

ALTER TABLE public.lm_users
  ADD COLUMN IF NOT EXISTS calendar_enable_pending boolean NOT NULL DEFAULT false;

CREATE OR REPLACE FUNCTION public.control_lm_web_travel(
  p_uid text,
  p_calendar_account_id text,
  p_action text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  user_row public.lm_users%ROWTYPE;
  preference_row public.lm_panel_preferences%ROWTYPE;
  changed integer;
BEGIN
  IF p_action IS NULL OR p_action NOT IN ('pause', 'resume', 'disconnect_begin', 'disconnect_finish') THEN
    RAISE EXCEPTION 'invalid_action';
  END IF;

  SELECT * INTO user_row
    FROM public.lm_users
   WHERE uid = p_uid AND telegram_chat_id IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'scope_mismatch'; END IF;

  IF p_calendar_account_id IS NULL THEN
    IF user_row.calendar_provider IS NOT NULL OR user_row.calendar_connected_account_id IS NOT NULL THEN
      RAISE EXCEPTION 'calendar_account_changed';
    END IF;
  ELSIF p_calendar_account_id !~ '^[A-Za-z0-9_-]{3,128}$'
     OR user_row.calendar_provider IS DISTINCT FROM 'composio_gcal'
     OR user_row.calendar_connected_account_id IS DISTINCT FROM p_calendar_account_id THEN
    RAISE EXCEPTION 'calendar_account_changed';
  END IF;

  IF p_action IN ('disconnect_begin', 'disconnect_finish') AND p_calendar_account_id IS NULL THEN
    RAISE EXCEPTION 'calendar_not_connected';
  END IF;
  IF p_action IN ('resume', 'disconnect_begin') AND user_row.calendar_enable_pending THEN
    RAISE EXCEPTION 'calendar_enable_pending';
  END IF;
  IF p_action = 'resume' AND nullif(trim(user_row.home_address), '') IS NULL THEN
    RAISE EXCEPTION 'home_required';
  END IF;

  IF p_action = 'pause' THEN
    -- Calendar OAuth can finish before home setup creates the Web preference row.
    INSERT INTO public.lm_panel_preferences(
      uid, call_enabled, notifications_enabled, daily_automation_enabled, calendar_disconnect_pending
    ) VALUES (p_uid, false, false, false, false)
    ON CONFLICT (uid) DO UPDATE SET daily_automation_enabled = false;
  ELSIF p_action = 'disconnect_begin' THEN
    -- Existing preference fields remain untouched; defaults are only for a missing Web row.
    INSERT INTO public.lm_panel_preferences(
      uid, call_enabled, notifications_enabled, daily_automation_enabled, calendar_disconnect_pending
    ) VALUES (p_uid, false, false, false, true)
    ON CONFLICT (uid) DO UPDATE SET
      daily_automation_enabled = false,
      calendar_disconnect_pending = true;
  ELSE
    SELECT * INTO preference_row
      FROM public.lm_panel_preferences
     WHERE uid = p_uid
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'preference_missing'; END IF;
    IF p_action = 'resume' AND preference_row.calendar_disconnect_pending THEN
      RAISE EXCEPTION 'calendar_disconnect_pending';
    END IF;
    IF p_action = 'disconnect_finish' AND NOT preference_row.calendar_disconnect_pending THEN
      RAISE EXCEPTION 'calendar_disconnect_pending';
    END IF;

    IF p_action = 'resume' THEN
      UPDATE public.lm_panel_preferences SET daily_automation_enabled = true WHERE uid = p_uid;
    ELSE
      UPDATE public.lm_panel_preferences
         SET daily_automation_enabled = false,
             calendar_disconnect_pending = false
       WHERE uid = p_uid;
    END IF;
  END IF;
  GET DIAGNOSTICS changed = ROW_COUNT;
  IF changed <> 1 THEN RAISE EXCEPTION 'preference_missing'; END IF;

  IF p_action = 'disconnect_finish' THEN
    UPDATE public.lm_users
       SET calendar_provider = NULL,
           calendar_connected_account_id = NULL
     WHERE uid = p_uid
       AND telegram_chat_id IS NULL
       AND calendar_provider = 'composio_gcal'
       AND calendar_connected_account_id = p_calendar_account_id;
    GET DIAGNOSTICS changed = ROW_COUNT;
    IF changed <> 1 THEN RAISE EXCEPTION 'calendar_account_changed'; END IF;
  END IF;

  RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.control_lm_web_travel(text, text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.control_lm_web_travel(text, text, text) TO service_role;

-- Serialize Calendar provider enables with disconnects using the same NULL-Telegram user lock.
CREATE OR REPLACE FUNCTION public.begin_lm_web_calendar_enable(
  p_uid text,
  p_calendar_account_id text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  user_row public.lm_users%ROWTYPE;
  preference_row public.lm_panel_preferences%ROWTYPE;
  changed integer;
BEGIN
  SELECT * INTO user_row
    FROM public.lm_users
   WHERE uid = p_uid AND telegram_chat_id IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'scope_mismatch'; END IF;
  IF p_calendar_account_id IS NULL
     OR p_calendar_account_id !~ '^[A-Za-z0-9_-]{3,128}$'
     OR user_row.calendar_provider IS DISTINCT FROM 'composio_gcal'
     OR user_row.calendar_connected_account_id IS DISTINCT FROM p_calendar_account_id THEN
    RAISE EXCEPTION 'calendar_account_changed';
  END IF;
  IF user_row.calendar_enable_pending THEN RETURN false; END IF;

  SELECT * INTO preference_row
    FROM public.lm_panel_preferences
   WHERE uid = p_uid
   FOR UPDATE;
  IF FOUND AND preference_row.calendar_disconnect_pending THEN
    RAISE EXCEPTION 'calendar_disconnect_pending';
  END IF;

  UPDATE public.lm_users
     SET calendar_enable_pending = true,
         updated_at = now()
   WHERE uid = p_uid AND telegram_chat_id IS NULL AND NOT calendar_enable_pending;
  GET DIAGNOSTICS changed = ROW_COUNT;
  RETURN changed = 1;
END;
$$;

REVOKE ALL ON FUNCTION public.begin_lm_web_calendar_enable(text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.begin_lm_web_calendar_enable(text, text) TO service_role;

CREATE OR REPLACE FUNCTION public.finish_lm_web_calendar_enable(
  p_uid text,
  p_calendar_account_id text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  user_row public.lm_users%ROWTYPE;
  preference_row public.lm_panel_preferences%ROWTYPE;
  changed integer;
BEGIN
  SELECT * INTO user_row
    FROM public.lm_users
   WHERE uid = p_uid AND telegram_chat_id IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'scope_mismatch'; END IF;
  IF p_calendar_account_id IS NULL
     OR user_row.calendar_provider IS DISTINCT FROM 'composio_gcal'
     OR user_row.calendar_connected_account_id IS DISTINCT FROM p_calendar_account_id THEN
    RAISE EXCEPTION 'calendar_account_changed';
  END IF;
  IF NOT user_row.calendar_enable_pending THEN RETURN false; END IF;

  SELECT * INTO preference_row
    FROM public.lm_panel_preferences
   WHERE uid = p_uid
   FOR UPDATE;
  IF FOUND AND preference_row.calendar_disconnect_pending THEN
    RAISE EXCEPTION 'calendar_disconnect_pending';
  END IF;

  UPDATE public.lm_users
     SET calendar_enable_pending = false,
         updated_at = now()
   WHERE uid = p_uid AND telegram_chat_id IS NULL
     AND calendar_provider = 'composio_gcal'
     AND calendar_connected_account_id = p_calendar_account_id
     AND calendar_enable_pending;
  GET DIAGNOSTICS changed = ROW_COUNT;
  RETURN changed = 1;
END;
$$;

REVOKE ALL ON FUNCTION public.finish_lm_web_calendar_enable(text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.finish_lm_web_calendar_enable(text, text) TO service_role;

-- OAuth callbacks and active-account recovery bind only while both control fences are clear.
CREATE OR REPLACE FUNCTION public.bind_lm_web_calendar_account(
  p_uid text,
  p_connected_account_id text,
  p_expected_calendar_provider text,
  p_expected_calendar_account_id text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  user_row public.lm_users%ROWTYPE;
  preference_row public.lm_panel_preferences%ROWTYPE;
  changed integer;
BEGIN
  SELECT * INTO user_row
    FROM public.lm_users
   WHERE uid = p_uid AND telegram_chat_id IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'scope_mismatch'; END IF;
  IF p_connected_account_id IS NULL OR p_connected_account_id !~ '^[A-Za-z0-9_-]{3,128}$'
     OR user_row.calendar_provider IS DISTINCT FROM p_expected_calendar_provider
     OR user_row.calendar_connected_account_id IS DISTINCT FROM p_expected_calendar_account_id THEN
    RAISE EXCEPTION 'calendar_account_changed';
  END IF;
  IF user_row.calendar_enable_pending THEN RAISE EXCEPTION 'calendar_enable_pending'; END IF;

  SELECT * INTO preference_row
    FROM public.lm_panel_preferences
   WHERE uid = p_uid
   FOR UPDATE;
  IF FOUND AND preference_row.calendar_disconnect_pending THEN
    RAISE EXCEPTION 'calendar_disconnect_pending';
  END IF;

  UPDATE public.lm_users
     SET calendar_provider = 'composio_gcal',
         calendar_connected_account_id = p_connected_account_id,
         updated_at = now()
   WHERE uid = p_uid AND telegram_chat_id IS NULL
     AND calendar_provider IS NOT DISTINCT FROM p_expected_calendar_provider
     AND calendar_connected_account_id IS NOT DISTINCT FROM p_expected_calendar_account_id;
  GET DIAGNOSTICS changed = ROW_COUNT;
  RETURN changed = 1;
END;
$$;

REVOKE ALL ON FUNCTION public.bind_lm_web_calendar_account(text, text, text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.bind_lm_web_calendar_account(text, text, text, text) TO service_role;

-- Reapply the earlier setup RPC after the disconnect fence exists. Both setup and controls lock the user row first.
CREATE OR REPLACE FUNCTION public.complete_lm_web_travel_setup(
  p_uid text,
  p_home_address text,
  p_calendar_account_id text
) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  user_row public.lm_users%ROWTYPE;
  preference_row public.lm_panel_preferences%ROWTYPE;
  preference_exists boolean;
  home_value text;
  trial_value timestamptz;
BEGIN
  home_value := trim(coalesce(p_home_address, ''));
  IF char_length(home_value) < 1 OR char_length(home_value) > 240 THEN
    RAISE EXCEPTION 'invalid_home_address';
  END IF;

  SELECT * INTO user_row
    FROM public.lm_users
   WHERE uid = p_uid AND telegram_chat_id IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'scope_mismatch'; END IF;
  IF user_row.calendar_enable_pending THEN
    RAISE EXCEPTION 'calendar_enable_pending';
  END IF;
  IF user_row.calendar_provider IS DISTINCT FROM 'composio_gcal' THEN
    RAISE EXCEPTION 'calendar_not_active';
  END IF;
  IF p_calendar_account_id IS NULL
     OR p_calendar_account_id !~ '^[A-Za-z0-9_-]{3,128}$'
     OR user_row.calendar_connected_account_id IS DISTINCT FROM p_calendar_account_id THEN
    RAISE EXCEPTION 'calendar_account_changed';
  END IF;

  SELECT * INTO preference_row
    FROM public.lm_panel_preferences
   WHERE uid = p_uid
   FOR UPDATE;
  preference_exists := FOUND;
  IF preference_exists AND preference_row.calendar_disconnect_pending THEN
    RAISE EXCEPTION 'calendar_disconnect_pending';
  END IF;

  UPDATE public.lm_users
     SET home_address = home_value,
         trial_expires_at = coalesce(trial_expires_at, now() + interval '3 days'),
         updated_at = now()
   WHERE uid = p_uid
  RETURNING trial_expires_at INTO trial_value;

  IF preference_exists THEN
    UPDATE public.lm_panel_preferences
       SET call_enabled = false,
           notifications_enabled = false,
           updated_at = now()
     WHERE uid = p_uid;
  ELSE
    INSERT INTO public.lm_panel_preferences(
      uid, call_enabled, notifications_enabled, daily_automation_enabled, calendar_disconnect_pending
    ) VALUES (p_uid, false, false, true, false);
  END IF;

  RETURN trial_value;
END;
$$;

REVOKE ALL ON FUNCTION public.complete_lm_web_travel_setup(text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.complete_lm_web_travel_setup(text, text, text)
  TO service_role;
