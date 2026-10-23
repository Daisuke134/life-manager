# Agentの永続状態接続 — source受入（2026-10-23）

Manager本体を先に進めるため、既存Ampersand adapterを、既存の非公開checkpointへ結ぶcallableを実装した。専用UI、新しいscheduler、別DB、別ownerは追加していない。

## 実装・統合の確認

- 正規PR: [#8650](https://github.com/Daisuke134/life-manager/pull/8650)。2026-10-23 07:32:43 UTCに通常の `bin/merge-when-green … --squash` で統合。
- reviewed head: `3a8080964e8ed51d91ee4f992977c4a422cf4551`。
- main merge: `1e72a952b0a4b61f644e947213c50f8a91db50b1`。
- exact-headチェックは15 pass／1意図したskip。skipはPRで実公開しない `publish-owned-prefix`。
- [Manager verify](https://github.com/Daisuke134/life-manager/actions/runs/39917467207)、[checkpoint contract](https://github.com/Daisuke134/life-manager/actions/runs/39917467398)、[必須sec-scan](https://github.com/Daisuke134/life-manager/actions/runs/39917467414)はいずれも成功。
- fresh contextの独立reviewはR1〜R3。壊れたschemaからの再送、別turnのcancel照合、復元割込み、矛盾するterminal receiptを修正し、最終未解決0件。
- main由来の全365テストをrootが独立再実行して成功。研究branchへ同じsourceを統合した全928テストは923成功／5 skip。原113件の状態とは別のテスト母数。

## 再利用と変更箇所

| ファイル | 接続・修正した内容 |
|---|---|
| `manager_core/ampersand_api.py`、`provider_deadline.py`、`scripts/phase_ampersand_lab.py` | 研究sourceの既存実装を再利用。labは明示opt-inの架空課題のまま |
| `manager_core/provider_sessions.py`、`provider_budget.py` | SQLite COMMITとcloseの後にcheckpointを保存し、ACK前には外部送信へ戻らない |
| `manager_core/owned_provider.py` | acquired `PrivateCheckpoint`へsessionと予算を結び、同じ `cycle.sqlite`を使う。initial/followup/reconcile/cancelを既存APIへ接続 |
| `manager_core/owned_checkpoint.py` | 任意provider表があれば4表全体のschema・一意性・参照・状態を検証。復元／保存の割込みも同じobjectを永久にfence |
| `manager_core/collaboration.py` | 公開sourceの助言と架空課題のpromptを区別。既存strict parserでP0に固定 |
| `.github/workflows/manager-phase06-service.yml` | 既存verifyのテスト一覧だけを拡張。owner・cadence・権限・planner・publisherは維持 |

元sourceは `7be0d77d3a84d9ef126a418a1c5c6db255250dbd`。別のAgents SDK、会話管理server、workflow engineは作らない。[実装計画](../../../../docs/superpowers/plans/2026-10-23-manager-checkpointed-provider.md)と[mainの運用README](https://github.com/Daisuke134/life-manager/blob/1e72a952b0a4b61f644e947213c50f8a91db50b1/products/manager/deploy/owned-digital/README.md)を参照。

## 受け入れた不変条件と限界

1. session intent、event、writer、予算予約は同じ非公開snapshotで復元する。保存応答が不明なら送らず、同じobjectで続行しない。
2. RESERVEDとUNKNOWNが同じrequestに重複する等の不正snapshotを復元前に拒否する。空DBへの差替え・重複の選別・UNKNOWNの再送はしない。
3. 予算IDを論理operationごとに導出し、別の推論が一予約を使い回せない。予約上限は実際の請求上限ではなく、provider側token/spend ceilingを保証しない。超過観測と未確定費用を保存する。
4. session全体へのcancelの前後で対象turnの一致と状態を照合する。矛盾・欠測はUNKNOWNでwriter/eventを保持。POST応答喪失は `cancellation_sent=null`、この呼出しでPOSTなしはfalse、ACKありはtrue。
5. cancel全体にも絶対期限を適用する。202・切断・古いturnの終了だけでcancel成功にしない。全application writerが同じfenceに従う前提であり、未確認のprovider-side CASや独立した外部writerとの競合防止は主張しない。
6. 公開文脈はtyped sourceで渡し、架空sourceを実世界の観測へ昇格しない。PROPOSEもP0の助言で、実行権限・publisher packetにはしない。

根拠となる既存公式guideは [Ampersand recovery](https://ampersand.humansand.ai/docs/GUIDES.html#recovery)。保存済み公式本文は2026-10-23 04:28 UTC取得。切断はcancelにならないこと、保存済state、単一application writerでのlatest-turn照合を再利用した。この作業で新規scrape成功やSDK schema全体の再検証は主張しない。

## 未実装・未実証の接続

これはsource／contractの受入であり、scheduled inferenceの稼働受入ではない。定期実行のplannerは引き続き決定論的。今回の検証に新しいlive Ampersand推論は含めない。

- U002/U003で実課題を確認し、モデルが単純ルール／非介入より価値を加えられる場面を選ぶ。
- その公開sourceからtyped contextと安定したoperation IDを作り、同条件のbaseline／holdout比較を既存評価へ結ぶ。
- caller、固定SDK依存、既存の秘密保管・予算設定、shadow評価を通常PRで実行経路へ結ぶ。助言で既存のsource／scope／browser／CAS検査を迂回しない。
- 長期記憶、既存channel、実結果からのpolicy更新を検証する。session/eventだけから自動のexact-turn復旧を完成したとはしない。
- 人の便益・害・費用・継続利用を実測する。公開ページの技術結果や架空課題の応答で置き換えない。

原113件は75 done／35 todo／3 skippedのまま。新task ID、done加算、元dependsや `original_*` の変更はない。新しい記事・書籍・応募・外部連絡は本体優先の後段に置く。cloud source-boundaryのcanonical path不在という既知FAILも書き換えず、所有者のcloud作業指示に従った。
