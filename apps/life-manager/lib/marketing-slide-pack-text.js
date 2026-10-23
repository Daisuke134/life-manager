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
      "question-hook": "寝る前に、今日の失敗ばかり\n思い出してない？",
      listicle: "一日の終わりに読みたい\n自分への言葉４つ",
      "myth-vs-fact": "うまくいかない一日＝\nダメな自分？",
      body: ["今日の失敗だけが、私のすべてじゃない", "できなかったことは、明日考えてもいい", "終わった一日を、今夜やり直さなくていい", "今日の私は、ここまででいい"],
    },
    {
      "question-hook": "SNSを閉じたあと、\n自分だけ遅れて見える？",
      listicle: "誰かと比べたあとに読む\n自分への言葉４つ",
      "myth-vs-fact": "誰かの近況＝\n私の締め切り？",
      body: ["誰かの近況は、私の締め切りじゃない", "見えているのは、その人の一部分", "私には、私が知っている積み重ねがある", "今日は、自分の次の一歩に戻ろう"],
    },
    {
      "question-hook": "仕事は終わったのに、\n頭の中では残業してる？",
      listicle: "仕事から帰った自分へ\n伝えたい言葉４つ",
      "myth-vs-fact": "仕事を考え続けるほど\nちゃんとした人？",
      body: ["今日の仕事は、ここで一区切り", "返信のない時間に、答えを作らなくていい", "仕事以外の時間も、私の時間", "続きは、次の勤務時間の私に任せよう"],
    },
    {
      "question-hook": "ひとつのミスで、\n今日全部を否定してない？",
      listicle: "ミスした日に読みたい\n自分への言葉４つ",
      "myth-vs-fact": "ミスをした私には\nやさしくしちゃダメ？",
      body: ["ミスをしたことと、私の価値は別の話", "直せるところを、ひとつずつ直そう", "自分を責め続けなくても、学べる", "次の行動を選ぶ余地は、まだある"],
    },
    {
      "question-hook": "朝、予定を見ただけで\nもう疲れてない？",
      listicle: "忙しい朝の自分へ\n伝えたい言葉４つ",
      "myth-vs-fact": "一日分の予定を\n今すべて背負う必要ある？",
      body: ["一日を全部、今こなさなくていい", "まずは、最初のひとつから", "私のペースを、途中で調整してもいい", "小さく始めることも、始めること"],
    },
    {
      "question-hook": "休んでいるのに、\n何もしてない自分を責めてる？",
      listicle: "休むのが苦手な自分へ\n伝えたい言葉４つ",
      "myth-vs-fact": "全部終わらないと\n休んじゃダメ？",
      body: ["休むために、すべてを終える必要はない", "何も生み出さない時間も、持っていい", "私の価値は、今日の成果だけでは決まらない", "今は休む、という選択をしていい"],
    },
    {
      "question-hook": "さっきの一言、\n頭の中で何度も再生してる？",
      listicle: "会話を振り返りすぎた時の\n自分への言葉４つ",
      "myth-vs-fact": "相手の沈黙＝\n私への悪い評価？",
      body: ["相手の気持ちを、今すべて知ることはできない", "想像と、実際に言われたことは分けよう", "必要なら、次に会った時に確かめられる", "ひとつの会話で、私のすべては決まらない"],
    },
    {
      "question-hook": "三日空いただけで、\nもう続かない人だと思ってる？",
      listicle: "習慣が途切れた日の\n自分への言葉４つ",
      "myth-vs-fact": "途切れたら\n最初から全部やり直し？",
      body: ["空いた日があっても、積み重ねは消えない", "前と同じ大きさで、再開しなくていい", "今日は、小さくひとつだけ", "戻ってくることも、続けることの一部"],
    },
  ]),
  en: Object.freeze([
    {
      "question-hook": "Still replaying today when you get into bed?",
      listicle: "4 lines for when your day follows you to bed",
      "myth-vs-fact": "Does one hard day mean you failed?",
      body: ["Today's mistakes are not my whole story.", "I can leave unfinished things for tomorrow.", "I do not have to redo this day tonight.", "I have done enough for this moment."],
    },
    {
      "question-hook": "Close the app and feel behind everyone else?",
      listicle: "4 lines to read after comparing your life online",
      "myth-vs-fact": "Is someone else's milestone your deadline?",
      body: ["Someone else's milestone is not my deadline.", "A post shows one part of someone else's life.", "My quiet progress still belongs to me.", "I can return to my own next step."],
    },
    {
      "question-hook": "Work is over. Why is your mind still at work?",
      listicle: "4 reminders for when you bring work home in your head",
      "myth-vs-fact": "Do you have to stay mentally on the clock?",
      body: ["I can put today's work down for now.", "An unanswered message does not need an imagined answer.", "My time outside work belongs to me too.", "The next workday can hold the next work task."],
    },
    {
      "question-hook": "Letting one mistake rewrite your entire day?",
      listicle: "4 things to tell yourself after making a mistake",
      "myth-vs-fact": "Do you need to be cruel to yourself to improve?",
      body: ["Making a mistake does not define my worth.", "I can repair what is mine to repair.", "I can learn without insulting myself.", "I still get to choose what I do next."],
    },
    {
      "question-hook": "Already overwhelmed before your morning starts?",
      listicle: "4 lines for a morning with too much on your list",
      "myth-vs-fact": "Do you have to carry the whole day at once?",
      body: ["I do not have to finish the whole day right now.", "I can start with the first small thing.", "I am allowed to adjust my pace.", "Starting small still counts as starting."],
    },
    {
      "question-hook": "Trying to rest but feeling guilty for doing nothing?",
      listicle: "4 reminders for when resting feels unearned",
      "myth-vs-fact": "Must everything be finished before you rest?",
      body: ["I do not have to finish everything to take a break.", "I am allowed time that produces nothing.", "My worth is more than today's output.", "Rest can be the choice I make right now."],
    },
    {
      "question-hook": "Replaying that one sentence from your conversation?",
      listicle: "4 lines for when a conversation keeps replaying",
      "myth-vs-fact": "Does their silence tell you what they think of you?",
      body: ["I cannot know every thought someone else has.", "I can separate what was said from what I imagined.", "If I need clarity, I can ask when the time is right.", "One conversation is not my entire identity."],
    },
    {
      "question-hook": "Missed a few days and ready to give up completely?",
      listicle: "4 reminders for restarting a habit you dropped",
      "myth-vs-fact": "Does missing a day erase the days you showed up?",
      body: ["A gap does not erase what I already practiced.", "I can return with a smaller version.", "One small step is enough to begin again.", "Coming back is part of continuing."],
    },
  ]),
});

function seedNumber(seed, label) {
  return crypto.createHash("sha256").update(`${seed}\u0000${label}`).digest().readUInt32BE(0);
}

function pickScene(scenes, familyId, seed, avoidTexts) {
  const used = new Set(avoidTexts.map((text) => String(text).trim().toLocaleLowerCase()));
  const start = seedNumber(seed, "hook") % scenes.length;
  for (let offset = 0; offset < scenes.length; offset += 1) {
    const scene = scenes[(start + offset) % scenes.length];
    if (!used.has(scene[familyId].trim().toLocaleLowerCase())) return scene;
  }
  return scenes[start];
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
    hook: scene[familyId],
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
