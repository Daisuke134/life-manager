---
name: resume-job-match-brief
description: Compare a buyer-pasted job posting with their pasted resume and return a match table, honest gap list and rewritten bullets that use only supplied experience.
---

# Resume-to-Job Match Brief

Compare one job posting with the buyer's resume, both pasted into the chat, and
return a practical match brief.

## Input

Ask for the full job posting and the buyer's current resume text. If either is
missing, ask for it. Do not guess what the posting or resume contains.

## Method

1. Split the posting into discrete requirements (skills, tools, experience level,
   responsibilities).
2. For each requirement, find supporting text in the resume. Label it Matched,
   Partly matched, or Not shown.
3. For every gap, say how the buyer could address it honestly: a real example to
   add, or a plain acknowledgement. Mark each missing detail `[ADD: ...]`.
4. Rewrite weak bullets so they reflect the posting's wording while keeping every
   fact from the original resume.

## Output

Return, in order:

1. A match table: requirement, status, supporting resume text.
2. A gap list with honest options for each.
3. Rewritten bullets, each next to its original.
4. Posting keywords the resume already supports.

Never invent employers, titles, dates, metrics, tools or achievements. Never claim
the result will pass an applicant tracking system or lead to an interview.
