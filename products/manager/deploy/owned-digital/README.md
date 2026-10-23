# Private manager checkpoint gateway

This directory contains the private checkpoint SQL migration and the
`manager-owned-state` Supabase Edge Function source. They form one deployment
unit: apply `20261022_private_checkpoint.sql` and deploy the complete
`state-gateway/` function bundle together. The gateway source is pinned to
`jose` 6.2.13; its offline SQL contract tests use PGlite 0.5.11.

The function verifies GitHub Actions OIDC tokens itself with the pinned
GitHub issuer, the fixed project audience, and claims for repository
`Daisuke134/life-manager`, the `main` ref, GitHub-hosted runners, and the
trusted `manager-phase06-service.yml` workflow. That function must be deployed
with Supabase JWT verification disabled (`verify_jwt=false`): Supabase's
default JWT check does not accept this GitHub token, and the function performs
the external verification before reading project credentials or accessing
PostgREST. Keep the trusted workflow restricted to `main`, `schedule` and
`workflow_dispatch`; it must request the `manager-owned-state` audience. The
added contract workflow is only a source check and intentionally receives no
OIDC permission or provider secrets.

State remains private in PostgreSQL. The migration enables and forces RLS,
revokes table access from public, `anon`, and `authenticated`, and grants the
checkpoint RPC only to `service_role`. The RPC enforces owner leases and
revision-based compare-and-swap (CAS). It does not seed a row: missing state
fails closed. Bootstrap or restore is a separate operator procedure that must
reconcile reserved occurrences before any sender runs. There is no public
state read endpoint, automatic initialization, or retry that could replay an
uncertain write.

