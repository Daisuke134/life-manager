---
name: dissertation-discussion-humanizer
description: Rewrite a pasted dissertation discussion chapter into clear, natural academic prose while preserving supplied results, limitations, and uncertainty.
---

# Dissertation Discussion Humanizer

## Purpose

Help a researcher turn a pasted dissertation discussion draft into precise, readable academic prose. Work only from the user's supplied material and model knowledge. Never add citations, data, results, participant counts, institutional claims, or literature findings.

## Required input

Ask for the discussion draft or notes, the research question, the results that must remain exact, target length/style, and any claims or wording that must not change.

## Workflow

1. Extract the supplied findings, interpretations, limitations, and required claims.
2. Identify overstatement, repeated phrasing, vague transitions, and places where a conclusion exceeds the supplied evidence.
3. Rewrite the discussion with a clear sequence: interpretation, relation to the stated question, implications, limitations, and bounded conclusion.
4. Keep all supplied numbers and caveats unchanged. Mark missing support as `[TBD]` or a direct question.
5. Return the revised text followed by a short `Evidence check` listing preserved facts and items the author must verify.

## Guardrails

- Do not claim to know the user's field literature or current evidence beyond what they paste.
- Do not create citations, references, study results, participant counts, effect sizes, or institutional requirements.
- Use calibrated language when the supplied evidence is preliminary, correlational, limited, or uncertain.
- Tell the user to check the final text against their source materials and supervisor or journal requirements.

## Test case

Input: A 900-word discussion draft about 18 interviews, with a request to preserve the count, avoid new citations, and flag unsupported causal language.

Expected: A clearer discussion draft that retains `18 interviews`, contains no invented references or figures, changes causal claims to bounded language where needed, and includes an Evidence check.
