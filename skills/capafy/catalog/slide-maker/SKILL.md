---
name: slide-maker
description: Turn any content — a report, notes, an outline, or a topic — into a presentation-ready deck as clean, self-contained HTML slides, without opening a design tool. It structures the content into slides, picks a cohesive visual style, and writes concise on-slide copy plus speaker notes. Output is HTML you can open in a browser or paste into a slide tool. It never invents facts, numbers, or sources. Use when you need a styled deck fast from existing content.
---

# Slide Maker

Turn a report, notes, an outline, or a topic into a presentation-ready deck as
one self-contained HTML document. Use only facts supplied by the buyer. Never
invent a number, quote, or source.

## Input

The buyer supplies content (a report, notes, an outline, or a topic) and,
optionally, an audience, a target slide count, and a visual style preference.
If slide count or style is absent, choose a reasonable default and state the
assumption.

## Method

Show these steps:

1. Extract the narrative: title, agenda, one idea per slide, and a logical arc
   (problem → insight → solution → next steps), ending with a close.
2. Pick ONE cohesive visual style (Minimal, Editorial, Bold Tech, Corporate, or
   Dark) and apply it consistently: palette, type scale, spacing.
3. Write each slide as a tight headline plus 3-5 skimmable bullets (or a key
   stat/quote), plus speaker notes. No walls of text.
4. Assemble one self-contained HTML document: one `<section>` per slide,
   inline CSS, 16:9 aspect ratio, opens in any browser.

## Output

Return, in order:

1. The complete self-contained HTML deck (inline CSS, no external assets).
2. Speaker notes per slide.
3. Any missing facts needed to finish the deck, marked `[ADD: ...]`.

Deliver the full HTML in one response. Match the requested slide count and
style. Never invent a number, quote, or source that the buyer did not supply.
