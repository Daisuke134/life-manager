"""Render measured charts plus editable slide/carousel material (docs only)."""
import html
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
font=FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
font_bold=FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')
root=Path(__file__).resolve().parents[1]
r=json.loads((root/'evidence/2026-10-18/household-v0-summary.json').read_text())
b=r['results']['baseline'];c=r['results']['calibrated']
fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
labels=['調整前','調整後\n小数の重み','調整後\n整数の世帯']
values=[b['weighted'],c['weighted'],c['integer']]
for ax,key,title in [(axes[0],'tvd','6区分の構成比のずれ（TVD）'),(axes[1],'max_marginal_error_households','周辺集計との最大差（世帯）')]:
    ys=[v[key] for v in values];bars=ax.bar(range(3),ys,color=['#6b7c93','#81c8cc','#008b96'],width=.62)
    shown=[f'{y:.7f}' for y in ys] if key=='tvd' else ['1,021','約0.000014','17']
    ax.bar_label(bars,labels=shown,padding=5,fontsize=11,fontproperties=font)
    ax.set_xticks(range(3),labels,fontproperties=font);ax.set_title(title,fontproperties=font,fontsize=14,pad=18)
    ax.set_ylim(0,max(ys)*1.22);ax.spines[['top','right']].set_visible(False);ax.yaxis.grid(alpha=.2);ax.set_axisbelow(True)
fig.suptitle('Rhode Islandの世帯人口を生成した実測結果',fontproperties=font_bold,fontsize=18)
fig.text(.02,-.055,'ACS 2020–2024。単一州・同じ調査由来の比較。行動・介入効果は未評価。',fontproperties=font,fontsize=10)
for suffix in ('png','svg'):fig.savefig(root/f'figures/2026-10-18-household-v0-measured.{suffix}',dpi=170,bbox_inches='tight')
plt.close(fig)

content=root/'content/2026-10-18-household-v0';content.mkdir(parents=True,exist_ok=True)
slides=[
 {'title':'人口表から、\n世帯と住民の一覧へ','body':'20,182世帯・45,755人の見本\n↓ 世帯単位で調整・整数化\n441,570世帯・1,042,763人を生成','note':'今回の実測：通常居住世帯のみ'},
 {'title':'家族を\nばらばらにしない','body':'3人世帯を2組選ぶ\n→ 2世帯・6人\n所属を保って、新IDを付ける','note':'この3人世帯の説明は架空の例'},
 {'title':'重みを調整して\n整数化する','body':'世帯種別と人数構成に合わせる\n小数の重み → 複製回数\n整数部分＋端数から抽選（TRS）\n世帯総数を厳密に保つ','note':'既存のIPFとTRSを使った基準実装'},
 {'title':'統計とのずれを\n測った','body':f"整数化後の6区分TVD\n{b['integer']['tvd']:.6f} → {c['integer']['tvd']:.6f}\n0に近いほど構成が近い\nこの比較で約76.8%低下",'note':'家族/非家族 × 1人/2人/3人以上'},
 {'title':'一致したことと、\n残るずれ','body':'世帯数：441,570で一致\n欠員・孤立・ID重複：0\n周辺集計の差：最大17世帯\n人数・年齢の分布は完全一致しない','note':'出力CSVを再読して検査した'},
 {'title':'次は、\n行動を予測する','body':'今回：どんな人が、誰と暮らすか\n次：状況を変えると何を選ぶか\n別の行動データで検証する\n使命：技術で苦しみを減らす','note':'今回、苦しみの軽減効果は未測定'}]
(content/'slides.json').write_text(json.dumps(slides,ensure_ascii=False,indent=2)+'\n')
for aspect,figsize,dpi in [('portrait',(6.75,12),160),('landscape',(12,6.75),160)]:
    for number,s in enumerate(slides,1):
        fig=plt.figure(figsize=figsize,facecolor='#f4f8fa')
        wide=aspect=='landscape';title_size=30 if wide else 25;body_size=21 if wide else 18
        fig.text(.08,.91,'マネージャー  |  世帯人口の実装記録',fontproperties=font,color='#008b96',fontsize=12)
        fig.text(.08,.79,s['title'],fontproperties=font_bold,color='#112b49',fontsize=title_size,va='top',linespacing=1.35)
        fig.text(.08,.52,s['body'],fontproperties=font,color='#18344d',fontsize=body_size,va='top',linespacing=1.9 if not wide else 1.5)
        fig.text(.08,.16,s['note'],fontproperties=font,color='#008b96',fontsize=12)
        fig.text(.08,.085,'出典：ACS 2020–2024 PUMS・B11016\n人口合成の実測。行動・介入効果は未評価。',fontproperties=font,fontsize=10,color='#506477',linespacing=1.5)
        fig.text(.90,.06,f'{number:02d}/06',fontproperties=font,color='#506477',fontsize=11,ha='right')
        fig.savefig(content/f'{aspect}-{number:02d}.png',dpi=dpi);plt.close(fig)
sections='\n'.join(f'<section><small>マネージャー | 世帯人口の実装記録</small><h1>{html.escape(s["title"]).replace(chr(10),"<br>")}</h1><p>{html.escape(s["body"]).replace(chr(10),"<br>")}</p><aside>{html.escape(s["note"])}</aside><footer>出典：ACS 2020–2024 PUMS・B11016<br>人口合成の実測。行動・介入効果は未評価。 {i}/6</footer></section>' for i,s in enumerate(slides,1))
page='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>マネージャー 世帯人口の実装記録</title><style>
body{margin:0;background:#dfe9ef;font-family:system-ui,"Noto Sans CJK JP",sans-serif;color:#18344d}nav{position:sticky;top:0;padding:12px;background:#112b49;color:white;z-index:1}button{padding:8px 16px}section{box-sizing:border-box;background:#f4f8fa;width:min(90vw,540px);aspect-ratio:9/16;margin:24px auto;padding:7%;display:flex;flex-direction:column;justify-content:space-between}small,aside{color:#008b96}h1{font-size:clamp(26px,5vw,42px);line-height:1.35;margin:0}p{font-size:clamp(18px,3vw,26px);line-height:1.8}footer{font-size:12px;color:#506477}.wide section{width:min(95vw,1000px);aspect-ratio:16/9;padding:4%;}.wide h1{font-size:32px}.wide p{font-size:23px;line-height:1.5}@media print{nav{display:none}section{break-after:page;margin:0;width:100%;height:100vh}}
</style><nav><button onclick="document.body.classList.toggle('wide')">縦長／横長を切替</button> 保存済み素材・未投稿</nav>'''+sections+'</html>'
(content/'deck.html').write_text(page)
