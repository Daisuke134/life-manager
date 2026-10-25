# Manager — 追加一次資料に基づくatomic patch plan

> **For agentic workers:** Use the applicable Superpowers implementation procedure when available. This plan began as research/specification work; the user's later explicit instruction authorized source implementation. Unchecked implementation steps remain incomplete and must not be reported as completed behavior.

**Goal:** 既成のruntime・agent・renderer・評価資産を比較し、E16の本番接続と証拠からの出版を、実ファイル単位で進める。
**Architecture:** 既存の権限/intent/outbox/正確なprovider照合を核として維持。汎用scheduler/memory/browser/eval engineを増やさず、既存部品へ最小接続する。DBOSを最初のdurable-runtime適合比較とし、製品名だけで移行を確定しない。
**Tech Stack:** 現core Python>=3.11、SQLite、GitHub既存publisher、Playwright/axe、既存python-pptx/FFmpeg/記事installer。追加runtimeは比較後に固定版とlicenseを確認。
**Spec:** [製品仕様](../MANAGER_PRODUCT_SPEC.md)、[追加選択肢調査](../research/manager-options-additional-20261022/REPORT_JA.md)。

**実行再開の記録（2026-10-25）:** 後続の継続指示でsource実装へ進んだ。PATCH-01、PATCH-02の送信境界と隔離比較、PATCH-04のcollector/typed delivery、PATCH-06のローカルSQLite backup/isolated restore＋quarantineを実装・P0検証した。PATCH-05ではrequest schema、Railway runtime preflight、versioned main admission/receiver、durable request outbox、one-shot sender、read-only workflow run reconciliationに加え、main SHA/gh-pages親/公開bytesを照合して候補からrequestを作る有限cycleと、旧effectのoccurrence/delivery先行reconciliationを実装。workerはunknownな旧effectを越えて新requestを送らない。ローカルfake transport/testsは通過したが、owner secrets、専用Railway service/volume、通常のmain promotion、実workflow run/readback、PATCH-06 host/volume実機試験、E16実配備受入れは未達。実結果は [recovery receipt](../verification/E16_RECOVERY_HARDENING_20261022.md) と本追記を参照し、未チェックを本番完了と読み替えず、既実装部分を再作成しない。

## Global constraints

- 状態・依存・Eカーソルは既存 [tasks.json](../roadmap/tasks.json)。PATCH番号は派生実装単位であり、新task/進捗authorityではない。E16と原113件の状態をこの文書だけで進めない。
- `OwnedEffectRecord.dispatch` はfresh reservationの一時的な判断。別stepのcheckpointに保存して送信許可として再利用しない。retryable `host.send` を単独でdecorateしない。
- 書込み前のexact source/artifact/owner/scope/target-parentを検査。UNKNOWNはreconcileするまで再送しない。fixtureのlive禁止、7パス、元publisherを維持。
- 現行SOURCE_REFを研究branchへ書換えて通さない。mainへの正規promotionと旧publisher契約の移行が必要なら、別のversioned admission変更としてレビュー/検査する。
- 本番run、published、paid、offer、YC accepted、人の便益はそれぞれ真正な外部証拠で判定。今回のdocs commitはそれらの完了ではない。
- third-party codeのlicenseとhosted契約、paperのtask assets/人物データ/図版の権利を分離。素材の再配布不明をrepo licenseで上書きしない。

## Review focus

1. 候補/contextが変化、scope失効、provider停止、NOT_DUE/STOPPEDの場合も過去UNKNOWNを読取照合し、新keyで同じ対象のfenceを逃れない（PATCH-01/04）。
2. 外部commit後に応答やengine checkpointが消失しても、cached dispatch許可を再生せず一度だけ送信（PATCH-02）。
3. tick記録後crash、古いbackup、二重ownerで、完了を捏造せず、失われた予約を不存在としない（PATCH-02/06）。
4. provider commit確定とserved bytes到達を分け、lagやpost-dispatch timeoutを二度目の書込み理由にしない（PATCH-04/05）。
5. benchmark paperとcodeの食い違い、無許諾assets、PDF/EPUB/MP4の偽装、画像PPTXの編集可能扱いを拒否（PATCH-07〜10）。

