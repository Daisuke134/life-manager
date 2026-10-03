# Routing provider benchmark evidence

Status: `partial` — bounded parser/contract and low-volume read-only probes completed; OTP and Valhalla have no configured endpoint/feed, and Tokyo Transit timed out once. No production scheduler, browser, or provider state was changed.

## Scope

- Fixture: `apps/life-manager/fixtures/provider-benchmarks/japan-route-cases.json`
- Runner: `apps/life-manager/scripts/provider-benchmark-routing.js`
- Release SHA: `unreleased` (read-only benchmark from the source worktree)
- Public read-only probes: Transit API and one OSRM demo driving request
- Digest: `3546c343f14a34fbf3fed4c37b20d6727b0e13f8a9eadaba99efbc1102a4f8`
- Rows: `16`; fresh `2`; timeout `1`; unsupported `8`; unavailable/provider-not-configured `4`; other network/error `1`

## Observed rows

- Transit API: Kyoto transit returned `fresh`, 2,709 seconds, one leg, no fare field. Tokyo transit timed out at the bounded probe deadline. Non-Japan Transit was not requested and is `provider_not_configured`.
- OSRM public demo: one Shibuya driving route returned `fresh`, 468 seconds, one leg. This is a documented low-volume read-only probe, not a production dependency or an SLA claim.
- OpenTripPlanner: no endpoint/feed configured; rows remain `provider_not_configured`.
- Valhalla: no endpoint configured; rows remain `provider_not_configured`.

## Source terms

- Transit is free/read-only/no-auth but unofficial and no-SLA: <https://transit.ls8h.com/terms>
- OSRM engine and demo/API documentation: <https://github.com/Project-OSRM/osrm-backend>, <https://project-osrm.org/>
- OpenTripPlanner requires maintained OSM/GTFS feeds: <https://www.opentripplanner.org/>
- Valhalla self-hosting/license/data requirements: <https://github.com/valhalla/valhalla>

No candidate is promoted by this artifact. Production remains Transit-first for Japan with bounded Google fallback; OSRM/Valhalla/OTP require additional feed freshness, accuracy, resource-cost, and seven-period evidence.
