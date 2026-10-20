from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import math
root=Path(__file__).resolve().parents[1]
out=root/'docs/visuals'
out.mkdir(parents=True,exist_ok=True)
W,H=1800,1070
im=Image.new('RGB',(W,H),'#F7FAFF')
d=ImageDraw.Draw(im)
reg='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
bold='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
def f(sz,b=False):return ImageFont.truetype(bold if b else reg,sz)
def text(x,y,t,sz=24,c='#244168',b=False): d.text((x,y),t,font=f(sz,b),fill=c)
def rr(x,y,w,h,fill,stroke='#D8E2EF',r=18,lw=2): d.rounded_rectangle((x,y,x+w,y+h),radius=r,fill=fill,outline=stroke,width=lw)
def rowitems(items, y, colors):
 w=400;start=35
 for i,(head,second,desc,line) in enumerate(items):
  x=start+i*435
  rr(x,y,w,216,'#FFFFFF',colors[i],16,3)
  rr(x+18,y+18,118,32,colors[i],colors[i],7,1)
  text(x+29,y+20,head,17,'white',True)
  text(x+18,y+64,second,28,'#0E2D53',True)
  text(x+18,y+111,desc,20,'#425770')
  text(x+18,y+144,line,18,'#59738D')
text(35,22,'H001  |  HeartSteps 実データの見取り図',44,'#0F2952',True)
text(35,94,'実データの構造を理解する  ·  個人の生データはまだ取得しない',23,'#516B89')
rr(35,156,1730,94,'#E8F2FF','#BBD3F1',18,2)
text(62,169,'解析対象37人  ≠  8,274件の介入判断',36,'#194B82',True)
text(63,219,'1人について1日最大5回、6週間にわたり観測  |  37人は解析対象数、8,274件はREADME記載の総判断時点数',18,'#526C8C')
text(35,267,'1｜研究チームが公開する4つのCSV',30,'#102C53',True)
items=[
 ('主役','suggestions.csv','介入判断・提案・歩数','8,274行 × 86列（README）'),
 ('参考','users.csv','属性・開始/終了アンケート','当面は取り込まない'),
 ('参考','jbsteps.csv','Jawboneの時系列歩数','当面は取り込まない'),
 ('参考','gfsteps.csv','Google Fitの時系列歩数','当面は取り込まない')]
rowitems(items,316,['#1679BE','#516A89','#516A89','#516A89'])
text(35,552,'2｜suggestions.csv の最小候補（公式Wikiで列名確認）',29,'#102C53',True)
nodes=[('参加者','user.index'),('判断時点','decision.index'),('介入可能性','avail'),('抽選・送信','is.randomized / send'),('30分の結果','jbsteps30.zero')]
positions=[38,379,720,1061,1402]
for i,(main,sub) in enumerate(nodes):
 x=positions[i]; rr(x,608,304,114,'#FFFFFF','#7FA6CE',16,2)
 text(x+14,622,main,22,'#173C65',True)
 text(x+14,665,sub,18,'#4277A8')
 if i<4:
  d.line((x+306,663,x+337,663),fill='#238BD8',width=5)
  d.polygon([(x+338,663),(x+328,655),(x+328,671)],fill='#238BD8')
