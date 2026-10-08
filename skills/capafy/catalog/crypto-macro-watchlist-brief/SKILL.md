---
name: crypto-macro-watchlist-brief
description: "Use when a user pastes a weekly crypto or macro watchlist with their own prices, notes, and dated events and wants a structured brief. Computes changes only from pasted numbers, lists dated catalysts, risks to re-check, and a review order. Analysis only: no buy or sell signals, no trade execution, no price lookups, no predictions."
---

# Crypto & Macro Weekly Watchlist Brief

Turn a pasted weekly watchlist into a source-bounded brief.

## Input

- `watchlist` (required): assets with the user's prices, notes, and dated events.
- `week_label` (optional): the week or date range.
- `prior_week` (optional): last week's prices or notes, for comparison.
- `focus` (optional): what the user cares about, such as risk or upcoming events.

## Workflow

1. Build an evidence ledger of every number, date, and claim in the paste. Anything the brief needs that is not in the paste is marked `[ADD: ...]`. Never supply a price, date, or fact from memory.
2. For each asset with two prices, compute the percent change and show the arithmetic inputs. With one price, state that no change can be computed.
3. List the dated catalysts the user supplied in date order, including macro events, noting each source as supplied.
4. Write risks and open questions to re-check. Each must tie to a supplied note or a named gap.
5. Give a review order with a one-line reason per asset, based only on supplied changes, events, and risks.

## Output

```markdown
# Weekly watchlist brief: [week]

## Evidence boundary
- Supplied: ...
- Missing: [ADD: ...]

## Assets
| Asset | Last week | This week | Change | Your note |

## Catalyst calendar (as supplied)
| Date | Event | Asset | Source |

## Risks to re-check
## Review order
## Missing inputs

Analysis from your pasted inputs only. Not financial advice.
```

## Rules

- No buy, sell, or hold signals, entries, targets, or stop levels. No trade execution.
- No price, news, or on-chain lookup, and no price predictions.
- If the user asks for a signal or trade, decline in one line and offer the brief instead.
- Empty watchlist: ask for it.
