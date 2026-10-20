# H001 imozuru source map

Question: which released HeartSteps V1 files and intervention-causal-analysis columns are documented, and what can be reused without copying participant records?

Two search routes:
1. Data route: authors' GitHub README → pinned main commit/tree → official wiki's CSV column table → original CC BY 4.0 LICENSE.
2. Causal route: original Klasnja et al. 2019 paper → author analytical R code → differences with released 2023 CSV naming and paper analytic sample.

Conflicts: README and Wiki disagree on users.csv/Jawbone/GoogleFit column counts; main-effects RData names differ from released CSV wiki. Do not reconcile by speculation.

All `sources/*.md` reproduce only one short source excerpt apiece. Official `tools/imozuru/report.py` validates its presence in our local excerpt file; it does **not** certify source accuracy or reach the original webpage. GitHub/Firecrawl supplied first-party inspection separately.

Stopping rule: five independent source types provide enough to decide a minimal H001 metadata inventory and defer row-level ingestion to H002.