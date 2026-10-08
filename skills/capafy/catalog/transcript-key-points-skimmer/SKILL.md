---
name: transcript-key-points-skimmer
description: Condense a buyer-pasted transcript into a summary, ordered key points with exact quotes, decisions, action items and open questions.
---

# Transcript Key Points

Turn a transcript the buyer pastes into a brief that can be skimmed in a minute.

## Input

Ask for the transcript text and the buyer's goal (study notes, meeting follow-up,
research quote hunt, or quick skim). If only a link or a title is given, say that
only pasted text can be used and ask for the text. If the transcript is long,
work through all of it and say if the paste appears cut off.

## Method

1. Read the full transcript before summarising.
2. Group statements into topics in the order they appear.
3. Keep exact wording for every quote; never paraphrase inside quotation marks.
4. Record decisions, action items and owners only when the transcript states them.
5. Note questions the speakers raise but do not answer.

## Output

Return, in order:

1. A summary of three to five sentences.
2. Key points in order, each with a short supporting quote.
3. Decisions and action items with owners, or "none stated".
4. Open questions; mark anything unclear as `[UNVERIFIED]`.
5. If the goal calls for it, a short list of quotable lines.

Never add facts, names, numbers or speakers that are not in the pasted text.
