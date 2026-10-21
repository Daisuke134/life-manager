# Manager Research Journal — Original editorial system inspired by Simile/Aaru

**Date:** 2026-10-21. **Product boundary:** This is a design/UX specification and content model **ONLY**. **No production deployment** or change to `aniccaai.com` was performed. Current owner-managed publishing site remains unaffected. Site clone/copyrighted image/branding copying is forbidden.

## 1. Actual current UI audit — do not start another competing blog

Inspected October 21, 2026:
- Existing [Anicca Manager research home](https://aniccaai.com/blog/manager) already hosts many English and Japanese Manager articles, including prior original pieces on Simile, Aaru, simulation fundamentals and behavioral causality. The page is mainly long grouped English/Japanese link lists, without strong cover-art prioritization or a methods/figures index.
- Existing [Anicca global blog](https://aniccaai.com/blog) is a broad app/product/content hub with high-volume mixed-purpose articles, guides, research and tool content. Overwriting that global surface to make it a research-only journal would harm existing unrelated publication workflows.
- Reference [Simile blog](https://www.simile.com/blog) uses large illustrative cards, clear editorial title, author/date/read time and company research sections; individual posts open with conceptual narrative, a strong diagram, then methodology and limitations.
- Reference [Aaru publications](https://aaru.com/publications) has focused study pages and both executive summary and detailed full methodological version. Its research article uses an opening summary of labeled metrics and linked reproducibility/assumptions.

**Decision:** Improve the canonical `/blog/manager` route as a new original research journal experience. Retain all existing URLs/links/SEO and English/Japanese articles. Do not copy Simile/Aaru website design code, typographic assets or proprietary figures. Adapt the *scientific storytelling pattern*, not their artwork or identity.

## 2. The distinctive Anicca research identity

Brand thesis: **End suffering — observe carefully, intervene legitimately, prove what changed.** Not a wellness app catalog and not a prediction marketplace.

Mood: calm evidence lab, warm humanistic editorial, clear scientific method. Visual patterns follow observed world-state → competing hypotheses → NO_ACTION → action receipt → independently observed change → causal evaluation. Each stage has a citation and confidence level; zero fictional victim or participant portraits.

### Original design system proposal (not a copied UI)
- Canvas: warm ivory `#FAF8F3`, white `#FFFFFF` paper, ink `#1A2429`, secondary slate `#52636D`; deep pine `#164A42` for links/action, muted vermilion `#B45032` for negative evidence/critical comparisons. Check all foreground/background combinations for at least WCAG AA contrast; numbers need independent shape/text signals.
- Typography: editorial serif system font for a limited number of large headings, UI system sans for readable body; no downloading or redistributing paid third-party fonts. Long-form body 17–19px, max 68–76 characters/line, line-height ~1.65. Code blocks monospace with horizontal scrolling.
- Layout: 12-column responsive grid; overall content max 1200px; long article column max 760px, optional desktop context rail max 260px, mobile single column.
- Photography/figures: first-party explanatory diagrams and code-generated aggregate figures, not stock AI avatars. Each diagram supports alt text, signed/source-linked data, accessible tables and dark-mode adaptation.
- Each numeric KPI accompanied by definition + denominator + as-of + provenance; avoid giant hero claims with hidden qualifiers.

## 3. Page architecture

```text
/  Anicca mission homepage  [keep existing]
/blog                    product/global blog  [keep existing]
/blog/manager            Manager Research Journal (new layout, SAME canonical route)
  ├── Hero: "Observe. Intervene. Prove." + what is / isn't yet verified
  ├── Featured research: 1 editorial cover, 3 recent deep studies
  ├── Browse by topic: Behavior / Causality / Autonomy / UBI / Real-world evidence
  ├── Research Explorer: clickable Evidence Cards and source-rights registry
  ├── Build Log: status of Manager Phase00-06 from canonical tasks.json
  ├── Reproduce: minimal documented runnable code, environment, license
  ├── Reading Paths: novice/intermediate/researcher
  └── Archive: existing EN/JA posts, sorted by original date without link loss
/blog/manager/<canonical-existing-slug> = old URLs preserved, new article template applied
```

The actual application code for the global site may be owned by a separate product/release plane. Before any deployment, inspect the exact route owner, existing static/SSR template, content ingestion pipeline, CDN, publishing bridge, tracking, accessibility and release/readback. This document does not authorize bypassing another project's production release ownership.

## 4. Editorial article template — every scientific claim is inspectable

1. **Human question / real-world stakes:** accessible, no fabricated beneficiary stories or causal claims.
2. **One-sentence result:** what was actually tested and its evidence level; not a vendor slogan.
3. **Original hero diagram:** short alt text and SVG/PNG source in Manager GitHub; no unauthorized brand marks.
4. **Methods at a glance:** time, units, outcome, comparator, population, sample size and license.
5. **Evidence ledger:** source URL, publication date, first-source vs vendor, model/data version, exact code, limitations.
6. **Prediction vs treatment vs world-state:** three independent horizontal plots where possible; missing stays UNKNOWN.
7. **Reproduction:** commit SHA, pinned dependencies, exact command, dataset rights, CI URL, negative and failed tests.
8. **Limitations and objections:** competing mechanisms, out-of-distribution, confounding, privacy and economic displaced value.
9. **Related field research** + next experiment and valid NO_ACTION.
10. **Corrections/version history:** readers can challenge a source or result, with original response and updates visible.

Readability affordances: sticky mini table of contents, footnotes/hover citations, in-content high-contrast diagrams, one-tap figure data table, visible confidence, short research abstract and companion full methods appendix.

## 5. Wireframe (content-first, not a rendered screenshot)

```text
┌────────────────────────────────────────────────────────────────────┐
│ ANICCA / MANAGER RESEARCH       Research   Methods   Evidence   Code│
│                                                                    │
│ Observe. Intervene. Prove.                                        │
│ An independent research journal on AI & real-world welfare.        │
│ Current scientific status: Gate1 UNMET / field benefit NOT_MEASURED│
├────────────────────────────────────────────────────────────────────┤
│ FEATURED RESEARCH                              LATEST FROM THE LAB  │
│ Why Prediction Is Not Intervention              How to verify...  │
│ [original data/causal contrast figure]           Tinker and Qwen...│
│ 2026-10-21 · Methods · P0 (literature/research)  Crypto UBI ≠ cash│
├────────────────────────────────────────────────────────────────────┤
│ [Behavior] [Causal Inference] [Interventions] [Open Models] [UBI]   │
│                                                                    │
│ REPRODUCIBLE NOTEBOOKS   INDEPENDENT EXTERNAL DATA   LIMITATIONS  │
│ [original plot]            [source locator]         [UNKNOWN]      │
├────────────────────────────────────────────────────────────────────┤
│ Browse full EN/JA Manager archive (existing permanent URLs)       │
└────────────────────────────────────────────────────────────────────┘
```

On individual article: meaningful data-linked cover; date/version/author; abstract; main text width max ~70ch; source-linked evidence levels; expandable methods and negative results; previous study / next study; contents rail on desktop.

## 6. Content schema and rebuild guarantees

Required metadata on any *new* Manager journal post:
```json
{
  "id": "manager-evidence-2026-10-21",
  "canonical_url": "/blog/manager/example-slug",
  "title": "Original research title",
  "subtitle": "What changed and what was actually observed",
  "language": "en",
  "published_at": null,
  "updated_at": "2026-10-21",
  "authors": ["Anicca Research"],
  "category": "Causal Interventions",
  "method": "review / benchmark / prospective field / causal",
  "evidence_level": "P0",
  "source_manifest_path": "products/manager/docs/research/crossfield-20261021/SOURCES.json",
  "code_commit_sha": null,
  "external_ci_url": null,
  "data_license_status": "review_required",
  "beneficiary_outcome_status": "NOT_MEASURED",
  "limitations": ["No Manager-caused real-world intervention measured"],
  "review_status": "draft"
}
```
**Example schema above is illustrative only; the article has NOT been published.** A published timestamp requires the true public-URL readback. Post fields should derive from the existing Manager structured evidence/source registry rather than creating a second task SSOT.

- Stable slugs; 301 redirects only on intentional relocation, with legacy coverage tests.
- Every article has canonical metadata, OpenGraph text/image only if owned, RSS/sitemap and accessible semantic headings.
- EN/JA locale switch uses independently reviewed versions, not machine-generated "translations" pretending to be new research.
- Do not interleave app-store sales articles with scientific claims in the Manager journal; crosslink the top-level blog.
- User input/analytics privacy and CORS/security remain under site owner's existing contracts, no new person-level tracking.
- New "Result" widgets must ingest externally verifiable, versioned aggregate metrics with proof levels, not arbitrary text from an LLM.

## 7. Release/QA acceptance (NOT executed)

- Inspect actual production route sources and the canonical site repository owner's release policy; do not edit `apps/life-manager` runtime.
- Keep old Manager article URLs/metadata and global Anicca e-commerce/product SEO surfaces unchanged.
- New layout plus original SVG/chart assets pass desktop 1440px, tablet, mobile 375px visual checks, 200% zoom, keyboard and screen-reader review.
- Test every visible numerical claim against canonical source JSON and true CI or externally observable evidence.
- Verify no source licenses or copyrighted UI/art have been copied and no fabricated P1/P2/P3/P4 field claims.
- Safe preview/staging deploy, review gate, immutable release, valid public readback and rollback before any production publish.
- **No production deployment, no new site and no live design mutation were performed in this research turn.**

## Reference pages (visual narrative, not designs to replicate pixel-for-pixel)
- [Simile research blog](https://www.simile.com/blog) / [its confidence methodology](https://www.simile.com/blog/confidence)
- [Aaru publications](https://aaru.com/publications) / [methodology and responsive graphics](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)
- [Current Anicca Manager journal](https://aniccaai.com/blog/manager) / [broader blog](https://aniccaai.com/blog)
