-- Signed owner projections only. Raw Gmail subject/body/snippet never enters this table.
CREATE TABLE IF NOT EXISTS lm_verified_outcomes (
  id bigserial PRIMARY KEY,
  uid text NOT NULL,
  source_outcome_id text NOT NULL UNIQUE,
  kind text NOT NULL CHECK (kind IN ('interview', 'offer', 'rejection')),
  company text NOT NULL CHECK (char_length(company) BETWEEN 1 AND 200),
  role text NOT NULL CHECK (char_length(role) BETWEEN 1 AND 300),
  verified_at timestamptz NOT NULL,
  evidence_ref text NOT NULL CHECK (char_length(evidence_ref) BETWEEN 1 AND 512),
  received_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lm_verified_outcomes_uid_verified_at
  ON lm_verified_outcomes (uid, verified_at DESC);

ALTER TABLE lm_verified_outcomes ENABLE ROW LEVEL SECURITY;
