# AUTOMATON ARTICLE → LAUNCH — full ordered TODO (the single place; do in order)

## Current Writer money order

この順序がWriterの現在の実行cursorである。後続項目は前項のreceiptなしに開始しない。
これは新規Writer loopの構築計画ではない。既に記事生成・Note/Substack/X等への公開実績を持つproduction Writerの
修復計画である。`canary`は「最初の記事」ではなく「今回の修復を反映した最初のproduction検証記事」を意味する。
過去記事を初回扱いせず、既存topic/publication ledgerとの重複0を必須にする。
新規媒体ごとのplatform adapter、固定selector、XPath、DOM script、API wrapper、固定step workflowは作らない。
各device上のLife Manager自身がprovider-neutral Browser ACIで公式画面を毎step observeし、見えているcontrolをモデルが
判断してsignup、login、profile、publish、earnings、payout readbackまで操作する。UI変更時は再observeして判断し直す。
決定論コードはcredential SSOT、browser lease、intent/effect fence、receipt、dedupe、金額計算だけを担う。

## Current execution state — 2026-09-19 JST

これは「Writer loopが毎日公開し、実際に収益を受け取った」と宣言するための現在cursorである。過去の成功記事、テスト、
`launchd loaded-idle`、HTTP healthだけでは公開成功に数えない。対象はLife Manager Main内の唯一のWriter loop
（`article-daily`、同じstateを再開する`article-resume`）で、現在のactive-fourは Note JA、Substack JA、Substack EN、
X Article JA である。Zenn JA、Dev.to EN、X Article EN、X Post JA は dormant のままで、別の有効化receiptが必要である。

### Live runtime readback — 2026-09-19 15:56 JST

- `origin/main` は `ed82c570ce367c66a4e792aacbffa97d2f2ecfaa`。`20260919T153206-ed82c570` を候補として作成し、
  `article-daily` と `article-resume` の両方へtarget-only applyした。両plistのloaded argv/source SHAは `ed82c570…` で一致する。
  `/Users/anicca/loops/current` symlinkは `215d6e53…` のまま（Writer以外の兄弟loopを一括reloadしないため、意図的にglobal currentは変更していない）。
- `article-daily` は loaded `ed82c570…`、`state=not running`、`last exit=0`。run `18d6a5488de1c250-14371` は
  same-JST-day safety blockのno-opで、provider-native publicationは発生していない。
- `article-resume` は loaded `ed82c570…`、`state=not running`。最新run `18d6a6855fccd740-34777`（06:56:37Z）は
  `host_admission_deferred:resource_effect_unknown` で、exact occurrence summary/pre-effect proofと公式provider readbackが無いため保持する。
- `article-healthcheck` は旧 `215d6e53…` loadedのまま。target-only applyとloaded-idle reconcileはともに
  `skipped=pending-admission` で、Writer以外は変更していない。
- host freeは `606,294,016 bytes`（15:56 JSTの最新`df` readback）で、Writer run floor `1,155,780,608 bytes`を下回る。
- 共有 `life-manager-release-reconciler` は別ownerの旧release `09a59ba1…`で稼働中（PID `26051`）。stderrには
  欠損worktree `/Users/anicca/Projects/life-manager-daily-revenue-priority`、`ENOSPC`、`another release build owns` が反復する。
  Writer workstreamからこのownerを停止・再起動・修正しない。

このreadbackにより、以前の「94c622f3を両Writerへtarget apply済み」は過去時点のreceiptとして保持し、現行のloaded SHAには数えない。
W2cのtarget-only applyは完了したが、W2のfresh publicationは次の自然JST日まで未完了である。

### Done

- [x] Writerのbounded executionがdetached child/grandchildを所有PID identity付きで終了させる。source test 3件、focused Writer/runtime test 64件、
      `lm-loop-contract`、immutable releaseのsource/runtime SHA一致を確認済み。ENOSPCで落ちたfull suite 2件は環境容量であり、Writerコードの失敗とは別である。
- [x] Writer-owned `effect_unknown` は occurrence-specific なpre-effect proofまたは公式draft readbackで処理済み。DBのadmission fenceと
      `lm-loop status`の過去イベント表示を混同しない。新しいterminal receiptが出るまでstatusの古いunknown表示は残り得る。
