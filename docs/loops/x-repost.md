# x-repost — what it is for, and what it does

Owner decisions folded in 2026-08-19. Everything stated as measured was measured; open items say
what is untrue today rather than what is planned.

## What the account is for

`@selawmqt` ("sela | AI Tools") is an AI-owned account. Its bio, its entire posting history and its
website are English, and it exists to earn: affiliate, creator revenue, and promoting the apps this
system builds. So the audience worth growing is the one that buys those, and everything below
follows from that rather than from what is convenient to scrape.

**Never runs on `@aniccaen` or `@diceai0`.** Those are the owner's personal accounts; posting to one
from a loop was revoked on 2026-07-18. Japanese reach needs its own AI-owned account, not those.

## Language

Answer in the language of the post being quoted. English is the majority because the account and
its buyers are English; a Japanese source is quoted in Japanese, because the people reading that
conversation are Japanese. When it cannot be told, English.

This was measured wrong first: six of six published quotes replied in Japanese to English sources,
which reaches almost nobody in the original post's audience.

## Topics

The rule is expand, never narrow. A zero-follower account's problem is reach, so every query is
another room it can be seen in. AI and crypto stay in full — they were the original surface and they
draw the most movement — and the surface widens outward from them toward what the account sells:
AI tools, building alone, automation, the creator economy. `config/queries.txt` is that surface; it
is data, so it can be re-aimed without touching code.

An earlier version of this cut crypto down to a single query on the theory that it drew the wrong
audience. That was the wrong instinct: narrowing to the buyers costs the reach that produces buyers
in the first place.

## What one pass does

1. CEO registry gate, then flush any report an earlier pass could not deliver
2. At most one post per hour, with a daily ceiling as a runaway brake
3. Lease the dedicated browser (`x:anicca`), restoring the X session from a stored cookie if lapsed
4. Scrape live search results; refresh engagement on posts still in play
5. Pick one post and draft three tones — the model decides, never a regex
6. Strip the AI register through the house `jp-humanizer-pro` skill, as a separate call
7. Choose one, check it against X's real length limit, publish, read the permalink back
8. Record, report to Telegram, mark the seed it spent

## The five rules, and how they failed

1. Do not put the other person down
2. Include something positive
3. Say something only you can say
4. Do not make it about yourself
5. Give the reader somewhere to go

Read back on 2026-08-19, five consecutive posts opened with "うち" and spent their one specific fact
on this machine's internals — CDP ports, exit codes, a count of unregistered launchd jobs. Rule 3
was satisfied in a way that broke rule 4, and nobody outside this Mac has any use for those numbers.
The brief now carries those five posts as the failure they are, requires the seed to be translated
into what it means for the reader, allows one number, and bans the private vocabulary.

## Primary information, and why it runs out

Rule 3 may only draw on `state/seeds.jsonl`: facts this system actually measured. A seed is withheld
for fourteen days after use, which is what ended twenty-nine posts recycling three anecdotes.

The arithmetic was wrong at first: the pass can spend up to twelve seeds a day and the daily job
added one, so the well emptied inside a day and the drafts fell back to empty commentary
("the design thinking is sound"). The daily job now harvests several at once from different angles
on the same material, and when no seed fits, the brief says to go deeper into the quoted post
rather than reach for a generality.

## Measuring, and the one knob

Counts are read from the post's action bar. An absent action means zero — X omits zero counts
entirely, which is why 27 of 29 posts once carried "likes unknown" when they had none. Samples are
appended with a timestamp rather than overwritten, thinning with age, because the ranker pays for
early velocity and a single end number mostly reflects how long ago a post went out.

Replies are disabled by owner decision, so the loop is judged on post metrics alone. That left the
evaluator with nothing it could change, so **tone** is the live knob: the mix moves toward whichever
tone earns more first-hour views, refusing to move on fewer than three measured posts per arm.

## Open

- Second samples exist for 1 of 30 posts; the rest arrive as the sampling schedule comes round
- Seven-day median against the previous seven days needs seven days
- The scheduled digest remains held by one resource_effect_unknown Telegram occurrence because
  exact message readback is unavailable; do not replay. Its missing adapter and evidence gate are
  tracked in the unified SSOT under T5-G-4.
- Original posts do not exist yet. Quoting alone gives nobody a reason to follow, which is what a
  zero-follower account needs most; the machinery (kind, strategy mix, evaluator) is already there
- A Japanese-language sibling account has not been created
