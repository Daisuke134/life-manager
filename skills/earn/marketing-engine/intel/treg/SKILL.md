---
name: treg
description: Use Treg for external public-data research in Life Manager agents. Use when a task needs live X/Reddit signals or current endpoint and price details.
---

# Treg for Life Manager agents

Use only the scoped agent identity already supplied as `TREG_TOKEN`. Never print it, request login, create/invite accounts, top up the team, or enable automatic top-ups.

Before a paid route:

1. Search Treg's catalog for the job and inspect the current endpoint, price, and hit rate.
2. For the weekly signal monitor, use public X and Reddit search routes only. The dedicated Codex MCP connection attaches `X-Treg-Route-Max-Cost: 0.003` to every request; inspect route prices and never choose a more expensive route.
3. Capture each exact `call_id` and `charged_micro`. Return only public post/profile URLs present in that call result, product fit, and a concise `why_now` reason; raw provider details stay in the private Codex MCP evidence.

The weekly monitor covers every supplied product with at most one X and one Reddit route per product (at most 18 billed routes and `$0.054` total for the current nine products). The dedicated Treg identity has an 18-call daily cap as a second limit; Treg documents that cap as fail-open if its quota database check errors, so validate actual receipts too. Before each route, preserve `$0.05` after subtracting its quoted cost and prior charges. Do not substitute a more expensive route when the cap refuses a call.

Do not perform email/phone lookup, contact enrichment, outreach, publishing, ads management, or any write operation. An empty result is valid and does not prove there is no demand.
