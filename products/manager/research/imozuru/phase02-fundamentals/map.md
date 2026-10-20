# Manager Phase02: imozuru source route

## Question
予測の校正、JITAI、因果DAG、反実仮想、RCT、MRT、波及効果、方針のオフライン評価を、公開一次資料と再現用のコードにどう結びつけるか。

## Branch A: Prediction metrics
- scikit-learn probability calibration docs: https://sklearn.org/stable/modules/calibration.html
- Source implementation (sklearn): https://github.com/scikit-learn/scikit-learn/blob/main/doc/modules/calibration.rst
- Simile confidence methodology: https://www.simile.com/blog/confidence

## Branch B: Intervention design and causality
- Nahum-Shani et al. JITAI: https://pmc.ncbi.nlm.nih.gov/articles/PMC5364076/
- Klasnja et al. HeartSteps: https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/
- Murphy lab MRT design FAQ: https://people.seas.harvard.edu/~samurphy/JITAI_MRT/faq.html
- Hernán & Robins official free book: https://miguelhernan.org/whatifbook (book contents are copyrighted; do not mirror)
- Wang/Agarwal/Dudík ICML 2017 off-policy evaluation: https://proceedings.mlr.press/v70/wang17a.html
- Milkman et al. Megastudy / real human intervention: https://www.nature.com/articles/s41586-021-04128-4

## Researcher map
- Inbal Nahum-Shani, Susan Murphy and collaborators: context-sensitive interventions and randomized decision points
- Miguel Hernán, Jamie Robins: identification and potential outcomes
- Yu-Xiang Wang, Alekh Agarwal, Miroslav Dudík: off-policy evaluation assumptions
- Katherine Milkman and collaborators: comparable megastudies of interventions

## Crucial negative cases
- Good forecasts do not imply accurate causal effect predictions.
- Short-window increases do not prove long-term health.
- Target funding gains do not imply net social gain because of interference/displacement.
- No logging propensity or overlap means naive off-policy estimates cannot be trusted.
- Vendor/LLM simulated participants are not human trial participants.

## Limits
- Six short local citation snippets are verified by the upstream imozuru report.py; that alone does not verify the source text scientific correctness or establish independent replication.
- External sources retrieved using web search in this turn; local container cannot fetch full source PDFs.
- No private participant data collected.
