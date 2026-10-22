"""Technical owned-page options plus NO_ACTION; no predicted human benefit needed."""
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
from .models.intervention import Candidate,OutcomeEndpoint,OutcomeVector
from .models.problem import Problem
from .authority import OwnedDigitalScope
from .digital_environment import PAGES,PUBLISH_PREFIX


@dataclass(frozen=True)
class CandidateCatalog:
    version: str = 'owned-digital-v1'

    def __post_init__(self):
        if self.version!='owned-digital-v1':raise ValueError('unknown catalog version')


def validate_candidates(candidates):
    if (type(candidates) is not tuple or not candidates or any(type(c) is not Candidate for c in candidates)
            or sum(c.no_action for c in candidates)!=1
            or len({c.candidate_id for c in candidates})!=len(candidates)):
        raise ValueError('unique candidates with exactly one structural NO_ACTION required')
    return candidates


def generate_candidates(problem: Problem,catalog: CandidateCatalog) -> tuple[Candidate,...]:
    if type(problem) is not Problem or type(catalog) is not CandidateCatalog:
        raise ValueError('existing typed problem and frozen catalog required')
    refs=tuple(sorted({o.source.source_id for o in problem.observations}))
    no_action=Candidate('no-action','NO_ACTION','NO_TARGET',refs,'Preserve existing bundle; opportunity cost unknown.')
    targets={o.scope for o in problem.observations}
    allowed={PUBLISH_PREFIX+p for p in PAGES}
    if len(targets)!=1 or not targets<=allowed:return (no_action,)
    target=next(iter(targets))
    candidates=[no_action,Candidate('ask','ASK',target,refs,'Clarify a technical ambiguity; no automatic message.'),
                Candidate('pass','PASS',target,refs,'Record abstention without external change.')]
    actions={'broken_official_links':('CORRECT_LINK','verified_official_link_target'),
             'missing_accessible_labels':('IMPROVE_ACCESSIBILITY','accessible_link_label')}
    if problem.target_metric in actions:
        action,criterion=actions[problem.target_metric]
        candidates.append(Candidate('technical-correction',action,target,refs,criterion,
            OutcomeVector((OutcomeEndpoint(problem.target_metric,'count',None,'existing_owned_bundle'),))))
    return validate_candidates(tuple(candidates))


def feasible(candidate: Candidate,authority: OwnedDigitalScope | None,budget: Decimal,*,at=None) -> bool:
    """Preview constraints only; does not authenticate or authorize an effect."""
    if type(candidate) is not Candidate:raise ValueError('typed candidate required')
    if candidate.action in {'NO_ACTION','ASK','PASS'}:return True
    if type(budget) is not Decimal or not budget.is_finite() or budget<0:return False
    return (type(authority) is OwnedDigitalScope and bool(candidate.technical_criterion)
            and authority.allows(candidate.target,at or datetime.now(timezone.utc))
            and candidate.command_cost_usd<=budget)
