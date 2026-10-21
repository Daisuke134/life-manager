# Manager article publication package — October 22, 2026

## Prepared result and current public state

The existing canonical package now contains **63 articles and the same 29 media files**: 54 legacy articles plus nine standalone Manager English manuscripts. This document records source preparation and a local import dry run. **It is not a production publication receipt.**

Independent unauthenticated public GETs during this session found:

- `https://aniccaai.com/blog/manager/release.json`: HTTP 200; source revision `6ec72c658ee993cd4292548b4f8668b3fca3181d`, 56 articles and 29 media.
- The deployed 56 are the 54 legacy articles plus `manager-evidence-cards-r007-r008-en` and `manager-population-behavior-causality-field-guide-en`. Both article bodies and canonical metadata returned HTTP 200.
- The great-management, prediction/intervention, Radiant and autonomous-wealth article URLs returned HTTP 404. Their source files alone did not constitute publication.
- Latest inspected successful landing deployment: [Anicca Products run 39618733450](https://github.com/Daisuke134/anicca-products/actions/runs/39618733450), publishing commit `9775280ba200cc6f8651ceaabe127f1390a90123`.
- The separate [Manager support service](https://daisuke134.github.io/life-manager/manager-support/) returned HTTP 200. Its manifest was source `ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5`, zero real participants, experiment disabled and beneficiary outcome `NOT_MEASURED`. Its [verify/publish/live-readback run 39632331532](https://github.com/Daisuke134/life-manager/actions/runs/39632331532) succeeded. That service is not the blog publishing target.

Firecrawl's exposed scrape connector returned `Unknown tool`; the web reader could not access these pages. The live results above came from direct bounded public HTTP GETs using Python's configured transport. No credentials or authenticated sessions were used.

## Canonical sources and generated artifacts

The editorial inventory is `products/manager/publication/articles-2026-10-22.json`. It pins each original source's SHA-256 and immutable source commit `ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5`. The generated hash/URL mapping is `products/manager/docs/verification/BLOG_PUBLICATION_PACKAGE_20261022.json`.

The generator is `products/manager/scripts/build_blog_publication.py`. It writes only the existing `docs/research/manager/publication/2026-10-19/manifest.json`, nine additional files under its `en/` directory, and the package verification JSON. The existing importer and renderer are unchanged. Its public URL convention remains `https://aniccaai.com/blog/<slug>`.

| Slug | Original source under `products/manager/docs/` | Editorial role |
|---|---|---|
| `manager-evidence-cards-r007-r008-en` | `articles/manager-evidence-cards-r007-r008-en.md` | Already public; retain exact bytes |
| `manager-population-behavior-causality-field-guide-en` | `articles/manager-population-behavior-causality-field-guide-en.md` | Already public; retain exact bytes |
| `manager-great-management-evidence-first-en` | `articles/manager-great-management-evidence-first-en.md` | Evidence and management research |
| `manager-prediction-intervention-blessing-en` | `articles/manager-prediction-intervention-blessing-en.md` | Prediction, intervention and causal benefit |
| `manager-radiant-societies-field-guide-en` | `articles/manager-radiant-societies-field-guide-en.md` | Radiant methods and limits |
| `manager-autonomous-agent-money-is-not-wealth-en` | `articles/manager-autonomous-agent-money-is-not-wealth-en.md` | Economic evaluation and realized net value |
| `manager-eba-evaluating-beneficial-action-en` | `public/2026-10-22-eba-evaluating-beneficial-action.md` | Working developer harness and methodology |
| `manager-eba-benchmark-landscape-en` | `research/publications/EBA_BENCHMARK_LANDSCAPE_PUBLIC_ARTICLE_20261022.md` | Map of 90 selected evaluation systems |
| `manager-eba-open-benchmark-en` | `research/publications/EBA_OPEN_BENCHMARK_ARTICLE_20261022.md` | Synthetic EBA-v0 proposal and reproduction |

The three EBA texts have distinct bodies and purposes; none is a byte-identical duplicate. The generator rejects duplicate source hashes and slugs. Book/seminar outlines, newsletter delivery drafts and internal research notes retain their separate workflows; they are not promoted as finished articles.

The first seven manuscripts preserve their original bytes, including original line endings and the absence of a trailing newline where applicable. For the last two EBA articles, the public copies remove YAML metadata; source-relative links in the landscape article resolve to existing Manager files at the pinned source commit. All prose, absolute references and existing registered images remain. The source and public hashes are separately recorded.

The two already public supplementary articles retain their existing citation-count labels. Other added articles omit the optional count label; no unverified paper count is invented. Their references remain readable in the body.

## Preservation and security properties

- All 54 legacy article records and all 29 media records must match frozen canonical inventory digests before generation. An unexpected legacy change or unrelated added draft fails closed.
- Each manuscript must reside inside Manager's documentation subtree and match its registered source SHA-256. Traversal, symlink escape, duplicate identities, unsafe URL schemes, missing relative targets and unregistered images are rejected.
- Generation is deterministic and repeatable. `--check` compares generated files without writing. No network access, model calls, credential access or publication occurs in the builder.
- Existing importer validation still enforces Manager slug/language identity, canonical URLs, exact package paths, Markdown hashes and media hashes. Its protected integration rejects changed legacy interfaces, preserves non-Manager rendering, escapes raw HTML and does not overwrite an unrelated article identity.
- The current Life Manager `main` package also contains a separate Maritime early-pilot article. This Manager research package deliberately retains the deployed 54-article baseline and includes only the nine identified Manager manuscripts; it does not advance that separate product's pending publication.

## Verification performed

The new tests were written before the builder: eight expected assertion failures for the missing builder, then all passed after implementation. A ninth byte-preservation regression failed on an added trailing newline and passed after preserving the original bytes.

```sh
python products/manager/scripts/build_blog_publication.py
python products/manager/scripts/build_blog_publication.py --check
python -m unittest discover -s products/manager/tests -p test_blog_publication.py -v
node --test apps/landing/manager-blog/tests/*.test.mjs
node apps/landing/manager-blog/scripts/verify-package.mjs
```

The focused nine tests passed. All four existing Node test files passed. The canonical verifier passed **63 articles / 29 media**. The full Manager suite initially passed 354 tests before the additional ninth publication test. A later shared-tree run had 380 tests and 12 failures, all from the concurrent test-first `test_governance.py` lane reporting `governance implementation missing`; these were reported to the integration owner. The final integration owner must rerun the complete tree after that implementation is ready; the latest full suite is not represented here as green.

A separate local dry run fetched the seven relevant publishing interfaces from Anicca Products commit `9775280ba200cc6f8651ceaabe127f1390a90123`, then ran the unchanged installer against all 63 local article files and all 29 media files. It confirmed all staged article/media hashes, all rendered article headings and preservation of an unrelated-content sentinel. The temporary import used an all-zero synthetic revision explicitly for this local exercise. It is not an immutable release identifier. Results are in ignored `products/manager/output/publication/import-dryrun.json`; the exercise was **not a complete Next build or a deploy**.

Source-boundary host note: the repository's Mac-oriented guard could not find `/root/Projects/life-manager-main` in this cloud workspace. It was neither modified nor represented as passing. The integration owner confirmed the user's authorization for the isolated Manager checkout after independently reading the exact Git root, research branch and canonical `https://github.com/Daisuke134/life-manager.git` origin. No Life Manager runtime, credentials, production owner or main branch was changed by this publication work.

## Remaining promotion steps for the integration owner

1. Review and integrate the complete source tree through the canonical research branch's PR/checks. Run the commands above and the current full Manager suite on the final source commit. Record its immutable SHA.
2. In a separate Anicca Products bridge-only change, update `MANAGER_BLOG_REVISION` in both `.github/workflows/landing-pr-build.yml` and `.github/workflows/netlify-deploy.yml` to that exact source SHA. The unchanged installer digest is `c0908ffa9f899138f3f342140063b595e3b7bcab72f6e516d704290d3207e141`. Update `apps/landing/CANONICAL-MANAGER-BLOG.md` to describe the consolidated 63-article package. Do not change the marketing revision, overlay, payment smoke, other product routes or generated article copies.
3. Let the normal publishing PR build exercise the full current Next site, review the preview, and merge through that repository's standard green-check path. Its existing Netlify workflow owns production deployment and payment smoke.
4. Read `https://aniccaai.com/blog/manager/release.json` back independently. Require the exact new source SHA, 63 unique articles, the nine expected hashes and all 56 previously deployed article/hash pairs intact.
5. Read all article URLs and canonical metadata, the Manager collection, the sitemap and any referenced media back from the actual public site. In particular verify all seven newly published URLs and the preserved scientific limitations. Only then record publication success with the deployment URL and readback evidence.

No remote writes, PR creation, merge or deployment were performed by this publication subtask.
