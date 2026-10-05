# .si Domain Flip Product Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and activate a bounded Life Manager loop that researches original .si brand names, registers at most one per pass, lists verified holdings for sale, and records sale proceeds only after settlement, transfer, payout, and all costs are proven.

**Architecture:** One financial money owner runs a finite daily pass with a private append-only ledger. The pure policy module decides budget, rights-evidence, replay, and net conditions; Openprovider and Sedo adapters perform provider calls and official readbacks; the existing shared agent runner proposes and evaluates names from evidence. The CFO consumes the same provider receipts and measured costs.

**Tech Stack:** Python 3.14, stdlib `urllib`, `xml.etree`, `decimal`, and JSONL; existing `runtime/agent-runner`; repository `lm-loop` and CFO contracts.

**Spec:** `docs/superpowers/specs/2026-10-05-domain-flip-loop-design.md`

## Global Constraints

- Product Loop ID is `domain-flip`; it is a separate financial money owner and never uses `agent-economy-loop`'s Base-USDC treasury.
- The initial owner-funded cap is 100 EUR equivalent total, with no automatic refill or repeat charge; one registration per pass and four active holdings maximum.
- The registrar request sets `autorenew` to `off`; each renewal is a fresh bounded decision with its cost reserved.
- A purchase requires a fresh registrar availability and price readback, rights review with source references, a legal registrant whose publication conditions are known, sufficient dedicated balance, and a positive conditional net at the minimum accepted Sedo price after measured fees and reserved costs.
- Conditional net is not a sale-probability or expected-profit estimate. Listings, offers, and acquisition costs are never revenue.
- State lives outside the immutable release at `~/.local/state/life-manager/domain-flip`; events include `run_id`, `owner_id`, `occurrence_id`, `release_sha`, loaded argv/env, phase, command, exit code, effect, readback, provider receipt, evidence refs, error class, retryability, and next action.
- An uncertain registration or listing effect fences the same candidate until provider readback resolves it; no blind replay is allowed.
- Realized revenue requires buyer settlement, registered-holder transfer, seller payout, receiving-account readback, and cost-complete positive net. Sale and payout IDs are deduplicated.
- Credentials stay in `~/.local/share/anicca/credentials.json`; no token, password, or private registrant fields enter source, events, logs, or chat.
- Do not modify `config/loop-registry.json`, the product-loop catalog, or CFO files while the active CFO lease owns them. Integrate those files after its lease is released and re-read their current source.

## Review Focus

- A quote is in a different currency or lacks a fresh FX/final-charge amount: block acquisition; test the currency mismatch.
- Registration timed out after request dispatch: mark `effect_unknown`, fence that domain, and issue no second registration; test the replay fence.
- Sedo accepts `DomainInsert` but later fails its checks: remain `sale-pending` or `listing-pending` until `DomainStatus`/`DomainList` confirms; test delayed listing.
- An offer, pending buyer payment, or payout notification lacks bank/holder readback: record no revenue; test each incomplete sale boundary.
- The same sale, payout, or provider event arrives twice: retain one economic entry; test idempotent receipt identity.

---

### Task 1: Deterministic purchase, event, and realized-net policy

**Files:**
- Create: `skills/domain-flip/core.py`
- Create: `skills/domain-flip/test_core.py`

**Interfaces:**
- Produces: `evaluate_purchase(candidate, quote, funding, portfolio, evidence) -> dict`, `advance_phase(current, event) -> str`, and `realized_sale(receipts, costs) -> dict`.
- `evaluate_purchase` returns `eligible`, stable `reason_codes`, `conditional_net_eur`, and `maximum_loss_eur`; it never calls a provider or model.
- `realized_sale` returns a revenue amount only when buyer settlement, holder transfer, seller payout, receiving-account readback, and all required costs are present and receipt IDs are unique.

