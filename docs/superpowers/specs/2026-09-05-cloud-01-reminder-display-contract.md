# CLOUD-01 — Detailed travel and online reminder display

Owner-approved scope: Cloud daily launch only, following the 2026-09-05 revision in PR #4149 of `2026-08-28-life-manager-cloud-telegram-product-ux-design.md`. Local operations, loop migrations, alternative billing, and agent-framework changes are excluded.

This is the display-only amendment to AC-21/AC-22 of `2026-08-26-life-manager-cloud-on-time-core-design.md`. All other existing runtime, consent, tenant, claim, receipt, privacy, and deployment requirements remain binding. CLOUD-02, not this change, owns departure calculations and Calendar/call timing consistency.

## Display contract

1. Render provider walking legs and rides in their original order. Render geographic access/egress walking summaries only when the respective detailed edge walking step is absent. Do not sum access and egress into a purported total that omits transfer walking.
2. Use each walking leg's valid timestamps to derive its duration; round positive partial minutes up. Missing, negative, or invalid walking duration must not become an invented zero. Preserve known endpoints and label an unknown duration.
3. Keep line, headsign, ride times, stations, supplied platforms, transfers, and supplied fare. Do not invent distances, entrances, exits, cars, crowding, or live service alerts. This slice adds no provider or fetch.
4. An online event uses a computer icon and a locationless event a reminder icon; neither displays departure, arrival, route errors, or a stale route. Existing Calendar interpretation remains authoritative and online routing stays zero.
5. A standalone HTTPS URL from the online location may be shown as `イベント詳細`, not asserted to be a meeting-room URL. Reject credentials in URLs, insecure/unsafe schemes, malformed URLs, and embedded whitespace. Escape rendered text for Telegram HTML. This is URL rendering only, not fetching.
6. Display a physical route's provider arrival when valid; never label Calendar start as the route arrival. A failed physical route displays the event, start, destination, and explicit unavailability, without fabricated departure/arrival. Timing computation is unchanged pending CLOUD-02.
7. Keep one message per existing claim. Bound escaped text conservatively to 4096 characters without cutting an HTML entity or Unicode code point, and mark truncation explicitly. Do not split into independently sent messages.
8. Preserve existing claim → send → receipt, positive message-ID validation, unknown-delivery reconciliation, and replay fences byte-for-byte outside the formatter area.

## Code and tests

- Production: `apps/life-manager/lib/travel-reminder.js` (formatting only).
- Existing snapshots: `apps/life-manager/lib/travel-reminder.test.js` (only the two intentionally changed display expectations).
- Regression coverage: `apps/life-manager/lib/travel-reminder-detail.test.js` (14 tests, including real parser/projection with injected external IO).
- Credential-free CI: `.github/workflows/cloud-reminder.yml` (read-only token, locked dependency install, no production credentials).

Run from `apps/life-manager`:

```bash
node --test lib/travel-reminder.test.js lib/calendar-interpreter.test.js lib/events.test.js lib/transit.test.js lib/travel-transit-wire.test.js lib/route-cache.test.js
node --test lib/travel-reminder-detail.test.js
```

## Verified evidence (2026-09-05)

- Implementation branch: `fix/cloud-01-detailed-reminder-20260905`; PR #4150.
- Original base: `7e10f5348f757eb103d1365bb5fd8aa7a0c94bb7`.
- RED head: `36cb54a349578e9f457e36e28e932841f882bd8a`; Actions run `33957886608`, job `101284414308`. Existing contracts 84/84 passed; new display suite 1/14 passed, 13 failed on the old behavior.
- Verified implementation head: `1a185c27a6f6d64ac07171db7c68a268987b5e55`. Actions run `33958578988`, job `101286278624`, tested prospective merge `9a57abfec5a0fc8f4bf383c40c00d2f012d7d341` against then-main `ff1a5ab4d6566762b2c3df640873ee37160b6efa`.
- GREEN: existing contracts 84/84 and new regressions 14/14, failures 0, skipped 0. Node 22.23.2, locked install completed. Full application suite was not run in this verification.
- Final source diff excludes the scheduling/effect function; a transient duplicate guard was removed. The existing release-claim assertion was restored; only intended formatter snapshots differ.
- Code review requested from the existing CodeRabbit integration. A request or a skipped automatic review is not completed independent review.
- Repository-wide Security Scan run `33958578941` reports failures in gitleaks, PII shapes, OSS boundary, and loop contracts. These are not waived or relabeled green by the focused tests. Diagnosis/clearance remains a merge gate.
- This evidence is NOT a claim of merge, deployment, actual Telegram delivery, or new real-user E2E. No production credential, Calendar event, Telegram send, phone call, or payment was used for these tests.

## Remaining gate before CLOUD-02

- [ ] Complete independent review and resolve material findings.
- [ ] Resolve or explicitly adjudicate the repository-wide verification failures without weakening safety checks.
- [ ] Merge through the normal path, then read back exact deployed service SHA and health.
- [ ] Observe one real physical and one online reminder, correlate the Telegram ID with durable receipt, and verify no duplicate on replay. Use an authorized test tenant; do not expose its data in this document.
- [ ] Update the primary progress ledger with those actual observations, then advance to CLOUD-02. Do not mark this item fully shipped from unit tests alone.

## Primary contracts consulted

- Transit OpenAPI: https://api.transit.ls8h.com/api/openapi.json — geographic `accessWalkSecs`/`egressWalkSecs`, walking leg times, and optional platforms.
- Telegram Bot API: https://core.telegram.org/bots/api#sendmessage — message length and HTML entity boundary.
- Existing current parser, event projection, transport, and delivery tests in this repository.
