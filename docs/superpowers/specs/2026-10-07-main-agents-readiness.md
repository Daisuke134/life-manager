# ローカルLife Manager — 主要15エージェントとOpenClaw移行仕様

## 目的・範囲

Daisが求める対象はローカルLife Managerの主要15の商品・業務エージェント。既存の制作・販売・応募・納品・投資・収支確認を壊さず、OpenClawを利用してモデル実行基盤の自作負担を減らす。クラウドWeb `/lm`、Travel商品、Web認証、Web画面の新設はこの仕様の対象外。

今回実行するのは読み取り専用検証、仕様・計画・SSOT更新のみ。業務source修正、start/restart/apply、実業務の再送、provider mutation、credential更新、effect fence解除は行わない。

## 確認した現状

- 最新READMEは15商品。旧14との差はeBook。Money Printer/Local/Cloud/内部support jobsを別の商品数へ足さない。
- catalogの15能力は107 jobへ対応。全入口存在、106 loaded argv/installed argv一致。Investment live service不在は紙取引運用とのdesired mode照合が残る。
- 実装済は商品catalog、既存owner群、macOS scheduler、共有admission/budget/runner、個別state/receipt/ledger。15全部が単一の新general specialistに接続済みとは確認していない。
- healthと業務成果は別。source/起動/終了0を販売・公開・入金へ昇格しない。
- `install.sh`はproduct別経路を持つが、15全部に完成済guided installがあるわけではない。unsupported商品を開始成功と表示しない。

## 単一推奨

OpenClawをモデル・tool実行エンジンとして採用する設計。初回は既存runner内部の有限 `openclaw agent exec` を使う。OpenClaw gateway/cronへ全体のschedule/stateを移す設計にはしない。現行backendを稼働させたまま、新backendはdefault off、限定owner/taskで検証する。

これは目標設計であり、本番OpenClaw切替は未実施。native account/model/tool/schema/budget/費用の互換が成立しないownerは現行経路を維持する。既存決定的jobにはモデルを追加しない。

## アーキテクチャ

```mermaid
flowchart TD
  U[利用者: ローカルCLI・既存Telegram] --> LM[Life Manager: 目標と15商品の管理]
  LM --> S[既存scheduler / queue / admission]
  S --> O[商品ごとの既存owner: 有限の仕事]
  O --> D[決定的処理: 収集・計算・照合]
  O --> R[共有runner: lease・budget・deadline]
  R --> H[OpenClaw agent exec: モデルと許可済tool]
  H --> T[既存の商品tool / browser経路]
  T --> F[既存effect intent / outbox / fence]
  F --> P[販売・応募・公開などの外部provider]
  P --> V[公式receipt / readback]
  D --> V
  V --> L[永続state・ledger・収支]
  L --> LM
```

- 管理者は目標・優先度・予算・商品状態を所有。15の商品エージェントは担当商品を制作し販売する能力で、内部owner/jobは分けたまま。
- 常駐するのはschedulerと必要なservice。モデルは仕事が来た時だけ有限実行し、結果を保存して終了する。24/7は継続して仕事を受けて再開できる意味で、15モデルの無限推論ではない。
- OpenClawはLLM+context+toolの実行を所有する。Life Managerは事業目的、wake、owner、予算、正本state、外部effect/receipt、純収支を所有する。二重scheduler、二重ledger、二重effect ownerを作らない。
- browserは既存identity/lease/direct CDP経路を利用。OpenClawのnative toolからfenceや既存browser ownerを迂回できる段階では販売ownerを有効化しない。
- データはimmutable releaseの外に保持。切替で商品、顧客、注文、過去receipt、認証profileを新規生成したり削除したりしない。

## ローカルUX

