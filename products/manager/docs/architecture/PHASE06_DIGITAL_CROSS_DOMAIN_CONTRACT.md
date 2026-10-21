# One bounded digital release contract across three support domains

The financial, mental and physical support pages use the same observation,
planning, admission, publication and readback path. Domain labels select official
resource content; they do not alter authority, proof requirements or write scope.

| Stage | Existing implementation | Observable boundary |
|---|---|---|
| Public observation | `digital_environment.py`, `phase06_kernel_release.live_snapshot` | Exact allowlisted official links and six served page hashes; no individual profiles |
| Candidate and NO_ACTION | `ManagerKernel.prepare_digital_release`, `digital_handoff.plan_release` | Candidate vs independently served baseline; fixed zero money budget; no execution |
| Standing authority | Existing GitHub workflow platform context | Exact repository, canonical source ref, workflow, immutable source SHA and revocation flag |
| Admission | `digital_handoff.admit_release`, existing seven-path release guard | Current target must match observed baseline or already contain the candidate; no authority minting |
| Effect | Existing separate publisher job | Non-force gh-pages commit under `manager-support/` only; unchanged target creates no new deployment |
| Independent readback | `phase06_kernel_release.prove` | Commit, immutable parent/candidate bundles, exact diff and live bytes bound to one effect |
| Outcome evaluation | Existing outcome ladder and domain contracts | Artifact change is P2 only; beneficiary/causal outcome needs independent downstream evidence |

The generic offline kernel, fixture HMAC authority and exact fixture executor
fences remain intact. Platform release authority is not represented as a model
grant. The kernel's release planner emits inert data and an audit record; it
cannot call a provider or change the default runtime configuration.

Tests cover wrong repository/ref/workflow/source, tampering, expiry, revocation,
baseline races, unchanged replay, a newer intent reconciling an old occurrence,
incorrect immutable contents, wrong parent and mismatched provider file lists.
Actual local staging and bounded rollback preserve unrelated files. No live
rollback is claimed by that local test.

The common pipeline verifies three distinct public navigation artifacts. It does
not imply three independent interventions, populations, clinical outcomes or
financial gains. F009's original two-domain field acceptance remains incomplete
until its original dependencies and real outcome evidence are satisfied.
