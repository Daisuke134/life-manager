"use strict";

const crypto = require("node:crypto");

// Copy stays local and deterministic. Background and text generation must not
// call a paid model; vary a seed per scheduled slot and render with Pillow.
const FAMILY_BRIEFS_BY_LOCALE = Object.freeze({
  ja: Object.freeze({
    "question-hook": "specific everyday situation followed by four coherent affirmations",
    listicle: "four numbered affirmations for one everyday situation",
    "myth-vs-fact": "a situation-specific belief followed by four gentle alternatives",
  }),
  en: Object.freeze({
    "question-hook": "specific everyday situation followed by four coherent affirmations",
    listicle: "four numbered affirmations for one everyday situation",
    "myth-vs-fact": "a situation-specific belief followed by four gentle alternatives",
  }),
});
const FAMILY_BRIEFS = FAMILY_BRIEFS_BY_LOCALE.ja;

// Keep the opening and its four-slide narrative together when rotating slots.
const SCENES = Object.freeze({
  ja: Object.freeze([
    {
      "question-hook": ["寝る前に、今日の失敗ばかり\n思い出してない？", "夜になると、今日のミスだけ\n思い出してしまう？", "ひとつの嫌な場面を、\nベッドまで連れてきてない？"],
      listicle: ["一日の終わりに読みたい\n自分への言葉４つ", "寝る前に、\nこの４つだけ読んで", "しんどい一日を終えるための\n自分への言葉４つ"],
      "myth-vs-fact": ["うまくいかない一日＝\nダメな自分？", "うまくいかない日も、\n自分の価値は変わらない", "今日がつらくても、\nあなた全部がダメなわけじゃない"],
      body: ["今日の失敗だけが、私のすべてじゃない", "できなかったことは、明日考えてもいい", "終わった一日を、今夜やり直さなくていい", "今日の私は、ここまででいい"],
    },
    {
      "question-hook": ["SNSを閉じたあと、\n自分だけ遅れて見える？", "誰かの投稿ひとつで、\n自分の毎日が小さく見える？", "人の報告が、\n自分への催促に聞こえてない？"],
      listicle: ["誰かと比べたあとに読む\n自分への言葉４つ", "また比べてしまう前に、\nこの４つを読んで", "SNSに疲れた日に読む\n自分への言葉４つ"],
      "myth-vs-fact": ["誰かの近況＝\n私の締め切り？", "誰かのハイライトは、\nあなたの締め切りじゃない", "人の幸せを喜ぶことと、\n自分のペースは両立できる"],
      body: ["誰かの近況は、私の締め切りじゃない", "見えているのは、その人の一部分", "私には、私が知っている積み重ねがある", "今日は、自分の次の一歩に戻ろう"],
    },
    {
      "question-hook": ["仕事は終わったのに、\n頭の中では残業してる？", "退勤したのに、\nまだ返信を考えてる？", "一通の仕事メールを、\n家まで連れてきてない？"],
      listicle: ["仕事から帰った自分へ\n伝えたい言葉４つ", "仕事の連絡を開く前に、\nこの４つを読んで", "帰っても仕事が離れない日の\n自分への言葉４つ"],
      "myth-vs-fact": ["仕事を考え続けるほど\nちゃんとした人？", "仕事に渡すのは勤務時間。\nあなたの一日全部じゃない", "仕事を置くことは、\n無責任になることじゃない"],
      body: ["今日の仕事は、ここで一区切り", "返信のない時間に、答えを作らなくていい", "仕事以外の時間も、私の時間", "続きは、次の勤務時間の私に任せよう"],
    },
    {
      "question-hook": ["ひとつのミスで、\n今日全部を否定してない？", "ひとつのミスから、\n人生全部を振り返ってない？", "自分にだけ、\nいちばん厳しい言葉をかけてない？"],
      listicle: ["ミスした日に読みたい\n自分への言葉４つ", "ミスしたあとに、\nこの４つを読んで", "ひとつのミスで消えない\n自分への言葉４つ"],
      "myth-vs-fact": ["ミスをした私には\nやさしくしちゃダメ？", "自分の敵にならなくても、\nミスは直せる", "ミスは、したこと。\nあなたそのものじゃない"],
      body: ["ミスをしたことと、私の価値は別の話", "直せるところを、ひとつずつ直そう", "自分を責め続けなくても、学べる", "次の行動を選ぶ余地は、まだある"],
    },
    {
      "question-hook": ["朝、予定を見ただけで\nもう疲れてない？", "朝ごはんの前から、\n予定表に疲れてない？", "まだ朝なのに、\n夜の心配まで背負ってない？"],
      listicle: ["忙しい朝の自分へ\n伝えたい言葉４つ", "ベッドを出る前に、\nこの４つを読んで", "忙しい一日を始める前の\n小さな言葉４つ"],
      "myth-vs-fact": ["一日分の予定を\n今すべて背負う必要ある？", "小さく始めることも、\nちゃんと始めること", "ゆっくりな朝でも、\n無駄な一日とは決まらない"],
      body: ["一日を全部、今こなさなくていい", "まずは、最初のひとつから", "私のペースを、途中で調整してもいい", "小さく始めることも、始めること"],
    },
    {
      "question-hook": ["休んでいるのに、\n何もしてない自分を責めてる？", "何もしない時間まで、\n悪いことに感じてない？", "休憩のたびに、\n自分を責める時間にしてない？"],
      listicle: ["休むのが苦手な自分へ\n伝えたい言葉４つ", "休むのをやめる前に、\nこの４つを読んで", "後回しにした休憩のための\n自分への言葉４つ"],
      "myth-vs-fact": ["全部終わらないと\n休んじゃダメ？", "休息は、全部終えた人だけの\nごほうびじゃない", "静かな時間のために、\n成果を出し続けなくていい"],
      body: ["休むために、すべてを終える必要はない", "何も生み出さない時間も、持っていい", "私の価値は、今日の成果だけでは決まらない", "今は休む、という選択をしていい"],
    },
    {
      "question-hook": ["さっきの一言、\n頭の中で何度も再生してる？", "もう終わった会話を、\nまだ頭の中で直してる？", "短い返信から、\n長い物語を作ってない？"],
      listicle: ["会話を振り返りすぎた時の\n自分への言葉４つ", "そのメッセージを読み返す前に、\nこの４つを読んで", "一通の返信が気になる日の\n自分への言葉４つ"],
      "myth-vs-fact": ["相手の沈黙＝\n私への悪い評価？", "短い返信ひとつで、\nあなた全部は決まらない", "返事の間は、\n失敗した証拠じゃない"],
      body: ["相手の気持ちを、今すべて知ることはできない", "想像と、実際に言われたことは分けよう", "必要なら、次に会った時に確かめられる", "ひとつの会話で、私のすべては決まらない"],
    },
    {
      "question-hook": ["三日空いただけで、\nもう続かない人だと思ってる？", "一日空いただけで、\nもう終わりにしてない？", "再開するための、\n完璧な月曜を待ってない？"],
      listicle: ["習慣が途切れた日の\n自分への言葉４つ", "自分を諦める前に、\nこの４つを読んで", "また始める自分への\n小さな言葉４つ"],
      "myth-vs-fact": ["途切れたら\n最初から全部やり直し？", "また始めることも、\n続けることのひとつ", "小さく戻るだけでいい。\n全部ゼロにはならない"],
      body: ["空いた日があっても、積み重ねは消えない", "前と同じ大きさで、再開しなくていい", "今日は、小さくひとつだけ", "戻ってくることも、続けることの一部"],
    },
  ]),
  en: Object.freeze([
    {
      "question-hook": ["Still replaying today when you get into bed?", "Does your brain save every mistake for bedtime?", "Why does one bad moment follow you to bed?"],
      listicle: ["4 lines for when your day follows you to bed", "Read these 4 lines before you fall asleep", "4 mantras for when today still feels heavy"],
      "myth-vs-fact": ["Does one hard day mean you failed?", "A hard day does not make you a failure.", "You can have a hard day and still be enough."],
      body: ["Today's mistakes are not my whole story.", "I can leave unfinished things for tomorrow.", "I do not have to redo this day tonight.", "I have done enough for this moment."],
    },
    {
      "question-hook": ["Close the app and feel behind everyone else?", "Did one scroll make your own life feel too small?", "Why does their good news feel like your deadline?"],
      listicle: ["4 lines to read after comparing your life online", "Read these 4 lines before you compare again", "4 lines for when everyone looks ahead of you"],
      "myth-vs-fact": ["Is someone else's milestone your deadline?", "Someone else's highlight is not your finish line.", "You can be happy for them and still take your time."],
      body: ["Someone else's milestone is not my deadline.", "A post shows one part of someone else's life.", "My quiet progress still belongs to me.", "I can return to my own next step."],
    },
    {
      "question-hook": ["Work is over. Why is your mind still at work?", "Off the clock, but still drafting that reply?", "Why does one work message follow you home?"],
      listicle: ["4 reminders for when you bring work home in your head", "Read these 4 lines before you check work again", "4 mantras for when your shift ends but worry stays"],
      "myth-vs-fact": ["Do you have to stay mentally on the clock?", "Your job gets work hours. It does not get every hour.", "Putting work down does not mean you care less."],
      body: ["I can put today's work down for now.", "An unanswered message does not need an imagined answer.", "My time outside work belongs to me too.", "The next workday can hold the next work task."],
    },
    {
      "question-hook": ["Letting one mistake rewrite your entire day?", "One mistake. Why are you replaying your whole life?", "Are you talking to yourself like your worst critic?"],
      listicle: ["4 things to tell yourself after making a mistake", "Read these 4 lines after that awkward mistake", "4 reminders one mistake cannot erase"],
      "myth-vs-fact": ["Do you need to be cruel to yourself to improve?", "You can fix a mistake without becoming your enemy.", "One mistake is something you did, not who you are."],
      body: ["Making a mistake does not define my worth.", "I can repair what is mine to repair.", "I can learn without insulting myself.", "I still get to choose what I do next."],
    },
    {
      "question-hook": ["Already overwhelmed before your morning starts?", "Did your to-do list drain you before breakfast?", "Why are you carrying tonight's worries this morning?"],
      listicle: ["4 lines for a morning with too much on your list", "Read these 4 lines before you get out of bed", "4 small reminders before a busy day begins"],
      "myth-vs-fact": ["Do you have to carry the whole day at once?", "One small start still counts on a busy morning.", "A slow morning does not mean a wasted day."],
      body: ["I do not have to finish the whole day right now.", "I can start with the first small thing.", "I am allowed to adjust my pace.", "Starting small still counts as starting."],
    },
    {
      "question-hook": ["Trying to rest but feeling guilty for doing nothing?", "Why does doing nothing feel like doing something wrong?", "Are you turning every break into another guilt trip?"],
      listicle: ["4 reminders for when resting feels unearned", "Read these 4 lines before you cancel your break", "4 mantras for the rest you keep postponing"],
      "myth-vs-fact": ["Must everything be finished before you rest?", "Rest is not a prize for finishing everything.", "You do not have to earn every quiet moment."],
      body: ["I do not have to finish everything to take a break.", "I am allowed time that produces nothing.", "My worth is more than today's output.", "Rest can be the choice I make right now."],
    },
    {
      "question-hook": ["Replaying that one sentence from your conversation?", "Still editing a conversation that already ended?", "Did one quiet reply turn into a whole story?"],
      listicle: ["4 lines for when a conversation keeps replaying", "Read these 4 lines before you reread that message", "4 reminders when one reply gets stuck in your head"],
      "myth-vs-fact": ["Does their silence tell you what they think of you?", "Their short reply is not your entire story.", "A pause in the chat is not proof you did something wrong."],
      body: ["I cannot know every thought someone else has.", "I can separate what was said from what I imagined.", "If I need clarity, I can ask when the time is right.", "One conversation is not my entire identity."],
    },
    {
      "question-hook": ["Missed a few days and ready to give up completely?", "Missed one day. Why are you calling it the end?", "Are you waiting for a perfect Monday to restart?"],
      listicle: ["4 reminders for restarting a habit you dropped", "Read these 4 lines before you quit on yourself", "4 small reminders for your next fresh start"],
      "myth-vs-fact": ["Does missing a day erase the days you showed up?", "Starting again is still part of showing up.", "You can start small without starting from zero."],
      body: ["A gap does not erase what I already practiced.", "I can return with a smaller version.", "One small step is enough to begin again.", "Coming back is part of continuing."],
    },
  ]),
});

