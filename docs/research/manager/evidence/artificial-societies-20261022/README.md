# Artificial Societies chapter evidence — 2026-10-22

This is a source/coverage record, not another task registry or an assertion of deployment. The article is `docs/research/manager/articles/2026-10-22-artificial-societies-open-behavior-research-ja.md` and its reviewed publication copy is in the existing `publication/2026-10-19/ja/` package.

- `index.json`: fresh official inventory, 25 entries (9 papers/internal research, 4 research blogs, 6 commercial blogs, 6 news). Alternate PDFs/social links do not create independent publications.
- `papers.json`: 9 entries; 7 body/webpage-equivalent retrievals and 2 partial previews. A retrieved body is not an independent reproduction.
- `cases.json`: the other 16 listed entries, 7 discovered case studies, and the official X alternative to the empty LinkedIn retrieval. Bloomberg/New Statesman are public leads only.
- `persuasion.json`: primary research, corrections/concern status, endpoint and execution boundaries. Full original regression replications were not performed.
- `reuse.json`: pinned upstreams, licenses/access, public Nature Source Data inspection results, and limits. An available download does not imply a redistribution license.

Raw copyrighted full texts, medical individual records, free-text participant profiles, API credentials and local provider receipts are not in this package. Retrieval artifacts remain in private scratch; their path fields are redacted here. Upstream URL, version, access status and hash fields remain where available. A provider `success` does not mean paywalled text was retrieved.

## Reproduce the aggregate inspection

Use Python's standard library, no new model inference or API subscription. Download the official Nature supplement and Source Data into a private directory, checking the expected hashes in `reuse.json` / the values below. No original Source Data bytes are redistributed here.

| Filename | Official MediaObjects suffix under DOI 10.1038/s41586-026-10742-x | SHA256 |
|---|---|---|
| `supplement.pdf` | `41586_2026_10742_MOESM1_ESM.pdf` | `c747529d8031695b101963aec3cdff8669dadc47fed569112a004ce1a719f001` |
| `fig1.xlsx` | `41586_2026_10742_MOESM4_ESM.xlsx` | `6b3bfc2566584a04ab65108e97ca27ab657f276583b7d61889cc9378198582e0` |
| `fig2.xlsx` | `41586_2026_10742_MOESM5_ESM.xlsx` | `c129c1f3ba5485cf2449685ac5143e98c989c28d2c531ef4f8c40f0874b0d548` |
| `fig3.xlsx` | `41586_2026_10742_MOESM6_ESM.xlsx` | `67c6c957b51ce5f2fcbe93985672ffe9d7d49e4b26c946c7413c90c4f8c8a0d7` |

Official base URL: `https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41586-026-10742-x/MediaObjects/`.

```sh
python docs/research/manager/evidence/artificial-societies-20261022/inspect_source_data.py /absolute/private/input-directory
```

Observed: 3,356 directed contrast rows, 70 study identifiers, 8 published model/human summary rows. The script spot-checks the published GPT-4 raw/adjusted correlation values and prints file hashes. The pooled diagnostic correlation is about .80515, distinct from the authors' published raw .85079. Dependent contrasts, random-reference repetitions, attenuation adjustment and study-cluster uncertainty make those different analyses. This is an aggregate inspection; no fresh predictions, independent trial, original confidence-interval replication, or new human benefit.

## Publication preservation and verification

The base `95369c9ce8cf1d4efd1b440cc3a79c7bcec25c8a` contains 56 articles/29 media, while the live content revision `32cb5b84d052de9f2be3b2a3c8e8c21a150c4da1` contains 65/33. This change keeps the union (66/33), then adds one new Japanese chapter and its conceptual AI-generated figure (67/34). Existing main article bytes and all deployed article/media bytes must remain identical. No production code, model, website integration code or workflow is changed in this canonical content PR.

Validation commands:

```sh
node apps/landing/manager-blog/scripts/verify-package.mjs
node --test apps/landing/manager-blog/tests/*.test.mjs
git diff --check
```

The local host-specific `scripts/verify-source-boundary.sh` returned `canonical Git root is unavailable=/home/agent/Projects/life-manager-main`. Its failure is recorded, not counted as a pass; the guard is unchanged. The owner explicitly authorized this cloud research/source-editing task. Normal PR/checks/main and the existing publishing bridge remain the publication route. Source commit, publishing commit, deploy result and public readback must be recorded after they actually exist.
