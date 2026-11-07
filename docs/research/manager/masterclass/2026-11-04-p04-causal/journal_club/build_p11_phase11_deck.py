#!/usr/bin/env python3
"""Build 33 editable Japanese Phase 11 research slides with per-slide notes.

Source-grounded lectures and original illustrations; no copyrighted paper figures.
Standalone supplement. Existing 34-slide talk and 118+ research archives untouched.
"""
from __future__ import annotations
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
PACKAGE = ROOT / "docs/research/manager/publication/2026-10-19"
OUTPUT = HERE / "MANAGER_PHASE11_RESEARCH_JA.pptx"
NOTES = HERE / "SPEAKER_NOTES_PHASE11_JA.md"
NAVY = RGBColor(6,19,34)
CARD = RGBColor(18,39,58)
CARD2 = RGBColor(28,55,76)
WHITE = RGBColor(242,248,255)
MUTED = RGBColor(173,196,212)
TEAL = RGBColor(55,218,197)
AMBER = RGBColor(255,203,116)
BLUE = RGBColor(130,177,251)
RED = RGBColor(244,144,142)
FONT = "Hiragino Sans"
W, H = 13.333, 7.5
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(W), Inches(H)
contents = []

def rect(slide,x,y,w,h,color,rounding=True):
    shp=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rounding else MSO_SHAPE.RECTANGLE,
                               Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid();shp.fill.fore_color.rgb=color;shp.line.fill.background()
    return shp

def txt(slide, text, x,y,w,h,size=23,color=WHITE,bold=False,align=PP_ALIGN.LEFT):
    box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf=box.text_frame;tf.clear();tf.word_wrap=True
    p=tf.paragraphs[0];p.text=text;p.alignment=align
    p.font.name=FONT;p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=color
    return box

def base(section,index):
    slide=prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide,0,0,W,H,NAVY,False)
    txt(slide,"ANICCA  /  MANAGER RESEARCH",.58,.30,5.1,.34,12,TEAL,True)
    txt(slide,section,10.3,.31,2.25,.35,11,MUTED,True,PP_ALIGN.RIGHT)
    rect(slide,.56,7.09,12.22,.012,CARD2,False)
    txt(slide,"Phase 11  •  Research lecture / synthetic demos ≠ human efficacy",.6,7.13,9.4,.19,9,MUTED)
    txt(slide,f"{index:02d} / 33",11.55,7.11,.8,.24,10,TEAL,True,PP_ALIGN.RIGHT)
    return slide

def notes(slide,index,heading,body,source=""):
    value=f"{heading}\n\n{body}\n\n出典・参考：{source or 'P11講義原稿および完全合成実験'}\nこのスライドでの推論と実際の人間への因果効果を区別する。"
    slide.notes_slide.notes_text_frame.text=value
    contents.append(f"## Slide {index:02d}｜{heading}\n\n{value}\n")

def topic_slide(section,title,b1,b2,b3,formula,source,index,foot=None):
    s=base(section,index)
    txt(s,title,.72,.82,11.8,.8,29,WHITE,True)
    rect(s,.72,1.86,7.65,4.74,CARD)
    for i,line in enumerate((b1,b2,b3)):
        y=2.21+i*1.34
        rect(s,1.06,y+.06,.08,.64,TEAL,False)
        txt(s,line,1.33,y,6.65,.99,21,WHITE,False)
    rect(s,8.69,1.86,3.89,4.74,CARD2)
    txt(s,"KEY IDEA",9.03,2.28,2.8,.45,16,TEAL,True)
    txt(s,formula,9.02,3.01,3.2,2.6,19,WHITE,True)
    if foot:txt(s,foot,9.02,5.72,3.06,.5,11,AMBER)
    notes(s,index,title,f"説明：{b1}／{b2}／{b3}。\n数式・概念：{formula}。\n限界：{foot or 'データ・仮定・適用対象の条件を確認。'}",source)