## 共通の実行規則

挙動を変えるpatchは、指定testを先に追加してREDを確認→対象helperの最小実装→同じtestをGREEN→関係する既存検査→差分レビュー→commit。docs-onlyの判断/台帳変更には実装を写すtestを追加せず、source/JSON/link/diffを確認する。異なるpatchのledger/schema/publisher変更を並列で書かない。コマンドは特記なき限り `products/manager/` から実行する。docs-only調査で未来のRED/GREENを実施したとは記録しない。

## PATCH-01 — 過去intentを新candidateより先に回収する

**Files:** Modify `manager_core/outbox.py::OwnedEffectJournal`、`manager_core/reconcile.py`、`manager_core/owned_cycle.py::run_owned_cycle`; Create `tests/test_owned_recovery_order.py`。
**Consumes:** `OwnedEffectRecord`, `reconcile_owned(journal,key,read_occurrence,observed_at)`、保存済みpacket/expected_parent。
**Produces:** `OwnedEffectJournal.pending_records(limit=100,after_key=None) -> tuple[OwnedEffectRecord,...]`、`reconcile_pending_owned(journal,read_occurrence,observed_at) -> tuple[ReconcileResult,...]`。最初のpatchでは未確定provider occurrenceを対象とし、PRESENT後のdelivery未確認はPATCH-04が扱う。

- [ ] RED `test_old_unknown_reconciles_before_changed_candidate` / `test_expired_scope_does_not_hide_old_occurrence` / `test_not_due_or_stop_still_allows_read_only_reconcile`。`prepare_owned_change`を呼ぶ前に過去key照合、`send.call_count==0`、保存parent/packet不変、未解決なら新key dispatchなしを検査。
- [ ] Run `python -m unittest discover -s tests -p 'test_owned_recovery_order.py' -v`。現コードのcurrent-key依存で失敗することを確認。
- [ ] `pending_records(limit=100,after_key=None)` はSQLで非PRESENT行をkey順に列挙、limitは1〜100、after_keyで次batchへ進む。未走査または未解決があれば新dispatchをblockし、各保存packetで既存reconcilerを呼ぶ。owner_lockの後、due/prepareより前に置く。停止中は読取のみ、新しい実行は許可しない。単発not-foundはUNKNOWN。
- [ ] GREEN同test＋実在する `test_digital_cycle_acceptance.py` / `test_owned_effect_recovery.py`。新test名だけを実装済みだと書かない。
- [ ] Commit: `fix(manager): reconcile prior owned intents before planning`。

## PATCH-02 — 送信許可をcheckpointで再生しない。DBOSと現在方式を同条件で比較

**Files:** Modify `manager_core/owned_cycle.py`; Create `scripts/compare_owned_runtime.py`, `tests/test_owned_dispatch_replay.py`; isolated optional adapter `manager_core/adapters/dbos_owned.py`は適合試験に進む時だけ追加。
**Consumes:** PATCH-01 journal、元の `admit_release`、既存host lock/CAS。
**Produces:** `dispatch_owned_once(state_store,host,packet,now) -> dict`。戻り値はeffect key/status/receiptのデータだけ。再生可能なdispatch permissionを返さない。probe出力はbackend/version/source/failure_case/dispatch_count/receipt/status/limitations。

