"""Two reconstructors. Neither accepts target joint tables or reference paths."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
import numpy as np
from ipfn import ipfn
from .contracts import FitResult, Marginals, PopulationDataError, numbers


def _residual(counts, target):
    x=np.array(counts).reshape(2,3)
    return float(max(np.max(np.abs(x.sum(axis=1)-target.poverty)),np.max(np.abs(x.sum(axis=0)-target.age)))/target.total)


def independent_population(target: Marginals):
    if not isinstance(target,Marginals): raise PopulationDataError('expected marginal-only input')
    counts=tuple(p/target.total*a for p in target.poverty for a in target.age)
    return FitResult(target.geo_id,'independent',counts,0,_residual(counts,target),None,target.source.extract_sha256)


def fit_population(seed, target: Marginals, *, tolerance=1e-10, max_iterations=1000):
    if not isinstance(target,Marginals): raise PopulationDataError('expected marginal-only input')
    numbers(seed,6,'seed')
    if min(seed)<=0: raise PopulationDataError('positive seed support required; no epsilon replacement')
    if isinstance(tolerance,bool) or not isinstance(tolerance,(float,int)) or not math.isfinite(tolerance) or not 0<tolerance<1:
        raise PopulationDataError('invalid tolerance')
    if type(max_iterations) is not int or max_iterations<1: raise PopulationDataError('invalid max_iterations')
    rows=np.array(target.poverty)>0;cols=np.array(target.age)>0
    original=np.array(seed,dtype=np.float64).reshape(2,3)
    sub=original[np.ix_(rows,cols)].copy()
    sub=sub/sub.sum()*target.total
    try:
        # ipfn's loop includes max_iteration; keep the public iteration cap exact.
        with redirect_stdout(io.StringIO()),np.errstate(all='raise'):
            fitted,flag,history=ipfn.ipfn(sub,[np.array(target.poverty)[rows],np.array(target.age)[cols]],
                [[0],[1]],convergence_rate=tolerance,max_iteration=max_iterations-1,
                verbose=2,rate_tolerance=0.0).iteration()
        output=np.zeros((2,3),dtype=np.float64);output[np.ix_(rows,cols)]=fitted
        counts=tuple(float(v) for v in output.flat)
        residual=_residual(counts,target)
        if not math.isfinite(residual) or residual>tolerance or len(history)>max_iterations:
            raise PopulationDataError(f'IPF did not meet residual/cap: residual={residual}, iterations={len(history)}, library_flag={flag}')
        seed_hash=hashlib.sha256(json.dumps([float(x) for x in seed],separators=(',',':'),allow_nan=False).encode()).hexdigest()
        return FitResult(target.geo_id,'ipf',counts,len(history),residual,seed_hash,target.source.extract_sha256)
    except (FloatingPointError,ValueError,OverflowError) as exc:
        if isinstance(exc,PopulationDataError): raise
        raise PopulationDataError(f'IPF numeric failure: {exc}') from exc
