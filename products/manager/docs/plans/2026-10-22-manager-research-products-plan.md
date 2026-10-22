# Manager Research Products and Website Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. This plan is a derived execution view, not a new task-status authority.

**Goal:** Convert source-grounded Manager research into bilingual public articles, durable book manuscripts, reusable presentation/carousel/manga scripts, and an accurate Anicca homepage without publishing unverified impact claims.

**Architecture:** One canonical research evidence package in `Daisuke134/life-manager`, transformed by the existing `products/manager/scripts/build_blog_publication.py` and publisher bridge. Reuse existing `apps/landing/marketing/pages/{en,ja}.html`; preserve current apps, payments, links, and all previous published articles. Scripts and Markdown are source products; rendered slides, manga and EPUB/PDF require their own artifact acceptance tests. Original Manager `tasks.json` stays authoritative.

**Tech Stack:** Existing Manager Python standard-library publication builder; existing Node static/Netlify site renderer and publisher; Playwright accessibility link checks; Markdown, JSON manifest; Quarto as the optional first-party book HTML/EPUB/PDF exporter after checked installation, not a replacement site. Latest public source evidence from Ampersand, Simile, Aaru, Andon Labs and research papers.

**Spec:** `../specs/2026-10-22-manager-validated-autonomy-design.md`.

## Global Constraints

- The user's latest request **does authorize publishing reviewed English/Japanese research articles and improving their owned site**. No future article should imply simulated welfare outcomes are field causal effects.
- Publisher/source separation: content in `life-manager`; dedicated bridge in `Daisuke134/anicca-products`; live source in `apps/landing/marketing/pages/`; do not install or overwrite the whole site blindly.
- Baseline publication package: at least 65 published Manager articles / 33 media in the earlier verified release. Preserve earlier package hashes, existing unrelated articles/assets, cross-language canonical links and sitemap; independently re-audit current production rather than assuming baselines unchanged.
- Existing `articles-2026-10-22.json` and `BLOG_PUBLICATION_PACKAGE_20261022.json` use a *frozen source revision*. Never silently repoint its source hashes or mutate an existing published article without an explicit revision and integrity checks.
- Never include API keys, private user conversations, human-identifiable case data, copyrighted third-party figures without license, unsupported literature claims or fake testimonials.
- Native slides, book or manga output is not complete when only a Markdown outline or instruction prompt exists. Preserve editorial acceptance and final artifact bytes separately.

## Review Focus

1. A PR merge is not proof that a URL is live and externally readable; require actual browser GET and asset hash.
2. Current Anicca EN/JA home source at `apps/landing/marketing/pages/en.html` / `ja.html` may differ from deployed Netlify bytes; never assert publication solely from edited source.
3. A research report's published quantitative metric must not be reworded as an independent field/welfare benchmark.
4. Removing or overwriting unrelated products, landing links, marketing tracks, paid content or prior media is prohibited.
5. Images, fonts and third-party material have distinct reuse rights; disclose conceptual/fictional illustrations.

## P01 — Freeze evidence and editorial source mapping

**Files:** Create `docs/content/manager-evidence-index-20261022.json`, `tests/test_content_evidence_index.py`; reference existing `docs/verification/ampersand-20261022` and `docs/research/ampersand-20261022`. **Interface:** `validate_article_claims(manifest: dict, evidence: dict) -> bool`. **Depends:** E01/E07.

- [ ] Step 1 RED: `test_fictional_claim_not_field_evidence` rejects a simulated 7/10 score labeled measured human benefit; `test_source_timestamp_and_rights` rejects URL-only attribution or prohibited figure reuse.
- [ ] Step 2 Run: `python -m unittest discover -s tests -p 'test_content_evidence_index.py' -v`; expect red on the missing evidence adapter.
- [ ] Step 3 Implement minimal evidence manifest with actual run IDs, fixed SHA, paper DOI/URL, status `PROVIDER_CLAIM|MOCK|SYNTHETIC_API|REAL_TECHNICAL|FIELD_OUTCOME|UNMEASURED`, date, rights and citations. No unobserved field data.
- [ ] Step 4 Run same tests expecting green; verify original raw 10-case artifact has not changed.
- [ ] Step 5 Commit evidence index without changing public site or task status.

