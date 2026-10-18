"""Educational arithmetic, not a trained Transformer or population predictor.
Run with Python standard library. All logits and activations are invented.
"""
import json
import math
from pathlib import Path

def softmax(xs):
    z = max(xs)
    es = [math.exp(x-z) for x in xs]
    return [x/sum(es) for x in es]

def loss(logits):
    return -math.log(softmax(logits)[0])

def main():
    logits = [2.0, 1.0, 0.0]
    before = softmax(logits)
    gradient = [before[0]-1, before[1], before[2]]
    step = 0.1
    after_logits = [x-step*g for x,g in zip(logits, gradient)]
    eps = 1e-5
    numeric = []
    for i in range(3):
        plus, minus = logits.copy(), logits.copy()
        plus[i] += eps
        minus[i] -= eps
        numeric.append((loss(plus)-loss(minus))/(2*eps))
    assert max(abs(a-b) for a,b in zip(gradient,numeric)) < 1e-8
    assert loss(after_logits) < loss(logits)
    attention = softmax([0,2,1])
    result = {
        'kind':'invented educational arithmetic; not research results',
        'candidates':['就業','非就業','学生'],
        'logits_before':logits,'probabilities_before':before,
        'loss_before':loss(logits),'analytic_gradient':gradient,
        'finite_difference_gradient':numeric,'learning_rate':step,
        'logits_after':after_logits,'probabilities_after':softmax(after_logits),
        'loss_after':loss(after_logits),
        'attention_scores':[0,2,1],'attention_weights':attention,
        'attention_values':[0,2,1],
        'attention_weighted_sum':sum(a*b for a,b in zip(attention,[0,2,1])),
        'neuron_example':{'input':[1,2],'weights':[0.4,-0.1],'bias':0.2,'preactivation':1*.4+2*(-.1)+.2},
    }
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
