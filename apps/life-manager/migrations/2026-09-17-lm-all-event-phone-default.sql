-- Paid phone reminders cover every timed commitment unless the user later selects travel-only.
ALTER TABLE public.lm_users ALTER COLUMN wake_policy SET DEFAULT 'all-events';
-- Keep existing user selections; a default cannot reveal which values were explicit.
