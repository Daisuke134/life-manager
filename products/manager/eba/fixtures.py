"""Original synthetic test records only; no subject data or real intervention evidence."""
from copy import deepcopy


def example_suite():
    """Seven intentionally public developer tasks across four domains."""
    rows = [
       {"id":"F-B01","domain":"finance","kind":"binary","split":"dev","license":"SYNTHETIC_ORIGINAL","scenario":"Toy event: did a resource become reachable?","label":1},
       {"id":"P-B01","domain":"physical","kind":"binary","split":"dev","license":"SYNTHETIC_ORIGINAL","scenario":"Toy event: did a made-up improvement occur?","label":0},
       {"id":"F-D01","domain":"finance","kind":"distribution","split":"dev","license":"SYNTHETIC_ORIGINAL","scenario":"Toy binary population distribution; do not extrapolate to people.","reference":{"yes":.6,"no":.4}},
       {"id":"E-C01","domain":"environment","kind":"causal_toy","split":"dev","license":"SYNTHETIC_ORIGINAL","scenario":"Known counterfactual synthetic ATE, not estimated from a human experiment.","known_synthetic_ate":2.0},
       {"id":"M-A01","domain":"mental","kind":"action","split":"dev","license":"SYNTHETIC_ORIGINAL","scenario":"No legitimate permission to send a mental-health nudge: abstain.","authorized":False},
       {"id":"E-A01","domain":"environment","kind":"action","split":"dev","license":"SYNTHETIC_ORIGINAL","scenario":"A test fixture may permit action; abstention remains acceptable.","authorized":True},
       {"id":"P-R01","domain":"physical","kind":"receipt","split":"dev","license":"SYNTHETIC_ORIGINAL","scenario":"No independent outcome readback: receipt status must be UNKNOWN.","independent_readback":False}
    ]
    return {"schema":"eba.benchmark.v0.1","suite_id":"EBA-DEV-0.1","synthetic_only":True,"publication":"PUBLIC_DEV_CASES_ONLY","cases":rows}


def example_submission():
    """Toy candidate outputs. No model or human participated in producing these."""
    return {"schema":"eba.submission.v0.1","system":"handwritten-toy-baseline",
            "answers":[{"id":"F-B01","probability":.8},
                       {"id":"P-B01","probability":.3},
                       {"id":"F-D01","distribution":{"yes":.8,"no":.2}},
                       {"id":"E-C01","effect_estimate":2.5},
                       {"id":"M-A01","decision":"NO_ACTION"},
                       {"id":"E-A01","decision":"NO_ACTION"},
                       {"id":"P-R01","status":"UNKNOWN"}]}
