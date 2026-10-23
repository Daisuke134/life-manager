# Manager Public Opportunity Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect original D011's approved public OSS artifact and separately readable platform Paid facts without claiming verified income.

**Architecture:** Copy the reviewed D003 frozen SAFE snapshot loader shape using existing Source.verify_content plus an independent immutable pin. Preserve separate evidence and unknowns, leaving old four-stage contracts untouched.

**Tech Stack:** Python stdlib, existing Source, unittest, existing Manager CI.

**Spec:** `docs/superpowers/specs/2026-10-23-manager-public-opportunity-connection-design.md`.

## Global Constraints

- No UI, network/runtime/provider/model/payment effects, secrets, dependency, new production owner, article, outreach or application.
- Actual Source; source_id=jhipster-d011-aggregate-20261023; exact immutable SAFE packet URL; independent reviewed SHA; maximum32768 bytes; Source.verify_content before JSON.
- Public platform Paid10000 USDminor and DEBIT-10000 are separate from actualbank settlement, Manager income and net benefit. Artifact diff hash is adapter-derived by exact PR URL, not attested by payment provider.
- Prior posting/nominalaward/cost/labor/opportunitydenominator/received/net remain unknown. Labels13seconds aftermerge do not close priorposting. Existing OpportunityRecord/four-stage contracts remain unchanged.
- Output P0/NO_ACTION, income_status=NOT_VERIFIED, human_welfare_status=NOT_MEASURED, verifiedincomeincrease/netbenefit=None, chain_completeness=INCOMPLETE_PRIOR_POSTING_UNKNOWN.
- Only minimal attributed public facts/links and provenance; no raw code/API/HTML, author/payee/contact/privateinvoice/payout fields. This is one frozen snapshot, not generic PII/authentication or an ingestion/evaluation engine.
- Worker owns module+test+one focused CI module addition. Root owns data/design/plan/board/receipt/registry/integration. REVIEW cap3 rounds.

## Review Focus

- Caller-rehashed modified payment, wrong PR/expense or added personal data must not bypass the reviewed pin.
- SAFE packet provenance must not use raw upstream URLs with a projection hash.
- Public Paid, debit direction and the adapter-derived artifact hash must not become bank/income authentication.
- Unknown priorposting and costs must not become fullchain, nominalaward or netbenefit.
- This historical external example must not become Manager revenue or D012 acceptance.

---

### Task 1: Connect the reviewed public opportunity snapshot

**Files owned:** create `products/manager/manager_core/public_opportunity_payment.py`; create `products/manager/tests/test_public_opportunity_payment.py`; modify `.github/workflows/manager-phase06-service.yml` only to add that focused test module.

**Interfaces:** consume Source.verify_content and root's `products/manager/docs/research/JHIPSTER_D011_SOURCE_20261023.json` (URL/SHA/actualretrieval supplied after data commit). Produce `connect_published_opportunity(packet_bytes: bytes, packet_source: Source) -> dict` with fields/statuses in the design. Constants SOURCE_ID/SNAPSHOT_URL/SNAPSHOT_SHA256 may support callers. Read D003 sibling as precedent, no cross-worktree source writes or imports from its not-yet-merged module.

- [x] **Step1: Add real behavior tests before code.** Actual packet must yield exact PR34939↔expense346205 links, merged metadata, diffSHA vs GitSHA1 distinction, platformPAID10000USD/DEBIT-10000/time, priorpostingUNKNOWN and nominalNone, no provider hashattestation, nullcosts/income/net and fixed statuses. Rehashed wrong amount/expense/link/status/privatekey must be rejected; rawURL/wrongSourceid/type/oversized/nonbytes rejected. Missing callable must fail assertions rather than import collection.
- [x] **Step2: Run and save actual RED.** `PYTHONPATH=products/manager:products/manager/tests python3 -m unittest test_public_opportunity_payment -v` before production code.
- [x] **Step3: Implement only the pure reviewed-snapshot adapter.** Reuse Source and D003 shape; no old module promotion, money helper, scraper, new state or action.
- [x] **Step4: Add the one focused CI module name.** Preserve publisher/planner/cadence/permissions and every existing module name; root resolves any concurrent main update.
- [x] **Step5: Run focused GREEN, full Manager suite once, import boundary and diffcheck.** Full: `PYTHONPATH=products/manager python3 -m unittest discover -s products/manager/tests -q`; report all skips/failures. Preserve known canonical-path sourceguard FAIL.
- [x] **Step6: Self-review and commit only owned3files.** Private report records real RED/GREEN/logs/commands/concerns; no push, registry or originalacceptance by worker. Root reviews and normally integrates.
