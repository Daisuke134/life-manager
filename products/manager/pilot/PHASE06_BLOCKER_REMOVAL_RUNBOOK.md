# Manager Phase06 — Removing F004 and F007 blockers (execution runbook)

**2026-10-21 JST · Canonical SSOT:** [tasks.json](../docs/roadmap/tasks.json)  
**Status:** executable evidence-readiness infrastructure implemented; not an authorized live finance or physical pilot. **F004 and F007 remain BLOCKED until independently checked legal rights and resources exist.** This runbook is not a second task registry.

## The rule: retire a blocker using proof, not by hiding it

An account login is not a grant to spend its assets. A public indoor sensor is not permission to change the building. A support inquiry is not a partner agreement. A software demo is not beneficiary welfare. Every gate is closed until independent evidence exists; then use a narrowly scoped authority certificate and a separately audited adapter. **NO_ACTION is mandatory** while missing.

### What the developer has now done

- Phase05 source→prediction→authorization→durable outbox→independent *fixture* readback→evaluation stack (P0 only).
- F002 fixed finance no-action comparator / outcome study **design**, not an actual empowered study, [preregistration](PREREGISTRATION.md).
- F003 genuine outside historic Open Collective public ledger readback, which is NOT a Manager-caused donation.
- F004/F007 minimum evidence is now machine-readable: [PHASE06_AUTHORITY_READINESS.json](PHASE06_AUTHORITY_READINESS.json) + [field_readiness.py](../manager_core/field_readiness.py) + `python scripts/check_phase06_authority.py`; filled-looking fields **never** self-authorize.
- **New:** publicly opted-in **real indoor** AirGradient readings through a fixed read-only endpoint are collected into an anonymous aggregate with units/timestamp/SHA256 and P0 labels, [adapter](../manager_core/adapters/public_indoor_air.py). It does not yield any building-owner permission, indoor treatment effect or participant profiles.

## F004 — quickest route to an actual finance operator

### Recommended: already legally administered fundraiser, with Manager handling no funds