Run the checks from `state-gateway/` with Node v24.19.0 and Deno 2.1.14, the
Deno version line compatible with hosted Edge Runtime:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm test
deno check --lock=deno.lock --frozen index.ts
```

`package-lock.json` pins the Node test dependencies. `deno.lock` pins Deno's
`jose` import. CI runs those same locked installs and checks for changes to
the SQL, gateway, lockfiles, README, or its workflow.

No function or schema has been deployed by this source change. Deployment
still needs the trusted main workflow, its scoped OIDC permission and provider
secrets, the reviewed Supabase `verify_jwt=false` setting, and separate live
readback of the SQL privileges, function authentication, and private state
behavior. This repository change does not establish those live facts.

## Optional checkpointed advisory provider

An explicitly approved host may add the optional direct SDK dependency with
`python -m pip install -r requirements-ampersand.txt` from `products/manager`.
The adapter checks installed distribution metadata and accepts exactly
`openai==3.24.0` before constructing a client. This file pins only the direct
SDK dependency; it does not lock transitive packages.
The trusted workflow installs it only for an effective catalog-shadow dispatch,
before creating fresh private runner state or invoking the lease-owning CLI.
The installer receives no API key.
Default, scheduled, and control operations do not install this optional SDK;
source tests use local fakes without installing it or making model calls.

The `manager_core.owned_provider.CheckpointedProvider` callable adapter can
connect an already acquired `PrivateCheckpoint` to the optional Ampersand
session journal and budget ledger. Both SQLite stores live in that exact
private `cycle.sqlite` database, so the existing SQLite Backup API carries
their state in the same private snapshot. It does not change the scheduled
deterministic planner or enable scheduled provider inference.

The adapter is advisory only. Its public-fact prompt rejects synthetic facts,
and its strict output parser returns P0 advice with execution authorization
disabled, causal support false, and human outcome not measured. Session
creation and followup reservations, UNKNOWN intents, event idempotency keys,
writer claims, usage estimates, and releases are checkpointed after SQLite
commit and close and before a possible provider write. A lost checkpoint
acknowledgement fences that owner; UNKNOWN creation or event state remains
UNKNOWN and is never automatically resent.

The configured reservation cap restricts which reservations this adapter may
add to its ledger. It is not a provider-enforced token or spend ceiling and is
not a settled bill. Token-derived costs remain estimates; settled cost is
unknown until separate provider billing evidence is reconciled. Exact-turn
recovery is not automatic because the session journal does not persist turn
identifiers. Cancellation is bounded by an absolute deadline, binds its local
reservation to the session and requested turn, and checks the provider's latest
turn before sending and before releasing the local writer. This check follows
the documented one-application-writer model: no provider-side expected-turn
compare-and-swap parameter has been verified, so it does not prevent races from
independent external session writers. A timeout or ambiguous cancellation keeps
the writer fence and reserved exposure.

## Opt-in catalog provider shadow

The trusted main workflow offers `catalog_shadow` (boolean, default `false`)
with optional string inputs `ampersand_max_total_usd` and
`ampersand_max_call_usd` (both default blank).
Effective enablement requires exactly `workflow_dispatch`, `operation=run-once`,
and `catalog_shadow=true`.
The same condition gates the SDK installer, `MANAGER_CATALOG_SHADOW_ENABLED`,
and the cycle-step `AMPERSAND_API_KEY` secret; every other case receives
`false` and an empty key.
A schedule, an omitted or false flag, or `stop`, `rollback`, or `resume` keeps
comparison and client/provider initialization OFF.
Preflight also remains OFF.
This adds no owner or writer: the existing verify dependency, trusted-main
identity, concurrency, CLI invocation, operation allowlist, and publisher
permissions remain the authority.

The money inputs reach `MANAGER_AMPERSAND_MAX_TOTAL_USD` and
`MANAGER_AMPERSAND_MAX_CALL_USD` as raw strings without numeric fallbacks.
Blank or invalid money leaves the send configuration `None`; it never implies
a zero-dollar or example allowance.
Both values must be finite Decimals in `(0, 100]`, represent exact microdollars,
and satisfy per-call upper bound <= cumulative cap.
A valid key and both valid limits create an inert client factory; parsing
configuration does not construct an SDK client or provider.
These reservations are cumulative in the existing private ledger and stay
charged until separate settlement.
They do not replenish per workflow run, rotate caps, or establish settled cost.
A changed persisted cap or exhausted ledger may still create one SDK client:
the accepted helper creates the client and `CheckpointedProvider` before
durable budget admission, then refuses a new model session on budget failure.
Static invalid configuration creates neither client nor provider.

`OwnedPlatformHost.prepare_candidate` calls the existing catalog planner once and sends
the exact prepared `(context, assessment, scope)` tuple to
`manager_core.owned_provider_shadow.compare_prepared_catalog_shadow` under its
already acquired `PrivateCheckpoint`.
The comparison does not replan, refresh scope, or acquire a second lease.
It compares the two frozen advisory baselines with one provider response for
a verified `CORRECT_LINK` or `IMPROVE_ACCESSIBILITY` candidate.
The standalone `run_catalog_shadow` helper remains available to callers that
already supply a client and acquired checkpoint; the host uses the prepared
comparison path instead.

Saved `manager.catalog-shadow.v1` comparisons replay from the same private
checkpoint without a new model send, even if send configuration is absent.
Replay still requires a current supported candidate, valid scope, and unexpired
time window: deadline checks precede saved-result lookup.
A prior uncertain provider intent stays UNKNOWN and is not automatically resent.
Ordinary comparison `UNKNOWN`, `SKIPPED`, or model `PASS`/`ASK`/`PROPOSE` does not
control the candidate or independent publisher admission.
`CheckpointUnavailable` follows the existing owner fence.
Comparison may consume an already committed cadence slot, so a later attempt
may be `NOT_DUE`.

The comparison window is at most 120 seconds from `run_once` entry and can
only shorten during preparation or replay.
It is also bounded by the existing 600-second host lifetime and the remaining
prepared scope lifetime, each reserving 120 seconds for the publisher.
That reserve is code policy, not a guarantee that publication will finish.
The SDK request timeout is 30 seconds; the provider retains its absolute
deadline and bounded cancellation grace.
The workflow job timeout remains 13 minutes.
The host attempts each successfully created SDK client's `close()` exactly once
on every comparison exit, including budget refusal, uncertainty, interruption,
and checkpoint failure.
An ordinary close exception is suppressed without replacing an active fence;
a close attempt does not prove successful cleanup.

Only the allowlisted nested `catalog_shadow` projection is added to the public
summary; the existing three public artifact paths remain unchanged.
Private comparison records, session/budget journals, and `cycle.sqlite` remain
in the existing private checkpoint snapshot.
Public advice remains P0: `authorized_execution=False`, `causal_support=False`,
`human_outcome='NOT_MEASURED'`, `action_writes=0`, and `settled_cost_usd=None`.
There is no publisher packet or additional execution authority in that summary;
model advice cannot change baseline or candidate bytes.
Source contracts and local fake-client tests establish this connection, not live
provider inference, cancellation behavior, human benefit, or row4 live utility.
Live activation, dispatch, deployment, and authoritative provider readback remain
separate operational acceptance; this source change performs none of them.

Final-text readback follows the pinned OpenAI SDK 3.24.0 result collector: it
joins `output_text` blocks from completed assistant messages whose phase is
`None` or `final_answer`, in returned item order, with no separator; commentary
is excluded. Follow-up SSE completion supplies the target turn ID only. The
adapter requires that turn to remain latest before and after the bounded saved
item scan, and retains its writer fence if any read is incomplete or uncertain.
Initial collected text is bound to its own result turn ID. Cancellation requests
are limited to Turn states `queued`, `in_progress`, and `waiting`; unsupported
states remain UNKNOWN. These SDK-shaped local contracts establish neither live
provider inference nor provider cancellation behavior. Provenance: official
OpenAI 3.24.0 wheel sources and compatibility audit retained outside this
repository at `/workspace/scratch/manager-provider-shadow-20261023/sdk-audit/`.
