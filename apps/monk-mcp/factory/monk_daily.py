#!/usr/bin/env python3
"""Anicca Monk Factory (EN): ONE HeyGen Avatar IV video/day with the existing 'Wise Buddhist Monk' look,
posted via Postiz to TikTok @monk_anicca. Guardrails: 1 video/day (ledger), wallet check, no print of keys.
Usage: monk_daily.py [--dry] [--no-post] [--topic truth|breath|letgo|night|db|art]  (default: Shalev-playbook script for the weekday, ebook CTA on every video)"""
import json,sys,time,os,datetime,urllib.request,urllib.parse,subprocess,uuid
D=os.path.dirname(os.path.abspath(__file__)); S='/workspace/.secrets/'
HG=open(S+'heygen-credentials').read().split()[0]; PZ=open(S+'postiz').read().split()[0]
AVATAR='ce6ef33ff2d0484dabf8a13ce059bbe8'   # Wise Buddhist Monk (Oct 8/9 monk videos, Mac pack ebook-en-anicca-monk)
VOICE='8be9884ebd16499fbe0efb274e769ed5'    # Simon - Calm & Gentle
MONK_TIKTOK='cmo5rwq2p00twn10yrsdglng3'     # @monk_anicca (never the Anicca-app YouTube channels)
MAX_COST_PER_DAY=1.00  # Avatar IV ~0.5-0.8/video
MONK_IG='cmoopzaak04yop70y1yx1bwr1'          # Instagram @monk.mujo (instagram-standalone, video => Reel)
EBOOK_URL='https://aniccaai.com/monk?utm_source=tiktok&utm_medium=monk&utm_campaign=monk_daily&ct=monk_ebook'
TAGS='#buddhism #mindfulness #anxietyrelief #innerpeace'
def T(id,hook,body,cap,tag,url=EBOOK_URL): return dict(id=id,url=url,script=hook+' '+body,caption=hook+' '+cap+' '+TAGS+' '+tag)
# GROWTH-PLAN.md: hook (<=3s) -> struggle -> ONE teaching -> tiny action -> comment prompt. Ebook CTA only on ebook days.
BANK={
 'truth':[
  T('truth','You are not weak for feeling this.',"Anger, fear, grief. They feel permanent, but they are weather. Anicca means everything changes, including this. Right now, place a hand on your chest and take one slow breath. Tell me in the comments: what is weighing on you today?",'Everything changes, even this feeling.','#anicca'),
  T('truth','Your mind is not your enemy.',"It is only trying to protect you, and it is loud. You do not have to obey every thought. Notice it, name it, and let it pass like a cloud. Try that once today. Which thought is loudest for you?",'You do not have to obey every thought.','#anicca')],
 'breath':[T('breath','Stop doing this when you feel anxious.',"Stop fighting the feeling. Breathe in for four. Out for six. Do it five times, slowly. A longer exhale tells the body it is safe. Do it with me now, then comment: done.",'Breathe in 4, out 6. Five times.','#breathwork')],
 'letgo':[T('letgo','Three things to let go of today.',"One: the conversation you cannot change. Two: the opinion of people who do not know you. Three: the idea that you must be fine all the time. Choose one and release it now. Which one is yours?",'Let go of one today.','#innerpeace')],
 'night':[T('night','If your mind is loud tonight, listen.',"The day is over. Nothing more can be solved in this bed. Let each thought arrive, and let it leave. Breathe in four, out six. Tomorrow will bring its own light. Sleep well, friend.",'For the loud mind at night.','#sleep')],
 'ebook':[
  T('ebook','Nobody tells you this about a restless mind.',"You cannot out-think it. You can only practice a quiet moment, every day. I wrote a short guided reflection book called The Anicca Reset. Plain English, not medical advice. The link is in my bio.",'The Anicca Reset: short guided reflections on impermanence. One-time $10.99. Link in bio. Not medical advice.','#anicca'),
  T('ebook','One sentence that changed how I handle stress.',"This too shall change. That is anicca. In The Anicca Reset, I turn that one idea into short daily practices you can finish in five minutes. Link in my bio. Not medical advice.",'Five-minute daily reflections. Link in bio. Not medical advice.','#anicca')],
}
# weekday(): Mon=0 .. Sun=6
SCHEDULE=['truth','breath','ebook','letgo','night','ebook','truth']

