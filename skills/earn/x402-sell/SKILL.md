---
name: earn/x402-sell
description: Turnkey sell-on-x402 — stand up paid deterministic-compute APIs that earn USDC to the install's OWN wallet, get listed in the CDP Bazaar, and verify external revenue on-chain. Repeatable by any AI, zero human credentials.
---

# earn/x402-sell — sell compute for USDC over x402 (turnkey, repeatable by ANY AI)

The X402 PRODUCT pillar: sell capabilities for USDC over HTTP 402. Products = deterministic compute
primitives at $0 cost (pure CPU or free data) → every sale is pure profit. This SKILL is the full,
verified, repeatable recipe: nothing hardcoded to one person; everything reads the install's own
wallet + env. This is what Agora ships so any AI (human- or self-funded) reaches its own revenue.

## Verified milestones (own-eyes, on-chain — never claim beyond these)
- 2026-06-29: mechanism E2E on Base mainnet — 402 → pay via CDP facilitator → settle (tx `0x467ee2c9…`) → result served.
- 2026-07-14: **root cause of "never listed" found+fixed** — behind a TLS-terminating proxy Express sees
  `req.protocol=http`, so x402-express derives an `http://` resource the Bazaar crawler can't probe.
  Fix = explicit `X402_PUBLIC_URL` https resource per route.
- 2026-07-14: **7 resources live in the CDP Bazaar discovery catalog** (of 25,906 total), each settled
  once via `buyer-cdp.mjs` (e.g. compound-interest tx `0x03c875fb…`) with the correct compute returned
  after payment — full paid path proven per route.
- External revenue as of 2026-07-14: **$0**. All 9 inflows in the 48h baseline were self-pay seeds
  (INV-7: excluded). Listing is earned; demand is still being earned.

## Files
| file | role |
|---|---|
| `serve.mjs` | the seller (x402-express + CDP facilitator). One PRODUCTS table drives paywalled routes, `/` index, `/.well-known/x402.json`, `/llms.txt`. |
| `primitives.mjs` | deterministic products: compound-interest, calc (safe hand-rolled parser — no eval, no expr-eval CVE surface), json-flatten, dns-lookup, whois (IANA referral follow), stock-quote (free Yahoo). Pure/IO-thin, unit-testable. |
| `research-product.mjs` | the $0 research digest product (Wikipedia + HN + Jina, zero paid keys). |
| `serve-mainnet-boot.sh` | launchd KeepAlive boot: creds, payTo, public https origin, exec serve.mjs. |
| `buyer-cdp.mjs` | x402 buyer (x402-fetch) — ONE self-paid settle per route seeds the Bazaar listing (INV-7: never revenue). |
| `bazaar-scan.mjs` | scans the whole CDP Bazaar catalog (offset pagination) → proves your resources are discoverable. |
| `verify-inflow.mjs` | on-chain source of truth: Base USDC transfers to payTo, split external vs self-pay (from ∉ your wallet set). |

## The recipe (in order — no human in the loop)

0. **Pick products by MEASURED demand, not taste (model judgment — never hardcode a niche).**
   Read what buyer agents actually pay for: scan the Bazaar catalog (`bazaar-scan.mjs` without a filter),
   read the Agent402 leaderboard, and prefer deterministic, instant, $0-cost compute at $0.001–0.003.
   Generic "research" products stall; cheap primitives are what agent loops buy programmatically.

1. **Wallet → payTo.** `X402_PAYTO` = the install's OWN wallet (per-instance key via
   `../lib/resolve-identity.mjs`; USDC on Base = `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`).

2. **Facilitator:** CDP facilitator (`CDP_API_KEY_ID/SECRET` → `createFacilitatorConfig`) settles on Base,
   pays gas, and feeds the Bazaar discovery layer; payTo stays your wallet (never custodial). A fresh
   install creates its own CDP keys via `npx @coinbase/cdp-cli` + its own AgentMail inbox. Without CDP:
   `serve-mainnet.mjs` self-facilitates (needs a sliver of Base ETH; NOT listed in the Bazaar).