rr(36,750,838,168,'#E9F7F0','#B8DDCA',18,2)
rr(890,750,875,168,'#FFF1EE','#F4CBC3',18,2)
text(60,767,'保存してよい：出典・メタデータ',27,'#176B4F',True)
text(60,817,'URL、列の名前、ライセンス、版、集計値',21,'#245B4E')
text(60,855,'必要最小限・帰属表示・原文との照合',19,'#527369')
text(912,767,'生データはHOLD：個人情報を守る',27,'#A83E38',True)
text(912,817,'参加者の行、正確な場所、活動の時系列',21,'#8F4D49')
text(912,855,'GitHub／ブログ／共有クラウドに再配布しない',19,'#945651')
rr(35,940,1730,92,'#10294D','#10294D',14,2)
text(59,951,'NEXT  H002：固定commitから読み取り専用取得 → SHA256 → 実ヘッダーと行数の検証',24,'#FFFFFF',True)
text(60,994,'要注意：READMEとWikiの列数に差があり、元の解析Rコードとも名称が異なる。現時点で再現できたと主張しない。',18,'#C6D9EF')
png=out/'2026-10-20-H001-HeartSteps-Data-Map-JA.png';im.save(png,optimize=True)
mermaid='''flowchart LR
  A["37人の解析対象者"] --> B["suggestions.csv / 8,274判断時点 / README報告"]
  B --> C["user.index と decision.index"]
  C --> D["avail：介入可能性"]
  D --> E["is.randomized：抽選対象 / send：送信"]
  E --> F["jbsteps30 / jbsteps30.zero：30分歩数"]
  B -.-> G["users.csv：属性 / 初回は不使用"]
  B -.-> H["jbsteps.csv と gfsteps.csv：分単位歩数 / 初回は不使用"]
  E --> I{"個人の行データを共有しない"}
  I --> J["H002：read-only + SHA256 + 生CSVヘッダー検証"]
'''
(out/'2026-10-20-H001-HeartSteps-Data-Map-JA.mmd').write_text(mermaid,encoding='utf8')
# PDF exact educational 2-page using ReportLab and original art
pdf=out/'2026-10-20-H001-HeartSteps-Data-Audit-JA.pdf'
pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
c=canvas.Canvas(str(pdf),pagesize=landscape(A4));cw,ch=landscape(A4)
c.setTitle('Manager H001 - HeartSteps source, schema and privacy audit')
c.drawImage(ImageReader(im),0,0,width=cw,height=ch,mask='auto')
c.showPage()
# second page
c.setFillColorRGB(.97,.98,1);c.rect(0,0,cw,ch,stroke=0,fill=1)
def block(x,y,title,lines,width=366):
 c.setFillColorRGB(.07,.18,.34);c.setFont('HeiseiKakuGo-W5',13);c.drawString(x,y,title)
 c.setFillColorRGB(.20,.27,.38);c.setFont('HeiseiKakuGo-W5',10)
 yy=y-25
 for ln in lines:
  c.drawString(x,yy,ln)
  yy-=19
 return yy
block(38,555,'H001: この資料が確定したこと',[
 '研究チームのGitHubには4種類のCSVがある。',
 '最初の候補は suggestions.csv のメタデータのみ。',
 '論文の37人と総8,274時点は異なる分母である。',
 '公開リポジトリのライセンスは CC BY 4.0。',
 '個別参加者の生データは本資料に含めていない。',
],355)
block(432,555,'まだ確定していないこと',[
 'users.csvの列数: README 117 / Wiki 120',
 'jbsteps.csvの列数: README 10 / Wiki 11',
 'gfsteps.csvの列数: README 7 / Wiki 8',
 '元Rコードの user / study.day.nogap とCSV列の対応',
 '実験解析に使う6,061件へのフィルタ',
],370)
block(38,369,'H002で確認する作業',[
 '1. 固定commitからCSVを読み取り専用で取得',
 '2. SHA256・行数・実際のヘッダーを記録',
 '3. 抽選 / 送信 / 介入可能の意味を再確認',
 '4. 欠測値と真のゼロ・補完値を区別する',
 '5. 生データを公共GitHub・クラウドへアップロードしない',
],745)
block(38,176,'一次出典',[
 'GitHub: https://github.com/klasnja/HeartStepsV1',
 'Column Wiki: https://github.com/klasnja/HeartStepsV1/wiki/Documentation-for-suggestions.csv',
 'Trial: https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/',
 'Source-anchored note: docs/research/heartsteps/H001_PUBLIC_DATA_REVIEW_JA.md',
],760)
c.setFont('HeiseiKakuGo-W5',9);c.setFillColorRGB(.43,.49,.6);c.drawRightString(cw-28,18,'Manager - learning artifact / no field impact demonstrated')
c.save()
print(str(png),png.stat().st_size, 'pdf',pdf.stat().st_size)