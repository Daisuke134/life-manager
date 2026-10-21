# Phase 06 F004–F009 — Real intervention execution blueprint

**Status:** DESIGN / NOT PERMITTED TO EXECUTE CURRENTLY. **Canon:** [tasks.json](../../roadmap/tasks.json). Founder approval covers Manager research/software development; it is not a verifiable third-party bank, donor, property, occupant, laboratory, or community legal authorization. F004/F007 remain **BLOCKED**; F005/F006/F008/F009 **TODO**. **No actual Manager-caused field benefit has been measured.**

## Cross-phase method: sim → shadow → field → independent causal net impact

| Stage | How it works | Evidence | Can call a Blessing? |
|---|---|---|---|
| Public observation | exact URL, rights, SHA, timestamp, PII classification, units | provenance P0 | NO |
| Prediction / simulation | Simile/Aaru-style response distribution; Andon agent task trajectory | separate TVD, error model, causal ATE error P0 | NO |
| Shadow deployment | proposal/no-action with *no external action*, independent comparison against future real observations | outcome forecasting P0 | NO |
| Authorized field action | real issuer signature, grant, budget, revocation, idempotent execution and official provider receipt | P1 if independently authenticated | NO, not sufficient |
| Independent readback | separate provider/sensor observes actual change for same action/time, not model log | P2 if verified | NO, not sufficient |
| Beneficiary measurement | resource/health/exposure/service outcomes, harms/costs and follow-up | P3 only if substantive benefit measured | Preliminary only |
| Causal net evaluation | contemporaneous randomized comparator or justified quasi-experimental design, CI, harms, no displacement double count | P4 after independent scrutiny | Potential, bounded to study |
| Replication | other site/population/domain with same critical invariants | P5 evidence | stronger, never universal |

## Finance track F004 → F005 → F006

### F004 — obtain REAL issuer authority, budget and beneficiary rights (BLOCKED)
**Potential operators:** consented public charity/collective, its legally responsible fiscal host; or a genuinely Manager-owned legal account whose owner has affirmatively delegated bounded authority under platform terms. The previously implemented Open Collective F003 read-only GraphQL interface is **not an authorization** to perform transfers. Funding rules must identify the actual legal source, issuer entity, purpose, treasury account, beneficiary eligibility, consent, allowable action names, spend cap, daily/multiday limits, expiry, key custody, revocation and conflict-of-interest handling. Require operator-signed, server-verifiable grant; do not let the AI mint its own trusted issuer. Confirm publicly verifiable aggregate financial ledger and a separate genuinely corroborated settlement/beneficiary readback. Keep `money_transfer=false` until a newly reviewed *separate* live adapter is built and approval is verified.

**Non-financial first alternatives:** read-only public donation/gov program observations, forecasting historical outcomes, improving information available on Manager-owned pages, open-source pull requests with maintainer acceptance. These can demonstrate capability but **do not mark F004 done** when funding authority is still absent. F004 task status must be evidence-driven, not relabeled.

### F005 — first real bounded financial intervention and receipt (TODO; requires F004)
Precommit a specific intent containing allowed object ID, amount minor units, grant ID, no_action comparator, source snapshot, expiration, spend limit and idempotency key. Refuse forged/revoked/missing/expired grants, 401/403, mismatched currency, recipient, unknown rights and unspecified costs. Perform exactly one reversible, low-harm action *through the owner's authorized adapter* only after independent permission checks; the implementation should not pass through our offline fixture type or alter unrelated Life Manager product state. Verify official provider receipt, reconcile asynchronous/unknown provider state without blind retransmission. Independently read back actual transaction/beneficiary effect from a distinct source, with transaction ID/timestamp/purpose linkage. A provider "SUCCESS" log without readback remains P1 at most or UNKNOWN.

### F006 — actual causal net improvement report (TODO; requires F005)
Read [existing locked F002 design](../../pilot/PREREGISTRATION.md). It is a **prospective design only**, hypothetical 40 campaigns, not an actually powered registered trial. Before F005, secure real opt-in cohorts, an independent sample-size/power plan, ethics/financial compliance review and **publicly timestamped immutable assignment/estimand**. Use intent-to-treat by predefined campaign groups, same period, explicit NO_ACTION, not just a before/after screenshot. Assess
`incremental confirmed outside aid - refunds - fees - attributable costs`
plus displacement and separately observed human welfare. Preserve uncertainty intervals and negative results. Different currencies, token amounts, self-funded matching, listing bounties and transferred ownership cannot be summed as new wealth. If none can be independently checked: **INCONCLUSIVE**, never a P4 claim.

