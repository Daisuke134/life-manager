# Manager completion presentation: Research lab

English slide source and Japanese speaker notes. Prepared 2026-10-22 JST / 2026-10-21 UTC. No scheduled presentation date is asserted.

Editable deck: [PowerPoint](artifacts/Manager_Completion_Lab_20261022.pptx). Visible slides: English. Full Japanese support and exact sources follow each slide.

The P2 claim concerns an existing public digital artifact. Human outcomes remain NOT_MEASURED. Forecasts, proposed studies and observed results are explicitly distinguished.

## Slide 1: Autonomous action with evidence

**Claim type:** `RESEARCH_QUESTION`

Manager research discussion

How can an authorized action produce a measurable human benefit?

### 日本語補助ノート

研究室向けの中心的な問いは、権限のある実行と、その後に人へ生じた結果を、どのように別々に検証できるかです。Managerは研究段階にあります。公開成果物の配信は確認されていますが、人の生活への改善効果は未測定です。本資料に発表予定日は記載していません。ファイル名の日付は資料の作成日です。

### Sources

- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)

## Slide 2: Evidence has distinct levels

**Claim type:** `DEFINITION`

Each claim requires its own observation

| Level | Meaning | Current interpretation |
| --- | --- | --- |
| P0 | Simulation or model/task score | Research evidence |
| P1 | Authentic execution receipt | Action evidence |
| P2 | Independently observed state change | Live artifact verified |
| P3 | Authentic downstream human outcome | NOT_MEASURED |
| P4 | Causal net improvement, costs and harms | Not established |
| P5 | Replication across settings | Not established |

### 日本語補助ノート

P0からP5は一般的な能力ランキングではなく、Managerの主張と証拠の対応です。P1は実行の受領証、P2は独立に確認した状態変化です。P3は実際の人の結果、P4は比較対象と費用・害を含む因果的な純改善、P5は異なる設定での再現です。P2の公開成果物からP3やP4へ飛躍してはいけません。

### Sources

- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)
- [Dated digital release evidence](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/verification/PHASE06_DIGITAL_SERVICE_EXECUTION_20261021.md)

## Slide 3: The public artifact is verifiable

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

## Slide 4: Prior work informs the evaluation

**Claim type:** `LITERATURE_AND_INFERENCE`

Original studies suggest different design requirements

| Research | What it contributes | Question for Manager |
| --- | --- | --- |
| HeartSteps / JITAI | Repeated decisions and availability | Does the action reach a valid opportunity? |
| Megastudies | Comparable arms and follow-up | Does the change persist? |
| Cash-transfer experiments | Separate recipient outcomes | Who benefits after costs and spillovers? |
| Generative Agents | Simulated behavior and interaction | What held-out result could falsify a policy? |

### 日本語補助ノート

ここでは各研究の成果をManagerの成果として移していません。HeartStepsとJITAIからは、意思決定の機会や利用可能性を定義する必要を学びます。メガスタディは共通条件下の比較と持続性を示す設計例です。現金給付研究では実際の受給者の複数の結果を区別しています。Generative Agentsのシミュレーションは、人の因果的な福祉改善をそのまま証明しません。右列は原著者の発言ではなく、Manager側の研究上の問いです。

### Sources

