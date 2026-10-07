# .si Domain Flip Product Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and activate a bounded Life Manager loop that researches original .si brand names, registers at most one per pass, lists verified holdings for sale, and records sale proceeds only after settlement, transfer, payout, and all costs are proven.

**Architecture:** One financial money owner runs a finite daily pass with a private append-only ledger. The pure policy module decides budget, rights-evidence, replay, and net conditions; Openprovider and Sedo adapters perform provider calls and official readbacks; the CFO consumes the same provider receipts and measured costs. A paid model review does not run without a proven zero marginal cost or a pre-reserved amount within the USD 4.99 cap.

**Tech Stack:** Python 3.14, stdlib `urllib`, `xml.etree`, `decimal`, and JSONL; existing `runtime/agent-runner`; repository `lm-loop` and CFO contracts.

**Spec:** `docs/superpowers/specs/2026-10-05-domain-flip-loop-design.md`

## Global Constraints

- Product Loop ID is `domain-flip`; it is a separate financial money owner and never uses `agent-economy-loop`'s Base-USDC treasury.
- Total domain-flip outlay is capped at USD 4.99 across registration, renewal reserve, taxes, provider/payment/FX fees, and measured model/infra costs. EUR costs require a verified USD-per-EUR basis tied to the dedicated funding receipt; cumulative reservations are stored in both EUR and USD.
- Spend may use only a verified, already allocated `domain-flip` business balance; no personal wallet, bank account, Upwork card, credit, automatic refill, or repeat charge is used. If the dedicated balance is absent, the loop remains scout-only.
- Acquisition requires an official dedicated-balance readback and provider receipt no older than 24 hours, tied to the original funding receipt and limited by the USD 4.99 lifetime cap.
- Sedo's public fee page is re-read each pass; the owner uses the highest applicable route rate and the current TLD minimum-sale price. Measured model/infra and other cost receipts use a separate readback snapshot no older than 24 hours.
- Each pre-registration dispatch event reserves its maximum loss, including renewal reserve and current measured costs. Pending/unknown registration holds its reservation; missing historical reservation evidence blocks further purchase.
- The lifetime funding cap reserves all fixed cost inputs used by conditional-net arithmetic, including tax, payout, and FX amounts; an absent, stale, or changed contact readback keeps acquisition scout-only.
- The registrar request sets `autorenew` to `off`; each renewal is a fresh bounded decision with its cost reserved.
- A purchase requires a fresh registrar availability and price readback, rights review with source references, a verified natural-person registrant whose approved public WHOIS fields are exactly email with no optional fields opted in, a verified business-owned dedicated balance, sufficient funds, and a positive conditional net at the minimum accepted Sedo price after measured fees and reserved costs.
- Only EUR registrar quotes are eligible. A foreign-currency quote remains scout-only until its charge and USD-cap conversion share one receipt-verifiable rate path.
- Conditional net is not a sale-probability or expected-profit estimate. Listings, offers, and acquisition costs are never revenue.
- The default paid candidate reviewer is disabled because no USD lifetime-cost reservation or fresh per-call cost readback exists. Missing a verified zero-marginal-cost basis or bounded reservation keeps the candidate `scout_only`.
- State lives outside the immutable release at `~/.local/state/life-manager/domain-flip`; events include `run_id`, `owner_id`, `occurrence_id`, `release_sha`, loaded argv/env, phase, command, exit code, effect, readback, provider receipt, evidence refs, error class, retryability, and next action.
- An uncertain registration or listing effect fences the same candidate until provider readback resolves it; no blind replay is allowed.
- The registration-dispatch event reserves `maximum_loss_usd` using the funding-receipt FX basis. A missing or mismatched basis, or cumulative spend/reservations above USD 4.99, blocks purchase.
- Realized revenue requires buyer settlement, registered-holder transfer, seller payout, receiving-account readback, and cost-complete positive net. Sale and payout IDs are deduplicated.
- Credentials stay in `~/.local/share/anicca/credentials.json`; no token, password, or private registrant fields enter source, events, logs, or chat.
- Provider responses are whitelist-filtered before persistence; events keep only public domain/status/expiry fields and a one-way owner-handle fingerprint.
- Do not modify `config/loop-registry.json`, the product-loop catalog, or CFO files while the active CFO lease owns them. Integrate those files after its lease is released and re-read their current source.

