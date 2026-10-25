# Manager: 新規の出版・教材・配布スタック調査 — 2026-10-22

調査対象は、一本の検証可能な実装・研究を記事、既存書籍、スライド、カルーセル、短尺動画に再利用し、技術的信用・仕事・顧客会話につなぐ方法。読取専用。基準コミットは `ae06f4ccfa30b29e427f71d6413eba0858a34cf8`、canonical remote は `Daisuke134/life-manager`。実装、公開、外部アカウント接続、投稿、課金、応募は行っていない。以下のパッチ名・関数名で「追加」と書くものは提案で、現在の実装ではない。

結論は、既存の Markdown/JSON → editable PPTX、Pillow画像、FFmpeg動画、記事パッケージ → 既存installer/Next/Netlify を完成させること。新規候補のうち MyST の DOCX/JATS と Slidev のコード解説用deckには条件付きの価値がある。Remotion、Ghost、Typefully、Bufferを直ちに別runtimeとして導入する根拠はない。

## 1. 新規性と実際に読んだもの

`AGENTS.md`、`REVIEW.md`、`MANAGER_PRODUCT_SPEC.md`、既存research-products-plan、`MANAGER_RESEARCH_BOOK_OUTLINE.md`、newsletter charter、既存strategy report/source registryを確認。既存source registryは37 source bundles。P01–P07を別タスク台帳に置き換えない。

`rg -n -i 'Jupyter.?Book|mystmd|Slidev|Marp|Remotion|Ghost|Typefully|Buffer|Postiz|Quarto|Made With ML|Full Stack Deep|FSDL|Goku Mohandas' products/manager docs/research/manager/publication` の調査時一致は、既存Quarto計画とPostiz接続制限の記述。MyST、Slidev、Marp、Remotion、Ghost、Typefully、Bufferはこの範囲では未記載。別途 `Made With ML|Goku Mohandas|Full Stack Deep Learning|Full Stack LLM|FullStack` は `products/manager` 内0件。これは検索範囲内の新規性で、世の中で初めてという意味ではない。QuartoとPostizは新規として数えない。

Firecrawl検索後に公式URL本文を取得。各ページの読取深度・支持する主張・限界を[PUBLISHING_SOURCES.json](PUBLISHING_SOURCES.json)に記録。外部3repoはscratchへcloneし、固定SHA、LICENSE、package metadata、対象export関数・CLIを確認した。依存のinstall、build、外部コード実行はしていない。現在環境の `command -v` では `ffmpeg`、`soffice`、`pdftoppm` は見つかったが、`quarto`、`myst`、`slidev` は見つからなかった。今回render成功は主張しない。

## 2. 新しい具体的選択肢

### A. Jupyter Book 2 / MyST: 書籍の置換ではなく、査読・編集用DOCX/JATS出口

