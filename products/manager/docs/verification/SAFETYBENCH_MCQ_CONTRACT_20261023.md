# SafetyBench MCQ actual fixed-control receipt — 2026-10-23

This finite receipt records actual frozen local intake and deterministic controls on the public/exposed SafetyBench MCQ benchmark. Model execution is `NOT_RUN`; supplied predictions and producer are `null`. It does not complete parent Task2/V002, model adoption or the parent goal.

## Actual authorization and immutable inputs

Code commit: `31e746640794068e714baeaf3636570abc2d4386`; reviewed source tree: `1582150c24073a80cbb10470eb2b70884777c0cd`. The actual `ROOT_SCOPED_PURPOSE_ACCEPTANCE` event occurred at `2026-10-23T22:35:25.697772+00:00`. Root accepted the final selected record bytes in `ROOT_ACCEPTED_SELECTED_RIGHTS_RECORD_BYTES` at `2026-10-23T22:47:20.060532+00:00`. Those exact event receipts were read and rehashed before intake. Private offline MCQ evaluation alone is authorized. Study read/local research/commercial evaluation retain their recorded conditions; commercial training, product use and raw redistribution remain held. Dataset-card MIT and repository-code MIT remain distinct evidence; all-row third-party provenance is `NOT_VERIFIED`. The card/release-label discrepancy is preserved. This is not external legal or clinical approval.

Upstream GitHub revision: `960833692a1ec82b191ff3e902daca7993c35cc1`; dataset-card revision: `70538631943dc1517ae9bb0733251809f4445d0e`. [Frozen protocol](../../experiments/behavior-model/safetybench-mcq-protocol-v1.json), [accepted rights record](../research/source-rights.json) and the existing complete MIT notice are unchanged.

| Binding | SHA256 |
|---|---|
| Protocol | `6369fe7f5b9ead9569892acf77da9c8b60d1b4f0933cf79e55562f99041e394e` |
| Selected accepted record, canonical | `07e6beea0bf5570a9b1fab8153c80306dde7a1f29159125109b6b03e16648fd4` |
| Rights manifest, exact bytes | `5ac22d1b0bfb08a938270518cab9a6fc87e4e6f5a486bbdc0595223971f25bbd` |
| Rights manifest, canonical | `3a4bb5e82e104c5a96a4e4470d645d288274aa5b7fefbd39be6726076e9f83b1` |
| Actual scoped-purpose acceptance receipt | `99529eb4ea10bb9d60ed6bfe45f42fdc0416a5a80c26dc07c6434633f7f91a6f` |
| Actual selected-record acceptance receipt | `65cf8ff4e82645852e682e45acf313d4929537d2f93a9cb52dc6b1fc5917b721` |
| Adapter source | `cd6bbf3b0e856d86fa7ef9bd8ee369da53bb8f9e5b105777d61d29442a350fe9` |
| CLI source | `01e183b35ebc0323a08f964e125d6bab15559766137d4db27a5b76b540dec758` |
| Ordered membership diagnostic | `9de8960602275a3cd65cdd53340ca8b5c918cefbd394343ebd0f744b7dae912a` |

| Frozen artifact | Bytes | SHA256 |
|---|---:|---|
| questions | 5110687 | `517648d44a68c79e5d46a284837d673c578fa53a45785c83407cd8358602c547` |
| answers | 729736 | `a26ec13deeb551d68f71d61dd269d05dd43c24e6b22d8be3b93788ee10cf8615` |
| scorer | 1743 | `46dce139f1807be2170fde1b16aac129b5184603ca9d1d751c03fd57ac9c8544` |
| code_license | 1065 | `d33dbec11dfcde5970d43c1a502b62e7d7dccec1f181266a0809a92409244a91` |
| repository_readme | 4536 | `1bc8b6c3a793bee2fc1688b1c2240050b82aa333411dd85240f396b999e97b39` |
| dataset_card | 2209 | `6835d19b015dd0a04b3a2413d78d69c7609d99e9193ff305e1eba9a5f40d6aed` |

Raw data stayed in its existing private cache. New private receipt files are mode 0600 in a mode-0700 directory. No raw rows, per-row IDs, questions, options, gold, predictions or local raw-data paths are published here.

## Actual intake and controls

The local CLI ran exactly once without a predictions argument from `2026-10-23T22:49:13.304897+00:00` to `2026-10-23T22:49:14.102410+00:00`, exit `0`, with empty stderr. Its explicit code-version argument was the immutable commit above. `LOCAL_BYTES_VERIFIED_AT` was `2026-10-23T22:49:13.364066+00:00`: this is a local verification time, not an HTTP retrieval time. Exact private command/cwd/redirects and outputs are retained in hashed metadata. There was no network, provider, model, training or installation call.

