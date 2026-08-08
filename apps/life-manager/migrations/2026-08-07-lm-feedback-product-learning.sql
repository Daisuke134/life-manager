ALTER TABLE public.lm_feedback_intake
  ADD COLUMN IF NOT EXISTS source_event_id text,
  ADD COLUMN IF NOT EXISTS user_segment text,
  ADD COLUMN IF NOT EXISTS opportunity text,
  ADD COLUMN IF NOT EXISTS desired_outcome text,
  ADD COLUMN IF NOT EXISTS evidence text,
  ADD COLUMN IF NOT EXISTS proposed_assumption_test text,
  ADD COLUMN IF NOT EXISTS success_metric text;

ALTER TABLE public.lm_feedback_intake
  ADD CONSTRAINT lm_feedback_intake_product_learning_complete CHECK (
    (source_event_id IS NULL AND user_segment IS NULL AND opportunity IS NULL
      AND desired_outcome IS NULL AND evidence IS NULL
      AND proposed_assumption_test IS NULL AND success_metric IS NULL)
    OR (source_event_id IS NOT NULL AND user_segment IS NOT NULL AND opportunity IS NOT NULL
      AND desired_outcome IS NOT NULL AND evidence IS NOT NULL
      AND proposed_assumption_test IS NOT NULL AND success_metric IS NOT NULL)
  );
