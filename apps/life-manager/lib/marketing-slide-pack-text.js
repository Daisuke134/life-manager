"use strict";

const crypto = require("node:crypto");

// Copy stays local and deterministic. Background and text generation must not
// call a paid model; vary a seed per scheduled slot and render with Pillow.
const FAMILY_BRIEFS_BY_LOCALE = Object.freeze({
  ja: Object.freeze({
    "question-hook": "short question followed by a gentle reframe",
    listicle: "four numbered small habits",
    "myth-vs-fact": "a common belief followed by a gentle alternative",
  }),
  en: Object.freeze({
    "question-hook": "short question followed by a gentle reframe",
    listicle: "four numbered small habits",
    "myth-vs-fact": "a common belief followed by a gentle alternative",
  }),
});
const FAMILY_BRIEFS = FAMILY_BRIEFS_BY_LOCALE.ja;

const BANKS = Object.freeze({
  ja: Object.freeze({
    "question-hook": Object.freeze([
      "今日の自分に、\n厳しすぎない？",
      "「まだ足りない」が\n口癖になってない？",
      "疲れた自分に、\n何と声をかける？",
      "小さくできたこと、\n見落としてない？",
      "うまくいかない日も、\n自分を責めてない？",
      "予定の前に、\n気分を確かめてる？",
      "休むことまで、\n後回しにしてない？",
      "不安な夜、\nひとりで抱えてない？",
    ]),
    listicle: Object.freeze([
      "気持ちを整える\n小さな習慣４選",
      "朝の自分を助ける\nやさしい習慣４つ",
      "心に余白をつくる\n小さなヒント４選",
      "疲れた日に試す\n自分への声かけ４選",
      "今日からできる\n気分の切り替え４選",
      "自分を責めないための\n小さな工夫４選",
      "忙しい朝にできる\n心の整え方４つ",
      "落ち着きたい時の\n小さな合図４選",
    ]),
    "myth-vs-fact": Object.freeze([
      "「気合いで直す」は\n本当に近道？",
      "いつも前向きで\nいなきゃダメ？",
      "休むのは遅れ？\n整える時間？",
      "完璧にできないと\n意味がない？",
      "「まだ足りない」は\n本当のこと？",
      "比べ続ければ\n前に進める？",
      "自分を責めるほど\n早く変われる？",
      "強くなるとは\n無理を続けること？",
    ]),
  }),
  en: Object.freeze({
    "question-hook": Object.freeze([
      "Are you asking too much of yourself?",
      "What would a kinder inner voice say?",
      "Are you leaving room to rest today?",
      "Do you notice what went well?",
      "Are you carrying this alone?",
      "What is one small step for today?",
      "Can you pause before judging yourself?",
      "What would make this morning gentler?",
    ]),
    listicle: Object.freeze([
      "4 small habits for a calmer day",
      "4 kinder ways to start your morning",
      "4 small steps to make room to breathe",
      "4 reminders for a difficult day",
      "4 ways to be less hard on yourself",
      "4 gentle habits you can try today",
      "4 ways to reset your attention",
      "4 calm starts for a busy morning",
    ]),
    "myth-vs-fact": Object.freeze([
      "Does willpower fix every hard day?",
      "Do you have to stay positive all the time?",
      "Is rest really falling behind?",
      "Does perfect mean worthwhile?",
      "Is not enough always a fact?",
      "Does comparing help you move forward?",
      "Does self-criticism create change?",
      "Does being strong mean never pausing?",
    ]),
  }),
});

const BODY_BANKS = Object.freeze({
  ja: Object.freeze([
    "できたことをひとつ数える",
    "比べる時間を少しだけ減らす",
    "疲れた日は基準を下げていい",
    "深呼吸して肩の力を抜く",
    "予定の前に気分を確かめる",
    "完璧より続けやすさを選ぶ",
    "休む時間を先に決めておく",
    "今できる一歩を小さく選ぶ",
    "気持ちを短くノートに書く",
    "迷ったらひとつだけ進める",
    "朝はやさしい一言から始める",
    "夜はできたことを振り返る",
    "心配ごとを紙に書き分ける",
    "できない日も予定の一部にする",
    "自分のペースを先に決めておく",
    "必要なら信頼できる人に話す",
  ]),
  en: Object.freeze([
    "Count one thing you finished today.",
    "Take a slow breath and lower your shoulders.",
    "Make one next step small enough to start.",
    "Choose a pace you can keep.",
    "Write the worry down and sort it later.",
    "Leave a little time to rest.",
    "Notice what went well before moving on.",
    "Ask someone you trust for support.",
    "Pause before comparing your day to theirs.",
    "Let a difficult day be one part of your week.",
    "Check how you feel before checking the schedule.",
    "Use one gentle reminder to begin the morning.",
    "Pick one task instead of chasing every task.",
    "Give yourself permission to do a smaller version.",
    "Close the day by naming one good moment.",
    "Keep the next step simple and clear.",
  ]),
});

function seedNumber(seed, label) {
  return crypto.createHash("sha256").update(`${seed}\u0000${label}`).digest().readUInt32BE(0);
}

function pickHook(hooks, seed, avoidTexts) {
  const used = new Set(avoidTexts.map((text) => String(text).trim().toLocaleLowerCase()));
  const start = seedNumber(seed, "hook") % hooks.length;
  for (let offset = 0; offset < hooks.length; offset += 1) {
    const candidate = hooks[(start + offset) % hooks.length];
    if (!used.has(candidate.trim().toLocaleLowerCase())) return candidate;
  }
  return hooks[start];
}

function pickBodyLines(lines, seed, familyId, locale) {
  const order = lines.map((_, index) => index);
  let state = seedNumber(seed, `${familyId}:${locale}:body`);
  for (let index = order.length - 1; index > 0; index -= 1) {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    const swap = state % (index + 1);
    [order[index], order[swap]] = [order[swap], order[index]];
  }
  const labels = locale === "ja"
    ? ["ひとつめ", "ふたつめ", "みっつめ", "よっつめ"]
    : ["1", "2", "3", "4"];
  return order.slice(0, 4).map((lineIndex, index) => (
    familyId === "listicle" ? `${labels[index]}: ${lines[lineIndex]}` : lines[lineIndex]
  ));
}

async function generateSlideCopy({ familyId, locale = "ja", variantSeed = "default", avoidTexts = [] } = {}) {
  const normalizedLocale = BANKS[locale] ? locale : "ja";
  const hooks = BANKS[normalizedLocale][familyId];
  if (!hooks) throw new Error(`family ${familyId} is not configured for locale ${normalizedLocale}`);
  const seed = `${normalizedLocale}:${familyId}:${String(variantSeed)}`;
  return {
    hook: pickHook(hooks, seed, avoidTexts),
    body: pickBodyLines(BODY_BANKS[normalizedLocale], seed, familyId, normalizedLocale),
    costUsd: 0,
  };
}

function familyForStyleHint(styleHint, locale = "ja") {
  const families = Object.keys(BANKS[locale] || BANKS.ja);
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