- [Klasnja et al. Efficacy of Contextually Tailored Suggestions for Physical Activity](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/)
- [Nahum-Shani et al. JITAI key components and design principles](https://pmc.ncbi.nlm.nih.gov/articles/PMC5364076/)
- [Milkman et al. Megastudies improve the impact of applied behavioural science](https://www.nature.com/articles/s41586-021-04128-4)
- [Haushofer and Shapiro: Short-Term Impact of Unconditional Cash Transfers](https://pmc.ncbi.nlm.nih.gov/articles/PMC7575201/)
- [Park et al. Generative Agents: Interactive Simulacra of Human Behavior](https://dl.acm.org/doi/10.1145/3586183.3606763)

## Slide 5: A support journey needs separate endpoints

**Claim type:** `PROPOSED_DESIGN`

Prospective definitions for the provisional finance-navigation wedge

| Endpoint | Unit | Evidence still needed |
| --- | --- | --- |
| Correct official destination | Browser or participant task | State which unit was tested |
| Completed support step | Consented support journey | Independent observation and follow-up |
| Recipient gain | Original outcome measure | Valid measurement and harms |
| Causal net benefit | Predeclared comparison | Assignment, uncertainty and total cost |

A link click cannot establish support receipt.

### 日本語補助ノート

最初の候補は経済的支援への公式情報を探す経路です。ただし、U002の5件の同意済み面談は揃っておらず、U003の選定は暫定です。ブラウザの検査と人が実際に操作する試験は単位が違います。公式ページへの到達、相談や申請の完了、受給、人の生活の改善を分けて測ります。対象集団、割付方法、サンプルサイズ、測定期間はまだ確定した試験計画ではありません。

### Sources

- [GOV.UK Measuring completion rate](https://www.gov.uk/service-manual/measuring-success/measuring-completion-rate)
- [Provisional first wedge](../product/FIRST_WEDGE.md)
- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)

## Slide 6: Outcomes retain their original units

**Claim type:** `MEASUREMENT_DEFINITION`

A measurement choice needs a version and a population

| Construct | Unit and direction | Limit |
| --- | --- | --- |
| Loneliness | Three-item score 3–9, higher worse | No universal diagnostic threshold |
| Mental wellbeing | WHO-5 0–25 or 0–100, higher better | Two-week recall and rights review |
| Functioning | WHODAS method-specific score | Version, scoring and license matter |
| Financial wellbeing | CFPB converted score | Age/mode conversion, local validity |

### 日本語補助ノート

孤独感、肯定的な精神的ウェルビーイング、生活機能、経済的ウェルビーイングは異なる構成概念です。WHO-5は5項目で過去2週間を対象とし、素点0〜25を4倍した0〜100表示があります。孤独感の3項目尺度は3〜9で方向が逆です。WHODASはバージョンと採点法を、CFPBは年齢帯と回答方法による変換を区別します。これらを合計して普遍的な苦しみの点数にはしません。実装前には権利と対象集団における妥当性を確認します。

### Sources

- [ONS Measuring loneliness: guidance for use of national indicators](https://www.ons.gov.uk/peoplepopulationandcommunity/wellbeing/methodologies/measuringlonelinessguidanceforuseofthenationalindicatorsonsurveys)
- [WHO-5 English instrument and rights (2024)](https://cdn.who.int/media/docs/default-source/mental-health/who-5_english-original4da539d6ed4b49389e3afe47cda2326a.pdf?sfvrsn=ed43f352_11)
- [WHO Disability Assessment Schedule 2.0](https://www.who.int/classifications/international-classification-of-functioning-disability-and-health/who-disability-assessment-schedule)
- [CFPB full financial well-being scorecard](https://files.consumerfinance.gov/f/documents/bcfp_fin-well-being_full-scorecard.pdf)

## Slide 7: The demo chooses NO_ACTION

**Claim type:** `OBSERVATION`

An actual public readback with a deterministic decision

| Observed state | Decision | Scope of the evidence |
| --- | --- | --- |
| 6 public pages match | NO_ACTION | An identical publication adds no new artifact |
| 0 external writes | Keep the existing release | No new field intervention |
| Human outcome unknown | NOT_MEASURED | No beneficiary or causal-effect claim |

The demo records a real observation and a bounded software decision.

### 日本語補助ノート

このデモは、実際の公開HTTPSページを読み戻し、同じ内容を再公開する候補に対してNO_ACTIONを選んだ記録です。JSONのcaptured_atは2026-10-21T16:47:27.352145+00:00です。6ページの観測と外部書き込み0件はこのデモの事実です。新しい配信、資金移動、現地介入、人の結果測定を行ったという意味ではありません。トレース中のローカル権限チェックはP0で、外部プラットフォームの実行権限が必要であることも記録されています。動画とJSONを併せて参照してください。

### Sources

- [Captured NO_ACTION decision](../demos/manager-public-no-action-20261022.json)
- [Recorded public-readback demo](../demos/manager-public-no-action-20261022.mp4)
- [Live support-navigation prototype](https://daisuke134.github.io/life-manager/manager-support/)

## Slide 8: The next study must answer a concrete question

**Claim type:** `RESEARCH_QUESTION`

### Product question

Do people and operators identify navigation as a meaningful barrier?

The five consented interviews remain outstanding.

### Scientific question

Does improving that journey cause a useful support step at acceptable cost?

A partner, protocol and independent outcome data remain outstanding.

Current contribution: inspectable artifacts and a falsifiable evaluation design.

### 日本語補助ノート

相談したいのは、一般的なAIの印象ではなく、特定の支援経路と測定可能な結果です。面談は問題の発見に役立ちますが、因果効果の証明にはなりません。研究の次の段階では、適切な比較、脱落と欠測、利用者への負担、無効や悪化を含む結果、実際の費用を事前に定義する必要があります。現時点では研究協力の確約も参加者もありません。

### Sources

- [Provisional first wedge](../product/FIRST_WEDGE.md)
- [Outcome measurement map](../research/MENTAL_PUBLIC_AGGREGATE_MAP.md)
- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)
