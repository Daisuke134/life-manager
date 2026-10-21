# Manager Phase06 — F002/F003 evidence and field gate report

**As of 2026-10-21 JST.** **Canonical task registry:** [tasks.json](../roadmap/tasks.json). Status: **F001 F002 F003 = DONE under documented preparatory engineering/research acceptance**; F004/F007 = BLOCKED; F005/F006/F008/F009 = TODO because no Manager-originated authorized field intervention exists.

**Current Manager task totals:** 113 = **63 done / 47 todo / 2 blocked / 1 scientifically skipped** (HeartSteps H005 remains a scientific skip). **Scientific Gate 1 remains UNMET; verified real-world beneficiary net improvements: zero known; properly: NOT_MEASURED.**

## F002: preregistered study *design*, not a human field RCT

- [Machine-readable frozen design](../../pilot/PREREGISTRATION.json), [SHA-256 byte lock](../../pilot/PREREGISTRATION.sha256) and [human-readable explanation](../../pilot/PREREGISTRATION.md). Host-computed SHA256: `22fd38e965818dce9b5d21380e5f36ae862cc1cd0bbc35e52ac1aa2b7f896ac6`.
- Hypothetical prospective eligible unit: **one distinct, consenting, USD-denominated public collective**, with 40 campaigns split 20/20 before assignment; **n=40 is a feasibility hypothesis, NOT a powered sample**. No participating collective/real assignment/independent registration has been observed.
- Comparator: prospectively randomized NO_ACTION vs bounded information intervention, with prospective 14-day baseline, 28-day intervention observation, and 30-day refund/settlement follow-up. The sample estimate needs independent power review **before any recruitment or random assignment**.
- Primary metric frozen in exact bytes: `incremental_net_confirmed_third_party_contributions` in **USD cents per campaign**, requiring settled and independently corroborated external contributions (not the matching principal, clicks, pledges or virtual balances) less attributable refunds/fees/costs. Across-charity displacement is a separate required assessment.
- Negative/null harms are also preregistered: refunds, chargebacks, displaced giving, donor complaints, privacy, worker time, computing costs and arbitrary overreach. Missing data remain UNKNOWN/NOT_MEASURED, not 0; causal conclusion is INCONCLUSIVE if intervals include zero or contamination invalidates assumptions.
- **Lock caveat:** Git SHA and independent hash catch post hoc modifications to committed text; they do not by themselves timestamp a genuine human-participant preregistration with an outside registry. That and legal/ethical approvals are future prerequisites.

## F003: public real external read-only finance observation

- [Adapter source](../../manager_core/adapters/public_finance.py): fixed Open Collective public GraphQL v2 endpoint, static QUERY operation, bounded 4-transaction sample, string-validated public account slug, no token, no mutation, no user-controlled URL. Private donor names/emails/account credentials are not queried or logged. Invalid/timeout/conflicting response => `LedgerUnverified`, never an invented zero.
- [Provider readback command](../../scripts/phase06_public_finance_readback.py): `python3 scripts/phase06_public_finance_readback.py --collective webpack`. The provider is independent of Manager, but is the reporting source for historical records, **not evidence that Manager executed an effect**.
- **Actual hosted network evidence:** [GitHub Actions run 39586031696](https://github.com/Daisuke134/life-manager/actions/runs/39586031696) completed successfully with **262 tests OK**, product boundary, existing Phase05 2-domain demo, and a real third-party Open Collective GraphQL response.
- At 2026-10-21T10:38:25Z, provider account `webpack` reported total public transaction count **52,029**. The four-transaction requested sample gave **USD** 20,000 positive-credit cents and −3,010 debit cents; limited-sample digest `c18bfc22509d55e711188b98b2fb577a37865ea6e3d39111e2d51c9542b39921`. **These numbers are not contributions created by Manager, settled profit, nor net charitable impact**, and should not be summed naively: credits/debits may represent a paired ledger, fees, refunds, expenses or external records. Open Collective explicitly cautions its platform ledger may omit off-platform financial activity.
- No independent payout certification, personally targeted data, Manager-originating transaction, live user funding, or causal comparison was present. **P0 only.**
- Sources: [Open Collective GraphQL developer docs](https://developers.opencollective.com/), [ledger disclosure limitations](https://documentation.opencollective.com/advanced/ledger), [paired entries](https://documentation.opencollective.com/advanced/ledger/transaction-pairs-groups-and-perspectives).

## Tests and failures

- Test-first RED in [39585239536](https://github.com/Daisuke134/life-manager/actions/runs/39585239536): seven F002/F003 tests failed because the intended preregistration, freeze contract, and public ledger adapter did not yet exist.
- GREEN except lock in [39585918378](https://github.com/Daisuke134/life-manager/actions/runs/39585918378): hosted CI computed exact preregistration hash while two lock-file tests failed, showing an actual missing safety artifact.
- GREEN in [39586031696](https://github.com/Daisuke134/life-manager/actions/runs/39586031696): 262 tests, prereg SHA, genuine public API readback, boundaries, prior demos, backlog consistency passed. No observed local Mac or production intervention execution.

### F003 failure model
```text
valid source URL and public account
    -> provider GraphQL READ QUERY
    -> authenticated server TLS and strict JSON parse
    -> validated timestamp, account, currency and transaction uniqueness
    -> privacy-safe aggregate + snapshot SHA256 (P0)
    -> NO_ACTION as provider data cannot itself grant authority

timeout / schema error / forgery / missing data
    -> LedgerUnverified -> UNKNOWN/NOT_MEASURED
```

## Blocking conditions for F004-F009 (unchanged)

| ID | Status | What actual completion needs |
|---|---|---|
| F004 | BLOCKED | An authenticated legal issuer with authority to commit specified real funds, actual funding, revocable scoped grant, consent and budget. Founder permission to develop Manager is **not** the funding issuer. |
| F005 | TODO | After F004, a real limited financial intervention, linked provider receipts and independent P1/P2 world-state readback for the same effect; no hypothetical transaction accepted |
| F006 | TODO | Real preregistered primary outcome, credible comparison/CI, costs, third-party displacement, harms, negative/null/unknown classification; no P3/P4 from one receipt |
| F007 | BLOCKED | Identified facility owner, legal permission for indoor actuation and verified independent indoor PM2.5 sensor; public outdoor monitoring is not indoor permission |
| F008 | TODO | After F007, randomized controlled indoor exposure intervention with independently calibrated PM2.5, electric power, noise, occupant comfort and adverse effects |
| F009 | TODO | Two-domain **real** independent P2+ replication on the same kernel, without substituting a synthetic demonstration |

**The founder has authorized normal research and code development. That cannot grant third-party account, payment, donor, facility or instrument permissions. Never enable the default-disabled live effect flags to force a demo to pass.**

## Concrete next Phase06 execution route

1. F004: select a verified Manager-controlled USD finance budget under an actual legal issuer, or an opting-in collective operator; publicly document amount, grant scope, revocation, responsible organization, account/controller, exclusions, and independent settlement readback. Without it, NO_ACTION and continue standalone read-only observations.
2. F007: identify an actually controlled indoor space and suitable external PM2.5/power/noise measurement; obtain the operator's effective revocable rights and exposure safeguards. Outdoor OpenAQ/Open-Meteo data alone cannot prove an indoor change.
3. When either exists, preregister independently (new locked version with realistic power and consent), then run a tightly bounded pilot, independent readback, comparator-based net impact and harm tracking before ever claiming a Transparent Blessing.
4. For generality, replicate in the second domain using the same core interfaces with no authorization/proof invariant weakening.
