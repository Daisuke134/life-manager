# Test case 1 — diagnose + one play + asset

## Input
"We get 5,000 visits/mo to our landing page but only 1% sign up for the free trial. B2B SaaS, $30/mo. We've tried changing the headline twice. What's the one thing to fix?"

## Expected output (semantic match)
- Steps shown (Diagnose → Prescribe ONE play → Build the asset → Define success).
- Diagnosis: locates the bottleneck (activation/conversion at the signup step) with hypotheses from the given facts (1% conversion, headline-only changes tried).
- ONE highest-leverage play (not a list of 12), justified by a proven tactic + the psychology of why it works; says what it will/won't fix.
- The asset drafted (e.g., a rewritten above-the-fold + a single experiment design).
- Success metric named; no invented benchmarks; assumptions labeled; gaps flagged [ADD: …].
- NO claim of browsing their site or pulling live competitor data.

## Pass criteria
A focused diagnosis + exactly ONE prescribed play (with the principle behind it) + a ready asset + a success metric, reasoning only from the user's input and marketing knowledge, with zero fabricated metrics and zero live-research claims.
