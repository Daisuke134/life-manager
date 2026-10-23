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
