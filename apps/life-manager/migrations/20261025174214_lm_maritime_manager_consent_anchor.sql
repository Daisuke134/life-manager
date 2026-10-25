ALTER TABLE public.lm_maritime_manager_enrollments
  ADD COLUMN IF NOT EXISTS consent_v2_at timestamptz;

COMMENT ON COLUMN public.lm_maritime_manager_enrollments.consent_v2_at IS
  'Timestamp when a legacy Life Manager Cloud tenant accepted manager consent v2; null for tenants without a recorded v1-to-v2 re-consent.';
