"""Optional illustration renderer for the Phase 02 educational notes.

Requires Pillow to reproduce images, but does NOT affect Manager's no-dependency
runtime and is not imported by manager_core. Every figure is synthetic.
"""
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import math

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/visuals'
OUT.mkdir(parents=True,exist_ok=True)
FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
BOLD='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
NAVY='#152D51'; BLUE='#2467B8'; BLUE2='#EAF3FD'; WHITE='#FFFFFF'; INK='#1D2A3D'; MUTED='#64748B'; TEAL='#087A73'; GREEN='#E5F7EF'; RED='#BB3250'; PINK='#FCEBF0'; AMBER='#FFF5DC'; GREY='#E9EEF5'

def f(size,bold=False): return ImageFont.truetype(BOLD if bold else FONT,size)

def page(title,subtitle,w=2700,h=1700):
 im=Image.new('RGB',(w,h),'#F7FAFF');d=ImageDraw.Draw(im)
 d.rounded_rectangle((35,26,w-35,h-30),radius=36,fill=WHITE,outline='#DCE6F2',width=2)
 d.text((95,60),title,font=f(62,True),fill=NAVY)
 d.text((97,153),subtitle,font=f(30),fill=MUTED)
 d.line([(96,207),(w-95,207)],fill=GREY,width=3)
 return im,d

def rounded(d,x0,y0,x1,y1,fill,stroke='#C9D6E5',radius=24):d.rounded_rectangle((x0,y0,x1,y1),radius=radius,fill=fill,outline=stroke,width=2)

def textwrap(d,text,x,y,maxwidth,font,fill=INK,leading=1.35):
 buf='';yy=y
 for para in text.split('\n'):
  if not para:
   yy+=int(font.size*leading*.6);continue
  line=''
  for ch in para:
   trial=line+ch
   if d.textbbox((0,0),trial,font=font)[2]>maxwidth and line:
    d.text((x,yy),line,font=font,fill=fill)
    yy+=int(font.size*leading);line=ch
   else: line=trial
  if line:
   d.text((x,yy),line,font=font,fill=fill);yy+=int(font.size*leading)
 return yy

def header(d,label,x,y,w,fill=BLUE):
 d.rounded_rectangle((x,y,x+114,y+51),radius=15,fill=fill)
 d.text((x+17,y+6),label,font=f(29,True),fill=WHITE)

steps=[
('L001','条件付き確率','ある状況Xで、行動Yが起きる確率を計算','観測確率 ≠ 介入の効果'),
('L002','予測誤差','TVD・Brier scoreで予測と結果のズレを測る','低誤差 ≠ 因果の予測'),
('L003','確率の校正','70%と予測した群で約70%起きるか確認','予測校正 ≠ 個人識別'),
('L004','介入設計','判断時点・選択肢・条件・決定規則を定義','NO_ACTIONを含める'),
('L005','因果DAG','共通原因Uにより相関が生まれる仕組み','P(Y|X) ≠ P(Y|do(X))'),
('L006','潜在結果','Y(0),Y(1)：現実では一方しか観測不可','同じ対象の両未来を知ったふりをしない'),
('L007','無作為化','割付で選択バイアスを抑えて群間比較','欠測・干渉などは別問題'),
('L008','微小無作為化','介入可能な時点で繰り返し選択を割り付ける','介入不可 ≠ 無介入比較群'),
('L009','測定の時間窓','30分の歩数と長期の健康改善を区別','短期成果 ≠ 長期的な便益'),
('L010','干渉・波及','他の場所への悪影響や運営費も計上','一地点の増加 ≠ 社会全体の純増'),
('L011','意思決定方法','Bandit, MDP, オフポリシーの前提を学ぶ','割付確率・supportが不可欠'),
('L012','成果の階層','P0研究 → P5複数領域での効果再現','便益と因果を証明したふりをしない'),
]

