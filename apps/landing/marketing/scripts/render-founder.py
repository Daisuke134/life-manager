"""Render the public profile and CV from public-only facts; never read application files.
Run from any directory with Python 3 + reportlab, then run the marketing tests.
"""
from pathlib import Path
from html import escape
import json, hashlib
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
P=Path(__file__).resolve().parent.parent
data=json.loads((P/'content/founder.json').read_text())
E=escape
for locale, filename, home, alternate in [('en','about.html','/en','/about/ja'),('ja','about-ja.html','/ja','/about')]:
    d=data[locale];ja=locale=='ja'; route='/about/ja' if ja else '/about'
    title='Daisuke Narita | '+d['role']; description=d['intro']
    body=''.join('<section class="section"><h2>'+E(s['title'])+'</h2><div class="founder-items">'+''.join('<article><h3>'+E(i['title'])+'</h3><p>'+E(i['text'])+'</p>'+('<div class="founder-links">'+' '.join('<a href="'+E(url,quote=True)+'">'+E(label)+'</a>' for label,url in i.get('links',[]))+'</div>' if i.get('links') else '')+'</article>' for i in s['items'])+'</div></section>' for s in d['sections'])
    html=f'''<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)}</title><meta name="description" content="{E(description,quote=True)}"><link rel="canonical" href="https://aniccaai.com{route}"><link rel="alternate" hreflang="en" href="https://aniccaai.com/about"><link rel="alternate" hreflang="ja" href="https://aniccaai.com/about/ja"><link rel="alternate" hreflang="x-default" href="https://aniccaai.com/about"><meta property="og:title" content="{E(title,quote=True)}"><meta property="og:description" content="{E(description,quote=True)}"><meta property="og:url" content="https://aniccaai.com{route}"><meta property="og:type" content="profile"><link rel="stylesheet" href="/assets/manager-site/styles.css"></head>
<body class="founder-profile"><nav aria-label="{'メインナビゲーション' if ja else 'Main navigation'}"><a class="brand" href="{home}">Anicca.</a><div class="navlinks"><a href="/blog">{'記事' if ja else 'Articles'}</a><a href="{'/dais/ja' if ja else '/dais'}">{'製品' if ja else 'Products'}</a><a href="{route}" aria-current="page">{'創業者' if ja else 'About'}</a><a href="{alternate}" lang="{'en' if ja else 'ja'}">{'EN' if ja else 'JA'}</a></div></nav>
<main class="wrap"><header class="founder-header"><div class="eyebrow">{E(d['role'])}</div><h1>Daisuke Narita</h1><p class="lead">{E(d['intro'])}</p><div class="actions"><a class="btn" href="/cv.pdf">{'履歴書 PDF（英語）' if ja else 'Download résumé (PDF)'}</a><a href="mailto:{data['email']}">{'お問い合わせ' if ja else 'Contact me'}</a></div><p class="subtle">{'更新日' if ja else 'Updated'} {data['updated']} · {'事業・研究に関するご連絡' if ja else 'Business and research inquiries'}: <a href="mailto:{data['email']}">{data['email']}</a></p></header>
<p class="founder-ownership">{E(d['ownership'])}</p>{body}
<section class="section"><h2>{'一緒に取り組むご相談' if ja else 'Get in touch'}</h2><p>{'プロダクト、研究、協業については、事業用の窓口にご連絡ください。' if ja else 'For conversations about products, research or collaboration, use my public business contact.'}</p><a href="mailto:{data['email']}">{data['email']}</a><div class="founder-links"><a href="https://github.com/Daisuke134">GitHub</a><a href="https://jp.linkedin.com/in/daisuke-narita">LinkedIn</a><a href="/cv.pdf">{'履歴書 PDF（英語）' if ja else 'Résumé PDF'}</a></div></section></main><footer><div class="bottom"><a href="{home}">Anicca</a><span>© 2026 Anicca · Daisuke Narita</span><a href="{'/privacy/ja' if ja else '/privacy/en'}">{'プライバシー' if ja else 'Privacy'}</a></div></footer></body></html>\n'''
    (P/'pages'/filename).write_text(html)
# Deterministic public PDF. The JSON is the shared factual input, not a private application resume.
font=Path('/usr/share/fonts/truetype/liberation')
pdfmetrics.registerFont(TTFont('PublicCV',str(font/'LiberationSans-Regular.ttf')))
pdfmetrics.registerFont(TTFont('PublicCV-Bold',str(font/'LiberationSans-Bold.ttf')))
pdfmetrics.registerFontFamily('PublicCV',normal='PublicCV',bold='PublicCV-Bold')
styles={k:ParagraphStyle(k,fontName='PublicCV-Bold' if k in ['name','section','title'] else 'PublicCV',fontSize=size,leading=leading,textColor=HexColor('#173d32'),spaceAfter=space) for k,size,leading,space in [('name',22,25,5),('role',10,13,6),('small',8,10,4),('body',9,11.5,4),('section',12,15,6),('title',10,12,2)]}
story=[]
def para(text,kind='body'):
    p=Paragraph(text,styles[kind]);p.keepWithNext=kind in ['name','section','title'];story.append(p)
d=data['en'];para(E(data['name']),'name');para(E(d['role']),'role')
para(f'<link href="mailto:{data["email"]}">{data["email"]}</link> | <link href="https://aniccaai.com/about">aniccaai.com/about</link> | Updated {data["updated"]}','small')
para(E(d['intro']));para(E(d['ownership']),'small')
for index,section in enumerate(d['sections']):
    if index==1:story.append(PageBreak())
    story.append(Spacer(1,3));para(E(section['title']),'section')
    for item in section['items']:
        para(E(item['title']),'title');para(E(item['text']))
        if item.get('links'):para(' | '.join('<link href="'+E(url,quote=True)+'">'+E(label)+'</link>' for label,url in item['links']),'small')
def page(canvas,doc):
    canvas.setFont('PublicCV',8);canvas.setFillColor(HexColor('#56645f'));canvas.drawString(40,25,'Daisuke Narita | Public professional profile');canvas.drawRightString(572,25,str(doc.page))
SimpleDocTemplate(str(P/'assets/public-resume.pdf'),pagesize=(612,792),leftMargin=40,rightMargin=40,topMargin=28,bottomMargin=36,title='Daisuke Narita | Public Resume',author='Daisuke Narita',invariant=1).build(story,onFirstPage=page,onLaterPages=page)
manifest_path=P/'route-manifest.json';manifest=json.loads(manifest_path.read_text())
for source,route,export in [('pages/about.html','/about','about.html'),('pages/about-ja.html','/about/ja','about/ja.html'),('assets/public-resume.pdf','/cv.pdf','cv.pdf')]:
    if not any(f['export_path']==export for f in manifest['files']):manifest['files'].append({'source':source,'public_route':route,'export_path':export})
for f in manifest['files']:f['sha256']=hashlib.sha256((P/f['source']).read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
