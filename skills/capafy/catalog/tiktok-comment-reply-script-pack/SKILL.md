---
name: tiktok-comment-reply-script-pack
description: >
  Turn buyer-pasted TikTok comments, product facts, and creator voice notes into
  a short reply-to-comment video script pack. Use when a creator needs precise,
  filmable responses that answer audience questions without inventing facts.
license: MIT
version: "1.0.0"
tags: [tiktok, creator-community, comment-replies, video-scripts, short-form]
compatibility: "Claude Code, ChatGPT, Gemini CLI, Cursor, Windsurf, OpenClaw, any AI agent"
metadata:
  author: anicca
  version: "1.0"
  stage: S2-Content
---

# TikTok Comment Reply Script Pack

Turn the comments and facts a creator already has into a practical reply-video
package. This is not a general idea-to-video writer: its job is to help a
creator convert an actual audience question, objection, or request into a
clear, respectful video response.

## Input

Ask for:

- the exact comment or a faithful pasted summary;
- the creator's approved facts, product details, or experience to use;
- audience and tone;
- desired response length (default: 20–30 seconds); and
- any claim, topic, or CTA to avoid.

Treat every fact not supplied by the buyer as unknown. Do not fabricate a
customer result, price, policy, review, trend, statistic, or platform feature.

## Workflow

1. Classify the comment as a question, objection, misconception, request, or
   praise worth acknowledging.
2. Identify the narrowest honest answer that uses only supplied facts. Flag any
   unanswered premise for the creator rather than guessing.
3. Produce three reply angles: direct answer, teachable clarification, and
   conversation-starter. Recommend one based on the stated goal.
4. Write a timed spoken script with the comment cue, on-screen text, visual
   action, and one low-pressure CTA.
5. Add a caption, 3–5 relevant non-invented hashtags, and a reply checklist.

## Output Format

```markdown
# Reply-to-Comment Video Pack

## Comment and fact boundary
- Comment: [buyer-pasted text]
- Approved facts: [facts]
- Unknown / ask before claiming: [gaps]

## Three response angles
1. **Direct answer** — [angle]
2. **Teachable clarification** — [angle]
3. **Conversation-starter** — [angle]

**Recommended:** [angle and reason]

## Timed script
| Time | Spoken line | On-screen text | Visual action |
|---|---|---|---|

## Caption
[caption]

## Reply checklist
- [ ] The comment is represented fairly.
- [ ] Every claim comes from supplied facts.
- [ ] Unknown details are omitted or framed as a question.
```

## Error Handling

- If no exact comment is supplied, ask for one before drafting a reply.
- If the comment asks for a claim the buyer cannot substantiate, offer a
  transparent acknowledgement rather than an answer that implies certainty.
- If the request targets a person or group, keep the response focused on the
  idea and avoid harassment, mockery, or personal assertions.
- If several comments are supplied, ask the buyer to rank them or create a
  separate compact package for each one.

## Quality Gate

1. The output names the supplied comment and separates facts from gaps.
2. The recommended script directly answers the comment within the requested
   length.
3. Every assertion is buyer-supplied or clearly framed as a prompt to verify.
4. The response contains no claim of account access, audience analytics, or
   current platform knowledge.
