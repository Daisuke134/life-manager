"""Owned digital-environment adapter: semantic HTML, source bounds, byte verification.

No external writes, participant tracking or inference of human wellbeing. The
publisher is a separate explicitly scoped developer/release operation. Reuses
stdlib HTTP/HTML/SHA and the existing Manager outcome_ladder, not a new scorer.
"""
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from manager_core.outcome_ladder import proof_level

HOSTS = frozenset({'www.mhlw.go.jp','www.fsa.go.jp','kennet.mhlw.go.jp'})
DOMAINS = {'finance':'生活費・仕事・借入','mental':'こころの相談','physical':'健康づくり'}
PUBLISH_PREFIX = 'manager-support/'
PAGES = frozenset({'index.html','finance.html','mental.html','physical.html','control.html','proof.html'})
SOURCE_REPO = 'https://github.com/Daisuke134/life-manager'
MAX_BODY = 2 * 1024 * 1024


def _url(value):
    if not isinstance(value,str) or len(value)>2048 or any(ord(c)<32 for c in value):
        raise ValueError('invalid public source URL')
    p=urlsplit(value)
    if (p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password
        or p.port not in (None,443) or p.fragment or not p.path.startswith('/')):
        raise ValueError('source outside exact public official host allowlist')
    return value


def validate_catalog(catalog):
    if (not isinstance(catalog,dict) or set(catalog)!={'schema','resources'}
        or catalog['schema']!='manager.official-support.v1'):
        raise ValueError('invalid catalog schema')
    rows=catalog['resources']
    if not isinstance(rows,list) or not 3<=len(rows)<=30:
        raise ValueError('bounded public source catalog required')
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'id','domain','title','description','url','reviewed_on','rights'}:
            raise ValueError('unknown source field; do not import private information')
        if any(not isinstance(v,str) or not v.strip() for v in row.values()):
            raise ValueError('explicit nonempty source metadata required')
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,63}',row['id']) or row['id'] in seen:
            raise ValueError('unique safe source identifier required')
        seen.add(row['id'])
        if row['domain'] not in DOMAINS or row['rights']!='LINK_ONLY':
            raise ValueError('unknown domain or source redistribution rights')
        if len(row['title'])>200 or len(row['description'])>800:
            raise ValueError('bounded source summaries required')
        _url(row['url'])
        reviewed=date.fromisoformat(row['reviewed_on'])
        today=datetime.now(timezone.utc).date()
        if not today-timedelta(days=45)<=reviewed<=today:
            raise ValueError('source review is stale or future-dated')
    if {r['domain'] for r in rows}!=set(DOMAINS):
        raise ValueError('all three domains must use the same source contract')
    return True


CSS = '''*{box-sizing:border-box}html{font-size:100%;color:#182923;background:#f8faf8}body{margin:0;font:1.06rem/1.8 system-ui,-apple-system,sans-serif}header,main,footer{max-width:65rem;margin:auto;padding:1.6rem}header{border-bottom:1px solid #cad5cc}a{color:#154f42;text-underline-offset:.22em;overflow-wrap:anywhere}a:hover{text-decoration-thickness:.16em}a:focus-visible,main:focus{outline:3px solid #8a4600;outline-offset:4px}nav{display:flex;flex-wrap:wrap;gap:.7rem 1.5rem}nav a{padding:.35rem .15rem}h1{font-size:clamp(1.8rem,5vw,2.8rem);line-height:1.4;margin:.5rem 0 1rem}h2{font-size:1.35rem;line-height:1.5}p{max-width:75ch}.eyebrow{font-weight:700;letter-spacing:.09em;font-size:.85rem}.intro{font-size:1.15rem}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr));gap:1rem;margin:1.5rem 0}.card{padding:1.4rem;border:1px solid #bccbc0;border-radius:.65rem;background:white}.card h2{margin-top:0}.meta{font-size:.9rem;color:#354e43}.notice{border-left:4px solid #315c4c;padding:.8rem 1.1rem;background:#eaf0eb}.skip{position:absolute;left:1rem;top:-8rem;background:#fff;padding:.6rem}.skip:focus{top:1rem;z-index:10}footer{border-top:1px solid #cad5cc;font-size:.95rem}code{overflow-wrap:anywhere}li{margin-bottom:.6rem}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #ccd6cf;padding:.7rem;vertical-align:top}caption{text-align:left;font-weight:bold} @media(max-width:500px){header,main,footer{padding:1rem}nav{gap:.4rem 1rem}}'''


