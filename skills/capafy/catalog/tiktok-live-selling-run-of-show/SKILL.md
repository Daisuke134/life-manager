---
name: tiktok-live-selling-run-of-show
description: Turn a seller's pasted product facts, approved claims, FAQs, offers, and livestream length into a timed TikTok LIVE selling run-of-show with safe objection handling and moderator cues.
---

# TikTok LIVE Selling Run-of-Show

Create an honest, timed livestream plan from the seller's supplied material.
This is for a live selling session, not a short-form video script: it organizes
the host's sequence, product demonstrations, audience questions, and moderator
cues over a complete session.

## Required input

Ask for the product facts and approved claims, audience, session length, offer
terms, inventory limits if relevant, FAQ or objections, required disclosures,
and any words or claims the host must avoid.

## Output

Return these sections in order:

1. A claim boundary: approved facts, prohibited claims, missing proof, and
   disclosure placement.
2. A timed run-of-show with host beats, demonstration prompts, audience
   questions, product transitions, and a close.
3. An objection-response bank that answers only from supplied facts; label a
   missing answer `[NEEDS APPROVAL]`.
4. Moderator cues: questions to pin, comments to acknowledge, escalation
   triggers, and moments to repeat the supplied offer terms.
5. A pre-live checklist and a short post-live note template for the seller's
   own observations.

## Truth boundary

Use only the buyer's pasted material and general writing knowledge. Do not
claim to access TikTok LIVE, inventory systems, comments, analytics, current
trends, product pages, or outside sources. Do not promise sales, legal or
platform-policy compliance, or a performance result. Never invent prices,
discounts, testimonials, availability, product features, or health claims.
Mark unsupported information as `[NEEDS APPROVAL]`.
