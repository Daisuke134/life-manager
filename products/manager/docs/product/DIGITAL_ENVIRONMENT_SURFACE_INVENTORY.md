# Verified owner-controlled digital release surface

2026-10-21. Reuse existing infrastructure; do not request an NPO's funds or indoor room. This is a bounded research release, not a new generalized money or medical agent.

## Observed existing surface

- Source: Daisuke134/life-manager, Manager-only research branch. Canonical source path products/manager.
- Public hosting: existing gh-pages branch, observed HEAD db229a38ba2374c4b67517b2d61e46282c46cd91. Existing root index.html, articles/ and .nojekyll are not Manager-owned change targets and must remain byte-identical.
- Existing deploy workflow: .github/workflows/pages.yml on gh-pages, uses GitHub official upload-pages-artifact and deploy-pages actions.
- Proposed additive release prefix: **manager-support/** only. Exactly index.html, finance.html, mental.html, physical.html, control.html, proof.html and manifest.json. No external/private asset writes.
- Intended public URL: https://daisuke134.github.io/life-manager/manager-support/. This URL is NOT declared live until real HTTP readback succeeds.

## Standing release scope

User has requested implementation and real internet publication on owned resources. The source PR/CI must be green; deterministic source-catalog and content tests enforce allowed official outbound destinations. A repository-scoped short-lived GitHub Actions token is allowed only in the separate release job. It is not exposed to a generative model or public browser code. No clinical study, financial transfer, form filling or personal-data collection is authorized. No per-run human approval needed for this static, allowlisted release path.

Every release uses existing GitHub Pages infrastructure. No administrative bypass, no environment setting mutation, no main or Life Manager runtime change, no forced branch push. If branch protection or environment policy refuses a release, report refusal; do not bypass it. Never alter global settings or delete an unrelated existing public artifact.

## Admission and safety

1. All source unit and real-browser accessibility checks pass.
2. Official source link audit yields four authenticated HTTPS 200 readbacks with exact expected identities; UNKNOWN blocks release.
3. Manifest matches all six tested HTML files. Any symlink, new file or altered hash blocks.
4. Add only the seven allowlisted names under manager-support. Git diff outside this path blocks.
5. Commit references immutable tested source commit. No force; concurrent branch advances fail rather than overwrite.
6. Existing GitHub Pages deploy service owns global release, with existing environment controls.
7. Independently GET all six live pages, compare hashes; stale/missing/redirected responses are UNKNOWN, not success.
8. Duplicate same-source release has no new commit. Rollback restores only this prefix from a known verified prior release, and must itself be read back.

This CI release adapter is separate from the Phase05 offline fixture kernel. Its successful operation alone is not proof that the generative Manager kernel can safely perform arbitrary autonomous interventions. Human financial/mental/physical benefits remain NOT_MEASURED.

Primary reused documentation: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages and https://playwright.dev/docs/accessibility-testing.
