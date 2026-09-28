category: ライティング · tags: Humanizer, Japanese, AI Writing

REVENUE-LEAK FIX (2026-09-28): live agent 3332784488 is agent_type=download with
a single "download" billing row and NO price (cyclePrice/oneTimeFee both null —
confirmed via publish-remote-status). Traffic API: 81 visitors/30d, 6 paid_orders,
sales_usd $0.00. Buyers get the package for $0. Comparable download-type sibling
Academic Humanizer (6839055303) earns $9.99/one-time. This same-Agent update sets
the missing one-time fee; everything else (title, description, skill) is unchanged.

## Pricing (Download mode — one-time fee, no cap/trial/hosted model; CP2 is
skipped for Download agents — verified 2026-09-28 via publish-remote-status:
is_confirmed_config_keys=false on the live download version)
| cycle | price | cap | trial |
|---|---|---|---|
| download | $9.99 | - | - |

## Title
Japanese Humanizer — Sound Human, Not AI

## shortDescription
Use when your Japanese draft still reads AI-written. For bloggers, PR teams, marketers, and students: paste the text and get a human-sounding rewrite, plus a diff of every AI tell removed. It replaces vague AI phrasing — 浮き彫りになった, 多面的な, 〜ではないでしょうか, 今後の展開が期待される — with concrete facts and one clear voice. Facts are never invented or changed, only the wording. Output = the rewritten full text + a change log of what was fixed.

## welcomeMessage
👋 日本語の「AIが書いた感じ」を取って、人が書いたように直します。ブロガー・PR・マーケター・学生向け。テキストを貼ると、書き換え全文＋「どのAIっぽさをどう直したか」の変更点リストを返します。事実は足さない・変えない、直すのは文体だけ。

例:
✍️「このAIっぽい日本語を自然にして: [貼り付け]」
🔍「どこがAIっぽい? 診断して直して: [貼り付け]」
まず直したい日本語を貼ってください。

## detailedDescription
# Japanese Humanizer — Sound Human, Not AI

日本語の下書きが「AIが書いた感じ」のまま残っているときに使う。ブロガー、PR・広報、マーケター、学生、レポート作成者向け。テキストを貼ると、(1) 人が書いたように読める書き換え全文と、(2) どのAI tellをどう直したかの変更点リストが返る。

## ✨ What it does
評価語をそのまま消すのではなく、「浮き彫りになった」「多面的なアプローチ」「〜ではないでしょうか」「今後の展開が期待される」などを、具体的な事実・数字・自分の判断に置き換える。**事実は足さない・変えない。直すのは文体だけ。**

## 📝 Example
**Before（AIが書いたまま）**
> 本取り組みは地域経済の活性化において極めて重要な役割を果たしており、その意義は大きいと言えるだろう。多面的なアプローチによって持続可能なまちづくりを推進することが可能です。

**After（humanize後）**
> このプロジェクトは、地域経済を立て直すために動いている。やり方を一つに絞らず、補助金が切れても続くまちづくりを進める。

加えて「何を・なぜ直したか」の変更点リストが付くので、自分の書き癖の学習にも使える。

## ⚙️ How to use
1️⃣ 直したい日本語テキストを貼る。
2️⃣ 「humanizeして」「AIっぽさを取って」と指示する。
3️⃣ 書き換え文＋変更点リストを受け取る。

ブログ記事、プレスリリース、レポート、メール、SNS投稿、論文要旨——人に読ませる日本語ならどれでも。

## 💡 What makes it different
1. **日本語特化** — 英語Humanizerの直訳でなく、日本語のAI tell（評価語・冗長な丁寧表現・空虚な締め）を狙って直す。
2. **変更点リスト付き** — 何をなぜ直したかが見えるので、次から自分で避けられる。
3. **事実を捏造しない** — 文体だけ直す。数字や固有名詞は足さない・変えない。

## 👤 Who it's for
ブロガー、PR・広報、マーケター、学生、レポート・論文を書く人。