## Review Focus

- A quote is in a different currency or lacks a fresh FX/final-charge amount: block acquisition; test the currency mismatch.
- Registration timed out after request dispatch: mark `effect_unknown`, fence that domain, and issue no second registration; test the replay fence.
- Sedo accepts `DomainInsert` but later fails its checks: remain `sale-pending` or `listing-pending` until `DomainStatus`/`DomainList` confirms; test delayed listing.
- An offer, pending buyer payment, or payout notification lacks bank/holder readback: record no revenue; test each incomplete sale boundary.
- The same sale, payout, or provider event arrives twice: retain one economic entry; test idempotent receipt identity.

### Prerequisite follow-up before Task 5: enforce the USD 4.99 total cap

**Files:** `skills/domain-flip/core.py`, `skills/domain-flip/run.py`, and their focused tests.

- [x] Replace the former EUR 100 cap with a strict USD 4.99 total cap. Derive conversion from the USD and EUR amounts on the same verified dedicated funding receipt.
- [x] Convert the full reserved maximum loss to USD with conservative cent rounding; persist and accumulate both EUR and USD reservation values before registration dispatch.
- [x] Prove missing/mismatched FX evidence, non-EUR quotes, missing historical reservations, and cumulative reservations above the cap block provider writes.
- [x] Update the spec and tests. Continue Task 5 only in files without another owner's active lease.

---

### Task 1: Deterministic purchase, event, and realized-net policy

**Files:**
- Create: `skills/domain-flip/core.py`
- Create: `skills/domain-flip/test_core.py`

**Interfaces:**
- Produces: `evaluate_purchase(candidate, quote, funding, portfolio, evidence) -> dict`, `advance_phase(current, event) -> str`, and `realized_sale(receipts, costs) -> dict`.
- `evaluate_purchase` returns `eligible`, stable `reason_codes`, `conditional_net_eur`, and EUR/USD maximum-loss reservations; it never calls a provider or model.
- A read-only price quote needs `readback_verified` and `evidence_refs`; `provider_receipt_id` is null when the provider does not issue one.
- `realized_sale` returns a revenue amount only when buyer settlement, holder transfer, seller payout, receiving-account readback, and all required costs are present and receipt IDs are unique.

- [x] **Step 1: Write failing tests** named `test_purchase_obeys_total_cap_and_one_per_pass`, `test_purchase_requires_known_public_registrant_and_rights_evidence`, `test_purchase_requires_quote_readback_evidence`, `test_purchase_requires_verified_business_balance_readback`, `test_prior_committed_loss_reserves_the_lifetime_cap`, `test_purchase_reserves_cumulative_spend_under_strict_usd_cap`, `test_funding_cap_must_remain_strictly_below_five_usd`, `test_purchase_respects_current_marketplace_minimum_sale_price`, `test_currency_mismatch_blocks_purchase`, `test_effect_unknown_fences_same_domain`, `test_pending_offer_is_not_revenue`, `test_sale_requires_settlement_transfer_and_payout`, and `test_duplicate_sale_or_payout_receipt_is_counted_once`. Assert receipt-backed business funding, cumulative USD 4.99 cap, four-holding limit, Sedo minimum sale price, `autorenew=off`, and exact Decimal arithmetic.
- [x] **Step 2: Run the test file and confirm the expected missing-module failures.** Run: `python3 -m pytest skills/domain-flip/test_core.py -q`. Expected: collection fails because `skills/domain-flip/core.py` does not yet exist.
- [x] **Step 3: Implement the three pure functions** with `Decimal`, explicit required evidence, stable reason codes, and no float arithmetic or hidden provider state.
- [x] **Step 4: Run the focused tests.** Run: `python3 -m pytest skills/domain-flip/test_core.py -q`. Expected: all named tests pass.
- [x] **Step 5: Commit** `feat(domain-flip): add bounded purchase policy`.

### Task 2: Openprovider read, quote, registration, and ownership readback

