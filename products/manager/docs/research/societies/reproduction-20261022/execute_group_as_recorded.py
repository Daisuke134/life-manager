import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

import nbformat
from nbclient import NotebookClient

ROOT = Path('/workspace/scratch/rothko-agent-group-alignment-artificial-societies-20261022')
OUT = Path('/workspace/scratch/rothko-group-run-20261022')

# Restrict this process and inherited notebook kernels only, never sibling work.
if hasattr(os, 'sched_getaffinity'):
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
os.environ.update(LOKY_MAX_CPU_COUNT='2', OMP_NUM_THREADS='1',
                  OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
                  NUMEXPR_NUM_THREADS='1', MPLBACKEND='module://matplotlib_inline.backend_inline',
                  MPLCONFIGDIR=str(OUT/'mpl-cache'),
                  JUPYTER_PATH=str(OUT))
kernel = OUT/'kernels/rothko-isolated'
kernel.mkdir(parents=True, exist_ok=True)
(kernel/'kernel.json').write_text(json.dumps({
    'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],
    'display_name':'Rothko isolated Python '+platform.python_version(),
    'language':'python',
}))

principal_diagnostics = '''
import json, pathlib, platform
diagnostics = {
    "source": "unmodified original cells, followed by this diagnostic cell",
    "python": platform.python_version(), "numpy": np.__version__,
    "n_agents": N_agent, "n_principals": N_principal,
    "alpha": ALPHA, "beta": BETA, "eta": ETA, "watched_fraction": M,
    "epsilon": EPSILON, "human_norm_mean": float(r_bar),
    "initial_latent_mean": float(theta0.mean()),
    "with_oversight": {"final_latent_mean":float(full.mean_latent_norm[-1]),
                       "aligned_fraction":float(full.aligned_fraction[-1])},
    "conformity_only": {"final_latent_mean":float(conf.mean_latent_norm[-1]),
                        "aligned_fraction":float(conf.aligned_fraction[-1])},
    "oversight_sweep": {"fractions":ms,"alpha_0":no_norms,
                        "alpha_005":lower_norms,"alpha_01":with_norms},
    "withdrawal": [],
}
for diagnostic_eta in [0.0, 0.002, 0.01, 0.05]:
    diagnostic_run=simulate(eta=diagnostic_eta,T=1200,T_off=600)
    diagnostics["withdrawal"].append({
        "eta":diagnostic_eta,"before_599":float(diagnostic_run.mean_behaviour[599]),
        "after_1199":float(diagnostic_run.mean_behaviour[-1]),
        "final_latent":float(diagnostic_run.mean_latent_norm[-1]),
        "final_aligned_fraction":float(diagnostic_run.aligned_fraction[-1])})
pathlib.Path("principal-agent.results.json").write_text(json.dumps(diagnostics,indent=2)+"\\n")
print("DIAGNOSTIC",json.dumps(diagnostics))
'''

abm_diagnostics = '''
import json, pathlib, platform
diagnostics = {
    "source": "unmodified original cells, followed by this diagnostic cell",
    "python": platform.python_version(), "numpy":np.__version__,
    "grid": GRID,"seeds_default":SEEDS,"n_jobs_declared":N_JOBS,
    "joblib_effective_n_jobs":__import__('joblib').effective_n_jobs(N_JOBS),
    "speed_ratios_h1":RHOS,"fast_started":list(map(float,fast_started)),
    "fast_to_fast":list(map(float,ff_share)),"fast_received":list(map(float,fast_received)),
    "baseline_C":{"estimate":float(base.estimate),"lo":float(base.lower_bound),
                  "hi":float(base.upper_bound),"ticks":base.ticks},
    "hypothesis_2_final_slow_share":{str(k):float(v[:,-1].mean()/1600) for k,v in traces.items()},
    "sweep":{"rhos":SWEEP_RHOS,"P_sf":SWEEP_PSF,
             "results":{str(k):v.tolist() for k,v in results.items()}},
    "heat":{"rho":HEAT_RHO,"P_sf":HEAT_PSF,"P_fs":HEAT_PFS,
            "values":heat.tolist(),"reaches_C_ge_1":int((heat>=1).sum())},
}
pathlib.Path("abm.results.json").write_text(json.dumps(diagnostics,indent=2)+"\\n")
print("DIAGNOSTIC",json.dumps(diagnostics))
'''

name = sys.argv[1]
if name == 'principal-agent':
    source=ROOT/'principal-agent-problem-framework/group-alignment-numerical-simulation.ipynb'
    diagnostics=principal_diagnostics
else:
    source=ROOT/'agent-based-modelling/hypotheses_numerical_simulation.ipynb'
    diagnostics=abm_diagnostics
notebook=nbformat.read(source,as_version=4)
original_cells=len(notebook.cells)
for cell in notebook.cells:
    if cell.cell_type=='code':
        cell.outputs=[];cell.execution_count=None
notebook.cells.append(nbformat.v4.new_code_cell(diagnostics))
start=time.monotonic()
def progress(cell_index, **kwargs):
    print(f'{name} cell {cell_index}/{len(notebook.cells)} start elapsed={time.monotonic()-start:.2f}s',flush=True)
client=NotebookClient(notebook,timeout=600,kernel_name='rothko-isolated',
                      resources={'metadata':{'path':str(OUT)}},
                      on_cell_execute=progress)
status='PASS';failure=None
try:
    client.execute()
except Exception as exc:
    status='FAIL';failure=f'{type(exc).__name__}: {exc}'
finally:
    nbformat.write(notebook,OUT/f'{name}.executed.ipynb')
    image_count=0
    streams=[]
    for ci,cell in enumerate(notebook.cells):
        for oi,output in enumerate(cell.get('outputs',[])):
            if output.get('output_type')=='stream':
                streams.append({'cell':ci,'text':output.text})
            encoded=output.get('data',{}).get('image/png')
            if encoded:
                (OUT/f'{name}-cell-{ci}-{oi}.png').write_bytes(base64.b64decode(encoded))
                image_count+=1
    result=dict(status=status,failure=failure,source=str(source),
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                source_commit='82cfd86cad33cd51327e17fc5eddeac9b9b5c1da',
                original_cells=original_cells,appended_diagnostic_cells=1,
                original_cell_mutations=0,seconds=time.monotonic()-start,
                cpu_affinity=sorted(os.sched_getaffinity(0)),figures=image_count,
                streams=streams)
    (OUT/f'{name}.execution.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='streams'}),flush=True)
if status!='PASS': sys.exit(1)
