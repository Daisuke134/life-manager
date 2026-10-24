# AnnoMI conversation-label evaluation v1

2026-10-24 UTC. A bounded offline evaluation of released utterance labels. It is not a study of intervention effects, completed behavior, suffering, clinical benefit, or a trained Manager agent.

## Frozen inputs and method

- Source: `uccollab/AnnoMI` commit `42936645ec3857a9c84ab296a36a3c34b779ef49`, `AnnoMI-simple.csv`, SHA-256 `b178db3b0b9858a0fa4ed670dabeccd63e975ba67e141d7ae16f2e8214f78e61`.
- Frozen design: [evaluation design v1](../../experiments/behavior-model/annomi-dialogue-evaluation-design-v1.json). Implementation and test hashes are pinned there. Runtime used Python 3.12.14, NumPy 2.3.5, and scikit-learn 1.8.0.
- Five-fold `StratifiedGroupKFold`, seed `20261024`, with platform-scoped video IDs as groups (YouTube and Vimeo); 119 groups total (116 YouTube, 3 Vimeo), 133 transcripts. Every group was tested once; cross-fold group overlap was zero.
- Two label tasks: therapist behavior labels and client talk-type labels. Compare train-fold majority with TF-IDF unigram/bigram plus balanced logistic regression. Primary metric: out-of-fold macro-F1 delta; uncertainty: paired 2,000-resample video-group bootstrap, percentile 95% interval.
- No row predictions, utterance text, transcript/video identifiers, source CSV, or weights are included in this repository. The only result artifact is [aggregate JSON](../../experiments/behavior-model/annomi-dialogue-evaluation-results-v1.json), SHA-256 `51a646b90c7d089e1a6ff9e8410d11451d23ca4b735696b34b4f867de72e5a1f`.

## Results

| Label task | Rows | Majority macro-F1 | TF-IDF/logistic macro-F1 | Difference (95% group-bootstrap CI) | Accuracy, majority → model | Balanced accuracy, majority → model |
|---|---:|---:|---:|---:|---:|---:|
| Therapist | 4,882 | 0.1226 | 0.6976 | +0.5750 [0.5508, 0.6007] | 0.3249 → 0.7235 | 0.2500 → 0.7059 |
| Client | 4,817 | 0.2611 | 0.5017 | +0.2405 [0.2112, 0.2706] | 0.6440 → 0.5904 | 0.3333 → 0.5298 |

The client task illustrates why accuracy alone is misleading under label imbalance: macro-F1 and balanced accuracy improve over the majority predictor while overall accuracy is lower. These are cross-validated predictions of the released conversation annotations only.

Exact normalized utterance text recurred across distinct source-video groups: 126 strings covering 2,415 rows. In held-out folds, 1,123 therapist rows and 1,206 client rows had exact normalized text present in that fold's training set. The model's macro-F1 on exact-text-seen versus exact-text-unseen rows was 0.4033 vs 0.6075 for therapist labels and 0.3533 vs 0.4701 for client labels. This subset comparison is descriptive; it does not eliminate speaker overlap or establish new-person generalization. Video-group isolation prevents the same source video crossing folds, not the same speaker appearing in different videos.

## Decision and limits

This finite slice shows that a standard text classifier predicts these released annotation labels better than a train-fold majority baseline under the frozen split. It demonstrates reuse of an established baseline, not a novel model contribution. The confidence intervals quantify uncertainty over sampled video groups under this dataset and protocol; they do not account for annotation validity, source selection, repeated speakers, population shift, or unobserved outcomes.

Do not treat therapist/client labels, change talk, or this score as evidence of persuasion success, a person's action, persistence, mental-state change, suffering reduction, or welfare. No participant-facing intervention or recruitment occurred; no behavior, suffering, harm, or cost was measured. The evaluation fit ten fold-local TF-IDF/logistic-regression classifiers (five folds per task) in memory; it saved no classifier weights and did not fine-tune or deploy a generative/Manager model. This AnnoMI slice is complete, but broad V002 remains todo: existing API/open-weight/rule/no-action comparisons, independent human-reference and harm/pressure/dependence assessment, costs, and other purpose-relevant tasks remain. V003 training/adoption remains gated on a separately justified objective and evaluation.

The bounded private-research rights decision and unresolved video/speaker/consent questions are in the [artifact audit](../research/2026-10-24-annomi-artifact-audit.md). Raw redistribution, weights, product use, and live intervention remain HOLD.