**Crypto/UBI wedge variant:** do not assume daily G$ or CRC minting creates real income. If an actual consenting partner proposes legally accepted digital-value distribution, identify cash-out/merchant acceptance, fraud/sybil risk, consumer cost, privacy, pricing and inflation, and preregister actual net retained purchasing power against NO_ACTION. On-chain event proofs can support transaction P1/P2 but rarely prove beneficiary wellbeing P3/P4 without separate measured outcomes. An on-chain market or new token is **not necessary** for the Manager.

## Environment track F007 → F008

### F007 — authorized physical space and independent instrument (BLOCKED)
Obtain *identified* controlled site and facility owner's specific written permission (room/device/time/treatment, stop access), occupants' appropriate safety/consultation, air system warranty/health compliance, baseline PM2.5 instrument calibration and independent timestamped indoor sensor data plus outdoor covariates. Independent monitor must not share the executor's writable control plane, and rights/limits must be revocable. Public OpenAQ outdoors alone proves neither indoor exposure nor right to actuate. Open-source sensor/hardware (e.g. calibrated local PM2.5 monitor) may be reused *after rights/safety review*, but public availability is not control authority.

### F008 — registered counterfactual and physical outcome (TODO; requires F007)
For an owner-controlled room/fan/filter intervention, randomly assign safe identical-length room/time conditions or randomized crossovers/stepped rollout, accounting for carryover, outdoor background, occupancy, CO2/temperature/humidity and device calibration. Predeclare duration, device cost, observed `PM2.5 µg/m³`, `kWh`, `dB`, occupant discomfort, maintenance and emissions proxies; include NO_ACTION. Record controller setting and independent before/during/after sensor, and immediate safe rollback thresholds. Estimate exposed-area net change with credible confidence interval. A lower PM2.5 reading is an **exposure proxy** and must not be presented as clinically demonstrated fewer illnesses.

### F009 — same core, two genuinely different live environments (TODO)
Only after F005/F006 and F007/F008 have verifiable P2+ at a minimum may F009 compare domains. No changes to core source/observation/authority/outbox/reconciliation/evaluation/learning/audit types. Compare domain adapters, source rights, authority enforcement, idempotency, readback independence, safety shutdown, harms and counterfactual eligibility. A new unsupported domain MUST downgrade the status to UNKNOWN/NO_ACTION, not be coerced into a positive success.

## Existing primitives NOT to rebuild
- `manager_core/authority.py`, `outbox.py`, `reconcile.py`, `verifier.py` (Phase05 offline only).
- `manager_core/adapters/public_finance.py` for *historical* open-collective observation (F003, no effect).
- `pilot/PREREGISTRATION.json` for initial design schema (F002, no live cohort).
- [DoWhy](https://github.com/py-why/dowhy) for identification/refutation, [CausalPy](https://github.com/pymc-labs/CausalPy) for time-series/quasi-experimental sensitivity, [Open Bandit Pipeline](https://github.com/st-tech/zr-obp) for logged-propensity policy value, [OpenAQ](https://docs.openaq.org/resources/measurements) as an external air-condition covariate only.
- [Behavior Change for Good megastudy](https://www.nature.com/articles/s41586-021-04128-4), [HeartSteps](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/), [Opower field trials](https://www.sciencedirect.com/science/article/pii/S0047272711000478), [GiveDirectly UBI study](https://www.givedirectly.org/2023-ubi-results) for authentic multi-arm, field-horizon and harm design references. Need source license review before raw replication.

## What is needed beyond this document

| Needed evidence | Who can supply/verify | Why not available yet |
|---|---|---|
| Authorized finance issuer, account/grant, funds, repayment/refund, benefit measures | Legal account holder / funder / finance provider | Not supplied to Manager; general development permission insufficient |
| Randomized consenting cohort + independent study preregistration | Institutional/consenting partner | F002 design is not a real participant registry or powered study |
| Actual P1/P2 receipts and beneficiary data | Provider and unrelated external measurement channel | No Manager-originating field action |
| Occupant-safe indoor location, actuator and calibrated sensor | Property owner and independent monitor | No F007 facility/measurement contract |
| Cross-domain P2+ reproducibility | Two real sites with independent evidence | Not provable by finance/env mock adapters alone |

**Default state:** keep live writes, money transfers, physical actuation, public posting, private-person processing disabled. No approval question is needed for ordinary source research and safe engineering; rights-gated external effects await authentic capability and partner evidence. **Beneficiary improvement remains NOT_MEASURED, scientific Gate1 UNMET**.
