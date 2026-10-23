# Incident, appeal and audit operating procedure — draft

**Procedure ID:** `MGR-G002-OPERATIONS-20261022-v1`. **Source design: SOURCE_DESIGN_ACCEPTED (actual root event recorded in the [bounded acceptance receipt](../verification/G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md)). Operational adoption: UNADOPTED.** Prepared 2026-10-22 JST / 2026-10-21 UTC. No operator has adopted the proposed staffing, response targets or retention rules; no external auditor or appeal reviewer is appointed. This is a usable procedure for adoption alongside the [public-interest charter](PUBLIC_INTEREST_CHARTER_DRAFT.md), not a report of incidents handled or audits completed.

The procedure reuses [governance.py](../../manager_core/governance.py), [audit.py](../../manager_core/audit.py), existing authority checks and the original task registry. It adds no runtime permission, second incident database or task-status authority. Ordinary releases within an already valid standing grant remain possible without per-run human approval.

## 1. Intake and immediate containment

The adopting operator publishes the real audit and appeal channels, responsible staff, service hours and accessible alternatives. Until those exist, do not advertise this draft as a monitored service or submit private reports into repository issues. A public repository or article link is evidence access, not a staffed complaint channel.

On a concern, the custodian records the affected public action/run, public version, discovery time, category, minimal reason code and any public evidence reference. Accept a report without demanding private financial records, health details or identity. If the reporter supplies sensitive material, keep it out of Manager/model prompts and route it to the appropriate authorized custodian; the public record contains only a nonpersonal description of the issue and disposition.

| Initial condition | Immediate operator response | Proposed response target after adoption |
|---|---|---|
| Credible serious harm, material private-data exposure or compromised authority | Suspend the affected operation, prevent further disclosure/effects where possible, preserve restricted evidence and use the responsible professional/security process | Start containment promptly; initial independent disposition targeted within 24 hours; do not claim continuous staffing unless it actually exists |
| Unknown external effect or mismatched receipt/readback | Mark `UNKNOWN`, stop retries that could duplicate effects, preserve the attempted action and reconcile independently | Triage within 1 working day; remain paused while effect state is unresolved |
| Ineffective action, worsened measured result, broken/false referral or accessibility defect | Record the unfavorable result; disable or revert the implicated change where material; assess whether harm or rights escalation is needed | Acknowledge within 2 working days; provisional assessment within 5 working days |
| Appeal or evidence challenge without immediate harm | Record `APPEAL`, preserve the challenged record, assign a reviewer independent of the original decision | Acknowledge within 2 working days; reasoned disposition targeted within 10 working days or explain the delay and next review date |

These are proposed operating targets, not clinical guidance or an existing service guarantee. Overdue or unavailable review must be visible in the public status; it does not clear an uncertain action for restart. Human-research concerns also follow the [independent safety protocol](../../pilot/MENTAL_OUTCOME_SAFETY_AND_INDEPENDENT_REVIEW.md), with private case assessment by the responsible qualified reviewer. A public interface is not an emergency-monitoring service.

## 2. Preserve every outcome class

`IncidentReport` supports the following fixed outcomes. Use the recorded meaning and its evidence limit; do not turn missing benefit evidence into demonstrated ineffectiveness.

| Outcome | Meaning in the record |
|---|---|
| `INEFFECTIVE` | A predefined technical or measured outcome was not achieved, with the relevant observation and limits stated |
| `WORSENED` | A valid observed measure moved in an unfavorable direction; causal attribution is a separate assessment |
| `UNKNOWN` | The effect, verification, outcome or required evidence remains unresolved |
| `HARM` | A reported or observed adverse effect requires protection/review; retain whether relatedness is established or still uncertain |
| `APPEAL` | A decision, evidence record, omission or claimed resolution is challenged |
| `RESOLVED` | A documented administrative disposition and remedy; it does not delete earlier incidents or establish a human benefit |

Record these using the existing `record_incident(audit, incident)` path. It appends an `evaluation` event containing `status`, `reason`, optional public-evidence SHA-256 and timezone-aware `recorded_at`. Its current benefit status remains `NOT_MEASURED` and proof level `P0`. Do not edit the implementation to make a governance event appear to be P3/P4 evidence.

`run_id` identifies the existing action/run, never a person. Use an approved concise reason code such as `official_destination_unverified` or `receipt_readback_mismatch` and a separately reviewed nonpersonal explanation where needed. Hashes must identify approved public evidence, not unsalted hashes of names, contact details or predictable sensitive answers. If evidence is private or unavailable, keep `evidence_sha256=None` and state the limitation through a safe reason; a missing hash is not permission to invent one.

