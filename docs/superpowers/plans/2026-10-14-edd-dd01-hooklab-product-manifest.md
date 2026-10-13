# Hook Lab Distribution Product Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register Hook Lab as a source-backed marketplace product profile so distribution EDD can measure it without enabling or publishing through its social account.

**Architecture:** Extend the existing `marketing.product.v1` registry with the additive `marketplace_agent` type and an optional, validated `distribution_profile`. Add one `hook-lab` product record with a frozen, date-bound offer snapshot and metadata for the existing Instagram destination and official outcome sources. Do not add an active publisher account or new scheduler. Update Gate10 so it protects its core products and exact safe plans rather than assuming the global registry never grows.

**Tech Stack:** Python 3 `unittest`, JSON Schema draft 2020-12, existing `product_router.py`; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` (DD01 design decision).

**Execution:** Native solo implementation is explicitly requested by Dais. Astra Advisor's dedicated native tools are not exposed and parent model/effort metadata are unobservable; no model-pinned reviewer will be fabricated. The primary self-reviews the complete diff and required CI; there is no production effect.

## Global Constraints

- Preserve Hook Lab seller `8123079349`, published v1.0.7 offer, and `skills/capafy/FROZEN.json`; do not reprice, resubmit, publish, or enable a launcher.
- Keep the buyer problem as seller-copy evidence, not validated customer research.
- `@capafy.hooklab` / `hooklab_ig` is a historical channel reference; shared-token visits are channel-window data, never per-slot success.
- Keep settled net, refunds, fees, and actual model cost `unknown` unless exact official receipts join to the product/occurrence.
- Keep `customer_revenue` separate from financing, investment, aggregator, and non-economic roles.
- No paid channel, tool, or provider; no production account or publisher state changes.

## Review Focus

- The official v1.0.7 price snapshot conflicts with stale static listing copy; use the official detail snapshot and preserve the conflict in the profile.
- Marketplace profiles without a matching active account manifest must remain non-routable.
- A shared `hooklab_ig` token cannot attribute a visit to multiple creative slots.
- Public Sold counters, detail views, gross sales, and model-cost estimates do not establish settled net profit.
- Additive product profiles must not change the two Gate10 safe-plan identities or weaken their product/account/hook/renderer checks.

---

### Task 1: Register the frozen Hook Lab profile

**Files:**
- Create: `skills/earn/marketing-engine/registry/products/hook-lab.json`
- Modify: `skills/earn/marketing-engine/schemas/product-manifest.schema.json`
- Modify: `skills/earn/marketing-engine/gates/product_router.py`
- Test: `skills/earn/marketing-engine/gates/test_product_routing.py`

**Interfaces:**
- `load_registry(engine)` returns `Registry.products["hook-lab"]` with `type="marketplace_agent"` and a validated `distribution_profile`.
- The profile binds `buyer_problem`, `offer_snapshot`, `allowed_channel_accounts`, `destination`, `outcome_sources`, `economic_role`, and `related_loop_id`.
- The profile records `publish_enabled=false`; no account is added to `registry/accounts`, so `product_router` cannot create a publisher route for Hook Lab.
- The top-level `price` uses the starting day plan; the complete frozen day/week/month schedule lives in `distribution_profile.offer_snapshot.price_tiers`.

- [ ] **Step 1: Write the RED profile test**

Add `test_hook_lab_marketplace_profile_is_frozen_and_not_routable` to assert `product_id="hook-lab"`, seller ID `8123079349`, v1.0.7 observed at `2026-10-13T17:40:00+09:00`, day USD 3.99/cap 10, week USD 9.99/cap 30, month USD 19.99/cap 80, and trial days 0. Also assert `buyer_problem.validation_status="seller_copy_unvalidated"`, a static-listing price conflict is preserved, Instagram `@capafy.hooklab` / Postiz integration `cmuuycr5402uzqw0yhanqggo9` / token `hooklab_ig`, destination `https://capafy.ai/agent/8123079349`, `per_slot_attribution="shared_token_not_per_slot"`, `primary_metric="settled_net_contribution"`, `publish_enabled=false`, settled-net/actual-cost sources are `unknown`, and no account-registry entry exists for `hook-lab`.

Update `test_four_products_and_locked_accounts_validate` to assert its five existing products as a required subset, not the full registry equality; the dedicated Hook Lab test covers the new profile.

- [ ] **Step 2: Write the RED malformed-profile test**

