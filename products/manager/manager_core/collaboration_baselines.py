"""Frozen deterministic advisory baselines; see only the public PlannerContext."""
from .collaboration import AdvisoryResult, PlannerContext


def no_action_baseline(context: PlannerContext) -> AdvisoryResult:
    if type(context) is not PlannerContext:raise ValueError('typed public context required')
    return AdvisoryResult('PASS','NO_ACTION comparison baseline.',())


def rule_baseline(context: PlannerContext) -> AdvisoryResult:
    if type(context) is not PlannerContext:raise ValueError('typed public context required')
    goal=context.goal.lower()
    if any(x in goal for x in ('do not interrupt','no further help','declined')):
        return AdvisoryResult('PASS','Respect the stated request for no further help.',())
    if any(x in goal for x in ('clarify','conflicting','unknown')):
        return AdvisoryResult('ASK','Clarify the unresolved public-information need.',())
    if any(x in goal for x in ('correct','accessibility','official link','update')):
        return AdvisoryResult('PROPOSE','Consider a bounded source-cited improvement.',
                              (context.facts[0].source.source_id,))
    return no_action_baseline(context)
