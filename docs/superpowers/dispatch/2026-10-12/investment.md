# Alpaca investment担当

これはDaisが明示依頼した新規Codex担当。team=lm、統括=lm-orchestrator-1012。提示された旧handoverを現在の状態へ照合して担当goalを完走する。正本はdocs/superpowers/specs/2026-09-25-life-manager-unified-ssot.mdだけ。開始前にREADME、該当SSOT節、skills/loop-development/SKILL.mdを必要箇所だけ読む。2MB SSOT全体をcatしない。旧SHA/PR未統合/容量条件を現在と断定せずfresh main/HEAD/upstream/dirty/lease/runtime/providerを確認し、既完項目をやり直さない。
他担当と共有。dirty root checkout、他担当worktree/branch/profile/stateを編集・revertしない。各lane内の実装は一人でserial、独立laneは並行する。変更は専用worktree/leaseで目的spec→最小RED/GREEN→focused checks→commit/push→PR、primaryが共有releaseと統合を調整する。SSOTは自分のlane節だけ更新し、全体順序はprimaryが管理する。大きなbuild/依存install/release cutを同時に行わず、共有境界は既存lease/lockで直列化する。初回は軽いreadbackとnext atom特定から入り、不要な複製dependencyや大きな一時artifactを作らない。
送信/応募/決済/effect_unknownは公式receiptなしに解除・再送しない。credentials/browser identity/memory/state JSONL/active dirty leased worktree/参照release/Simulatorを保持する。credentialsはprivate SSOTのみ、値をchat/log/specへ出さない。Codex/ClaudeはTelegramへ進捗を送らない（既存業務loopは別）。Mac/loginwindow/App Server restart/raw launchctl禁止、必要なloop操作は既存安全preflight経路のみ。価格・spend cap・本人確認/entitlement境界を守る。過剰なreviewや新frameworkを増やさない。model IDを指定/変更せずUI/account既定を尊重する。
この文書のgoalを自分のruntimeのpersistent goalとして設定し、既存goalがあれば重複作成しない。着手時と節目にAGMSG sendでprimaryへ「owner/owned WT/branch/HEAD/実施atom/検証/公式receipt/残件/次手」を短く報告する。登録やprocessだけを着手/Doneとしない。外部gate/自然run待ちでは独立safe TODOを続ける。成功はsource/fixtureだけでなく本番・自然run・公式readback・replay-zero/費用込み成果まで。百万長者・無故障・世界初は未実証の目標であり保証/広告claimにしない。

/goal Life Manager Alpaca loopがfees/slippage/model/system costs控除後のowner帰属の正のrealized net profitをsettleし、Alpaca/銀行/CFOの同period公式receipt join/replay-zeroで証明する。30 paper round trips/strategy/cross-venue/AT-24/29/fresh反対review前のlive funding/orderは禁止。AT-13は自然qualified sellのみ、手動wake/sell/replayなし。未指定個人資金を使わずunknownを利益にしない。

再開・所有境界:
旧WT investment-paper-lifecycle-pnl-20261009/37e81790、PR #7373の現在統合状態をfresh確認。残りはAT-13のfresh official no-order契約と初paper sell fill→既存QQQ buy/全cost P&L/replay-zero、その後30回等。新実装は .worktrees/investment-goal-20261012/branch fix/investment-goal-20261012、旧dirty/leased WTはread-only。所有はinvestment source/testsと対応SSOT節。金融P&L高リスク判断だけfresh read-only reviewer。

資格情報の保存先・SSOT全体確認・credentials[]のservice完全一致検索・identity/profile/owner/lease確認手順 → ~/.config/ai/core.md「No-human-loop（既定）」を起動時とブラウザ操作前に読む。lane個別の認証境界を保持し、secret値を起動指示へ含めない。