im,d=page('Manager — Phase 02 完了までの全12段階','行動予測 → 介入設計 → 因果評価。 12の土台を、すべて独立した小さな教材で確認。')
for i,(sid,name,desc,caution) in enumerate(steps):
 col=i%2;row=i//2
 x=100+col*1260;y=238+row*216
 rounded(d,x,y,x+1194,y+199,'#EAF3FD' if i<3 else '#F1F8F7' if i<8 else '#FFF7E8')
 rounded(d,x+16,y+19,x+135,y+72,BLUE if i<3 else TEAL if i<8 else '#9E680C',radius=13)
 d.text((x+27,y+25),sid,font=f(30,True),fill=WHITE)
 d.text((x+157,y+17),name,font=f(40,True),fill=NAVY)
 textwrap(d,desc,x+35,y+85,1120,f(27),INK)
 d.text((x+35,y+150),'注意：'+caution,font=f(24),fill=RED)
rounded(d,100,1538,2594,1644,NAVY,stroke=NAVY)
d.text((138,1563),'現在地：Phase 02 のコード理解とテスト。実世界への介入・受益の実証は未実施。',font=f(32,True),fill=WHITE)
im.save(OUT/'2026-10-20-phase02-roadmap-JA.png',optimize=True)

im2,d=page('Phase 02 — 4つの重要なメカニズム','すべて架空の計算例。一次資料の考え方を理解するための図であり、Managerの実績ではない。',w=2700,h=1810)
regions=[(95,237,1330,967),(1370,237,2603,967),(95,1000,1330,1720),(1370,1000,2603,1720)]
for i,(x0,y0,x1,y1) in enumerate(regions):rounded(d,x0,y0,x1,y1,[BLUE2,AMBER,GREEN,PINK][i])
# 1 calibration scatter
x0,y0,_,_=regions[0]
d.text((x0+36,y0+25),'L003：予測の校正',font=f(41,True),fill=NAVY)
d.text((x0+38,y0+90),'予測した確率と実際の頻度を比較',font=f(27),fill=MUTED)
gx0,gy0,gx1,gy1=x0+190,y0+190,x0+940,y0+550
for p in [0,.25,.5,.75,1.]:
 xx=gx0+(gx1-gx0)*p; yy=gy1-(gy1-gy0)*p
 d.line((xx,gy0,xx,gy1),fill='#D0DEEC',width=2)
 d.line((gx0,yy,gx1,yy),fill='#D0DEEC',width=2)
 d.text((xx-25,gy1+10),f'{int(p*100)}%',font=f(19),fill=MUTED)
d.line((gx0,gy1,gx1,gy0),fill=BLUE,width=4)
for pr,real in [(.5,.5),(.7,.7),(.9,.6)]:
 xx=gx0+(gx1-gx0)*pr; yy=gy1-(gy1-gy0)*real
 d.ellipse((xx-18,yy-18,xx+18,yy+18),fill=TEAL if pr==real else RED,outline='white',width=3)
 d.text((xx+18,yy-40),f'{int(pr*100)}→{int(real*100)}',font=f(21,True),fill=NAVY)
d.text((gx0+150,gy1+65),'横軸：予測確率　／　縦軸：実測頻度',font=f(24),fill=NAVY)
d.text((x0+35,y0+638),'過信した90%予測は、実際には60%しか起きない。',font=f(29,True),fill=RED)
# 2 dag
x0,y0,_,_=regions[1]
d.text((x0+32,y0+25),'L005〜L007：相関と因果',font=f(41,True),fill=NAVY)
d.text((x0+36,y0+91),'U（意欲）が時刻と歩行の両方に影響',font=f(27),fill=MUTED)
def node(cx,cy,label,color):
 d.rounded_rectangle((cx-145,cy-48,cx+145,cy+48),radius=20,fill=color,outline='#B5C8D6',width=2)
 bb=d.textbbox((0,0),label,font=f(30,True));d.text((cx-(bb[2]-bb[0])/2,cy-26),label,font=f(30,True),fill=NAVY)
def arrow(x1,y1,x2,y2,color=BLUE):
 d.line((x1,y1,x2,y2),fill=color,width=8)
 a=math.atan2(y2-y1,x2-x1)
 points=[(x2,y2),(x2-29*math.cos(a-.52),y2-29*math.sin(a-.52)),(x2-29*math.cos(a+.52),y2-29*math.sin(a+.52))]
 d.polygon(points,fill=color)
