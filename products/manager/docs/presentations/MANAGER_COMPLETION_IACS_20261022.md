# Manager completion presentation: IACS

English slide source and Japanese speaker notes. Prepared 2026-10-22 JST / 2026-10-21 UTC. No scheduled presentation date is asserted.

Editable deck: [PowerPoint](artifacts/Manager_Completion_IACS_20261022.pptx). Visible slides: English. Full Japanese support and exact sources follow each slide.

The P2 claim concerns an existing public digital artifact. Human outcomes remain NOT_MEASURED. Forecasts, proposed studies and observed results are explicitly distinguished.

## Slide 1: Accountable autonomous intervention

**Claim type:** `RESEARCH_QUESTION`

Manager discussion for an IACS audience

Connecting behavioral models to observable changes

### 日本語補助ノート

IACS向けには、行動モデルの予測と、現実の環境を変える実行、その後の人の結果を接続する問題として説明します。IACSの正式な開催予定や発表枠は未確認なので、予定日は記載していません。研究段階であることと、人への改善効果が未測定であることを明示します。

### Sources

- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)
- [Park et al. Generative Agents: Interactive Simulacra of Human Behavior](https://dl.acm.org/doi/10.1145/3586183.3606763)

## Slide 2: Observation, prediction and effect

**Claim type:** `CONCEPTUAL_DISTINCTION`

Three statements require different evidence

| Statement | Example | Required support |
| --- | --- | --- |
| Observation | The served file matches its digest | Independent readback |
| Prediction | A policy may improve access | Held-out predictive evaluation |
| Causal effect | The policy improved access | Credible comparator and uncertainty |

Agreement in simulation does not identify a field effect.

### 日本語補助ノート

観測とは、例えば公開ファイルの内容が期待したハッシュに一致することです。予測は、ある方策が今後の行動をどう変えるかというモデルの主張です。因果効果は、比較可能な条件との差として介入の結果を推定する主張です。三者は必要なデータと検証方法が異なります。表は概念整理であり、シミュレーションから得た予測値やManagerの効果推定を示しているわけではありません。

### Sources

- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)
- [Park et al. Generative Agents: Interactive Simulacra of Human Behavior](https://dl.acm.org/doi/10.1145/3586183.3606763)
- [Klasnja et al. Efficacy of Contextually Tailored Suggestions for Physical Activity](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/)

## Slide 3: A controlled action has separate records

**Claim type:** `DESIGN_CONTRACT`

Conceptual contract for the Manager system

| Record | What it binds | What it cannot establish alone |
| --- | --- | --- |
| Authority | Purpose, target, scope and expiry | Benefit |
| Execution | Actual authorized operation | Independent world state |
| Readback | Observed state and source | Human outcome |
| Outcome | Original units and provenance | Causality without a comparator |

A simulation signature remains a simulation artifact.

### 日本語補助ノート

これは実装の設計契約を説明する図表です。権限は目的、対象、範囲、期限を結びます。実行の受領証と独立した読み戻しは別の記録です。結果は元の単位と出所を保持します。ローカルなfixture署名は、外部の本物の操作権限になりません。この表だけでライブの端から端までの実行がすべて完成したとは主張していません。

### Sources

- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)

## Slide 4: The public artifact is verifiable

**Claim type:** `OBSERVATION`

Recorded verification: 21 October 2026, 14:36 UTC

| Value | Meaning | Scope |
|---|---|---|
| 6 | HTML pages matched | One public product release |
| 16 | Public browser checks passed | Software scenarios, not participants |

P2 artifact only. Human outcomes remain NOT_MEASURED.

### 日本語補助ノート

この数字は、2026年10月21日14時36分UTCの既存の公開検証記録から取っています。6ページは一つの公開成果物を構成するHTMLであり、6回の人への介入ではありません。16件はブラウザの検査であり、16人の利用者ではありません。配信の確認はP2 artifact onlyです。公的支援に到達した人数や、精神・身体・経済面の改善効果は未測定のままです。後続のコード変更や新しいテスト総数を、この固定された記録に混ぜません。

### Sources

