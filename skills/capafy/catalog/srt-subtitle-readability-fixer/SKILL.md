---
name: srt-subtitle-readability-fixer
description: "Use when a user pastes SRT subtitle text and wants lines reflowed for readability and fast cues flagged. Splits lines at natural phrase breaks within the user's limits, keeps cue numbers, timestamps, and wording unchanged, and calculates characters per second per cue. Text only: no transcription, translation, audio or video processing, or file upload."
---

# SRT Subtitle Readability Fixer

Reflow pasted SRT text and flag cues that read too fast.

## Input

- `srt_text` (required): the pasted SRT content.
- `max_chars_per_line` (optional, default 42).
- `max_lines_per_cue` (optional, default 2).
- `max_cps` (optional, default 17 characters per second).

## Workflow

1. Parse cues: number, `start --> end` timestamps, and text. If the paste is not valid SRT, say which cue looks malformed and continue with the rest.
2. Reflow each cue's text at natural phrase breaks (after punctuation, before conjunctions or prepositions), balancing line lengths, within the line limits. Do not change, add, or remove words.
3. Compute duration from the pasted timestamps and characters per second as characters (excluding line breaks) divided by seconds. Show the numbers.
4. Flag each cue above the speed limit or that cannot fit the line limits. Suggest a shorter wording or a longer cue, and do not apply it unless asked.
5. Return the full SRT text, unchanged timestamps, then the report.

## Output

````markdown
```srt
[cleaned SRT]
```

## Report
- Cues: N, reflowed: N, flagged: N
| Cue | Chars | Seconds | CPS | Issue | Suggestion |
````

## Rules

- Never move or change timestamps or cue numbers.
- Never change words unless the user asks for a shortened version.
- Text only: no audio, transcription, translation, burning in, or file upload.
- No SRT in the paste: ask for it.
