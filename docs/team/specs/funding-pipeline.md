# 資金・機会パイプライン（2026-10-23 JST 時点）

目的: Life Manager / Anicca が応募できる、締切が 2026年12月頃までの助成金・アクセラ・ハッカソン・クレジット枠を一次ソースで一覧化し、上位3件の下書きを用意する。YC / a16z は対象外（RULES.md 4）。**この作業では何も提出していない・どこにもログインしていない。**

取得方法: 各行の URL を `crwl crawl URL -o markdown-fit` で取得（2026-10-23）。発見は DuckDuckGo HTML と Devpost 公開 API。締切が一次ソースに書かれていない行は「未記載」とし、推測しない。
台帳: `scripts/ledger-check.sh <ドメイン>` を全行で実行（2026-10-23）。全件 FREE（未）。claimed 行は追加していない（提出しないため）。
法人の有無: 統合SSOT L18576「`company.legal_name=Anicca` はフォーム用名称で、法人化済み・法人所在地・設立日の証明ではない」。よって会社要件のある枠は応募不可または条件付きとする。

| # | 名称 | URL | 締切 | 対象 | 必要書類 | 応募可否 | 台帳 |
|---:|---|---|---|---|---|---|---|
| 1 | J-Startup 第6次選定（経産省、今回から公募制） | https://www.meti.go.jp/press/2026/10/20261023002.html | 2026-11-13 17:00 必着 | 革新的な技術・ビジネスモデルでグローバルに急成長しうるスタートアップ。会社（外国会社を除く）であること | 応募要領・応募書類は J-Startup 公式HP / 事務局（PwC）HP 参照（取得ページに書類一覧なし） | **応募不可**: 会社要件。法人化の証拠なし（SSOT L18576） | 未 |
| 2 | 小規模事業者持続化補助金〈一般型・通常枠〉第20回（商工会議所地区） | https://r6.jizokukahojokin.info/ （告知: https://www.chusho.meti.go.jp/koukai/hojyokin/kobo/2026/260527002.html ） | 受付 2026-11-05〜2026-12-15 17:00。事業支援計画書（様式4）の発行受付締切 2026-12-04 | 小規模事業者の販路開拓等（自ら策定した経営計画に基づく取組） | 公募要領 第8版、事業支援計画書（様式4・地域の商工会議所が発行）、電子申請（郵送不可） | 条件付き: 小規模事業者としての事業者実態（開業届等）を未確認。様式4発行は商工会議所とのやり取り、電子申請はログインが必要＝人手 | 未 |
| 3 | PayPal AI Hackathon（Devpost） | https://paypalaihackathon.devpost.com/rules | 2026-11-12 12:00 PT（2026-11-13 05:00 JST） | 成年の個人・チーム・法人。PayPal 開発基盤（sandbox）と任意の AI を統合したアプリ（新規、または期間中に大幅更新） | Devpost 提出フォーム、YouTube 公開のデモ動画、動作するデモ/テスト環境、英語（または英訳） | 可（個人）。除外国の例示（Brazil, Quebec, Russia 等）に日本なし。Devpost ログインと動画制作が必要 | 未 |
| 4 | Kiroween 2026（Kiro / Devpost） | https://kiroween.devpost.com/rules | 期間 2026-10-30〜2026-12-04（公式規約は未公開） | 未記載（規約公開前） | 未記載（規約公開前） | 保留: 規約公開後に再確認 | 未 |
| 5 | Nebius x NVIDIA Global AI Hackathon（Devpost） | https://nebiusglobalaihackathon.devpost.com/rules | 2026-10-30 10:00 PT（2026-10-31 02:00 JST） | 成年の個人・チーム・法人。Nebius Token Factory か Nebius AI Cloud 上で動き、NVIDIA の OSS モデルを1つ以上使うアプリ（4トラック） | Devpost 提出フォーム、既存PJなら期間中の大幅更新の説明 | 可（個人）だが残り約7日で Nebius への移植が必要。Devpost ログイン要 | 未 |
| 6 | OpenAI Codex open source fund | https://openai.com/form/codex-open-source-fund/ | 未記載（"reviewed on an ongoing basis"） | Codex CLI と OpenAI モデルを使う OSS プロジェクト。1件最大 $25,000 の API クレジット | Web フォーム（項目は JS 描画のため未取得）。提出案は他者と重複しうる旨の同意文あり | **可**: Life Manager は MIT ライセンスの OSS で、Codex CLI（ChatGPT サインイン）で動く | 未 |
| 7 | Claude for Open Source（Anthropic） | https://claude.com/contact-sales/claude-for-oss | 未記載 | OSS メンテナ・貢献者。Claude Max 20x を6か月無料。基準例: 依存repo 500以上 / PR 100件以上マージ / 外部貢献者20人以上 / OpenSSF criticality 0.4以上 など | 申請フォーム | 条件付き: 上記基準は未計測で未達の見込み。ページに "Don't quite fit? … apply anyway" 枠あり | 未 |
| 8 | GitHub Secure Open Source Fund | https://resources.github.com/github-secure-open-source-fund/ （表示先 github.com/open-source/github-secure-open-source-fund） | 未記載（"open on a rolling basis"） | OSS プロジェクトの現メンテナ（チームは最大2人）。3週間のセキュリティ教育＋資金（セキュリティ成果に連動） | Microsoft Forms の申請（https://forms.office.com/r/YN3MWEKQ5m）、選考後オンライン面接、プログラム参加の確約 | 可（個人メンテナ）。Forms のサインイン要否は未確認 | 未 |
| 9 | NLnet（Restack / Open Social 等の公募） | https://nlnet.nl/propose/ | 2026-11-03 12:00 CET（以後、奇数月の3日） | FOSS（オープンライセンス・オープン標準）。EU 支援基金は強い「欧州次元」が必要 | 短い申請フォーム（ログイン不要） | **応募不可**: 生成AIポリシー v2.0（2026-10-20）で提案書の生成AI作成を禁止（https://nlnet.nl/news/2026/20261020-AI-policy.html ）。加えて EU 基金は欧州次元が要件 | 未 |
| 10 | AWS Activate Founders | https://aws.amazon.com/startups/credits | 未記載（随時） | 自己資金のスタートアップ。Pre-Series B・設立10年以内・AWS 有料プラン。$1,000 から最大 $5,000 | AWS アカウント、製品・資金段階・会社情報 | 条件付き: AWS アカウントへのログインが必要。会社要件の厳密さは未確認 | 未 |
| 11 | Kiro Startup Credits（AWS） | https://kiro.dev/startups/ | 未記載（期間限定・随時審査） | Early〜Series A。最大1年分の Kiro Pro+。Activate クレジット保有中は対象外 | 会社ドメインと一致するビジネスメール、AWS Account ID | 条件付き: ドメインメールと AWS アカウントが必要。除外国リストに日本なし | 未 |
| 12 | Google for Startups Cloud Program（Start 枠 $2k） | https://cloud.google.com/startup | 未記載（随時） | Start: 設立2年以内・動く MVP・明確なビジネスモデル・近くVC調達予定。consultancies / agencies は対象外 | 課金アカウントID、稼働中の会社サイト（AI生成文が多いと却下あり）、サイトと同ドメインのメール | 条件付き: ドメインメール・GCP ログインが必要。受託主体だと agency 扱いの懸念 | 未 |
| 13 | Microsoft for Startups | https://www.microsoft.com/en-us/startups | 未記載 | スタートアップ。最大 $150,000 のクレジット | ポータル経由（取得ページに詳細要件なし） | 条件付き: 詳細要件未取得、ポータルのログイン要 | 未 |
| 14 | IPA 未踏IT人材発掘・育成事業 2027年度 | https://www.ipa.go.jp/jinzai/mitou/it/2026/koubo.html | 未記載（2027年度公募は未公表。参考: 2026年度はエントリー 2025-11-10〜2026-03-11、締切 2026-03-12 16:59） | 個人または個人のグループ（法人不可）。期間中は日本在住 | 電子申請（Google Forms）、事前エントリー、所属組織の承諾書（採択後） | 可（公募開始待ち）。法人不要なので相性が良い | 未 |

