---
license: other
language: en
tags: [uplift, intervention, hillstrom, managerbench]
---

# Manager v0 — Hillstrom SFT + ManagerBench cases

Serialized derivatives of the Hillstrom MineThatData e-mail challenge
(2008), prepared for Manager v0 post-training and the MG-06 uplift eval.
Full provenance, split definition and license note:
`DATA_CARD.md` in https://github.com/Daisuke134/anicca
(`models/manager/v0/`). The raw CSV is not redistributed.

Files:
- `sft_train.jsonl` — 2,000 prompt/completion cases (frozen train split).
- `sft_train_v0.jsonl` — the 1,000-row subsample v0 trained on.
- `cases_train.jsonl` / `cases_test.jsonl` — the full frozen split in
  ManagerBench intervention-case schema v1.

## Feedback

Expert feedback is explicitly welcome — issues and PRs on
https://github.com/Daisuke134/anicca. Reproduction commands are in the
repo's `models/manager/v0/README.md` and `MODEL_CARD.md`. If your
numbers differ from ours, that is exactly the report we want.
