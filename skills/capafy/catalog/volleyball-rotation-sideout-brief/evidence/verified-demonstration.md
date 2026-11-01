# Verified Demonstration — Volleyball Rotation & Side-Out Brief

## Concrete input

```text
Match: Harbor VC vs Summit VC, buyer's match-review notes.

Rotation notes: Harbor's setter starts front-right in Rotation 1. Harbor's outside hitter is left-front. Summit's right-side blocker is matched against Harbor's outside in the listed rotation.

Serve-receive notes: Summit Server 7 targeted the Harbor libero seam twice. The buyer recorded one overpass and one controlled pass. No other serve sample or pass-rating total is supplied.

Block-defense notes: Harbor's middle closed late on Summit's outside in two noted rallies. The buyer recorded no attack height, set location, transition count, substitution, score state, or player availability information.

Decision question: What conditional side-out issue should a coach discuss before the next set?
```

## Actual output

```markdown
# Volleyball Rotation & Side-Out Brief: Harbor VC vs Summit VC — match-review notes

## Evidence boundary
- Supplied: Harbor's setter starts front-right in Rotation 1, with its outside at left-front and Summit's right-side blocker matched there.
- Supplied: Server 7 targeted the libero seam twice; the buyer recorded one overpass and one controlled pass.
- Supplied: Harbor's middle closed late on Summit's outside in two noted rallies.
- [UNVERIFIED]: the wider serve sample, pass ratings, attack height, set location, transition count, substitutions, score state, player availability, and all unlisted rotations.

## Rotation card
| Rotation or matchup | Supplied observation | Side-out read | Confidence | Limitation |
| --- | --- | --- | --- | --- |
| Rotation 1 receive | Server 7 targeted the libero seam twice, producing one overpass and one controlled pass. | First-contact stability at the named seam is the leading supplied side-out question before changing the attack. | low | Two serves do not establish a repeatable serving pattern. |
| Left-front outside vs right-side block | Harbor's outside is left-front against Summit's listed right-side blocker. | The matchup supports discussing the outside's first available option after a stable pass, not a fixed attack call. | low | No set location, attack result, or blocker-position detail is supplied. |
| Middle closing on Summit outside | Harbor's middle closed late in two noted rallies. | Closing timing is a conditional transition question if the same outside attack sequence appears again. | low | Two rallies lack tempo, score, and transition context. |

## Conditional decision points
- If Server 7 repeats the libero-seam target: state the receive responsibility before altering the attack option. Evidence: two supplied seam targets, one overpass, and one controlled pass. Reconsider if: a larger pass sample shows the target is not recurring.
- If Harbor gets a controlled pass in Rotation 1: discuss the left-front outside's first available option against the listed right-side block rather than treating the matchup as settled. Evidence: the supplied rotation roles. Reconsider if: added set-location or attack-result notes change the matchup.
- If the opposing outside repeats the noted sequence: make middle closing timing a transition checkpoint. Evidence: two supplied late closes. Reconsider if: added rally notes show a different tempo or attacker route.

## Coverage angle
Rotation 1 is a first-contact question before it is an attack-selection story: the buyer's two seam-target notes justify checking reception responsibility, while the small sample prevents a stronger conclusion.

## Verify before using
- Add pass ratings and targets for more than the two listed serves.
- Add set location, attack outcome, and blocker position for the left-front matchup.
- Add rally tempo and transition detail for the two late middle closes.

## 45-second rundown
The supplied notes identify one cautious side-out discussion for Harbor's Rotation 1. Two serves at the libero seam produced one overpass and one controlled pass, so the first question is reception responsibility if that target repeats, not a wholesale attack change. The left-front outside matchup and two late middle closes are useful prompts for the next review, but there is no wider pass sample, set-location detail, or transition count. The disciplined read is to test these conditions in the next supplied sequence rather than treat them as settled patterns.
```

## Verification notes

- **Input traceability:** Every named team, role, rotation, server, target, count, and observation in the output appears in the concrete input.
- **Unknown handling:** The output explicitly preserves the absent pass sample, attack detail, score, availability, and unlisted rotations as `[UNVERIFIED]`.
- **Capability boundary:** This is self-contained text analysis of buyer-pasted material. It makes no claim to browse, retrieve current volleyball information, place wagers, or determine a match result.
- **Output contract:** The output contains the required evidence boundary, rotation card, conditional decision points, coverage angle, verification queue, and 45-second rundown.