- [Dated digital release evidence](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/verification/PHASE06_DIGITAL_SERVICE_EXECUTION_20261021.md)
- [Source/build/readback run](https://github.com/Daisuke134/life-manager/actions/runs/39617848783)
- [Pages deployment run](https://github.com/Daisuke134/life-manager/actions/runs/39618047098)

## Slide 5: Behavioral research offers complementary tests

**Claim type:** `LITERATURE_AND_INFERENCE`

The research map links original work to open questions

| Approach | Primary example | Useful test |
| --- | --- | --- |
| Adaptive intervention | HeartSteps and JITAI | Availability and repeated outcomes |
| Multi-arm field experiment | Milkman et al., 2021 | Shared comparison and persistence |
| Recipient outcome study | Haushofer and Shapiro, 2016 | Benefit beyond transferred money |
| Generative simulation | Park et al., 2023 | Behavioral fidelity on held-out cases |

### 日本語補助ノート

4つの研究方法を同じ競技のランキングにせず、何を検証できるかで対応させています。適応的介入では繰り返しの意思決定と利用可能性が重要です。複数アームの現地実験では共通条件下で比較します。受給者研究では資金の移転とその後の生活を分けます。生成的シミュレーションでは未知の行動に対する再現性を問います。公開人物マップは13名を原著と公開成果に結びますが、交流や推薦は主張しません。

### Sources

- [Klasnja et al. Efficacy of Contextually Tailored Suggestions for Physical Activity](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/)
- [Nahum-Shani et al. JITAI key components and design principles](https://pmc.ncbi.nlm.nih.gov/articles/PMC5364076/)
- [Milkman et al. Megastudies improve the impact of applied behavioural science](https://www.nature.com/articles/s41586-021-04128-4)
- [Haushofer and Shapiro: Short-Term Impact of Unconditional Cash Transfers](https://pmc.ncbi.nlm.nih.gov/articles/PMC7575201/)
- [Park et al. Generative Agents: Interactive Simulacra of Human Behavior](https://dl.acm.org/doi/10.1145/3586183.3606763)
- [13-researcher source map](../research/RESEARCHER_PUBLIC_SOURCE_MAP.md)

## Slide 6: Public aggregates provide population context

**Claim type:** `PUBLIC_AGGREGATE_AND_DEFINITION`

Community Life Survey 2024/25, England adults aged 16+

| Value | Meaning | Scope |
|---|---|---|
| 6.6% | Often or always lonely | October 2024–March 2025 |
| 3–9 | Indirect loneliness score range | A distinct instrument and unit |

Neither figure describes a Manager visitor or estimates a Manager effect.

### 日本語補助ノート

6.6%はイングランドの16歳以上の成人に関する公式集計で、期間は2024年10月から2025年3月です。見出しでは7%に丸められています。3〜9は別の間接的な3項目尺度の採点範囲であり、6.6%の計算から得た値ではありません。公的な集計でも、個々の閲覧者の孤独感は推定できません。日本の対象集団やManagerの介入効果への外挿もしません。ONSは2025年8月に尺度の正式名称を訂正しています。

### Sources

- [Community Life Survey 2024/25: Loneliness and support networks](https://www.gov.uk/government/statistics/community-life-survey-202425-annual-publication/community-life-survey-202425-loneliness-and-support-networks)
- [ONS Measuring loneliness: guidance for use of national indicators](https://www.ons.gov.uk/peoplepopulationandcommunity/wellbeing/methodologies/measuringlonelinessguidanceforuseofthenationalindicatorsonsurveys)

## Slide 7: Evidence status for the current prototype

**Claim type:** `DEFINITION_AND_OBSERVATION`

Real delivery and unmeasured human outcomes coexist

| Level | Meaning | Current interpretation |
| --- | --- | --- |
| P0 | Simulation or model/task score | Research evidence |
| P1 | Authentic execution receipt | Action evidence |
| P2 | Independently observed state change | Live artifact verified |
| P3 | Authentic downstream human outcome | NOT_MEASURED |
| P4 | Causal net improvement, costs and harms | Not established |
| P5 | Replication across settings | Not established |

### 日本語補助ノート

P2のデジタル成果物の存在は事実ですが、P3の人の結果を測定したことにはなりません。P4には比較、費用、害、推定の不確実性が必要で、P5には再現が必要です。欠測をゼロとして扱わず、悪化と無効を含めて同じ水準で証拠を残します。異なる領域の単位も維持し、一つの便益点数へ任意に足し合わせません。

### Sources

- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)
- [Dated digital release evidence](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/verification/PHASE06_DIGITAL_SERVICE_EXECUTION_20261021.md)

## Slide 8: Open questions for a field evaluation

**Claim type:** `RESEARCH_QUESTION`

### Model validity

Which held-out outcomes could reject a policy recommendation?

How should uncertainty prevent an unsupported action?

### Human outcomes

Who can independently observe the support journey?

How will the study report missing data, harms and unequal effects?

A partner and a prospective protocol are still required.

### 日本語補助ノート

問いは、モデルがもっともらしい答えを出すかだけでなく、どの観測によって方策を棄却できるかです。現地の観測者と比較設計がなければ人への純改善を主張できません。Simileの公式ページも人による検証と不確実性を説明しているため、他社は人で検証しないという比較は行いません。Managerの仮説は、権限から実行と検証、結果までの接続が役立つかどうかです。

### Sources

- [Provisional first wedge](../product/FIRST_WEDGE.md)
- [Outcome measurement map](../research/MENTAL_PUBLIC_AGGREGATE_MAP.md)
- [Simile official company site](https://www.simile.com/)