**Files:**
- Create: `skills/domain-flip/openprovider.py`
- Create: `skills/domain-flip/test_openprovider.py`

**Interfaces:**
- Consumes: Task 1 purchase result.
- Produces: `OpenProviderClient.check_domain(name)`, `quote_create(name, funding_fx_basis=None)`, `register(name, owner_handle, idempotency_key)`, `get_domain(domain_id)`, and `list_domains()`.
- Produces: `get_customer(handle)` via official `GET /v1/customers/{handle}?with_additional_data=0`; it returns only verified fingerprints and email-verification state, never raw contact fields.
- `get_domain` and `list_domains` return only whitelisted domain/status/expiry fields and a one-way fingerprint of the owner handle; they discard registrant names, emails, addresses, and phone fields even when the provider response includes them. Complete `list_domains` rows carry explicit official-readback metadata for receipt-loss reconciliation.
- `list_domains` fails closed if the provider's reported `total` exceeds the returned rows; a truncated page cannot prove that an owned domain is absent.
- The live client uses the official bearer-token API and the credential SSOT. Its production base URL is fixed; tests use a local HTTP server.
- Read-only price responses may not include a provider receipt ID; the owner persists only the verified, privacy-filtered quote and its evidence refs. The adapter never synthesizes a receipt.
- Registration sends one-year `.si`, `autorenew="off"`, and the approved owner contact; it never turns private-WHOIS on or retries a timed-out create.

- [x] **Step 1: Write failing local-server tests** named `test_check_and_quote_use_official_si_fields`, `test_quote_does_not_fabricate_provider_receipt_id`, `test_fx_requires_matching_funding_receipt`, `test_register_sends_owner_and_autorenew_off`, `test_domain_readback_filters_personal_contact_fields`, `test_customer_readback_fingerprints_current_contact_without_returning_pii`, `test_list_truncation_is_not_complete_readback`, `test_missing_credentials_prevent_mutation`, `test_nonzero_provider_code_is_not_success`, and `test_timeout_is_effect_unknown_without_retry`. Assert method/path/body, `code == 0`, returned domain ID, no raw registrant fields, and no second create request.
- [x] **Step 2: Run the test file and confirm the expected missing-module failure.** Run: `python3 -m pytest skills/domain-flip/test_openprovider.py -q`. Expected: collection fails because the client is absent.
- [x] **Step 3: Implement the stdlib REST client** for `/v1/auth/login`, `/v1/domains/check`, `/v1/domains/prices`, `/v1/domains`, `/v1/domains/{id}`, and `GET /v1/domains`; validate responses and redact credentials from errors.
- [x] **Step 4: Run the focused tests.** Run: `python3 -m pytest skills/domain-flip/test_openprovider.py -q`. Expected: all named local-server tests pass.
- [x] **Step 5: Commit** `feat(domain-flip): add Openprovider adapter`.

### Task 3: Sedo listing and official listing readback

**Files:**
- Create: `skills/domain-flip/sedo.py`
- Create: `skills/domain-flip/test_sedo.py`

**Interfaces:**
- Consumes: Task 1 policy and Task 2 registered-domain readback.
- Produces: `SedoClient.insert_for_sale(domain, price_eur, min_price_eur)`, `domain_status(domain)`, and `domain_list(domains)`.
- `insert_for_sale` reads the current official `DomainCategories` taxonomy, resolves the `Computers > Artificial Intelligence` category path, and sends those returned IDs. If the source is unavailable or the category is absent, it submits no listing.
- The adapter submits documented POST form requests and parses XML with the stdlib. `DomainInsert` returning `Ok` is only submission; `listed` requires a later official `DomainStatus` or `DomainList` match.
- Sedo's listing API does not prove buyer settlement or seller payout; those receipts remain separate events.

