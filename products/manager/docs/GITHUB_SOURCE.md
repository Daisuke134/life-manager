# GitHub source location and retention (Manager independent product)

**User authorization:** source may live in the existing Life Manager repository. This does not merge Manager and Life Manager products or runtimes.

- **Repository:** https://github.com/Daisuke134/life-manager
- **Manager source branch:** `research/manager-product-r006-20261020`
- **Manager-only subtree:** `products/manager/`
- **First synchronized commit (GitHub):** `68a2214d1edc9de4cfdd24ef75b84c8d59e5db6c`
- **Source of rights PDF:** `products/manager/docs/reports/2026-10-20-manager-r006-source-rights-ja.pdf`
- **Independent local historical repository R006 revision:** `10e8011f925ec69fb934e6a059679b6c4904b736`. Its separate commits are not automatically the same as GitHub root commits.
- **Main preservation check at initial publication:** `060297d154d01dfa6f543b4b4c3c86de00067c60` (checked unchanged after first source sync).
- **Runtime:** no Life Manager imports/DB/credentials, no external writes, publishing or live monetary actions.

## Cloud artifact policy

GitHub branch: code, original specs, original scientific summaries, small excerpts and source metadata, originally authored PDF. ChatGPT Library `/Manager`: historical standalone Git ZIP, exported author-created PDF, project source bundle. No participant raw data or third-party full journal PDFs on public GitHub. The Library is storage, not proof of GitHub version or official source status.

## Working and reviewing

1. Treat the branch path as Manager's GitHub source, while the original standalone Git history is a recoverable archive.
2. Edit `products/manager/` in dedicated research branches; no Life Manager production changes.
3. Run `python3 -m unittest discover -s tests`, `python3 scripts/make_roadmap.py --check`, `python3 scripts/check_boundaries.py` from the Manager folder before updates.
4. Explicitly compare the GitHub branch head, not only a local process result. GitHub-hosted CI status is a separate check.
5. Do not merge Manager work into Life Manager main or publish without a new explicit production/review decision.