Add `test_marketplace_profile_missing_offer_or_outcome_source_fails_closed`. Remove `published_version` or the `settled_net_contribution` outcome source from a temporary copy and assert `load_registry` rejects the profile.

- [ ] **Step 3: Run the focused tests and confirm RED**

Run from `skills/earn/marketing-engine/gates`:

```bash
python3 -m unittest test_product_routing.MarketplaceProductProfileTest
```

Expected: the new product is absent or the marketplace profile is rejected by the current product schema/router.

- [ ] **Step 4: Implement the minimal registry extension**

Add `marketplace_agent` and the optional `distribution_profile` object to the existing schema. Update `product_router.py` to validate required provenance and offer tiers for marketplace profiles while keeping all existing product manifests valid. Add the Hook Lab profile with v1.0.7 official offer data, source conflict reference, allowed Instagram identity, Capafy destination/CT, and unknown settled-net/cost status. Do not add a publisher account or change provider state.

- [ ] **Step 5: Run tests and confirm GREEN**

Run from `skills/earn/marketing-engine/gates`:

```bash
python3 -m unittest test_product_routing
```

Expected: all product manifests validate; Hook Lab is loaded but no publishing account is registered.

- [ ] **Step 6: Commit the profile and validator**

```bash
git add skills/earn/marketing-engine/schemas/product-manifest.schema.json skills/earn/marketing-engine/gates/product_router.py skills/earn/marketing-engine/gates/test_product_routing.py skills/earn/marketing-engine/registry/products/hook-lab.json
git commit -m "feat(marketing-engine): register Hook Lab distribution profile"
```

### Task 2: Keep Gate10 safe-plan verification additive

**Files:**
- Modify: `skills/earn/marketing-engine/gates/verify_gate10.py`
- Test: `skills/earn/marketing-engine/gates/test_verify_gate10.py`

**Interfaces:** Gate10 continues to require its four core products and validates the exact existing safe-plan product/account/hook/renderer identities; unrelated product profiles and accounts do not fail a global equality check.

- [ ] **Step 1: Extend the failing test**

Update `test_live_gate10_evidence_passes` to assert the core Gate10 products remain registered, Hook Lab can coexist in the registry, and the existing two safe plans are unchanged. The baseline currently fails with `initial product registry differs` because Gate10 compares the complete registry to a stale four-product list.

- [ ] **Step 2: Run the test and confirm RED**

Run from `skills/earn/marketing-engine/gates`:

```bash
python3 -m unittest test_verify_gate10
```

Expected: fail at the stale global product-count equality, not at a safe-plan identity.

- [ ] **Step 3: Make Gate10 scope explicit**

Change the verifier to require its core product IDs as a subset and rely on existing per-plan checks for account and route identity. Remove the stale global account-count assertion; preserve exact safe-plan count, hook, renderer, CTA, attribution, and quarantine checks.

- [ ] **Step 4: Run the Gate10 test and confirm GREEN**

Run `python3 -m unittest test_verify_gate10` from `skills/earn/marketing-engine/gates`.

- [ ] **Step 5: Commit the Gate10 correction**

```bash
git add skills/earn/marketing-engine/gates/verify_gate10.py skills/earn/marketing-engine/gates/test_verify_gate10.py
git commit -m "fix(marketing-engine): keep Gate10 checks product-scoped"
```

### Task 3: Verify, document, review, and integrate DD01

**Files:**
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`
- Modify: `docs/evals/distribution-edd-research.md` only if a new source limitation must be recorded.

- [ ] Run `python3 -m unittest test_product_routing test_verify_gate10` from `skills/earn/marketing-engine/gates`.
- [ ] Run `python3 -m unittest test_product_binding` from `skills/earn/marketing-engine/identity`.
- [ ] Run `python3 -m unittest test_experiment_attribution` from `skills/earn/marketing-engine/measure`.
- [ ] Run `npm run test:writer-eval` from `apps/life-manager`.
- [ ] Update DD01's SSOT status with the exact profile path, validation results, source conflict, and `publish_enabled=false`; leave DD02–DD12 in order.
- [ ] Run `bash scripts/verify-source-boundary.sh`, `git diff --check`, commit/push, open PR, complete exact-head CI, and self-review the full diff before integration. Astra native orchestration/reviewer controls are not exposed and parent model/effort are unobservable; do not claim Astra review. Do not deploy or publish because DD01 is source/evaluation metadata only.
