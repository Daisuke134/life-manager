# Verified demonstration — Football Match Analyst

## Concrete input

```text
Matchweek: Saturday slate
Competition: North Coast League

Fixture 1: Northbridge FC vs River Athletic
Kickoff: 2026-10-10 15:00 local time
Northbridge team news: the starting centre-back is suspended; the first-choice winger is available.
River team news: the striker is doubtful after a minor knock; River played an away match on Wednesday.
Recent evidence: Northbridge won its last home match; River drew its last two away matches.
Tactical note: Northbridge normally presses high; River prefers a controlled build-up.
Odds notes: none supplied.

Fixture 2: Harbor Town vs Eastvale United
Kickoff: 2026-10-10 17:30 local time
Harbor Town team news: no availability update supplied.
Eastvale team news: the goalkeeper is suspended.
Recent evidence: Harbor Town's last result is not supplied; Eastvale won its last match.
Tactical note: Harbor Town usually attacks through wide areas; Eastvale relies on quick transitions.
Odds notes: Eastvale is listed at 2.40 in the buyer's notes; source and market timing are not supplied.
```

## Actual output

### Fixture table

| Fixture | Home/away setup | Availability | Rest/travel | Recent evidence | Tactical matchup | Confidence | Key swing factor |
|---|---|---|---|---|---|---|---|
| Northbridge FC vs River Athletic | Northbridge has the home setting; River is away. | Northbridge loses its starting centre-back; River's striker is doubtful. | River played away on Wednesday; Northbridge's prior travel is `[UNVERIFIED]`. | Northbridge won its last home match; River drew its last two away matches. | Northbridge's high press meets River's controlled build-up. | Moderate | Whether River's striker is available and whether Northbridge can cover the suspended centre-back. |
| Harbor Town vs Eastvale United | Harbor Town is at home; Eastvale is away. | Eastvale's goalkeeper is suspended; Harbor Town availability is `[UNVERIFIED]`. | Both teams' recent travel and rest details are `[UNVERIFIED]`. | Harbor Town's last result is `[UNVERIFIED]`; Eastvale won its last match. | Harbor Town's wide attack meets Eastvale's transition approach. | Low | Eastvale's replacement goalkeeper and the missing Harbor Town form evidence. |

### Matchup briefs

**Northbridge FC vs River Athletic**

The supplied notes point to three decisive questions: Northbridge must cover the suspended starting centre-back, River may be without its striker, and River arrives after an away match on Wednesday. Northbridge's high press against River's controlled build-up is the supplied tactical contrast. The notes support a moderate-confidence comparison, not a certain result.

**Harbor Town vs Eastvale United**

Eastvale's suspended goalkeeper is the clearest supplied availability change. The comparison is low confidence because Harbor Town's availability and last result are missing, and the supplied Eastvale odds note has no source or market timing. The tactical contrast is Harbor Town's wide attack against Eastvale's quick transitions.

### Scenario splits

1. If River's doubtful striker is available, the supplied availability concern is reduced; the centre-back suspension remains open for Northbridge.
2. If River's striker is unavailable, River's attacking options are less certain in this supplied record; no replacement quality is provided.
3. If Eastvale's suspended goalkeeper is replaced by an unreported first-choice-quality keeper, the impact is unknown. If not, the match effect cannot be assessed from the supplied material.

### Missing-facts watch list

- Northbridge's replacement plan for the suspended centre-back: `[UNVERIFIED]`.
- River striker's final availability: `[UNVERIFIED]`.
- Northbridge travel/rest information: `[UNVERIFIED]`.
- Harbor Town availability and latest result: `[UNVERIFIED]`.
- Eastvale replacement goalkeeper: `[UNVERIFIED]`.
- Source and timing for the 2.40 odds note: `[UNVERIFIED]`.

### Matchweek ranking

No reliable ranking is produced. The two fixtures have different evidence gaps, and the supplied record does not support a fair comparison across them.

All current team news, form notes, tactical notes, and the odds note came from the buyer's pasted input. No live data or betting recommendation is used.

## Verification notes

1. Every team, date, availability note, result, tactical note, and odds value in the output is present in the concrete input.
2. The seven required axes are shown for each fixture; absent facts remain `[UNVERIFIED]`.
3. The output does not invent a score, live lineup, statistic, source, probability, wager, or certain prediction.
4. The scenario splits change only the supplied striker/goalkeeper uncertainties and do not assert an outcome.
5. No live service, Capafy API, PromptBase UI, browser, or model call was used to author this offline demonstration.