def figure_slide(section,title,figidx,bullet1,bullet2,src,index):
    s=base(section,index)
    txt(s,title,.72,.83,11.84,.71,28,WHITE,True)
    path=None
    for file in (PACKAGE/"media").glob("*.png"):
        # decide from article manifest's embedded first original image
        article=next(a for a in json.loads((PACKAGE/"manifest.json").read_text())["articles"] if a["slug"].startswith(f"manager-p11-{figidx}-") and a["lang"]=="ja")
        if file.name in article["markdown"]:
            path=file;break
    if path is None:raise FileNotFoundError(figidx)
    s.shapes.add_picture(str(path),Inches(.8),Inches(1.76),width=Inches(8.1),height=Inches(4.55))
    rect(s,9.20,1.80,3.33,4.45,CARD)
    txt(s,bullet1,9.53,2.27,2.67,1.26,20,WHITE,True)
    txt(s,bullet2,9.53,4.07,2.60,1.5,16,MUTED)
    notes(s,index,title,f"図は自作であり論文図の転載ではない。\n{bullet1}\n{bullet2}\n全ての合成数値は架空である。",src)

n=1
s=base("P11 • OVERVIEW",n)
txt(s,"PHASE 11",.75,1.15,8.1,1.08,49,TEAL,True)
txt(s,"人間を予測するAIから\n未来を比較するAIへ",.78,2.38,11.3,2.20,39,WHITE,True)
txt(s,"Offline RL  •  Social Simulation  •  Distributed Cognition  •  Behavioral FM  •  Transfer",.82,5.34,11.5,.5,18,MUTED)
notes(s,n,"Phase 11｜研究講義","P11-1からP11-5まで。学習成果は論文と合成実装で保存。これは製品の実ユーザー有効性や独自行動FM完成の主張ではない。")
n+=1
s=base("P11 • ROADMAP",n)
txt(s,"P11-1〜5をつなぐ5つの問い",.72,.90,11.9,.7,32,WHITE,True)
stages=[
("01","どう選ぶ？","Offline RL / OPE"),
("02","人々はどう影響する？","Social Network / Interference"),
("03","誰が分担する？","Distributed Cognition"),
("04","何を共通化する？","Behavior Foundation Model"),
("05","未知でも通用する？","Domain Transfer")]
for j,(id,title,sub) in enumerate(stages):
    y=1.82+j*.87
    rect(s,.77,y,11.67,.71,CARD if j%2==0 else CARD2)
    txt(s,id,1.08,y+.16,.56,.32,18,TEAL,True)
    txt(s,title,1.83,y+.12,4.55,.42,22,WHITE,True)
    txt(s,sub,7.1,y+.18,4.8,.3,16,MUTED)
notes(s,n,"Phase 11の全5講義","全講義はモデルと実行の境界を跨ぐが、共通の規則は『予測≠介入効果≠独立検証された価値』。")
n+=1

