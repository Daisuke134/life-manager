# Data card — Manager v0 training & eval data

## Source

**Hillstrom MineThatData E-Mail Challenge (2008)** — a randomized
e-mail marketing experiment (64,000 customers; men's / women's /
no-e-mail arms). We use the two arms the MG-06 preregistration froze:
*Womens E-Mail* (treated) vs *No E-Mail* (control) = 42,693 rows.

- Download (same mirror as the MG-06 prereg):
  `https://hillstorm1.s3.us-east-2.amazonaws.com/hillstorm_no_indices.csv.gz`
- SHA-256: `bab6578f60db5d792f1c2372c502f029152a5249cf5ea84390f3b7f885d7234f`
- License/terms: the challenge data is distributed by MineThatData for
  research and analysis. This repository redistributes only the
  serialized derivatives needed to reproduce the run (prompts, case
  records), with attribution. It does not redistribute the raw CSV.

Why this dataset first: it is real randomized intervention data with
measured outcomes — the same shape as our product data
(situation → stimulus → measured response) — and our MG-06 baseline and
gate were already preregistered on it, so v0 is comparable to every
number we published before it.

## Split (frozen)

70/30 `train_test_split(test_size=0.3, random_state=0)`, stratified by
treatment × visit: **train 29,885 / test 12,808**. Identical to the
MG-06 baseline (anicca-ops `files/eval/mg06/mg06_hillstrom_baseline.py`),
whose published numbers this pipeline reproduces exactly.

## Files produced by `build_dataset.py`

| file | content |
|---|---|
| `cases_train.jsonl` / `cases_test.jsonl` | Full split in ManagerBench intervention-case schema v1 (see `product/`), split order |
| `sft_train.jsonl` | 2,000 train cases (`sample(n=2000, random_state=0)`), prompt/completion pairs |
| `manifest.json` | Provenance: source sha256, split, sizes, rates |

SFT sample statistics: treated share 0.4985, visit rate 0.124.
The file v0 trained on, `sft_train_v0.jsonl`, is a uniform subsample
(`sample(n=1000, random_state=0)`) of that file: treated share 0.502,
visit rate 0.120. `build_dataset.py` emits both files.

## Serialization (`serialize.py`)

Prompt (one format for training and scoring):

```
History: recency={recency}; spend={history}; mens={mens}; womens={womens}; zip={zip_code}; newbie={newbie}; channel={channel}.
Intervention: {send a promotional e-mail featuring women's products. | send no e-mail.}
Will the person visit the website within two weeks? Answer 1 for yes, 0 for no.
Answer:
```

Completion: `" 1"` if the person visited within two weeks, else `" 0"`
(the observed outcome under the arm actually delivered).

The renderer is verified: `validate_serialize.py` re-renders the frozen
train split and reproduces all 2,000 shipped (prompt, completion) pairs
exactly.

## What is NOT in v0 data

- **Product (Anicca) cases: 0.** The common case format and converter
  exist (`product/`), but the app does not yet export the two fields the
  schema requires for causal use — a stable `delivery_id` and the
  `assigned_probability` of the delivery policy. Until it does, product
  events cannot honestly enter training or eval. This is the recorded
  blocker in anicca-ops `files/manager-v0-start-2026-11-14.md` §5.
- Criteo uplift data: used by MG-06 baselines, not by v0 training
  (families are never pooled; the prereg keeps Hillstrom primary).