- [x] **Step 1: Write failing tests** named `test_insert_uses_post_eur_price_and_live_category_ids`, `test_missing_ai_category_prevents_insert`, `test_ok_submission_does_not_mark_listed`, `test_domain_status_confirms_exact_price`, `test_domain_not_in_sedo_is_not_listed`, `test_sedo_fault_stays_unverified`, and `test_fee_schedule_uses_live_category_and_maximum_sale_route`. Use fixture XML and fee markup, while the runtime reads the official fee page.
- [x] **Step 2: Run the test file and confirm the expected missing-module failure.** Run: `python3 -m pytest skills/domain-flip/test_sedo.py -q`. Expected: collection fails because the adapter is absent.
- [x] **Step 3: Implement the minimal form/XML adapter** for `DomainInsert`, `DomainStatus`, and `DomainList`; read API credentials only from the credential SSOT and never log them.
- [x] **Step 4: Run the focused tests.** Run: `python3 -m pytest skills/domain-flip/test_sedo.py -q`. Expected: all named tests pass.
- [x] **Step 5: Commit** `feat(domain-flip): add Sedo listing adapter`.

### Task 4: Finite owner pass and effect reconciliation

**Files:**
- Modify: `skills/domain-flip/core.py`
- Modify: `skills/domain-flip/test_core.py`
- Modify: `skills/domain-flip/openprovider.py`
- Modify: `skills/domain-flip/test_openprovider.py`
- Create: `skills/domain-flip/run.py`
- Modify: `skills/domain-flip/effect_reconcile.py`
- Create: `skills/domain-flip/rights_search.py`
- Modify: `skills/domain-flip/sedo.py`
- Modify: `skills/domain-flip/test_sedo.py`
- Create: `skills/domain-flip/candidate-review.schema.json`
- Create: `skills/domain-flip/test_run.py`
- Create: `skills/domain-flip/test_rights_search.py`

**Interfaces:**
- Consumes: Tasks 1–3; a review callback whose cost is proven zero at the margin or reserved within the USD 4.99 cap. The default paid runner is disabled.
- Produces: one daily pass for owner `domain-flip`, with candidate packet, a cost-gated review result if available, a domain-level event stream, and exact registrar/Sedo readbacks.
- The owner exposes `append_event(state_dir, event)`; it validates and durably appends all required occurrence fields before any owner-visible transition.
- The owner saves sanitized Openprovider readback payloads to private evidence files and attaches resolvable local evidence refs; it combines fresh availability with the separate create/renew quote response.
- Sedo fee readback includes Category I minimum-sale price; acquisition is ineligible below that floor. A listing is recognized only when `DomainStatus` and `DomainList` agree on the submitted price, minimum, EUR currency, and non-fixed-price mode.
- The owner revalidates the full review schema, restricts loaded environment/argv fields, and rejects PII-like values from any injected review callback.
- The owner does not invoke a paid runner by default. Without a verified zero-marginal-cost basis or bounded cost reservation, it records `review_cost_unverified` and stays scout-only.
- Registration submission, provider identity, resource ID, and registration readback ID must match exactly; any missing or mismatched value keeps the registration fenced and prevents listing.
- Before acquisition, the owner compares a fresh official Openprovider customer readback against the private approved handle/contact/email fingerprints; changed or incomplete contact state blocks registration. Events and evidence retain only safe fingerprints/status, never raw contact fields.
- Registration requires the Register.si natural-person WHOIS rule to be recorded in private state as email-only with no optional fields opted in; a mismatched provider holder type or absent official policy evidence blocks the candidate before model review.
- `submitted` is an unresolved external effect. Only an exact active domain/owner readback or matching confirmed listing readback clears its fence; PRE, mismatched, or missing readback remains uncertain.
- `rights_search.py` queries the official EUIPO Trademark Search API with `wordMarkSpecification.verbalElement` wildcard RSQL; it loads OAuth client credentials from the credential SSOT. Missing credentials, subscription approval, readback, or complete results is `rights_evidence_missing`, never a clean result. It retains only mark name, office, status, class, and official record URL. The adapter also attaches the official Register.si ADR procedure reference. It does not scrape the TMview web UI because the EUIPO legal notice prohibits automated commercial data collection.
- Production token endpoint and subscription state must be explicitly verified in the official EUIPO portal and recorded in credential SSOT; the sandbox token URL is never inferred as production.
- A purchase pass requires a business-balance receipt, a live Sedo fee/minimum-price readback, and a separate measured-cost snapshot. Each readback must be no older than 24 hours; missing or stale costs stay scout-only.
- When Openprovider and Sedo read credentials are available, each pass re-reads every confirmed existing holding, including registrations recovered by reconciliation. It reads all known holdings even after an earlier read failure or mismatch; unresolved `effect_unknown` occurrences stay with `effect_reconcile.py`. A listing mismatch or disappearance becomes `sale_or_listing_change_unresolved`; the owner neither relists nor records revenue until seller settlement, transfer, and payout receipts are read back.
- Follow-up regression `test_reconciled_registration_without_listing_dispatch_still_reads_all_providers` covers the recovered-registration path with no listing dispatch: all provider readbacks still run, while missing terms remain unresolved and trigger no write.
- The owner generates original, era-inspired names and gathers market, official rights-search, registrar, and sale evidence. A paid model review requires a lifetime-cost reservation; its absence keeps the pass scout-only.
- `effect_reconcile.py --occurrence-id ...` performs provider read-only calls only. Sedo readback may use POST with credentials in the body; no mutating endpoint is allowed. The reconciler either records a conclusive effect result or keeps the occurrence fenced.