PAPERS={
"P11-1":"Jiang & Li 2016 / CQL 2020 / MOPO 2020",
"P11-2":"Park 2023 / OASIS 2024 / AgentSociety 2025",
"P11-3":"Hutchins 1995 / Anthropic 2025 / Google 2026",
"P11-4":"Binz et al. Nature 2025 / BehaviorBench 2026",
"P11-5":"Arjovsky et al. 2019 / Bailey et al. 2015",
}
BATCH={
"P11-1":[
("予測と方策価値は違う","P(Y|X,A)は観測の予測。","P(Y|do(A))には介入の識別仮定が必要。","NO_ACTIONも有効な候補として扱う。","Predict ≠ Causal Effect"),
("MDPとBellman方程式","状態S、行動A、遷移P、報酬R、割引γ。","即時のクリックが長期の福祉改善とは限らない。","将来の負担や離脱も状態・評価対象に含める。","Q = E[R + γV(next)]"),
("Offline RLで何が難しい？","固定ログには選ばれなかった行動の結果がない。","Qの外挿がデータ外の行動を過大評価し得る。","CQL/MOPOは保守性・モデル不確実性を扱う。","No Support → No Claim"),
("OPEはログに存在する確率で評価","IPS: πe(a|x)/πb(a|x) の重み。","DR: outcome model と残差補正。","ESSが小さい場合やsupport欠落なら棄権。","IPS / SNIPS / DR"),
("固定乱数の架空20,000件","真の合成policy価値 0.435。","IPS 0.43551 / DR 0.43539。","人間の有効性・実通知の改善は一切未測定。","SYNTHETIC ONLY"),
("本当の研究の受入条件","割付と実配信を区別し、propensityを保存。","人単位の分割・欠測・事前停止を検査。","新しい方策は同意・独立比較を経てから評価。","Experiment ≠ Product")],
"P11-2":[
("個人は孤立していない","友人・家族・推薦・制度が行動に影響。","ネットワークG=(V,E)上の相互作用を記述。","社会的影響の因果と観測相関を区別。","Individual ≠ Society"),
("ABMとGenerative Agents","個体の記憶・規則・環境から集団を模擬。","Parkら2023の町では25体が相互作用。","自然な会話は未知集団での予測証拠ではない。","Believable ≠ Predictive"),
("OASIS / AgentSociety","SNSの投稿・推薦・つながりをモデル化。","1万〜100万規模の設計・模擬研究が公開。","分布・時間・文化・少数集団を外部検証する。","Scale ≠ Validity"),
("HomophilyとContagion","同類選好・共通曝露・因果的伝播は別。","見かけの友人間一致が100%でも因果影響0もあり得る。","ネットワークがあるとSUTVAが破れ得る。","Correlation ≠ Influence"),
("4ノードの合成構造方程式","近隣曝露率 e_i = treated neighbors / neighbors。","架空のaの期待値は0.20+0.30=0.50。","実世界のspillover推定ではない。","SYNTHETIC ONLY"),
("評価の多層性","個人NLL・集団TVD・ネットワーク統計。","拡散曲線・干渉・長期変化の別評価。","現実の因果実験を模擬出力に置き換えない。","Multi-Level Validation")],
"P11-3":[
("Distributed Cognition","認知は人・道具・記録・手順に分散。","Hutchins 1995の航海作業研究が理論の基礎。","AI同士の会話も「全体システム」で評価。","System > Individuals"),
("協調の4つの構造","Single / Central / Decentralized / Hierarchical。","通信経路は完全グラフn(n−1)/2。","10体で45ペア、スターでは9本。","Topology Matters"),
("AnthropicとGoogleの実測","並列化可能な研究はsubagentsで分担可能。","Anthropicはトークン増大を報告。","Googleは180構成で逐次タスクの悪化を報告。","More ≠ Better"),
("Amdahlと通信オーバーヘッド","並列率pと調整費が処理時間を決定。","12架空タスク、単体120。","2 worker: 並列90%=74、並列10%=122。","SYNTHETIC TIME"),
("共通エラーと独立監査","二体の誤りが独立ならp²。","完全相関なら同時誤りはpのまま。","Providerの公式readbackは別の証拠源。","Agreement ≠ Evidence"),
("Managerで役割をどう分ける？","Research / Analysis / Builder / Verifier。","権限はLLMの自己申告から付与しない。","成功率だけでなく総費用と誤りを評価。","Measure Per Work")],
"P11-4":[
("基盤モデルの定義","複数領域の人間の選択確率を学習。","人・研究・時間・文化の未知データで評価。","行動予測と介入の因果効果を分離。","Predictive Foundation"),
("Nature Centaurを元論文から","Psych-101：160実験・60,092人・1,068万選択。","Llama3.1 70BにQLoRA rank8。","回答tokenだけにloss。A100 80GBで約5日。","Real Paper Facts"),
("BehaviorBenchの設計","行動予測/戦略/特徴/知識の4能力。","個人精度と集団分布の一致を分離。","公開比較は実測条件と権利を明記。","Individual + Distribution"),
("LoRAと負の転移","W' = W + (α/r)BA。","複数タスクの勾配が競合する場合がある。","PCGrad/EWC等の効果は外部実験で検証。","Shared ≠ Superior"),
("相反する2領域の合成結果","Shared logloss: A .677 / B .717。","Specialist: A .395 / B .433。","学習済みManager BFMの結果ではない。","SYNTHETIC ONLY"),
("BFMの正しい受入条件","人物/研究/時期/文化/領域Holdout。","校正・OOD・棄権・負の転移を検査。","ライセンスと再配布権も別Gate。","Evidence & Rights")],
"P11-5":[
("Domain Shiftを分類","Covariate / Label / Concept / Temporal。","特徴の割合だけ変わるのか、規則自体が変わるのか。","領域移植に万能な補正はない。","P_train ≠ P_target"),
("Transportabilityの仮定","効果修飾因子を十分に観測する。","対象集団に重なりがある。","ATE_T = Σ CATE_S(z) P_T(z)。","Assumptions First"),
("架空の効果移植計算","元研究：A/B半数、効果 .30/.10→平均.20。","対象：A20%/B80%なら .14。","条件付き効果の移植可能性が必要。","SYNTHETIC .14"),
("金融でのBacktest Overfitting","大量の候補を試すと偶然の勝者が出る。","過去と未来を分けるだけでなく試行数も記録。","手数料・流動性・リスクを含む必要。","Best Past ≠ Future"),
("150の架空ゼロ技能戦略","過去最良+0.537、同戦略の未来−0.0365。","架空取引費後−0.0665。","実市場・投資利益・注文実行とは無関係。","SYNTHETIC ONLY"),
("他領域へ広げるGate","独立の未来期間・別母集団で評価。","選択したベンチマークをtestへ混ぜない。","規制・権限・資本リスクは別審査。","No Automatic Transfer")],
}

