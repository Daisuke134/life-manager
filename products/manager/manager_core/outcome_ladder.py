"""L012: evidence presence classification, not automated causal certification."""
KEYS=('external_receipt','independent_readback','tangible_benefit',
      'preregistered_comparison','uncertainty_quantified','harms_and_costs_measured',
      'replicated_across_populations')


def proof_level(evidence):
    """Highest attainable P0..P5 from reviewed boolean evidence flags."""
    if not isinstance(evidence,dict) or evidence.keys()-set(KEYS) or any(type(v) is not bool for v in evidence.values()):
        raise ValueError('reviewed known boolean evidence flags required')
    if not evidence.get(KEYS[0],False): return 0
    if not evidence.get(KEYS[1],False): return 1
    if not evidence.get(KEYS[2],False): return 2
    if not all(evidence.get(k,False) for k in KEYS[3:6]): return 3
    return 5 if evidence.get(KEYS[6],False) else 4