Independent parsing confirmed 11,435 unique question assignments, an exact gold ID-set match and matching categories for every row. Original assignment order and option order remain; no rows were dropped, sampled, balanced or deduplicated. Option counts are 2:5,223 / 3:445 / 4:5,767. The first-choice map was fixed from question IDs before the independent gold read; every choice is index 0 and no choice depends on gold.

| Lane | Assigned | Status counts | Valid / coverage | Correct | Conditional accuracy | Native Avg. % |
|---|---:|---|---|---:|---|---:|
| Recorded, absent predictions | 11435 | NOT_RUN 11435; all other states 0 | 0 / 0 | 0 | null | 0.0 |
| NO_ACTION | 11435 | ABSTAIN 11435; all other states 0 | 0 / 0 | 0 | null | 0.0 |
| FIRST_OPTION_RULE | 11435 | VALID 11435; all other states 0 | 11435 / 1 | 4098 | 0.3583734149540883 | 35.83734149540883 |

NO_ACTION supplies no semantic answer and is not refusal: refusal count is 0. Missing/abstained rows remain in the full gold denominator. Conditional accuracy uses only valid predictions and stays null when that denominator is zero. No MAE on categorical IDs is used.

| Category | Full gold denominator | FIRST_OPTION_RULE correct | FIRST_OPTION_RULE native % | NO_ACTION native % |
|---|---:|---:|---:|---:|
| OFF | 1805 | 957 | 53.01939058171745 | 0.0 |
| UB | 1904 | 866 | 45.483193277310924 | 0.0 |
| PH | 1149 | 414 | 36.0313315926893 | 0.0 |
| MH | 1566 | 396 | 25.287356321839084 | 0.0 |
| IA | 1778 | 381 | 21.428571428571427 | 0.0 |
| EM | 1934 | 713 | 36.86659772492244 | 0.0 |
| PP | 1299 | 371 | 28.560431100846806 | 0.0 |

## Exact native and synthetic contract parity

The complete fixed 1,743-byte upstream scorer was inspected and its SHA256 reverified before execution. Python `3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]` and already-installed NumPy `2.3.5` were used. Native printing was redirected to a private aggregate capture. Exact original `eva_res` was called once with the empty mapping at `2026-10-23T22:49:14.324761+00:00` and once with every case ID mapped to index 0 at `2026-10-23T22:49:14.332139+00:00`. Each returned all eight percentages exactly equal to the actual CLI receipt: `Avg.`, `OFF`, `UB`, `PH`, `MH`, `IA`, `EM`, `PP`. No tolerance, retry, rule tuning or alternate control was used.

`SYNTHETIC_CONTRACT_PARITY` separately compared the adapted `_native_accuracy` helper with the exact upstream function on entirely authored 14-assignment fixtures spanning all seven categories and 2/3/4 options. The valid case scored 14/14 (all eight percentages 100); the wrong case scored 0/14 (all eight 0); the sparse case supplied 3 predictions, 2 correct, with Avg. `14.285714285714285`, OFF/PH `50.0` and the other five categories `0.0`. All eight percentages matched exactly in each case, including absent-category predictions remaining in full category denominators. These three synthetic calls are contract checks, never benchmark model output.

## Verification and private evidence bindings

Root already completed the entire Manager suite on this exact source: `PYTHONPATH=. python3 -B -m unittest discover -s tests`, run from the Manager project directory, 1,160 tests in 27.246s, `OK (skipped=5)`, exit 0; actual interval `2026-10-23T22:46:41.848564+00:00`–`2026-10-23T22:47:09.946845+00:00`. This is separate from the earlier 44 focused authored tests. The suite was not rerun for this metadata-only slice. The earlier baseline invocation from repository root, `PYTHONPATH=products/manager python3 -B -m unittest discover -s products/manager/tests`, ran 1,145 tests (5 skipped) with 2 errors, exit 1, at `2026-10-23T22:29:11.784733+00:00`–`2026-10-23T22:29:40.395099+00:00`. The errors were the existing SFT `SFTExecutionBindingTests.test_execution_config_accepts_file_bindings_without_claiming_remote_authority` and `FixedAdapterExecutionTests.test_complete_fictional_config_and_actual_inventory_hashes_are_checked` cwd guards. Changing only cwd made those two tests pass (0.046s), then the project-cwd baseline passed 1,145 tests in 27.355s (5 skipped), exit 0, at `2026-10-23T22:30:45.519254+00:00`–`2026-10-23T22:31:13.859061+00:00`. Both baseline invocations were on earlier source `ffae1e2a3a8b0f23513b337de10c9e1ec57b65ea`, distinct from the final 1,160-test result. The original failed invocation/log remain retained, not counted as a pass. No guard was weakened.

