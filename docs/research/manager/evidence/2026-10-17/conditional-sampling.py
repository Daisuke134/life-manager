"""Fictional tutorial only: sample a commuting attribute conditionally."""
import json, random
from pathlib import Path

r = random.Random(42)
people = []
for group, n, probability in [('male', 60, .30), ('female', 40, .05)]:
    for _ in range(n):
        people.append({'group': group, 'bike': r.random() < probability})
counts = {group: sum(p['bike'] for p in people if p['group'] == group)
          for group in ['male', 'female']}
result = {'kind':'fictional educational sampling, not a real population result',
          'random_seed':42,'group_counts':{'male':60,'female':40},
          'conditional_probabilities':{'male':.30,'female':.05},
          'reference_table':[[18,42],[2,38]],
          'expected_bicycle_count':60*.30+40*.05,
          'sampled_bicycle_counts':counts,
          'sampled_bicycle_total':sum(counts.values()),
          'sources':['https://www.jasss.org/15/1/1.html',
                     'https://seeing-theory.brown.edu/compound-probability/index.html'],
          'product_implemented':False}
assert result['expected_bicycle_count']==20
assert len(people)==100
Path('docs/research/manager/evidence/2026-10-17/conditional-sampling-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
