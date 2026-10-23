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

## mainの既存実行経路の互換確認

- [既存workflowのrun39918652169](https://github.com/Daisuke134/life-manager/actions/runs/39918652169)を一度だけ起動し、main source `1e72a952b0a4b61f644e947213c50f8a91db50b1`でverify／publisherの両jobが成功した。公式publisher summaryの出力時刻は2026-10-23 07:54:33 UTC。
- 公式結果は `authentication=GATEWAY_ACKNOWLEDGED`、`status=NO_ACTION`、`reason=MISSING_TYPED_CANDIDATE`、`writes=0`。変更候補を作るためのfixture差替えや再送は行っていない。
- `current_proof_exported=true`、参照先は既存の `faf18b39207be69af89d9b10389a294731288a20`。今回の `receipt_sha=null`、`rollback_delivery=null`を保持し、新しい配信・介入のreceiptと数えない。
- このrunの生の `proof_level=P0`、`E16_ACCEPTANCE=INCOMPLETE`、`positive_canary=NOT_RUN`、`human_outcome=NOT_MEASURED`も保持する。これは既存loopの後方互換の確認であり、新しい正の介入、scheduled inference、人の便益の受入ではない。過去のE16限定技術受入は別のoccurrenceを集約した証拠に基づく。
- source同期と仕様更新の研究head `f784d106ccf9237dc414eb08c6e9dc330e4510ac`は[公式CI39919819042](https://github.com/Daisuke134/life-manager/actions/runs/39919819042)で成功。全902テスト中6 skip、失敗0。E01 receipt、P0 advisory、113件の台帳不変とManager source境界も成功した。これは同headの証拠で、この追記の後のheadへ実行結果を付け替えない。

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
- 公開sourceのtyped context・安定operation ID・既存baselineを使うshadow callerは下記PR8660でsource受入済み。実課題のholdout／実model比較は未実証。
- 既定OFFのcallerはsource統合済み。固定SDKの実行環境、既存の秘密保管・予算設定、実shadow評価を通常の経路で結ぶ。助言で既存のsource／scope／browser／CAS検査を迂回しない。
- 長期記憶、既存channel、実結果からのpolicy更新を検証する。session/eventだけから自動のexact-turn復旧を完成したとはしない。
- 人の便益・害・費用・継続利用を実測する。公開ページの技術結果や架空課題の応答で置き換えない。

原113件は75 done／35 todo／3 skippedのまま。新task ID、done加算、元dependsや `original_*` の変更はない。新しい記事・書籍・応募・外部連絡は本体優先の後段に置く。cloud source-boundaryのcanonical path不在という既知FAILも書き換えず、所有者のcloud作業指示に従った。


## 追加source受入 — shadow callerとSDK整合性修正（2026-10-23）

[PR8660](https://github.com/Daisuke134/life-manager/pull/8660)は08:57:30 UTCにmain `78c9f8738bf4c48068b8ddc7515c75e8af778a4c`へ通常統合した。`owned_provider_shadow.py`は既存の公開catalog／browser検証、typed context、安定operation ID、checkpoint、ルール／NO_ACTION比較をつなぐ。既定OFFでP0記録のみ、action_writes=0、便益NOT_MEASURED。新しいpublisher packetや作用は生成しない。381テストと独立review、exact-headの15成功／1意図したskipを確認した。skipはPRで公開しないpublisher。

公式[PyPI openai3.24.0](https://pypi.org/pypi/openai/3.24.0/json)のwheelを静的に取得・検査し、公表SHA256 `b59703a3e3b5df78b269e90049d383a1dda58c90104cc4be59db21078db4b7a4`との一致を確認した。SDKのインストール・import・client生成・推論は行っていない。SSE text-doneはpart単位、collectorは完成したassistant messageのoutput_textを区切りなしで連結、Turnの非終端状態はqueued/in_progress/waitingであることを一次sourceから確認した。

[PR8665](https://github.com/Daisuke134/life-manager/pull/8665)は09:26:20 UTCにmain `1b418f56303945a1051d90e02366f6f07b4b398c`へ通常の `bin/merge-when-green … --squash` で統合した。reviewed headは `b10399a1677d443d35ff58cf4a5ffe41e347fb9e`。

- followupの最終textを完成したexact-turn保存itemから読み、commentaryを除外して全blockを連結。途中の欠測・不正shape・不完全pageはsilenceと区別する。読み取り前後に対象turnの一致を確認する。
- initial結果のturn IDを保存済みcompleted turnへ照合し、cancelのTurn状態語彙を修正した。Sessionのみのrequires_actionをTurnとして扱わない。
- 独立R1で、deadline wrapperの回復が不完全なfinal itemを残したままterminal metadataだけでwriterを解放する問題を再現。実PrivateCheckpoint／Journal／Ledgerを使うRED→GREENで修正し、確認失敗・読取り中timeoutでもwriter／event／RESERVED exposureを保持する。active-turnのcancelは保持した。R2の未解決0件。
- rootの独立391テスト、独立reviewの100 focused contractsが成功。研究branchへの同期後は既存fakeのSDK shapeだけを補正し、954テスト中949成功／5 skip。テストの母数は原113件と別。
- exact-headは15成功／1意図したpublisher skip。[Manager verify39931015467](https://github.com/Daisuke134/life-manager/actions/runs/39931015467)、[checkpoint contract39931015460](https://github.com/Daisuke134/life-manager/actions/runs/39931015460)、[必須Security Scan39931015539](https://github.com/Daisuke134/life-manager/actions/runs/39931015539)はいずれも成功。Manager source境界・loop contract・product範囲gitleaksも成功した。

追加したのはsourceと契約検証である。定期plannerは決定論的のまま、新しいlive Ampersand推論／cancel、SDK runtime install、課金確定、scheduled inference、人の便益を受入れたとはしない。元の実行receipt／UNKNOWN／nullを書き換えず、原113件の75 done／35 todo／3 skippedも維持する。
