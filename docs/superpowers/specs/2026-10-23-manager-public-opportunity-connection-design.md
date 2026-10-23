# Manager D011 — public artifact and platform payment connection

Original D011 depends on accepted D010, has external=none, and connects
承認された成果物と独立して確認可能な受領証拠を照合. Its verify is
支払完了を証明できなければ収入増と主張しない. This unit connects a
historical public OSS example; it is not Manager income, a new job application,
a payment, an article or a new UI. The user delegated implementation choices.

## Decision and precedent

Reuse the reviewed D003 `public_program_disbursement.py` shape: actual Source,
immutable SAFE packet URL, Source.verify_content and an independent reviewed
SHA pin before JSON. That source is reviewed, with normal main integration
pending while this independent unit starts. No import from that not-yet-merged
module is required. Copy the narrow adapter shape, not a new ingestion framework.

Converting the packet into the old OpportunityRecord would pull unrelated
research dependencies into main and blur Source URLs for per-field projections.
It is unnecessary for original D011. Leave its strict four-stage contract and
all existing research types unchanged. Do not create shared money validators
or promote OutcomeBench just to read one reviewed packet.

## Source facts and limits

GitHub JHipster PR34939 is merged, with recorded head/merge Git SHA1 values and
a separately acquired diff snapshot SHA256. Its public comment links exact
Open Collective expense346205; that expense's description/invoice item links
the exact PR. Open Collective reports PAID USD100.00 (10000 minor), with a
COLLECTIVE_EXPENSE_PAID activity and platform DEBIT -10000 at
2026-09-15T17:00:57.283Z. These are public platform declarations, not inspected
recipient bank/processor settlement. The expense does not attest the diff hash;
the adapter derives that binding from the exact PR URL and recorded snapshot.

Bounty labels occur13 seconds after the merge. Prior posting and nominal award
remain unknown. No full four-stage chain is established. Labor, costs,
opportunity cost, opportunity denominator, received/net income and human benefit
remain unknown. Do not turn an external person's historical payment into
Manager revenue, income increase, welfare or causal effect.

The SAFE packet holds only minimal aggregate/public artifact facts and links,
raw URL/hash/bytes/retrieval references, attribution, extraction and limits.
Raw API/HTML/diff, author/payee identity, contacts, private invoice/payout data
are excluded. Upstream code licensing is not extended to personal metadata.
Only attributed minimal facts and links are published, not raw redistribution.
Source points to the SAFE packet itself; its immutable URL/hash/actual retrieval
are recorded outside the packet after the root data commit.

## Interface and acceptance

`connect_published_opportunity(packet_bytes: bytes, packet_source: Source) -> dict`
in `manager_core/public_opportunity_payment.py`. Require actual Source type,
source_id=jhipster-d011-aggregate-20261023, exact immutable SAFE packet URL,
independent reviewed SHA, bytes bounded at32768, and Source.verify_content
before parsing. A caller recomputing its Source hash cannot admit changed facts.

Return opportunity_id/subject_scope, public_artifact, platform_payment,
crosslinks, prior_posting, raw_sources, unknown_costs, claim_limits, limitations,
limited_rights, attribution, extraction, safe packet_source and
public_paid_amount_minor=10000 from the reviewed platform field. Fix
proof_level=P0, action=NO_ACTION, income_status=NOT_VERIFIED,
human_welfare_status=NOT_MEASURED, verified_income_increase_minor=None,
verified_net_benefit_minor=None and
chain_completeness=INCOMPLETE_PRIOR_POSTING_UNKNOWN.
This adapter does not execute the old reconciler or certify a completed chain.

One pure module, one test module and one existing CI test-list addition. No
network/filesystem I/O, secret, model, dependency, scheduler, production owner
or action. Root owns data/design/plan/board/receipt/registry and integration.
Test actual observed artifact/payment/link facts, unknowns, no hash attestation,
rehashed replacement facts/PII/status/URL, provenance/identity mismatch and bounds.
Fresh independent review evaluates source/spec/quality/original D011, then
normal exact-head CI/main and owner registry acceptance. D012 remains separate.