- [x] **Step 1: Write failing tests** including `test_default_paid_reviewer_is_not_invoked_without_cost_reservation`, receipt/readback boundaries, reservations, and `effect_unknown` fences.
- [x] **Step 2: Run the owner tests and confirm the expected missing-module failure.** Run: `python3 -m pytest skills/domain-flip/test_run.py -q`. Expected: collection fails because the owner entrypoint is absent.
- [x] **Step 3: Implement the one-pass owner and read-only reconciler** using the private state root, validated append-only event writer, `effect_unknown` fencing, and a fail-closed paid-review cost gate.
- [x] **Step 4: Run focused tests and syntax checks.** Run: `python3 -m pytest skills/domain-flip/test_run.py -q` and `python3 -m py_compile skills/domain-flip/*.py`. Expected: all tests pass and compilation exits 0.
- [x] **Step 5: Commit** `feat(domain-flip): add finite owner pass`.

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

- [x] **Step 1: Write failing adapter tests** for receipt-gated revenue, cost categories, listings, duplicate receipts across changed sale metadata, missing payout proof, settlement timestamps, fee reconciliation, domain matching, future-dated costs, zero-cost coverage, and projected net.
- [x] **Step 2: Run the adapter tests and confirm the expected missing-module failure.** Collection failed because the adapter was absent.
- [x] **Step 3a: Implement the isolated domain-flip receipt adapter.** It derives sale identity from the immutable buyer receipt ID, verifies settlement/transfer/payout/bank timestamps, matches all costs to the sold domain, reconciles gross-to-payout deductions, requires explicit complete coverage including zero-cost categories, and emits gaps for incomplete/future evidence.
- [ ] **Step 3b: Wire the adapter to loop PnL, catalog, registry, and SSOT.** Re-read each shared file after its active owner lease clears; keep this integration separate from the isolated adapter.
- [ ] **Step 4: Run focused CFO and loop contract checks.** Run: `python3 -m pytest skills/cfo/test_domain_flip_adapter.py skills/cfo/test_economic_attribution.py skills/cfo/test_loop_pnl.py -q` and `./bin/lm-loop-contract`. Expected: focused tests pass and loop contract returns `ok=true` with 15 product loops and no errors.
- [ ] **Step 5: Commit** `feat(domain-flip): register CFO loop ownership`.

### Task 6: Live readiness, immutable release, and natural pass

**Files:**
- Modify only task-owned files if a contract defect is found; otherwise use the canonical runtime and private credential/state stores.

**Interfaces:**
- Consumes: Task 5 accepted main branch and the normal Life Manager immutable-release/apply path.
- Produces: one natural `domain-flip` occurrence, official listing/ownership readbacks, and a cost-complete payout ledger when a buyer closes.

