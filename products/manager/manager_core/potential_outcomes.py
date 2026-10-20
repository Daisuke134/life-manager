"""L006 synthetic potential outcomes. Both Y0 and Y1 never known in real trials."""
from math import isfinite


def _validate(units):
    if not isinstance(units,(list,tuple)) or not units:
        raise ValueError('nonempty synthetic units required')
    ids=set()
    for u in units:
        if not isinstance(u,dict) or set(u)!={'id','y0','y1'} or not isinstance(u['id'],str) or not u['id'] or u['id'] in ids:
            raise ValueError('unique units with id/y0/y1 required')
        ids.add(u['id'])
        if any(type(u[k]) not in (int,float) or not isfinite(u[k]) for k in ('y0','y1')):
            raise ValueError('finite numeric potential outcomes required')
    return ids


def oracle_ate(units):
    """An ORACLE only for fabricated data (impossible on actual individual records)."""
    _validate(units)
    return sum(u['y1']-u['y0'] for u in units)/len(units)


def observed_only(units, assignments):
    ids=_validate(units)
    if not isinstance(assignments,dict) or set(assignments)!=ids or any(type(v) is not int or v not in (0,1) for v in assignments.values()):
        raise ValueError('one binary assignment for each unique unit required')
    return [{'id':u['id'],'treatment':assignments[u['id']], 'outcome':u['y1'] if assignments[u['id']]==1 else u['y0']} for u in units]
