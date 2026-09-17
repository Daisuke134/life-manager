---
name: loop-engineering
description: Use when building, fixing, releasing or operating a Life Manager loop, adding a marketplace lane, or deciding whether existing loop components must be reused.
---

# Loop Engineering

Loop engineering is the control system that keeps an agent useful across time. One architecture
router prevents a lane from inventing what another lane already owns. This file routes; release and
launchd work still requires the focused `loop-development` subskill.

## Master catalog route

Read this skill first. Then consult the pinned **[Awesome Harness Engineering](https://github.com/ai-boost/awesome-harness-engineering)**
snapshot (`692a1a681c464de22a5e9b947bd081808600b0b3`) for Agent Loop, Planning & Task Decomposition,
Task Runners & Orchestration, Human-in-the-Loop, and Evals & Verification. Use the chapter as a
decision map, then read `references/source-notes.md` and the pinned implementation path it names.
Do not introduce a second runner because the catalog lists another framework.

```text
loop config -> reusable recipe -> shared runtime -> provider adapter -> official provider
```

Dependencies run one way only. `runtime/` owns scheduling, admission, model
routing, checkpoint/resume, retries, replay prevention, receipts and recovery,
and knows no marketplace rules. A recipe owns one business lifecycle (Apply,
Negotiate, Storefront, Paid) and knows no DOM selector or credential. An adapter
owns only official observation, mutation and readback. A loop config selects a
recipe, provider, cadence and policy — it never implements a second runner,
retry engine, ledger, browser launcher or model client.

## One loop, two host adapters

Local/self-hosted and cloud run one logical loop from the same repository-owned
implementation. They share the loop ID, recipe, model/tool and provider
contracts, job/event/effect/receipt/outbox schemas, replay fence and tests. Only
the supervisor, durable-storage adapter, secret store and browser transport vary.

Host adapters implement the shared contracts; they do not own business
decisions, retry/replay policy or a second runner. Do not create local/cloud
copies, including temporary copies, and do not add deployment machinery such as
a Dockerfile unless the measured target runtime requires it. An unavailable host
capability fails closed instead of forking the workflow. The target shape and
migration status live in
`docs/superpowers/specs/2026-09-06-life-manager-one-repo-two-runtimes-design.md`.

## Route by task

| Task | Read |
|---|---|
| Change a loop, its cadence, release or plist | `skills/loop-development/SKILL.md` |
| Build or fix an Apply lane on any marketplace | `references/marketplace-apply-lane.md` |
| Build or fix a Paid/Fulfillment lane on any marketplace | `references/marketplace-paid-lane.md` |
| Build or fix a Storefront lane on any marketplace | `references/marketplace-storefront-lane.md` |
| Decide whether a failure may end a wake, or add a retry | `references/transient-vs-fatal.md` |
| Decide whether a loop may earn on a platform, and what to ask a human for | `references/platform-automation-map.md` |
| Reuse the shared marketplace runtime | `skills/_shared/marketplace-core/scripts/` |
| Sell the same catalogue on a new platform | `skills/gig-work/profile/listings/catalog.json` |
| Lane ownership and parallelism rules | spec §6.2A, `docs/superpowers/specs/2026-08-22-life-manager-gig-economy-loop-design.md` |

## Before writing code

Search `runtime/`, existing recipes, provider adapters and `skills/_shared/`.
Reuse what is there. A new abstraction is prohibited for one speculative
consumer — the second real consumer is the extraction trigger.

For a new or migrated loop, name the shared core and smallest host adapters
before editing. Mixed business and host code is a boundary to extract, not a
reason to duplicate the loop.

## Recipe

1. Define one durable goal/owner scope with a measurable result, budget, deadline, and typed terminal
   states.
2. Observe authoritative state; record observation ID, time, owner, and source hash.
3. Build a bounded capsule from goals, facts, commitments, artifacts, effect keys, and questions;
   the last message is never the whole state.
4. Let the model choose the capability/arguments; runtime policy enforces boundaries without keyword
   judgment.
5. Execute one leased transition and persist the attempt before an external effect.
6. Verify official readback, append receipt/facts, and reconcile unknown effects instead of retrying.
7. Schedule the next wake from durable state, then feed verified outcomes to evals/observability.

## Contract

| Boundary | Required fields |
|---|---|
| Wake | `wake_id`, owner, goal revision, observed-at, bounded deadline |
| Decision | model-selected capability, arguments, context hash, policy result |
| Effect | deterministic `effect_key`, attempt, lease, target identity |
| Verification | provider source, readback status, receipt ID/hash, replay result |
| Resume | durable cursor, next eligible time, failure class, retry count |
| Completion | official receipt or typed wait/blocker; never PID/exit 0 alone |

The four lanes are independent owners: Apply submits applications, Negotiate replies to buyer
threads, Storefront mutates listings, and Paid fulfils orders. They may run concurrently, but their
effect namespaces and mutable contexts never overlap.

## Failure modes

| Symptom | Correct move |
|---|---|
| Worker exits while goal is active | Persist failure and schedule bounded retry/continuation |
| Provider result is uncertain | Reconcile official state; never blind-retry the same effect key |
| Repeated identical failures | Stop repeating, classify the boundary, and create a repair/eval case |
| One lane blocks another | Keep owners and queues independent; repair only the shared boundary |
| “Self-healing” means only a restart | Require durable progress plus official effect separation |

## Source map

Read `references/source-notes.md` for pinned upstream code. For lifecycle or production changes,
also read `skills/loop-development/SKILL.md`; it owns worktree, immutable release, launchd, and
natural-wake gates. The Coconala-to-meta-loop TODO remains a separate owner’s input.

## Lane ownership

Apply alone submits applications. Negotiate alone replies to buyer threads.
Storefront alone mutates listings. Paid alone fulfils orders. Effects are
disjoint by construction, so there is no cross-lane lock, shared queue, sibling
wait or effect arbitration. Each owner prevents replay from its own durable
state and reconciles an uncertain result from official state without pausing any
other owner.

## Completion

Completion is official provider readback, never process liveness, never a clean exit code. A lane
that ran and reported success without a receipt has not completed.