- [x] CTAの固定landing、Life Manager `/start` の帰属ref保存、`writer_attribution_ref` migration、既存のactive-four publisher/gate/replay契約をmainへ統合済み。
- [x] anicca-products PR #407–#410をmergeし、production valid queryのHTTP `302`と決定的`wr_<32hex>` Telegram Locationをreadback済み。保存receiptはbest-effortで、302を売上receiptとは数えない。
- [x] Main `94c622f3…`由来immutable releaseを`article-daily`と`article-resume`へtarget-only applyした過去時点のreceiptを保存済み。
      その後のdriftはW2cで解消した。
- [x] 直近のsame-JST-day safety blockは重複公開を防いでおり、同じrunを再送していない。既存runを「今日の公開」とは数えていない。
- [x] 直前のcanary `20260919-014228` は Note JA、Substack JA、Substack EN、X Article JA の4件を公式readbackし、completion notificationを送信済み。
      ただしこのrunのsourceは現行`94c622f3…`ではないため、最新releaseのfresh canary完了やreplay-zeroの証明にはまだ使わない。

### Not done yet / remaining cursor

- [ ] **W2: 次の自然JST日を1回だけwakeする。** 実測capacity floor `1,155,780,608` bytes以上をreadbackし、最新Main由来の単一immutable releaseでfresh run、
      source article、article固有headline、GPT Image 2 receipt、quality、completionを揃える。同日runの再送や日付偽装はしない。
- [x] **W2a: CTA帰属導線を本番で成立させる。** PR #407–#410、deploy #35424169317、custom domain `302` readbackまで完了。
- [x] **W2b: Life Manager deterministic ref parserをmainへmergeし、immutable releaseへtarget applyした過去時点のreceiptを保存する。**
      PR #5697、Main `94c622f3…`、article-daily/resumeのloaded argv readbackは当時完了。現行driftはW2cで扱う。
- [x] **W2c: 現在のrelease driftを解消する。** 最新 `origin/main` (`ed82c570…`) から
      `20260919T153206-ed82c570` を作成し、`article-daily`/`article-resume`へtarget-only apply。install event
      `097de43691424c93ac6a26e6` / `78a5aaebdf7d7821a9b22b33`、loaded argv/source SHA一致、current symlink不変をreadback済み。
- [ ] **W2d: Writer healthcheckのpending admissionを安全にreconcileする。** `article-healthcheck`だけを
      loaded-idleで再bindし、最新Main releaseのargv/source SHA、state root、terminal receiptをreadbackする。
- [ ] **W3–W6: fresh runについて、Note JA / Substack JA / Substack EN / X Article JAを各provider-native UI/APIでreadbackする。**
      title、body、owner、headline、paywall、live URLを4件すべて記録する。local testやpublisher `rc=0`だけでは完了にしない。
- [ ] **W7: 2回目の自然wakeでreplay-zeroを確認する。** 記事、payment row、notification、Telegram attributionの重複effectを0件で確認する。
- [ ] **W13–W16: 収益joinを完成し、最初のreceived writing paymentを公式provider/payment receiptで確認する。** view、like、pending、available、
      CTA click、Telegram sendだけは売上ではない。最新readbackはNote今月`¥0 / 0 purchases`、Substackはsubscriber/revenueが`-`でunknown。
      received payout receiptと$10K MRRの証明は存在しない。
- [ ] **W17–W21: 7日21 run、14日42 source article、別tenant OSS再現、完全calendar monthのunique net received payoutを順に実測する。**
      完全月のreceived writing payoutがUSD換算で$10,000以上になるまで、目標は未達である。

### Current blockers

1. **最新releaseのfresh canary**: same-day safety blockを迂回して再送することはできない。次の自然JST日まで待つ必要があり、日付を偽装したcanaryは受け入れない。
2. **Writer healthcheck drift**: `article-healthcheck`は`215d6e53…` loaded、target apply/reconcileは`pending-admission`でskipされた。
3. **host capacity**: floorは`1,155,780,608` bytes、今回のfree readbackは`606,294,016` bytes。floor未達ならgeneration前にfail-closedする。
   別ownerのbrowser/session/reconcilerを停止して回復しない。release-reconcilerの欠損worktree/ENOSPCは別ownerの境界である。
