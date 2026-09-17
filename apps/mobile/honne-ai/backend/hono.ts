import { Hono } from "hono";
import { cors } from "hono/cors";

const app = new Hono();

app.use("*", cors());

const TOOLKIT_URL = process.env["EXPO_PUBLIC_TOOLKIT_URL"] ?? "https://toolkit.rork.com";

const aiResponseJsonSchema = {
  type: "object",
  properties: {
    honne: { type: "string" },
    psychologicalState: { type: "string" },
    suggestedResponse: { type: "string" },
    emotionLevel: { type: "number", minimum: 1, maximum: 5 },
  },
  required: ["honne", "psychologicalState", "suggestedResponse", "emotionLevel"],
};

app.get("/", (c) => {
  return c.json({ status: "ok", message: "API is running" });
});

app.get("/privacy/ja", (c) => {
  return c.html(`<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>プライバシーポリシー - 本音翻訳AI</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans',sans-serif;max-width:700px;margin:0 auto;padding:24px 16px;color:#1d1d1f;line-height:1.7;background:#fff}
h1{font-size:1.6em;margin-bottom:8px}
h2{font-size:1.2em;margin-top:32px;border-bottom:1px solid #e5e5e5;padding-bottom:8px}
p,li{font-size:0.95em}
ul{padding-left:20px}
.updated{color:#86868b;font-size:0.85em}
</style>
</head>
<body>
<h1>プライバシーポリシー</h1>
<p><strong>本音翻訳AI</strong></p>
<p class="updated">最終更新日: 2026年3月7日</p>

<h2>1. はじめに</h2>
<p>本音翻訳AI（以下「本アプリ」）は、ユーザーのプライバシーを尊重し、個人データの保護に努めます。本プライバシーポリシーは、本アプリが収集、使用、共有する情報について説明します。</p>

<h2>2. 収集する情報</h2>
<p>本アプリは以下の情報を収集・処理します：</p>
<ul>
<li><strong>ユーザーが入力したメッセージ・会話文</strong>：AI分析機能を利用する際に、ユーザーが任意で入力するテキストデータ</li>
<li><strong>関係性の選択情報</strong>：分析の精度を高めるためにユーザーが選択する関係性カテゴリ（恋人、友人、職場など）</li>
<li><strong>サブスクリプション情報</strong>：RevenueCat社を通じて処理される購入・サブスクリプションの状態情報</li>
<li><strong>利用回数</strong>：無料利用制限の管理のため、デバイス上にローカル保存される翻訳利用回数</li>
</ul>
<p>本アプリは、氏名、メールアドレス、電話番号、位置情報などの個人を特定できる情報は収集しません。</p>

<h2>3. 第三者AIサービスへのデータ送信</h2>
<p><strong>重要：</strong>本アプリは、メッセージ分析機能を提供するために、ユーザーが入力したテキストデータを第三者のAIサービスに送信します。</p>
<ul>
<li><strong>送信されるデータ</strong>：ユーザーが入力したメッセージ・会話文および選択した関係性カテゴリ</li>
<li><strong>送信先</strong>：OpenAI社が提供するAI言語モデルサービス（Rork Toolkit経由）</li>
<li><strong>送信目的</strong>：入力されたメッセージの心理分析、本音の推測、返答提案の生成</li>
<li><strong>ユーザーの同意</strong>：アプリは初回利用時にデータ送信について明示的な同意を求めます。同意しない場合、分析機能は利用できません。</li>
</ul>
<p>OpenAI社のプライバシーポリシーについては<a href="https://openai.com/policies/privacy-policy" target="_blank">こちら</a>をご参照ください。</p>

<h2>4. データの利用目的</h2>
<ul>
<li>メッセージの心理分析と本音翻訳の提供</li>
<li>最適な返答の提案</li>
<li>サブスクリプションの管理</li>
<li>アプリの機能改善</li>
</ul>

<h2>5. データの保存</h2>
<ul>
<li>翻訳履歴はデバイス上にのみローカル保存されます</li>
<li>サーバー側でユーザーの入力データを永続的に保存することはありません</li>
<li>AI分析のために送信されたデータは、OpenAI社のデータ保持ポリシーに従います</li>
</ul>

<h2>6. データの共有</h2>
<p>本アプリは以下の第三者とデータを共有する場合があります：</p>
<ul>
<li><strong>OpenAI社</strong>（Rork Toolkit経由）：メッセージ分析のためのテキストデータ</li>
<li><strong>RevenueCat社</strong>：サブスクリプション管理のための購入情報</li>
<li><strong>Apple社</strong>：App内課金の処理</li>
</ul>
<p>上記の第三者は、それぞれのプライバシーポリシーに基づき、ユーザーデータの保護に同等以上の措置を講じています。</p>

<h2>7. ユーザーの権利</h2>
<ul>
<li>設定画面からデータ同意をリセットし、AI分析へのデータ送信を停止できます</li>
<li>デバイスからアプリを削除することで、ローカルに保存された全データを削除できます</li>
</ul>

<h2>8. 子供のプライバシー</h2>
<p>本アプリは13歳未満のお子様を対象としておらず、意図的にお子様から個人情報を収集することはありません。</p>

<h2>9. ポリシーの変更</h2>
<p>本プライバシーポリシーは予告なく変更される場合があります。重要な変更がある場合は、アプリ内で通知します。</p>

<h2>10. お問い合わせ</h2>
<p>プライバシーに関するご質問は、以下までご連絡ください：</p>
<p>メール：support@aniccaai.com</p>
</body>
</html>`);
});

