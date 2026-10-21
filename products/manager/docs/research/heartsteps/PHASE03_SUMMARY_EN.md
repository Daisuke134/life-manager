# HeartSteps V1: What We Reproduced, What We Could Not

**Manager research log — October 21, 2026**

The Manager project has completed an **alternative, exploratory, reproducible analysis** of a pinned public HeartSteps V1 release. This is **not an exact reproduction of the 2019 randomized trial's analysis population or causal estimand** and is **not evidence that Manager has improved anyone's health**.

We used a fixed 8,274-row, 86-column public file from `klasnja/HeartStepsV1`, source commit `3016391de426116bdef41880d72bc8cd4b9b2477` and SHA256 `60ee7896183d7084a084f9a6e8ef2d0afea2e7fecdb41d6b15382ce1745c5ddb`. The code operates on 6,330 available decision points with known assignments and 37 participants. All participant rows are held only in temporary execution memory/storage, never committed or published.

Our exploratory participant-cluster-adjusted **associations** are 1.140 (normal-approximation 95% CI 1.001–1.297) for any activity suggestion versus no suggestion and 1.239 (1.056–1.454) for walking suggestion versus no suggestion in the selected subset. The original paper reports 1.14 and 1.24 respectively, but the numerical proximity does not establish an exact reproduction: the original trial used 6,061 available decision points and a different data-processing and inference contract. The means also differ (220.42 versus the reported 253 steps).

The decision-order interaction estimate is a multiplier of 0.858 per 50 ordinal indexes (95% CI 0.772–0.953). **Ordinal indexes are not study days**, and the interaction must not be described as a day-by-day effect from the original study.

The original analysis-set reconstruction (task H005) was deliberately **skipped** with founder authorization. Public release metadata and device-derived day information do not resolve the original analysis population without ambiguity; previous attempts to force-match counts failed. We preserved that limitation and completed other aggregate analysis tasks under revised, explicitly nonidentical acceptance criteria. The methodological milestone requiring independently reproduced randomized causal effects remains unmet; future work needs a different fully accessible and suitably permissioned human experiment.

**Engineering result:** a standard-library, hash-pinned data ingestion and reporting job with synthetic unit tests, participant-cluster adjusted regression, external CI, independent audit artifacts and an unambiguous privacy boundary.

**Primary sources:** [Original paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/), [public author data](https://github.com/klasnja/HeartStepsV1), [source code](https://github.com/Daisuke134/life-manager/tree/research/manager-product-r006-20261020/products/manager), [real-data research workflow](https://github.com/Daisuke134/life-manager/actions/runs/39526839889).

This educational note has **not** been published to the blog; later public distribution can reuse it after writer-agent review.