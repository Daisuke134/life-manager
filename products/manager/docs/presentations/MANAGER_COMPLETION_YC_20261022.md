# Manager completion presentation: YC

English slide source and Japanese speaker notes. Prepared 2026-10-22 JST / 2026-10-21 UTC. No scheduled presentation date is asserted.

Editable deck: [PowerPoint](artifacts/Manager_Completion_YC_20261022.pptx). Visible slides: English. Full Japanese support and exact sources follow each slide.

The P2 claim concerns an existing public digital artifact. Human outcomes remain NOT_MEASURED. Forecasts, proposed studies and observed results are explicitly distinguished.

## Slide 1: Manager

**Claim type:** `PRODUCT_THESIS`

Autonomous software for access to public services

We are building auditable evidence of what changed.

### 日本語補助ノート

一文の説明は、公的支援へのアクセスを改善し、何が変わったかを検証できる自律型ソフトウェアを開発している、というものです。開発中の目標と現在の実績を区別します。公開試作はありますが、人の生活への改善効果は未測定です。YC W27は準備上の文脈で、応募、面接、採択や締切の確認を意味しません。

### Sources

- [English/Japanese pitch](../founder/Y001_MANAGER_PITCH_EN_JA.md)
- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)

## Slide 2: The first customer problem is a hypothesis

**Claim type:** `CUSTOMER_HYPOTHESIS`

### Potential beneficiary

A person trying to find the right official route for financial support.

The prototype offers a public navigation page.

### Potential customer

An organization responsible for a support-information journey.

Demand and willingness to pay remain unvalidated.

Five consented interviews are still required before the wedge decision.

### 日本語補助ノート

受益者と顧客を分けます。受益者候補は経済的支援の公式な窓口を探す人です。顧客候補はその情報経路を運営する自治体や支援組織などですが、現時点で契約や支払意思を確認したわけではありません。MHLWの公式ページは支援制度の存在を確認する資料であり、利用者の課題仮説を検証する証拠ではありません。5件の同意済み面談がないため、最初の対象選定は暫定です。

### Sources

- [MHLW livelihood-support system overview](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000059425.html)
- [Provisional first wedge](../product/FIRST_WEDGE.md)

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

## Slide 4: The demo chooses NO_ACTION

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

## Slide 5: The product and business hypotheses

**Claim type:** `BUSINESS_HYPOTHESIS`

### Product value to test

An operator can inspect what the software was allowed to do and what it actually changed.

Human outcomes have their own evidence.

### Commercial value to test

A service operator may pay for maintaining and evaluating a support journey.

No validated pricing or revenue claim is available.

The immediate test is a real operator problem and a measurable support task.

### 日本語補助ノート

技術的な仮説は、権限、実行、独立した状態確認、その後の結果を追跡できることが運営者に役立つというものです。事業面では、情報経路の維持や評価への支払意思を確認する必要があります。市場規模、売上、顧客パイプラインを仮の数字で埋めません。また、他社も人の検証を行っているため、未検証の独占的優位性は主張しません。

### Sources

- [English/Japanese pitch](../founder/Y001_MANAGER_PITCH_EN_JA.md)
- [Provisional first wedge](../product/FIRST_WEDGE.md)
- [Simile official company site](https://www.simile.com/)

## Slide 6: The next decisive milestones

**Claim type:** `PROPOSED_MILESTONES`

Each milestone answers an unresolved question

| Milestone | Question it answers | Current status |
| --- | --- | --- |
| Five consented interviews | Is navigation a material barrier? | Outstanding |
| An operating partner | Can we observe a real support task? | Not secured |
| A prospective evaluation | Does a change improve that task? | Not run |
| A customer commitment | Will an operator pay for the value? | Unvalidated |

Current evidence: a live artifact. Human benefit remains NOT_MEASURED.

### 日本語補助ノート

次の段階は、面談、実際の運営者、事前に定めた評価、顧客価値の確認です。これは達成済みの実績表ではありません。面談で課題が否定された場合には対象候補を変えます。実際の支援ステップが観測できない場合には、配信試作の範囲に主張を留めます。資料の提示は応募や連絡の送信ではなく、発表の開催日時も未確認です。

### Sources

- [Provisional first wedge](../product/FIRST_WEDGE.md)
- [English/Japanese pitch](../founder/Y001_MANAGER_PITCH_EN_JA.md)
- [Manager evidence definitions](https://github.com/Daisuke134/life-manager/blob/ce75c0add1d9cec7de5ddcb9a9347dbd0c1632e5/products/manager/docs/MANAGER_PRODUCT_SPEC.md)
