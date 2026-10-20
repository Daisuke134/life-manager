"""L007: reproducible, synthetic individual randomization demonstration."""
import random
from math import isfinite


def assign_randomly(n, probability, seed):
    if type(n) is not int or n < 1 or type(probability) not in (int,float) or not isfinite(probability) or not (0 < probability < 1) or type(seed) is not int:
        raise ValueError('positive sample size; 0<p<1; integer seed required')
    rng=random.Random(seed)
    return [int(rng.random()<probability) for _ in range(n)]


def toy_rct_estimate(n=25000,seed=23):
    """Exposes observed outcomes only; oracle truth is known by construction."""
    a=assign_randomly(n,.5,seed)
    treated=[i%10+2. for i,z in enumerate(a) if z==1]
    controls=[float(i%10) for i,z in enumerate(a) if z==0]
    if not treated or not controls:
        raise ValueError('both randomized groups required')
    return {'design':'synthetic_individually_randomized','known_synthetic_ate':2.0,
            'observed_group_difference':sum(treated)/len(treated)-sum(controls)/len(controls),
            'treated_n':len(treated),'control_n':len(controls)}
