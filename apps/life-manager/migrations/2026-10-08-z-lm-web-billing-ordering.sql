-- Web billing uses per-stream event cursors and an optimistic row revision.
-- A Stripe invoice and subscription update are independent evidence streams; keeping separate cursors
-- lets a paid invoice restore a just-expired trial even when its event was created earlier.
ALTER TABLE public.lm_users
  ADD COLUMN IF NOT EXISTS web_billing_revision bigint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS web_billing_cancel_at_period_end boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS web_automation_resume_pending boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS web_automation_user_paused boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS web_trial_payment_method_present boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS web_subscription_created_at timestamptz,
  ADD COLUMN IF NOT EXISTS web_subscription_event_at timestamptz,
  ADD COLUMN IF NOT EXISTS web_subscription_event_priority smallint,
  ADD COLUMN IF NOT EXISTS web_subscription_event_id text,
  ADD COLUMN IF NOT EXISTS web_subscription_latest_invoice_id text,
  ADD COLUMN IF NOT EXISTS web_invoice_event_at timestamptz,
  ADD COLUMN IF NOT EXISTS web_invoice_event_priority smallint,
  ADD COLUMN IF NOT EXISTS web_invoice_event_id text,
  ADD COLUMN IF NOT EXISTS web_invoice_id text,
  ADD COLUMN IF NOT EXISTS web_invoice_subscription_id text,
  ADD COLUMN IF NOT EXISTS web_invoice_paid boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS web_invoice_amount_paid bigint;

-- Serialize user pauses with billing activation so a webhook retry cannot undo an explicit pause.
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
  IF p_action IS NULL OR p_action NOT IN ('pause', 'initial_scan_pause', 'resume', 'disconnect_begin', 'disconnect_finish') THEN
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

  IF p_action IN ('pause', 'disconnect_begin') THEN
    UPDATE public.lm_users
       SET web_automation_resume_pending = false,
           web_automation_user_paused = true,
           web_billing_revision = web_billing_revision + 1,
           updated_at = now()
     WHERE uid = p_uid AND telegram_chat_id IS NULL;
  ELSIF p_action = 'resume' THEN
    UPDATE public.lm_users
       SET web_automation_user_paused = false,
           web_billing_revision = web_billing_revision + 1,
           updated_at = now()
     WHERE uid = p_uid AND telegram_chat_id IS NULL;
  END IF;

  IF p_action IN ('pause', 'initial_scan_pause') THEN
    INSERT INTO public.lm_panel_preferences(
      uid, call_enabled, notifications_enabled, daily_automation_enabled, calendar_disconnect_pending
    ) VALUES (p_uid, false, false, false, false)
    ON CONFLICT (uid) DO UPDATE SET daily_automation_enabled = false;
  ELSIF p_action = 'disconnect_begin' THEN
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

REVOKE ALL ON FUNCTION public.control_lm_web_travel(text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.control_lm_web_travel(text, text, text)
  TO service_role;

-- A one-shot billing activation may enable automation only while its persisted intent is pending.
CREATE OR REPLACE FUNCTION public.resume_lm_web_billing_automation(
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
  IF user_row.web_automation_resume_pending IS DISTINCT FROM true THEN RETURN true; END IF;
  IF user_row.web_automation_user_paused IS TRUE THEN
    UPDATE public.lm_users
       SET web_automation_resume_pending = false,
           web_billing_revision = web_billing_revision + 1,
           updated_at = now()
     WHERE uid = p_uid AND telegram_chat_id IS NULL;
    RETURN true;
  END IF;
  IF user_row.calendar_enable_pending THEN RAISE EXCEPTION 'calendar_enable_pending'; END IF;

  SELECT * INTO preference_row
    FROM public.lm_panel_preferences
   WHERE uid = p_uid
   FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'preference_missing'; END IF;

  IF preference_row.calendar_disconnect_pending THEN
    UPDATE public.lm_users
       SET web_automation_resume_pending = false,
           web_billing_revision = web_billing_revision + 1,
           updated_at = now()
     WHERE uid = p_uid AND telegram_chat_id IS NULL;
    RETURN true;
  END IF;

  IF user_row.web_billing_cancel_at_period_end IS DISTINCT FROM false
     OR user_row.plan_status IS NULL
     OR user_row.plan_status NOT IN ('active', 'trialing')
     OR (user_row.plan_status = 'trialing'
       AND (user_row.web_trial_payment_method_present IS DISTINCT FROM true
         OR user_row.trial_expires_at IS NULL OR user_row.trial_expires_at <= now())) THEN
    UPDATE public.lm_users
       SET web_automation_resume_pending = false,
           web_billing_revision = web_billing_revision + 1,
           updated_at = now()
     WHERE uid = p_uid AND telegram_chat_id IS NULL;
    RETURN true;
  END IF;

  -- An active subscription created from a paid Checkout can precede its invoice.paid webhook.
  -- Keep the intent pending, but do not enable automation until that exact invoice is verified.
  IF user_row.plan_status = 'active' AND user_row.paid IS DISTINCT FROM true THEN
    RETURN true;
  END IF;

  UPDATE public.lm_panel_preferences
     SET daily_automation_enabled = true
   WHERE uid = p_uid;
  GET DIAGNOSTICS changed = ROW_COUNT;
  IF changed <> 1 THEN RAISE EXCEPTION 'preference_missing'; END IF;

  UPDATE public.lm_users
     SET web_automation_resume_pending = false,
         web_billing_revision = web_billing_revision + 1,
         updated_at = now()
   WHERE uid = p_uid AND telegram_chat_id IS NULL;
  GET DIAGNOSTICS changed = ROW_COUNT;
  IF changed <> 1 THEN RAISE EXCEPTION 'scope_mismatch'; END IF;

  RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.resume_lm_web_billing_automation(text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.resume_lm_web_billing_automation(text, text)
  TO service_role;
