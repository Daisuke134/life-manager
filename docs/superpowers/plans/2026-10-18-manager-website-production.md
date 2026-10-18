# Approved Manager website production integration

> Execution: inline. The user reviewed the English screenshots and explicitly authorized production publication twice. Do not ask for the same approval again.

Goal: publish the approved English/Japanese home, unified My products and Life Manager pages on the existing aniccaai.com hosting identity, preserving other products and onboarding.

Design: docs/design/2026-10-18-products-and-story-preview/README.md and its six reviewed HTML pages. Source authority: this Life Manager repository. Existing unrelated marketing site remains an immutable baseline input until its source/deployment migration is resolved; never edit a second source checkout.

1. Confirm existing production route/build/hosting ownership, read-only. Capture the baseline commit, published run and routing contracts. Do not start a second Site or replace the whole site with six files.
2. Prepare six production HTML pages and the stylesheet under apps/landing/marketing. Remove draft/noindex markings, convert locale/internal links to live routes, set metadata/canonical/hreflang, preserve the Cloud Calendar entry point as well as the approved primary CTAs. Verify all six local pages, mobile layout and links; retain a manifest with hashes.
3. Connect the existing Netlify authority. Integrate only the allowlisted routes into a full existing export, keeping all other pages/assets/functions/redirects. Adapt the old money-path smoke only after preserving its real onboarding/billing contract; do not silently disable it. Build/test the composite site, publish through the normal PR/merge pipeline and verify the actual production routes and deployment SHA. If provider credentials or source migration are unavailable, save the concrete package and report that publication remains blocked.

Checks: no preview/noindex or local .html links on public pages; EN/JA pairs; product directory includes Life Manager without a separate apps group; founder story and established neurofeedback terminology preserved; no unsupported profits/clinical claims; unrelated functions/onboarding/callbacks and routes preserved. Full-site build and official provider readback are required to claim production completion.

Current ordering/state is recorded only in the unified SSOT.