- [ ] RED `test_replayed_step_result_cannot_reuse_dispatch_permission`、`test_commit_then_engine_checkpoint_loss_does_not_resend`、`test_engine_dedup_expiry_does_not_bypass_journal`、`test_slot_claim_crash_is_not_completed_effect`。
- [ ] Run `python -m unittest discover -s tests -p 'test_owned_dispatch_replay.py' -v`。
- [ ] fresh journal lookup→pure admission→reserve→guarded sendを同じlock内helperにまとめる。再開はjournalを読み直す。新しいfresh reservationだけ送信できる。既存sandbox型guardは保持し、比較用runtimeに本番権限を与えない。
- [ ] DBOS+SQLiteを最初の候補として隔離比較。固定監査commitから実際のinstall pin/依存/SQLite制約を再確認し、同一6crash点とread-only多段階再開/長期waitで現在方式と比較する。core defaultに無条件dependencyを追加しない。結果保存だけのunit testをdurable engine実行と呼ばない。
- [ ] 判定: 全fence検査合格、Python/lock/backup適合、実際に手書き復旧を減らすなら既成runtimeへschedulerを委譲。満たさない場合は既存single-workerを維持し、tickは完了証拠ではないと記録。custom workflow engineの増築はしない。
- [ ] Commit: `fix(manager): fence replayed dispatch across durable runtimes`。

## PATCH-03 — 既成agentを直接使うbaselineを製品判断へ入れる（docs-only）

**Files:** Update `docs/product/FIRST_WEDGE.md`, `docs/MANAGER_PRODUCT_SPEC.md` の利用場面/代替比較。新しいadapter、memory、scheduler、tool executorはこのpatchで作らない。

- [ ] 比較欄を `user_job / native_alternative / existing_interface / missing_boundary / evidence / operating_cost_unknowns / decision` に固定する。
- [ ] 個人の予定調査はOpenClaw/Khoj、定型の取得/通知/更新はn8n/Activepieces、業務agentはGumloop/RelevanceAI/Lindyを直接使うbaselineとして、確認済みsourceを対応させる。
- [ ] Managerでしか必要条件を満たせないと未実測のまま書かない。未充足がなければ `USE_EXISTING_PRODUCT`、authority/effect/readbackが未充足なら `TEST_THIN_MANAGER_BOUNDARY`。顧客の既存作業と同条件比較がまだなら `UNVALIDATED`。
- [ ] source/link/diff確認後にcommit。remote agentの実接続は未充足が確認できた後の別patchで、現時点の必要作業へ数えない。

## PATCH-04 — 公式occurrenceとdelivery待ちを独立に回収

**Files:** Create `manager_core/owned_public_collector.py`, `tests/test_owned_public_collector.py`; Modify `scripts/phase06_kernel_release.py::{public_get,immutable_snapshot,live_snapshot,prove}`を再利用可能に整理、`manager_core/reconcile.py`、`manager_core/outbox.py`、`manager_core/owned_cycle.py::run_owned_cycle`。
**Consumes:** immutable packet+expected parent、元の `validate_commit_receipt` と `verify_readback`。
**Produces:** `collect_owned_occurrence(key,journal) -> OwnedOccurrenceEvidence | None` と `collect_owned_delivery(key,journal,observed_at) -> dict`。`PRESENT` はcommit証拠に留め、独立delivery receiptはkey/commit/candidate hash/observed_at/proof referenceを保持する。`DeliveryObservation.status` は `VERIFIED|PENDING|REGRESSION|UNKNOWN` とし、boolへ潰さない。

