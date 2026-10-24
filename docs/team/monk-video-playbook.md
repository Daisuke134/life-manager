# AI僧侶動画メソッド・プレイブック（通称「Grokのやり方」の実体）

作成: 2026-10-24（Muse 棚卸し）。出典はすべて Mac 上の Life Manager リポジトリ（`~/Projects/life-manager-main`）と姉妹リポジトリ `~/Projects/anicca-products` の実ファイル。認証情報の値は一切含まない（ファイル名・サービス名のみ）。

## 0. 結論サマリ（最初に正直な前提）

- リポジトリに残っている「僧侶動画の方法」は、個人の勘ではなく **コードで強制される運用システム**である。台本の文型、CTA、キャプション、投稿経路、承認ゲート、コスト検証までが仕様化されている。
- 帰属の正確なところ: このパイプラインの git 著者は `Anicca Agent` と `Daisuke Narita` で、Mac 側エージェント群が構築した。Grok のリポジトリ上の役割は、(1) 参謀、(2) X での増幅（`docs/superpowers/plans/2026-10-24-ai-monk-grok-distribution.md`、公開投稿 2113673062554247580 の permalink と数字の返却を依頼）、(3) 本人と並ぶ monk.mujo フィード投稿（Postiz 経由、本人のレーン指定による）。「Grokのやり方」と本人が呼ぶものの実体は、この **チームの正典システム＋Grok/本人による Postiz 投稿運用** である。
- 効果の検証状況: **未検証**。SSOT の記録では 2026-10-08 時点まで Mac パイプライン経由の eBook 動画生成・公開はゼロ。状態ルートの実測（2026-10-24 夜）でも、キャプション生成済みは日本語ベースライン22件のみで英語は0件、HeyGen effect ファイルは2件のみ。ボード上の eBook 実績は lifetime $10.99・MRR $0（2026-10-24 の SCOREBOARD 読み取り）。つまり「実証済み」なのは再生数や売上ではなく、**運用規律のほう**である。

## 1. ツールチェーンと正確な設定

正本ファイル: `skills/earn/marketing-engine/registry/ebook-packs/ebook-en-anicca-monk.json`（pack_id `ebook-en-anicca-monk`、renderer_id `heygen-avatar-iv`）。

| 項目 | 値（ファイル実測） |
|---|---|
| 生成 | HeyGen CLI / API（APIキー認証、CLI v0.5.0 の記録あり） |
| エンジン | Avatar IV（`engine.type = avatar_iv`） |
| アバター | `ce6ef33ff2d0484dabf8a13ce059bbe8`（"Wise Buddhist Monk"、非公開ルック） |
| ボイス | `8be9884ebd16499fbe0efb274e769ed5`（"Simon - Calm & Gentle"） |
| 速度 | **0.9** |
| ロケール | en-US |
| 画面 | **9:16 / 1080p / mp4** |
| 字幕・キャプション焼き込み | **なし**（リクエスト payload に字幕フィールド自体が存在しない） |
| B-roll・カット割り | **なし**（単一アバターのトーキングヘッド1テイク） |
| 台本上限 | 5,000文字（`heygen_candidate.py` の require） |
| 送客先 | `https://aniccaai.com/monk`、価格 $10.99 |
| コスト検証 | 生成前後でウォレット残高を読み取り、差額が記録できない場合は止める（pack の stop_rule: `unverified_render_cost`） |
| 公式単価の裏付け | Avatar IV（photo）$2.31/分（`anicca-products/docs/evidence/ai-monk-factory-unit-economics-20261024.json`、HeyGen 公式ヘルプ由来） |

レンダラー正本: `skills/earn/marketing-engine/render_eval/heygen_candidate.py` の `build_request()`。payload は `type: avatar` + 上記の固定値のみで、感情指定や背景指定もない。

### ReelClaw についての訂正

