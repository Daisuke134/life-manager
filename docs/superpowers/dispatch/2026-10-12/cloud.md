# Life Manager Cloud担当

これはDaisが明示依頼した新規Codex担当。team=lm、統括=lm-orchestrator-1012。提示された旧handoverを現在の状態へ照合して担当goalを完走する。正本はdocs/superpowers/specs/2026-09-25-life-manager-unified-ssot.mdだけ。開始前にREADME、該当SSOT節、skills/loop-development/SKILL.mdを必要箇所だけ読む。2MB SSOT全体をcatしない。旧SHA/PR未統合/容量条件を現在と断定せずfresh main/HEAD/upstream/dirty/lease/runtime/providerを確認し、既完項目をやり直さない。
他担当と共有。dirty root checkout、他担当worktree/branch/profile/stateを編集・revertしない。各lane内の実装は一人でserial、独立laneは並行する。変更は専用worktree/leaseで目的spec→最小RED/GREEN→focused checks→commit/push→PR、primaryが共有releaseと統合を調整する。SSOTは自分のlane節だけ更新し、全体順序はprimaryが管理する。大きなbuild/依存install/release cutを同時に行わず、共有境界は既存lease/lockで直列化する。初回は軽いreadbackとnext atom特定から入り、不要な複製dependencyや大きな一時artifactを作らない。
送信/応募/決済/effect_unknownは公式receiptなしに解除・再送しない。credentials/browser identity/memory/state JSONL/active dirty leased worktree/参照release/Simulatorを保持する。credentialsはprivate SSOTのみ、値をchat/log/specへ出さない。Codex/ClaudeはTelegramへ進捗を送らない（既存業務loopは別）。Mac/loginwindow/App Server restart/raw launchctl禁止、必要なloop操作は既存安全preflight経路のみ。価格・spend cap・本人確認/entitlement境界を守る。過剰なreviewや新frameworkを増やさない。model IDを指定/変更せずUI/account既定を尊重する。
この文書のgoalを自分のruntimeのpersistent goalとして設定し、既存goalがあれば重複作成しない。着手時と節目にAGMSG sendでprimaryへ「owner/owned WT/branch/HEAD/実施atom/検証/公式receipt/残件/次手」を短く報告する。登録やprocessだけを着手/Doneとしない。外部gate/自然run待ちでは独立safe TODOを続ける。成功はsource/fixtureだけでなく本番・自然run・公式readback・replay-zero/費用込み成果まで。百万長者・無故障・世界初は未実証の目標であり保証/広告claimにしない。

/goal Life Manager Cloudを販売可能なWebアプリとして仕上げ、計測可能なmarketingを継続し、Stripe公式readbackでgross MRR $10,000を確認する。Google Calendar接続→Google本人確認/Calendar許可→同画面の接続完了と7日カード必須trial/$29月額→バックエンド自動処理→Google Calendar日常利用を保つ。dashboard/scan/Web chatを作らず、価格変更・live自己決済なし。Google既存認証sessionのみ、新規login/recoveryなし。

再開・所有境界:
旧PR #7366/branch fix/lm-cloud-calendar-proxy-20261009/tip9aa88892は歴史context。main統合/Calendar E2E/Stripe TESTが既完か先に確認する。最新はSDK/production health/stream startup確認済み、実iPhone pairing/reply未完。docs/superpowers/plans/2026-10-06-life-manager-web-first-travel.mdを読む。旧MFA/実端末gateを捏造で閉じない。Cloud source/marketing adaptersだけ所有、CFOとeBookのStripe分類コードは編集しない。既存cloud-readiness担当の作業を先に照合し、重複はprimaryへ連絡。
