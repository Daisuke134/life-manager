"""Retrospective cell reconstruction scores; no behavior or field claims."""
import math
from dataclasses import asdict
from manager.population.contracts import PopulationDataError, PopulationScore, same_total

TRACKS = {'population_fidelity':'measured','behavior_prediction':'not_run','policy':'not_run','execution':'not_run','field':'not_run'}


def score_population(prediction, reference):
    if prediction.geo_id != reference.geo_id or prediction.target_source_sha256 != reference.source.extract_sha256:
        raise PopulationDataError('prediction/reference scope mismatch')
    same_total(prediction.counts, reference.total)
    p, r = prediction.counts, reference.counts
    differences = [abs(a-b)/reference.total for a,b in zip(p,r)]
    rates=[]
    for i in range(3):
        denominator=r[i]+r[i+3]
        predicted=p[i]+p[i+3]
        if denominator == 0:
            rates.append(None)
        elif predicted == 0:
            raise PopulationDataError('prediction omitted a nonempty age category')
        else:
            rates.append(100*abs(p[i]/predicted-r[i]/denominator))
    return PopulationScore(reference.geo_id,prediction.method,math.fsum(differences)/2,max(differences)*100,tuple(rates))


def summarize_population(scores, references):
    refs={r.geo_id:r for r in references}
    if not refs or len(refs)!=len(references): raise PopulationDataError('empty/duplicate reference')
    grouped={}
    for score in scores:
        group=grouped.setdefault(score.method,{})
        if score.geo_id in group: raise PopulationDataError('duplicate score')
        group[score.geo_id]=score
    if not grouped: raise PopulationDataError('no scores')
    methods={}
    for method,group in sorted(grouped.items()):
        if set(group)!=set(refs): raise PopulationDataError('incomplete score coverage')
        ordered=[group[g] for g in sorted(refs)]
        total=math.fsum(r.total for r in refs.values())
        methods[method]={
            'mean_tvd':math.fsum(s.tvd for s in ordered)/len(ordered),
            'max_tvd':max(s.tvd for s in ordered),
            'population_weighted_mean_tvd':math.fsum(group[g].tvd*refs[g].total for g in sorted(refs))/total,
            'mean_max_cell_error_pp':math.fsum(s.max_cell_error_pp for s in ordered)/len(ordered),
            'max_cell_error_pp':max(s.max_cell_error_pp for s in ordered)}
    return {'stage':'empirical_reconstruction','tracks':dict(TRACKS),'region_count':len(refs),'methods':methods}
