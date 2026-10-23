# Deterministic reference forecast procedure

For target `fomc-2026-10-27-28.upper-below-4pct.v1`, use only the fixed three official historical statements in the frozen context. Their upper target bounds are 3.75%, 3.75%, and 4.00%, in chronological order. Count a cut when a later scheduled statement has a lower upper bound than the preceding statement. There are 0 cuts across 2 transitions and 3 values. Apply Laplace smoothing: `(cuts + 1) / (transitions + 2) = (0 + 1) / (2 + 2) = 0.25`.

Set the forecast probability `P(upper bound < 4.00 percent)` to 0.25. This is a deterministic historical-frequency reference, not a model call or a human probability judgment. It intentionally equals the separately recorded historical-frequency baseline. It has no independent performance claim.
