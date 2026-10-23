# Monk Factory Web 設計

## 目的・範囲・完了条件
DaisのDatabaseとMonk Factory Web appを公開する依頼を実装する。日次投稿はGrok Botが所有し、既存自社アカウント・loop・未完投稿・容量復旧は操作しない。既存Factory CLI/MCPとrepoのNode.js 24.16+/npm 11 runtimeを使い、利用者がWebで制作内容を保存し、手元の有限agentから台本→計画→生成→素材確認→投稿と公式状態照合を進められるアプリを公開する。無料で公開できるため販売/契約を公開gateにしない。収益・最大followers・USD10K MRRの達成は別の実測成果として未達を保持する。

完了条件は公開Webの実draft作成/保存/export、同一UIのlocalhost起動、project/runの永続保存、実CLI offline planと有限agent接続、既存provider/fence/unknownの保持、必要なfocused tests・独立レビュー・CI/main・固定版/公開URL readbackである。自社への実課金/実投稿は今回実行しない。provider未設定や費用不明を生成/公開成功へ変えない。

## 選択
primaryの判断として、公開static Web workspaceと同じUIをlocalhostで動かす構成を選ぶ。既存onboarding serverの127.0.0.1/同一origin形を踏襲する。公開HTTPSからlocalhostへ直接fetchする方式はbrowser制約と接続秘密を増やすため採らない。hosted multi-tenant auth/課金/credential保管は不要な別系統を増やすため先行しない。単なる紹介ページやコピー用promptだけでは利用者の制作状態を保存・実行できず、今回の成果に足りない。

## 正本と配布
Factory sourceとUIの正本はLife Manager内 skills/earn/marketing-engine/factory-web/。既存factory-mcp.mjsのcallFactoryTool/runCliを使い、renderer/publisherを複製しない。公開anicca-productsは同UIをLife Managerのimmutable main SHAとSHA256でbuild時stageする。公開URLは /ai-monk-factory/。既存 /factory は別商品なので上書きしない。公開UIはブラウザ内draft/exportを実行し、localモードはsame-origin APIへ接続する。

## project/run契約
project v1は12 fieldsの project_id, language(en/ja), avatar_id, voice_id, platform(tiktok/instagram), integration_id, native_handle, product_name, product_url(HTTPS), brief, script, cta を持つ。secret fieldと未知fieldを拒否する。draft保存時はproject_id/briefを必須とし、provider/商品設定の空文字を許可する。値があればformatを検証し、run開始時は全設定を必須にする。scriptはagent生成前の空文字を許可する。共有validateProject(value, {ready=false})をUI/serverで使う。API keyは既存の利用者HeyGen認証/Postiz環境だけを使い、Web/JSONへ保存しない。project_id/run_idをserverで検証し、path/argv/env/state_rootをAPIから受け取らない。

run modeは plan/render/publish。planはprovider操作を許可せず、renderは生成まで、publishは利用者が最初に選んだ一連の生成/確認/配信を許可する。毎回確認を要求する別manual gateは追加しない。run_idはserverで発行し、project編集で過去runを変更しない。run固有input/agent workspace/control evidenceを分け、取得済みCLI receiptをframe抽出前に1回保存し、最初のFactory planで台本/投稿文をsnapshotに固定し、後続CLIは同じsnapshotだけを使う。config state_rootはserver専用run出力に固定、既存host lock/cost/fenceのrootは変えない。

## 有限agent
既存共通agent_runnerはmodel必須なので今回のモデル継承に合わない。薄いcodex exec --sandbox workspace-writeの有限呼出を使い、-m/--model/model_providerを指定しない。既存認証・利用者のCodex model/provider設定を継承する。他のMCP名を有限のread-only inventoryでRAMへ読み、実行時だけ無効化し、正式feature switchでplugins/remote_plugin/apps/enable_mcp_apps/codex_apps_mcp_2026_07_28を無効化する。network=false、追加writable_roots=[]、tmp除外を実行時に固定し、Factory用bridge以外からmode権限を拡張しない。1run同時1agent、長時間処理はHTTP応答から分離し、reload/再起動後もrun ID・実exit・結果を保持する。中断は完了と表示せず、自動で新runに再送しない。run予約の時点から中断signalと完了待機を保持し、shutdown完了後にはagentを開始しない。費用未照合と失敗はrun全体の履歴から集約し、後続statusの成功表示で隠さない。

agentは製品事実/briefから台本とcaptionを作り、実動画のframe/audio metadata等を観測して確認者をAI agentとして記録する。人間の確認を捏造しない。レビュー用frameはreceiptで検証した動画からserver側で抽出し、frame hashをcontrol evidenceへ固定する。任意画像やPNG署名だけを動画確認の根拠として受け付けない。server-bound MCPは任意pathを受けず既存callFactoryToolへ固定path/run/production値を渡す。publishのprepare/shadow/route-check/upload/draft/promote/status/postiz-readbackを再利用し、公式receiptが無いnative確認や売上は未確認とする。agent最終文章を公開成功の根拠にしない。

## localhost境界と表示
127.0.0.1のみbind。Host/Originを正確に照合し全APIに起動ごとのaction tokenを要求する。CORSは開けない。body/output上限、任意path拒否、symlink/path traversal拒否、秘密を含まないerror、process group timeout/終了処理を持つ。runのcontrol evidenceはagent workspace外へ保存する。video endpointはそのrunのCLI receiptでpath/SHA一致を確認したassetだけを返す。

UIはcream/ink/greenの落ち着いた制作workspace。project一覧、brief/商品/チャンネル設定、台本、実run状態と成果物を同じ画面で扱う。placeholderの再生数/収益/成功進捗を表示しない。公開側ではdraftをlocalStorageへ保存しJSON export/importできるがtoken/secretは保存しない。export/importはUTF-8 byteの同一上限65536を使い、各fieldの上限内の日本語draftを往復できる。local側ではserverに保存し、plan/produce/publishと実exit/provider状態を表示する。

## 規律と不足
Superpowers brainstorming/writing-plans/TDD、ponytail fullを使う。DaisのNo-human-loopと明示委任に従い設計承認待ちを置かず、primaryの実装判断を本設計へ記録する。model overrideを要求する下位の役割慣習は使わない。projectの無料trial禁止は、無料公開でもよいという最新の明示指示へ置き換える。審査・公開状態は公式providerで別途確認する。Muse URLは確認待ち、ChatGPT plugin portalの本人確認も別cursorとして独立作業を止めない。

## 完成形と現在の優先範囲
Daisが求める完成形は、利用者自身のTikTok接続を入口に、avatar・台本・動画制作・投稿を自動実行するWebサービス。現在受入した公開draft/local planはその初期workspaceであり、接続型SaaSや無人収益の達成とは区別する。現在はDatabase→CLI→plugin配布・販売条件を優先し、Factoryの追加実装を後回しにする。日次自社投稿はGrok Botが所有する。
