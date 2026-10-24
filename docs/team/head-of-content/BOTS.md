# Ryan's 11 roles → existing teammates & routines (no new agents)
Approval gate: 成田さん pre-approved posting to @diceai0; 参謀 (Grok Bot) reviews every draft against VOICE.md before posting. Nothing else publishes.

| Ryan role | Dept | Owner (existing) | Existing routine it extends |
|---|---|---|---|
|Chief of Staff|—|参謀 (Grok Bot)|hourly money loop + Manager group chat|
|X Researcher|Research|参謀|X timeline reader (overnight run)|
|Competitor Watch|Research|claude-1 (Reason)|copy-the-winners (TOP20.md as list)|
|Bookmarks Brain|Research|claude-2|copy-the-winners (evening)|
|QT Scout|Research|参謀|engage pass|
|Sparring Bot|Create|claude-3|on demand in Reason|
|X Writer|Create|Codex|X build-in-public|
|Banner & Visuals|Create|Dots|on demand|
|Fact Checker|Create|claude-4|on demand, before any number goes out|
|Article Tracker|Track|Muse + Fucker (paid articles)|Sunday list|
|Analytics Analyst|Track|claude-5 / Side Hustle CEO data|X money scout morning|
Anicca Marketer keeps Anicca app channels; reuses PILLARS #2 posts.

## Run first (3–4 active): Chief of Staff debrief, QT Scout, X Writer (build-in-public), Analytics.

## Prompt additions (append to existing routines)
### A. Chief of Staff → add to hourly money loop (Daily Debrief run 21:30 JST)
"Read docs/team/head-of-content/*. Collect today's outputs from QT Scout, X Writer, Analytics and the Manager chat. Write one debrief: posts shipped (links), top post and why, 3 drafts awaiting review, tomorrow's 3 post slots (08:00 JA, 12:15 EN, 19:00 EN). Reject any draft off VOICE.md and add the correction to VOICE.md. Max 15 lines."
### B. QT Scout → add to engage pass (09:30, 14:30, 20:30 JST)
"From TOP20.md accounts and the timeline, pick 5 posts <6h old with traction. For each: link, why it's working, one angle from our real story (PILLARS.md), and a draft quote/reply in VOICE.md (1–3 sentences, a concrete fact from our setup, no generic praise). Never invent numbers. 参謀 posts at most 2."
### C. Analytics (Daily Debrief input) → add to X money scout (07:30 JST)
"Read @diceai0's last 24h posts with public_metrics. Report impressions, top 3 posts and why, replies to answer, follower change. Name one thing to repeat and one to stop. Append to docs/team/head-of-content/ANALYTICS.md."
