# What Numerai Unity teaches us about scoring predictions against reality

Sources checked October 18, 2026. This is an explanation and participation proposal, not a report of model training, account creation, prediction submission, event registration, NMR purchase, or staking.

Numerai operates an ongoing stock-prediction data-science tournament and a hedge fund using predictions. Participants normally submit numerical predictions per stock, not their entire model code. Model Uploads is an optional exception that supplies a model for automatic execution.[1][3]

## Inputs and outputs

One row represents a stock at a time. Historical records contain features available then and targets representing subsequent performance. Train on history, evaluate on temporally separated periods against a simple model, then submit predictions on live data whose outcomes are not yet known.

A fictional submission is “stock A: 0.8, B: 0.5, C: 0.2.” These are relative prediction scores, not necessarily 80%, 50%, and 20% probabilities of price increases. Later outcomes allow ongoing scoring. The Meta Model combines participant predictions.[1]

## What Unity changes

The October 16, 2026 announcement introduced Unity with 1,040 features and real stock identifiers. This does not disclose every feature’s original name or unprocessed meaning: anonymized, ranked, normalized, or binned features remain. Identifiable stocks make external-feature research and joins easier.[2]

The official example retrieves SEC EDGAR filings, asks a small open-weight LLM to evaluate performance comparisons, outlook, and tone, and ranks/bins the outputs over time into features. Only filings public before each prediction time should be used. This is an additional-feature research example, not proof of guaranteed profits; incremental prediction value still needs evaluation.[2]

The announced schedule was a Unity session on October 19 at 9 a.m. Pacific, Numerai Unity submissions opening November 6, and Numerai/Signals unification planned for January 1, 2027. Do not describe integration as complete on the October 18 check date. Older descriptions of Signals as entirely bring-your-own-data need to be read alongside migration guidance.[2]

## Participation versus capital at risk

Official documentation allows prediction submissions and scoring without staking. Staking puts NMR at risk for rewards or burns; it is not required to participate. Under the current description, unstaked predictions are scored but have zero stake-weighted Meta Model weight and are not used by the fund.[1][3]

Participating or holding NMR is not equivalent to investing in the hedge fund. Separate an unstaked forecasting experiment from financial decisions about tokens or fund exposure.

## The Renaissance Technologies comparison

Renaissance Technologies is known for quantitative investment based on statistical and mathematical models. Numerai solicits predictions from external contributors worldwide. An earlier founder account names Renaissance co-founder Howard Morgan as an early investor.[4]

“The next Renaissance” is an aspiration or comparison, not evidence of equal returns, scale, or methods. Fund performance, company valuation, tournament scores, and participants’ NMR gains/losses are different measures.

## Lessons for Manager

The most useful design is recording a prediction before its outcome and checking it later. Preserve data timestamps, model versions, predictions, later observations, and scoring rules. Compare complex models against simple baselines and measure whether new features or forecasts add information to existing models.

Manager’s targets concern life conditions and service use rather than stock returns. Financial forecasting success does not establish population accuracy, and accurate predictions do not themselves identify intervention effects.

If we participate, start with a small separate experiment: inspect columns, timestamps, targets, and terms; evaluate a simple model through time; compare one new feature family or model; stop expanding if it adds no value. Before live submission, verify the dataset’s opening date and account/submission conditions. Set a time budget so it does not displace Manager development. This is a proposal, not an experiment already begun.

## Sources

1. [Getting Started](https://docs.numer.ai/).
2. Richard Craib, [Unifying Numerai and Signals](https://blog.numer.ai/unifying-numerai-and-signals/), October 16, 2026, including data, migration, and event links.
3. [Staking](https://docs.numer.ai/numerai-tournament/staking), [FAQ](https://docs.numer.ai/numerai-tournament/faq).
4. Richard Craib, [Rogue Machine Intelligence and A New Kind of Hedge Fund](https://medium.com/numerai/rogue-machine-intelligence-and-a-new-kind-of-hedge-fund-7b208deec5f0), the founder’s early-investor account.
