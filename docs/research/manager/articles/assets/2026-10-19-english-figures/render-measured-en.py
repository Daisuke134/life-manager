"""Draw English charts directly from saved measured results; never modify image pixels.
Adapted from figures/plot_population_v0.py and figures/render_household_v0.py.
Only writes the two task-owned English PNGs beside this file.
"""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
DATA = ROOT / 'evidence/2026-10-18'
pop = json.loads((DATA / 'population-v0-summary.json').read_text())
house = json.loads((DATA / 'household-v0-summary.json').read_text())
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11})

fig, ax = plt.subplots(figsize=(12, 6.1), layout='constrained')
for method, offset, color, label in [('independent', -.18, '#667b91', 'Independence baseline'), ('ipf', .18, '#008b96', 'IPF')]:
    ys = [pop['partitions'][split]['methods'][method]['mean_tvd'] for split in ('development', 'validation', 'test')]
    bars = ax.bar([v+offset for v in range(3)], ys, .36, color=color, label=label)
    ax.bar_label(bars, labels=[f'{y:.6f}' for y in ys], padding=5, fontsize=12)
ax.set_xticks(range(3), ['Development: 6 states\nUsed to build initial table', 'Validation: 4 states', 'Final evaluation: 41 regions'])
ax.set_ylabel('Unweighted regional mean TVD (0 = agreement)')
ax.set_title('Measured reconstruction of six age-by-poverty categories', fontsize=17, pad=18)
ax.set_ylim(0, .021)
ax.spines[['top', 'right']].set_visible(False)
ax.yaxis.grid(True, alpha=.2)
ax.set_axisbelow(True)
ax.legend(frameon=False)
fig.text(.02, -.045, 'ACS 2020–2024 B17001; comparison with survey estimates. Behavior and intervention effects were not evaluated.', fontsize=10)
fig.savefig(OUT / '2026-10-18-population-v0-measured-en.png', dpi=170, bbox_inches='tight')
plt.close(fig)

b = house['results']['baseline']; c = house['results']['calibrated']
values = [b['weighted'], c['weighted'], c['integer']]
fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout='constrained')
labels = ['Before\nadjustment', 'Adjusted\nfractional weights', 'Adjusted\ninteger households']
for ax, key, title in [(axes[0], 'tvd', 'Six-cell composition discrepancy (TVD)'), (axes[1], 'max_marginal_error_households', 'Maximum marginal-total discrepancy (households)')]:
    ys = [v[key] for v in values]
    bars = ax.bar(range(3), ys, color=['#6b7c93', '#81c8cc', '#008b96'], width=.62)
    shown = [f'{y:.8f}' for y in ys] if key == 'tvd' else [f'{ys[0]:,.0f}', f'{ys[1]:.8f}', f'{ys[2]:.0f}']
    ax.bar_label(bars, labels=shown, padding=5, fontsize=12)
    ax.set_xticks(range(3), labels)
    ax.set_title(title, fontsize=14, pad=18)
    ax.set_ylim(0, max(ys)*1.22)
    ax.spines[['top', 'right']].set_visible(False)
    ax.yaxis.grid(alpha=.2)
    ax.set_axisbelow(True)
fig.suptitle('Measured household reconstruction in Rhode Island', fontsize=19)
fig.text(.02, -.045, 'ACS 2020–2024; one state, shared survey source. The 17-household marginal discrepancy is not a bound on every cross-cell.\nPerson totals and age composition are not fully matched. Behavior and intervention effects were not evaluated.', fontsize=10, linespacing=1.5)
fig.savefig(OUT / '2026-10-18-household-v0-measured-en.png', dpi=170, bbox_inches='tight')
plt.close(fig)
