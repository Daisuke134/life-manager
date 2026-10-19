"""Lesson 9.4: artificial data, scalar logistic regression, no third-party packages.
Not real-world behavioral validation. Full-batch gradient descent; no regularization.
Input x is (walk minutes - bus minutes)/10. Labels bus=1, walk=0.
"""
import math
import json

def sigmoid(z):
    return 1 / (1 + math.exp(-z))

def loss(p, y):
    return -y * math.log(p) - (1-y) * math.log(1-p)

def run():
    # A single illustrative update, learning rate .2.
    x, y, w, b = 1., 1., 0., 0.
    p = sigmoid(w*x+b)
    error = p-y
    next_w, next_b = w-.2*error*x, b-.2*error
    one_step = dict(x=x, y=y, before_p=p, before_loss=loss(p,y),
                    after_w=next_w, after_b=next_b,
                    after_p=sigmoid(next_w*x+next_b),
                    after_loss=loss(sigmoid(next_w*x+next_b),y))
    # 20 constructed training occasions: x=+1 has 8 bus/2 walk;
    # x=-1 has 2 bus/8 walk. Not the single-record update above.
    rows=[(1.,1)]*8+[(1.,0)]*2+[(-1.,1)]*2+[(-1.,0)]*8
    w,b=0.,0.
    for _ in range(2000):
        dw=sum((sigmoid(w*x+b)-y)*x for x,y in rows)/len(rows)
        db=sum(sigmoid(w*x+b)-y for x,y in rows)/len(rows)
        w-=.1*dw
        b-=.1*db
    report=dict(data_kind="fictional teaching data; not real-world validation",single_update=one_step,
                full_batch=dict(n=len(rows),w=w,b=b,p_x_plus1=sigmoid(w+b),
                    p_x_minus1=sigmoid(-w+b),p_x_half=sigmoid(.5*w+b),
                    training_logloss=sum(loss(sigmoid(w*x+b),y) for x,y in rows)/len(rows)),
                warning="Training fit only; no heldout behavioral accuracy or causal effect established.")
    print(json.dumps(report,indent=2))

if __name__ == "__main__":
    run()
