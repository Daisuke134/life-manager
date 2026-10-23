# G001/G002 bounded source-design acceptance — root receipt

**Disposition: BOUNDED_SOURCE_DESIGN_ACCEPTED.** Root accepted the two original finite source/offline DESIGN tasks only after independent review, actual source application and dependency confirmation. Operational charter adoption remains **UNADOPTED**; actual external audit remains **NOT_PERFORMED**. No role, staffed URL, real population reconciliation, intervention result or human benefit is established.

## Actual root event

- Pre-application source: `72ec5a9953e71aeb3b3692129b3c7706c35d32f7`. Reviewed patch SHA256 `9e69f45cedbb59d134453dc7df93f4286729bdc1da2088b44d86a8d4871e7e1d` was applied and all13 payload bytes matched before actual-event display updates.
- Actual G001 acceptance UTC: `2026-10-23T19:35:43.544820+00:00`, after actual K007 and V001 done. Actual G002 acceptance UTC: `2026-10-23T19:35:43.544834+00:00`, after G001. The original dependency chain is preserved.
- Actor: Codex root AI technical/design reviewer within the owner's standing development authorization. This is not a human operational, legal/ethics, consent or external-audit signature.
- V001 actual finite-design source `647589c1d152b5d5fc42e4800e046256210ad07e`, actual event `2026-10-23T19:25:39.926533+00:00`, [receipt](V001_PURPOSE_SPECIFIC_DESIGN_ACCEPTANCE_20261023.md) SHA256 `df34d545ba0d8018626670e8fb3970a75828efcd6896c2f9308594e2cca98e25` remain unchanged.
- Final independent whole review: 0 findings / 0 blocking, SPEC/QUALITY/INTEGRATION PASS, report SHA256 `d5def4ac90dc940b179313a10b583a57bdf023a993df839a9e3c57b4da97f175`. Actual application/dependency/protected-source proof SHA256 `bbf9deb70c24cb7372f97df5278b4831c491c2ad8912f58405c017d034a98886`.
- Actual registry: 113 IDs =83 done /20 todo /10 skipped; only G001/G002 changed from the prior accepted registry, other111 rows unchanged. The exact target is bounded source DESIGN; actual operating conditions below remain unresolved.
- Source-boundary guard retains actual FAIL/exit2 for the absent canonical host, distinct from existing explicit authorized cloud worktree use. No false PASS, new runtime authority, actual external audit or model execution is asserted.
- No final own commit hash is preclaimed. Commit/push/ref readback are separate root integration evidence; this is not main/production promotion.

This receipt records the source-design decisions for the existing registry. It is not a second task authority or an operational-adoption record.

## Original requirements and bounded evidence

| Task / unchanged original requirement | Technical design evidence and limit |
|---|---|
| G001 depends K007, V001; learn デジタル・ブッダという比喩と公的権限の違い | [charter](../governance/PUBLIC_INTEREST_CHARTER_DRAFT.md) §§1–3 separates aspiration/public office, authentic owner grant, scope/budget/expiry/revocation and independent roles. K007 remains existing done; V001 actual receipt must be accepted first. No public authority or person appointment is supplied. |
| G001 change 公共利益憲章、権限・異議申し立て・停止条件を制定 | Charter §§4/6/7 and [procedure](../governance/INCIDENT_APPEAL_AND_AUDIT_PROCEDURE.md) define stop, appeal, review and recovery. Source adoption establishes these finite design rules only; actual operator/roles/monitored URLs/funding/custody remain pending operational conditions. |
| G001 verify 管理者が監査・停止でき、AIが自分の権限を変更できない | [governance.py](../../manager_core/governance.py) reuses [authority.py](../../manager_core/authority.py); [governance tests](../../tests/test_governance.py) cover scope/issuer/domain/action/target/budget/validity rejection, stop/unknown/OOD and always can_execute=False. Existing [K007 evidence](PHASE05_FINAL_OFFLINE_KERNEL_EVIDENCE_JA.md) and [E16 STOP/resume/readback proof](E16_DEPLOYED_ACCEPTANCE_20261023.md) support the bounded mechanism. E16 is prior real technical evidence, not new access verification or a new model-controlled grant. |
| G002 depends G001; learn 介入による害を監査する仕組み; change 第三者監査と事故報告プロセスを設計する | Procedure §§1–7 preserves intake, triage, custody/retention, independent appeals/audits, scope/period/sample/omissions/conflicts, correction and recovery. The first future 90-day operational audit and optional human study are not prerequisites for source-process design. Actual audit remains NOT_PERFORMED. |
| G002 verify 無効・悪化・未知のすべての介入の監査証拠が保全される | Existing AuditTrail retains distinct INEFFECTIVE/WORSENED/UNKNOWN plus HARM/APPEAL/RESOLVED. Commit 3bada adds finite declared-population ID/trace reconciliation and meaningful omission/extra/missing/corrupt-chain/restart tests. This accepts a finite source design for preserving and detecting gaps; it does not assert all actual interventions have been populated, classified or independently audited. |

The original section, depends, learn, change, verify and external fields remain exact. Only status, implementation_status, appended implementation_evidence and explicit source_acceptance_scope differ for G001/G002; the other 111 rows remain byte-equivalent as JSON objects against the actual V001 source baseline 647589c1d152b5d5fc42e4800e046256210ad07e. No V002/V003, D/U or G003+ acceptance is included.

## Technical implementation, verification and provenance

