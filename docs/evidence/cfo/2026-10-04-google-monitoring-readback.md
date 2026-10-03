# Google Cloud Monitoring readback — 2026-10-04

Status: `partial/estimated`; this is project-level request telemetry, not a settled Cloud Billing charge.

## Read-only source and window

- Read at approximately 2026-10-04 08:12 JST through the official Cloud Monitoring REST `projects.metricDescriptors.list` and `projects.timeSeries.list` APIs.
- Project scope: `anicca-461216` only.
- Window: 2026-10-01 00:00 JST (`2026-09-30T15:00:00Z`) through 2026-10-04 08:12 JST (`2026-10-03T23:12:58Z`).
- Metric: `serviceruntime.googleapis.com/api/request_count` (`DELTA`, `INT64`), grouped by service, method, HTTP response code, and response class.
- Google returned no active Monitoring descriptors with the `generativelanguage.googleapis.com/` prefix for this project. Gemini usage is therefore not refreshed by this query.

## Project-level Maps/API requests

| service / method | response | count |
|---|---:|---:|
| Directions backend / `google.routes.Directions.Http` | 404 | 804 |
| Places backend / `google.places.TextSearch.Http` | 200 | 372 |
| Places backend / `google.places.TextSearch.Http` | 404 | 1 |
| Geocoding backend / `google.places.Geocoding.Http` | 200 | 155 |
| Places backend / `google.places.Details.Http` | 200 | 15 |

These counts are not joined to tenant, user, loop, or individual request events. A separate Maps metric family (`maps.googleapis.com/service/request_count_by_domain`) returned 1,160 aggregate requests (515 2xx, 645 4xx), which does not reconcile with the 1,345 service/method counts above; the two metric families are kept separate rather than added together.

## Cost interpretation

- September settled Cost Table effective averages were approximately JPY 1.604 per Places Text Search request, JPY 0.386 per Geocoding request, and JPY 0.232 per Directions request.
- Applying those historical blended averages to only known successful Text Search and Geocoding requests gives an illustrative pre-tax subtotal of about JPY 657, excluding the 15 Details requests.
- If all 4xx requests were also billed at the same historical averages, the corresponding illustrative subtotal would be about JPY 845 pre-tax, still excluding Details. Whether these 4xx attempts are billed is not proven by Monitoring.
- These are request-count scenarios, not an October invoice, per-SKU reconciliation, or current total Google spend. Free caps, credits, volume tiers, SKU differences, other projects, Gemini usage, and source attribution are not covered. The earlier JPY 984 MTD / JPY 9,800–10,200 pace estimate is not reused as a current total after this newer partial readback.

No credential, bearer token, raw request, or bank information is stored in this evidence.
