# D014 — HTTPS host-case and default-port source-alias screening

Date: 2026-10-27 JST. Scope: one independent, offline, synthetic P0 engineering atom supporting the existing D014 public-aggregate cooperation protocol. Original D014 acceptance remains **todo**; this check does not verify publishers, obtain data, or approve any publication.

## Question → opposing hypotheses → falsifier (imozuru)

**Question.** Could an otherwise identical public HTTPS release evade the existing cross-table provenance-overlap screen solely by changing the hostname's letter case or spelling the default `:443` port explicitly?

**Unsafe H0:** compare URI strings after dropping only fragment identifiers. Then `https://WWW.ONS.GOV.UK/data` and `https://www.ons.gov.uk:443/data` look independent, although the case/default-port differences alone cannot establish independence.

**Conservative H1:** when checking *possible source aliases*, normalize the HTTPS scheme and hostname case, and treat omitted port and explicit 443 as the same endpoint; strip fragment, but keep path, query and non-default ports distinct. Check syntax of both port declarations independently before considering source-ID/hash equality. This is not permission, identity verification, or a byte match.

**Falsifiers, all synthetic:** differing source IDs and SHA strings with host-case+port+fragment variants must yield `RELEASE_SOURCE_OVERLAP`; the same risk must propagate to a family of 3 via `FAMILY_SOURCE_OVERLAP`. Non-default port `:8443`, path-case difference, and query-case difference must not trigger this *particular* overlap code. Invalid port labels, zero and out-of-range ports must fail closed with a constant error. Every result remains fixed diagnostic codes only, with all authority/effect flags false.

## Primary-source locators (checked 2026-10-27)

1. IETF RFC 3986, **§6.2.2.1 Case Normalization**, https://www.rfc-editor.org/rfc/rfc3986#section-6.2.2.1 : scheme/host are case-insensitive; other generic parts are assumed case-sensitive unless the scheme specifies otherwise.
2. IETF RFC 3986, **§6.2.3 Scheme-Based Normalization**, https://www.rfc-editor.org/rfc/rfc3986#section-6.2.3 : default-port removal is an example of scheme-based normalization. HTTPS default TCP port 443 is an established standard convention, not a statistical proof of dataset identity.
3. UK ONS, **Policy on protecting confidentiality in tables of birth and death statistics**, R5 (differencing), https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/disclosurecontrol/policyonprotectingconfidentialityintablesofbirthanddeathstatistics : linked and differently aggregated tables can expose otherwise withheld counts. This guidance does not certify Manager's releases or establish a universal minimum safe cell size.

## Implementation and verification

- `manager_core/public_aggregate_cross_release.py`: deterministic `_source_origin_key()` for HTTPS URL claims; no network, unlicensed data, profile ingestion, write authority, or intervention.
- `tests/test_public_aggregate_cross_release.py`: four synthetic regression tests for equivalence, conservative negative controls, and invalid port rejection.
- `tests/test_public_aggregate_release_family.py`: one synthetic regression test confirming family propagation.
- Commands: `cd products/manager && python -m unittest tests.test_public_aggregate_cross_release tests.test_public_aggregate_release_family -v && python -m unittest discover -s tests -v && python scripts/check_boundaries.py && python scripts/make_roadmap.py --check`.
- Hosted GitHub Actions outcomes must be verified independently; do not infer their results from this research note.

## Proof boundary and remaining original acceptance

Matching a normalized URL is only a **potential source alias**; source bytes, underlying people/cohorts, legal rights, identities, release independence, ethics approval, partner permission and causal net welfare benefit all remain unverified. Outputs cannot ingest, publish, execute or contact participants; no reconstructed sensitive counts or labels are returned. This atom concerns risk screening only, not a validated anonymisation system.

Canonical `docs/roadmap/tasks.json` remains unchanged: **69 done / 41 todo / 3 blocked** at this checkpoint (113 tasks); D014 remains todo pending documented independent source and disclosure review, public aggregate and legitimate operator/ethics cooperation. H005 remains blocked because the historical HeartSteps study-day/selection information needed for exact reproduction is not recoverable from the public version; F004 and F007 are also blocked pending permission. No Phase03 paper numbers were manufactured. P0 testing is not field action P1, independent readback P2, beneficiary improvement P3, or causal net gain P4.

Mission: **End suffering** through lawful public non-personal macro-environment improvements, including concern for humans and animals; **No Human in the Loop** for standing-authorized routine operations, without depending on other people's credentials or equipment. Distinguish research, simulation and verified intervention effects.
