-- Result reports use an explicit owner channel and one receipt per cadence period.
ALTER TABLE public.lm_users
  ADD COLUMN IF NOT EXISTS cfo_report_channel text NOT NULL DEFAULT 'email'
    CHECK (cfo_report_channel IN ('email', 'telegram', 'off')),
  ADD COLUMN IF NOT EXISTS cfo_report_cadence text NOT NULL DEFAULT 'hourly'
    CHECK (cfo_report_cadence IN ('hourly', 'daily'));

CREATE TABLE IF NOT EXISTS public.lm_cfo_result_receipts (
  uid text NOT NULL REFERENCES public.lm_users(uid) ON DELETE CASCADE,
  period_key text NOT NULL,
  channel text NOT NULL CHECK (channel = 'email'),
  recipient_hash text NOT NULL CHECK (recipient_hash ~ '^[0-9a-f]{64}$'),
  status text NOT NULL CHECK (status IN ('pending', 'sent')),
  message text NOT NULL,
  observed_at timestamptz NOT NULL,
  provider_message_id text,
  sent_at timestamptz,
  PRIMARY KEY (uid, period_key),
  CHECK ((status = 'sent' AND provider_message_id IS NOT NULL AND sent_at IS NOT NULL)
    OR (status = 'pending' AND provider_message_id IS NULL AND sent_at IS NULL))
);
ALTER TABLE public.lm_cfo_result_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.lm_cfo_result_receipts FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.lm_cfo_result_receipts TO service_role;