for section, items in BATCH.items():
    for j,(title,a,b,c,formula) in enumerate(items):
        if j==4:
            figure_slide(section,title,section[-1],a,b,PAPERS[section],n)
        else:
            topic_slide(section,title,a,b,c,formula,PAPERS[section],n,
                        "研究主張と合成例を混同しない")
        n+=1

s=base("P11 → P12",n)
txt(s,"Phase 11で得た重要な区別",.7,.9,12,.7,33,WHITE,True)
pairs=[
("予測","介入の因果効果"),("社会的相関","他者への波及"),
("AI同士の合意","独立した結果確認"),("共通モデル","専用モデル超え"),
("過去の高成績","未知環境への汎化")]
for i,(a,b) in enumerate(pairs):
    y=1.89+i*.88
    rect(s,.77,y,11.75,.68,CARD if i%2==0 else CARD2)
    txt(s,a,1.25,y+.13,4.35,.36,23,WHITE,True)
    txt(s,"≠",6.27,y+.13,.55,.36,27,RED,True,PP_ALIGN.CENTER)
    txt(s,b,7.25,y+.13,5,.38,23,TEAL,True)
notes(s,n,"Phase 11まとめ / 次はP12-1","P11-1〜5の5つの区別を確認。教材/38 tests/公開記事は証拠の種類を分けて報告する。次の正式学習はP12-1（第三者再現）。")

if n!=33:raise AssertionError(f"unexpected slide count {n}")
OUTPUT.parent.mkdir(parents=True,exist_ok=True)
prs.save(OUTPUT)
NOTES.write_text("# Phase 11｜全33枚・日本語発表ノート\n\n"+"\n".join(contents),encoding="utf8")
print("Phase 11 deck:",len(prs.slides),"slides;",OUTPUT)
