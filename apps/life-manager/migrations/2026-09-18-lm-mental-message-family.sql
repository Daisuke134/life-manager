-- V1 routine MENTAL receipts. Existing rows remain intact and are backfilled as legacy.
ALTER TABLE public.lm_mental_send_log
  ADD COLUMN IF NOT EXISTS family text,
  ADD COLUMN IF NOT EXISTS template_id text,
  ADD COLUMN IF NOT EXISTS local_day date,
  ADD COLUMN IF NOT EXISTS "window" text;

UPDATE public.lm_mental_send_log
SET family = COALESCE(family, 'legacy'),
    template_id = COALESCE(template_id, trigger),
    local_day = COALESCE(local_day, (sent_at AT TIME ZONE 'UTC')::date),
    "window" = COALESCE("window", 'legacy')
 WHERE family IS NULL OR template_id IS NULL OR local_day IS NULL OR "window" IS NULL;

ALTER TABLE public.lm_mental_send_log
  ALTER COLUMN family SET NOT NULL,
  ALTER COLUMN template_id SET NOT NULL,
  ALTER COLUMN local_day SET NOT NULL,
  ALTER COLUMN "window" SET NOT NULL;

DO $$
DECLARE
  names text[];
  found int;
BEGIN
  SELECT array_agg(conname ORDER BY conname) INTO names
  FROM pg_constraint
  WHERE conrelid = 'public.lm_mental_send_log'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) ILIKE '%pre_sleep%';
  found := coalesce(array_length(names, 1), 0);
  IF found > 1 THEN
    RAISE EXCEPTION 'lm_mental_send_log: ambiguous trigger checks: [%]', array_to_string(names, ', ');
  END IF;
  IF found = 1 THEN
    EXECUTE format('ALTER TABLE public.lm_mental_send_log DROP CONSTRAINT %I', names[1]);
  END IF;
END $$;

ALTER TABLE public.lm_mental_send_log
  ADD CONSTRAINT lm_mental_send_log_trigger_check
  CHECK (trigger IN ('pre_event', 'between_events', 'pre_sleep', 'precepts', 'precepts_mirror', 'relations',
                     'morning_orientation', 'midday_awareness', 'evening_direction'));

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.lm_mental_send_log'::regclass AND conname = 'lm_mental_send_log_family_check') THEN
    ALTER TABLE public.lm_mental_send_log ADD CONSTRAINT lm_mental_send_log_family_check
      CHECK (family IN ('legacy', 'affirmation', 'manifestation', 'mindfulness_inquiry'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.lm_mental_send_log'::regclass AND conname = 'lm_mental_send_log_window_check') THEN
    ALTER TABLE public.lm_mental_send_log ADD CONSTRAINT lm_mental_send_log_window_check
      CHECK ("window" IN ('legacy', 'morning_orientation', 'midday_awareness', 'evening_direction'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.lm_mental_send_log'::regclass AND conname = 'lm_mental_send_log_template_check') THEN
    ALTER TABLE public.lm_mental_send_log ADD CONSTRAINT lm_mental_send_log_template_check
      CHECK (char_length(template_id) BETWEEN 1 AND 200);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS lm_mental_send_log_uid_local_day
  ON public.lm_mental_send_log (uid, local_day DESC, "window");
