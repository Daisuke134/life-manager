# Manager build first architecture

Date: 2026-10-19. Written design proposal requested by the user. This document defines architecture and acceptance requirements, not deployed behavior. The unified SSOT remains the sole owner of ordered tasks and progress. New article publication and website changes remain on hold.

## Latest scope correction for handover

The user's final correction prioritizes **macro intervention**: change shared conditions, systems, access, information or resources so that benefits can reach a population. Do not frame the first product as highly personalized nudging, individual event applications or travel management. Life Manager is a source of reusable execution components, not the definition of Manager.

The personal event-registration trace below remains an internal illustration of existing execution contracts. It is not the selected macro MVP. The first macro environment/operator is not yet selected. The next architecture discussion must choose one controllable shared environment with actual observations, a concrete permitted change, a meaningful outcome and a comparison method; then scope the smallest end-to-end implementation. Do not invent operating access or treat a simulation result as a field result. Earlier example-specific recommendations are superseded by this paragraph.

## Purpose and current decision

Anicca's mission is exactly **End suffering.** Manager proactively identifies problems, changes actionable conditions, verifies what happened, and learns whether the change helped. The build strategy now takes priority over a linear curriculum: build one complete useful loop, investigate missing components when they block a concrete implementation, and save explanations as reusable learning material. Lesson 9.5 is paused, not deleted or marked complete.

The current request authorizes research, architecture, a detailed build backlog and specification updates. This work does not install a new production owner or activate a participant intervention. Existing delegation and production promotion contracts govern later execution.

## Three approaches

1. **Recommended: reuse the existing action runtime and connect a problem to its measured outcome.** This has the shortest route to a real, inspectable demonstration and makes use of existing intent, adapter, job and receipt contracts. It initially proves a narrow operational loop, not universal environmental competence.
2. **Population/simulation first:** finish a world simulator, optimize policy, then connect an operator. This is appropriate when population interaction or shared capacity determines the answer. It delays useful action where a rule and an existing operator already suffice.
3. **New general multiagent framework:** put an LLM in charge of observation, planning, execution and scoring. This duplicates existing runtime work and makes self-reported success harder to distinguish from provider evidence. Do not adopt it as the default.

Use a shared Manager decision and outcome layer. Existing Life Manager capabilities are execution adapters into personal environments, not a second competing Manager implementation. Shared-resource and population adapters extend the same contracts later.

## Reusable implementation and bounded gaps

| Responsibility | Existing source | Design decision |
|---|---|---|
| Observations and context | apps/life-manager/lib/daily-preflight-collectors.js; context-graph.js; care-detector-runtime.js | Reuse source/time-aware readers; retain source owner and freshness. Calendar entries are plans, not proof an activity happened. |
| Goals and delegation | intent-graph.js; opportunity-engine.js | Reuse explicit goals, prohibitions and act/ask/skip. Do not treat a general mission as permission for every external action. |
| Read projection | agent-graph.js | Tenant-scoped projection with provenance; provider ledgers remain authoritative. |
| Work and adapters | loop-adapter-registry.js; config/loop-adapters.json | Existing plan/execute/reconcile/verify/report interface. Prefer the existing capability instead of reimplementing its provider path. |
| Durable execution | runtime-job-store.js; effect-reconciler.js | Keep jobs, leases, idempotency and unknown-effect reconciliation in the existing owner. Unknown is not absence; no blind resend. |
| Content artifacts | content-object-store.js | Store immutable bytes outside Git and reference by SHA256; do not invent an unrelated blob service. |
| First action path | luma-rsvp-adapter.js; connector-candidate-outcome.js; existing provider receipt readers | Reuse eligible event registration to test the connection from a concrete goal to verified completion. No new email or public publishing workflow. |
| General handoff | general-agent-work-adapter.js; goal-work-item.js | Audit the loop identifier mismatch before any connection. Do not hide provider effects behind an effectClass:none parent. |
| Population | apps/manager/src/manager/population/ and benchmarks/ | Reuse only when aggregate scenarios require it. 8A/8B do not supply observed behavioral labels. |
| Comedy/music | legacy anicca-comedy-factory inventory reference; music source not located in this audit | Discover original source and runtime owner before migration. Absence from this checkout is not proof that the user's previous work never existed. |

