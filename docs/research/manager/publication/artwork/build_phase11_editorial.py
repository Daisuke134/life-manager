#!/usr/bin/env python3
"""P11 original figures and verifiable bilingual publication package. No network."""
from pathlib import Path
from hashlib import sha256
from io import BytesIO
import json
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[5]
SRC=ROOT/"docs/research/manager/articles"
PKG=ROOT/"docs/research/manager/publication/2026-10-19"
COLORS={"bg":"#071421","panel":"#142C40","ink":"#F1F7FD","dim":"#ABC1CF","mint":"#39E3D0","amber":"#FFC777","red":"#F68B8B","blue":"#85B5FF"}
TITLES=[
("1","offline-rl-ope","Evaluate the policy, not the nudge"),
("2","social-simulation","Social correlation is not contagion"),
("3","multi-agent-cognition","More agents is not always better"),
("4","behavior-foundation-model","Shared models can transfer negatively"),
("5","domain-transfer-finance","The best backtest can be noise")]

def font(sz):
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/System/Library/Fonts/Helvetica.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:return ImageFont.truetype(path,sz)
        except OSError:continue
    return ImageFont.load_default()

def text(d,x,y,t,sz=30,col="ink"):
    d.text((x,y),t,font=font(sz),fill=COLORS[col])

def card(d,x1,y1,x2,y2):
    d.rounded_rectangle((x1,y1,x2,y2),radius=26,fill=COLORS["panel"])

def circ(d,x,y,col,rad=26):
    d.ellipse((x-rad,y-rad,x+rad,y+rad),fill=COLORS[col],outline=COLORS["ink"],width=3)

def line(d,x1,y1,x2,y2,col="dim",width=5):
    d.line((x1,y1,x2,y2),fill=COLORS[col],width=width)

def make_image(id,title):
    im=Image.new("RGB",(1600,900),COLORS["bg"]);d=ImageDraw.Draw(im)
    text(d,100,63,"ANICCA / MANAGER RESEARCH",28,"mint")
    text(d,100,115,"PHASE 11-"+id+"    ·    SYNTHETIC EDUCATIONAL FIGURE",26,"dim")
    text(d,100,184,title,53)
    if id=="1":
        for x in (80,590,1100): card(d,x,305,x+420,656)
        text(d,120,345,"Logged policy",40,"blue")
        text(d,120,433,"Actions & propensity",28,"dim")
        text(d,625,345,"OPE estimates",40,"mint")
        for i,msg in enumerate(["Oracle  0.43500","IPS      0.43551","DR       0.43539"]):
            text(d,625,433+61*i,msg,30)
        text(d,1130,345,"Evidence",40,"amber")
        text(d,1130,433,"No user outcomes",29)
        text(d,1130,490,"No live policy",29)
        line(d,501,482,577,482,"mint",8);line(d,1012,482,1087,482,"mint",8)
    elif id=="2":
        card(d,80,300,1520,650)
        for origin,color in ((240,"mint"),(680,"blue")):
            coords=[(origin,443),(origin+110,378),(origin+110,510)]
            for i in range(3):
                for j in range(i+1,3):line(d,*coords[i],*coords[j])
            for x,y in coords:circ(d,x,y,color)
        text(d,1055,358,"100% linked",43,"mint")
        text(d,1055,435,"0 causal effect",40,"red")
        text(d,200,565,"Type A ties",29)
        text(d,615,565,"Type B ties",29)
    elif id=="3":
        for x in (90,820):card(d,x,303,x+675,649)
        text(d,140,353,"Single agent",42,"blue")
        text(d,140,459,"Time: 120",47)
        text(d,862,353,"Two workers",42,"mint")
        text(d,862,445,"90% parallel: 74",37)
        text(d,862,519,"10% parallel: 122",34,"amber")
    elif id=="4":
        card(d,75,292,1525,695)
        groups=[("Domain A",.677,.395),("Domain B",.717,.433)]
        for i,(label,single,specific) in enumerate(groups):
            x=335+640*i
            for dx,value,col in ((0,single,"red"),(162,specific,"mint")):
                height=int(value/.85*235)
                d.rectangle((x+dx,645-height,x+dx+115,645),fill=COLORS[col])
                text(d,x+dx,600-height,f"{value:.3f}",31)
            text(d,x-12,659,label,28)
        text(d,400,305,"Shared",26,"red");text(d,615,305,"Specialist",26,"mint")
    else:
        card(d,70,304,1530,650)
        cards=[("BEST TRAIN","+0.537","mint"),("HELD-OUT","-0.0365","amber"),
               ("NET OF COST","-0.0665","red")]
        for i,(label,value,col) in enumerate(cards):
            x=120+i*475
            text(d,x,360,label,31,"dim")
            text(d,x,462,value,52,col)
            if i<2: line(d,x+418,348,x+418,590,"dim",2)
        text(d,120,606,"150 null strategies. All with zero true expected edge.",26)
    line(d,100,785,1500,785,"dim",2)
    text(d,100,810,"This is an original diagram; all performance figures are synthetic.",25,"dim")
    out=BytesIO();im.save(out,format="PNG",optimize=True);return out.getvalue()