- [ ] **Step 1: Write failing tests** named `test_purchase_obeys_total_cap_and_one_per_pass`, `test_purchase_requires_known_public_registrant_and_rights_evidence`, `test_currency_mismatch_blocks_purchase`, `test_effect_unknown_fences_same_domain`, `test_pending_offer_is_not_revenue`, `test_sale_requires_settlement_transfer_and_payout`, and `test_duplicate_sale_or_payout_receipt_is_counted_once`. Assert the 100 EUR cap, four-holding limit, `autorenew=off` policy value, and exact Decimal net arithmetic.
- [ ] **Step 2: Run the test file and confirm the expected missing-module failures.** Run: `python3 -m pytest skills/domain-flip/test_core.py -q`. Expected: collection fails because `skills/domain-flip/core.py` does not yet exist.
- [ ] **Step 3: Implement the three pure functions** with `Decimal`, explicit required evidence, stable reason codes, and no float arithmetic or hidden provider state.
- [ ] **Step 4: Run the focused tests.** Run: `python3 -m pytest skills/domain-flip/test_core.py -q`. Expected: all named tests pass.
- [ ] **Step 5: Commit** `feat(domain-flip): add bounded purchase policy`.

### Task 2: Openprovider read, quote, registration, and ownership readback

**Files:**
- Create: `skills/domain-flip/openprovider.py`
- Create: `skills/domain-flip/test_openprovider.py`

**Interfaces:**
- Consumes: Task 1 purchase result.
- Produces: `OpenProviderClient.check_domain(name)`, `quote_create(name)`, `register(name, owner_handle, idempotency_key)`, `get_domain(domain_id)`, and `list_domains()`.
- The live client uses the official bearer-token API and the credential SSOT. Its base URL is fixed to Openprovider production or its documented sandbox; tests use a local HTTP server.
- Registration sends one-year `.si`, `autorenew="off"`, and the approved owner contact; it never turns private-WHOIS on or retries a timed-out create.

- [ ] **Step 1: Write failing local-server tests** named `test_check_and_quote_use_official_si_fields`, `test_register_sends_owner_and_autorenew_off`, `test_missing_credentials_prevent_mutation`, `test_nonzero_provider_code_is_not_success`, and `test_timeout_is_effect_unknown_without_retry`. Assert method/path/body, `code == 0`, returned domain ID, and no second create request.
- [ ] **Step 2: Run the test file and confirm the expected missing-module failure.** Run: `python3 -m pytest skills/domain-flip/test_openprovider.py -q`. Expected: collection fails because the client is absent.
- [ ] **Step 3: Implement the stdlib REST client** for `/v1/auth/login`, `/v1/domains/check`, `/v1/domains/prices`, `/v1/domains`, `/v1/domains/{id}`, and `GET /v1/domains`; validate responses and redact credentials from errors.
- [ ] **Step 4: Run the focused tests.** Run: `python3 -m pytest skills/domain-flip/test_openprovider.py -q`. Expected: all named local-server tests pass.
- [ ] **Step 5: Commit** `feat(domain-flip): add Openprovider adapter`.

### Task 3: Sedo listing and official listing readback

**Files:**
- Create: `skills/domain-flip/sedo.py`
- Create: `skills/domain-flip/test_sedo.py`

**Interfaces:**
- Consumes: Task 1 policy and Task 2 registered-domain readback.
- Produces: `SedoClient.insert_for_sale(domain, price_eur, min_price_eur)`, `domain_status(domain)`, and `domain_list(domains)`.
- The adapter submits documented POST form requests and parses XML with the stdlib. `DomainInsert` returning `Ok` is only submission; `listed` requires a later official `DomainStatus` or `DomainList` match.
- Sedo's listing API does not prove buyer settlement or seller payout; those receipts remain separate events.

- [ ] **Step 1: Write failing tests** named `test_insert_uses_post_and_eur_price`, `test_ok_submission_does_not_mark_listed`, `test_domain_status_confirms_exact_price`, `test_domain_not_in_sedo_is_not_listed`, and `test_sedo_fault_stays_unverified`. Use fixture XML based on the official API response examples.
- [ ] **Step 2: Run the test file and confirm the expected missing-module failure.** Run: `python3 -m pytest skills/domain-flip/test_sedo.py -q`. Expected: collection fails because the adapter is absent.
- [ ] **Step 3: Implement the minimal form/XML adapter** for `DomainInsert`, `DomainStatus`, and `DomainList`; read API credentials only from the credential SSOT and never log them.
- [ ] **Step 4: Run the focused tests.** Run: `python3 -m pytest skills/domain-flip/test_sedo.py -q`. Expected: all named tests pass.
- [ ] **Step 5: Commit** `feat(domain-flip): add Sedo listing adapter`.