- [ ] RED `test_delivery_lag_or_timeout_does_not_rollback` / `test_confirmed_regression_rolls_back_once_with_exact_target`。wrong repo/parent/key/body、ページング先の同名commit、redirect、部分body、provider success+served lag/timeout/missingではrollback0、PRESENT後のreadback-before-crash、別ownerがtargetを進めた場合は復元しないことを検査。データのdict/dataclassを渡しただけでは公式collector経由の証明にならない。
- [ ] Run `python -m unittest discover -s tests -p 'test_owned_public_collector.py' -v`。
- [ ] 固定origin・SHA・全7fileの既存GETとvalidatorを共用する。provider occurrence探索は完全一致とpaginationを要求し、見つからない/制限はUNKNOWN。delivery receipt未確認のPRESENT行も起動時に回収する。歴史的に検証済みの旧deliveryと現在の公開版を混同しない。
- [ ] `run_owned_cycle` の現行 `elif host.readback(...): ... else: stop/rollback` をtyped observation分岐へ変更する。served lag/timeout/missingはPENDINGまたはUNKNOWN、bounded read-only poll後も未確定ならUNKNOWN、`rollback_writes=0`、publish再送なし。hash mismatchだけではREGRESSIONにしない。REGRESSIONは、現在のexact candidate target/公式deployment完了に結び付いた観測bytesに対し、固定technical rubricで実際の回帰を確認した場合に限定し、rollback直前にもtarget CASを再確認する。receiptはprivate owner store、公開集計は必要最小限。P0 sandbox receiptとは別schema/collectorを用いる。
- [ ] GREEN＋既存publisher/readback tests。Commit: `feat(manager): collect exact owned occurrences and delivery separately`。

## PATCH-05 — workerから既存の特権publisherへ接続する

**Files:** Create `manager_core/owned_platform_host.py`, `tests/test_owned_platform_host.py`; Modify `scripts/run_owned_digital_cycle.py`、`scripts/phase06_kernel_release.py::admit_owned` と `.github/workflows/manager-phase06-service.yml` の必要最小bridge。
**Current evidence:** 既存workflowは旧research refでCLI `admit`を実行していた。2026-10-25にmain intent v2とmainのworkflow_dispatch＋owner requestを要求するreceiver入口、durable request outbox、one-shot sender、exact GitHub run lookup、Railway identity preflight、main source/Pages baseline/served bytesを照合してrequestを作る有限worker cycle、過去effect occurrence/deliveryの先行reconciliationを追加。未確定過去effectは新requestを止める。コード・fake transport/SQLiteの範囲で検証し、実Railway host/volume、owner secrets、通常promotion、実workflow/readbackは未達。接続済みChatGPT pluginの認証がRailwayへ自動で渡るとも扱わない。
**Produces:** workerはproposal/effect keyを送るだけ。特権jobが同一の固定source/artifactを再構築・照合し、scopeとassessmentを再検証し、元の7-file guard/CASを実行。hostのconstructorやenv flagは権限ではない。

**2026-10-25 implementation receipt:** `manager_core/owned_platform_host.py` defines `manager.owned-workflow-request.v1` (owner, effect key, immutable packet digest, source SHA, expected parent, request ID) and strict parser/rebinding. Requests can only be created from the fixed `main` intent version. The digest covers every validated packet field except its short-lived created/expiry timestamps and self-digest. The SQLite outbox atomically reserves request/effect; its atomic `READY→SENDING` claim also marks the effect `DISPATCHING`, while a not-yet-sent request remains `RESERVED`. POST is fixed to the exact repository/workflow/main ref; timeout and ambiguous responses remain UNKNOWN and never resend. Run lookup filters exact request title, branch, event and source SHA across at most ten pages; a duplicate across pages is retained, while a full page bound leaves uniqueness UNKNOWN. `read_railway_runtime_identity` binds Railway project/environment/service/volume values to separately supplied expected IDs, requires the `Daisuke134/life-manager` `main` SHA, a separate mounted state directory, explicit owner enablement, bounded cadence and a present dispatch credential; the credential is not returned. `digital-handoff.v2` preserves v1 reads/admission while allowing only fixed `refs/heads/main` for the new version. The workflow binds main requests to protected `MANAGER_OWNER_ID`, current Pages HEAD and the original seven-path release guard. `run_owned_workflow_bridge_once` now performs the complete source-level cycle: it reconciles old occurrence and delivery records first, confirms Railway source SHA equals current main, confirms the gh-pages manifest and each published page match the live served bundle, builds the checked-in support catalog for that SHA, and reserves/submits at most one request when due. A regression test confirms an unresolved older effect blocks the newer request without POST. The entrypoint is wired to the finite cycle, not just an existing-request drain. Focused request, sender, replay/race, bounded-run-pagination, worker, prior-effect barrier, runtime-preflight, main-admission and workflow-structure tests pass. This remains local fake-transport evidence; no owner secrets, dedicated Railway service/volume, ordinary main promotion, real workflow/commit/readback, or host restart/restore proof is connected.

