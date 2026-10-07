# README主要15エージェントの稼働確認

判定: **移行・全体復旧の実装準備は未完了**。READMEの15能力を正本として107ジョブを照合した。ハーネス比較の内部ジョブ分類を能力の稼働証明に使わない。

## 確認済みの範囲

- source base: `960c0f4b499064ad960b72afa9e00ccd3abab28e`。共有checkoutの古いREADMEではなく最新mainを読む。
- 15 groups / 107 jobs。全107 entrypointが存在。106件のconfigured entrypointの内容は監査mainと一致、106件のloaded argvはinstalled plistと一致。Alpaca liveだけservice absent（rc113）。liveを起動すべきかは別判定。
- safe GUI preflight PASS。全launchd読み取りは`bin/launchctl-safe`経由。fleet snapshot用の`_launchctl`はプローブ内だけ安全ラッパーに置換。production変更・再送・実model呼出は0。
- 107ジョブ: healthy12 / running14 / safely_fenced48 / failed26 / effect_unknown7。これはジョブhealthの分類であり、売上・入金・15能力の完了数ではない。
- healthはeffect detailsを省いたsnapshot。official receiptのnullはreceipt不存在の証明ではない。business成果の全provider readbackは未取得。

## 15能力の現在観測

| 能力 | 正常/実行中 | failed | fence | effect unknown | 次の確認 |
|---|---:|---:|---:|---:|---|
| Gig — Coconala | 2/1 | 2 | 2 | 0 | host_admission_deferred:resource_effect_unknown, host_admission_deferred:resource_control_busy |
| Gig — Lancers | 0/1 | 1 | 5 | 0 | host_admission_deferred:resource_capacity_busy, entrypoint_exit_1, host_admission_deferred:resource_effect_unknown |
| Gig — CrowdWorks | 0/1 | 0 | 4 | 0 | entrypoint_exit_75, host_admission_deferred:resource_capacity_busy, host_admission_deferred:resource_effect_unknown |
| Writer | 2/0 | 3 | 2 | 0 | host_admission_deferred:resource_capacity_busy, apply_lock_busy, host_admission_deferred:resource_effect_unknown |
| Affiliate | 0/3 | 2 | 1 | 0 | host_admission_deferred:resource_capacity_busy, host_admission_deferred:resource_effect_unknown |
| Investment | 1/0 | 0 | 3 | 0 | host_admission_deferred:resource_effect_unknown |
| Agent Economy | 0/5 | 10 | 1 | 3 | host_admission_deferred:resource_capacity_busy, host_admission_deferred:resource_effect_unknown |
| Job Hunter | 0/0 | 2 | 5 | 0 | host_admission_deferred:resource_capacity_busy, host_admission_deferred:resource_effect_unknown, apply_lock_busy |
| Fundraiser | 0/0 | 0 | 1 | 0 | host_admission_deferred:resource_effect_unknown |
| Connector | 1/0 | 0 | 0 | 0 | 同一occurrenceの業務成果 |
| Self-Build / Product Improvement | 4/0 | 0 | 0 | 0 | 同一occurrenceの業務成果 |
| Mobile App Loops | 0/2 | 0 | 20 | 0 | entrypoint_exit_1, host_admission_deferred:resource_control_busy, entrypoint_exit_75, host_admission_deferred:resource_effect_unknown |
| eBook | 0/0 | 1 | 0 | 2 | apply_lock_busy, entrypoint_exit_1 |
| Capafy | 2/1 | 2 | 4 | 2 | host_admission_deferred:resource_capacity_busy, host_admission_deferred:resource_control_busy, host_admission_deferred:resource_effect_unknown, entrypoint_exit_1 |
| CFO | 0/0 | 3 | 0 | 0 | host_admission_deferred:resource_capacity_busy |

## 原因が絞れた範囲と残る穴

- 共通admission: 独立read-only監査でqueue約76/reservation0、実DBの既存3索引を確認。claim PIDは観測中変化。capacity待ちはtotal/class上限・revenue floor・legacy fenceのどれか。control待ちはowner deploy/global lock/claim flockのどれか。まだ値を変える根拠はない。SQLite lockも一時観測、control待ちと同一原因にしない。
- Lancers work-sync: 01:35:13 UTCの自然runはentrypoint_exit_1/effect none。shared stdoutの直近にはaccount_unavailableとlancers_http_errorが反復するが、ログに同一run相関がなく、このrunの確定原因にはできない。`run_tick`のaccount_diagnosticとowner/runを結合する必要がある。空のwork-sync.jsonは観測したが、同関数はそれを入力JSONとして読まないため原因と断定しない。
- Capafy daily: exit0/passでもeffect publish/unknown、provider receipt/readback null。正常終了を公開成功に昇格しない。既存reconcilerの公式publish-listとversion readbackを同occurrenceへ結ぶ。
- eBook JA: old occurrenceでentrypoint_exit_1、effect unknown。現loaded releaseと過去run releaseが異なる。Postiz/provider readback前の再投稿を禁止する。
- Connector/Self-Build: health上healthy。ただしno-effect passや旧releaseの結果を新しいイベント登録・改善成果の証明にしない。
- financial adapters: catalogはAffiliate/Fundraiser/Self-Build/Mobile/eBook/Capafyでmissing、Writer/Investment/Job Hunterはpartialと明記。全15のsettled-netを既存healthだけで確定できない。missing表記は新規実装要求とは別で、既存データ経路を先に確認する。

## 移行判断

推奨は、既存15能力の原因・receiptを先に閉じ、現在正常な能力をそのまま残し、後から有限runnerを1ownerずつ切り替える。共通scheduler/state/effect fenceを同時置換しない。
best: capacity待ちとaccount/readback不足だけなら既存運用の対象限定復旧で済む。base: admission競合と複数provider成果の未確認をowner別に解消する。worst:外部作用が未確認で公式receiptも取得不能なら該当ownerをfenceのまま残す。所要時間は未測定で確約しない。
棄却案の最強論拠:全面ハーネス置換なら一度に標準化できる。しかし現観測の待ち・auth・receipt不足を解消する根拠はない。
自分が間違うとしたら最有力の筋: snapshotが保守的に古い結果を保持しており、公式readbackではすでに多くが解決済み。

次のatomic cursorは計画のMA-01。この監査を「すべて検証済み」「即実装可能」と報告しない。

追加観測: CFOはtotal7<8で空き、deterministic2<2が偽、borrow floor0<5が真。現在class上限がborrow CFOを制限する。過去occurrenceの判定時snapshotはなく、現queueは0。容量増加が必要とは判定しない。`admission-capacity.json`を参照。
