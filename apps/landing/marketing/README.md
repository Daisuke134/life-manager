# Approved Manager marketing pages

Production candidates based on the English-first design explicitly accepted on 2026-10-18. **This is a route package, not a complete site export.**

Production readback on 2026-10-25: `https://aniccaai.com/lm` returned HTTP 200 with SHA256 `d49deb6f996ea8aea648419abe09ec20ea96e60f9206c29ef7f492b8666babb2`, exactly matching the immutable overlay revision `bd8cc9703ac513bbdded7639cc51f7dacb4df29f` and `life-manager` main at `1e8fdd9e09dc369c25a2f27fb818058ee82eb959`. The serving workflow is `Daisuke134/anicca-products/.github/workflows/netlify-deploy.yml`: it pins `MANAGER_MARKETING_REVISION`, stages this overlay, builds the full landing site, deploys to Netlify, and runs the money-path smoke/rollback. The updated candidate in PR #8934 has a different SHA and is not live yet. The public `/route-manifest.json` returned HTTP 404.

`route-manifest.json` defines six page candidates, the target routes/export paths and SHA256 hashes. English is primary at `/en`, `/dais`, `/lm`; Japanese at `/ja`, `/dais/ja`, `/lm/ja`. The existing `/`→`/en` behavior belongs to the full site's routing and is preserved. `pages/` contains ordinary HTML, with working locale links, canonical/hreflang/description/Open Graph metadata. The Calendar onboarding link continues to the existing Railway web application; callbacks and billing are not reimplemented.

Do not deploy this directory as the whole website: it would omit the other products, blog, legal pages, assets and serverless functions. Publish reviewed candidates through the existing immutable overlay pin in `anicca-products/.github/workflows/netlify-deploy.yml`, retaining all unrelated routes, Netlify redirects/functions, the Calendar/Stripe onboarding/billing, and the money-path smoke/rollback. Verify the live `/lm` response after the workflow completes.

The existing full site and production path were inspected read-only in `Daisuke134/anicca-products`. Its main-branch deploy workflow identifies the source/build/publish sequence, and the public response hash matches the workflow's pinned overlay. A direct Netlify deploy-ID/API readback was not available in this session.

Current environment: GitHub source and PR write access works; no direct Netlify administration surface is available. This does not block publishing: update the workflow's immutable overlay revision through the existing GitHub deployment path, then verify the public response. Do not create another Sites project or change DNS as a substitute for updating the existing domain.

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
