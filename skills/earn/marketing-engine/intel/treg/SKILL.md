---
name: treg
description: Use Treg for external public-data research in Life Manager agents. Use when a task needs live X/Reddit signals or current endpoint and price details.
---

# Treg for Life Manager agents

Use only the scoped agent identity already supplied as `TREG_TOKEN`. Never print it, request login, create/invite accounts, top up the team, or enable automatic top-ups.

Before a paid route:

1. Search Treg's catalog for the job and inspect the current endpoint, price, and hit rate.
2. For the weekly signal monitor, use public X and Reddit search routes only. Each product/platform route must include `X-Treg-Route-Max-Cost: 0.003`.
3. Capture the exact `call_id`, `charged_micro`, provider, and source URLs. Return only public post/profile URLs, product fit, and a concise `why_now` reason.

The weekly monitor covers nine products with at most one X and one Reddit route per product (18 billed routes, at most `$0.054` total). Stop before a paid call if the Treg balance is below `$0.05`; do not substitute a more expensive route when the cap refuses a call.

Do not perform email/phone lookup, contact enrichment, outreach, publishing, ads management, or any write operation. An empty result is valid and does not prove there is no demand.
