# Approved Manager marketing pages

Marketing routes based on the English-first design explicitly accepted on 2026-10-18. **This is a route package, not a complete site export.** Publication state and receipts belong to the unified SSOT.

`route-manifest.json` defines six pages, an English root alias, two assets, the target routes/export paths and SHA256 hashes. English is primary at `/en`, `/dais`, `/lm`; Japanese at `/ja`, `/dais/ja`, `/lm/ja`. The root serves the English HTML with `/en` as its canonical URL. Retired RSC payloads are removed only for overlaid routes so legacy Next client links fall back to full-page navigation. `pages/` contains ordinary HTML, with working locale links, canonical/hreflang/description/Open Graph metadata. The Calendar onboarding link continues to the existing Railway web application; callbacks and billing are not reimplemented.

Do not deploy this directory as the whole website: it would omit the other products, blog, legal pages, assets and serverless functions. Integrate the allowlisted candidates into the existing full static export only after its baseline/source identity and Netlify deployment authority are confirmed. All unrelated files and Netlify redirects/functions must be retained. The existing deployment workflow's Calendar/Stripe money-path smoke must be reconciled with the new broad marketing copy while preserving actual onboarding/billing, rather than bypassed or silently removed.

The full existing site was inspected read-only at `Daisuke134/anicca-products@64ae00d6fedc53206251d3e2426023c2633f8d68`. Its successful deploy run is https://github.com/Daisuke134/anicca-products/actions/runs/39123914425 . This identifies the build source/run, not an authenticated Netlify published-SHA readback.

Deployment uses the existing `Daisuke134/anicca-products` GitHub Actions → Netlify route. Provider secrets stay inside that existing workflow; local Netlify credentials are unnecessary. The workflow fetches the canonical adapter by immutable SHA, verifies its SHA256 and route manifest, then overlays only allowlisted output after the full existing build. Keep the money-path smoke and rollback active. No new Sites project, duplicate product implementation or DNS change is required.

Current order/state: repository's unified SSOT. Implementation outline: `docs/superpowers/plans/2026-10-18-manager-website-production.md`.
