# E16 — 限定した実稼働能力の総合受入（2026-10-23 UTC）

**判定範囲:** Digital Autonomy v0.1の所有デジタル7パスに限る。通常mainの単一Actions owner、Supabase private checkpoint、既存publisherを使用する。人の便益、汎用AGI、広い環境で活動するManager全体の完成判定ではない。F005/F006/F008/F009は本判定後に[別の個別受入記録](PHASE06_DIGITAL_V2_ACCEPTANCE_20261023.md)で技術P2として受入済み。

## 実証と元のE16要件の対応

| 元の要件 | 実証・検証 |
|---|---|
| 永続状態・所有者・scheduler | mainの `.github/workflows/manager-phase06-service.yml`、UTC毎時17分・3600秒slot・共有writer concurrency。既存Supabaseの非公開checkpoint、実OIDC/CAS/解放と別runner復元。Macは検証adapterで第二ownerを作っていない |
| observe→compare→admit→限定write→独立readback | finance commit `61909d20220fcf14132a6f5f459ce19796f1fc2d` とmental `374cb9ac73d1bd703e44c452e8d5c7ae60d9ad7f` の各公式commit・parent・Pages成功・独立7 GET。内容・SHA・時刻とnative P1/P2は[版付き結果](PHASE06_DIGITAL_V2_RESULT_20261022.json) |
| 初回UNKNOWNとlost-response回収 | finance 39892782613、mental 39898014550のUNKNOWN／writes=nullを保持。別runner 39893308922／39898468888で照合し書込み0。後続のproof exportを新しいpositive canaryに数えない |
| STOPの永続性 | 39890247403でSTOP、別runner39890599654はSTOPで拒否。39892445213で明示resume。mental後39899007434で再度STOP |
| 許可旧bundleだけの復元 | 旧39901996368はwrites=0で拒否。実collectorのrelative path境界をPR8632で修正。39907087699の初回UNKNOWNを保持し、実rollback `c6d5de029e91142ef3e0c965f4ef800d37a0f515`、parent=mental374cb9a、許可7パスのみ、Pages39907376445成功、05:46 UTCの独立GETでfinance61909d2の全bytesへ復元を確認 |
| 復元後の照合と停止解除 | fresh39907673029、source808d041、05:56:38 UTCに公式GATEWAY_ACKNOWLEDGED／RESUMED_BY_OWNER／writes=0。resume経路は保存済みrollback・deliveryと現在P2の照合を要求する。個別private journal行を公開・直接読出ししたという意味ではない。公式summaryのrollback_deliveryはnullを保持 |
| 通常運用へ戻した後の実配信 | 39908693666は新slotの新候補で、初回UNKNOWN／writes=nullを保持。実commit `faf18b39207be69af89d9b10389a294731288a20`、parent=c6d5de0、許可7パスのみ。Pages39909038806は06:02:35 UTCに成功。rootの06:03:29 UTCの独立7 GETは全200・immutable bytes一致、finance／mental両cueあり |
| fresh runnerの再送0とnative proof | 39909274852、source `318f3223df9b4d581ce0edf1a4db418f2eb132b2`、06:07:14 UTCに公式GATEWAY_ACKNOWLEDGED／NOT_DUE／writes=0／current_proof_exported=true／current_proof_receipt_sha=faf18b3。公開tipはfaf18b3不変。元UNKNOWNのsend permissionを再利用していない |
| catch-up once・競合・負metric・改変bytes・checkpoint欠落 | `test_digital_cycle_acceptance.py` の10契約と `test_owned_checkpoint_order.py`、`test_owned_platform_rollback.py`。固定時計の取り逃し、競合owner拒否、served-byte regressionと正確な旧bundle復元、無関係path保持、checkpoint ACKより前の送信禁止、UNKNOWN隔離を検証。負の技術判定は同じoccurrenceに結び付いたP2の固定rubric不成立（`BOUND_CURRENT_PAGE_CUE_FAILURE`等）であり、`test_deployment_lag_does_not_stop_but_exact_bound_rubric_failure_does`がSTOPPED_REGRESSIONを検証する。人の便益や任意の数値metricの監視は未実装。自然に取り逃したslotや実障害を追加で作ることは元要件に加えない |

最後の実checkpoint metadataはrevision20、163840 bytes、owner／leaseなし、recovery_required=false。raw snapshot・秘密・nonceをGitへ置いていない。最初のUNKNOWNを後のreadbackで成功や0へ変更しない。

## sourceとテストの区別

- 研究full CI [39905051912](https://github.com/Daisuke134/life-manager/actions/runs/39905051912)、source `9deec0f375b6bbd9d20b1bc3987e56a16c1f8db7` は870件中864成功・6 skip。同sourceのlocalは896件中891成功・5 skip。任意B依存の差でCIは26件少ない。
- 実配備のmanager_core／scripts／workflow全43ファイルは、この研究CIの43ファイルとblob同一。研究側の追加78ファイルがmainで稼働しているという意味ではない。配備source318f322はf8e11と同じruntime bytes。
- rollback修正のmain全291 tests、143 owned＋8 service、同じ修正sourceのMac検証は別の証拠。PR8632は通常guard・exact-head securityと独立Solレビューを通してmainへ統合した。
- 台帳受入guardの統合source `a8701d1bbac22258482c9bc8b009f9d3d3477263` はlocal900件中895成功・5 skip。独立レビューの指摘2件を修正後、18 focusedと生成viewの整合を確認した。このsourceの900件をmainの291件と取り違えない。

## 判定の意味と限界

各runの公式 `E16_ACCEPTANCE=INCOMPLETE` は元のsummaryのまま残す。各runは総合判定器ではなく、特に最後のNOT_DUE runはP0・positive_canary=NOT_RUNのままである。本書は別時点のP1/P2、停止・復元・再開・再送0、source別テストを元のE16条件へ対応付ける総合判定である。台帳のE16だけをPASSED／cursor=nullへ進め、Fの4件は個別に判定する。

費用は、過去の指定7 Actions runのUBUNTU billable 0 msだけが確認値。全期間の実請求額、hosting／model費、運営者・利用者の時間、害の網羅性はUNKNOWN。支出権限JPY0から実費0を推定しない。Actionsの開始遅延、障害、永続容量の無制限性を保証しない。

P3/P4、人の行動・説得・健康・家計・苦痛低減、純便益、収益は未測定／未確認。元のGate 1独立RCT再現はUNMET、H005/F004/F007はskippedを保持。専用UIなしの限定loopは動くが、広い環境を横断する主体、AI助言の本番接続、長期記憶と実結果からの学習は残る。
