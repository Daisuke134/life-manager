# AgentCore CL01–CL04 evidence

This file separates verified local/PostgreSQL evidence from real-provider evidence. A local PASS is never treated as an AWS deployment PASS.

## Verified locally

- Immutable runtime envelope rejects foreign `state`, `receipt`, `credential`, `browser-session`, and `artifact` references before lease acquisition or provider invocation.
- Raw S3 keys, human credentials, approval URLs, resume callbacks, and injected runtime-session IDs are rejected before backing calls.
- Foreign or human-owned Browser Profiles and foreign Identity refs make zero AgentCore calls.
- Known pre-accept transient failure is retryable; timeout or accepted disconnect is `reconcile`, never blind retry.
- Concurrent redelivery acquires one tenant lease and invokes one effect once.
- Expired external-effect jobs quarantine; stale browser leases stop the exact provider session once.
- An old release SHA makes zero provider calls.
- One tenant rejection does not stop a valid independent tenant.

Command:

```bash
node --test test/cloud/agentcore-tenant-isolation.test.js test/cloud/agentcore-effect-recovery.test.js test/tenant-isolation.test.js
```

Expected result: all tests pass, forged-reference provider calls are zero, and redelivery provider calls equal one.

## Real-provider evidence still required

- Dedicated read-only AgentCore invocation using the approved release.
- Synthetic ambiguous-acceptance canary that reads back `effect_unknown` quarantine.
- Reconciliation followed by replay-zero.
- Active Runtime and Browser sessions read back as zero after teardown.

These checks remain blocked until AWS account service activation is proven by successful CloudFormation and S3 API readback. Control-plane listing alone is insufficient.