def _shell(title,body,commit):
    nav=''.join(f'<a href="{domain}.html">{escape(label)}</a>' for domain,label in DOMAINS.items())
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="description" content="生活・こころ・健康の公的な支援情報への、登録不要の入口。"><title>{escape(title)} | Manager</title><style>{CSS}</style></head>
<body><a class="skip" href="#main">本文へ移動</a><header><p class="eyebrow">MANAGER / 公的支援への入口</p><nav aria-label="主な案内"><a href="index.html">ホーム</a>{nav}<a href="proof.html">検証と限界</a></nav></header>
<main id="main" tabindex="-1"><h1>{escape(title)}</h1>{body}
<aside class="notice" aria-label="案内の範囲"><p data-limit>このサイトは公式情報への案内です。申請・診断・治療や金融取引を行うサービスではありません。</p><p>個人情報の入力、会員登録、Cookieによる追跡はありません。リンク先では、その機関の利用条件とプライバシー方針が適用されます。</p><p data-experiment>利用者を対象とした実験は実施していません。表示を利用するかどうかは、ご自身で選べます。</p></aside></main>
<footer><p data-outcome>人の健康・家計への効果：NOT_MEASURED（未測定）</p><p>公開やリンクの存在だけでは、実際に誰かの状態が改善したとはいえません。</p><p><a href="control.html">同じ情報を一覧で見る（NO_ACTION参照版）</a> · <a href="{SOURCE_REPO}/tree/{commit}/products/manager">この版のソース</a></p><p class="meta">独立した研究プロジェクト Manager。政府機関の公式サイトではなく、公的な承認・提携を示すものでもありません。</p></footer></body></html>\n'''


def _cards(rows):
    parts=[]
    for r in rows:
        parts.append(f'''<article class="card"><h2><a data-official href="{escape(r['url'],quote=True)}" rel="noreferrer">{escape(r['title'])}</a></h2><p>{escape(r['description'])}</p><p class="meta">出典：{escape(urlsplit(r['url']).hostname)} / 確認日：{escape(r['reviewed_on'])}</p></article>''')
    return '<div class="cards">'+''.join(parts)+'</div>'


def build_site(catalog,out,commit):
    validate_catalog(catalog)
    if not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):
        raise ValueError('immutable source commit required')
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    if out.is_symlink() or any(p.is_symlink() for p in out.iterdir()):
        raise ValueError('symlink output prohibited')
    pages={}
    menu=''.join(f'<article class="card"><h2><a href="{k}.html">{escape(v)}</a></h2><p>必要な情報を、公的機関の案内から確認できます。</p></article>' for k,v in DOMAINS.items())
    pages['index.html']=_shell('必要な支援へ、迷わず進む。','<p class="intro">生活費や借入、こころのつらさ、健康づくり。必要な項目を選ぶと、公式情報への入口を確認できます。</p><div class="cards">'+menu+'</div><p>読む・閉じる・公式サイトへ進む。どの選択もご自身で決められます。</p>',commit)
    for domain,title in DOMAINS.items():
        intro='<p class="intro">ご自身に合う情報を、公式の案内から確認してください。個別の資格や状態はここでは判断しません。</p>'
        if domain=='mental':
            intro+='<p class="notice">差し迫った危険や急な体調の変化があるときは、このページを待たずに地域の緊急窓口・医療機関へ直接相談してください。</p>'
        pages[domain+'.html']=_shell(title,intro+_cards([r for r in catalog['resources'] if r['domain']==domain]),commit)
    flat='<p>分類された案内と同じ出典を、通常の一覧で確認できます。実際の対照試験ではありません。</p><ul>'+''.join(f'<li><a data-official href="{escape(r["url"],quote=True)}" rel="noreferrer">{escape(r["title"])}</a></li>' for r in catalog['resources'])+'</ul>'
    pages['control.html']=_shell('公式情報の一覧 / NO_ACTION',flat,commit)
    proof='<p>公開されたページ、案内先、アクセシビリティを確認するための検証環境です。利用者の所得、症状、身体機能を測定した研究ではありません。</p><table><caption>何を確認でき、何がまだ不明か</caption><thead><tr><th scope="col">対象</th><th scope="col">証拠</th></tr></thead><tbody><tr><th scope="row">ページの公開</th><td>外部からの読戻しと内容のハッシュ一致で確認します。</td></tr><tr><th scope="row">操作のしやすさ</th><td>Playwrightとaxe-coreによる自動検査。すべての障壁を検出できるわけではありません。</td></tr><tr><th scope="row">精神・身体・経済への効果</th><td>NOT_MEASURED。臨床効果や給付受領は確認されていません。</td></tr></tbody></table><p>WHO-5、WHODAS、CFPBの既存尺度は将来の適切な評価の参考です。本サイトでは回答を収集せず、質問票を転載しません。</p>'
    pages['proof.html']=_shell('検証できること、できないこと',proof,commit)
    hashes={}
    for filename,body in pages.items():
        raw=body.encode('utf-8')
        (out/filename).write_bytes(raw)
        hashes[filename]=sha256(raw).hexdigest()
    manifest={'schema':'manager.public-service.v1','source_commit':commit,'files':hashes,'beneficiary_outcome':'NOT_MEASURED','real_participants':0,'clinical_claim':False,'experiment_enabled':False}
    (out/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    verify_bundle(out,manifest)
    return manifest


def permitted_publish_path(path):
    return isinstance(path,str) and path in {PUBLISH_PREFIX+n for n in PAGES|{'manifest.json'}}


def _valid_manifest(m):
    if (not isinstance(m,dict) or m.get('schema')!='manager.public-service.v1'
        or not isinstance(m.get('source_commit'),str) or re.fullmatch('[0-9a-f]{40}',m['source_commit']) is None
        or not isinstance(m.get('files'),dict) or set(m['files'])!=PAGES
        or m.get('beneficiary_outcome')!='NOT_MEASURED' or type(m.get('real_participants')) is not int
        or m['real_participants']!=0 or m.get('clinical_claim') is not False or m.get('experiment_enabled') is not False):
        raise ValueError('invalid immutable release manifest')
    if any(not isinstance(h,str) or re.fullmatch('[0-9a-f]{64}',h) is None for h in m['files'].values()):
        raise ValueError('invalid digest')


def verify_bundle(out,manifest):
    _valid_manifest(manifest)
    out=Path(out)
    if out.is_symlink() or {p.name for p in out.iterdir()}!=PAGES|{'manifest.json'}:
        raise ValueError('unexpected release file or directory')
    bodies={}
    for name in PAGES:
        p=out/name
        if p.is_symlink() or not p.is_file():
            raise ValueError('non-regular release file')
        bodies[name]=p.read_bytes()
    verify_readback(manifest,bodies)
    if json.loads((out/'manifest.json').read_text())!=manifest:
        raise ValueError('manifest contents differ')
    return True


def verify_readback(manifest,bodies):
    _valid_manifest(manifest)
    if not isinstance(bodies,dict) or set(bodies)!=PAGES:
        raise ValueError('missing independent page readback')
    for name,wanted in manifest['files'].items():
        if not isinstance(bodies[name],bytes) or sha256(bodies[name]).hexdigest()!=wanted:
            raise ValueError('independent page bytes mismatch')
    return {'delivery':'VERIFIED_BYTES_ONLY','technical_proof':f'P{proof_level({"external_receipt": True,"independent_readback": True})}_ARTIFACT_ONLY','beneficiary_outcome':'NOT_MEASURED','causal_effect_verified':False}


class OfficialOnlyRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        _url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def audit_sources(catalog):
    validate_catalog(catalog)
    opener=build_opener(OfficialOnlyRedirect())
    results=[]
    for r in catalog['resources']:
        item={'id':r['id'],'url':r['url'],'status':'UNKNOWN','http_status':None,'sha256':None,'observed_at':datetime.now(timezone.utc).isoformat()}
        try:
            req=Request(r['url'],headers={'User-Agent':'Manager-Public-Source-Review/0.1','Accept':'text/html'},method='GET')
            with opener.open(req,timeout=15) as response:
                _url(response.url)
                raw=response.read(MAX_BODY+1)
                item['http_status']=response.status
                if response.status!=200 or len(raw)>MAX_BODY or 'html' not in response.headers.get('Content-Type','').lower():
                    raise ValueError('unexpected source response')
                item.update(status='REACHABLE_NOT_OUTCOME',sha256=sha256(raw).hexdigest(),final_url=response.url)
        except Exception as exc:
            item['error_type']=type(exc).__name__
        results.append(item)
    return {'sources':results,'content_rights':'LINK_ONLY','human_outcome':'NOT_MEASURED'}


def assess_outcomes(data):
    # No implementation can authenticate real human outcomes from caller claims.
    # A reviewed real outcome integration must be added before any positive branch.
    return {'status':'NOT_MEASURED' if data is None else 'UNVERIFIED_OUTCOME_INPUT','effect':None,'n':None,'confidence_interval':None,'mental':'NOT_MEASURED','physical':'NOT_MEASURED','financial':'NOT_MEASURED','causal_effect_verified':False}