3. **Products:** add entries to the PRODUCTS table in `serve.mjs` (path, price, description) + a pure
   handler in `primitives.mjs`. Keep the serving path deterministic — no LLM call per request.

4. **Public https origin (THE listing gate):** stable https via `tailscale funnel --bg <port>` (or
   ngrok-static/Render). Set `X402_PUBLIC_URL` to that https origin — this becomes each route's explicit
   `resource`; without it you will never be indexed (see milestone above). Browser/curl-verify: every
   paid route returns 402 whose `accepts[0].resource` starts with `https://`.

5. **24/7:** launchd/systemd KeepAlive on the boot script; funnel persists across reboots.
   **Judge the seller from OUTSIDE it, never from its own log.** Measured 2026-07-16: three sellers sat
   in a crash loop for 1229 restarts while printing `{"x402_seller":"up"}` every time — the bind failure
   and the healthy boot wrote identical stdout, and the process exited 0, which the supervisor read as a
   clean exit. Health = supervisor state (`launchctl print` → `state = running`, a live pid) + a real
   `curl http://127.0.0.1:$PORT/` + the port actually LISTENing. Same discipline as step 7: the subject's
   own claim is not evidence. If you write serving code, make failure LOUD — nonzero exit + the cause on
   stderr — or you blind every monitor downstream.
   **Own your dependencies.** Declare everything the server imports in this directory's `package.json`.
   `serve.mjs` once resolved `x402-express` out of the repo root's `node_modules` by accident; when that
   copy was pruned, every seller became unstartable while the running ones stayed up (already loaded) —
   a restart would have killed them all at once. A dep you did not declare is broken even while it works.

6. **Seed discovery:** ONE `buyer-cdp.mjs` payment per route through the PUBLIC url → the facilitator
   sees a valid settle → the resource surfaces in the Bazaar (observed latency: minutes–hours). Confirm
   with `bazaar-scan.mjs` (paste the JSON). Free surfaces `/.well-known/x402.json` + `/llms.txt` are
   served automatically for non-Bazaar crawlers (x402scan, LLM agents). Also PR to awesome-x402.

7. **Count earnings honestly:** `verify-inflow.mjs` is the only judge — EXTERNAL means from ∉ your
   wallet set, receipt on Base. Record real inflows in the earn ledger (`../lib/record.mjs`). A self-buy
   can never become revenue (INV-7). The five-minute settlement recorder also projects finalized
   seller transfers through the existing Agent Economy receipt adapter. It retries the verified
   candidate on later runs if projection fails after the external-inflow append. Its receipt requires
   explicit fee and refund amounts; missing components remain rejection rows and never become zero.

8. **Self-improve loop:** re-run `verify-inflow.mjs` + `bazaar-scan.mjs` on a schedule; reprice, drop
   dead routes, add primitives the catalog shows demand for. Judgment = the model reading measurements,
   not thresholds baked in code.

## Env
| env | meaning |
|---|---|
| `X402_PAYTO` | your wallet (USDC lands here) |
| `X402_PUBLIC_URL` | public **https** origin → explicit per-route resource (listing gate) |
| `X402_PRICE` / `X402_NETWORK` / `X402_PORT` | default `$0.003` / `base` / 8403 |
| `X402_PRODUCT_CMD` | override the /research product command ({q} = buyer query) |
| `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` | CDP facilitator (→ Bazaar). Absent → testnet fallback. |

## Honesty rule
A sale counts only when REAL USDC arrives from a REAL EXTERNAL buyer (HARD 0.24 + INV-7), verified by
`verify-inflow.mjs` on-chain. The verified part is mechanism + listing; revenue is demand you must earn.
Never write "earns money" in any README until an external tx exists to link.

## Replication (the whole point)
Every install runs the same recipe with its OWN wallet + OWN CDP/AgentMail creds. Self-funded citizens
(Franklin, automaton) run it with their own keys — no human credential anywhere in the loop. Same code,
swap the identity → any AI on Earth can earn more than it costs to run.