## P02 — Prepare reviewed bilingual Ampersand article package

**Files:** Existing `docs/articles/manager-ampersand-ten-case-lab-{en,ja}.md`; create `publication/ampersand-ten-case-20261022.json`; test `tests/test_ampersand_article_package.py`. **Interface:** `validate_bilingual_pair(en_path, ja_path, evidence, slug_pair) -> Receipt`. **Depends:** P01.

- [ ] Step 1 RED: test that translated tables have the same ten case IDs, both quote 7/10, held-out 4/7 vs always-PASS 4/7, real calls 10, one follow-up, proof P0, human outcomes unknown, and distinguish the 600-character parser rejection.
- [ ] Step 2 Verify RED; missing pair manifest must fail.
- [ ] Step 3 Review text against raw artifact and primary sources, add source SHA+rights, working canonical slug pair and revision metadata; preserve the original unfavorable failures.
- [ ] Step 4 GREEN bilingual content test, official-source outgoing links, no credential scan, reading order/accessibility structure.
- [ ] Step 5 Commit reviewed manuscripts and explicit release intent; do not invent publication receipts.

## P03 — Publish only additive articles through the existing installer

**Files:** Update/additive entry to `products/manager/publication/articles-2026-10-22.json` using the builder's documented mode; `docs/research/manager/publication/2026-10-19/`; `docs/verification/BLOG_PUBLICATION_PACKAGE_20261022.json`; referenced `anicca-products` bridge workflows; existing blog installer. **Depends:** P02.

- [ ] Step 1 RED: a package canary rejects a changed legacy SHA, non-registered slug, missing media, broken canonical or an untrusted source revision.
- [ ] Step 2 Run builder in `--check` mode first (read the actual `--help`); verify any intentional new entries fail until built.
- [ ] Step 3 Build append-only package with two new EN/JA slugs; fix source-revision pins and manifest using existing checks. Produce a reviewable PR, run pre-production canary.
- [ ] Step 4 GREEN current blog Node/CI tests + Netlify build and manual article canary; then independently GET both live article URLs, content/canonical/hreflang, sitemap/collection and hash every old/new media path. Preserve all previous pages.
- [ ] Step 5 Commit publisher receipt with actual deployed SHA, run ID, URLs and UTC GET verification; task not complete if PR merely exists.

## P04 — Update accurate EN/JA Anicca homepage and metadata

**Files:** Existing `apps/landing/marketing/pages/en.html`, `ja.html`, homepage accessibility/SEO tests; test `apps/landing/marketing/tests/manager-progress.test.mjs` or the actual sibling location after inspection. **Depends:** P01; editorial review can run in parallel with P03.

- [ ] Step 1 RED: tests require a visible `Manager · Research in progress` evidence section linked to the actual latest authenticated model experiment and its unresolved field-validation limitations; check EN/JA equivalence and existing products links.
- [ ] Step 2 Verify RED in current Node test harness.
- [ ] Step 3 Add concise copy explaining behavior simulation, autonomous owned-digital pilot, observational vs technical vs welfare proof. Link primary existing proof and article URLs. Update meta description/og descriptions without new unverifiable statistics or implying Ampersand sponsorship. Preserve existing artwork and other products.
- [ ] Step 4 GREEN Node/build plus Playwright desktop/mobile contrast, viewport, screen-reader labels, broken links and meta/canonical/hreflang. Produce additive owned-site PR.
- [ ] Step 5 After reviewed site deployment, independently GET `https://aniccaai.com/en` and `/ja`; verify text, mobile, citation URLs and unrelated product navigation, then save before/after evidence and exact deployment receipt. Source edit alone is not done.

## P05 — Behavior Simulation & Intervention book chapters, index, EPUB

**Files:** Extend current `docs/research/ampersand-20261022/BOOK_CHAPTER_DEEP_DIVE_{EN,JA}.md`; create `docs/books/behavior-simulation-intervention/{index.qmd,_quarto.yml,chapters/,references.bib}`; tests `tests/test_book_evidence.py`. **Depends:** P01; can run in parallel with P03.

