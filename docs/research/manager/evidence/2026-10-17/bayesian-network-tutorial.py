"""Fictional three-node network: enumerate and sample; no causal inference."""
import json,random,hashlib
from pathlib import Path
from collections import Counter
age_p={'young':.6,'older':.4}
employed_p={'young':.8,'older':.3}
low_p={True:.2,False:.7}
joint=[]
for age,pa in age_p.items():
 for employed in [True,False]:
  pe=employed_p[age] if employed else 1-employed_p[age]
  for low in [True,False]:
   pl=low_p[employed] if low else 1-low_p[employed]
   joint.append({'age':age,'employed':employed,'low':low,'probability':pa*pe*pl})
assert abs(sum(x['probability'] for x in joint)-1)<1e-12
assert abs(joint[0]['probability']-.096)<1e-12
r=random.Random(42);counts=Counter()
for _ in range(10000):
 age='young' if r.random()<.6 else 'older'
 employed=r.random()<employed_p[age]
 low=r.random()<low_p[employed]
 counts[(age,employed,low)]+=1
src=Path('/workspace/scratch/manager-research/2026-10-17-remaining/pgmpy-Sampling.py')
out={'kind':'fictional specified-model tutorial; not data-fitted, not a product result','joint':joint,'samples':10000,'seed':42,'sampled_cells':[{'age':a,'employed':e,'low':l,'n':n} for (a,e,l),n in sorted(counts.items())],'assumption':'income is independent of age conditional on employment in this toy chain','causal_model_established':False,'pgmpy_read':{'url':'https://raw.githubusercontent.com/pgmpy/pgmpy/dev/pgmpy/sampling/Sampling.py','sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'method':'BayesianModelSampling.forward_sample','execution':'not_run'},'source_paper':'https://lijunsun.github.io/files/papers/2015-TRC-BN-Population.pdf'}
Path('docs/research/manager/evidence/2026-10-17/bayesian-network-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print('8 joint probabilities sum to 1; target path probability 0.096; 10000 fictional records sampled.')