- [ ] RED fake owner/env、wrong source/artifact/run、changed scope/target parent、replayed request、fixture host、tokenがagent出力へ渡るケースを拒否。
- [ ] RED fake owner/env、wrong source/artifact、changed scope/target parent、extra/duplicate request fields、malformed request JSON、token exposureを拒否。**Partial:** request field/parser/owner/packet/parent cases are covered; workflow run/artifact authenticity, durable replay at the receiver, and credential-redaction across an actual agent output path remain untested until a receiver exists.
- [x] Worker request schema version-fixes effect key/packet digest/owner identity/source commit/expected parent; no model-selected artifact URL or callback is accepted. Strict parser and rebinding tests pass.
- [x] Railway runtime identity preflight rejects wrong configured project/environment/service/volume, non-main/wrong repository source, missing mount separation, disabled/unbounded owner config and missing dispatch credential without returning the credential. It is wired to the finite cycle CLI; **fake environment/mount test only, with no live Railway deployment.**
- [x] Main向けversioned admissionを追加。`digital-handoff.v1`/旧SOURCE_REFを保持し、新`v2`は厳密な`refs/heads/main`＋actual workflow contextだけを受入れ。今回研究branchはallowlistへ追加しない。
- [x] Existing jobのsame-run artifact、actual workflow context、7-path guard/CAS、既存Pages workflow委譲を維持。main入口にowner request inputを追加し、fake Git integrationでwrong owner/event/release toggle/target parent/replayを無書込みで拒否。
- [x] Railway sender・durable request outboxとbounded cycleを実装。固定repository/workflow/ref以外へ送らず、HTTP 204は「run accepted」に限定し、timeout/connection lossはUNKNOWNとして同じrequest IDをread-only照合する。source SHA・gh-pages parent/manifest・live bytesから候補とrequestを作り、古いeffectのexact occurrenceとdelivery readbackを先にreconcileする。UNKNOWN/未読戻しなら新規requestを止め、過去要求を再送しない。Fake HTTP/SQLite/public-reader fixturesのみ。**実host接続は未達。**
- [ ] GitHub protected `MANAGER_OWNER_ID` / `MANAGER_RELEASE_ENABLED` settingsと実workflow run/readbackを確認。未確認ならCLI/workerはexit2・write無しを維持。
- [ ] GREEN unit/contract→レビュー→通常promotion→1canary→official readback→replay-zero。Commitと配備証拠は別。

## PATCH-06 — host設定・backup・restoreを実物で検証