4. **provider/payment boundary**: 旧releaseのactive-four canaryはliveだが、現行Main由来releaseのfresh live URLとreceived payout receiptはまだ無い。コード、
      test、loaded/running、provider公開、収益を別々に証明する必要がある。
5. **sales measurement**: private envを正規sourceしてreadback済み。Noteは今月`¥0 / 0 purchases`、Substackは`-`表示でunknown。
   payment receiptが無く、$10K MRRの証明は無い。
6. **dormant surfaces**: Zenn JA、Dev.to EN、X Article EN、X Post JAはactive-four外で、enablement receiptが無い。
7. **resume fence**: `article-resume`に過去occurrenceに加え、最新run `18d6a6855fccd740-34777`の`effect_unknown` claimが残る。
   occurrence-specificな公式readbackまたはpre-effect proofなしに解除せず、日次fresh canaryの完了とは別に解決する。

**Completion rule:** 上記W2a→W2b→W2c→W2d→W2→W3–W7→W13–W21のreceiptが揃うまで、Writerを「毎日全platformで公開済み」「稼働して$10K MRR」とは報告しない。

- [x] W0 stale publication lock互換を修復する。`owner.pid`だけの旧lockについて、実PID不在、start token取得不能、
      directory identity不変を確認した場合だけquarantineし、新lockを取得する。`identity unavailable`を成功扱いの
      exit 0にせずterminal failure receiptへ残す。完了: PR #2952、21 lock cases PASS、production legacy lock回収。
- [x] W1a `lm-loop doctor all`と`lm-loop status all`で全loopのlabel、release、argv、state root、terminal receiptをbefore保存する。
- [x] W1b current `origin/main`からWriter修復を含むimmutable releaseを作る。完了release=`edcc3577`。
- [x] W1c `LIFE_MANAGER_APPLY_TARGET=article-daily`だけをapplyし、release SHA、argv、state root、terminal receiptをreadbackする。
- [x] W1d 同じreleaseから`article-resume`だけをtarget applyして同じ項目をreadbackする。
- [x] W1e 同じreleaseから`article-healthcheck`だけをtarget applyして同じ項目をreadbackする。
- [x] W1f `lm-loop doctor all`と`lm-loop status all`をafter保存し、W1aとの差分がWriter 3 labelだけで、
      sibling loopのrelease/state/plist/argv変更0であることを証明する。自然wakeで進んだsibling receiptは同じownerの
      valid terminal advancementとして分離し、停止・失敗・重複作用へのregressionがないことを確認する。完了:
      doctor hash同一、167 loop中release差分はWriter 3件だけ、3件とも新SHAで自然terminal PASS。
- [x] W1g 未完prepublication runをprunerから保護する。inner provider rc=1の`20260828-043519`が同じpassで
      `deleted`になった再現を閉じ、同じrunのgeneration state・prompt・artifactをresume可能なまま保持する。
      code完了: PR #2956、generation-stateを持つrunはpruneしない5行修正。release `40065a10`へproduction反映済み。
      production完了: run `20260828-083954`はprovider rc=1後もgeneration stateとpromptを保持し、prunerは
      古いterminal `daily-2026-08-18`だけを削除した。
- [x] W1i Writer helper sourceをloaded immutable releaseへ統一する。現在のplistはProgramArgumentsがloops releaseでも
      `ARTICLE_ROOT/ARTICLE_SKILL_DIR/LIFE_MANAGER_REPO`をgig releaseへ向けるため、pruner等が別SHAを読む。
      daily/resume/healthcheckに加え、money/discovery/response/reportを含む全Writer ownerのenvとargvを同じmain由来
      release SHAへ一致させ、他loop env変更0をreadbackする。完了: PR #2962/#2965、14 Writer labelのargv/rootが
      sparse immutable release `40065a10`へ一致。general currentは元full releaseへ復元。
- [x] W1j concurrent apply後の3 label driftをreconcileする。3 labelのowner idleを確認してsparse immutable
      release `40065a10`へtarget applyし、全14 Writer labelのargv、release SHA、`ARTICLE_ROOT`、
      `ARTICLE_SKILL_DIR`、`LIFE_MANAGER_REPO`が同じreleaseへ一致することをplistからreadbackした。
