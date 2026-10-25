# Approved Manager marketing pages

Production candidates based on the English-first design explicitly accepted on 2026-10-18. **This is a route package, not a complete site export.**

Production readback on 2026-10-25: `https://aniccaai.com/lm` returned HTTP 200 through Netlify, and its response SHA256 (`d49deb6f996ea8aea648419abe09ec20ea96e60f9206c29ef7f492b8666babb2`) matched `pages/life-manager-en.html` at `origin/main` `ca87ec5f5`. This confirms the live page bytes at that time; it does not identify the full site's build repository or prove that a commit to this repository triggers a Netlify deploy. The public `/route-manifest.json` returned HTTP 404.

`route-manifest.json` defines six page candidates, the target routes/export paths and SHA256 hashes. English is primary at `/en`, `/dais`, `/lm`; Japanese at `/ja`, `/dais/ja`, `/lm/ja`. The existing `/`→`/en` behavior belongs to the full site's routing and is preserved. `pages/` contains ordinary HTML, with working locale links, canonical/hreflang/description/Open Graph metadata. The Calendar onboarding link continues to the existing Railway web application; callbacks and billing are not reimplemented.

Do not deploy this directory as the whole website: it would omit the other products, blog, legal pages, assets and serverless functions. Integrate the allowlisted candidates into the existing full static export only after its baseline/source identity and Netlify deployment authority are confirmed. All unrelated files and Netlify redirects/functions must be retained. The existing deployment workflow's Calendar/Stripe money-path smoke must be reconciled with the new broad marketing copy while preserving actual onboarding/billing, rather than bypassed or silently removed.

The full existing site was inspected read-only at `Daisuke134/anicca-products@64ae00d6fedc53206251d3e2426023c2633f8d68`. Its successful deploy run is https://github.com/Daisuke134/anicca-products/actions/runs/39123914425 . This identifies the build source/run, not an authenticated Netlify published-SHA readback.

Current environment: GitHub source/read access works; Actions management/Secrets API calls return HTTP 403. No Netlify management tool, `NETLIFY_AUTH_TOKEN`/`NETLIFY_SITE_ID` binding, Netlify CLI profile or registered owner browser is available here. Consequently the deployment source identity, an automatic deploy from this repository, production-site migration and post-change production readback remain unverified. Do not create another Sites project or change DNS as a substitute for updating the existing domain.

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

Track-record preservation: before updating, compare each accomplishment and link
against the prior verified resume. Keep concrete delivery scope, contribution,
conference representation, product launches and measured results. Do not replace
these with generic job descriptions or remove them merely to fit one page. The
public CV may span multiple pages. Preserve historical periods and attribution;
conference attendance/reporting is not paper acceptance, team delivery is not
sole authorship, and historical revenue is not recurring revenue or profit.