Root’s prior diff/boundary-import/PII/full-70,940-byte-gitleaks checks passed and the narrow Task1 R2 review had 0 findings/0 blocking, approved. The canonical-checkout source guard retains its standing cloud exception: actual Task2 preflight returned exit 2 because the canonical root was unavailable. This is a host-boundary exception, not a guard pass. The source guard is unchanged. Official exact-source CI, independent whole-change review and later source adoption/integration remain root-owned and pending for this receipt; none is inferred from local control parity.

| Private evidence (aggregate or metadata) | Bytes | SHA256 |
|---|---:|---|
| task-2-preflight.json | 3855 | `0bb56f011d3f7a39a91bb1335271436bc5169bf59bef5511b4c1fd2656e1afea` |
| task-2-cli-command.json | 1248 | `6bea0605eff0aace1cbbdc9539ffca1f80cec879e890ecd781dfa5635fc44167` |
| task-2-cli-aggregate.json | 17047 | `31ee8233f9858fc7dceb93927e0abbe40dbb55c4d53a21d2bbfe0c911bfc9bad` |
| task-2-independent-intake.json | 831 | `d8c6a3e876326f7451439412abc241866e95c7ef92e0eaed16f662fb14380754` |
| task-2-native-parity.json | 2601 | `22f444e6b31d8c2c5d13c5f07e26a36ff9372fcbde14b8c28028d8b00f8695a8` |
| task-2-native-print-capture.txt | 956 | `88add0ba4e68957d2598464c27c3f498a8c3ae59f274dfc8f68dd9703fc944ae` |
| task-2-execution-summary.json | 1631 | `c0e9d47faca9182881f8e487c97928c600009dfe73b60e3be7a70e5eafd4496b` |
| root-final-manager-suite.json | 498 | `15dd4735722af3315cd75e03fe27fe59a3670394555a9a2a63c87935102876ee` |
| root-final-manager-suite.log | 1569 | `0e0257309c52c62dc36049f3e838739885264a484df3955a8a846e8d620803a2` |
| root-task1-final-checks.json | 2041 | `0a2ae38aae96737a14b399d3baa9d6217d3b026174cf4d042a71f87291884565` |
| task-1-review-r2.md | 4553 | `47d5ede83a1603baf248fe2158f26e1a1e4564f33a7f3098485ec9109089e345` |
| root-baseline-tests.json | 544 | `b3d91025d656b9669f6b0fd69a6675522f92be112fa0bb1bf5f26b7c688bab93` |
| root-baseline-tests.log | 4322 | `34bcb6d7f98e678313338bc3350f79f4e1e4f5bad984e25c1843b73089ff2abf` |
| root-baseline-tests-manager-cwd.json | 927 | `18a05496939dfe0f1c2c03e0196f5279691b77667dbdf550fd8a69be45bb4d46` |
| root-baseline-tests-manager-cwd.log | 1554 | `17866537837a56247b30b931bb8a93d712c88e29feddef88293a0608d48f6ae7` |

## Interpretation and preserved limits

This result is descriptive fixed-rule categorical key agreement on a `PUBLIC_EXPOSED_NOT_PRISTINE` benchmark. It measures neither a model nor free-response safety, superiority, human benefit or an independent final/unseen holdout. Pretraining contamination and generalization remain `UNKNOWN`; person/study/time split availability remains `UNAVAILABLE`. P0 / `NOT_MEASURED`, empty EvidenceBundle/reproduction-manifest references, `can_execute=False` and adoption `HOLD` remain. Pressure, dependency, response harm, clinical validity and behavior change remain null.

All 17 historical canonical rights records, prior negative results, old SCI/results, current final16 `SCORED/NOT_PRISTINE`, model `HOLD`, 85 done / 18 todo / 10 skipped and parent `ACTIVE` are preserved. No original-final16 material was read or rescored. The four parent Task2 checkboxes remain unchecked; all V002, human study, model knowledge/response safety and the parent goal are not completed by this finite slice. Requested worker model/effort was gpt-6.1-sol/high; actual CLI model/effort readback is `UNKNOWN`.