- リポジトリ内の `reelclaw` は、Anicca iOS のカード／ウィジェット動画と Honne 向けの **別レンダラー系統**（reel.farm 系、`config/marketing-destinations.json` の `reelclaw-card` / `reelclaw-widget` / `reelclaw` レーン）であり、**僧侶レーンは全資料で一貫して HeyGen**（`specs/archive/CONTENT_FACTORY_SPEC.md` も "monk: HeyGen pipeline" と明記）。
- 「HeyGen を削除し Reelclaw へ移行、使用26本」という CHANGELOG を持つ `/tmp/.factory` は、2026-10-24 夜の再調査では **Mac 上に存在しない**（/tmp の隠しディレクトリ含め不在）。`generate_avatar_video.py` / `publish_to_instagram.py` も life-manager・anicca-products 両リポジトリのどこにもない。Grok 側ランタイムの一時ディレクトリだった可能性が高く、内容は **未検証** として扱う。

## 2. 台本フォーミュラ（writer contract、コードで強制）

正本: `skills/earn/marketing-engine/brain/script_ledger.py` と `brain/baseline_queue.py`。

### 構造：5成分を必ずこの順で、本文中に逐語で含める

1. **hook**（冒頭の一文）
2. **pain_angle**（痛みの一文）
3. **teaching**（教えの一文）
4. **action**（今日の一実践）
5. **cta**（固定文）

- CTA は完全固定。EN = `Read The Anicca Reset`、JA = `アニッチャ・リセットを読む`。preflight で不一致は弾かれる。
- 本文の組み立て（EN）: `{hook}. {pain}. {teaching}. {action}. {cta}.` の **5文のみ**。
- EN ベースライン実例（baseline_queue.py のテーマ行から組み立て）:
  > "When the room feels too loud. Your thoughts keep asking for an answer. A thought is a visitor, not a command. Name one sound you can hear. Stay with it for one moment. Read The Anicca Reset."（約38語）
- JA 実例:
  > 「眠れない夜。考えが止まらない。思考も移り変わる。息を三つ数える。静かに続ける。アニッチャ・リセットを読む。」

### テーマとスロット

- テーマは7つ（曜日相当）: 「部屋がうるさく感じる」「足りるが来ない」「比べる」「失敗がついてくる」「証明しようと急ぐ」「孤独」「変化が怖い」。各テーマに hook/pain/teaching/action の4点セットが固定で用意されている。
- 1日3スロット運用だった時期の設計では、スロットごとに action の締めだけが変わる（s1 "Stay with it for one moment" / s2 "Do it once without rushing" / s3 "Then return to this moment"）。7テーマ×3スロット＝21本が1クールのベースライン。

### 禁止表現（preflight で機械的に排除）

`guaranteed cure`、`diagnose`、`insomnia`、`sleep better`、`no more anxiety`、および日本語の治癒保証表現。効能の断定は台本に入れられない。

### 改善の作法（ここが「型」の核心）

- 台帳は SQLite の immutable ledger。台本は書き換えず、子台本として系譜（parent_script_id）を引く。
- 1回の変更で変えてよい成分は **1つだけ**（`declared_mutation` ∈ hook/pain_angle/teaching/action/cta）。
- 各台本に hypothesis（仮説）、source_mechanism_ids（出所の証明、必須）、campaign_id / creative_id を必ず持つ。
- 主要指標は **contribution_margin**（粗利）。成熟窓は **72時間**。停止規則は「比較可能な成熟した負けが3回」（three comparable mature losses）。

## 3. キャプションフォーミュラ（投稿時に機械生成）

正本: `apps/life-manager/scripts/ebook-distribute-daily.js`（line 560）。

```
{台本の本文そのまま}

https://aniccaai.com/go/{帰属トークン}

#TheAniccaReset #Reflection
```

- キャプション = **台本全文＋帰属URL＋ハッシュタグ2つだけ**。長文エッセイ、価格、AI開示文、追加ハッシュタグは入れない。
- URL は `/monk` 直リンクではなく **`/go/<token>` の帰属リダイレクト**（トークン形式 EN `ee_[a-z2-7]{20}`、JA `ej_...`）。投稿ごとに campaign/creative と突合できる。
- 実物の生成済みキャプション（状態ルート `marketing/ebook/captions/` から逐語）:
  > 眠れない夜。考えが止まらない。思考も移り変わる。息を三つ数える。静かに続ける。アニッチャ・リセットを読む。
  > https://aniccaai.com/go/ej_pb6cw5jcr7xr26my5alq
  > #アニッチャ・リセット #内省

