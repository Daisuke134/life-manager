"""Render the measured public summary, using matplotlib (documentation only)."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
font=FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
root=Path(__file__).resolve().parents[1]
data=json.loads((root/'evidence/2026-10-18/population-v0-summary.json').read_text())
fig,ax=plt.subplots(figsize=(10,5.4),layout='constrained')
x=range(3);width=.36
for method,offset,color,label in [('independent',-.18,'#667b91','単純独立法'),('ipf',.18,'#008b96','IPF')]:
    ys=[data['partitions'][split]['methods'][method]['mean_tvd'] for split in ('development','validation','test')]
    bars=ax.bar([v+offset for v in x],ys,width,color=color,label=label)
    ax.bar_label(bars,labels=[f'{y:.5f}' for y in ys],padding=4,fontsize=11)
ax.set_xticks(list(x),['開発6州\n初期表に使用','検証4州','最終評価41地域'],fontproperties=font)
ax.set_ylabel('地域平均TVD（0が一致）',fontproperties=font)
ax.set_title('年齢×貧困状態の6区分を復元した実測結果',fontproperties=font,fontsize=16,pad=18)
ax.set_ylim(0,.021);ax.spines[['top','right']].set_visible(False);ax.yaxis.grid(True,alpha=.2);ax.set_axisbelow(True)
ax.legend(prop=font,frameon=False)
fig.text(.02,-.04,'ACS 2020–2024 B17001。推計値との比較。行動予測・介入効果は未評価。',fontproperties=font,fontsize=10)
fig.savefig(root/'figures/2026-10-18-population-v0-measured.png',dpi=170,bbox_inches='tight')
fig.savefig(root/'figures/2026-10-18-population-v0-measured.svg',bbox_inches='tight')
