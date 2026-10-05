-- Store Web travel setup atomically without changing Telegram or Stripe-owned fields.
CREATE OR REPLACE FUNCTION public.complete_lm_web_travel_setup(
  p_uid text,
  p_home_address text
) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  user_row public.lm_users%ROWTYPE;
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
  IF user_row.calendar_provider IS DISTINCT FROM 'composio_gcal'
     OR coalesce(user_row.calendar_connected_account_id, '') !~ '^[A-Za-z0-9_-]{3,128}$' THEN
    RAISE EXCEPTION 'calendar_not_active';
  END IF;

  UPDATE public.lm_users
     SET home_address = home_value,
         trial_expires_at = coalesce(trial_expires_at, now() + interval '3 days'),
         updated_at = now()
   WHERE uid = p_uid
  RETURNING trial_expires_at INTO trial_value;

  INSERT INTO public.lm_panel_preferences(uid, call_enabled, notifications_enabled, daily_automation_enabled)
  VALUES (p_uid, false, false, true)
  ON CONFLICT (uid) DO UPDATE SET
    call_enabled = false,
    notifications_enabled = false,
    daily_automation_enabled = true,
    updated_at = now();

  RETURN trial_value;
END;
$$;

REVOKE ALL ON FUNCTION public.complete_lm_web_travel_setup(text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.complete_lm_web_travel_setup(text, text) TO service_role;
