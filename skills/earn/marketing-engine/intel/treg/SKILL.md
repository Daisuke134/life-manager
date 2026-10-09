---
name: treg
description: Use Treg for external public-data research in Life Manager agents. Use when a task needs live X/Reddit signals or current endpoint and price details.
---

# Treg for Life Manager agents

Use the gated Treg MCP tools available to the Life Manager Codex agent. The local gate reads the scoped credential from private SSOT; never request, print, or pass a token through the agent environment. Do not bypass the gate with direct HTTP or the Treg CLI. Never create/invite accounts, top up the team, or enable automatic top-ups.

Before a paid route:

1. Search Treg's catalog for the job and inspect the current endpoint, price, and hit rate.
2. For the weekly signal monitor, use public X and Reddit search routes only. Put `X-Treg-Route-Max-Cost: 0.003` in the `headers` argument of every billed `call`; Treg's MCP server forwards that argument to the upstream route. Inspect route prices and never choose a more expensive route.
3. Capture each exact `call_id` and `charged_micro`. Return only public post/profile URLs present in that call result, product fit, and a concise `why_now` reason; raw provider details stay in the private Codex MCP evidence.

The shared local gate limits all Codex agent tasks to 18 billed routes and `$0.054` per UTC day across one Treg identity. It reserves `$0.003` before each route and checks current balance, unresolved receipts, and the `$0.05` floor. The Treg identity's server cap is an additional limit; Treg documents it as fail-open if its quota database check errors. Never retry a refused or uncertain route, and do not substitute a more expensive route.

Do not perform email/phone lookup, contact enrichment, outreach, publishing, ads management, or any write operation. An empty result is valid and does not prove there is no demand.
