# AI Monk Factory 日本語avatar移行 実装計画

> **実行担当:** `superpowers:executing-plans`で各taskのRED/GREENを実行する。primaryはcore renderer、workerはpack/baseline/配信契約を所有し、最後に差分全体を独立reviewする。

**Goal:** 既存JA TikTok/Instagram経路を、旧記録を保持して写実的なWise Buddhist Monkと日本語voiceへ切り替える。

**Architecture:** Node→既存Python runner→HeyGen→既存Postiz adapterを再利用する。新しい日本語baselineを追加して既存のsemantic重複防止を維持し、両言語のHeyGen処理を同じaccount lockと未確定費用guardで直列化する。

**Tech Stack:** 既存Node.js、Python、SQLite、HeyGen CLI、Postiz。新依存・scheduler・schema・credential保存先を追加しない。

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`のS11 / AM-14 JA写実avatar移行契約。

## Global Constraints

- avatar=`ce6ef33ff2d0484dabf8a13ce059bbe8`（Wise Buddhist Monk）、JA voice=`662e1397965c484e8f65fa58c77effde`（Satoshi）。公式catalogはJapanese/male、support_locale=false。JA要求は任意のlocale hintを省略する。
- EN要求のvoice・en-US・canonical request/fingerprintを維持する。`wallet_cost=null`、既存未確定HeyGen sidecar、新規生成guardを維持する。
- JA旧21台本・render/receipt・ledgerは削除/更新しない。`script_ledger.py`とsemantic unique制約を変更しない。
- 現在のproduct/CTA/価格・account/integration・cadenceを維持する。対象は既存アニッチャ・リセットで、新刊の広告と扱わない。
- source受入中のJA2ownerはdisabled/unloaded。provider write・課金生成・投稿は0。EN完成動画の通常FIFO/10GiB下限待ちを迂回しない。
- UI選択のモデルを継承する。新しいagent runnerやLLM呼出を作らない。

## Design

rendererだけの置換は本番の旧JA21件とsemantic signatureが衝突する。旧ledgerを削除/上書きする案は履歴の意味を変える。primary判断で、新しい日本語本文7テーマ×3slotを追加する。短い具体的な悩み→１つの実行できる行動→既存CTAとし、比喩・医療効能・売上保証を使わない。

新JA creative/campaign IDは`baseline.ebook-ja.avatar-v2.d{day}.s{slot}`、source mechanismは`baseline.owner-authored.ebook-ja.avatar-v2.{day}.{slot}`、versionは`2`とする。EN baselineのpayload/IDは変更しない。同じ新JA materializeの反復は同じ21件を返す。

参考は[Yang Munの公式Short](https://www.youtube.com/shorts/Er2Ig4GM7z0)。保存済み一次metadataは65秒/521,580再生の観測で、正面の固定shot・落ち着いた語り・朝夜のreflectionへの誘導を確認する。売上への寄与は未確認で、このsampleに有料CTAは見えない。JAの写実avatarで同媒体・同目的の成功例は未確認なので、JAの成果は仮説として将来の最初の１本で完了率・views・owned CTA流入/実注文を測る。既存book/台本事実だけを使い、元の文章や映像は複製しない。

## Review Focus

- 既存EN assetのrequest/hashを変えて再生成しない。EN既定要求の完全一致を既存fixtureで確認する。
- EN未確定費用がある時、JAもcreate0で待つ。両言語の同時slotでもaccount lockは１つ。
- 旧JA台本をseedしたledgerでも新JAを登録でき、旧payloadは不変。同文のrenderer差だけを許す例外は作らない。
- pack名/hash・renderer/format・product/accountが１箇所でも違えば既存production admissionが拒否する。
- JAへ必要なCLI path/NO_ANALYTICSだけを渡し、他productや無関係secretへ拡張しない。disabled ownerを復帰しない。

## Task 1: 言語別要求と共有費用guard（primary所有）

**Files:**
- Modify: `skills/earn/marketing-engine/render_eval/heygen_candidate.py`
- Modify: `skills/earn/marketing-engine/ebook_runner.py`
- Modify: `skills/earn/marketing-engine/ebook_distribute_daily.py`
- Test: `skills/earn/marketing-engine/render_eval/test_heygen_candidate.py`
- Test: `skills/earn/marketing-engine/test_ebook_distribution_owner.py`
- Test: `skills/earn/marketing-engine/test_ebook_runner_replay.py`

**Interfaces:** `build_request(script, config, *, language="en")`、`render(..., language="en")`。runnerは`script["language"]`を渡す。対応言語はen/ja、JA voiceはpackから渡す。account lockの選択はproduct名ではなく`pack["renderer_id"] == "heygen-avatar-iv"`とする。

- [x] JA要求のvoice設定が`{"speed": 0.9}`、EN要求は従来と完全一致、不正言語は外部call前拒否の最小REDを確認する。
- [x] 上記interfaceだけを追加し、EN既定要求のbytes/fingerprintと費用/readback処理を変えずGREENにする。
- [x] JAでも未確定EN sidecarから`prior_heygen_effect_unresolved`/create0、EN+JA同時実行の最大renderer数1をRED→GREENで確認する。
- [x] 現JAの２account同slot共有render testをHeyGenへ更新し、同run/hash/token・render１回のassertを維持する。
- [x] 関連３test filesを実行する。Task 2との統合前のpack依存REDは区別し、guard失敗を隠さない。

## Task 2: JA pack・baseline・配信先を接続（worker所有）

**Files:**
- Modify: `skills/earn/marketing-engine/brain/baseline_queue.py`
- Replace: `skills/earn/marketing-engine/registry/ebook-packs/ebook-ja-watercolor.json` → `ebook-ja-anicca-monk.json`
- Modify: `skills/earn/marketing-engine/registry/renderers.json`
- Modify: `skills/earn/marketing-engine/registry/accounts/{tiktok,instagram}.obou_anicca.json`
- Modify: `skills/earn/marketing-engine/gates/{ebook_packs,product_router}.py`
- Modify: `apps/life-manager/scripts/ebook-distribute-daily.js`
- Modify: `config/{marketing-destinations,loop-registry}.json`
- Modify: `runtime/loop/lm_loop_run.py`のowner-scoped HeyGen envだけ
- Regenerate: `runtime/loop/tests/fixtures/macos-loop-jobs.json`
- Test: 新規`skills/earn/marketing-engine/test_baseline_queue.py`、既存`gates/test_product_routing.py`、`runtime/loop/tests/{test_lm_loop_run_bounds,test_macos_loop_registry}.py`、`apps/life-manager/{scripts/ebook-distribute-daily.test.js,lib/marketing-destination-contract.test.js}`

**Interfaces:** pack ID=`ebook-ja-anicca-monk`、renderer=`heygen-avatar-iv`、format=`ebook-avatar-iv`。NodeのJA両JOBS/PACK_FILES、registry gates、宛先２行のexact pack/hashを同じ値へ揃える。JA2ownerのresource_classはdeterministicとし、EN Instagram・priority/admission/effect_scopeは変更しない。CLI path/NO_ANALYTICSはEN TikTokとJA2ownerだけに限定する。

- [x] 実旧JA baseline payloadを隔離ledgerへseedし、新21件の登録・反復・旧payload不変を示すREDを先に確認する。EN baselineの固定ID/payloadを維持する。
- [x] 新JA本文とIDを追加し、semantic unique制約には触れずGREENにする。商品事実・CTA・claimsを維持する。
- [x] 新packとrenderer/account許可を接続し、JA HeyGen許可・他product拒否の既存routing testを通す。旧clip/default asset packは保持する。
- [x] Node両JA経路と宛先２行のexact hashを同期し、JA新契約/EN旧契約・誤hash/誤product拒否を既存testで確認する。
- [x] scoped envのJA2owner許可・他owner/secret拒否をnative→Nodeの既存testで確認する。fixtureを既存generatorで同期する。
- [x] workerは所有差分とRED/GREEN結果をprimaryへ報告し、他者の編集をrevert/stage/commitしない。

## Task 3: 統合・source受入・反映（primary所有）

- [x] 上記関連Python/Node tests、Loop Contract、source-boundary/OSS、diff checkを実行する。無関係な全suiteや新frameworkを追加しない。
- [x] fresh read-only reviewerへ言語/費用/lock/旧ledger/secret/宛先pinの反証を依頼し、成立した指摘を修正する。
- [x] S11と本planの状態を更新し、最新mainを保持してcommit/push、exact-head CI全成功後PRをmainへ統合する。
- [x] main由来ALL/sealed releaseを配置する。JA disabled/unloaded、既存receipt/sidecar、EN既存動画hashを確認し、未確定費用・disk/FIFOを維持する。
- [x] 実JA生成/配信の未完条件をS11へ残す。費用の公式照合・通常admissionが揃う前に生成/owner再開/投稿をしない。source成功を日次配信・実売上の成功と報告しない。

## 実装記録

- Task 1の言語要求は4 RED→16 PASS。EN既定要求の完全一致を維持し、JAはlocaleを省略、不正言語はexecutor前に拒否する。
- 既存runnerのproduct==ebook-ja固定分岐をrenderer判定へ変える。旧archive asset/sourceは保持する。
- 実file lockの英日並列fixtureで最大同時数2をRED再現し、rendererに基づく共通account lockで1へ修復する。pack接続後のTask 1関連３filesは25 PASS。
- Task 2は旧JA21件だけの件数と旧routing/envをREDで確認し、Python４files412 PASS/217 subtests、Node２files41 PASS。旧JA21件＋新JA21件の共存とEN固定payload/IDを検証する。新pack SHAは`e58df19e1de5789de288dc056e79cce6b3ed11581fb901232a88e2738b504931`。
- 本番EN要求のread-only再構築は既存fingerprint `4519ee11894303b3dce9316621a969334375669c333642c3163a4bf6690bf814`と完全一致し、MP4/費用sidecar不変。private evidence SHAは`0c14d91419f6eff0e402f1f65765f84f372398cc656af9a1feba1e791aa8ae32`。新JAの実生成・投稿・owner再開を意味しない。
- native単独実行のskill既定より独立作業の並行指示を優先し、rootのcoreとworkerのwiringを分担する。全差分のfresh reviewは維持し、UIモデル固定や承認待ちを追加しない。

- primary統合再実行はPython７files437 PASS/217 subtests、Node２files41 PASS、Loop Contract18業務/191jobs/errors0、source-boundary/OSS/diff PASS。fresh review指摘0件とexact-head CI全14checks成功、main/完全releaseまで確認する。
- fresh whole-branch reviewerはhead87f5b3122dの本機能差分を検証して指摘0件。独立Python49件/4 subtests・Node41件・diff PASS。PR8651を全14checks成功後main e626079013aa1b29914191bd6a2530d2f5b1f254へ統合し、ALL/sealed immutable20261023T162024-e6260790を配置する。
- source準備の受入は完了。主要14sourceのmain bytes一致、JA disabled/unloaded、既存MP4/費用sidecarと共有current不変を確認する。private release proof SHA75f2abbbda141e46de8c776580e20af488e90d8c36554073fd901182228a20c3。JA対象apply/再開/実生成/投稿は0。実配信・購入・収益は未完である。
- fresh本番準備reviewも指摘0件。GitHub/main/ALL/sealed14source、両JAの自身公式停止readback、MP4/sidecarを独立照合する。DB/providerは再照合しない。結果docsのremote checkpoint20029fb435を確認済み。
