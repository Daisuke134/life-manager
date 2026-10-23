# Manager public-interest charter — draft

**Charter ID:** `MGR-G001-CHARTER-20261022-v1`. **Source design: SOURCE_DESIGN_ACCEPTED (actual root event recorded in the [bounded acceptance receipt](../verification/G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md)). Operational adoption: UNADOPTED.** Prepared 2026-10-22 JST / 2026-10-21 UTC. Adopting operator: **unappointed**. Independent oversight: **unappointed**. External audit: **NOT_PERFORMED**. This is a proposed operating constitution for G001, not a grant of public authority, an adopted legal charter or proof of beneficial effects.

The canonical task registry remains [tasks.json](../roadmap/tasks.json). Task completion covers only the finite source/offline design; its actual acceptance event is recorded in the receipt. It neither expands nor suspends the existing, separately authorized routine publication of Manager's owned internet surfaces. An already valid standing release grant does not acquire a new per-run approval requirement from this draft.

## 1. Purpose and limits

Manager aims to make bounded, evidenced improvements through authorized actions while preserving people's autonomy, privacy and ability to challenge results. A metaphor such as “digital Buddha” expresses an aspiration; it gives the system no public office, professional license, mandate over people, ownership of others' assets or exemption from accountability.

The operator must distinguish an executed action, an independently observed artifact, a measured human outcome and a causal net improvement. A successful deployment, generated statement or favorable model estimate is not evidence that suffering decreased. Unknown outcomes and harms remain explicit. Negative, ineffective and disputed interventions remain auditable under the [incident, appeal and audit procedure](INCIDENT_APPEAL_AND_AUDIT_PROCEDURE.md).

No model can grant itself rights, expand a budget, extend permission expiry, select a new target, remove a stop or declare independent approval. Third-party accounts, money, facilities, communications and private records require their own actual authority. Public availability of a source establishes neither control of its publisher nor permission to collect individual data.

## 2. Standing authority and scope

An adopting operator must identify its actual asset-control authority and the independently verifiable standing grant. The grant must state its issuer, immutable reference, domain, action, exact repository/branch/path or service target, budget unit and finite limit, valid-from/expiry times, revocation mechanism and rollback scope. Authority belongs to the real issuer; a self-written permission record or fixture signature is insufficient.

Routine operations within that standing scope may proceed without repeated human confirmation when their existing preconditions pass. New targets, new powers, larger budgets or longer validity require an authentic owner-issued change. A model may propose a change; it cannot make the change effective. Narrowing a proposal does not authorize an activity missing from the original grant.

The current [digital surface inventory](../product/DIGITAL_ENVIRONMENT_SURFACE_INVENTORY.md) documents the owned-publication context. This charter is not a replacement inventory or permission source. Manager's research/product subtree and authorized publication paths remain isolated from Life Manager runtime and unrelated products. The adopting operator must bind the actual approved scope rather than copy a broad repository name into an unrestricted grant.

Budget units must remain explicit. An action-count limit is not a currency limit; a free-tier charge of zero is not zero resource use. Preserve the current JPY 0 incremental paid-spend limit where applicable and the existing finite release/action envelope separately. Do not invent a positive financial grant to fit an offline fixture type. Record actual compute, review time and cost uncertainty in original units.

## 3. Operator and oversight roles

The following responsibilities are proposed; **no appointment or acceptance is established by this document**.

| Role | Responsibility | Separation and authority |
|---|---|---|
| Accountable asset owner / adopting operator | Establish legitimate scope, budget, stop and revocation; remain responsible for operations and correction | Must be the actual authority holder or documented delegate, not the model |
| Release operator | Execute only approved-scope releases, preserve baseline/readback and use bounded rollback | Cannot expand its own grant or convert a test fixture into live permission |
| Incident custodian | Preserve minimal nonpersonal evidence, maintain the incident trail and route concerns | Cannot erase unfavorable events or publish private reports |
| Independent oversight reviewer | Examine conflicts, material incidents, unresolved harm, recovery and challenges | Independent of the disputed action and its success incentives; disclose limitations and conflicts |
| Appeal reviewer | Reconsider a challenged decision using evidence and the original scope | Must not be the original decision-maker; if a qualified independent reviewer is unavailable, the appeal stays unresolved |
| External auditor | Independently examine a defined period, scope and evidence population and issue a report | No external auditor is presently appointed; internal chain verification is not an external audit |

Small operations may combine administrative roles where conflicts are documented. The original decision-maker may not decide their own appeal or label their own review independent. Human-outcome research additionally follows the [public-aggregate collaboration protocol](../../pilot/PUBLIC_AGGREGATE_COLLABORATION_PROTOCOL.md) and its appropriate independent safety roles. That optional research process is separate from ordinary anonymous digital publication.

## 4. Mandatory stops and revocation

The proposed stop vocabulary matches `STOP_CONDITIONS` in [governance.py](../../manager_core/governance.py):

| Stop condition | Required disposition |
|---|---|
| `operator_stop` | Do not start the affected action; stop queued actions where possible, preserve evidence and retain verified ordinary support access |
| `unknown_effect` | Reconcile the prior action with independent evidence before any retry that could duplicate its effect; unknown is neither success nor failure |
| `harm` | Suspend the implicated action or study component, protect affected people through the responsible operator, and obtain appropriate independent assessment |
| `authority_revoked` | Reject further use of the grant; expiration, missing authenticity or unverified authority likewise cannot permit execution |
| `out_of_distribution` | Abstain where the population, environment or action lies outside evaluated scope; do not infer safety or effectiveness from an unrelated holdout |