Source presence and passing local tests are not evidence of current production activity. Current account access, loaded production releases, and provider status have not been audited in this design task.

## Technology choices

- Orchestrator: existing Node.js CommonJS application in apps/life-manager, on its supported Node >=20.19 runtime.
- Schemas: existing versioned common records, current validation conventions and Zod where already used. Add a narrow domain record without silently widening closed schemas.
- Scheduling/workflow: existing runtime owner, queue/leases and Inngest integration; no second cron owner or mandatory Temporal installation.
- Storage: retain current owner-controlled job/receipt tables in Postgres and local host-adapter stores. The existing lm_runtime_jobs, lm_runtime_job_receipts and lm_runtime_scheduler_leases remain execution authority. Do not migrate unrelated domain state or add a new database for this MVP.
- Artifacts: existing content-addressed object store; job input_refs point to domain records/artifacts, rather than arbitrary extra common-record fields.
- Predictors: deterministic rule first. When prediction has measurable value, call a versioned Python model from apps/manager with validated input/output; logistic regression or a tree is a comparison candidate. Do not require GPU training.
- Jev: optional bounded semantic classifier/router after evaluation, not an execution authority and not a validated human simulator. Generative LLM only for text or planning that needs it. Keep amounts, dates, identity and resource constraints in code.
- Simulation: optional adapters, not a prerequisite. Introduce Mesa/AgentTorch or optimization tooling only for a concrete interaction/resource problem; do not install every referenced research framework.
- Human-facing surfaces: existing Telegram/control panel or user-chosen channel. No mandatory new chatbot interface. Preserve stop, correction, explanation and preference controls.

## Logical data flow

Observation -> ProblemCase -> eligible ActionProposals -> decision -> existing RuntimeJob -> provider readback -> execution Receipt -> OutcomeObservation -> next decision.

These are domain contracts, not declarations that named modules already exist:

- **Observation:** source_ref, observed_at, available_at, subject_ref, measured value/unit, freshness and observation-versus-inference status.
- **ProblemCase:** version, case_id, tenant scope, problem kind, supporting observation_refs, linked goal/delegation refs, baseline, actionable target, expiry/resolution rule, current projection status.
- **ActionProposal:** candidate_id, case_ref, adapter capability, exact target/version, prerequisites, cost/constraint bounds, valid alternatives including no_action; model version and action-selection probability only when probabilistic selection is actually used.
- **Decision:** allowed action or no_action/needs_information, reason, policy version, evidence references. A model cannot grant itself permission or invent a valid target.
- **Execution receipt:** existing job/effect/receipt records with provider evidence. Distinguish planned, attempted, unknown, failed and verified.
- **OutcomeObservation:** case/receipt refs, actual exposure, observation window, metric/unit, value or missingness, data source, adverse/annoyance signal where collected, comparison method. Actual benefit may remain unknown even after execution succeeds.

Keep the case view as a projection over existing domain records, jobs and receipts. Do not create a competing truth ledger. For the first patch, inspect current domain schema and add only a versioned case reference/record necessary to reconstruct the path. Preserve separate case, attempt and effect identifiers. A retry never creates a new identity merely to evade deduplication.

Proposed source boundaries for the new glue are apps/life-manager/lib/manager-case.js and manager-case-service.js with matching *.test.js. These paths are planned and must be checked against the latest main before implementation; no files were scaffolded here.

## Existing execution trace for reuse, not the macro MVP

A **user-requested, eligible, free event registration with an existing delegated action path** illustrates reusable execution behavior. It is not the first product domain after the macro-intervention correction. Its source and independent readback are useful to copy when building a shared-environment operator.

Example trace:

