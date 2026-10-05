-- Keep Web travel controls scoped to the exact NULL-Telegram user and selected Calendar binding.
CREATE OR REPLACE FUNCTION public.control_lm_web_travel(
  p_uid text,
  p_calendar_account_id text,
  p_action text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  user_row public.lm_users%ROWTYPE;
  automation_value boolean;
  changed integer;
BEGIN
  IF p_action IS NULL OR p_action NOT IN ('pause', 'resume', 'disconnect') THEN
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

  IF p_action = 'disconnect' AND p_calendar_account_id IS NULL THEN
    RAISE EXCEPTION 'calendar_not_connected';
  END IF;
  IF p_action = 'resume' AND nullif(trim(user_row.home_address), '') IS NULL THEN
    RAISE EXCEPTION 'home_required';
  END IF;

  automation_value := p_action = 'resume';
  UPDATE public.lm_panel_preferences
     SET daily_automation_enabled = automation_value
   WHERE uid = p_uid;
  GET DIAGNOSTICS changed = ROW_COUNT;
  IF changed <> 1 THEN RAISE EXCEPTION 'preference_missing'; END IF;

  IF p_action = 'disconnect' THEN
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