### Task 4: Finite owner pass and effect reconciliation

**Files:**
- Create: `skills/domain-flip/run.py`
- Create: `skills/domain-flip/effect_reconcile.py`
- Create: `skills/domain-flip/rights_search.py`
- Create: `skills/domain-flip/candidate-review.schema.json`
- Create: `skills/domain-flip/test_run.py`
- Create: `skills/domain-flip/test_rights_search.py`

**Interfaces:**
- Consumes: Tasks 1–3; existing `runtime/agent-runner/agent_runner.py` with `--task-class diagnostic-agent --prompt-stdin --schema ... --read-only`.
- Produces: one daily pass for owner `domain-flip`, with candidate packet, model result, domain-level event stream, and exact registrar/Sedo readbacks.
- The owner exposes `append_event(state_dir, event)`; it validates and durably appends all required occurrence fields before any owner-visible transition.
- `rights_search.py` queries the WIPO Global Brand Database API and the official EUIPO Trademark Search API (`GET https://api.euipo.europa.eu/trademark-search/trademarks`) for exact/close word marks; a failed or unavailable search is `rights_evidence_missing`, never a clean result. EUIPO query uses the documented `wordMarkSpecification.verbalElement` field. The adapter also attaches the official Register.si ADR search reference.
- The owner generates original, era-inspired names; sends market, official rights-search, registrar, and sale evidence to the model; and accepts only schema-valid recommendations whose source refs are present. Model prose cannot bypass deterministic cap, rights-evidence, or economic checks.
- `effect_reconcile.py --occurrence-id ...` performs provider GET readbacks only and either records a conclusive effect result or keeps the occurrence fenced.

- [ ] **Step 1: Write failing tests** named `test_wipo_and_euipo_queries_are_candidate_specific`, `test_failed_rights_search_is_not_clean`, `test_event_writer_records_required_occurrence_fields`, `test_pass_is_scout_only_without_provider_credentials`, `test_model_choice_cannot_bypass_purchase_policy`, `test_domain_insert_requires_registered_owner_readback`, `test_lost_registration_response_is_not_replayed`, `test_sedo_listing_is_pending_until_provider_readback`, and `test_reconcile_uses_get_only_and_holds_ambiguous_state`.
- [ ] **Step 2: Run the owner tests and confirm the expected missing-module failure.** Run: `python3 -m pytest skills/domain-flip/test_run.py -q`. Expected: collection fails because the owner entrypoint is absent.
- [ ] **Step 3: Implement the one-pass owner and read-only reconciler** using the private state root, validated append-only event writer, `effect_unknown` fencing, and the existing agent runner.
- [ ] **Step 4: Run focused tests and syntax checks.** Run: `python3 -m pytest skills/domain-flip/test_run.py -q` and `python3 -m py_compile skills/domain-flip/*.py`. Expected: all tests pass and compilation exits 0.
- [ ] **Step 5: Commit** `feat(domain-flip): add finite owner pass`.

### Task 5: CFO attribution, canonical loop contract, and SSOT cursor

