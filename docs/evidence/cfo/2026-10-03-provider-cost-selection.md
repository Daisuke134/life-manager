# Provider cost selection and CFO acceptance — 2026-10-03

Status: `partial` / fail-closed. The provider contracts, benchmark runners, fallback caps, and synthetic seven-period gate are implemented. No provider switch, scheduler cutover, bank/marketplace mutation, or fabricated seven-day natural run is claimed.

## Evidence roots

| capability | evidence | decision |
|---|---|---|
| Japan POI | `2026-10-02` OpenPOI live probe; `0cff346fea` geocoder benchmark contract | Keep OpenPOI primary; Google Places remains budgeted fallback. |
| Japan transit | `ba24a8d7a7`; live Kyoto probe fresh `2709s/1 leg`; Tokyo probe timeout | Keep Transit primary with timeout/cache; Google fallback remains sequential. |
| Driving | `ba24a8d7a7`; one documented OSRM demo read-only probe fresh `468s/1 leg` | OSRM is shadow candidate only; no production endpoint selected. |
| Geocoding | `0cff346fea`; digest `8156a9373f58db2ff05f3ebd6c1d49a2f726389b878c49a579e26ea18802e9bc` | No winner: Google/Geoapify/selfhost slots were unconfigured, so no candidate is promoted. |
| LLM | `f91cafffaf`; digest `3b1e4bf9064eff18b730bec13c2c7b3b6bbe0bf1adaa89742c0e52067b058350` | `keep_current`; local lane is not eligible until a real existing routing-boundary shadow run has receipts. |

## Cost controls

The provider budget policy now exposes explicit nonessential caps:

- Google Places fallback: USD 0.50/day, USD 5/month, 100 units/month.
- Google route fallback: USD 0.50/day, USD 5/month, 100 units/month.
- Google geocoding: USD 0.50/day, USD 5/month, 200 units/month.
- Nonessential Gemini: USD 5/month.

Caps deny before network, preserve cache reads, and emit `budget_state`, `cap_key`, `next_action`, and `actual_status=unknown` without secrets. The CFO report renders cap state and next action.

## Official Google settlement

- Receipt: `google-billing://sha256/c5157075fe3e8331fa2a72d3b33fc98bbacb8b84a0ee2cfc945051ee87f66c64`
- September invoice: `JPY 27,889` including tax.
- B7 service totals remain official; estimated Monitoring/API counts are never included as settled.
- `skills/cfo/loop_pnl.py` now exposes `readback.variance` with invoice total, positive line total, and tax/rounding reconciliation. The focused test proves the variance while every emitted line remains `basis=official_invoice`.

## Seven-period gate

The synthetic gate now requires, in addition to fresh Moneytree/business/Google sources and delivery receipts:

- `poi` lane fresh with bounded fallback calls;
- `transit` lane fresh with bounded fallback calls;
- `geocoder` lane fresh with bounded fallback calls.

Production plumbing reads the tenant-bound `lm_provider_lane_summary` Supabase RPC for the JST reporting day, normalizes UTC day buckets, requires explicit unknown-count/numeric fields and a free-primary success, carries `poi`/`transit`/`geocoder` lane state into the Financial Manager report, and records OpenPOI free-primary usage. The migration must be applied before production readback; a missing, malformed, cross-tenant, or failed RPC readback remains partial and cannot satisfy the gate or become zero usage.

The acceptance test proves that a stale geocoder benchmark or an over-cap transit fallback keeps `complete=false`. No seven consecutive real production days are yet available; the existing owner-run natural observation remains the final external gate.

## Remaining external blockers

The latest B7 read-only run is separately recorded in `2026-10-03-b7-readback.md`: historical/trailing are both `unknown` with 137 coverage gaps and no currency totals. Moneytree freshness, current Coconala/PartnerStack/CrowdWorks/Alpaca/Stripe settlement coverage, branch-to-production parity, and seven elapsed daily closes remain as Section 11 financial TODOs. Provider benchmark artifacts with `provider_not_configured`, timeout, or no-winner states are not treated as zero-cost or production approval.
