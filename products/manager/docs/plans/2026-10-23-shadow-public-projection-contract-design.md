# Shadow public projection consistency design

Fix the reproduced automated review finding on PR8710 comment4359623048. The public P0 projection currently accepts COMPARED_P0/DISABLED and COMPARED_P0 without comparison evidence. Main6b5390133 includes the prepared/store boundary; this follow-up changes only consistency validation before connecting it to the host. The user authorized routine decisions and agent-first execution and opted out of repeated design questions.

Reuse the existing projection, its parsed values, enum/date/hash/decision checks, and fixed19-key output. Alternatives: leave inconsistent public states accepted; reuse the existing validator and add cross-field invariants (selected); or invoke the whole private saved-result validator (rejected: it calls the projection, would recurse, and would unnecessarily require/redact private IDs). No new validation engine or dependency.

Status and reason form one contract: COMPARED_P0 only MODEL_RESPONSE_PARSED; UNKNOWN only PLANNER_UNCERTAIN/PRIOR_INTENT_RECONCILIATION_REQUIRED/PROVIDER_TRANSPORT_UNKNOWN/INPUT_BINDING_MISMATCH; SKIPPED only the remaining existing skip reasons. Derive any all-reasons set from that mapping rather than duplicate it.

COMPARED_P0 requires a UTC comparison time, all four public identities/digests, both baseline decisions, and MODEL_ADVICE_P0 or INVALID_MODEL_OUTPUT. Valid model advice requires a decision and both exact comparison booleans equal to its comparison with baseline decisions. Invalid output has no model decision/advice or comparison evidence. Non-compared results have no completed timestamp/model evidence; already available baseline/hash fields remain allowed, and absent/None model fields remain compatible.

Keep unknown private fields ignored, not copied; a private reason or provider-ID marker must not leak or become required for this projection. This validates record consistency, not authentic remote completion. P0, no authority, writes0, costNone, and human outcomeNOT_MEASURED remain unchanged. Do not change storage/provider/parser/schema/host/CLI/workflow/runtime, make model requests, or alter80/30/3.

Acceptance: reproduce the reported combinations; reject missing or contradictory completed evidence and model evidence on non-completed states; preserve existing valid compared/invalid/unknown/skipped cases, privacy projection, saved-result restore, and all current432 tests. Dedicated tests use actual existing offline comparison fixtures. Fresh task and whole-branch reviews, exact-head CI, and normal main integration remain required.