1. 初期設定: ローカルにinstallし、任せる商品と予算を設定し、その商品に必要な本人のaccount/profileを接続する。15全商品の完成済one-click installerは未実装なので、既存guided経路とsetup_requiredを正直に分ける。
2. 通常利用: 既存のCLIとTelegram報告を使う。OpenClawのCLIや内部sessionを利用者が直接操作する必要はない。今回のrunner切替で新Web画面を要求しない。
3. 商品状態: 実行中、次回待ち、準備が必要、結果確認中、本人対応が必要、一時停止を区別する。容量待ちは待機、外部結果未確認は結果確認中として説明し、自動で再投稿しない。
4. 成果: 作成、公開、応募、契約、納品、売上、入金、原価、純収益を分けて報告する。公開だけを入金、原価不明を0と表示しない。内部job数を成功商品の数にしない。
5. 一時停止: 対象ownerの新しい仕事を止める。進行済の外部作用は取消や再送をせず公式確認を終える。group全体pauseの便利な新UIは今回の切替前提にしない。
6. 復旧: 通常の一時失敗は既存予算内のbounded recovery。auth/本人手続き/公式receipt不足は必要な入力を短く報告する。自動復旧をKYC突破や不明effect再送と同義にしない。

## 自己修復・自己改善・評価

- 自己修復は既存ownerのfailure classごとの回復を使い、効果不明ならreadbackへ進む。OpenClawのretry既定が既存budget/deadlineと衝突しないようprivate instance設定で制御する。
- 自己改善はproduction失敗から候補prompt/skill変更を作り、保存した同じtask群で成功率・実費/推論費・時間・禁止effectを比較する。PASSしたversionだけ限定ownerへ反映し、失敗なら次のwakeを現行engineへ戻す。
- OpenClawのtraceが事業成果やbanked netを自動評価するとは扱わない。trace/run/owner/occurrence/release/official receiptの結合はLife Managerで保持する。
- 商品ごとの実際の合格条件をevalに使う。販売数だけでなく入金・原価・純収益を区別し、モデルの完了自己申告は独立検証しない限り合格にしない。

## 検証済みと残る条件

- pinned配布物によるfake有限CLI検証は13cases。default retry/deadlineは不適合、private retry0の限定probeはPASS。native/backend/account/tool/費用は未証明。
- Context7の公式OpenClaw docsでもgatewayなしのone-shot exec、message-file/stdin、cwd、json、timeoutを再確認。main docsの仕様をpinned版の実証の代用にはしない。
- CFO現在観測ではtotal7<8、deterministic2<2が偽。容量増加を決める証拠ではなく、過去run判定時の占有snapshotは未取得。
- Capafy公式GETで53商品のlistを取得。対象runのsnapshotからversion変化0。最新成果と同一occurrenceの公開成功/入金を確定したとは扱わない。
- eBookのidentity directoryに該当ownerのsidecarを確認できない。plistにtenant envがないことは不具合ではない。`lm_loop_run.py::_child_environment_for_owner`がdais-localとdata rootを注入するため、実child境界を正本に確認する。
- 最適ケースは互換adapterだけで済む。通常ケースはowner別のtool/receipt不整合を直して限定切替。最悪ケースはnative/tool/費用条件が成立せず当該ownerは現行を維持する。移行の時間と追加発見ゼロは確約しない。
- 棄却案の最強論拠:全gateway移行ならschedule/sessionを標準化できる。しかし既存収益経路の変更範囲が増す。最初は有限execの局所切替を優先する。
- 自分が間違うとしたら最有力の筋:OpenClawのnative/tool互換adapterが大きすぎ、既存runnerへSDKを局所導入する方が小さく済むこと。

## 原子的実行順

正本cursorは統一SSOT。検証MA-01〜21の残条件を閉じ、source不具合だけ修正atomへ昇格する。最初のrunner実装atomは既存MX計画のdecode_envelope→write_caller_result→project_usage→build_command→private retry settings→select_engine→既存runner接続。publisher/scheduler/stateを同時変更しない。

参照: [復旧検証plan](../plans/2026-10-07-main-agents-readiness.md)、[有限runner atom](../plans/2026-10-07-harness-first-cutover.md)、[現状監査](../../research/2026-10-07-main-agents-readiness.md)。
