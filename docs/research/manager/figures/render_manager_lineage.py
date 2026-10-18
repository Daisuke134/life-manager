"""Render saved research slides; reuses household-v0's Matplotlib/Noto pattern."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
out=root/'content/2026-10-18-manager-lineage'
data=json.loads((out/'slides.json').read_text())
# Reuse the household-v0 figure renderer's established font, image sizes and text layout.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
font=FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
bold=FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')
for aspect,size in [('landscape',(12,6.75)),('portrait',(6.75,12))]:
 for i,s in enumerate(data,1):
  wide=aspect=='landscape';fig=plt.figure(figsize=size,facecolor='#f5f2eb')
  fig.text(.075,.925,'マネージャーのための研究読解',fontproperties=font,fontsize=12,color='#b4452c')
  fig.text(.075,.81,s['title'],fontproperties=bold,fontsize=30 if wide else 25,va='top',linespacing=1.3,color='#172823')
  fig.text(.075,.53,s['body'],fontproperties=font,fontsize=19 if wide else 16.5,va='top',linespacing=1.65 if wide else 2,color='#172823')
  fig.text(.075,.16,s['note'],fontproperties=font,fontsize=10 if wide else 8.5,color='#b4452c')
  from urllib.parse import urlsplit
  names=' / '.join(dict.fromkeys(urlsplit(u).hostname for u in s['sources']))
  fig.text(.075,.09,'出典：'+names+'\n各資料の確認日：2026-10-18。詳細出典は記事とslides.json。',fontproperties=font,fontsize=8,color='#637069',linespacing=1.6)
  fig.text(.93,.07,f'{i:02}/12',fontproperties=font,fontsize=10,ha='right',color='#637069')
  fig.savefig(out/f'{aspect}-{i:02}.png',dpi=160);plt.close(fig)
print('24 slide PNGs rendered from saved slides.json')
