ALTER TABLE public.lm_maritime_manager_enrollments
  ADD COLUMN IF NOT EXISTS email_verified_at timestamptz;

COMMENT ON COLUMN public.lm_maritime_manager_enrollments.email_verified_at IS
  'Trusted auth-provider confirmation timestamp for the signup address captured at enrollment; null blocks Cloud billing and report email.';