1. An existing explicit participation goal and a verified upcoming deadline create a case. Missing local receipt triggers status inspection, not an assumption that registration is absent.
2. The provider reader confirms either already registered, not registered, or unknown. Already registered resolves the operational case without another submission. Unknown stays unresolved.
3. For confirmed absence, valid profile/eligibility, free event, no conflicting prohibition and existing delegation, choose the existing registration adapter. Otherwise record the concrete blocker or no_action.
4. Submit through the existing effect path and reconcile by the provider's confirmation. A timeout creates an unknown effect, not an automatic duplicate request.
5. Link confirmation to the original case. The next scan sees verified resolution instead of repeatedly discovering the same problem.
6. Record deadline completion and any actually observed user effort. Task completion is a useful operational result. It is not a measurement of suffering reduction. Optional burden feedback has its own record and may be missing.

The offline replay should cover already-completed, eligible-and-pending, stale/conflicting, and unknown-effect cases, including repeats and process restarts. The first real demonstration requires the existing runtime owner and an actually connected, authorized target; do not fabricate either from source fixtures.

## Minimum acceptance requirements

- Every case can be traced from observation to decision, job, provider receipt and outcome window.
- Replaying the same case does not cause a second external effect.
- A previous successful action makes the next observation resolve or suppress the same operational issue.
- Unknown external state does not authorize a retry; expired evidence does not authorize an action.
- Tenant scope and existing delegation are preserved.
- The result report distinguishes operational completion, subjective feedback, causal evidence and unmeasured outcomes.
- A rule-based baseline and no_action are valid decisions; invoking an LLM/Jev is not a success condition.
- Local replay passes before a single delegated production canary. Use the normal repository PR/checks/release path and the existing runtime owner; no parallel production instance.

## Comedy and music extensions

Treat content factories as suppliers and delivery adapters, not as the welfare objective itself. A daily creative production loop can keep producing drafts without sending daily content to every person.

Factory path: idea -> script/track -> editorial or listener evaluation -> immutable content artifact -> existing distribution adapter -> verified exposure -> separate audience outcome -> next creative iteration.

Intervention options remain distinct: existing comedy clip, newly generated comedy, preferred recorded music, newly generated music, practical assistance, or no intervention. A music therapist's session, a laughter exercise, a stand-up video and Spotify playback are not interchangeable treatments.

An opt-in pilot must specify the actual audience, allowed channels/times, interruption budget, delivery choice, proximal outcome and follow-up window. Start with existing liked material and a fixed policy. Separate two questions: is our new work funny/enjoyable, and does offering it at this moment help? Blinded human ratings can compare creative quality; randomized eligible opportunities can later assess offer effects. Opening an offer, verified playback and subjective benefit are different events.

Do not optimize watch time or posting frequency as a substitute for benefit. Retain annoyance, refusal, skipped delivery and missing feedback. No mood diagnosis from incidental behavior. A contextual bandit (e.g. Vowpal Wabbit) is a later candidate only once valid reward observations, action probabilities and adequate variation exist. For causal evaluation distinguish assigned offer from actual exposure, and define interference/carryover rather than assuming every moment is independent.

## Evaluation and expansion

Preserve separate evaluation categories: population_fidelity, behavior_prediction, policy, execution, field. Unknown outcomes remain not_run or missing as appropriate. Never promote population fidelity or model agreement into field benefit.

For the first case, report official completion, time to completion, duplicate effects, unresolved cases, actual user steps and cost. For creative support, record blinded funniness/enjoyment separately from short-term relief and longer outcomes. A founder N-of-1 exploration is not population-level proof. Choose the comparator, measurement window and sample plan before collecting confirmatory results; do not invent a universal participant count or acceptable benefit threshold.

After a real narrow loop: add one shared-environment operator (for example an owned service's availability or resource allocation), select real operator data and outcomes, and introduce population/behavior/simulation components only if the counterfactual requires them. Capacity constraints, spillovers and delayed effects become explicit then.

## Evidence reviewed for this proposal

The local command node --test over opportunity-engine, agent-graph, loop-adapter-registry, effect-reconciler and connector-candidate-outcome tests passed 34 tests. This verifies existing component behavior on the tested tree, not the proposed integration or a production outcome.

Primary research and philosophical sources are in the accompanying source map, with private originals and reading limits. No new provider calls, model training, participant recruitment, messages, production deployment or article publication occurred in this design task.