現在の[Jupyter Book公式stable](https://jupyterbook.org/stable/)はMyST Document Engineのdistributionで、CLIの動詞が `jupyter book` と `myst` で違うと明記。旧Sphinx系Jupyter Book v1の機能表をそのままv2へ移さない。

[MyST export仕様](https://mystmd.org/guide/documents-exports)は `myst.yml` の `project.exports[]` に `format/template/article(s)/output/id/toc` を宣言し、`myst build --pdf --docx`、`myst build --all` で書き出せる。PDF/TeX/Typst/JATS/Word/CITATION.cff/MyST Markdownを列挙する。この現行一覧はEPUBの根拠ではない。既存計画のEPUB用途はQuartoのまま扱い、MySTを入れる理由は編集者向けDOCXまたは研究提出用JATSが実際に必要な場合。

固定repo: `jupyter-book/mystmd@033fa068af225e974d183143ead7f5dd180663da`（2026-10-21）、`mystmd` 1.11.0、MIT、Node >=20。確認した実装は `packages/myst-cli/src/build/build.ts::{build,getAllowedExportFormats,getRequestedExportFormats}`、`build/docx/single.ts::runWordExport`、`build/jats/single.ts::runJatsExport`、`build/cff.ts::runCffExport`。固定[LICENSE](https://github.com/jupyter-book/mystmd/blob/033fa068af225e974d183143ead7f5dd180663da/LICENSE)。

限界: PDFにはLaTeX/Typstが別途必要。templateは別repo/assetの権利と固定点を要確認。現行code docsではnotebook実行は既定disabledで、`--execute` がJupyter kernel実行を始める。教材生成で勝手に実験を再実行しない。MySTのdirective/roleやJATSは既存blog Markdown rendererが理解しないので、canonical本文に混入させず薄いexport用configで同じ章を参照する。

### B. Slidev: コード・式・デモを見せる講義deckの限定export

[公式export](https://sli.dev/guide/exporting.html)と[CLI](https://sli.dev/builtin/cli)を確認。MarkdownからPDF/PNG/Markdown/image-PPTXを出し、現行の `slidev export --format pptx-editable` はbrowser測定結果からnative PowerPoint shapesを作る。image-PPTXは全slideが画像でtext選択不可、presenter notesは移る。editable版もSVG/Mermaid/式/canvas/iframe/video/一部CSSは画像、slide全体のfallbackがあり理由をreportする。fontは埋め込まれず、PowerPointでは折返しが変わり得る。`--with-clicks false` がないとPPTXのclick step数でページが増える点に注意。

固定repo: `slidevjs/slidev@73053ab2b9653ed475960301b56e1ce4439d9c75`（2026-10-02）、`@slidev/cli` 53.0.0、MIT、Node >=22.12.0。確認: `packages/slidev/node/commands/export.ts::{exportSlides,exportNotes,getExportOptions}`、`commands/pptx/index.ts::{exportPptxEditable,reportEditableExport}`、`commands/pptx/build.ts::buildPptx`。固定[LICENSE](https://github.com/slidevjs/slidev/blob/73053ab2b9653ed475960301b56e1ce4439d9c75/LICENSE)。

条件: current docsとlegacy docsを混ぜない。CLI exportにはPlaywright Chromiumが必要。remote font、image、iframeを使うとbuild時network/第三者資源が増える。Managerの既存python-pptxは既にeditableなので、現行YC/IACS/Lab deckを移行しない。新しいコード解説deck一つでだけ比較し、本文・notes・source IDs・fallbackを検査して採否を決める。Marpは公式ホームのHTML/PDF/PPTX exportまでscreeningしたが、今回repo/CLI詳細未監査のため実装推奨には格上げしない。

### C. Remotion: JSON→動画のAPIは使えるが、現時点では既存FFmpegを選ぶ

[renderMedia](https://www.remotion.dev/docs/renderer/render-media)の実契約は `renderMedia({composition,serveUrl,codec:'h264',outputLocation,inputProps})`。`bundle()` → `selectComposition({serveUrl,id,inputProps})` → 同じ `inputProps` の `renderMedia()` が文書化される。storyboard JSONから1080×1920/fps/durationを決める仕組みに適合する。

固定repo: `remotion-dev/remotion@aa5d82347db5eeab4a2be3557aff3c3c3a373e9d`（2026-10-22）、`@remotion/renderer` / core 4.0.537。`packages/renderer/src/render-media.ts::renderMedia`、`select-composition.ts::selectComposition`、[固定LICENSE](https://github.com/remotion-dev/remotion/blob/aa5d82347db5eeab4a2be3557aff3c3c3a373e9d/LICENSE.md)を確認。MITではない。現行free条件は個人、営利3人以下、非営利、または非商用評価。eligibleなら商用video/image制作可。Remotion派生自体の再販売等は禁止。LICENSEは将来5.0の変更予告を含むため4.0の条件を5.0に保証しない。

反証: canonical `skills/video/canonical-renderer/render.py` が既にlocal FFmpeg、H.264/yuv420p/BT.709、AAC48kHz、音量、黒フレーム、opening motion、contact sheet、source SHAを持つ。60–90秒のslide sequenceを加えるだけなら、React/Webpack/Chromiumの別runtimeを増やさずここを拡張する方が小さい。既存関数は `render,parser,probe,validate_probe,validate_audio,validate_no_black_frames,validate_opening_motion,create_contact_sheet`。現状は単一input/output demoでありmulti-panelを既実装とは言わない。

### D. Ghost / Typefully / Buffer: 将来adapterの比較材料。新接続は不要

| 候補 | 現在の公式インターフェース | Managerに必要な制約・判断 |
|---|---|---|
| [Ghost Admin](https://docs.ghost.org/admin-api)、[create post](https://docs.ghost.org/admin-api/posts/creating-a-post) | `POST /ghost/api/admin/posts/`、`posts:[{title,lexical,status}]`。HTML入力は `?source=html`。integration keyから5分以下のHS256 JWT、`Authorization: Ghost <token>`、`Accept-Version` | HTML→Lexicalはlossy。記事本文、脚注、図、canonicalを別途render照合。integration tokenはcommon publishing用の標準権限でdraft専用tokenとは限らない。user tokenはrole依存。古いexampleのv3を現在のserver versionと誤認しない。既存owned blogがあるのでGhostサーバー新設は不要 |
| [Typefully v2](https://typefully.com/docs/api)、[v1→v2](https://support.typefully.com/en/articles/13133296-typefully-api-v1-v2-migration-guide) | `POST /v2/social-sets/{id}/drafts`、`platforms.x.posts[].text`、Bearer key。social-set IDを指定 | keyは作成userの権限を継承。user/social-set rate limitsと429。X用途は自分/会社のpersonal automation向けと明記。comment markersを落としたGETをPATCHするとanchor破壊。v1の単一account workflowを流用しない。API entitlement/priceは今回未確認、無料とは主張しない |
| [Buffer posts](https://developers.buffer.com/guides/posts-and-scheduling.html)、[efficiency](https://developers.buffer.com/guides/efficient-api-usage.html) | GraphQL `POST https://api.buffer.com`、Bearer key、`createPost(input:{text,channelId,schedulingType,mode})` | HTTP成功だけでなくGraphQL union errorを見る。公式はcreate_postにidempotency keyがなくtimeout後の盲再送はduplicateになると説明。channel+狭いcreatedAtでreadback。MCPとpersonal keyは同一quota。移行理由がなければ既存Postizの効果fence/readbackを再利用 |
| [Postiz current](https://docs.postiz.com/public-api/posts/create)、[overview](https://docs.postiz.com/public-api/introduction) | `POST /public/v1/posts`、`type:draft|schedule|now`、`posts[].integration.id/value[].content/image/settings.__type` | 既存手段。API key/OAuthは外部identity。create IDはpublic permalinkではない。current docsはcreate endpoint 90req/hour（cloud100）、channel/月間quotaは別。provider設定を固定。今回接続状態・plan・live postは未照合 |

権利はAPI利用権と第三者本文/図/音源の再配布権を分ける。いずれのserviceにも認証、draft作成、publishを実行していない。ghost/typefully/bufferのcode licenseは今回監査していない。価格や顧客testimonialsを売上receiptに変換しない。

## 3. 新しいend-to-end先例: 名前より実装対応表をコピーする

**Made With ML / Goku Mohandas** — [現行home](https://madewithml.com/)、[本人によるAnyscale参加記事（2023-07-26）](https://www.anyscale.com/blog/machine-learning-for-developers)、[code](https://github.com/GokuMohandas/Made-With-ML)。公開教材はDesign→Data→Model→Develop→Utilities→Test→Reproducibility→Productionを一つのapplicationで貫く。本人記事はGokuとMade With MLがAnyscaleにjoinしたことを述べ、企業支援や利用規模も本人公表する。これは技術教材と職業上の機会の実在する接続。売上、取得金額、現在給与は未公開でunknown。

固定 `3361aeb8ddfc2affdba9f545c978c38c85cee764`、2026-03-04、MIT、非archive。検査した `.github/workflows/documentation.yaml` はmain push→Python3.10.11/MkDocs1.4.2/mkdocstrings→`mkdocs gh-deploy --force`、`mkdocs.yml` は実装module data/models/train/tune/evaluate/predict/serve/utilsを教材ナビへ対応づける。コピーするのは「Managerの各lessonが実在module/example/testへ戻る対応表」で、別MkDocsサイトやforce deployではない。homeのupcoming cohortは日付未確認のinterest formで、現在の開講receiptではない。repo MITから講義videoや他サイト素材の権利は推定しない。

**Full Stack / askFSDL** — [bootcamp top](https://fullstackdeeplearning.com/llm-bootcamp/)、[2023 curriculum](https://fullstackdeeplearning.com/llm-bootcamp/spring-2023/)、[askFSDL walkthrough](https://fullstackdeeplearning.com/llm-bootcamp/spring-2023/askfsdl-walkthrough/)。公式にApril 2023の無料録画と、以後技術が進化した旨を明記。walkthroughは2023-05-09公開で、recording・code・章別screen shots/summary・communityを同じpageへ統合する。一部外部serviceのaccountがなければ実行できない点も開示する。イベント・無料archive・スポンサーの存在は確認、現行有料cohortや利益額のreceiptではない。

ask-fsdl code固定 `b725c0ecdf0d484b48b79e32c37905614522ba4d`、2023-11-24、`LICENSE.txt` はMIT。website固定 `c315f42e16b8b0208039cc841c3f34da0c405a2e`、2026-10-21、license metadata null。websiteの文章・画像をMITと扱わない。講義要約creatorには認証、Modal、`make it-all` があり、Managerへ生成基盤を追加する理由にはならない。コピーするのは「章ID・開始秒・claim ID・図・再現command・限界」を一つのsource mapから出す構造。

この二例は、教材が仕事や事業の証拠になる可能性を示すが、Managerの採用、契約、売上、YC採択を予測するものではない。最初の題材は既存のdeadline-cancel/recovery/replay-zero一件で十分。実装SHA→再現command→failure→修正→test→限界→図→article/chapter→slide/videoの対応を公開できる形に整える。

## 4. 現行パイプラインの正確な接続点

sparse checkoutで見えない `apps/` と `skills/` はcanonical `git show HEAD:<path>` で確認した。別repoを実装元にしていない。

- `products/manager/scripts/build_blog_publication.py`: `source_file(root,value,suffix='.md')` はManager docs境界を検査。`additive_media(root,config,original,frozen)` は登録PNGとSHAを確認。`public_markdown(markdown,source,root,revision,known_media)` はfrontmatter除去、relative citationをimmutable GitHub URLへ変換。`build_publication(root,config,original)` → `(package,copies,receipt)`。`--check` は生成byte照合のみ。receiptの `publication_verified` はfalse。
- inventory `products/manager/publication/articles-2026-10-22.json` → `docs/research/manager/publication/2026-10-19/manifest.json`。54 legacy articles/29 legacy mediaの凍結hashを保護。歴史的65/33等を現在のlive censusにしない。
- `apps/landing/manager-blog/scripts/package-contract.mjs::validatePublication` はmediaを `png|jpg|jpeg|webp|gif` に制限。PDF/EPUB/PPTX/MP4を現状mediaに混ぜられない。`install.mjs::installManagerBlog({revision,root,fetchBytes})` がmodule integrityとpackage bytesを検査し既存publisher repoへstageする。publicationは既存 `anicca-products` のNext/Netlify bridge。新hostingは不要。
- `apps/landing/manager-blog/lib/render-manager-markdown.mjs::renderManagerMarkdown(md)` はtable/list/code/imageを処理、raw HTMLをescape。MyST directive、動画HTML、任意JSをそのまま通さない。
- `products/manager/scripts/build_manager_completion_presentations.py`: `build_slide(prs,spec,number,sources)`、`notes(slide,spec,sources)`、`footer(slide,number,spec,sources)`、`markdown(deck,data,target)`。`main()` は固定SOURCE/OUTを読みPPTXとMarkdownを生成する。PDF生成codeはここにはない。既存artifact/検証文書のPDFは過去のLibreOffice render evidenceであり、今回の自動PDF出口ではない。
- `apps/life-manager/scripts/render-slide-image.py`: positional `bg out width height text`。`load_font,wrap_to_lines,fit_text,draw_scrim,measure_contrast` を持つPillow renderer。現状Mac font path、最大2行、source footerなし。技術図や長文を無加工で入れない。
- `apps/life-manager/lib/marketing-slide-pack-factory.js::renderSlideImage` は既存scriptを1080×1350で呼び、`generateSlidePackCandidates` は6枚・app CTA・cached backgroundsに依存。Managerの8panelをfactoryへ無理に通さない。
- `apps/life-manager/lib/marketing-native-carousel-publication-adapter.js::{selectMarketingNativeCarouselLane,buildMarketingNativeCarouselPublicationJob,executeMarketingNativeCarouselPublicationJob,verifyMarketingNativeCarouselPublicationReceipt}` はlane identity、hash-addressed objects、approval、media順序、provider reconciliationを検査。`SLIDE_COUNT=6`、Anicca app lane、app-store CTAに結合。Managerのresearch内容と8枚は現状不適合。
- `skills/earn/marketing-engine/publish/postiz_adapter.py`: `HttpPostizClient::{create_draft,list_integrations,list_posts,upload_file,promote}` と `PostizAdapter::{_draft_payload,upload_media,create_draft,promote}` はIntentStore/fenceを使う。draftでも外部write。native公開用 `skills/video/lm-distribution/postiz_video.py::{build_payload,upload_image,create_post,read_publish_state,is_reconciled_state}` を持つ。source registryのintegration IDだけで現行権限を確定しない。
- `skills/earn/marketing-engine/manifests/slideshow.manifest.sh` は別affiliate laneの古いplaceholder/停止条件を含む。名前がslideshowだからManager publication設定としてコピーしない。

## 5. 7つの原子的パッチ候補（提案、未実施）

### 1 — 一件の教材にsource→code→test→derivative対応を追加する

既存 `products/manager/docs/presentations/MANAGER_COMPLETION_DECK_SOURCES_20261022.json` のsource/spec型を再利用し、P06で既に予定した `products/manager/docs/content/behavior-agi-20261022/storyboard.json` だけを教材の入力とする。完成deck sourceやtask ledgerを複製しない。

追加fields: chapter/article sourceとSHA、claim IDs、source version/read depth/rights、code path+commit、test/reproduce command、fictional/observed、EN/JA copy、alt、canvas、panel順、duration、source footer、canonical CTA。最初の題材は一つの既存recovery case。新規 `products/manager/scripts/build_content_derivatives.py::validate_storyboard` はexport orchestration/validationのみ、rendererを実装しない。

検証: 追加 `products/manager/tests/test_content_derivatives.py` でunknown claim、source hash違い、重複panel、8panelの脱落、未許可図、fictional→observed誤記をreject。`python -m unittest discover -s products/manager/tests -p 'test_content_derivatives.py' -v`。これは今後のcommandで今回実行していない。

### 2 — editable deck builderを入力指定可能にし、PDF出口を再現可能にする

既存 `build_manager_completion_presentations.py::main` をdefault挙動保持のまま `--source/--output-dir` 対応へ薄く分離し、既存 `build_slide/notes/footer/markdown` をそのまま呼ぶ。新規ファイル名で12-slide教材deckを作り、既存3deckを上書きしない。PDFはinstalled LibreOfficeを明示選択してPPTXから変換する一工程をorchestratorへ加え、PPTXとPDFのtext/page数を照合する。

追加test: `products/manager/tests/test_presentation_derivatives.py`。ZIP内native text/table、JA note、claim/source footer、speaker note数、非既存output collisionを検査。実canaryは12pagesをrenderして全page/contact sheetを目視、PPTX/PDF hashをreceiptに保存。Slidevはこの既定pathを置換しない。コード実演が必要な新deckだけ、同じstoryboard→薄いMarkdown exportで別途比較する。

### 3 — 既存Pillow rendererにresearch layoutを一つ追加する

`apps/life-manager/scripts/render-slide-image.py` に追加 `render_research_panel(...)` を設ける。既存positional CLI/2行Larry layoutを保持し、research modeではheadline/body/source footer/alt sidecar/explicit fontを受ける。既存 `fit_text/measure_contrast` を再利用し、最低font size以下・欠glyph・footer overflowをfail。新規fontを再配布せずinstalled CJK fontとlicenseを明示する。

P06の8panelは1080×1350 JPEG、記事用PNGは同一compositionから出す。技術diagramの権利もmanifestで固定。追加 `apps/life-manager/tests/test_render_slide_image.py` とManager derivative testで、EN/JA長文が黙って切れない、citationが出る、順序/hash/寸法が一致することを検査。現在の輝度heuristicだけを研究panelのアクセシビリティ判定にしない。

### 4 — canonical FFmpegにmulti-panel storyboard入口を追加する

`skills/video/canonical-renderer/render.py` に追加 `render_storyboard` とstoryboard入口を設け、既存 `render` のdemo modeを保持する。入力はlocal panel assets、順序、各秒数、caption、音声rights、evidence/source SHA。60–90秒を一度だけencodeし、既存 `validate_probe/validate_audio/validate_no_black_frames/validate_opening_motion/create_contact_sheet` を通す。genericな「VERIFIED OUTPUT」表示を研究panelの未計測outcomeへ流用しない。

既存 `skills/video/tests/test_canonical_renderer.py` に、panel欠落/asset hash違い/時間負値/総時間外れ/音声rights不足をrejectするtestを追加。実canaryはffprobe、各panel境界frame、contact sheet、字幕safe marginsを確認。Remotionを入れる前にこれで必要十分か確かめる。

### 5 — 書籍は同一章を既存Quartoへ、DOCX/JATSが必要な時だけMyST比較

既存 `MANAGER_RESEARCH_BOOK_OUTLINE.md` と `manager-prediction-intervention-blessing-en.md` + JA companionをcanonical本文に保つ。予定済みbook/evidence testを完成し、source/bibliography/rights/claim IDsを固定する。EPUBは既存Quarto計画を使う。新しいMyST書籍サイト、別原稿ツリーは作らない。

具体的追加候補は `products/manager/scripts/build_book_exports.py` のthin command adapter。export targetがDOCX/JATSのときだけ、同じ章を参照する一時 `myst.yml` を生成し、確認済みinstalled binary/versionを使う。自動installや`--execute`をしない。追加 `products/manager/tests/test_book_exports.py` でcanonical本文の二重化、未固定template、unsupported target、元引用欠落をreject。実出力はDOCX ZIP/JATS XML/EPUB ZIPの内部、脚注、図、JA glyphを確認して初めてartifact receiptにする。必要がEPUBだけならこの新adapter自体を見送る。

### 6 — 既存blog packageにdownload artifacts契約を追加する

現状のimage-only `media` は維持し、明示 `artifacts` 配列にPDF/PPTX/EPUB/MP4を登録する。追加候補fieldsはsource、source_sha256、size、mime、extension、role、lang、claim/source manifest SHA、download URL。非imageを `media` へ入れて既存image validationを弱めない。

変更点は既存 `build_blog_publication.py::{source_file,build_publication}` に追加 `additive_artifacts`、`articles-2026-10-22.json`、既存 `package-contract.mjs::validatePublication`、`install.mjs::installManagerBlog`、release receipt。既存owned siteの `public/blog/manager/downloads/<sha>.<ext>` にhash付きでstageする。articleはMarkdown download linkのみで、raw HTML許可は不要。

既存 `products/manager/tests/test_blog_publication.py` と `apps/landing/manager-blog/tests/{package,install,integration}.test.mjs` に追加test: MIME/bytes/extension不整合、traversal、hash違い、duplicate/collision、legacy SHA変更はreject、同じ入力のrebuild bytes一致。module変更後は既存 `build-release-manifest.mjs` とNode tests。公開後の完成条件は既存bridge release→実URL GET→download bytes hash＋既存payment smoke。ローカルartifactを販売/公開済みにしない。

### 7 — 配布は既存Postizを使い、Manager lane適合を先に定義する

新しいschedulerやGhost/Buffer/Typefully connectorは追加しない。まず `selectMarketingNativeCarouselLane` と `assertPack/assertApproval` の現行identity、6panel、app CTAを明示し、Manager未登録をrejectするregressionを既存 `marketing-native-carousel-publication-adapter.test.js` へ追加する。8枚のoffline teaching artifactはそのまま保存できるが、native postを許可したことにはならない。

実配布を実装する場合だけ、所有者・channel・research CTA・panel countを一つのtrusted lane configへ追加し、既存fence/object store/receipt/reconcileを共用する。既存Anicca laneの意味は変えない。最初はoffline payload/approved packをreviewし、現行integration権限と無料利用枠が読み戻せてから、明示された配布範囲で一unit canary。timeout後に盲再送せずprovider stateを照合。public permalink/provider official receiptを得るまでpublishedにはしない。exact account metadataやsecretは教材/sourceに出さない。

## 6. 受入と優先順位

最初の順は1→2/3→4→6。5は実際のbook target次第、7は実配布の適合前提が揃う時だけ。各patchは一つのreviewable diffと意味のあるtestで分離し、P01–P07および既存task状態に接続する。これらを新しい技術SSOTにしない。

一つの教材releaseには source/code commit、reproduce command、case/test evidence、limitations、原稿、artifact hashes、実public URLs/readback、correction routeを揃える。CTAはsource/再現codeか、実際に存在する関係のあるofferの一つ。impressions、読者返信、qualified interview、採用応募、仕事受注、決済/返金/コストは別々に観測する。新しいtoolや先例の存在だけで売上やcareer outcomeを既成事実にしない。



---
統合注記: このlaneは読取調査。repoへ収録した統合担当の文書変更と、未実施の実装/外部操作は別。[追加調査の判断](REPORT_JA.md)と[atomic patch plan](../../plans/2026-10-22-manager-e16-atomic-patches.md)を参照。