- [ ] **Step 1: Create or reuse no-charge Openprovider and Sedo API access** only if setup needs no personal identity-document submission; save any new credential to the credential SSOT. Use EUIPO rights API only if an already authorized production subscription exists; do not submit identity documents or request a new subscriber approval. Expected: no personal funds or identity documents are sent, no provider write occurs, and missing EUIPO credentials keep purchase scout-only.
- [ ] **Step 2: Verify payout and registrant readiness** from existing owner-owned account data: exact legal registrant, current .si WHOIS fields, a receiving-tested functional public email alias with no personal data, Sedo payout account, and receiving-account readback. Expected: private legal registrant fields stay in credential SSOT/provider account data; WHOIS exposes only the intended functional email for a natural-person holder.
- [ ] **Step 3: Close the Sedo sale and payout readback path.** The official Basic API/WSDL exposes domain listing/status and parking-payment operations, but no marketplace settlement, ownership-transfer, or seller-payout receipt. After seller access exists, use an official Seller Center readback; if no API is supported, implement a bounded read-only collector through the registered CloakBrowser daily-driver direct CDP path. Persist only sanitized provider receipt IDs/status and evidence refs. Missing login, unsupported pages, ambiguous transfer, or absent bank-credit proof remains unresolved and never becomes zero revenue.
- [ ] **Step 4: Run a fresh-context read-only audit** of the exact candidate, rights evidence, public registrant fields, provider quote, sale/payout readback path, payout destination, funding amount, and remaining cap. Expected: the audit returns no unresolved critical or important risk; it does not authorize or perform any external effect.
- [ ] **Step 5: Verify whether an already allocated `domain-flip` business balance exists** and read back its owner, currency, balance, cap, and auto-refill state. Do not transfer or top up funds. The user authorizes a purchase only when total reserved outlay stays below USD 5.00. Expected: a matching pre-existing business balance and fresh quote within the USD 4.99 cap can enable acquisition; if absent, acquisition remains disabled and the missing funding source is recorded while scout-only work continues.
- [ ] **Step 6: Run one natural pass** through the admitted immutable release and confirm loaded SHA/argv/env, owner occurrence, registrar availability/quote, deterministic acquisition decision, Sedo listing status, and sale/payout reconciliation status. Expected: zero purchase when any identity, rights, quote, evidence, review-cost budget, or readback gate is missing; otherwise at most one registration and one verified listing.
- [ ] **Step 7: Continue scheduled natural passes** without duplicate effects until an actual Sedo sale completes buyer settlement, registered-holder transfer, payout, receiving-account credit, all-cost CFO attribution, and replay-zero. Expected: only then report positive realized net; keep the persistent goal active until this is true.

## Source references

- Openprovider official getting-started guide and REST schema: `https://developer.openprovider.com/get-started.html`, `https://developer.openprovider.com/data/swagger.json`
- Sedo official Basic API: `https://api.sedo.com/apidocs/v1/Basic/`
- Sedo official Basic API WSDL: `https://api.sedo.com/api/v1/?wsdl`
- Sedo official DomainCategories API: `https://api.sedo.com/apidocs/v1/Basic/functions/sedoapi_Categories.html`
- Sedo DomainListExtended, DomainParkingPayments, and GetBankData API docs: `https://api.sedo.com/apidocs/v1/Basic/functions/sedoapi_DomainListExtended.html`, `https://api.sedo.com/apidocs/v1/Basic/functions/sedoapi_DomainParkingPayments.html`, `https://api.sedo.com/apidocs/v1/Basic/functions/sedoapi_GetBankData.html`
- Register.si official rules and WHOIS §13: `https://www.register.si/splosni-pogoji/`
- EUIPO Trademark Search API and security: `https://dev.euipo.europa.eu/product/trademark-search_110/api/trademark-search`, `https://dev.euipo.europa.eu/security`
- EUIPO production API subscriber identity requirements: `https://dev.euipo.europa.eu/getting-started`
- EUIPO legal notice on automated data collection: `https://eutm.euipo.europa.eu/en/info/legal-notices`
- Register.si ADR procedure: `https://www.register.si/en/adr-procedure-guidelines/`
- Sedo .si fees and payout/transfer contract: `https://sedo.com/us/what-we-offer/price-list/`, `https://sedo.com/us/services/domain-transfer-service/`
- Current reported .si sale evidence and liquidity caveat: `https://www.dynadot.com/blog/why-si-domains-are-gaining-attention`
