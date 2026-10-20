"""L008 toy MRT: 5 decision points/day, available occasions randomized.

Not real HeartSteps data, implementation or actual intervention.
"""
import random


def simulate_decision_points(availability, seed):
    if not isinstance(availability,(list,tuple)) or not availability or len(availability)%5 or any(type(a) is not bool for a in availability) or type(seed) is not int:
        raise ValueError('whole days of five true/false availability points and seed required')
    rng=random.Random(seed); result=[]
    for i,possible in enumerate(availability):
        point={'day':i//5+1,'slot':i%5+1,'available':possible,
               'randomized':possible,'action':'unavailable','assignment_probability':None,
               'proximal_window_minutes':None}
        if possible:
            u=rng.random()
            action,probability=('no_suggestion',.4) if u<.4 else (('walking_suggestion',.3) if u<.7 else ('anti_sedentary_suggestion',.3))
            point.update(action=action,assignment_probability=probability,proximal_window_minutes=30)
        result.append(point)
    return result