## 締切済み・対象外（確認済み、表に入れない）

- 未踏アドバンスト 2026年度下期: 締切 2026-09-25（https://www.ipa.go.jp/jinzai/mitou/advanced/2026second/koubo.html ）
- NEDO NEP 開拓コース 2026年度: 締切 2026-02-24（DuckDuckGo の検索結果で NEDO 公募 CA2_100510 と NEP 告知を確認。一次ページは未取得。次年度は未公表）
- Anthropic Claude Startups: "current cohort is now full"（https://www.anthropic.com/startups ）
- Google for Startups Accelerator: Japan: "Applications are now closed"（https://startup.google.com/programs/accelerator/japan/ ）
- AI Grant: "Applications for Batch 4 are closed"（https://aigrant.com/ ）
- 東京都 創業助成事業: TOKYO創業ステーション・公社サイトとも 2026-10-22 22:00 からメンテナンス中で一次ソース未取得。復旧後に再取得する。

## 上位3件（適合度 × 締切の近さ × ログイン不要のテキストフォーム）

ログイン不要・テキストのみで出せて締切が近い行（#9 NLnet）は AI 作成提案禁止で除外。ハッカソンは Devpost ログインと動画が必要。残る随時枠から適合度順に選んだ:

1. OpenAI Codex open source fund（随時）→ [funding-drafts/codex-open-source-fund.md](funding-drafts/codex-open-source-fund.md)
2. GitHub Secure Open Source Fund（随時）→ [funding-drafts/github-secure-open-source-fund.md](funding-drafts/github-secure-open-source-fund.md)
3. Claude for Open Source（随時、"apply anyway" 枠）→ [funding-drafts/claude-for-open-source.md](funding-drafts/claude-for-open-source.md)

次の候補: #3 PayPal AI Hackathon（11/12）は動画を作れるなら最も締切が近い賞金枠。#14 未踏IT は 2027年度公募が出たら最優先で着手する。