- [x] W1h `article-daily.sh`のinner rc=1をruntime terminal PASSへ変換しない。外部作用0を保持したまま、exact
      release/run/error classをterminal failure eventへ記録し、launchd process resultとbusiness effectを分離する。
      完了: PR #2985で末尾を`exit "$RC"`へ変更し、productionの非zero wakeが`entrypoint_exit_75/78`を持つ
      terminal FAILになることをreadbackした。process successをpublication successとして数えない。
- [ ] W2 修復済みinstalled loopの1回のcanary wakeで、既存記事と重複しない次のsource articleと記事固有のheadlineを生成する。OpenAI Image APIの
      `model=gpt-image-2-2026-04-21`、x-request-id、request model、prompt/response/file SHA、dimensions、alt、rights receiptを保存する。
      現在: restart/rebootは不要かつ禁止された復旧案である。browser/processの自然終了と公式cache/release GCで
      capacityを回復する。PR #2990/#2993/#2998/#3003/#3007/#3009/#3011/#3016/#3020/#3023で、empty resume、
      demand race、preventive disk marker、provider schema、exhaustion、900秒agent、pre-topic receipt、release rebind、
      quality前crashを順に修復する。run `20260828-111213`はJA/EN draftとmediaを生成したがENOSPC前にquality/publicationへ
      到達せず、Note/Substack/Xの新規live URLは0、received writing revenueは0である。headlineはImageMagick生成のため
      GPT Image 2 receipt要件を満たさない。固定5GiBは標準でも収益条件でもないため廃止する。release buildとarticle runを
      同時実行せず、`max(実測release-build peak, 実測article-run peak) + atomic-write reserve`をcapacity receiptへ保存し、
      その実測floorを満たしてmain由来releaseを作る。次にorphan cardをqueueへhash-bound復旧して新runを1回wakeする。
      最新readback: `article-daily`はloaded-idle、毎朝06:00にscheduleされ、`ARTICLE_AUTOPUBLISH=1`である。
      installed release `f7214aac`のwakeは空き約7.37GBでdisk gateを通るが、claim-loop receiptが
      `MODEL_UNAVAILABLE`のためgeneration前にexit 75となる。run `20260828-195017`はgit hashとbaseline strategy receiptだけで、
      article、headline、publication state、public ledger rowは0である。公開ledgerと外部公開面の最新は
      Note JA / Substack JA / Substack ENが8月21日、X Article JAが8月20日で、8月22日以降の新規live articleは0である。
      schedule設定や過去のlive記事を「毎日公開verified」と呼ばない。
      再開readbackではowner不在を確認してclaim-loopを1回kickしたが、provider rc=0/schema validにもかかわらず
      agent resultが空object `{}` となり、`MODEL_UNAVAILABLE`、queue 0、外部作用0を再現した。根因はshared runnerの
      汎用schema `{}` がCodex側で`additionalProperties:false`の空object schemaへ変換されることだった。
      `fix/writer-w2-resume`で空schema時だけprovider-side structured outputを外し、具体schemaと後段JSON validationは維持する。
      release `f8600ca9`をclaim ownerへapplyしたproduction wakeでは有効なSELECTが返り、空object問題は解消した。
      次のblockerは、選択済み価格receiptをbindingが参照したのに上位observation_idsへ重複記載せず
      `DEMAND_CARD_INVALID`となることだった。選択済みimmutable IDだけをdeterministicに集合へ補完する最小修正を進める。
      PR #3120をmainへmergeし、sparse immutable release `c38659a4`をclaim ownerだけへapplyした結果、
      production receiptは`FILLED`、queue 0→1、topic card hash-bound、exit 0となった。article-dailyは未発火で、
      run `20260828-195017`のartifactは依然2 receiptsだけ、外部作用0である。空きが約1.0〜1.3GiBのため、
      article-run capacity floor未達としてgenerationを開始しない。別ownerのscheduled workを触らず自然終了後に再測定する。
      追加のcapacity recoveryでは、plist参照0の再生成可能full release `f8600ca9`だけをsafe GCで回収し約1.19GiBを解放した。
      公式disk governorはprotected deletion 0でfail-closed exit 78、続く90秒観測は空き約1.50〜1.52GiBで安定した。
      topicは`SUFFICIENT`、article ownerはloaded-idleだが、実測article-run peak＋atomic reserve receiptがないため発火しない。
      過去run `20260828-111213`にはENOSPCと生成artifact receiptはあるが開始free/時系列sampleがなく、peakを復元できない。
      current freeは約346MiBまで再低下し最低512MiB reserve未満。公式inventoryの大容量pathはunknown/protectedで手動削除しない。
      残るplist参照0・open file 0のsparse release 2件もsafe GCし7,061,841 bytesを回収した。全release candidateを
      使い切った後もfreeは約328MiB、protected deletion 0、article wake 0。capacity blockerが3 goal turns連続で再現しblocked。
      Daisのcleanup再開指示後、公式governorがexact allowlist済みclosed Chrome code-sign clone内部の`.js/.md`を
      protected sourceと誤判定していた根因を修正した。PR #3172、main/release `54139add`、cleanup labelだけapply済み。
      repair passはclosed clone 3件をlogical 5,937,120,978 bytes回収しactive clone 1件を保存、replayはeffect 0。
      さらにclosed ignored node_modules、Chromium一時download、MediaCrawler venv、npm/clang/node cache、肥大logを回収し、
      current freeは約1.48GiBへ回復したためcapacity blockedを解除する。次のcursorはGPT Image 2 API receipt契約の修復である。
      PR #3194/main `c310f609`でexact `gpt-image-2-2026-04-21` Image APIをintent-fenced exactly-once化し、
      x-request-id、request/prompt/response/file SHA、1536x1024、alt、rights provenance receiptを新runのmandatory media gateへ接続した。
      release `c310f609`をarticle-dailyだけへapplyしたcanary `20260829-165022`はmax free 913,412KiB、min 309,008KiB、
      観測消費604,404KiB。次回floorは消費＋reserveで1,128,692KiBと確定した。reserve割れで`lm-loop stop`し、
      generationは`interrupted-safe`、GPT API intent 0、publication state/ledger/native URL/effect 0。article-dailyはbootout中。
      旧full release `cb8c3917`を指す5分cadenceの`article-resume`が同じrunを再開したため正規stopし、残留Writer gate子PIDだけをTERMした。
      GPT API intent/publication/ledger/native URLは引き続き0。`article-resume`はtarget applyでrelease `c310f609`へ置換し、installed argvをreadbackした。
      closed cacheだけを追加回収し、Codex runtime一時展開528MiBはowner完了後の自動消去、bun/tsx/CodexBar、SiriTTS 268,096KiB、
      mediaanalysisd/CUA cache 142,956KiBを削除した。一時freeは1,330,800KiBでfloorを超えたが、直後にmacOS swapが1GiB増え、
      swap total 15,360MiB/used 14,680MiB、free 456,104KiBへ低下した。swapfileは直接削除せず、他ownerのbrowser/sessionも停止しない。
      target apply後の`article-resume` run 1もfree 630,160KiBで開始したため即bootoutし、GPT API intent/publication/effectは0。
      根因はdaily/resumeがhost実測receiptではなく汎用524,288KiBだけを読んでいたこと。stdlib-only `writer_capacity_floor.py`を正本にし、
      両入口とpublication guardが同じreceiptを使用、壊れた算術はfail-closed、環境変数で測定floorを下げられないよう修復した。
      `capacity/article-run-floor.json`はsample SHA `996cf6a784fc2c85d3d5f7fdf656eba6a4dfcf650c93c6511d161258b17b4455`、
      consumption 604,404KiB＋reserve 524,288KiB＝required 1,128,692KiBをmode 600で保存し、helper readbackは1,155,780,608 bytes。
      PR #3209/main `bc87aeb86`、Writer sparse release `20260830T105811-bc87aeb8`をdaily/resumeへtarget applyした。
      production dailyはfree 253,648,896 bytesに対しrequired 1,155,780,608 bytesをreadbackしてrun作成前に拒否。両ownerをbootoutし、
      旧子PID、GPT API intent/receipt、publication state、external effectは0。次回cadenceが汎用512MiBで誤発火する経路は閉じた。
      最新claim supplyは`FILLED`、queue 1、topic `paid-demand:a594587f90506f1392fee3718065c99e6501abaf66d55b23c213f3605e6ca320`。
      公式cleanup run 20はerrors/protected deletion 0、orphan/shared-cache candidate 0。再生成cacheも0、swap used約14.3GiBでfree 444,076KiB。
      同じfloor未達がresume後3 goal turns以上継続し、他owner停止・swapfile直接削除・Mac restartなしには安全な回復経路がないためblocked。
      W2 canaryはfreeが1,128,692KiB以上へ戻るまで再発火しない。