# --- Grounded scripts (Dais 10/23): every script is drawn from Codex's monk DB + article, never invented.
DB_URL='https://aniccaai.com/data/ai-monk-avatar-database-2026.json'
ART_FILE=D+'/sources/article-en.json'   # cache of anicca-products apps/landing/data/research/ebook-publishing-ai-monk-economy-2026.json
ART_URL='https://aniccaai.com/blog/ebook-publishing-ai-monk-economy-2026'
import re
def _sents(t,n=3):
    t=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',t); t=re.sub(r'[*_`>#]','',t); t=' '.join(t.split())
    return ' '.join(re.split(r'(?<=[.!?])\s+',t)[:n])
def sources():
    try: db=api('GET',DB_URL,{'User-Agent':'monk-factory'}); json.dump(db,open(D+'/sources/db.json','w'))
    except Exception: db=json.load(open(D+'/sources/db.json'))
    md=json.load(open(ART_FILE))['markdown']
    secs=[(h.strip('# ').strip(),_sents(b)) for h,b in re.findall(r'^(#{2,3} .+)\n+([\s\S]*?)(?=^#{2,3} |\Z)',md,re.M)]
    secs=[x for x in secs if len(x[1])>80 and not x[0].lower().startswith(('sources','the open index'))]
    accs=[a for a in db['accounts'] if a.get('ai_status')=='reported' and a.get('ai_evidence')]
    return secs,accs
def grounded(d,ebook=False):
    secs,accs=sources(); i=d.toordinal()
    if ebook:
        return T('ebook','I am a monk made of light and code. Sit with me for one breath.',"Everything changes. That is anicca. In The Anicca Reset, I turn that one idea into five-minute daily reflections. Link in my bio. Not medical advice.",'The Anicca Reset: five-minute reflections on impermanence. Link in bio. Not medical advice.','#anicca')
    if i%2==0 and accs:
        a=accs[(i//2)%len(accs)]; ev=a['ai_evidence'][0]['summary']
        body=f"Let me tell you about {a['display_name']}. {ev} Notice how a calm face and a robe earn trust before a single word. Trust is a gift. Check the source before you give it. What do you look for in a teacher?"
        return T('db-'+a['id'],'Not every monk you see is human. Neither am I.',body,f"From the open AI Monk Database: aniccaai.com/ai-monk-database",'#aimonk')
    h,b=secs[(i//2)%len(secs)]
    return T('art-'+re.sub(r'\W+','-',h.lower())[:40],h if h.endswith(('?','.')) else h+'.',b+" Breathe in, and see it clearly. Tell me in the comments what you notice.",'From my field guide: '+ART_URL,'#aimonk')
# --- Shalev playbook (Yang Mun creator, X article 2026-04-09; sources/winning-hooks.json, AI Monk DB):
# pain (2s) -> flip/fix (3s) -> ONE teaching (20-40s) -> identity line (3s) -> soft ebook CTA (link in bio). Same voice always.
CTA="If you want the five-minute version for every day, it is in The Anicca Reset. Link in my bio."
def S(id,pain,flip,teach,identity,tag,cap):
    return dict(id='sh-'+id,url=EBOOK_URL,script=' '.join([pain,flip,teach,identity,CTA]),
                caption=f"{cap} The Anicca Reset, link in bio. Not medical advice. {TAGS} {tag}")
SHALEV=[  # weekday Mon..Sun; empathy-reframe and solution hooks, one teaching each
 S('overthink',"If you are going to overthink tonight,","then overthink the good things too.","Name one thing that went right today. Hold it for three breaths. The mind becomes what it keeps returning to.","The calm ones are not lucky. They just practice this first.",'#overthinking','Overthink the positive.'),
 S('sleep2min',"How to fall asleep in two minutes, even when your mind will not stop.","Do not fight the thoughts. Give them somewhere to go.","Breathe in for four, out for six. On each out-breath, silently say: not now. Five rounds. The longer exhale tells your body it is safe.","Peaceful sleepers are not empty-minded. They just stopped arguing with the mind.",'#sleep','Two-minute monk sleep method.'),
 S('weather',"You are not weak for feeling this.","This feeling is weather, not climate.","Put a hand on your chest and say: this too will change. That is anicca. Watch the feeling rise, peak and fall, like a wave.","Strong people still feel everything. They just know it passes.",'#anxietyrelief','Everything changes, even this.'),
 S('approval',"If you are tired of trying to be liked by everyone,","you can stop today.","Before you answer anyone, take one breath and ask: is this mine to carry? If not, put it down.","The free ones are not cold. They just stopped carrying what is not theirs.",'#innerpeace','Put down what is not yours.'),
 S('morning',"If you wake up already anxious,","give your first minute to yourself, not your phone.","Sit up, feel your feet on the floor, take three slow breaths and choose one word for today.","Calm days are not luck. They are decided in the first minute.",'#morningroutine','The first minute decides the day.'),
 S('anger',"If someone made you angry today,","you do not have to carry their fire home.","Holding anger is like holding a hot coal to throw at someone. You are the one who gets burned. Open your hand: breathe out slowly and let it cool.","Peaceful people still get angry. They just put the coal down sooner.",'#anger','Put the coal down.'),
 S('lonely',"If you feel alone even around people,","you are not broken. You are human.","Tonight, send one honest message to one person. Not perfect. Just true.","Connection is not found. It is practiced, one small message at a time.",'#loneliness','One honest message.'),
]
def pick(d,topic=None):
    if topic in ('db','art'): return grounded(d)
    if topic in BANK and topic!='ebook': return BANK[topic][0]
    return SHALEV[d.weekday()]
TOPICS=[x for v in BANK.values() for x in v]
def api(method,url,hdr,data=None):
    r=urllib.request.Request(url,data=data,method=method,headers=hdr)
    return json.load(urllib.request.urlopen(r,timeout=120))
def hg(method,path,body=None):
    return api(method,'https://api.heygen.com'+path,{'X-Api-Key':HG,'Content-Type':'application/json'},json.dumps(body).encode() if body else None)
def wallet(): return float(hg('GET','/v1/user/me')['data']['wallet']['remaining_balance'])
def main():
    a=sys.argv[1:]; today=datetime.date.today().isoformat()
    led=json.load(open(D+'/ledger.json')) if os.path.exists(D+'/ledger.json') else {}
    if '--post-ig-only' in a:  # usage: --post-ig-only DATE
        d=a[a.index('--post-ig-only')+1]; e=led[d]; t=pick(datetime.date.fromisoformat(d),e['topic'])
        global MONK_TIKTOK; return post_ig(e['captioned'],t,led,d)
    if today in led and '--force' not in a: print('already generated today',led[today]); return
    t=pick(datetime.date.today())
    if '--topic' in a: t=pick(datetime.date.today(),a[a.index('--topic')+1])
    print('topic',t['id'])
    if '--dry' in a: print(t['script']); print('CAPTION:',t['caption']); return
    before=wallet(); print('wallet before',before)
    if before<MAX_COST_PER_DAY: print('wallet too low'); return
    r=hg('POST','/v3/videos',{'type':'avatar','avatar_id':AVATAR,'script':t['script'],'voice_id':VOICE,
        'voice_settings':{'speed':0.9,'locale':'en-US'},'engine':{'type':'avatar_iv'},'aspect_ratio':'9:16','resolution':'1080p','title':'monk-'+today+'-'+t['id']})
    vid=(r.get('data') or r).get('video_id') or (r.get('data') or r).get('id')
    led[today]={'video_id':vid,'topic':t['id'],'wallet_before':before}; json.dump(led,open(D+'/ledger.json','w'),indent=1)
    for _ in range(90):
        time.sleep(10); v=hg('GET','/v3/videos/'+vid)['data']
        if v['status']=='completed': break
        if v['status']=='failed': print('failed',v); return
    out=f'{D}/out/monk-{today}-{t["id"]}.mp4'
    urllib.request.urlretrieve(v['video_url'],out)
    after=wallet(); led[today].update(wallet_after=after,cost_usd=round(before-after,2),duration=v.get('duration'),out=out)
    json.dump(led,open(D+'/ledger.json','w'),indent=1); print('video',out,'cost',before-after)
    cap=out.replace('.mp4','-captioned.mp4')
    try:
        subprocess.run([D+'/venv/bin/python',D+'/captions.py',out,cap],check=True,timeout=600)
        out=cap; led[today]['captioned']=cap
    except Exception as e:
        print('caption failed, NOT posting uncaptioned:',e); led[today]['caption_error']=str(e)
        json.dump(led,open(D+'/ledger.json','w'),indent=1); return
    json.dump(led,open(D+'/ledger.json','w'),indent=1)
    if '--no-post' in a: return
    post(out,t,led,today)
def post(out,t,led,today):
    # multipart upload to Postiz
    b=uuid.uuid4().hex; fb=open(out,'rb').read()
    body=(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{os.path.basename(out)}"\r\nContent-Type: video/mp4\r\n\r\n').encode()+fb+f'\r\n--{b}--\r\n'.encode()
    up=api('POST','https://api.postiz.com/public/v1/upload',{'Authorization':PZ,'Content-Type':'multipart/form-data; boundary='+b},body)
    payload={'type':'now','shortLink':False,'date':datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z'),'tags':[],
      'posts':[{'integration':{'id':MONK_TIKTOK},'value':[{'content':t['caption'],'image':[{'id':up['id'],'path':up['path']}]}],
      'settings':{'__type':'tiktok','title':t['caption'][:90],'privacy_level':'PUBLIC_TO_EVERYONE','duet':False,'stitch':False,'comment':True,
        'autoAddMusic':'no','brand_content_toggle':False,'brand_organic_toggle':False,'video_made_with_ai':True,'content_posting_method':'DIRECT_POST'}}]}
    img=[{'id':up['id'],'path':up['path']}]
    payload['posts'].append({'integration':{'id':MONK_IG},'value':[{'content':t['caption'],'image':img}],
      'settings':{'__type':'instagram-standalone','post_type':'post','collaborators':[]}})
    res=api('POST','https://api.postiz.com/public/v1/posts',{'Authorization':PZ,'Content-Type':'application/json'},json.dumps(payload).encode())
    led[today]['postiz']=res; json.dump(led,open(D+'/ledger.json','w'),indent=1); print('posted',res)
def post_ig(out,t,led,d):
    b=uuid.uuid4().hex; fb=open(out,'rb').read()
    body=(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{os.path.basename(out)}"\r\nContent-Type: video/mp4\r\n\r\n').encode()+fb+f'\r\n--{b}--\r\n'.encode()
    up=api('POST','https://api.postiz.com/public/v1/upload',{'Authorization':PZ,'Content-Type':'multipart/form-data; boundary='+b},body)
    payload={'type':'now','shortLink':False,'date':datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z'),'tags':[],
      'posts':[{'integration':{'id':MONK_IG},'value':[{'content':t['caption'],'image':[{'id':up['id'],'path':up['path']}]}],
      'settings':{'__type':'instagram-standalone','post_type':'post','collaborators':[]}}]}
    res=api('POST','https://api.postiz.com/public/v1/posts',{'Authorization':PZ,'Content-Type':'application/json'},json.dumps(payload).encode())
    led[d]['postiz_ig']=res; json.dump(led,open(D+'/ledger.json','w'),indent=1); print('posted ig',res)
if __name__=='__main__': main()
