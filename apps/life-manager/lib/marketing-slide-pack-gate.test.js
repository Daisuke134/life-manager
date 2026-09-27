"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { runAutomatedGate, SLIDE_COUNT, rubricScore } = require("./marketing-slide-pack-gate.js");

function slide(position, role, text) {
  return { position, role, text, media_ref: `object://sha256/${"a".repeat(64)}` };
}

function goodPack() {
  return {
    slide_count: SLIDE_COUNT,
    slides: [
      slide(1, "hook", "メンタルが勝手に安定する口癖５選"),
      slide(2, "body", "ひとつめ: 朝の一言を変える"),
      slide(3, "body", "ふたつめ: 夜の振り返りを短くする"),
      slide(4, "body", "みっつめ: 比較をやめる合図を持つ"),
      slide(5, "body", "よっつめ: 疲れた日は基準を下げる"),
      slide(6, "body", "続けるコツはアプリの通知に任せること"),
    ],
  };
}

const GOOD_CAPTION = "メンタルが勝手に安定する口癖５選\n\nアプリはこちら → https://apps.apple.com/app/id6755129214";

test("runAutomatedGate approves a well-formed pack + caption", () => {
  const result = runAutomatedGate({ pack: goodPack(), caption: GOOD_CAPTION, platform: "instagram" });
  assert.equal(result.passed, true);
  assert.ok(result.score >= 60);
  assert.deepEqual(result.reasons, []);
});

test("runAutomatedGate rejects the wrong slide count", () => {
  const pack = goodPack();
  pack.slide_count = 5;
  pack.slides = pack.slides.slice(0, 5);
  const result = runAutomatedGate({ pack, caption: GOOD_CAPTION });
  assert.equal(result.passed, false);
  assert.ok(result.reasons.some((r) => r.includes("exactly 6 slides")));
});

test("runAutomatedGate rejects a blank slide", () => {
  const pack = goodPack();
  pack.slides[2].text = "   ";
  const result = runAutomatedGate({ pack, caption: GOOD_CAPTION });
  assert.equal(result.passed, false);
  assert.ok(result.reasons.some((r) => r.includes("slide 3 text is blank")));
});

test("runAutomatedGate rejects a caption missing the App Store CTA", () => {
  const result = runAutomatedGate({ pack: goodPack(), caption: "メンタルが勝手に安定する口癖５選" });
  assert.equal(result.passed, false);
  assert.ok(result.reasons.some((r) => r.includes("App Store CTA")));
});

test("runAutomatedGate rejects a caption over the platform limit", () => {
  const longCaption = `${"a".repeat(2300)}\nアプリはこちら → https://apps.apple.com/app/id6755129214`;
  const result = runAutomatedGate({ pack: goodPack(), caption: longCaption, platform: "instagram" });
  assert.equal(result.passed, false);
  assert.ok(result.reasons.some((r) => r.includes("exceeds")));
});

test("runAutomatedGate rejects a banned claim in a slide", () => {
  const pack = goodPack();
  pack.slides[1].text = "このアプリでうつ病が治る";
  const result = runAutomatedGate({ pack, caption: GOOD_CAPTION });
  assert.equal(result.passed, false);
  assert.ok(result.reasons.some((r) => r.includes("banned phrase")));
});

test("runAutomatedGate rejects a banned claim in the caption", () => {
  const caption = `${GOOD_CAPTION}\n必ず痩せる`;
  const result = runAutomatedGate({ pack: goodPack(), caption });
  assert.equal(result.passed, false);
  assert.ok(result.reasons.some((r) => r.includes("banned phrase")));
});

test("runAutomatedGate rejects heavily duplicated slide text (rubric score falls below threshold)", () => {
  const pack = goodPack();
  pack.slides[2].text = pack.slides[1].text;
  pack.slides[3].text = pack.slides[1].text;
  pack.slides[4].text = pack.slides[1].text;
  const result = runAutomatedGate({ pack, caption: GOOD_CAPTION });
  assert.equal(result.passed, false);
  assert.ok(result.reasons.some((r) => r.includes("rubric score")));
});

test("runAutomatedGate rejects a slide image smaller than 1080x1350", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gate-jpeg-"));
  const file = path.join(dir, "small.jpg");
  // 4x4 minimal baseline JPEG (SOF0 width=4 height=4), enough for the
  // dimension parser used by assertMarketingCarouselJpeg.
  const bytes = Buffer.from([
    0xff, 0xd8, 0xff, 0xc0, 0x00, 0x0b, 0x08, 0x00, 0x04, 0x00, 0x04, 0x01, 0x01, 0x11, 0x00, 0xff, 0xd9,
  ]);
  fs.writeFileSync(file, bytes);
  const result = runAutomatedGate({ pack: goodPack(), caption: GOOD_CAPTION, mediaFiles: [file] });
  assert.equal(result.passed, false);
  assert.ok(result.reasons.some((r) => r.includes("smaller than 1080x1350")));
});

test("rubricScore rewards a short, distinctive, numbered/question hook", () => {
  const strong = rubricScore(goodPack());
  const weakPack = goodPack();
  weakPack.slides = weakPack.slides.map((s) => ({ ...s, text: "同じ文言です" }));
  const weak = rubricScore(weakPack);
  assert.ok(strong > weak);
});
