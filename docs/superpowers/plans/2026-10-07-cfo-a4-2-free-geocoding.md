# CFO A4.2 Free Geocoding Fallback Plan

> **For agentic workers:** Use `superpowers:executing-plans` task-by-task. The unified CFO SSOT remains the only TODO/order/status source.

**Goal:** Reduce avoidable Google Geocoding requests in Japan without changing travel UX, accepting ambiguous coordinates, or losing source attribution.

**Architecture:** Keep the current transit-first route flow. For Japanese address-shaped queries, try GSI AddressSearch; for Japanese named-place queries, try OpenPOI Suggest. Accept only one exact, valid candidate with required provenance. Otherwise fall through once to the existing Google Geocoding path. Keep free-provider results process-local so license/attribution metadata is not lost in the coordinate-only Supabase geocode table. Bound cache RPCs and fail open.

**Tech Stack:** Existing Node.js `fetch`, `AbortController`, `node:test`, current geocode and route caches.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`, CFO A4.2. Cloud UX reference: `docs/superpowers/specs/2026-10-06-life-manager-web-first-travel-design.md`.

## Problem This Plan Solves

The existing Travel flow can call paid Google Geocoding for uncached home/event locations. Free Japanese sources may avoid that geocoding charge for some locations, but a coarse or ambiguous point can make the user miss an appointment; provider errors must not break the existing route flow. OpenPOI also logs search query text and requires attribution/license handling, while the coordinate-only persistent cache cannot safely retain its full provenance. The goal is to reduce avoidable Google **Geocoding** requests without claiming savings for Google Directions/Routes or accepting a bad route.

## To-Be User Experience

- The user keeps the same Calendar event location and saved home/base input. There is no geocoder selection screen, new question, or changed route workflow.
- For a Japanese address-shaped location, Life Manager may try GSI; for a specifically recognized Japanese facility name, it may try OpenPOI. The user sees the same Transit-first route and Travel Calendar helper if a unique, precise, attributable candidate is accepted.
- If a free candidate is coarse, ambiguous, invalid, private/free-form, unavailable, or times out, the existing Google Geocoding fallback runs once. Existing non-Japan, Transit-failure, and Google Directions/Routes behavior remains unchanged.
- A free-source helper adds source/license attribution to its description. A4.2 does not otherwise change the user-facing Calendar or dashboard screens. Raw location/query text is not placed in usage telemetry.
- The broader Cloud Web-first journey (public landing → browser sign-in → Calendar consent → one home/base input → next-departure dashboard) is specified separately in `docs/superpowers/specs/2026-10-06-life-manager-web-first-travel-design.md`. A4.2 does not implement that signup flow; the public landing still hands off to Telegram until WB-14 is completed.

## Execution Order and Ownership

- The canonical SSOT currently has cursor `A4.1`, and its existing TODO order is `A4.1 → A4.2 → A4.3 → A5 → A6 → A3 conditional → A7 → A8 → A9 → A10`.
- A4.1 fixture evidence and focused tests are complete on this branch. Current readback confirms owner `lm-cfo-observability-1002` still holds the active managed-worktree lease for `cfo-mobile-evidence-ssot-20261007` through `2026-10-08T00:02:50Z`; that worktree has a staged edit to the same canonical SSOT. This is an internal write-coordination guard, not an A4.2 product dependency, and the canonical file remains untouched here.
- User direction is to continue available work rather than wait on that shared-file write. Therefore this branch implements and tests A4.2 next; the shared SSOT update remains last and must record both A4.1 evidence and A4.2 source evidence in one owner-safe update. This does not claim the canonical cursor has advanced.
- Do not edit the leased SSOT from another worktree/branch, steal the lease, deploy/restart production, query real calendar data, or send real user locations to candidate providers during tests.

## Current Status

- A4.2 source and regression tests are pushed through `5ab934a5ca6f7d52428e45ae115aa50812978e4b` and `ec7165eaccf91bcf27f148c5390ea1c3ec8bba39`; the branch is synchronized with `origin/main` `a4a3837d` at merge commit `0b84a5c1a7`.
- Independent read-only review passes the source/privacy fixes. The canonical cursor remains `A4.1`; this branch has not edited or advanced the leased SSOT. Once the lease is released, record A4.1 fixture evidence and A4.2 implementation/test evidence together, then advance the cursor to `A4.2` without claiming production natural-run acceptance.
- Latest PR #6803 readback at `2026-10-07T02:29Z`: `OSS self-contained boundary` and `gitleaks` fail, `Loop control contracts` is pending, and the other reported checks pass. The OSS check reports `manifest_inventory_mismatch` for `skills/capafy-autopublish`; `origin/main` commit `c0da6b382c` changed files under that root without updating `docs/manifests/oss-merge-1-sources.json`, while this PR diff touches neither. The cause of the current gitleaks failure is not yet established. Keep the PR draft until failures are understood/resolved and the canonical evidence update is safely recorded.

## Acceptance Criteria

- Existing non-Japan, unresolved-coordinate, Transit failure, and Google route fallback conditions remain unchanged; Transit remains first for Japan routes.
- A GSI candidate is accepted only when the response has exactly one valid point and its normalized title exactly preserves the query's address precision.
- An OpenPOI candidate is accepted only when exactly one suggestion exactly matches the normalized place name, coordinates are valid and in Japan, and complete non-empty `licenses` and `attributions` arrays are present. Reject records carrying `Apache-2.0` until the required Foursquare NOTICE is present in developer documentation.
- Address-shaped inputs are never sent to OpenPOI. Provider requests contain only the location string, never calendar title, description, attendee, event ID, or account data.
- OpenPOI is used only for specific recognized Japanese facility names; generic labels such as `会場`, personal/home labels, and arbitrary Japanese text bypass it and retain the existing Google path.
- Accepted free candidates cause exactly zero Google Geocoding requests. Ambiguous, unmatched, malformed, timed-out, or unavailable free-provider results cause exactly one existing Google Geocoding fallback per unresolved location.
- Free-provider cache keys are tenant/provider/normalized-query scoped; free-provider cache entries retain provenance. The coordinate-only persistent cache is not used for free-provider results.
- Geocode cache RPC timeout/failure does not prevent the provider fallback path from running.
- Usage events identify provider, operation, result/failure, request count, estimated cost, and the existing opaque event version without recording raw location text. Zero estimate is not reported as settled actual cost.
- When a free-provider result creates a travel event, the generated event description displays the required source attribution/link while retaining the existing calendar interaction flow.

## Tasks

### Task 1: Add offline candidate contract tests

- [x] Write tests first for exact GSI match, GSI precision loss, unique OpenPOI match, duplicate exact-name ambiguity, missing provenance, unsupported Apache-2.0 record, invalid/out-of-Japan coordinates, zero results, timeout, and address-query privacy routing.
- [x] Run the focused test and confirm a meaningful assertion failure before implementation.

### Task 2: Implement provider candidate resolution and fallback

- [x] Add the smallest provider adapter using the fixture-observed GSI and OpenPOI response shapes; enforce bounded requests and strict eligibility.
- [x] Integrate it before existing Google Geocoding, retaining provider-separated tenant/query cache keys and complete candidate provenance.
- [x] Limit OpenPOI dispatch to specific facility-name suffixes; generic venue labels and private/home hints bypass it.
- [x] Add focused usage tests proving accepted-free `Google Geocoding=0`, each rejected candidate produces exactly one Google geocode, and event usage metadata contains no raw location.

### Task 3: Bound geocode cache RPCs

- [x] Add a finite timeout to existing geocode-cache get/upsert calls; return cache miss/write-false on timeout so the route continues.
- [x] Test a never-resolving injected cache fetch and verify the Google/free provider path still proceeds.

### Task 4: Carry attribution through the existing calendar output

- [x] Preserve free geocode provider/license/attribution metadata in the structured route result and existing route cache payload.
- [x] Add source attribution/link to the auto-created travel event description only when free-provider data was used; leave summaries, timing, Transit-first behavior, and write count unchanged.
- [x] Test fresh-route and cached-route attribution plus the unchanged no-attribution Google path.

### Task 5: Focused acceptance and delivery

- [x] Run fixture, geocode cache, travel usage, and route tests plus `git diff --check`.
- [x] Review secret/PII diff, commit and push this branch; keep the PR draft until the canonical SSOT lease is released and its cursor/order record is updated.

### Task 6: Record A4.1/A4.2 evidence in the canonical SSOT after lease release

- [ ] Re-read current `origin/main`, owner/lease, cursor, and any intervening SSOT edits.
- [ ] Record A4.1 fixture findings and A4.2 source-test findings without claiming production natural readback; preserve the established TODO order and advance the cursor from `A4.1` to `A4.2` in the same update.
- [ ] Run the required source-boundary check, commit/push, and merge only after the shared owner has released the file and the update is based on latest main.

## Review Focus

- GSI's captured full-address result drops the house number; it must fall back rather than silently route to a coarse point.
- OpenPOI's captured `東京駅` suggestions contain two exact names with materially different coordinates; they must remain ambiguous.
- OpenPOI docs require an OpenPOI attribution/link and preserve full `licenses` / `attributions`; Apache-2.0 records also require the Foursquare NOTICE in developer docs.
- Provider timeout and cache timeout must be observable but must not add a new user interaction or prevent the existing fallback.