The actual source implementation is `3bada454efaff896c4a425c8e3f362708e13e77b` (`fix(manager): reconcile declared incident run population`), based on `420b24626d325c8d32f969e6ea1c08c56fdb1f6b`. It changes only governance.py and test_governance.py, +144/-10. Source SHA-256 is `c94a576e444f764f3f8e690ee0df9bbb2cf0fcc57b5219bab8fc3aa88e54b69f`; test SHA-256 is `46f9c5e22887dec57b620a3359d2a392738b4ab842eb06ba01c601756fa0e8b9`.

The existing implementation report records API-absence RED (19 tests / 12 error records), focused GREEN 19 tests, and exactly one full Manager run: `python -m unittest discover -s tests -q`, **1088 tests, skipped=5, failures=0/errors=0**, exit0. Independent Task 1 source review: **0 findings / SPEC PASS / QUALITY PASS**. The five-document preparation has its own independent **0 findings / SPEC PASS / QUALITY PASS** review. These are previous actual executions and reviews; this integration did not rerun tests, guard, CI or ML. The canonical-host source-boundary guard's recorded FAIL/exit2 remains FAIL, not a borrowed PASS. Root's authorized cloud source work and final integration checks are separate facts.

Private evidence names and exact SHA-256 values (review provenance only; private artifacts are not published/source dependencies):

```text
645e81e5c934cc96e2da5134f31ef599b111e36772d1fc2f303f475b3ce3e9ad  governance-design-gate-applicability.md
b00f569fc066d4f87c36d9665bfa679492302f52d966ceea17a4dd8010d8f6b8  governance-population-sdd/spec-and-plan.md
ea29ffaa4cd365ee4b28b458872b8bcf83de4b5e7cbf20df3f122fa7d2426900  governance-population-sdd/task-1-report.md
21d6abb8ae345bcb20ea370a68766df0df415d509e433310829d2e000ff6b5b3  governance-population-sdd/task-1-review.md
a70993348013de535598b26e32cb94b6257ecd343cf062dce7e9863ba584a5c3  governance-population-sdd/task-1-green.log
72c601d78a30d12daf1c418c82630f3d30dbcf7841efecb650a8e07dafaf75cf  governance-population-sdd/task-1-full-manager.log
45a14b7c9b319561b552899304960d120b1c1076da7187de6e07563ed9854d45  governance-design-docs-sdd/task-1-report.md
7295f355c792b45576f6139341f0247ed77b3cbb754b0ffea077d93af67c127b  governance-design-docs-sdd/task-1-review.md
6c5bda82fbaa8265c5b1adb6b7656004745710dccbcffe40cae8a7da38926b99  governance-design-docs-sdd/source-adoption.patch
```

The earlier docs review applies to the five-file PREPARED proposal, patch hash above. The final adoption amendment and integrated views completed the independent R1 whole review recorded in the Actual root event section (0 findings; SPEC/QUALITY/INTEGRATION PASS). The subsequent R2 actual-event delta review found one blocking current-state propagation inconsistency (SPEC PASS; QUALITY/INTEGRATION BLOCK). R3 reviewed the bounded wording/checksum fix and closed that finding: 0 findings / 0 blocking, SPEC/QUALITY/INTEGRATION PASS, report SHA256 `2b8dfac8c0c189bdcdecc92007b4f6ccfd1bee14fccbfc070773f56eea789219`. The recorded source-design acceptance events remain actual; the final limited integration review is complete. This result record creates no new operational adoption or human approval. No own commit/hash is preclaimed. Draft historical hashes remain comments in the [existing manifest](../governance/GOVERNANCE_DRAFTS_20261022.sha256); active entries bind the current amended source-design bytes.

## Population and authority limits retained

`incident_inventory(audit, run_ids, *, population_run_ids=None)` returns `population_reconciled=None` when no population is supplied; otherwise False for missing declared IDs, unexpected requested IDs, missing selected traces or invalid chains, and True only for equality of declared/requested finite IDs with valid nonempty selected traces. An explicit empty declaration/selection is a bounded vacuous equality, not all-world zero. Existing positional calls remain valid. Counts/events cover actual retained requested-run evaluation events only; missing runs do not become zero or enter the count silently. UNKNOWN evidence remains None, beneficiary outcome NOT_MEASURED, proof P0 and audit NOT_PERFORMED; counts are not persons or authenticated intervention totals.

Set equality/valid chains do not authenticate the independent population, source classification, all receipt/readback requirements, custody or full-world completeness. A DB controller can replace a local hash chain. A real operating reconciliation must independently obtain execution/outbox scope, source period, immutable revision and source-snapshot SHA-256; include every owned effect regardless of status, separate rollback records, NO_ACTION/refusal/pre-execution failure run/decision records, and map run/occurrence→effect/attempt→receipt/readback→evaluation/incident→correction. Preserve UNKNOWN/GAP for unavailable/unrecorded inputs and missing classification/evidence. Never derive the population from incident selection or pending-only outbox records. No automatic full-runtime ingestion or actual population run is claimed.

## Historical operating gaps remain unresolved

The earlier PHASE G001 row required “実責任者の採択と停止/異議手続の運用”; G002 required “実担当・独立監査・保存/訂正/復旧の運用”. The engineering G001–G002 remaining condition was “採択された統治、実際の oversight/appeal 運用、独立監査”. These are retained as actual operational-adoption/operation conditions, not erased or certified by finite design acceptance. Charter §7 still requires an actual accountable operator, authentic grant, exact version/hash/scope/budgets, stop/revocation owner, functioning staffed appeal/audit URLs, assigned roles/conflicts and retention/review commitments. No such actual adoption is recorded. Existing authority/STOP/recovery channels and V001 limited scope, frozen protocols/rights/receipts remain unchanged.