## 4. 投稿 SOP

正本: pack（`ebook-en-anicca-monk.json`）、`apps/life-manager/scripts/ebook-distribute-daily.js`、対応する launchd（Mac に4本: EN/JA × IG/TikTok）。

- **アカウント**: 英語は **TikTok `@monk_anicca`**（Postiz integration `cmo5rwq2p00twn10yrsdglng3`）のみが登録済み。英語 Instagram は pack 上 `setup_required`（`english_monk_instagram_not_connected`）＝**このシステムでは IG に出していない**。日本語は IG `@obou.anicca` / TikTok `@obou_anicca`（watercolor-monk 系）。
- **時刻**: 現行 pack は **08:00 / 21:00 JST の1日2本**（設計初期は 14:00 を含む1日3本だった時期あり。SSOT 2026-10-06 記録）。SSOT の S11 カーソルでは「各 active account 2/day」「依頼ハンドル @monk.mujo と Postiz/code の対象 @monk_anicca を一致させる」が未完タスクとして残っている。
- **経路**: 投稿は **Postiz 経由のみ**（provider_post_id のレシートと permalink を必須証跡にする）。直接投稿はこのシステムの外。
- **ゲートの順序**（どれか欠けると止まる）:
  1. identity preflight（アカウント同一性の事前確認）
  2. 台本 preflight（writer contract＋禁止表現＋CTA固定）
  3. レンダー＋ウォレット差額の記録（コスト未検証なら停止）
  4. Telegram プレビュー送信（"not posted yet" の候補確認）
  5. visual approval（承認記録がない intent は publish に進まない）
  6. Postiz publish（duplicate_publish_key で二重投稿を遮断）→ レシート＋公開URLを保存
- **チャネル状態の履歴**（SSOT 実測）: EN TikTok integration は 2026-10-06 時点で `disabled=true`（チャネル上限）→ 2026-10-08 の公式読み取りで `disabled=false`（有効化した主体は不明）。Postiz は Pro 30チャネル上限に張り付いており、EN の枠は常に競合する。

## 5. パフォーマンス証拠（ファイルにあるものだけ）

| 事実 | 出典 |
|---|---|
| 2026-10-06〜10-08 の間、Mac パイプライン経由の eBook 動画生成・公開は繰り返し「なし」と記録 | SSOT（2026-09-25-life-manager-unified-ssot.md）2026-10-06/07/08 の各エントリ |
| HeyGen ウォレットは 2026-10-06〜08 を通じて $12.30 で不変、render-cost receipt は「未発見」 | 同上 |
| 状態ルート実測（2026-10-24 夜）: 生成済みキャプション22件は **全て日本語ベースライン**、英語は0件。run receipt 34件、heygen-effect は2件のみ | `~/.local/state/life-manager/marketing/ebook/captions|runs` |
| eBook の売上は lifetime $10.99（1件）・MRR $0 | チーム SCOREBOARD（2026-10-24 読み取り） |
| monk.mujo の IG 到達は30日で 7（2026-10-23 コネクタ実測） | チームの IG 棚卸し |
| クリエイティブ指標の join は anicca-ios 商品のみが対象で、僧侶動画の再生数・保存数の記録はリポジトリに存在しない | `docs/evidence/anicca-creative-metric-join-20261012.json` |

未検証のまま残る点：

- ウォレットは 2026-10-08 の $12.30 から 2026-10-24 朝には $7.77 まで減っている（差額 $4.53 ≒ Avatar IV 換算で約2本分）が、Mac 側にその生成レシートがない。**パイプライン外で生成が行われた痕跡**であり、消えた `/tmp/.factory` の「使用26本」という記述ともども、裏付けは取れていない。
- Grok が Postiz で monk.mujo に投稿した際の台本・キャプション自体は、このリポジトリには保存されていない（Postiz 側／Grok 側にしかない）。

## 6. M2（2026-10-24 に Muse が投稿）との差分