- [ ] W3 W2修復後canaryのNote JAだけをprovider-native readbackし、title、body、owner、headline、paywall、URLを確認する。
- [ ] W4 W2修復後canaryのSubstack JAだけを同じ項目でprovider-native readbackする。
- [ ] W5 W2修復後canaryのSubstack ENだけを同じ項目でprovider-native readbackする。
- [ ] W6 W2修復後canaryのX Article JAだけを同じ項目でprovider-native readbackする。
- [ ] W7 W2修復後canaryのinstalled loopを2回目wakeし、article、payment row、notificationのduplicate effect=0を証明する。
- [ ] W7a HubPages Earnings ProgramとKompasiana K-Rewardsについて、Dais所有accountのsignup/eligibility、対象国、
      payout identity、税務・本人確認、現行AI/originality規則を公式画面でreadbackする。HubPagesは広告/Amazon、Kompasianaは
      GoPay rewardを直接収益lane候補とする。現在、Substackはaccount、session設定、公開実績あり。ただしfreshな公式
      logged-in画面のreadbackは未取得なのでW3〜W5で再確認する。HubPagesとKompasianaは
      credential SSOT、login session、公式account receiptがなく未作成である。W7aで各deviceのLife ManagerがBrowser ACIを使い、
      公式UIを目で見て両accountを作成し、credential SSOT保存、新規session login、profile/eligibility/payout identityの
      公式画面readbackまで完了する。未適格または受取不能ならdiscovery laneへ降格する。