**Files:** `deploy/owned-digital/Dockerfile` と product-level `.dockerignore`、`scripts/owned_runtime_entrypoint.py`、`tests/test_owned_runtime_entrypoint.py` を追加。`scripts/backup_owned_cycle.py` と `tests/test_owned_state_recovery.py` は既にlocal実装済み。Railway service settingsはconnector経由で別途管理し、`railway.json` は作らない。
**Produces:** main由来のimmutable container source、private `/data/manager`、単一owner、finite hourly cron tick、start時のmount/ID検査後に非root UIDへdrop、stop/backup/restore/health/費用記録。backupはstdlib `sqlite3.Connection.backup`を使う。
**Platform basis:** 2026-10-25に一次資料を再取得。Railway Cronは短命で完了後exitするtask用、UTC、5分以上の間隔、前runが続くと次runをskipする。system varsにはproject/environment/service/deployment/volume name/mount pathとGit repository/branch/SHAがある。Config as Code (`railway.json`/`.toml`) はdeprecatedでnew servicesはopt-in不可、2026-12-01 cutoff。従ってmain promotion後、Manager専用staging service/volumeへ`rootDirectory=products/manager`, Dockerfile path=`deploy/owned-digital/Dockerfile`, volume mount=`/data/manager`, `cronSchedule=0 * * * *`, one replicaをRailway settingsで設定する。現行 `MANAGER_INTERVAL_SECONDS=3600` と整合する。公式根拠: [Cron Jobs](https://docs.railway.com/cron-jobs), [Variables Reference](https://docs.railway.com/variables/reference#railway-provided-variables), [Config as Code](https://docs.railway.com/config-as-code)。

- [ ] RED tmp/ephemeral/source配下state、reservation前/後のstale restore、許可外sourceからのproduction起動。**一部済み:** 同時owner/backup corruption/source内state/non-overwriting restoreは追加testでRED→GREEN。
- [x] `python -m unittest discover -s tests -p 'test_owned_state_recovery.py' -v` — 3 test pass (2026-10-25; local fixture only)。
- [x] Local DB online-backup API→integrity/hash→新規隔離先restore。古いsnapshotを起動cycle/direct dispatch両方で拒否。
- [ ] Production起動時に元parent/packetのofficial occurrenceを読み取り回復し、回復不能なら隔離を維持する。restored markerを解除する手順は実hostとofficial collectorでのみ設計/検証する。backup取得後の外部commit欠落を新しいparentで再予約しない。
- [x] Source package: Docker context allowlist、Python 3.12 slim image、systemd-free finite entrypoint、mount/ID preflight後のsingle-inode chownとUID/GID 10001へのdropを追加。local Docker image build pass。設定なしでは`DEPLOYMENT_HOST_REQUIRED`、fake identity＋temporary mount＋network-noneではpreflight通過後に`UNKNOWN / MAIN_HEAD_UNAVAILABLE`・effect writes=0で停止。**Railway実volume権限/cron/実workerは未検証。**
- [ ] Railwayの専用staging service/volumeでlock・kill/restart・restore・単一catch-up・停止時間・費用を観測。現在の既存serviceは用途確認まで保全。productionはnormal promotion後のみ。
- [ ] E16/F受入を実receiptで判定し、それ以前はBLOCKEDを維持。

## PATCH-07 — 新benchmarkの権利と採点不一致を台帳へ反映

**Files:** Update `docs/research/evals/UPSTREAM_CODE_AUDIT_20261022.md`, `docs/research/source-rights.json`, `docs/research/manager-options-additional-20261022/`。既存 `manager_core/eba_benchmark.py` のinterfaceを確認してから新fixturesを接続。

- [ ] DuMateBenchは論文の採点式と固定codeの採点式を別列に保存し、どちらを再計算するか明示。現在defaultから論文結果を再現したと書かない。
- [ ] task assetsの再配布不明、licenseなしrepo、論文と別実装のcodeを別statusで記録。code licenseから素材/人物の利用権を推論しない。
- [ ] ττ-Benchのpost-commit timeout/async completion/projection lag/paginationを、権利確認済みのcleanな自作fixtureでPATCH-01/04の検査へ取り入れる。未確認の公式codeをvendorしない。
- [ ] visual judge高一致≠human一致、macro分布≠individual fidelity、environment/tool corruptionを各claim/eval contractに明記。人の便益やE09のscopeを昇格しない。

## PATCH-08 — 一つのclaim sourceから記事・章・deckを作る

**Files:** Create `docs/content/manager-evidence-index-20261022.json`, `tests/test_content_evidence_index.py`; Update既存 `docs/books/MANAGER_RESEARCH_BOOK_OUTLINE.md`、該当記事EN/JA、`docs/presentations/MANAGER_COMPLETION_DECK_SOURCES_20261022.json`。
**Produces:** claim ID→source/version/read_depth/license/own receipt/limit、code SHA、再現command、失敗、未実測。claimsは証拠参照でありtask台帳ではない。

- [ ] RED fabricated revenue/people、code-paper式取り違え、license不明asset、翻訳の数値/限界不一致を拒否。
- [ ] Made With MLの「実装moduleと教材章の対応」、FSDLの「録画章とcode/図/解説の対応」を既存構造へ取り入れる。新しい教材CMSを作らない。
- [ ] 本の初章と英日記事を同一caseから完成させる。既存Quarto候補でEPUBを検証し、MySTがEPUBを出せるとは記録しない。
- [ ] deckは既存python-pptxの編集可能出力を優先。Slidevの画像PPTX/編集可能PPTXとfallbackを区別し、必要がある場合だけpin付き代替exportを比較。

## PATCH-09 — 既存記事installerへ実download artifactを追加

**Files:** Modify `scripts/build_blog_publication.py::{source_file,build_publication}`、`publication/articles-2026-10-22.json`、`tests/test_blog_publication.py`; 同じrepoの既存 `apps/landing/manager-blog/scripts/package-contract.mjs::validatePublication`, `scripts/install.mjs::installManagerBlog`, `lib/render-manager-markdown.mjs::renderManagerMarkdown`, `tests/{package,install,integration}.test.mjs`（各pathは `apps/landing/manager-blog/` 相対）、`scripts/build-release-manifest.mjs`。
**Produces:** 新しいadditive `artifacts`項目でpath/hash/bytes/MIME/format/source/rightsを明示。既存image `media`にPDF/EPUB/MP4を偽装しない。

- [ ] RED path traversal/symlink/hash mismatch/MIME偽装/duplicate/legacy SHA変更/unsupported rawHTML。
- [ ] 実file bytesをvalidateして既存builder→contract→installer→download linkへ接続。HTMLは既存escape維持。新しいpublisher/storefrontを作らない。
- [ ] GREEN Python＋既存Node/build。公開は別のreviewed releaseで、URL/MIME/hash/readbackを確認してからpublishedと記録。

## PATCH-10 — carousel/slideshowは既存画像・動画rendererへ接続

**Files:** Create `docs/content/behavior-agi-20261022/storyboard.json`, `scripts/build_content_derivatives.py`, `tests/test_content_derivatives.py`; Reuse `apps/life-manager/scripts/render-slide-image.py` と `skills/video/canonical-renderer/render.py` の既存helper/検査を、共有所有範囲を確認して接続。
**Produces:** 8panel画像、60–90秒slideshow、claim/source footer、alt、順序、実出力hash。6枚/iOS app-store CTAを持つ既存投稿adapterへそのまま送らない。

- [ ] RED wrong panel count/claims、font unavailable、overflow、missing evidence footer、Anicca app-store CTA混入、duration/audio/probe不正。
- [ ] rendererの実引数とfont discoveryを読み、Manager用wrapperでpanel sourceから描画。既存FFmpegのprobe/audio/no-black-frame/contact-sheet検査を再利用する。Remotionの新runtime導入やlicense未確認のcopyを先行させない。
- [ ] 実PNG/MP4/contact-sheetを目視確認。PNGだけから動画完成と記録しない。投稿は既存channel/review/receiptを使う別工程。

## PATCH-11 — 職務・顧客・YCへ同じcaseを対応付ける

**Files:** Update `docs/founder/Y001_MANAGER_PITCH_EN_JA.md`, `docs/plans/2026-10-22-manager-founder-execution-map.md`; Create `docs/founder/MANAGER_TECHNICAL_CASE_PACKET_20261022.md`（公開可能な実績のみ）。

- [ ] 相手のjob/problemに対し、case一件・reproduction・失敗・小さな依頼を選ぶ。本人の学位/経験/就労/移住/commitmentは創作しない。
- [ ] buyerの現行代替をOpenClaw/Khoj/n8n/SaaS等と比較し、Managerの必要がなければ提案を止める。自社demoを顧客tractionにしない。
- [ ] 新しいprovider接続やbulk coldmailシステムを作らず、既存の公開業務経路・本人情報・提出version・official acknowledgementを使う。応募準備をbook完成待ちにしない。

## PATCH-12 — 実結果だけをscorecardと公開資料へ戻す

**Files:** 既存経済scorecard/receipt所有store、`docs/verification/` の対応文書、既存publication receiptへ参照を追加。新しい売上DBやtask SSOTを作らない。

- [ ] submitted/auto acknowledgement/human reply/interview/offer、published/readback、invoiced/paid/refunded/costを別記録。
- [ ] UNKNOWNを0へ変えず、顧客/個人情報をGitへ出さない。単発pilotをMRRへしない。
- [ ] 実sourceの結果で次のwedge/runtime/記事を更新。5会話/2提案/1入金は仮説目標で、達成・因果効果・採否を保証しない。

## 順序と合格の意味

PATCH-01→02→04→05→06がE16の技術線。PATCH-03は既成製品を直接使うbaselineの文書比較だけ。新adapterは未充足需要がある時だけ。07→08→09/10が証拠/出版線。11の準備は締切に合わせ並行し、12へ実証を戻す。元のU/G/F依存は維持する。DBOS適合比較の結果、再利用できるschedulerがあるならそれを採用して手書きコードを減らす。比較しないまま現方式を「最適」とは呼ばない。

この計画には、実験結果が出る前に決められない枝を合否条件付きで残す。手順・所有ファイル・検査・停止条件は具体化できるが、未実施の実験/売上/採否を確定したことにはしない。

既存 `test_digital_cycle_acceptance.py::test_lost_send_response_is_unknown_count_then_reconciled_without_resend` はcommit後の応答消失を既に検査する。PATCH-02/04では同じtestを増やさず、engine checkpoint消失、candidate変更、delivery読戻し前crash、stale restore等の差分だけ追加する。


## 提案する検証commandとinterfaceの固定

- PATCH-01: `python -m unittest discover -s tests -p 'test_owned_recovery_order.py' -v`。
- PATCH-02: 上記専用testに加え、提案CLI `python scripts/compare_owned_runtime.py --backend current --case checkpoint_loss --state-dir <private-isolated-dir>`、次に同じcaseを `--backend dbos`。出力receiptでversion/source/dispatch_countを比較。実装前のコマンドなので今回の実行結果ではない。
- PATCH-04/05/06: `test_owned_public_collector.py` / `test_owned_platform_host.py` / `test_owned_state_recovery.py` / `test_owned_runtime_entrypoint.py` を各 `python -m unittest discover -s tests -p '<file>' -v` で個別実行。fake transport/SQLite/mount testsはlocal source contractのみで、Railway実物や課金/停止/volume permissionsの証明ではない。
- PATCH-07: source JSON parseと既存 `python -m unittest discover -s tests -p 'test_eba_landscape_sources.py' -v`。新fixtureを実装する時だけ専用failure testを追加。
- PATCH-08: `python -m unittest discover -s tests -p 'test_content_evidence_index.py' -v`。
- PATCH-09: `python -m unittest discover -s tests -p 'test_blog_publication.py' -v`、repo rootから `node --test apps/landing/manager-blog/tests/{package,install,integration}.test.mjs`。
- PATCH-10: `python -m unittest discover -s tests -p 'test_content_derivatives.py' -v`。提案orchestrator CLIは `python scripts/build_content_derivatives.py --storyboard docs/content/behavior-agi-20261022/storyboard.json --out output/content --formats pptx,pdf,png,mp4`。既存rendererを呼び、利用不可exporterはUNKNOWN/UNAVAILABLEとし、成功fileを捏造しない。
- 挙動変更後の共通確認: `python -m unittest discover -s tests -q`、`python scripts/check_boundaries.py`、`python scripts/make_roadmap.py --check`。既存optional skipは明示。ブラウザ/Node/実render/live canaryは対象の変更時だけ追加する。