1. **Discover an existing Collective + legitimate Fiscal Host + target initiative** willing to be an informed operator. Do **not** create a new financial platform, token, escrow or foundation. Open Collective confirms fiscal hosts are the legal parties holding funds, undertaking compliance and authorizing payouts: [Official Fiscal Host documentation](https://documentation.opencollective.com/fiscal-hosts/fiscal-hosts).
2. **Propose a non-spendable field action** to the Collective's verified administrator, e.g., bounded correction of eligible public campaign text, one authorized message slot, or opt-in improvements in campaign discovery. **No AI payment permission**, no unsolicited donor messages, no individual targeting. A technical identity with only the required edit capability is separate from the fiscal host's funds/custody role.
3. **Document F004 authority packet** with host/controller identity proof, source of funds and budget for attributable costs, the precise campaign URLs, affected user/partner consent, positive + no-action arms, grant issuer, allowed action/time/budget/expiry, revocation + emergency contact and independent provider readback. The grant must be issued/verified by the real operator, not signed by our test helper.
4. **No 40-campaign RCT assumed available.** The F002 hypothetical 20/20 design is unpowered and no cohort exists. First run a read-only retrospective plus a single operator-signed shadow/proposed campaign. An optional one-campaign authorized *technical P1/P2 dry run* can validate the provider chain, but it **cannot support F006 P4** and must not be called a pilot effect estimate.
5. After actual permission, implement a separate live adapter behind external security review; preserve Phase05 deny-by-default production scaffold, no wallet transfers. Operator remains responsible for publication/finance. The existing `OpenCollectivePublicLedger` is READ ONLY and cannot be used as a payment executor.
6. Preregister with valid statistical power, cohort/assignment, control, settlement window, cost/displacement checks, public challenge and null results. Only then perform carefully bounded actions and linked independent readback.

**Where to acquire that operator now:** [Browse suitable Fiscal Hosts](https://opencollective.com/), [host application guide](https://documentation.opencollective.com/fiscal-hosts/fiscal-hosts), [Open Collective staging environment](https://staging.opencollective.com/) for pretend funds only. [Official support](https://opencollective.com/contact) can clarify Japan eligibility, non-spend permissions and partner introductions. Existing fiscal host is the shortcut; one should not self-declare the Manager project as an incorporated legal entity or an already authorized grant sponsor.

**Alternative:** use a genuinely operator-owned legally established account/organization after rights and budget are explicitly certified; do not import Life Manager accounts, credentials, seller ledgers or finances without separate permission and technical isolation.

**Precise F004 clearance** requires a verifiable real issuer, an actually usable rights scope and resource budget, confirmed consent/public outcome terms, and a tested revocation path; template fields alone do not qualify.

## F007 — fastest legal path to a controlled indoor environmental pilot

### Data problem: existing solution reused today

[AirGradient's September 2026 indoor Map API](https://www.airgradient.com/documentation/kb/global-indoor-air-quality-dataset/) already offers opt-in publicly shared room readings via:
```text
GET https://map-data.airgradient.com/map/api/v1/indoor/measurements/current?pagesize=2&page=1
```
The [public sample API](https://map-data.airgradient.com/map/api/v1/docs) exposes PM2.5 (µg/m³), temperature, humidity, CO2 and measurement timestamps. Independent location IDs and coordinates, although obfuscated, still carry [linkage/reidentification risk](https://www.airgradient.com/documentation/kb/data-obfuscation-for-indoor-data-sharing/) and must not be republished. Our adapter outputs aggregate values, sample count, latest timestamp, content hash and explicit P0 only. Data rights and per-location license still need review before broad redistribution. Public site ≠ consent to instrument or change it.

### Physical actuation problem: select a controllable room, not a laboratory moonshot

1. **Location:** a private small office/room with a real responsible owner who gives specific written access and permission for a portable filter/fan. Do NOT assume an office is already available, and do not use any publicly opted-in AirGradient contributor's building as an actuator.
2. **Instrument:** one portable HEPA air purifier with manufacturer CADR/filter specification and safe normal use; two PM2.5 instruments ideally one independent vendor/reference, with colocated calibration and timestamped remote export. Add a watt-hour meter, decibel monitor, indoor temperature/humidity and an outdoor background reading (not a proxy for indoor). No need for a new robotics platform.
3. **Measurement independence:** allow read-only access for an external observer/instrument admin, with no sensor-data writes by the purifier controller. Consider AirGradient ONE/Home Assistant for open local telemetry and AirGradient opt-in public data for attribution; independent instrument certification cannot be created by our own logs.
4. **Safety:** occupancy/worker consent as applicable, placement away from direct exhalation/fan flow, no induced smoke, aerosols, incense or harmful PM2.5 exposures. Operator retains hard power-off, device shutdown and immediate stop authority. Review outlet and airflow constraints; avoid room ventilation changes unless separate facility approval.
5. **Comparative design:** prospective safe randomized ON/OFF crossover with stable observation windows and washout or an alternate-control room/period where feasible; log background, opening doors, other HVAC, occupancy, kWh, dB, temperature, humidity and occupants' discomfort. Low background PM2.5 or carryover may make a treatment effect INCONCLUSIVE, not “zero.”
6. **Independent field readback:** register sensor ID/source privately with the operator, publish only privacy-cleared aggregates if consented, and compare actual measured conditions to the predefined control. A sensor PM2.5 reduction is **exposure proxy P2**, never proof of fewer illnesses or improved life expectancy P3/P4.
7. **Never activate:** if ownership, occupant safety, device scope, independent monitor calibration, budget, acceptable sharing policy or stop procedure remains unknown, hold F007, select NO_ACTION. A study may be simulated without any device operation.

**Official references:**
- [AirGradient local integration in Home Assistant](https://www.home-assistant.io/integrations/airgradient)
- [Open Indoor Map and API](https://www.airgradient.com/documentation/kb/global-indoor-air-quality-dataset/)
- [Opt-in with privacy conditions](https://www.airgradient.com/documentation/kb/share-your-indoor-air-quality-data-publicly-on-the-global-indoor-air-quality-map/)
- [Public/local token boundaries](https://www.airgradient.com/documentation/kb/where-do-i-access-the-api-documentation-api-token-and-local-api/)
- [EPA low-cost indoor monitor limitations and placement](https://www.epa.gov/indoor-air-quality-iaq/low-cost-air-pollution-monitors-and-indoor-air-quality)
- [AirGradient public-data attribution and licensing](https://www.airgradient.com/documentation/kb/kb-diy-data-ownership-and-sharing)

**Precise F007 clearance** requires actual named site/owner rights, permission for a bounded purifier intervention, safe occupants, physically present independent calibrated indoor sensor and revocable stop authority. The currently tested public map has **no site-level grant**.

## Everything after the blockers is already dependency ordered

| Task | Concrete field objective | Scientific success condition |
|---|---|---|
| F005 | one real bounded authorized finance intervention with linked provider receipt and independently seen change | P1 action vs P2 outside readback; no provider success-only upgrading |
| F006 | campaign-level randomized NO_ACTION vs treatment, actual net contribution and human-side harms | preregistered primary outcome, independent data, CI/attrition/displacement; inconclusive if unpowered |
| F008 | authorized room purifier field exposure intervention, independent PM2.5 + kWh + dB measurements | real timed contrast with confounders; no inference of clinical welfare |
| F009 | both sectors with independent P2+ and unchanged core authority/source/effect logic | genuine two-domain field replication, no simulation substituted |

## Evidence clearance checklist — independent external sources

**Finance must provide:** `fiscal_host_or_operator_ref, legal_entity_and_country_ref, funding_custody_ref, scoped_grant_ref, grant_verified_by_operator_ref, budget_currency_and_max_ref, target_campaigns_and_rights_ref, revocation_check_ref, participant_consent_ref, independent_receipt_source_ref, external_preregistration_ref, harm_displacement_plan_ref`.

**Environment must provide:** `site_owner_ref, room_access_and_safety_ref, permission_for_portable_actuation_ref, independent_sensor_ref, sensor_public_api_provenance_ref, calibration_ref, electricity_noise_measurement_ref, stop_and_rollback_ref, occupant_consent_ref, independent_trial_review_ref`.

Represent private permission documents as nonidentifying opaque source references in the public template; originals stay with issuers and designated reviewers. Do not put bank statements, tax records, personal addresses, tokens, private contacts or identities into public Git.

A filled checklist gives only `AWAITING_INDEPENDENT_VALIDATION`. It can NEVER change `can_execute` to `true`. Once a legally binding capability is verified, implement separate independently audited policy and authenticated execution code, with real external receipts. No autonomous self-issuance or default effect flag override.

## Immediate handoff for outreach

Contact the official platform technical teams about **eligibility and rights**, not with a claim of completed authorizations. Templates and contacts:
- Open Collective [official contact](https://opencollective.com/contact), published support contact `support@opencollective.com`: country/host eligibility, nonprofit or opt-in fundraiser partnerships, permission-scoped campaign editing with no spend, independent receipts, staging, prior scientific trials.
- AirGradient [support site](https://www.airgradient.com/support/), documented `support@airgradient.com`: nonpersonal opt-in indoor license, best calibration/independent instrument practices, public readback, institutional pilot suggestions.
- Actual finance partner/room owner has NOT been selected or provided a valid grant by this document. Any provider answer is not itself a signed grant.

## Reproduce

```sh
cd products/manager
python3 -m unittest discover -s tests -v
python3 scripts/phase06_public_finance_readback.py --collective webpack
python3 scripts/phase06_public_indoor_readback.py
python3 scripts/check_phase06_authority.py
python3 scripts/check_boundaries.py
python3 scripts/make_roadmap.py --check
```

This runbook advances readiness while **preserving F004/F007 as blocked** until actual rights. Real population/medical welfare benefits: NOT_MEASURED. Research provenance P0, no published Transparent Blessing.