Append related recovery and correction events to the same run using existing allowed audit fields/stages and identify the public earlier event/version. Do not overwrite the prior status. A `RESOLVED` event leaves `HARM`, `UNKNOWN` or `APPEAL` events in the trail. The interface counts events, so repeated reports must not be represented as distinct people or interventions.

## 3. Evidence preservation and integrity

Preserve the approved source snapshot/version, original grant reference and scope, policy version, bounded cost, intent/attempt, provider receipt, independent readback, evaluation, stop decision and subsequent correction. Retain ineffective and negative cases alongside favorable ones. Document gaps explicitly, including absent external receipts, inaccessible sources, unknown harms and missing comparisons.

Use `incident_inventory` with requested run IDs and an independently supplied finite `population_run_ids`. The population must come from authorized execution/outbox source records, with its scope, source period, immutable source revision and source-snapshot SHA-256 retained in the review evidence. Do not derive it from the incident list or pending-only outbox records. Include owned effects across all statuses and rollbacks as a distinct kind; supplement them with existing run/decision records for NO_ACTION, refusals and pre-execution failures. Declare the run/occurrence-to-effect/attempt/receipt/readback/evaluation mapping. Unavailable or unrecorded source evidence stays an explicit UNKNOWN/GAP. This design does not claim an automatic runtime-wide ingestion adapter or authenticate a caller-supplied population.

`population_reconciled` is tri-state: `None` (JSON `null`) means no population was supplied; `False` means a declared population has missing requested IDs (`missing_population_run_ids`), unexpected requested IDs (`unexpected_run_ids`), absent requested traces (`missing_trace_run_ids`) or an invalid chain; `True` means only that the requested IDs equal the declared finite population and their traces are nonempty with valid chains. An explicitly declared empty population can reconcile only within that empty scope. This result does not establish complete outcome classification, required receipt/evidence completeness, source authenticity, external audit or the absence of incidents in the wider world.

Returned traces, `counts` and `chain_valid` cover requested runs only; counts are the actual retained incident-class evaluation events, not distinct people or interventions. Omitted population runs are reported as missing, without loading their traces or assigning them zero incidents. Review unclassified runs, missing receipts/readbacks and other required evidence separately against the preserved source mapping, even when ID/trace reconciliation is `True`. An empty or omitted record cannot silently become “no incident.”

The SHA-linked SQLite chain is an integrity check on the retained events, not a tamper-proof ledger. An operator with database control could replace it. For an actual reviewed release, publish a disclosure-reviewed nonpersonal snapshot manifest with date, scope, source commit, file hashes and custody/attestation under the existing authorized channel. Preserve the prior externally published reference. A matching hash authenticates bytes against that reference, not the underlying outcome or legal authority. No external snapshot, signature or audit is claimed to exist by this draft.

The audit allowlist restricts field names and primitive values; its credential checks do not comprehensively detect personal information. Review free-text reasons before public release. Never include secrets, private reports, individual financial/health records or contact details in the audit database, public artifacts, CI logs or model context. If such material enters a public surface, stop further distribution, remove exposed serving copies within actual authority, preserve necessary evidence in restricted custody and publish a nonpersonal correction. Do not duplicate the sensitive content to explain the incident.

## 4. Retention, public aggregates and corrections

The adopting operator must confirm that this proposed schedule fits its actual obligations and capabilities before publishing it as a promise:

| Record | Proposed retention and access |
|---|---|
| Nonpersonal run evidence and incident trail | Retain at least 24 months after final disposition; preserve longer while an appeal, audit or material uncertainty remains open. Review yearly for unnecessary detail. |
| Published nonpersonal audit manifests, decisions and corrections | Preserve version/history for reproducibility under the existing repository/publication policy; public copies cannot be guaranteed erasable. Retire unsupported claims with a correction/retraction rather than silently deleting their history. |
| Reporter contact or restricted incident correspondence, if a real operator needs it | Separate from Manager; retain only to resolve the concern and for up to 90 days after closure, unless a documented applicable requirement or unresolved appeal requires longer. Explain any longer period to the reporter where appropriate. |
| Human-study records | Follow the separately adopted consented research retention plan; this procedure neither imports those records into Manager nor changes participant withdrawal terms. |

Public reporting contains nonpersonal operational facts or disclosure-reviewed aggregates. For sensitive human-outcome/complaint categories, apply the [public-aggregate protocol](../../pilot/PUBLIC_AGGREGATE_COLLABORATION_PROTOCOL.md): small cells, complements, rare events, overlapping releases and outliers require suppression or withholding. A minimum cell-size rule is not an anonymity guarantee. Do not publish raw free-text complaints or infer a person's circumstances from an incident count.

