# Manager D003 — published disbursement and report connection

## Purpose and original acceptance

Original D003 depends on D002 and has no external prerequisite. It connects
公表された支援先の受益報告と資金移動を別の証拠として接続 and verifies
第三者報告がない経済的生活改善は未測定と明示する.
This unit is an offline source connection, not a new intervention or proof of
Manager-caused benefit. It adds no UI and preserves the owner-directed priority
of agent work before articles. User delegated implementation choices and opted
out of repeated approval/questions; the choices below are the controller's.

## Approaches and decision

1. Convert outgoing public expenditures into existing incoming FundingLedger:
   rejected because direction, settlement and unknown report-window meanings differ.
2. Build a generic IATI/PDF ingestion engine: unnecessary for one reviewed source
   and would introduce parsing/privacy/dependency work unrelated to D003.
3. **Selected:** a source-specific loader for a reviewed, immutable aggregate
   packet. Reuse `Source.verify_content` and the pinned-artifact pattern in
   `evidence.load_verified_trial`. Pin the reviewed packet's SHA and immutable
   public URL independently of caller-supplied Source metadata. This is a fixed
   snapshot connection, not an extensible schema or automatic truth verifier.

## Evidence and scope

The retained publisher XML activity US-EIN-27-1661997-Ug-refugees-pilot links
directly to the retained Uganda pilot report PDF. Three selected type4 outgoing
beneficiary expenditure rows total **290390000 USD minor**. They cover quarters
2017-Q4, 2018-Q1 and 2018-Q2; dates have day precision and coverage is partial.
Incoming type1, type11 commitments and other expenses are excluded.

The separate implementer report gives **87 percent**, with a reported followup
sample of **484 households**. The income item's valid response count and exact
positive count are unknown. PDF physical pages 1/6/7/12 bind report month,
sample, study limitations and percentage. Exact followup window and household
payment linkage are unknown. There is no baseline/control or independent
third-party evaluation. The connection is **same_program_only**.

The packet contains minimal aggregate facts, raw URL/hash/bytes/retrieval
metadata, selectors/pages, attribution, extraction version and explicit unknowns.
No raw XML/PDF, names, contacts, household IDs, narratives or full text enter Git,
runtime or model context. The reviewed packet hash is its exact allowlist;
changed bytes are rejected even if a caller supplies their new hash. This is
not a general PII detector. IATI registry states cc-by-sa without verified
version; PDF raw redistribution is NOT_VERIFIED. Use minimal facts and links,
not raw redistribution or narrative reuse. Preserve the limited rights notice.

## Interface and output

`connect_published_program(packet_bytes: bytes, packet_source: Source) -> dict`
lives in `manager_core/public_program_disbursement.py`.

Require the actual existing Source type, exact source_id givedirectly-d003-aggregate-20261023, exact immutable packet URL, reviewed
packet SHA and bounded bytes (maximum 32768). Call Source.verify_content before
parsing. The separate root data/design commit supplies the URL/SHA to the task
brief, avoiding a self-referential packet hash. Use stdlib JSON and no network,
filesystem read, database, model, mutation or transport inside this function.

Return separate disbursements, beneficiary_aggregate and source_relation fields,
plus packet provenance, raw references, limited_rights, attribution, extraction,
unresolved_accounting and claim_limits. Compute the selected outgoing total from
the three reviewed rows. Fix proof_level=P0, action=NO_ACTION,
human_welfare_status=NOT_MEASURED, measurement_authentication=NOT_VERIFIED,
verified_income_increase_minor=None and verified_net_benefit_minor=None.
Do not allocate the expenditure total across 484 households or treat it as
donations received, income, net welfare, Manager revenue or verified settlement.

## Boundaries and acceptance

Only one module, its focused test and one existing CI test-list addition are
implemented. Root owns data/design/plan, evidence receipt, board, integration
and original registry acceptance. Keep program_funding.py and its strict
incoming/window contract unchanged; do not promote its unrelated dependencies.
No model/provider call, secrets, new dependency, scheduler, owner or article.

Tests must exercise the actual packet, known separate totals/sample/unknowns,
exact source relation and day precision; byte mismatch; a caller changing both
Source hash and packet to introduce altered amounts/foreign activity/private
keys; wrong raw URL used as packet provenance; wrong Source type; bounded input.
No fabricated successful response replaces the actual loader.

Independent fresh review checks spec, source quality, implementation quality and
original D003 acceptance. Normal exact-head CI and main integration are required.
Root then reads the published immutable packet, verifies bytes, synchronizes
source to the research registry branch and evaluates the original task. Passing
this task does not prove economic living improvement, authenticate bank payments,
or complete D004, Phase09, the entire Manager or the long-term mission.
