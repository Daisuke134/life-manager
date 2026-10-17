"""Offline source inspection and one validation probe; no model inference."""
import hashlib, importlib.util, json, subprocess, sys
from pathlib import Path
upstreams = Path('/workspace/scratch/manager-research/2026-10-17-remaining')
records=[]
for folder in sorted(upstreams.iterdir()):
    if not (folder/'.git').exists(): continue
    files=[]
    selected = {
      'StanfordHCI__genagents':['README.md','LICENSE','genagents/genagents.py','genagents/modules/interaction.py','genagents/modules/memory_stream.py'],
      'akaashkolluri__socrates':['README.md'],
      'MJones235__LLM-Population-Generator':['LICENSE','population_generator/engine/generator.py','population_generator/generation/prompts.py','population_generator/data/validation.py'],
      'MJones235__Synthetic-Population-Experiments':['LICENSE','experiments/03_newcastle/scripts/04_analysis/validate_full_cross_tab.py','experiments/07_method_benchmark/scripts/09_compare_methods.py']
    }[folder.name]
    for name in selected:
        p=folder/name
        files.append({'path':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    records.append({'repository':folder.name.replace('__','/'),'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=folder,text=True).strip(),'files_read':files})
p=upstreams/'MJones235__LLM-Population-Generator/population_generator/data/validation.py'
spec=importlib.util.spec_from_file_location('inspected_validation',p)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
validator=module.CustomValidator()
validator.add_function_rule('nonnegative_age',lambda x: x['age']>=0,description='Teaching-only nonnegative age check')
valid=validator.validate_with_summary({'age':30});invalid=validator.validate_with_summary({'age':-1})
assert valid['valid'] is True and invalid['valid'] is False
out={'date':'2026-10-17','repositories':records,'probe':{'kind':'fictional offline validator exercise, not population generation','age_30':valid,'age_minus_1':invalid},'model_inference_run':False,'training_run':False,'commercial_product_reproduced':False,'product_implementation_complete':False}
Path('docs/research/manager/evidence/2026-10-17/upstream-inspection.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print('Pinned',len(records),'repositories; offline validation probe passed; no model calls.')