app.get("/privacy/en", (c) => {
  return c.html(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Privacy Policy - Honne Translation AI</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:700px;margin:0 auto;padding:24px 16px;color:#1d1d1f;line-height:1.7;background:#fff}
h1{font-size:1.6em;margin-bottom:8px}
h2{font-size:1.2em;margin-top:32px;border-bottom:1px solid #e5e5e5;padding-bottom:8px}
p,li{font-size:0.95em}
ul{padding-left:20px}
.updated{color:#86868b;font-size:0.85em}
</style>
</head>
<body>
<h1>Privacy Policy</h1>
<p><strong>Honne Translation AI (本音翻訳AI)</strong></p>
<p class="updated">Last updated: March 7, 2026</p>

<h2>1. Introduction</h2>
<p>Honne Translation AI (the "App") respects your privacy and is committed to protecting your personal data. This Privacy Policy explains what information the App collects, uses, and shares.</p>

<h2>2. Information We Collect</h2>
<p>The App collects and processes the following information:</p>
<ul>
<li><strong>User-entered messages and conversations</strong>: Text data that users voluntarily input when using the AI analysis feature</li>
<li><strong>Relationship selection</strong>: The relationship category selected by the user (e.g., romantic partner, friend, coworker) to improve analysis accuracy</li>
<li><strong>Subscription information</strong>: Purchase and subscription status processed through RevenueCat</li>
<li><strong>Usage count</strong>: Translation usage count stored locally on the device for managing free usage limits</li>
</ul>
<p>The App does not collect personally identifiable information such as names, email addresses, phone numbers, or location data.</p>

<h2>3. Data Sharing with Third-Party AI Service</h2>
<p><strong>Important:</strong> To provide the message analysis feature, the App sends user-entered text data to a third-party AI service.</p>
<ul>
<li><strong>Data sent</strong>: User-entered messages/conversations and the selected relationship category</li>
<li><strong>Sent to</strong>: OpenAI's AI language model service (via Rork Toolkit)</li>
<li><strong>Purpose</strong>: Psychological analysis of input messages, inference of true feelings, and generation of suggested responses</li>
<li><strong>User consent</strong>: The App requests explicit consent before sending any data for analysis on first use. If consent is not given, the analysis feature cannot be used.</li>
</ul>
<p>For OpenAI's privacy practices, please refer to <a href="https://openai.com/policies/privacy-policy" target="_blank">OpenAI's Privacy Policy</a>.</p>

<h2>4. How We Use Your Data</h2>
<ul>
<li>Providing psychological analysis and true feelings translation of messages</li>
<li>Suggesting optimal responses</li>
<li>Managing subscriptions</li>
<li>Improving app functionality</li>
</ul>

<h2>5. Data Storage</h2>
<ul>
<li>Translation history is stored locally on the device only</li>
<li>We do not permanently store user input data on our servers</li>
<li>Data sent for AI analysis is subject to OpenAI's data retention policies</li>
</ul>

<h2>6. Data Sharing</h2>
<p>The App may share data with the following third parties:</p>
<ul>
<li><strong>OpenAI</strong> (via Rork Toolkit): Text data for message analysis</li>
<li><strong>RevenueCat</strong>: Purchase information for subscription management</li>
<li><strong>Apple</strong>: In-app purchase processing</li>
</ul>
<p>Each of these third parties maintains privacy protections equal to or greater than those described in this policy.</p>

<h2>7. Your Rights</h2>
<ul>
<li>You can reset your data consent in the Settings screen to stop sending data for AI analysis</li>
<li>You can delete all locally stored data by removing the App from your device</li>
</ul>

<h2>8. Children's Privacy</h2>
<p>The App is not intended for children under 13 and does not knowingly collect personal information from children.</p>

<h2>9. Changes to This Policy</h2>
<p>This Privacy Policy may be updated from time to time. Significant changes will be communicated through the App.</p>

<h2>10. Contact Us</h2>
<p>For privacy-related questions, please contact us at:</p>
<p>Email: support@aniccaai.com</p>
</body>
</html>`);
});

app.get("/terms/ja", (c) => {
  return c.html(`<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>利用規約 - 本音翻訳AI</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans',sans-serif;max-width:700px;margin:0 auto;padding:24px 16px;color:#1d1d1f;line-height:1.7;background:#fff}
h1{font-size:1.6em;margin-bottom:8px}
h2{font-size:1.2em;margin-top:32px;border-bottom:1px solid #e5e5e5;padding-bottom:8px}
p,li{font-size:0.95em}
ul{padding-left:20px}
.updated{color:#86868b;font-size:0.85em}
</style>
</head>
<body>
<h1>利用規約</h1>
<p><strong>本音翻訳AI</strong></p>
<p class="updated">最終更新日: 2026年3月7日</p>

<h2>1. サービスの概要</h2>
<p>本音翻訳AI（以下「本アプリ」）は、ユーザーが入力したメッセージや会話文をAIが分析し、相手の本音や心理状態を推測するサービスです。</p>

<h2>2. AI分析の免責事項</h2>
<p>本アプリが提供する分析結果はAIによる推測であり、正確性を保証するものではありません。分析結果に基づく判断や行動は、ユーザーの自己責任で行ってください。</p>

<h2>3. サブスクリプション</h2>
<ul>
<li>本アプリは無料版とプレミアム版を提供しています</li>
<li>プレミアムサブスクリプションはApple IDアカウントに請求されます</li>
<li>サブスクリプションは現在の期間終了の24時間前までにキャンセルしない限り自動更新されます</li>
<li>サブスクリプションの管理・キャンセルはiPhoneの設定 > Apple ID > サブスクリプションから行えます</li>
</ul>

<h2>4. データの取り扱い</h2>
<p>入力されたメッセージは第三者のAIサービス（OpenAI社）に送信されます。詳細はプライバシーポリシーをご確認ください。</p>

<h2>5. 禁止事項</h2>
<ul>
<li>アプリの不正利用、リバースエンジニアリング</li>
<li>他者への嫌がらせや脅迫を目的とした利用</li>
<li>違法な目的での利用</li>
</ul>

<h2>6. お問い合わせ</h2>
<p>メール：support@aniccaai.com</p>
</body>
</html>`);
});

app.get("/terms/en", (c) => {
  return c.html(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Terms of Use - Honne Translation AI</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:700px;margin:0 auto;padding:24px 16px;color:#1d1d1f;line-height:1.7;background:#fff}
h1{font-size:1.6em;margin-bottom:8px}
h2{font-size:1.2em;margin-top:32px;border-bottom:1px solid #e5e5e5;padding-bottom:8px}
p,li{font-size:0.95em}
ul{padding-left:20px}
.updated{color:#86868b;font-size:0.85em}
</style>
</head>
<body>
<h1>Terms of Use</h1>
<p><strong>Honne Translation AI (本音翻訳AI)</strong></p>
<p class="updated">Last updated: March 7, 2026</p>

<h2>1. Service Overview</h2>
<p>Honne Translation AI (the "App") uses AI to analyze user-entered messages and conversations to infer the true feelings and psychological state of the other party.</p>

<h2>2. AI Analysis Disclaimer</h2>
<p>Analysis results provided by the App are AI-generated inferences and are not guaranteed to be accurate. Users are solely responsible for any decisions or actions taken based on analysis results.</p>

<h2>3. Subscriptions</h2>
<ul>
<li>The App offers both free and premium versions</li>
<li>Premium subscriptions are charged to your Apple ID account</li>
<li>Subscriptions automatically renew unless cancelled at least 24 hours before the end of the current period</li>
<li>Manage or cancel subscriptions in iPhone Settings > Apple ID > Subscriptions</li>
</ul>

<h2>4. Data Handling</h2>
<p>Messages entered are sent to a third-party AI service (OpenAI). Please refer to our Privacy Policy for details.</p>

<h2>5. Prohibited Uses</h2>
<ul>
<li>Misuse, reverse engineering, or unauthorized access to the App</li>
<li>Using the App for harassment or intimidation</li>
<li>Using the App for any illegal purpose</li>
</ul>

<h2>6. Contact</h2>
<p>Email: support@aniccaai.com</p>
</body>
</html>`);
});

app.post("/translate", async (c) => {
  try {
    const body = await c.req.json();
    const { text, relationship } = body;

    if (!text || !relationship) {
      return c.json({ error: "text and relationship are required" }, 400);
    }

    const prompt = `あなたは人間関係の専門家であり、心理カウンセラーです。
ユーザーが送ってきたメッセージや会話文を分析し、JSON形式で回答してください。

関係性: ${relationship}

以下のメッセージを分析してください：

${text}`;

    const response = await fetch(new URL("/llm/object", TOOLKIT_URL).toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [
          { role: "user", content: prompt },
        ],
        schema: aiResponseJsonSchema,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("[translate] Toolkit error:", response.status, errorText);
      return c.json({ error: "AI analysis failed" }, 500);
    }

    const data = await response.json();

    return c.json({ success: true, data: data.object });
  } catch (error: any) {
    console.error("[translate] Error:", error);
    return c.json({ error: error.message || "AI analysis failed" }, 500);
  }
});

export default app;

