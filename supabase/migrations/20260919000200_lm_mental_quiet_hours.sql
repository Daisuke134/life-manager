-- Canonical Supabase CLI copy of apps/life-manager/migrations/2026-09-18-lm-mental-quiet-hours.sql.
-- Explicit per-user MENTAL quiet hours. NULL/NULL means no configured quiet-hours override.
ALTER TABLE public.lm_panel_preferences
  ADD COLUMN IF NOT EXISTS mental_quiet_start_minute integer,
  ADD COLUMN IF NOT EXISTS mental_quiet_end_minute integer;

CREATE OR REPLACE FUNCTION public.mutate_lm_panel_preferences(p_uid text, p_chat_id text, p_patch jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE result jsonb;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.lm_users WHERE uid = p_uid AND telegram_chat_id::text = p_chat_id) THEN RAISE EXCEPTION 'scope_mismatch'; END IF;
  INSERT INTO public.lm_panel_preferences(uid) VALUES (p_uid) ON CONFLICT (uid) DO NOTHING;
  UPDATE public.lm_panel_preferences SET
    call_enabled = COALESCE((p_patch->>'call_enabled')::boolean, call_enabled),
    notifications_enabled = COALESCE((p_patch->>'notifications_enabled')::boolean, notifications_enabled),
    daily_automation_enabled = COALESCE((p_patch->>'daily_automation_enabled')::boolean, daily_automation_enabled),
    call_time_zone = COALESCE(p_patch->>'call_time_zone', call_time_zone),
    mental_quiet_start_minute = CASE WHEN p_patch ? 'mental_quiet_start_minute' THEN (p_patch->>'mental_quiet_start_minute')::integer ELSE mental_quiet_start_minute END,
    mental_quiet_end_minute = CASE WHEN p_patch ? 'mental_quiet_end_minute' THEN (p_patch->>'mental_quiet_end_minute')::integer ELSE mental_quiet_end_minute END,
    updated_at = now()
  WHERE uid = p_uid RETURNING to_jsonb(lm_panel_preferences.*) INTO result;
  RETURN result;
END $$;

REVOKE ALL ON FUNCTION public.mutate_lm_panel_preferences(text,text,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.mutate_lm_panel_preferences(text,text,jsonb) TO service_role;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.lm_panel_preferences'::regclass
      AND conname = 'lm_panel_preferences_mental_quiet_start_check'
  ) THEN
    ALTER TABLE public.lm_panel_preferences
      ADD CONSTRAINT lm_panel_preferences_mental_quiet_start_check
      CHECK (mental_quiet_start_minute IS NULL OR mental_quiet_start_minute BETWEEN 0 AND 1440);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.lm_panel_preferences'::regclass
      AND conname = 'lm_panel_preferences_mental_quiet_end_check'
  ) THEN
    ALTER TABLE public.lm_panel_preferences
      ADD CONSTRAINT lm_panel_preferences_mental_quiet_end_check
      CHECK (mental_quiet_end_minute IS NULL OR mental_quiet_end_minute BETWEEN 0 AND 1440);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.lm_panel_preferences'::regclass
      AND conname = 'lm_panel_preferences_mental_quiet_pair_check'
  ) THEN
    ALTER TABLE public.lm_panel_preferences
      ADD CONSTRAINT lm_panel_preferences_mental_quiet_pair_check
      CHECK ((mental_quiet_start_minute IS NULL) = (mental_quiet_end_minute IS NULL));
  END IF;
END $$;