- [ ] Step 1 RED: bibliography test fails on absent 5-part learning ladder (probability→simulation→intervention→causal validation→operational safety), unsupported citations, unlabeled fictional results, and an unregistered rights-protected figure.
- [ ] Step 2 Verify RED and freeze a chapter manifest (intro; behavioral forecasting; population synthesis; Persimmon/Ampersand; off-policy/CORO; interventions; causal inference and spillover; calibration and sim-to-real; field failures; Manager implementation; governance; glossary; reproducibility).
- [ ] Step 3 Author chapter-by-chapter from verified source cards with paired Japanese/English glossary. The one canonical source drives HTML/EPUB (and PDF if the required rendering environment exists). Pin Quarto only after official binary version/permission check; fall back to vetted Markdown manuscripts without falsely claiming EPUB produced.
- [ ] Step 4 GREEN: `quarto render docs/books/behavior-simulation-intervention --to html` and `--to epub` after installation; inspect rendered footnotes, tables, accessible images and actual EPUB contents. PDF optional, require actual PDF byte/render check.
- [ ] Step 5 Commit source, bibliography, checksum manifest and output paths; publishing a commercial book or setting a price requires a separate storefront and distribution approval.

## P06 — Reusable presentation, carousel and manga teaching sources

**Files:** Create `docs/content/behavior-agi-20261022/storyboard.json`; reuse `docs/presentations/`, existing asset/citation registry; add `tests/test_content_derivatives.py`. **Depends:** P01,P05 chapter-level facts.

- [ ] Step 1 RED: each visual panel/page must reference an existing evidence ID and have reading-order, JP/EN copy, alt-text, rights and a defined audience/canvas size; reject invented company affiliation or claimed real experimental photos.
- [ ] Step 2 Run failing test, then build 3 reusable storyboards: 12-slide technical talk, 8-panel 1:1 or 4:5 carousel, and 6-page educational manga script (characters explicitly fictional).
- [ ] Step 3 Reuse existing renderer and writing/layout assets first. Export concrete PPTX/PDF or PNG/WEBP using the appropriate existing pipeline; image-generation may support only expressly requested visuals and must be labeled conceptual. No fonts redistributed.
- [ ] Step 4 GREEN: automatically check panel count, proof/citation coverage, exact text, links, safe margins, readable font and visual render. Manually inspect exports. Manuscript/script alone is NOT a finished deck or comic.
- [ ] Step 5 Commit source storyboards, exported asset hashes and tests. Public distribution requires channel-specific review and actual permalink/readback.

## P07 — Editor and release ledger, durable cycle

**Files:** Add to existing evidence-ledger/report registry without a second SSOT; `docs/content/publication-ledger.json` as **publication receipts only**, not Manager task status; test `tests/test_publication_receipts.py`. **Depends:** P03–P06.

- [ ] Step 1 RED: article drafts cannot be treated as published; changed URLs must preserve historical version and correction; missing external live GET must block publication status.
- [ ] Step 2 Run RED, add schema with source SHA, package SHA, translation version, revision summary, publication timestamp, external readback, error/withdrawal state and prior version.
- [ ] Step 3 Connect existing release verification to this receipt, never directly to the model's judgment or reviewer score; preserve legacy 65/33 baseline as historical counts pending a new full live census.
- [ ] Step 4 GREEN reverify bilingual articles, homepage, media checksums and exported document formats. Record unknown when checks fail.
- [ ] Step 5 Commit actual audited receipts and open a clean PR; no unreviewed cross-product auto-publisher.

## Execution order and stop rules

P01 → P02 → P03; P04 after P01; P05 after P01, P06 after P05; P07 after P03/P04/P06. This runs alongside the core E tasks without mutating shared task statuses or product runtime. The technical blog and homepage may publish independently of original field-dependent `C002/Y008`; **do not mark those original tasks done** unless their original dependency+acceptance have genuinely occurred. Save favorable, negative and null outcomes with identical editorial discipline.
