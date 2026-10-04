# Capafy catalog hold

Listings here are kept but are NOT publishable: the factory only reads `skills/capafy/catalog/`.

2026-10-04: five unpublished Hook Lab derivatives moved here. The three live Hook Lab
derivatives (Ad, Reels, Shorts) had 0 orders in 30 days while Hook Lab had 11, which is
the C3 stop rule in `capafy_daily_decision.py` (2+ children below the parent). Capafy
developer doc 4.2 also removes near-identical mass uploads. The model-judged duplicate
gate rated some of these "distinct" against YouTube Script Writer, so it did not stop them.

To publish one again: `git mv` it back into `skills/capafy/catalog/` once the live
Hook Lab derivatives show paid orders.