function seedNumber(seed, label) {
  return crypto.createHash("sha256").update(`${seed}\u0000${label}`).digest().readUInt32BE(0);
}

function pickScene(scenes, familyId, seed, avoidTexts) {
  const normalize = (text) => String(text).replace(/\s+/g, " ").trim().toLocaleLowerCase();
  const used = new Set(avoidTexts.map(normalize));
  const candidates = scenes.flatMap((scene) => scene[familyId].map((hook) => ({ hook, body: scene.body })));
  const start = seedNumber(seed, "hook") % candidates.length;
  for (let offset = 0; offset < candidates.length; offset += 1) {
    const candidate = candidates[(start + offset) % candidates.length];
    if (!used.has(normalize(candidate.hook))) return candidate;
  }
  return candidates[start];
}

async function generateSlideCopy({ familyId, locale = "ja", variantSeed = "default", avoidTexts = [] } = {}) {
  const normalizedLocale = SCENES[locale] ? locale : "ja";
  if (!Object.hasOwn(FAMILY_BRIEFS_BY_LOCALE[normalizedLocale], familyId)) {
    throw new Error(`family ${familyId} is not configured for locale ${normalizedLocale}`);
  }
  const seed = `${normalizedLocale}:${familyId}:${String(variantSeed)}`;
  const scene = pickScene(SCENES[normalizedLocale], familyId, seed, avoidTexts);
  const labels = normalizedLocale === "ja" ? ["ひとつめ", "ふたつめ", "みっつめ", "よっつめ"] : ["1", "2", "3", "4"];
  return {
    hook: scene.hook,
    body: scene.body.map((line, index) => familyId === "listicle" ? `${labels[index]}: ${line}` : line),
    costUsd: 0,
  };
}

function familyForStyleHint(styleHint, locale = "ja") {
  const families = Object.keys(FAMILY_BRIEFS_BY_LOCALE[locale] || FAMILY_BRIEFS);
  const index = crypto.createHash("sha256").update(String(styleHint || "")).digest()[0] % families.length;
  return families[index];
}

async function generateVideoHookText({ styleHint, avoidTexts = [], locale = "en", variantSeed } = {}) {
  const familyId = familyForStyleHint(styleHint, locale);
  const copy = await generateSlideCopy({
    familyId,
    avoidTexts,
    locale,
    variantSeed: variantSeed || `${styleHint || ""}:${avoidTexts.join("|")}`,
  });
  return { hook: copy.hook, costUsd: 0 };
}

module.exports = { FAMILY_BRIEFS, FAMILY_BRIEFS_BY_LOCALE, familyForStyleHint, generateSlideCopy, generateVideoHookText };