- [ ] W7b HubPages ENとKompasiana IDを、platform固有adapterなしでLife Manager Browser ACIへ接続する。モデル自身が
      毎action後の公式UIを再observeし、native記事の投稿、live URL、owner、headline、earnings、payoutを目視判断する。
      deterministic boundaryはeffect fence、receipt、replay-zero、money joinだけに限定する。各記事は別topic、
      別reader job、各言語native執筆とし、自動翻訳・近似複製だけの配信を禁止する。Mediumはprimarily AI-generated記事を
      paywall不可とする公式規則があるため、AI開示付きdiscovery-onlyに固定する。
- [ ] W7c W2〜W7とW7a〜W7bのreceipt後、入金を待たず06:00 JA（Note paid + X）、14:00 EN（HubPages、
      Substackは月水金だけ）、22:00 ID（Kompasiana）の3独立slotを開始し、14日で42 source articlesを観測する。
      各slotはunique run/topic、同じidentity/safety/quality/readback/replay-zero gateを持つ。
- [ ] W8 `WinnerObservation` schemaを実装し、source、observed_at、evidence excerpt/hash、fact/inference、
      transfer hypothesisの欠落を拒否する。
- [ ] W9 winner researcher promptを既存research境界へ接続する。
- [ ] W10 mechanism transfer promptを接続し、1変数experimentだけを許可する。platform固有adapterは作らない。
- [ ] W11 article builderとrevenue reviewer promptを既存generation/review境界へ接続する。本文・画像・brand copyを拒否する。
- [ ] W12 learning reviewer promptを既存learning境界へ接続し、losing experimentを保存する。
- [ ] W13 note purchase/fee/refund/payoutをartifact/runへjoinする。
- [ ] W14 Substack purchase/fee/refund/payoutをartifact/runへjoinする。
- [ ] W15 editorial/self-owned purchase/fee/refund/payoutをartifact/runへjoinする。
- [ ] W16 最初のreceived writing paymentを公式readbackする。view、like、pending、availableはrevenue 0/unknownのままにする。
- [ ] W17 3 slotを7 calendar days連続観測し、全21 scheduled source runsのterminal、headline readback、payment attribution、
      Telegram receipt、duplicate=0を保持する。このreceiptが揃うまで「Life Managerは毎日3本公開verified」と宣言しない。
- [ ] W18 14日42本の言語・媒体別received revenue、conversion、engagement、refund、制作costを比較する。入金0でも実験を
      開始するが、継続判断はreceived moneyを最優先する。品質または記事当たりexpected net revenueが悪化したlaneだけを
      停止し、勝っているlaneの頻度は維持または次の一変数実験で増やす。
