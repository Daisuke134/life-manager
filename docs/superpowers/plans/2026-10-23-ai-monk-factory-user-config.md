# AI Monk Factory 利用者設定CLI 実装計画

> **実行担当:** `superpowers:executing-plans`でRED/GREENを確認する。primaryは既存CLI・README・正本、bounded workerは純粋planner・設定例・対応testsを所有する。最後に全差分をfresh reviewする。

**Goal:** 利用者自身の設定と台本から、課金・生成・投稿なしで生成要求と投稿予定をJSONで確認できるようにする。

**Architecture:** 既存`bin/lm`へ`factory plan`を追加し、既存`render_eval.heygen_candidate.build_request`を再利用する。Dais専用の商品・account registryやprivate SSOTを読み書きしない。

**Tech Stack:** 既存Python CLIと標準ライブラリ。新dependency・scheduler・agent runner・認証経路を追加しない。

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`のS11 / AM-15a利用者設定契約。

## Global Constraints

- 入口は`skills/earn/marketing-engine/bin/lm factory plan --config <JSON> --script <UTF-8 text>`。成功JSONはstdout、失敗JSONはstderr/exit1。
- 設定schemaは`ai-monk-factory.config.v1`。必須top-level keysは`schema_version, project_id, language, heygen, postiz, product, state_root`だけ。
- `project_id`は`[a-z0-9][a-z0-9_-]{0,63}`、languageは`en|ja`。heygenは`avatar_id,voice_id`、postizは`platform,integration_id`、productは`name,url`だけ。未知fieldやcredentialの混入は値をechoせず拒否する。
- avatar/voiceは既存`heygen_candidate.IDENTIFIER`で検証する。integrationは空白/制御文字なしの非空文字列128字以内。platformは`tiktok|instagram`。
- product nameは非空の文字列200字以内、URLはuserinfoなしのHTTPS URL。state_rootは`~`展開後の絶対pathで、作成・state読取をしない。
- requestは既存build_requestへ渡す。JA locale省略、EN en-US、speed0.9/Avatar IV/9:16/1080pを変更しない。台本上限5000字も既存関数を使う。
- plan schemaは`ai-monk-factory.plan.v1`、status=`planned`、`project_id,language,state_root,render_request,request_sha256,publication_plan,provider_calls,external_effects`を返す。publication_planはprovider=`postiz`と利用者のplatform/integration/productだけ。
- `provider_calls=0`、`external_effects=[]`。auth/credential lookup・wallet/HTTP/CLI・DB・ディレクトリ作成をしない。planをprovider検証済み・投稿済み・売上達成と扱わない。
- 既存Daisのpack/ledger/費用guard・owner停止・admission/cadenceを変更しない。Index SDKの検索機能とFactoryを混同しない。

## 設計判断

primaryは既存CLI拡張を選ぶ。独立した新CLI/packageは起動入口を二重化し、Dais用registryの書換えは利用者設定と本番設定を混在させるため採らない。利用者のvoice/商品/投稿先が実在し使用可能かは、このoffline planでは未検証である。

実生成・日次配信・費用確定・収益・Factory MCP/hosted subscriptionは引き続き未完。今回のplan出力は次の実行入口が共有する入力契約であり、実生成を小さく言い換えた完了条件ではない。

## Review Focus

- Daisのintegration、商品、private pathが利用者の出力へ混入しない。
- 不正JSON/type/未知field/credential値をstderrへ漏らさない。
- EN/JA要求が既存builderと完全一致し、別の要求実装を作らない。
- 有効な入力でもHTTP/subprocess/auth/state/DBへ到達しない。
- 成功planを生成・投稿のreceiptと誤認させない。

## Task 1: 利用者設定から既存CLIでoffline planを返す

**Files / ownership:**
- Worker create: `skills/earn/marketing-engine/factory_plan.py`
- Worker create: `skills/earn/marketing-engine/test_factory_plan.py`
- Worker create: `skills/earn/marketing-engine/examples/ai-monk-factory.config.example.json`
- Primary modify: `skills/earn/marketing-engine/bin/lm`
- Primary modify: `skills/earn/marketing-engine/README.md`
- Primary owns: 本planとS11。workerはstage/commit/pushしない。

**Interfaces:** `factory_plan.build_plan(config: dict, script: str) -> dict`。CLIは２入力fileを読むだけでこの関数へ渡す。state_rootは展開・正規化して出力するだけ。request SHAは既存と同じUTF-8/ensure_ascii=False/sort_keys=True/separators=(",", ":")のSHA256。

- [x] EN/JA入力で要求・SHA・利用者投稿先が一致し、state_root未作成のままであるtestを先に書く。
- [x] 不正language/type/未知field・credential値・不正ID/URL/相対state root/空または長すぎる台本の拒否を最小のparametrized testで確認する。
- [x] CLI実経路で上記設定を渡し、HTTP/subprocessを失敗させるfixtureでも成功し、環境credentialを出力しないtestを先に書く。
- [x] 対応testを実行し、機能が未実装で失敗することを確認する。import errorだけのREDにはせず、CLIの欠落または期待動作のassertで確認する。
- [x] workerは標準ライブラリと既存builderで最小実装する。primaryは既存argparseへの接続と、設定例/台本を渡す実行例・未実施範囲をREADMEへ追加する。
- [x] 設定例にはplaceholderだけを使い、実integrationやcredentialを含めない。EN/JAの成功・失敗・隔離・zero-effect境界をGREENにする。
- [x] `rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=skills/earn/marketing-engine python3 -m pytest -q skills/earn/marketing-engine/test_factory_plan.py skills/earn/marketing-engine/render_eval/test_heygen_candidate.py skills/earn/marketing-engine/publish/test_intent_cli.py`を実行する。Expected: 関連全件PASS。
- [x] primaryが差分を確認し、source-boundary/diff check後commit/push、remote object一致を確認する。

## Task 2: 公開source受入と未完条件の保持

- [x] fresh read-only reviewerがReview Focusと実CLI境界を検証する。成立した不具合は最小RED→GREENで修正する。
- [ ] 最新mainの既存変更を保持し、関連tests・Loop Contract/source-boundary/OSS/diffを確認する。無関係な全suiteや新frameworkを足さない。
- [ ] exact-head CI全成功後PR/mainへ統合する。READMEの実行例をmain由来の完全sealed releaseで呼び、外部呼出し0のJSONを確認する。
- [ ] S11/本planへsource結果と残る実生成・投稿・費用・収益/OSS導入・MCP・subscription条件を記録する。実配信や収益の完了とは報告しない。

## 実装記録

- 既存linked worktreeを再利用する。新しいcheckoutやdependency installを増やさず、既存CLI helpとpublish intent関連7 testsのPASSを基準にする。
- userのNo-human-loopとUIモデル選択を優先し、skillの承認待ち・モデル固定・無関係な全suiteは追加しない。独立作業の並行指示に従いbounded workerとprimaryで所有を分け、全差分reviewを保持する。

- CLIのEN/JA成功assertは2 RED（argparse exit2）、pure plannerは39 RED（空plan/未検証）を先に観測する。統合した関連３filesはprimary/workerとも67 PASS。Loop Contract18業務/191jobs/errors0、OSSとdiffもPASS。whole-branch fresh reviewは進行中で、CI/main/releaseは未完。
- whole-branch fresh reviewerはhead8d7ac26a3aで指摘0件。関連67件/新規単独44件PASS。cold importのprovider/subprocess/DB/private state操作0、既存jsonschema同梱schema20件の静的読取を観測する。PR8654のCI/main/完全releaseは未完。
