"""Distinguish calibration, integerization, and same-source person diagnostics."""
import math
from manager.population.contracts import PopulationDataError
from manager.population.households import cell_index
from manager.population.household_export import validate_copies


def age_group(person):return 0 if person.age<18 else 1 if person.age<65 else 2


def evaluate_households(households,weights,copies,controls,reference):
    validate_copies(households,copies)
    if not isinstance(weights,tuple) or len(weights)!=len(households) or any(type(w) not in (int,float) or not math.isfinite(w) or w<0 for w in weights):
        raise PopulationDataError('invalid evaluation weights')
    if not math.isclose(math.fsum(weights),controls.total,rel_tol=1e-10,abs_tol=1e-7):raise PopulationDataError('weighted household total mismatch')
    if not isinstance(reference,tuple) or len(reference)!=6 or any(type(v) is not int or v<0 for v in reference) or sum(reference)!=controls.total or reference[0]!=0:
        raise PopulationDataError('invalid household reference')
    if (sum(reference[:3]),sum(reference[3:]))!=controls.family or tuple(reference[i]+reference[i+3] for i in range(3))!=controls.size:
        raise PopulationDataError('reference and controls disagree')
    person_ref=tuple(sum(p.weight for h in households for p in h.persons if age_group(p)==i) for i in range(3))
    ref_total=sum(person_ref);ref_shares=tuple(v/ref_total for v in person_ref)
    def measure(values):
        counts=tuple(math.fsum(w for h,w in zip(households,values) if cell_index(h)==i) for i in range(6))
        age_counts=tuple(math.fsum(w*sum(age_group(p)==i for p in h.persons) for h,w in zip(households,values)) for i in range(3))
        total=math.fsum(values);people=math.fsum(age_counts)
        if total<=0 or people<=0:raise PopulationDataError('empty synthesized population')
        shares=tuple(v/people for v in age_counts)
        marginals=(sum(counts[:3]),sum(counts[3:]),*(counts[i]+counts[i+3] for i in range(3)))
        residual=max(abs(a-b) for a,b in zip(marginals,controls.family+controls.size))
        return {'counts':counts,'households':total,'persons':people,'tvd':math.fsum(abs(a/total-b/controls.total) for a,b in zip(counts,reference))/2,
                'max_marginal_error_households':residual,'max_marginal_error_fraction':residual/controls.total,
                'age_shares':shares,'age_share_error_pp':tuple(100*abs(a-b) for a,b in zip(shares,ref_shares))}
    return {'weighted':measure(weights),'integer':measure(copies),
            'person_reference':{'weight':'PWGTP','persons':ref_total,'age_shares':ref_shares,'independent':False}}
