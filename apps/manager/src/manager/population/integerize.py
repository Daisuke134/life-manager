"""Truncate–replicate–sample (TRS), preserving the requested household total."""
import math
import numpy as np
from .contracts import PopulationDataError
from .households import integer


def integerize(weights,total,seed):
    integer(total,1,1000000,'total');integer(seed,0,2**32-1,'random seed')
    if not isinstance(weights,tuple) or not weights or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in weights):
        raise PopulationDataError('invalid household weights')
    if not math.isclose(math.fsum(weights),total,rel_tol=1e-10,abs_tol=1e-7):raise PopulationDataError('weights do not sum to target households')
    x=np.array(weights,dtype=float);copies=np.floor(x).astype(np.int64);remaining=total-int(copies.sum())
    if remaining<0:raise PopulationDataError('integer parts exceed target')
    if remaining:
        fractions=x-copies
        if fractions.sum()<=0:raise PopulationDataError('no fractional support for remaining households')
        rng=np.random.Generator(np.random.PCG64(seed))
        draws=rng.choice(len(x),remaining,replace=True,p=fractions/fractions.sum())
        copies+=np.bincount(draws,minlength=len(x))
    return tuple(int(v) for v in copies)
