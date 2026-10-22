# Approved Manager marketing pages

Production candidates based on the English-first design explicitly accepted on 2026-10-18. **Not deployed. This is a route package, not a complete site export.**

`route-manifest.json` defines six page candidates, the target routes/export paths and SHA256 hashes. English is primary at `/en`, `/dais`, `/lm`; Japanese at `/ja`, `/dais/ja`, `/lm/ja`. The existing `/`→`/en` behavior belongs to the full site's routing and is preserved. `pages/` contains ordinary HTML, with working locale links, canonical/hreflang/description/Open Graph metadata. The Calendar onboarding link continues to the existing Railway web application; callbacks and billing are not reimplemented.

Do not deploy this directory as the whole website: it would omit the other products, blog, legal pages, assets and serverless functions. Integrate the allowlisted candidates into the existing full static export only after its baseline/source identity and Netlify deployment authority are confirmed. All unrelated files and Netlify redirects/functions must be retained. The existing deployment workflow's Calendar/Stripe money-path smoke must be reconciled with the new broad marketing copy while preserving actual onboarding/billing, rather than bypassed or silently removed.

The full existing site was inspected read-only at `Daisuke134/anicca-products@64ae00d6fedc53206251d3e2426023c2633f8d68`. Its successful deploy run is https://github.com/Daisuke134/anicca-products/actions/runs/39123914425 . This identifies the build source/run, not an authenticated Netlify published-SHA readback.

Current environment: GitHub source/read access works; Actions management/Secrets API calls return HTTP 403. No NETLIFY_AUTH_TOKEN/NETLIFY_SITE_ID binding, Netlify CLI profile or registered owner browser exists here. Consequently provider deployment, production-site migration and live final readback remain unperformed. Do not create another Sites project or change DNS as a substitute for updating the existing domain.

Current order/state: repository's unified SSOT. Implementation outline: `docs/superpowers/plans/2026-10-18-manager-website-production.md`.


## Public founder profile and resume

The public-only factual input is `content/founder.json`. It generates `/about`,
`/about/ja`, and `/cv.pdf` through `python scripts/render-founder.py` (Python 3,
ReportLab, and Liberation Sans fonts at `/usr/share/fonts/truetype/liberation` on Linux). These are separate from employer-specific
application resumes; never copy personal phone numbers, private email addresses,
addresses, application answers, confidential customer details, or credentials here.

For an authorized update, reconcile the latest verified accomplishments with their
public evidence and preserve qualifications and unresolved outcomes. Update both
language entries, regenerate the HTML and PDF, visually inspect the PDF, then run
`node --test tests/*.test.mjs`. The renderer refreshes all route-manifest hashes.
The PDF is deterministic for the same factual input and renderer dependencies.
Do not use a new scheduler: maintain these artifacts in the existing reviewed
website/content-update workflow. Changing a resume or profile does not authorize
contacting employers or sending applications.

The immutable overlay must verify the profile pages and PDF before writing any
marketing output. Preserve the full site's product routes, articles, legal pages,
Netlify functions, and money-path smoke/rollback. Publish only a reviewed immutable
source revision through the existing publisher; coordinate its release lease and
retain the current blog renderer/content pins. Inspect desktop/mobile preview,
PDF links and public-only contact, then verify live routes and release identity.
