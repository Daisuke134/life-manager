# Dot organic mobile editorial handoff

Status: review-ready copy; not published, deployed, scheduled, or revenue-producing evidence.
Owner: this Codex dot-organic task. This is an execution artifact, not a new SSOT.
Authority: docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md, C2/C4. User prioritizes Anicca/Honne, English first and Japanese second, zero incremental spending, independent of Postiz. $10k MRR is a goal, never a claim.

## Ready action

Website owner can adapt the four bodies in articles.md to the existing blog schema, then preview and review them. Publish only after separate authorization; this handoff does not authorize submission. Proposed exact URLs (NOT live):

- https://aniccaai.com/blog/affirmations-after-a-small-work-mistake
- https://aniccaai.com/blog/shigoto-no-chiisana-miss-kotoba
- https://aniccaai.com/blog/reply-to-a-short-message-without-guessing
- https://aniccaai.com/blog/mijikai-henji-kimochi-kimetsukenai

Start with Anicca EN, then Honne EN. Japanese copies are localized alternatives, not another scheduled campaign. No social posts, scheduler, account, or paid API is created. Do not submit these articles through Postiz. Check each proposed slug against live site and open content PRs again before publication. Do not overwrite existing affirmation support pages.

Anicca article is a specific work-mistake use case, avoiding the existing overthinking-at-night / self-doubt / comparing-yourself page titles. Honne copy deliberately avoids treating AI output as knowledge of another person's thoughts. All examples are fictional and labeled; no testimonials, ratings, medical outcomes, or revenue claims are invented.

## Product facts re-read 2026-10-10

- https://aniccaai.com/affirmation-app and /affirmation-app/ja: affirmation product; optional subscriptions. Public EN page still says iOS 15, but https://apps.apple.com/jp/app/id6755129214 says iOS 16.6. Use Apple's requirement. Anicca-products draft #447 owns partial FAQ correction; open #432 owns AffirmationLanding.tsx and sitemap. Neither is changed here.
- https://aniccaai.com/honne and https://apps.apple.com/us/app/id6759667221: pasted-chat analysis and suggested replies, 3 free analyses/day, optional premium, iOS 18. No promise of accurate mind-reading.
- https://aniccaai.com/lm: Google Calendar travel-time blocks/departure reminders, eligible events, Calendar permission. Keep Life Manager as the next separate editorial topic, after mobile readback; no revenue claim or price change.
- https://aniccaai.com/dais: portfolio hub. Other products remain in their owners' queues; no duplicate campaign created here.

Pattern research before writing: ThinkUp's https://thinkup.me/positive-affirmations/ provides concrete examples and https://thinkup.me/daily-affirmations/ pairs them with use instructions and an app CTA. Adopt that educational structure, not its text or outcome claims. Public selection counts are publisher-reported, not audited sales; no current bestseller-rank assertion is made.

## Measurement boundary

All four existing landing-page CTAs use utm_source=dot_owned, utm_medium=organic_editorial, utm_campaign=mobile_work_moments_20261010 and distinct utm_content. These identify proposed links only. They do not prove analytics ingestion, preserve attribution through the App Store, or create Apple campaign tokens.

Before publishing, the website owner must read back a preview click and the actual outbound App Store URL. Confirm existing analytics records the source and content. Reuse a verified Apple campaign link owned by the correct app if available; do not invent a provider token, add credentials, or claim end-to-end measurement otherwise. Keep click counts, ASC first-time downloads, RevenueCat trials/paid transactions, refunds and MRR separate. Do not divide mismatched reporting windows or count purchase_completed events as settled revenue.

Report after publication: article URL + deployed commit + actual publication time; observed visits/clicks with dates; product-scoped ASC/RC readback with source windows; attributed revenue only if a supported join exists. Missing data is unknown. This pack's baseline is no publication and no attributed revenue.

## Ownership / coordination

- AGMSG CLI was not on PATH; the checked ~/.local/share/agmsg, ~/.config/agmsg, ~/.local/state/agmsg locations were absent. Historical SSOT AGMSG entries were read as context only. No live coordination success claimed; no binding or seat created.
- Open Life Manager marketing PRs observed: #7133 metrics/reporting and legacy self-heal lanes. No matching dot-owned editorial pack observed. This is not proof that every unpublished owner task is absent.
- #7443 is fully superseded functionally by #7447 and is not used as this campaign's achievement. #7450 is the other owner's watchdog lane; no implementation overlap.
- Dedicated docs-only worktree, separate from active runtime and existing PRs. No source registry, SSOT, browser session, effect fence, pricing, publication or credential edits.

## Review checklist

- Verify product facts and four CTA destinations against current pages.
- Ensure the four proposed slugs remain unused and no other owner has claimed them.
- Read the examples and affiliation disclosures in both languages.
- Confirm all four CTA query sets identify dot-owned editorial content.
- Fix the landing-to-store attribution gap through the existing website owner before claiming measured conversion.

## Local verification evidence (2026-10-10)

- Read-only public HEAD checks: /affirmation-app, /affirmation-app/ja, /honne, /honne/ja each HTTP 200; all four proposed /blog slugs HTTP 404 (unused at check time, not a reservation).
- Python standard-library check passed: four distinct slugs; four correct product/locale CTA paths; all query fields match the isolated dot_owned campaign; no missing product/locale mapping.
- verify-source-boundary.sh PASS; git diff --check PASS. No dependencies installed, build, paid model call, deployment, or external submission.