- [ ] W19 OSS packageを別tenant・別deviceへinstallし、platform adapterや事前accountに依存せず、device-local Life Managerが
      Browser ACIでsignupから開始できることと、credential/state/receipt交差0を証明する。
- [ ] W20 W19 tenantのLife Managerが公式UIをobserveし、account signup/login、実provider draft、headline、publication、
      earnings/payout、money ledgerまでを同じagent loopで完了する。2回目wakeでreplay-zeroを証明する。
      「誰でも必ず儲かる」とは表示しない。
- [ ] W21 完全なcalendar monthのunique net received writing payoutsを受領日ECB rateのFX receiptでUSD換算し、
      $10,000以上であることをreadbackする。rate欠落はunknownで加算しない。
      Writer software revenueはwriting payoutと別streamで報告する。

The end of this list = the product is fully made + announced. Article = `~/anicca-project/docs/articles/
2026-06-11-automaton-jp.md` (worktree `~/.cache/anicca-article-wt`, branch `docs/frank-article`).

## Earn experiment (feeds the article numbers)
- ☑ FIXES live: cook query, buffer/close-in-profit steer + loop-break, deposit guard, dashboard HL, earn-arg bug.
- ☑ #9 FREE re-run (plumbing fixed): 22 wakes / ~64 min / **realised +$0.1676** (trade only; x402/yield/cook = $0).
- ☐ #2 PREMIUM run: switch the live instance to a frontier model, 20–30 wakes, record per-tool realised P&L
      (prereq: free liquid via the HL close it already did). Then revert to free.

## Article (JP-first; reader-facing, never a bug-log; lead with TIME × MONEY per tool)
- ◐ [6]③ free row written (+$0.17, per-tool journey). ☐ add the [6]③-premium row from #2.
- ☐ [6]① clean the residual English (free/gpt-oss-120b, the [WAKE UP] code block) → plain JP.
- ☐ [7] conclusion = the whole-article summary (free vs premium, what earned, the honest takeaway).
- ☐ [0] hero = the whole finding up top (so a reader needn't read it all) + a 目次 / timeline to click through.
- ☐ De-slop pass (default-ON: stop-slop + stop-ai-slop-jp blocklists, Claim|Evidence|Status, 音読).
- ☐ #4 English version (translate JP → EN, dev.to/Substack/X).

## Skill (so this becomes repeatable, no-human)
- ☐ #12 ITERATE `~/.openclaw/skills/ai-entity-article-writer` (DON'T delete) — playbook now has rules 16–18
      (journey-not-buglog, time×money, de-slop default-ON). Integrate stop-slop/jp blocklists + research-paper
      Claim|Evidence|Status into the gate scripts. cody = ideas only (proprietary).

## System hygiene (not blocking the article)
- ☐ #10 fix pre-existing failing tests (selectTier/config/integration).
- ☐ #11 portfolio-realtime: read ALL venues via a shared net-worth module (DRY = Don't-Repeat-Yourself, a
      code-reuse principle — NOT a "dry/fake run". The numbers stay 100% real on-chain reads.)

## PHASE E — PUBLISH everywhere + LAUNCH (the finish line)
- ☐ #6 publish JP (note / Zenn / Substack / X Article) → EN (dev.to / X Article) → product launch post.
- ☐ demo video (YouTube) for the launch.
- ☐ LAUNCH ANNOUNCEMENT (canonical copy, Dais-approved 2026-06-22):

  人間の介入なしで、自分の計算コストを払い、稼いだ収益を生命に配布するAIを開発しました。
  ・APIキー不要。クラウド・ローカルで動作。Baseウォレットに USDC課金すると、有料モデルを利用。
  ・現在は、クラウドで３体・ローカルで1体。全個体の収支はリアルタイムで公開中。
  ・自己監視・自己修復・自己改善・自己増殖・日次報告を繰り返す。
  ・収益の一部を、生命に対してベーシックインカムとして毎日配布。
  ・何兆体のAIがGithub Issuesで共進化しながら、全体としてより総資産を増やすことを目指す。
  https://github.com/Daisuke134/life-manager
  記事：X Articleのリンク
  デモ動画：Youtubeリンクを添付