node(x0+300,y0+260,'U：運動意欲','#E0EDF9')
node(x0+820,y0+170,'X：時刻','#FDF9E7')
node(x0+820,y0+385,'Y：歩行','#FDF9E7')
arrow(x0+460,y0+225,x0+655,y0+182)
arrow(x0+460,y0+289,x0+655,y0+370)
d.text((x0+55,y0+505),'観測上：朝90% － 夕方10% ＝ 80pt',font=f(30,True),fill=NAVY)
d.text((x0+55,y0+566),'しかし「時刻だけ」を変更する因果効果＝0',font=f(29,True),fill=RED)
d.text((x0+55,y0+643),'割付実験が必要。予測の一致だけでは証明できない。',font=f(25),fill=MUTED)
# 3 MRT time sequence
x0,y0,_,_=regions[2]
d.text((x0+35,y0+25),'L008〜L009：繰り返し判断と時間窓',font=f(38,True),fill=NAVY)
d.text((x0+38,y0+93),'研究の構造を模した架空の1日5時点',font=f(26),fill=MUTED)
for i,available in enumerate([True,False,True,True,True]):
 cx=x0+155+i*213;cy=y0+250
 color=TEAL if available else '#A4AEBB'
 d.ellipse((cx-57,cy-57,cx+57,cy+57),fill=color)
 d.text((cx-13,cy-29),str(i+1),font=f(40,True),fill=WHITE)
 if i<4:arrow(cx+65,cy,cx+142,cy,BLUE)
 label='利用可能' if available else '不可'
 d.text((cx-67,cy+77),label,font=f(22,True),fill=color)
d.text((x0+50,y0+427),'利用可能：提案なし40%／歩行30%／座りすぎ防止30%',font=f(29),fill=NAVY)
d.text((x0+50,y0+504),'介入不能な時点は「提案なし群」に含めない。',font=f(30,True),fill=RED)
d.text((x0+50,y0+579),'近接アウトカム：介入後30分の歩数',font=f(28),fill=INK)
d.text((x0+50,y0+635),'≠ 長期の健康が改善した証拠',font=f(27,True),fill=RED)
# 4 Spillover & P ladder
x0,y0,_,_=regions[3]
d.text((x0+34,y0+25),'L010〜L012：純便益と実証の段階',font=f(38,True),fill=NAVY)
d.text((x0+35,y0+97),'一つの支援先が増えても、全体では損失の可能性',font=f(26),fill=MUTED)
vals=[('+100 支援先Aの増加',GREEN,TEAL),('-90 他の支援先の減少',PINK,RED),('-20 介入運営費',PINK,RED)]
for i,(txt,bg,fg) in enumerate(vals):
 yy=y0+173+i*106
 rounded(d,x0+42,yy,x0+1155,yy+82,bg,stroke='#D2DCE9',radius=16)
 d.text((x0+68,yy+21),txt,font=f(33,True),fill=fg)
d.text((x0+50,y0+516),'全体の追加資源 = -10',font=f(44,True),fill=RED)
d.text((x0+48,y0+598),'P0 研究 → P1 実行 → P2 状態変化',font=f(28),fill=NAVY)
d.text((x0+48,y0+642),'→ P3 便益 → P4 因果 → P5 再現',font=f(27,True),fill=TEAL)
im2.save(OUT/'2026-10-20-phase02-mechanisms-JA.png',optimize=True)

# Native PDF combines the same exact, code-grounded raster panels; no font substitution.
with Image.open(OUT/'2026-10-20-phase02-roadmap-JA.png') as p1,Image.open(OUT/'2026-10-20-phase02-mechanisms-JA.png') as p2:
 p1.save(OUT/'2026-10-20-phase02-learning-JA.pdf','PDF',resolution=180,save_all=True,append_images=[p2])
print('Created',[(p.name,p.stat().st_size) for p in OUT.glob('2026-10-20-phase02-*')])
