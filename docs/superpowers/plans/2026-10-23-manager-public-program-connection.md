# Manager Public Program Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the reviewed public outgoing expenditures and separate beneficiary report for original D003 while retaining unmeasured economic improvement.

**Architecture:** Reuse Source.verify_content and the existing pinned-artifact loader pattern. Load only one immutable reviewed aggregate snapshot; keep disbursement, report and relation separate. No generic ingestion engine or incoming-ledger changes.

**Tech Stack:** Python stdlib, existing Source, unittest, existing Manager CI.

**Spec:** `docs/superpowers/specs/2026-10-23-manager-public-program-connection-design.md`.

## Global Constraints

- No UI, model/provider/network/runtime effects, secrets, dependencies, scheduler, new production owner, article, payment or source/registry mutation by worker.
- Only the reviewed aggregate packet is accepted; caller-controlled replacement hash must not admit altered data. Source must point to the packet's exact immutable URL, not an upstream raw URL.
- Maximum input32768 bytes. Reuse actual Source.verify_content, stdlib JSON and the pinned-artifact shape. No generic schema/PII engine or unrelated funding/outcome imports.
- Selected outgoing total290390000 USD minor is separate from reported87percent and followup sample484 households. Income-item valid denominator/positive count/window remain unknown.
- same_program_only, partial coverage, day precision, implementer report, third_party_evaluation=false, unknown costs/refunds/displacement and limited rights remain explicit.
- Output proof_level=P0, action=NO_ACTION, human_welfare_status=NOT_MEASURED, measurement_authentication=NOT_VERIFIED, verified_income_increase_minor=None, verified_net_benefit_minor=None.
- Preserve existing incoming/window semantics and all other source. Root owns data, design, plans, board, evidence and task acceptance; REVIEW.md cap is3 rounds.

## Review Focus

- A caller changing both packet bytes and Source hash cannot bypass the independent reviewed snapshot pin.
- Packet provenance cannot claim upstream raw bytes are the nonpersonal projection.
- Rounded87percent and sample484 do not become an exact respondent count, per-household allocation or causal benefit.
- Outgoing type4 expenditure cannot become incoming donations or authenticated settlement.
- Source-only acceptance cannot claim runtime inference, new intervention or original downstream task completion.

---

### Task 1: Load and connect one reviewed public aggregate snapshot

**Files owned:**
- Create `products/manager/manager_core/public_program_disbursement.py`
- Create `products/manager/tests/test_public_program_disbursement.py`
- Modify `.github/workflows/manager-phase06-service.yml` only by adding the focused test module.

**Interfaces:**
- Consume actual `manager_core.models.source.Source` and its `verify_content(payload)`.
- Consume root-owned `docs/research/GIVEDIRECTLY_D003_SOURCE_20261023.json` under products/manager; immutable URL and SHA supplied in brief after root's data commit.
- Produce `connect_published_program(packet_bytes: bytes, packet_source: Source) -> dict` with the separate fields and fixed non-authority status in the design. Snapshot constants may be exported for callers/tests; no other execution interface.
- Follow `evidence.load_verified_trial`'s independent artifact pin; do not call its Ampersand-specific parser or import unrelated research modules.

- [ ] **Step 1: Write meaningful failing tests before production code.** Assert callable availability (not an import-only failure), then actual reviewed packet output: total290390000, currencyUSD, three outgoing rows, report87/sample484, unknown item count/window, same_program_only, direct report link, distinct raw hashes, dates/dayprecision, preserved rights and fixed P0/NO_ACTION/NOT_MEASURED/None. Test altered bytes against original Source; rehashed tampered packet (amount, foreign activity, added contact/raw body) still rejected by reviewed pin; wrong upstream raw URL, wrong Source type and oversized bytes rejected. Keep each actual behavior observable.
- [ ] **Step 2: Run focused module and retain actual RED before adding implementation.** `PYTHONPATH=products/manager:products/manager/tests python3 -m unittest test_public_program_disbursement -v`; failures must identify missing callable or behavior, not typos.
- [ ] **Step 3: Implement the small pure loader using Source and reviewed independent pin.** Preserve separate categories and unknowns; no generic pipeline, model, raw file parser, live action or new dependency.
- [ ] **Step 4: Add the focused test module to the existing CI verify list only.** Do not alter publisher, cadence, permissions or call paths.
- [ ] **Step 5: Run focused tests, full391-test baseline plus new tests once, Manager import boundary and diffcheck.** Full command `PYTHONPATH=products/manager python3 -m unittest discover -s products/manager/tests -q`. Retain all errors/skips accurately in private logs; source guard's known canonical-path failure stays a failure.
- [ ] **Step 6: Self-review and commit only the three owned files.** Write private report with RED/GREEN, commands, actual results and concerns; root reviews/integrates and evaluates original D003 separately.