def main():
    meta={
      "1":("Before an AI Sends Another Nudge, Ask What the Logs Can Actually Prove",
           "AIに「通知すべきか」を教える前に、過去のログで確かめる",
           "Off-policy evaluation, propensities, IPS/DR and the boundary between prediction and intervention."),
      "2":("If a Million AI Agents Talk to Each Other, Have We Predicted Society?",
           "100万人のAIが会話したら、社会を予測したことになるのか",
           "Social simulation, homophily versus contagion, and network interference."),
      "3":("When Does a Team of AI Agents Actually Beat One Agent?",
           "AIエージェントを増やせば、チームは賢くなるのか",
           "Distributed cognition, multi-agent coordination cost and correlated errors."),
      "4":("A Bigger Language Model Is Not Automatically a Better Model of Human Behavior",
           "人間を理解するFoundation Modelは、巨大であれば十分なのか",
           "Centaur, BehaviorBench and negative transfer in shared behavioral models."),
      "5":("The Best Backtest Can Be the Worst Reason to Trust a Strategy",
           "過去の勝者は、なぜ未来の勝者ではないのか",
           "Transportability, domain shift, backtest overfitting and held-out evaluation.")
    }
    pkg=json.loads((PKG/"manifest.json").read_text("utf8"))
    before=(len(pkg["articles"]),len(pkg["media"]))
    image_links={}
    for id,topic,title in TITLES:
        data=make_image(id,title);h=sha256(data).hexdigest()
        medpath=f"media/{h}.png"
        (PKG/medpath).write_bytes(data)
        url=f"https://aniccaai.com/blog/manager/{medpath}"
        image_links[id]=url
        pkg["media"].append({"package_path":medpath,"sha256":h,"public_url":url})
    for id,topic,title in TITLES:
        for lang in ("ja","en"):
            filename=SRC/f"2026-11-07-p11-{id}-{topic}-{lang}.md"
            src=filename.read_text("utf8")
            marker="{{P11_"+id+"_IMAGE}}"
            if marker not in src:raise ValueError(f"Placeholder missing: {filename}")
            src=src.replace(marker,image_links[id]);filename.write_text(src,"utf8")
            digest=sha256(src.encode()).hexdigest()
            slug=f"manager-p11-{id}-{topic}-{lang}"
            rel=f"{lang}/{slug}.md"
            packaged=PKG/rel;packaged.parent.mkdir(parents=True,exist_ok=True)
            packaged.write_text(src,"utf8")
            n_references=sum(1 for l in src.splitlines() if l.startswith("- ["))
            pkg["articles"].append({
                "source":filename.relative_to(ROOT).as_posix(),"source_sha256":digest,
                "slug":slug,"language":lang,
                "title":meta[id][1] if lang=="ja" else meta[id][0],
                "package_path":rel,"canonical_url":f"https://aniccaai.com/blog/{slug}",
                "date":"2026-11-07","project":"Manager","lang":lang,
                "n_papers_cited":n_references,"word_count":len(src.split()),
                "character_count":len(src),"markdown":src,"sha256":digest,
                "description":meta[id][2],
                "series_order":200+int(id) if lang=="ja" else 120+int(id)
            })
    (PKG/"manifest.json").write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+"\n","utf8")
    print(json.dumps({"before":before,"after":(len(pkg["articles"]),len(pkg["media"])),
                       "figures":image_links},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
