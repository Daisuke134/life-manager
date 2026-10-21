// Generated portfolio entries consume the one canonical registry; surrounding routes remain hand-authored.
import {readFileSync,writeFileSync} from 'node:fs';
const root=new URL('../',import.meta.url);
const apps=JSON.parse(readFileSync(new URL('assets/published-apps.json',root),'utf8'));
const escape=s=>String(s).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;');
for(const [locale,file] of [['en','products-en.html'],['ja','products.html']]) {
 const path=new URL('pages/'+file,root);let html=readFileSync(path,'utf8');let i=0;
 html=html.replace(/<article\b[^>]*data-category="mobile"[^>]*>.*?<\/article>/gs,()=>{
  const a=apps[i++];const ja=locale==='ja'||a.presentationLanguage==='ja';const intro=a.intro[locale];
  return `<article class="card app-card" data-category="mobile"${a.presentationLanguage==='ja'?' lang="ja"':''}><img class="app-icon" src="${a.icon}" alt="${escape(a.name)} app icon" width="96" height="96" loading="lazy"><h3>${escape(a.name)}</h3><p>${escape(a.description[locale])}</p><div class="app-actions">${intro?`<a href="${intro}" aria-label="${escape(a.name)} ${ja?'紹介':'introduction'}">${a.id==='6766485903'?'公式サイト':ja?'アプリの紹介':'Explore the app'}</a>`:''}<a href="${a.store}" aria-label="${escape(a.name)} on the App Store">${ja?'App Storeで見る':'View on the App Store'}</a></div></article>`;
 });
 if(i!==apps.length)throw new Error('Six existing app entries required');
 html=html.replace('<body>','<body class="owned-media">');
 writeFileSync(path,html);
}
// Apply the same restrained link presentation to the entire owned route package.
const manifest=JSON.parse(readFileSync(new URL('route-manifest.json',root),'utf8'));
for(const source of new Set(manifest.files.map(f=>f.source).filter(p=>p.endsWith('.html')))){
 const path=new URL(source,root);
 writeFileSync(path,readFileSync(path,'utf8').replace(/[↗↖↥↑⬆][\uFE0E\uFE0F]?/gu,''));
}