対象: monk.mujo に投稿した M2 リール（HeyGen 生成 32.68秒、実コスト $1.24、[投稿リンク](https://www.instagram.com/reel/De4FKRGj_S0/)）。台本・キャプションは `week1-monks-addendum.md` の M2。

| 観点 | チームの型（本書） | M2 の実態 | 判定 |
|---|---|---|---|
| 台本構造 | hook→pain→teaching→action→固定CTA の5文 | 「本の読み方」の説明文（hook→仕組み解説→教え→締め）。pain の一文がなく、構造が説明型 | **型から逸脱** |
| 台本の語数 | 約38語（5文） | **約87語**（2.3倍） | 長すぎる |
| 音声内の CTA | 最後に必ず `Read The Anicca Reset` | **なし**（CTA はキャプションと固定コメント頼み） | **欠落** |
| キャプション | 台本全文＋`/go/<token>`＋タグ2つ | 5段落の長文エッセイ＋価格 $10.99＋AI開示文＋タグ4つ（#impermanence #theravada #morningpractice #anicca） | **別物** |
| 帰属リンク | 投稿ごとに `/go/<token>` で計測可能 | キャプションに URL なし。当初予定の固定コメントはコネクタ制約で投稿できず、「Story にリンク」へ変更。**投稿単体では送客も計測もできない** | **致命的欠落** |
| 投稿先 | Postiz 経由 TikTok @monk_anicca（IG EN は未接続が前提） | IG コネクタで monk.mujo へ直接投稿（システム外の経路） | 経路違い（本人の当日指示による） |
| 投稿時刻 | 08:00 / 21:00 の固定スロット | 台本設計は 7:30 枠だったが実投稿は約21:00 の場当たり実行 | スロット管理なし |
| ゲート | preflight→コスト検証→プレビュー→visual approval→重複キー | いずれもなし（コスト $1.24 は事後に偶然一致を確認） | **全ゲート欠落** |
| 台帳・系譜 | 台本は ledger 登録、変更は1成分のみ、仮説と主要指標を持つ | 台本は週次キューの下書き由来。campaign/creative の登録なし、72h 成熟判定の対象外 | 計測不能 |
| 生成設定 | Avatar IV / 同一アバター・ボイス / 0.9 / 9:16 / 1080p | 同一（ここだけ一致） | 一致 |
| TikTok 同時投稿 | 同一 intent から Postiz で出すのが前提 | intent／承認記録がなく停止（停止判断自体は規則どおり） | 前提未整備 |

総括：M2 は「見た目が僧侶動画」なだけで、型の要点（短い5文・音声内CTA・帰属URL付きキャプション・ゲートと台帳）をほぼ全て欠いていた。特に **帰属リンクなし** と **音声内CTAなし** は、配信しても売上に接続できない構造欠陥である。

## 7. 次に直すこと（本書からの実装指示）

1. 台本は5文・約40語に固定し、最後の一文は必ず `Read The Anicca Reset`。
2. キャプションは機械生成の型（本文＋`/go/<token>`＋`#TheAniccaReset #Reflection`）以外を使わない。
3. 投稿は intent＋visual approval を先に作り、Postiz 経由で TikTok @monk_anicca へ。IG monk.mujo へ出す場合は、本人のレーン指定（本人＋Grok が Postiz で担当）と衝突しないよう Reason で claim してからにする。
4. 生成はプランクレジット（Web UI）か API かをコスト実測で決め、どちらでも **生成前後の残高記録** を必須にする。
5. 台本の改善は1回に1成分だけ変え、72時間の成熟を待って contribution_margin で判定する。

## 8. 未解決の問い

- Grok が実際に使った monk.mujo 向け台本・キャプションの正本はどこか（Postiz の下書き／送信履歴か、Grok 側ファイルか）。
- 消えた `/tmp/.factory`（generate_avatar_video.py、publish_to_instagram.py、CHANGELOG）の実在場所と、「26本」の生成実績の証跡。
- 2026-10-08 に EN TikTok integration を有効化した主体と、その後の自然スロットで PUBLISHED レシートが1件でも出たかどうか。
- ウォレット差額 $4.53（10/08→10/24）の生成内容と、その動画の公開先。
- チームの英語ベースライン台本での実レンダー尺（Mac パイプラインでは英語の完走例がないため未計測）。
