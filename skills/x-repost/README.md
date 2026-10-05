# Life Manager X growth loops

Life Manager ships three independent macOS launchd owners. Each wake finds current public
information, creates at most one grounded post, reads the official X permalink back, records the
effect in a durable ledger, and exits.

| Owner | Output | Source | Default cadence | State |
|---|---|---|---|---|
| `x-repost` | English quote post | Live X search | minute 0 and 30 | `~/loops/x-repost-en` |
| `x-repost-ja` | Japanese quote post for Dice | Live Japanese or English X search | minute 5 and 35 | `~/loops/x-repost-ja` |
| `x-tweeter` | English original | Public Chinese platforms | minute 15 hourly | `~/loops/x-tweeter` |

The owners never share their state or Affiliate queues. A private firsthand seed is optional:
exact source-specific evidence is sufficient. Empty seed state therefore cannot stop an otherwise
grounded post. Safety gates still reject unsupported claims, wrong-language output, duplicate
sources, excessive X length, wrong-account browser sessions, and ambiguous duplicate effects.

## Pipeline

1. Collect a bounded candidate receipt.
2. Select one source and bind an exact evidence quote.
3. Draft, humanize, and choose one post.
4. Run a separate source-grounding and usefulness critic.
5. Publish once through the configured transport.
6. Read back the exact `https://x.com/<handle>/status/<id>` permalink.
7. Append `posted.jsonl` and retain the pass evidence directory.

## Shared agent capacity

`x-repost` uses the shared agent pool with `admission_class=borrow` and `priority=revenue`. This
queue priority puts the requested X feed ahead of routine support work when a borrow slot opens;
the borrow admission class still preserves reserved revenue capacity and never preempts an active
owner. When capacity is busy, scheduled wakes coalesce into one pending queue position. Once a
claim runs, it searches live X at execution time and does not replay one post for every missed
half-hour interval.

## Affiliate disable

The English wrapper sets `X_REPOST_DISABLE_AFFILIATE=1`. While set, the pass does not claim or
requeue affiliate distribution jobs or publish a fresh affiliate proposal. It still records an
exact prior `POSTED` receipt for duplicate protection. Existing `UNVERIFIED` jobs receive a
readback-only check when the browser is available. The pass preserves their `UNVERIFIED` result and
Affiliate ledgers, regardless of the readback result, then continues ordinary X discovery.
When that readback already holds the registered X browser lease, the same CDP session is reused
for discovery and released once at pass end.

Each Postiz submission belongs to its X-loop occurrence and cannot prove an effect for a later
occurrence. A readback-only pass or a receipt outside the exact occurrence window leaves that host
effect fenced.
Any host effect without a unique, in-window `PUBLISHED` receipt remains fenced. An Affiliate result
also remains `UNVERIFIED` until its owned article URL is confirmed.

## Host effect reconciliation

The `x-repost` registry adapter closes one exact `effect_unknown` occurrence only after pairing all
of its runtime execute/report attempts, verifying that the fence row's `queued_at` does not follow
the first attempt, and reading one unique evidence directory for each attempt. FIFO admission wait
may separate queue time from execution start; the exact occurrence/run pair anchors identity, while
the Postiz window begins at actual execution. It waits until 15 minutes after the latest report,
then reads the exact Postiz integration over the combined window. A post counts for the occurrence
only when its published time falls inside one of those attempt windows; unrelated posts returned
between attempts do not count. No-effect proof accepts only releases audited for this exact readback-only branch:
`c16f437b93028ea5d94014a1fa32c091795cbee0`,
`86fa863d4fe04ec0b5c44e8a2e513e55edaf2928`,
`88872a85cc652877f242ead444108a813084cfc9`, and
`4eb6bbbaeb9a8368895e6391e34e8c895908b0ec`, with exact readback-only evidence for every attempt.
Other releases can prove a positive effect only through the exact Postiz submission ID and X
permalink in the matching pass evidence. Unsupported releases or transports without that receipt,
missing or ambiguous evidence, unfinished Postiz listings, and out-of-window posts stay fenced. Old
runtime rows may lack loaded argv/env hashes; the adapter does not infer those hashes.

A positive proof requires one in-window `PUBLISHED` Postiz row whose ID and X permalink match the
same pass evidence. A no-effect proof requires the exact `UNVERIFIED` readback-only branch for every
attempt, no post result, all success/generic/crash recoveries clear, empty reconcile errors, and a
complete listing with no owner-integration rows in any attempt window. The Postiz query rounds its
combined bounds outward to whole seconds and validates each publication time against the exact
attempt windows. Its synthetic receipt records those windows, the rounded official query, and the
Postiz response hash. Historical posts outside those windows never count for the occurrence.

The English original owner runs `skills/x-tweeter/scripts/chinese_source_collect.py`. Its default
public sources are Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba, and Zhihu. The collector
only gathers source text and URLs; the model makes the editorial decision. MediaCrawler is not
used.

## Configure your accounts

The single scheduler declaration is `config/loop-registry.json`. Account-specific runtime defaults
live in the repository-owned `x-repost-en-cli.sh`, `x-repost-ja-cli.sh`, and `x-tweeter-cli.sh`
wrappers; there is no second `loop.toml`/plist generator path.

Runtime credentials stay outside Git. Provide `POSTIZ_API_KEY` when using Postiz and a healthy
registered CloakBrowser X session for source collection and exact readback. `TWITTER_AUTH_TOKEN` is
an optional recovery cookie used only when that browser session has lost its X auth cookie.
Browser identities are resolved through the local browser registry rather than hardcoded CDP
ports. The Chinese collector also requires the `crwl` CLI on `PATH`.

## Test

```bash
python3 -m unittest discover -s skills/x-repost/tests -p 'test_*.py' -v
python3 -m unittest discover -s skills/x-tweeter/tests -p 'test_*.py' -v
python3 -m unittest runtime.loop.tests.test_macos_loop_registry -v
```

## Install on a Mac

Cut a read-only release from a pushed main commit, then apply the registry through its single owner:

```bash
bash bin/cut-loop-release.sh origin/main
~/loops/current/bin/lm-loop apply
```

launchd always executes `~/loops/current`, an atomic symlink to an immutable release. State and
ledgers remain outside releases, so deployment and rollback cannot erase duplicate protection.
Healthchecks run every five minutes.

## Verification

Do not treat process exit, provider acceptance, or a draft as publication. For each owner require:

- loaded launchd `ProgramArguments` pointing through `~/loops/current`;
- `last exit code = 0`;
- a new `posted.jsonl` row;
- an exact X permalink in the post receipt;
- a second wake that creates no duplicate effect for the consumed source.

Every pass writes `~/loops/<owner>/evidence/<pass-id>/` with candidate, prompt, model, critic,
publish, and readback receipts.