Stop and revocation must be usable by the real operator outside model discretion. A paused system cannot resume itself by editing the charter, replacing the grant issuer or relabeling an unknown outcome. Revocation must affect pending authorization, not merely a documentation label. Existing bounded corrective releases may still restore verified safe navigation when authorized; do not block necessary correction to preserve an experiment or metric.

These are proposed operating requirements. The present governance module is **offline preparation**: `governance_preflight` checks an explicit stop flag, unresolved-effect count, holdout assessment and scope-preserving grant verification. It returns `OFFLINE_PREFLIGHT_PASSED` / `OFFLINE_CANDIDATE_ONLY`, always with `can_execute=False`. It neither implements a live revocation service nor independently detects harms. A responsible caller must translate a relevant harm or operator stop into the stop state. [authority.py](../../manager_core/authority.py) uses fixture HMAC grants and expressly does not establish live legal authority.

## 5. Evidence, publication and correction

Retain the action's source/version, target, authority reference, decision, costs, attempt, receipt, independent readback, uncertainty, evaluation and any incident in the existing restricted audit mechanism. Keep distinct evidence for `INEFFECTIVE`, `WORSENED`, `UNKNOWN`, `HARM`, `APPEAL` and `RESOLVED`; resolution is an administrative disposition, not erasure of the event or a proof-level upgrade.

Public records are minimal, nonpersonal artifacts or disclosure-reviewed aggregates. Do not publish identities, private financial or health evidence, credentials, individual questionnaire answers or complainant narratives. The audit field allowlist and credential checks do not constitute a general personal-data detector. Use reviewed reason codes and public evidence references. Private research material stays with its authorized custodian under the separate study protocol.

Corrections append a dated explanation with the affected public record and replacement evidence; preserve what was previously claimed. Retract unsupported benefit claims promptly. If unsafe information or an accidental private disclosure must be removed from a serving surface, preserve a nonpersonal correction notice and appropriately restricted incident record without mirroring the sensitive material. A SHA-linked SQLite trail can detect inconsistent edits in the retained chain; an operator controlling the database can replace the chain. External snapshots or signatures are necessary to support a stronger integrity claim, and neither proves source truth by itself. [Audit implementation](../../manager_core/audit.py)

## 6. Appeals, recovery and public accountability

An adopting operator must supply an actual accessible appeal channel and public audit location, with responsible staffing and limits. A nonexistent or unmonitored URL cannot satisfy adoption. People may challenge source accuracy, scope, impact, omissions, accessibility, privacy or a claimed resolution without having to disclose a sensitive personal history. An appeal may be anonymous where the remedy permits; ordinary support must not be withheld because of a complaint.

The [operating procedure](INCIDENT_APPEAL_AND_AUDIT_PROCEDURE.md) fixes intake, acknowledgement targets, independence, retention, evidence review and recovery gates. Targets become operational commitments only after a real operator adopts and staffs them. Missing staffing is an explicit capability gap, not an invented service-level guarantee.

Recovery after a material incident requires preserved evidence, authenticated continuing authority, reconciliation of unresolved effects, correction and independent verification, a bounded rollback/restart plan and the appropriate independent disposition. Ordinary subsequent runs inside the same valid standing scope do not need a new human approval. An incident-specific recovery decision is not a permission for unrelated expanded actions.

## 7. Adoption record and amendment

The finite source/offline design may be accepted separately from actual operational adoption. Such acceptance requires the root's review of the applied source revision, current code and verification, and actual acceptance of the original dependencies K007 and V001. It establishes the bounded charter, authority/stop rules and review process in source; it creates no live grant, role appointment or staffed appeal service. The [bounded acceptance receipt](../verification/G001_G002_SOURCE_DESIGN_ACCEPTANCE_20261023.md) records actual root SOURCE_DESIGN_ACCEPTED decisions, the original requirements and technical evidence after confirmation of K007/V001 done → G001 → G002. The recorded actor is the Codex root AI technical/design reviewer under standing development authorization; no operational adoption date is established. The existing [owned-cycle stop state](../../manager_core/owned_cycle.py), [trusted run control](../../scripts/run_owned_digital_cycle.py) and [historical E16 stop/resume evidence](../verification/E16_DEPLOYED_ACCEPTANCE_20261023.md) remain governed by their existing authority and recovery gates.

For actual operational adoption, publish a dated record binding this exact version/hash to the accountable operator, authentic standing-grant reference, scope/budgets, stop/revocation owner, functioning audit and appeal URLs, assigned roles and conflicts, evidence retention and review schedule. The record must distinguish responsibilities currently staffed from capabilities not yet available. A machine-readable `PublicInterestCharter` should be constructed only with genuine values; this draft intentionally supplies no placeholder operational URLs or invented issuer.

Amendments retain the prior hash, rationale, approving authority and effective date. An amendment cannot retroactively authorize an out-of-scope action, erase a harm, silently change an evaluation endpoint or claim an external audit that did not occur. Implementation tests can verify bounded contract behavior; they cannot adopt the charter for an organization.

**Current disposition:** source design `SOURCE_DESIGN_ACCEPTED` (actual root acceptance recorded in the receipt); operational adoption `UNADOPTED`; adopting operator and independent roles unfilled; public appeal service not established by this draft; external audit `NOT_PERFORMED`. Existing separately authorized publication remains governed by its actual authority. The draft is byte-bound in [GOVERNANCE_DRAFTS_20261022.sha256](GOVERNANCE_DRAFTS_20261022.sha256).
