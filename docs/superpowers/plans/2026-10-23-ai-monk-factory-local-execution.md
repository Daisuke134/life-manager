# AI Monk Factory 利用者設定のローカル生成入口

> **実行担当:** `superpowers:executing-plans`で進める。primaryはCLI・README・正本、bounded workerはfactory_render.pyと対応testsを所有する。新しいmodel指定や承認質問は追加しない。

**Goal:** 利用者自身のconfig/台本/run IDを既存HeyGen rendererへ渡し、同じUnix userの既存費用fenceとaccount lockを共有した1回の生成入口を作る。

**Architecture:** v1 offline planを検証器として再利用し、`factory render`から既存rendererへ接続する。shared account rootは既存host設定LM_DATA_DIR、未設定時はuser-homeの`.local/state/life-manager`を使い、その`marketing/ebook`以下を既存ebook ownerと共有する。利用者configのstate_rootは出力だけに使う。生成/投稿を再実装しない。

**Tech Stack:** 既存Python CLI・標準ライブラリ・既存HeyGen CLI/renderer/lock/pending guard/host disk gate。新dependency・DB・schedulerなし。

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` S11 AM-15b。

## Global Constraints

- v1 configと`factory plan`の無効果性・拒否契約は維持する。新commandは`factory render --config JSON --script UTF-8 --run-id ID`。
- run IDはproject IDと同じ`[a-z0-9][a-z0-9_-]{0,63}`。不正入力は新directoryやprovider呼出の前に拒否する。
- API key/passwordをJSONへ追加せず、HeyGen CLIの認証は親processの実sessionを使う。environment引数でauth profileを切り替えるとは説明しない。
- `LM_DATA_DIR`はhost全体の既存state設定で、projectごとに変更してよい設定ではない。空または相対値は拒否する。未設定時は`Path.home()/.local/state/life-manager`。config/CLIからshared guard rootを指定させない。
- shared ebook root=`<host-data>/marketing/ebook`、lock=`locks/heygen-avatar-iv-account.lock`、intent=`runs/factory.<project_id>.<run_id>.heygen-effect.json`。出力=`<config.state_root>/renders/<project_id>.<run_id>.mp4`。
- 既存`exclusive_lock(Path)`の内側で`unresolved_heygen_effect(shared_root/'runs', current_intent)`を使う。他pending/壊れたsidecarがあれば既存費用fenceを保持してrendererへ進まない。同intentは既存rendererの厳密request/output/replay検証に任せる。
- 既存host producer disk gateを課金に先立って呼び、floor/stop flagが未達ならprovider呼出0。登録owner/cadence/FIFO/current/他ownerを変えず、新しいdaemonやpriority経路を作らない。
- 成功/保留結果は`schema_version=ai-monk-factory.render.v1`、project_id/run_idと既存renderer結果をJSONで返す。`state=rendered`でもwallet_cost=null/cost_reconciliation_requiredを消さない。生成物のreceiptを投稿・売上のreceiptとして扱わない。
- 既存rendererには事前USD上限envが無い。wallet/auto-reload threshold/差分/unknownの範囲を超えて費用上限を保証しない。日次全自動の費用上限制御、publisher context、Factory MCP/hosted subscriptionは未完。

## 設計判断と根拠

- 既存`heygen_candidate.render`を直接呼ぶ。`ebook_runner.run`はDaisの商品pack/ScriptLedger/JST slotへ結合しているため汎用入口にしない。
- projectごとにpending rootを作る案は、同じHeyGen accountの既存unknownを見落とすため採らない。email/usernameから新account ID schemeを作る案も、local OSSの共有lockには不要なので採らない。hosted tenant分離は別の未完である。
- 公式user me getのread-onlyではstable account IDが返らずemail/username/wallet等のkeysだけを確認する。秘密値は保存しない。証拠SHA08060986027985edd2c2f9096adaade4fb6020a47229069780a768f66e1f051c。
- `render(environment=...)`はID/CLI選択用で、subprocessへenvを渡さない。既存sidecarには完成済み動画だが費用未確定の状態があるため、state名だけで成功を判定しない。

## Review Focus

- state_root/run ID/LM_DATA_DIRによるpath escapeや既存sidecarの取り違え。
- 別projectに移って同一accountの未知費用を迂回する経路。
- lock外のpending検査、同時生成、再試行時の二重create。
- auth/setup/host disk延期を生成成功や費用0と報告する経路。
- config値・環境credentialのerror echo、既存offline CLIへの新しいstate/provider副作用。

## Task 1: 既存rendererへ利用者設定を接続する

**Files / ownership:**
- Worker create: `skills/earn/marketing-engine/factory_render.py`
- Worker create: `skills/earn/marketing-engine/test_factory_render.py`
- Primary modify: `skills/earn/marketing-engine/bin/lm`
- Primary modify: `skills/earn/marketing-engine/README.md`
- Primary owns: 本plan/S11。既存renderer/runner/lockは通常変更しない。必要な変更が実証された場合はprimaryへ報告する。

**Interfaces:** `render_from_config(config: dict, script: str, run_id: str, *, environment: dict[str,str] | None = None, executor=subprocess.run) -> dict`。build_planの検証結果からID/language/outputを使い、existing renderへ渡す。host gateは既存`runtime/host/disk_admission.py`へ委譲し、隔離testsでは最小のprivate helperを差し替える。providerはexecutor fixtureで置換し、live呼出しない。

- [ ] EN/JAの実CLIでconfig/request IDs・出力・request SHAが一致する失敗testを先に追加し、missing commandまたは期待動作のassertでREDを確認する。
- [ ] 不正config/run ID/host rootを入力し、directory/provider0で拒否するREDを確認する。
- [ ] 異なるproject state rootでも同じ既存lock・pending rootを使い、既存costunknown/破損sidecarでcreate0となるtestを先に書く。
- [ ] 同一intent反復はcreate最大1、別script/outputへの変更は既存conflictでcreate0、2projectの同時executor最大1をtestする。
- [ ] host gate=false、auth setup不足、renderer reconciliation、renderedだがcostunknownを成功/0ドルへ変換しないtestを追加する。
- [ ] 上記境界を最小実装でGREENにし、CLI/READMEへpaid command・既存認証/共有state・費用上限未保証・未完の投稿/売上を明記する。
- [ ] 新規testと既存`test_factory_plan.py`、`render_eval/test_heygen_candidate.py`、`publish/test_intent_cli.py`を一度実行する。Expected: 全件PASS。Loop Contract/source-boundary/OSS/diffも確認する。
- [ ] primaryが差分を確認しcommit/push・remote object一致を確認する。

## Task 2: source受入と実事業成果の区別

- [ ] fresh read-only reviewerが共有root/lock/pending/replay/host gate/秘密値/CLI境界を検証する。
- [ ] latest mainを保持し、exact CI成功後PR/mainへ統合する。main由来の固定版で構文/CLI helpと、実providerへ進まない既存host/費用ガードの結果を確認する。
- [ ] S11/本planにsource受入を記録する。Daisの既存費用unknownや通常admissionが未解消ならlive生成せず、その条件を残す。
- [ ] 次のAM-15cでpublisherの利用者context（native handle/provider/disclosure/caption/destination/asset承認hash等）を具体化する。既存IntentStore/PostizAdapterのfence/upload/draft/promoteを使い、第二実装を作らない。実投稿・日次全自動・実売上・Factory MCP/subscriptionは別の未完である。

## Self-review

v1 planの互換・共有費用fence・private path非固定・live provider0のsource検証・host gate・未完範囲をTask1/2に対応させる。published/revenueをmockやrenderedから導出しない。質問を省略する既存委任に従いprimaryがこの最小local方式を採り、承認待ちを追加しない。
