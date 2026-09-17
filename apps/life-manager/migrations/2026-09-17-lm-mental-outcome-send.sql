-- Receipt-only outcome bridge. Raw Gmail subject/body/snippet never enters this table.
CREATE TABLE IF NOT EXISTS lm_mental_outcome_send_log (
  id bigserial PRIMARY KEY,
  uid text NOT NULL,
  source_outcome_id text NOT NULL,
  evidence_ref text NOT NULL,
  quote_id text NOT NULL,
  telegram_message_id text NOT NULL,
  sent_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (uid, source_outcome_id),
  UNIQUE (telegram_message_id)
);

CREATE INDEX IF NOT EXISTS lm_mental_outcome_send_uid_sent_at
  ON lm_mental_outcome_send_log (uid, sent_at DESC);

ALTER TABLE lm_mental_outcome_send_log ENABLE ROW LEVEL SECURITY;
