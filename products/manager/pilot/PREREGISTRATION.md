# Manager — F002 Prospective preregistration, DESIGN ONLY

**Version:** `MGR-FINANCE-F002-20261021-01` (2026-10-21). **Current status: PREREGISTERED_DESIGN_ONLY.**
**This is NOT a registered/authorized real-world experiment or a recruitment announcement.** The locked machine-readable source is [PREREGISTRATION.json](PREREGISTRATION.json); the byte-level hash is [PREREGISTRATION.sha256](PREREGISTRATION.sha256). Changes to the outcome definition must produce a new version, including an explicit reason and a review, before real assignment.

## Prior-to-experiment choices

- **Unit and N:** 40 separate, consenting, USD-based donation/grant campaigns, 20 treatment + 20 NO_ACTION, randomized at the campaign cluster. No individual donors are profiled. **N=40 is an exploratory engineering feasibility target and is NOT a powered trial.** No study may commence without actual eligible campaigns, independent authorization and revised power calculations if needed.
- **Primary outcome:** `incremental_net_confirmed_third_party_contributions` (USD cents per eligible campaign), defined as verified outside contributions minus refunds and attributable fees/costs, excluding the sponsor's own matching principal. Count only independently corroborated settled receipts; account for substitution/displacement separately. Zero is NEVER imputed from missing data.
- **Comparator:** contemporaneous randomly assigned NO_ACTION campaigns, normal ordinary campaign activity otherwise unchanged. Intent-to-treat and cluster-level inference, randomization and spillover audit. Historical trends alone are not reliable causal estimates.
- **Windows:** fixed proposed 14-day pre-measurement baseline, 28-day treatment/observation and 30-day settlement/refund follow-up. If payment settlement requires longer, issue and lock a NEW version *before assignments*, never redefine windows after learning results.
- **Outcome uncertainty and harms:** 95% CI, negative and null results, refund and chargeback costs, transaction fees, worker/volunteer/computing costs, displaced gifts, donor complaints, privacy and adverse events; any unknown or unavailable measure is reported as such, never silently zero.
- **Stop:** a valid owner/fund issuer grant, contracts, rights review and provider readback MUST exist before a single live intervention; otherwise NO_ACTION. Real-world causal evidence rank remains UNMET.

## What is frozen, what isn't

The static design choices above and the exact `PREREGISTRATION.json` bytes are immutable after commit by the SHA256 lock; changing either invalidates reproducible version-1 acceptance. No assignment roster or randomization seed has been frozen because **there is no authorized operator and no cohort**. A later actually authorized RCT needs a separately dated, independent public preregistration and a documented power calculation. No research document, software test or founder development approval grants financial actuation authority.

## Official methodological and ledger sources

- [Open Collective public GraphQL documentation](https://developers.opencollective.com/) — public transaction query and financial metadata, **not beneficiary outcome proof**
- [Open Collective ledger](https://documentation.opencollective.com/advanced/ledger) — off-platform activity may be absent
- [Ledger transaction pairing](https://documentation.opencollective.com/advanced/ledger/transaction-pairs-groups-and-perspectives) — credit/debit mirrored, so never sum double-entry records as new wealth
- [Karlan & List RCT](https://www.aeaweb.org/articles?id=10.1257/aer.97.5.1774) — a research precedent, not Manager intervention evidence
