# Product connection — how Anicca events become Manager cases

**Status: format defined and verified on fixtures; live product cases: 0.**
The blocker is app-side and specific (§3). This document is the hand-off
spec for the app lane (Phase 1): implement the export below and product
deliveries start flowing into ManagerBench and Manager training in the
exact shape the Hillstrom v0 pipeline already consumes.

## 1. The common shape

Every Manager case — benchmark or training — is one randomized decision
point in the ManagerBench intervention-case schema v1
(`intervention-case-schema-v1.json`, copied byte-identically from
anicca-ops `files/eval/managerbench/`):

*situation* (`personal_history`, observed before assignment) →
*stimulus* (`intervention_id` / `delivery_id`, with the policy's
`assigned_probability`) → *measured response* (`proximal_outcome`
inside `outcome_window_sec`, `outcome_observed`).

## 2. App event export (what the app must emit)

Two event types, JSONL, one file per export window:

```json
{"type": "delivery", "delivery_id": "dlv_...", "user_id": "u_...",
 "at": "2026-11-14T09:00:00Z", "intervention_id": "affirmation_morning_calm",
 "assigned_probability": 0.5, "available": true,
 "personal_history": {"onboarding": {...}, "recent_opens": 3}}
{"type": "outcome", "delivery_id": "dlv_...", "at": "2026-11-14T21:00:00Z",
 "proximal_outcome": 1, "outcome_name": "opened_within_window"}
```

Rules:

- A **delivery event is recorded for every assignment, including
  control** (no intervention sent). Control: `intervention_id: null`,
  `assigned_probability` = the policy's probability of assigning
  control. Without control deliveries there is no uplift — only
  correlations.
- `assigned_probability` is the probability the *current policy*
  assigned to the arm this person actually got, recorded **at decision
  time**. It must be in (0, 1) exclusive (schema requirement). A
  deterministic policy that always sends (p = 1.0) produces cases the
  schema rejects — by design: deterministic delivery is not an
  experiment and cannot train or evaluate uplift.
- `personal_history` is whatever the app knows about the person
  *before* the decision (onboarding answers, usage history). It must
  not contain anything observed after the decision point.
- Outcomes join by `delivery_id`. An outcome later than the registered
  window does not count (the converter drops it and marks the case
  unobserved rather than silently extending the window).

`convert_anicca_events.py` turns an export into schema cases;
`validate_cases.py` checks them; the ManagerBench checker
(`check_intervention_cases.py` in anicca-ops) must report
`invalid=0`. Fixtures in `fixtures/` demonstrate the round trip
(3 cases: treated+observed, control+observed, treated+unobserved).

## 3. The app-side blocker (as of 2026-11-14)

The Anicca app does not currently export `delivery_id` or
`assigned_probability` (MG-06 prereg section 3 / 8.3 noted the same
gap). Until a delivery policy exists that (a) sometimes assigns
control or an alternative intervention and (b) logs the assignment
probability at decision time, **zero** product cases can be produced
honestly — so v0 trains and evaluates on Hillstrom only, and this
directory is the ready socket.

Hand-off: this spec plus the MG-06 prereg sections 3 and 8 go to the
Phase 1 app lane. When the export exists, the first product cases are
validated here and counted in ManagerBench
(`files/eval/managerbench/` in anicca-ops) — the count moving off 0 is
the acceptance test.