**Files:**
- Create: `skills/cfo/adapters/domain_flip.py`
- Create: `skills/cfo/test_domain_flip_adapter.py`
- Modify: `skills/cfo/loop_pnl.py`
- Modify: `apps/life-manager/config/product-loop-catalog.json`
- Modify: `config/loop-registry.json`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` §99

**Interfaces:**
- Consumes: Task 4's append-only domain events and Task 1's sale/cost receipt contract.
- Produces: one `domain-flip` Product Loop mapped to the financial owner job; B0 records only settled sale revenue, refunds, and measured domain-flip costs with official receipt IDs.
- Update shared files only after the active CFO lease is released; re-read its merged `origin/main` code and use its then-current adapter order and schema.

- [ ] **Step 1: Write failing adapter tests** named `test_only_settled_paid_transferred_sales_become_revenue`, `test_registration_and_renewal_are_costs_not_revenue`, `test_pending_sale_or_listing_is_not_revenue`, `test_duplicate_sale_receipt_is_deduplicated`, and `test_missing_payout_readback_is_a_coverage_gap`.
- [ ] **Step 2: Run the adapter tests and confirm the expected missing-module failure.** Run: `python3 -m pytest skills/cfo/test_domain_flip_adapter.py -q`. Expected: collection fails because the adapter is absent.
- [ ] **Step 3: Implement the domain-flip receipt adapter and wire the loop catalog, registry, and SSOT.** Keep existing production TODO order intact and record the direct user authorization, initial cap, current worktree/cursor, and the active-lease sequencing ruling in §99.
- [ ] **Step 4: Run focused CFO and loop contract checks.** Run: `python3 -m pytest skills/cfo/test_domain_flip_adapter.py skills/cfo/test_economic_attribution.py skills/cfo/test_loop_pnl.py -q` and `./bin/lm-loop-contract`. Expected: focused tests pass and loop contract returns `ok=true` with 15 product loops and no errors.
- [ ] **Step 5: Commit** `feat(domain-flip): register CFO loop ownership`.

### Task 6: Sandbox proof, live readiness, immutable release, and natural pass

**Files:**
- Modify only task-owned files if a contract defect is found; otherwise use the canonical runtime and private credential/state stores.

**Interfaces:**
- Consumes: Task 5 accepted main branch and the normal Life Manager immutable-release/apply path.
- Produces: sandbox registrar/Sedo proofs, one natural `domain-flip` occurrence, official listing/ownership readbacks, and a cost-complete payout ledger when a buyer closes.

- [ ] **Step 1: Provision or reuse sandbox access** and run the documented Openprovider sandbox checks for domain check, price, create with autorenew off, and official owner/expiry readback. Expected: sandbox credential is in the credential SSOT, receipt IDs match the domain, and no production charge or registry create occurs.
- [ ] **Step 2: Verify payout and registrant readiness** from existing owner-owned account data: exact legal registrant, current .si WHOIS fields, a receiving-tested functional public email alias with no personal data, Sedo payout account, and receiving-account readback. Expected: private legal registrant fields stay in credential SSOT/provider account data; WHOIS exposes only the intended functional email for a natural-person holder.
- [ ] **Step 3: Run a fresh-context read-only audit** of the exact candidate, rights evidence, public registrant fields, provider quote, payout destination, funding amount, and remaining cap. Expected: the audit returns no unresolved critical or important risk; it does not authorize or perform any external effect.
- [ ] **Step 4: Create or reuse registrar, Sedo, WIPO, and EUIPO API access** with the existing credential SSOT, enable only required API/registry access, fund no more than the initial 100 EUR equivalent once, and verify account/balance/auto-refill state. Expected: every new credential is saved to the SSOT, final charge is within cap, auto-refill is off, and official account readback matches.
- [ ] **Step 5: Run one natural pass** through the admitted immutable release and confirm loaded SHA/argv/env, owner occurrence, registrar availability/quote, the deterministic acquisition decision, and Sedo listing status. Expected: zero purchase when any identity, rights, quote, evidence, budget, or readback gate is missing; otherwise at most one registration and one verified listing.
- [ ] **Step 6: Continue scheduled natural passes** without duplicate effects until an actual Sedo sale completes buyer settlement, registered-holder transfer, payout, receiving-account credit, all-cost CFO attribution, and replay-zero. Expected: only then report positive realized net; keep the persistent goal active until this is true.

## Source references

- Openprovider official getting-started guide and REST schema: `https://developer.openprovider.com/get-started.html`, `https://developer.openprovider.com/data/swagger.json`
- Sedo official Basic API: `https://api.sedo.com/apidocs/v1/Basic/`
- Register.si official rules and WHOIS §13: `https://www.register.si/splosni-pogoji/`
- WIPO Global Brand Database API: `https://developers.branddb.wipo.int/`
- EUIPO Trademark Search API: `https://dev.euipo.europa.eu/product/trademark-search_110/api/trademark-search`
- Register.si ADR procedure: `https://www.register.si/en/adr-procedure-guidelines/`
- Sedo .si fees and payout/transfer contract: `https://sedo.com/us/what-we-offer/price-list/`, `https://sedo.com/us/services/domain-transfer-service/`
- Current reported .si sale evidence and liquidity caveat: `https://www.dynadot.com/blog/why-si-domains-are-gaining-attention`
