# Geocoder provider benchmark evidence

Status: `partial` — deterministic contract and fail-closed runner proved; live provider rows were not attempted because this worktree has no approved Google/Geoapify credential or self-host endpoint.

## Scope

- Fixture: `apps/life-manager/fixtures/provider-benchmarks/japan-geocoder-cases.json`
- Runner: `apps/life-manager/scripts/provider-benchmark-geocoder.js`
- Release SHA: `unreleased` (read-only benchmark from the source worktree)
- Observation clock: `2026-10-03T00:00:00.000Z`
- Case/provider rows: `30`
- Digest: `8156a9373f58db2ff05f3ebd6c1d49a2f726389b878c49a579e26ea18802e9bc`

## Read-only result

All 30 rows are `unavailable/provider_not_configured` for the three configured candidates (`google-geocoding`, `geoapify-free`, `selfhost-photon`). No network call was made, no credential was read into output, and the winner is correctly `no_winner/provider_accuracy_or_coverage_below_threshold`. This is not evidence that any candidate is inaccurate; it is evidence that the runner refuses to promote an unconfigured candidate or a corpus without ground-truth coverage.

## Selection rules

A candidate can become `eligible_for_shadow` only when it returns a fresh coordinate, a non-empty attribution reference, a supported license reference, and a bounded observation. Missing attribution, unsupported license, timeout, quota, or no-result remains non-promotable.

## Source terms to verify during the live benchmark

- Google Maps Geocoding policies and pricing: <https://developers.google.com/maps/documentation/geocoding/policies>, <https://developers.google.com/maps/billing-and-pricing/pricing>
- Geoapify commercial free plan and attribution: <https://www.geoapify.com/pricing>, <https://www.geoapify.com/terms-and-conditions/>
- Photon self-host/API and OSM attribution: <https://github.com/komoot/photon>, <https://www.openstreetmap.org/copyright>

The production route remains on the existing cache/Google path until a live benchmark produces a source-backed winner and the seven-period CFO gate passes.
