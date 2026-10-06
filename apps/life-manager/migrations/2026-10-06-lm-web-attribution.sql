ALTER TABLE public.lm_users
  ADD COLUMN IF NOT EXISTS web_first_touch jsonb;
