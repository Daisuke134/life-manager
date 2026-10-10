---
name: lead-signals
description: Find recent public posts that show a likely fit with one of Life Manager's product buyer profiles. Use for the scheduled Treg signal monitor.
---

# Life Manager lead signals

Read the supplied buyer sentence for each product. Keep a row only when a public X or Reddit post from the last seven days shows first-person pain or clear intent that the product can address. Generic discussion, promotional posts, vendors, recruiters, and unrelated comments are not leads.

For each kept row, return the exact product ID, platform, public person/profile URL, signal type, exact source post URL, observed date, and one concise `why_now` sentence supported by the post. Never invent or normalize a URL. Omit uncertain rows.

Review every supplied product profile, with `anicca-ios` first. Return at most one strongest new signal per product so the weekly digest stays useful across the whole product set.

The first monitor run is a baseline: return qualified rows for private deduplication, but do not label them new or send historical rows. Later runs may report only keys the host says are absent. The host owns the private `signals.csv`; do not read or modify files outside the supplied evidence.

Never look up email addresses or phone numbers, enrich contacts, send messages, publish content, or use Treg routes outside public X/Reddit search. Return every Treg call ID and exact reported cost in the structured result.
