"""Equal-record, 170/40-study supervised head on a public pretrained encoder.

Scientific boundaries: numeric cross-study response-code labels are not
equivalent human choice options. Frozen published sentence embeddings and
supervised logistic head are a weak text representation benchmark, not the
original Socrates model (8B/14B) or a human-behavior foundation model.
"""
from collections import Counter, defaultdict
from math import isfinite

LABELS=[str(i) for i in range(11)]+["OTHER"]


def validate_and_partition(mapping, sample, *, rows_per_study=20):
    if type(mapping) is not dict or set(mapping)!={"seen","unseen"}:
        raise ValueError("invalid split")
    seen=set(mapping["seen"]); unseen=set(mapping["unseen"])
    if len(seen)!=170 or len(unseen)!=40 or seen&unseen or len(seen|unseen)!=210:
        raise ValueError("invalid study metadata")
    bystudy=Counter();tr=[];te=[]
    for r in sample:
        if type(r) is not tuple or len(r)!=3:
            raise ValueError("only (study-id, stimulus text, coarse label)")
        study,stimulus,label=r
        if study not in seen|unseen or type(stimulus) is not str or not stimulus or label not in LABELS:
            raise ValueError("bad observed sample input")
        if len(stimulus)>600:
            raise ValueError("long text not bounded")
        bystudy[study]+=1
        (tr if study in seen else te).append(r)
    if set(bystudy)!=seen|unseen or any(n!=rows_per_study for n in bystudy.values()):
        raise ValueError("all studies must have predeclared fixed count")
    return tr,te


def score_same_rows(training_labels, samples, prob_vectors):
    """Non-sensitive labels only. Predictions correspond to the *same* heldout rows."""
    if len(samples)!=len(prob_vectors) or not training_labels or not samples:
        raise ValueError("test predictions and labels must align")
    training=Counter(training_labels)
    if any(k not in LABELS for k in training_labels):
        raise ValueError("bad training label")
    ntrain=sum(training.values())
    prior=[training[k]/ntrain for k in LABELS]
    majority=max(range(len(LABELS)),key=lambda i:prior[i])
    methods={
        "train_frequency_prior":[prior]*len(samples),
        "train_majority_hard":[[int(j==majority) for j in range(len(LABELS))]]*len(samples),
        "frozen_pretrained_encoder_plus_trained_head":prob_vectors,
    }
    reports={}
    for model,vectors in methods.items():
        acc=brier=0.0
        study_prob=defaultdict(list)
        study_actual=defaultdict(Counter)
        bins=[{"count":0,"confidence_sum":0.0,"correct_sum":0.0} for _ in range(10)]
        for (_,_,label),p in zip(samples,vectors):
            if len(p)!=len(LABELS) or any(type(x) not in (float,int) or not isfinite(x) or x<0 or x>1 for x in p) or abs(sum(p)-1)>1e-5:
                raise ValueError("not a categorical probability vector")
            index=LABELS.index(label)
            chosen=max(range(len(p)),key=lambda i:p[i]);matched=int(chosen==index)
            acc+=matched
            brier+=sum((v-int(j==index))**2 for j,v in enumerate(p))
        # Keep explicit sample row index rather than any derived person ID.
        for (study,_,label),p in zip(samples,vectors):
            study_prob[study].append(p)
            study_actual[study][label]+=1
            conf=max(p)
            matched=int(LABELS[p.index(conf)]==label) if isinstance(p,list) else int(LABELS[max(range(len(p)),key=lambda i:p[i])]==label)
            b=min(9,int(conf*10))
            bins[b]["count"]+=1;bins[b]["confidence_sum"]+=conf;bins[b]["correct_sum"]+=matched
        tvds=[];ns=[]
        for study,cnt in study_actual.items():
            size=sum(cnt.values())
            pred=[sum(v[i] for v in study_prob[study])/size for i in range(len(LABELS))]
            actual=[cnt[k]/size for k in LABELS]
            tvds.append(.5*sum(abs(p-q) for p,q in zip(pred,actual)))
            ns.append(size)
        n=len(samples)
        reports[model]={
            "n":n,"studies":len(study_actual),
            "accuracy":round(acc/n,8),"brier_multiclass":round(brier/n,8),
            "tvd_study_macro":round(sum(tvds)/len(tvds),8),
            "tvd_study_micro":round(sum(t*w for t,w in zip(tvds,ns))/n,8),
            "reliability":[{"bin":i,"n":b["count"],"mean_confidence":round(b["confidence_sum"]/b["count"],7) if b["count"] else None,"observed_correct":round(b["correct_sum"]/b["count"],7) if b["count"] else None} for i,b in enumerate(bins)],
        }
    return reports