Every correction states the affected version/event, correction date, reason, changed interpretation, replacement evidence and remaining uncertainty. Append a correction event and update public-facing claims; retain the prior nonpersonal record/reference. If the source retracts evidence, withdraw the dependent claim rather than preserving an unjustified proof level. Lack of public access to confidential evidence is a stated audit limitation, not a fabricated independent verification.

## 5. Appeals and independent audit

An appeal can challenge authority, source authenticity, inaccessible information, missing harms, outcome interpretation, exclusion from evidence, or the adequacy of a remedy. The reviewer obtains the original decision and available legitimate evidence, identifies conflicts, distinguishes verified facts from allegations, and provides a reasoned decision. Do not demand a sensitive personal disclosure as the price of challenging a public claim.

Permitted appeal outcomes are **UPHELD**, **PARTLY_UPHELD**, **NOT_UPHELD_WITH_REASONS**, and **UNRESOLVED_INSUFFICIENT_EVIDENCE**. These are document dispositions; the existing event taxonomy stays `APPEAL` followed by an appropriate documented `RESOLVED` or continuing `UNKNOWN` event. A reviewer may require a correction, withdrawal of a claim, repair, scoped stop or further evidence. The original decision-maker cannot certify their own appeal review as independent. If no qualified independent reviewer is available, preserve the appeal as unresolved and maintain any necessary stop.

For a future external audit, appoint an independent reviewer with a documented scope, competence, conflicts, evidence-access limits and reporting terms. The proposed audit period is the first 90 days after actual operational adoption, then every 90 days while operating, plus a review after a material incident. This future operating schedule and any optional human study are not prerequisites for accepting the original finite source-process design. Examine all material harm, unknown-effect and appeal cases; reconcile all run IDs and inspect a declared sample of ordinary/no-action cases. Record the sample and omissions rather than calling a convenience sample complete. Private information remains with authorized custodians; external audit access is separately controlled.

The report must state: period, actual reviewer/independence, complete run population and reconciliation gaps, event counts and unresolved cases, authority/budget checks, chain/snapshot checks, outcomes and harms limits, corrections, conflicts and follow-up actions. `incident_inventory.external_audit_status` currently equals **NOT_PERFORMED**. Calling that function, passing a unit test or reading a local hash does not change the status into a performed external audit. A real auditor's attributable report is separate evidence.

## 6. Recovery and closure gates

Before resuming an implicated action after a material incident, record each applicable gate and its evidence:

1. The issue and affected scope are identified, evidence is preserved, and the responsible operator and independent reviewer are known where required.
2. Continuing authority is authentic, within target/budget/time, not revoked, and available through the actual execution channel. The agent has not amended its own grant.
3. Prior attempts and possible external effects are reconciled. Unknown effects remain stopped; a retry cannot be used to discover whether an irreversible action already occurred.
4. The correction or rollback is within existing authority, restores a verified safe state, and passes the focused checks relevant to the incident. The old version is not assumed safe if its sources or authority have expired.
5. Independent readback corroborates the actual result rather than relying only on the write log or model report.
6. Material harm, privacy, research-consent or safety issues have the appropriate independent disposition. Unresolved safety or missing capability keeps the implicated action at **NO_ACTION**.
7. The recovery record states changed behavior, remaining limits, monitoring and rollback/stop owner. Any necessary prospective protocol amendment is versioned before new study exposure.
8. Append the recovery/closure disposition, publish a minimal correction where relevant, and notify a reporter only through the actual consented/authorized channel. Do not send messages merely because this draft describes the process.

The procedure does not assert that these operational integrations or staffing exist. A documented restart permits only the already authorized scope; subsequent routine actions do not require repeated human confirmation. Recovery cannot grant new public authority, approve unrelated targets, erase unfavorable events or establish human causal improvement.

## 7. Present state

The finite source design is **SOURCE_DESIGN_ACCEPTED** under the [bounded acceptance receipt](../verification/G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md). Root recorded actual applied-source review/verification and dependency acceptance K007/V001 → G001 → G002, making the bounded source-design acceptance effective. The recorded actor is the Codex root AI technical/design reviewer under standing development authorization; no operational adoption date is established. Operational adoption remains **UNADOPTED**, with no appointed external auditor or appeal service and no completed audit asserted; `external_audit_status=NOT_PERFORMED`. Its source design addresses G002's requirement to preserve ineffective, worsened and unknown interventions for scrutiny. The code remains offline governance preparation and the accepted G002 done status covers this finite design only and does not certify an actual population run. Exact draft bytes are listed in [GOVERNANCE_DRAFTS_20261022.sha256](GOVERNANCE_DRAFTS_20261022.sha256).
