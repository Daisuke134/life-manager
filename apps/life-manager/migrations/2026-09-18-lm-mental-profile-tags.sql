-- Explicit source-backed mental profile only. Raw Telegram/mail text never enters this table.
CREATE TABLE IF NOT EXISTS public.lm_mental_profile_tags (
  id bigserial PRIMARY KEY,
  uid text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('theme', 'tone', 'goal', 'avoid')),
  tag text NOT NULL,
  weight numeric NOT NULL CHECK (weight > 0 AND weight <= 10),
  basis text NOT NULL CHECK (basis IN ('explicit_user_statement', 'explicit_goal', 'explicit_correction')),
  explicit boolean NOT NULL CHECK (explicit = true),
  source_ref_hash text NOT NULL CHECK (source_ref_hash ~ '^[0-9a-f]{64}$'),
  observed_at timestamptz NOT NULL,
  expires_at timestamptz,
  superseded_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (uid, kind, tag, source_ref_hash)
);

CREATE INDEX IF NOT EXISTS lm_mental_profile_tags_uid_observed
  ON public.lm_mental_profile_tags (uid, observed_at DESC);

ALTER TABLE public.lm_mental_profile_tags ENABLE ROW LEVEL SECURITY;
