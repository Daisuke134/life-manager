"""Calibrate existing household weights; never invent missing households."""
from contextlib import redirect_stdout
import io
import math
import numpy as np
from ipfn import ipfn
from .contracts import PopulationDataError
from .households import Household,HouseholdControls,cell_index


def household_weights(households,controls,method,*,tolerance=1e-10,max_iterations=1000):
    if not isinstance(controls,HouseholdControls) or not households or any(not isinstance(h,Household) for h in households):
        raise PopulationDataError('expected households and marginal-only controls')
    if len({h.serialno for h in households})!=len(households):raise PopulationDataError('duplicate seed households')
    if method not in ('baseline','calibrated'):raise PopulationDataError('unknown household method')
    if type(max_iterations) is not int or max_iterations<1 or type(tolerance) not in (int,float) or not math.isfinite(tolerance) or not 0<tolerance<1:
        raise PopulationDataError('invalid household solver settings')
    total=sum(h.weight for h in households)
    if method=='baseline':return tuple(h.weight*controls.total/total for h in households)
    seed=np.array([math.fsum(h.weight for h in households if cell_index(h)==i) for i in range(6)],dtype=float).reshape(2,3)
    rows=np.array(controls.family)>0;cols=np.array(controls.size)>0
    sub=seed[np.ix_(rows,cols)].copy()
    if np.any(sub.sum(axis=0)==0) or np.any(sub.sum(axis=1)==0):raise PopulationDataError('missing support for a positive household target')
    sub*=controls.total/sub.sum()
    try:
        with redirect_stdout(io.StringIO()),np.errstate(all='raise'):
            fitted,flag,history=ipfn.ipfn(sub,[np.array(controls.family)[rows],np.array(controls.size)[cols]],[[0],[1]],
                convergence_rate=tolerance,max_iteration=max_iterations-1,verbose=2,rate_tolerance=0).iteration()
        target=np.zeros((2,3));target[np.ix_(rows,cols)]=fitted
        residual=max(np.max(abs(target.sum(axis=0)-controls.size)),np.max(abs(target.sum(axis=1)-controls.family)))/controls.total
        if not np.isfinite(target).all() or residual>tolerance or len(history)>max_iterations:
            raise PopulationDataError(f'household IPF did not converge: residual={residual}, flag={flag}')
        if target[0,0]!=0 or np.any((seed==0)&(target!=0)):raise PopulationDataError('solver invented unsupported households')
        return tuple(float(h.weight*target.flat[cell_index(h)]/seed.flat[cell_index(h)]) for h in households)
    except (FloatingPointError,ValueError,OverflowError) as exc:
        if isinstance(exc,PopulationDataError):raise
        raise PopulationDataError(f'household IPF failed: {exc}') from exc
