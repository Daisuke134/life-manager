// Opt-in renderer for reviewed Manager articles. Raw HTML is always text.
const esc = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function safeUrl(value) {
 if(value.includes('\\')) return false;
 return /^(https?:\/\/[^\s<>"']+|\/(?!\/)[^\s<>"']*|#[a-zA-Z0-9_-]+)$/.test(value);
}
function inline(text) {
 const token = /(!?\[[^\]\n]*\]\([^)\n]+\)|`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g;
 let out = '', last = 0;
 for (const match of text.matchAll(token)) {
  out += esc(text.slice(last, match.index)); const s=match[0];
  const link = s.match(/^(!?)\[([^\]]*)\]\(([^)]+)\)$/);
  if (link) {
   const [, image, label, url] = link;
   out += !safeUrl(url) ? esc(label) : image
    ? `<img src="${esc(url)}" alt="${esc(label)}" class="my-10 w-full rounded border border-bone" loading="lazy" />`
    : `<a href="${esc(url)}" class="underline underline-offset-4" rel="noopener noreferrer">${esc(label)}</a>`;
  } else if (s.startsWith('`')) out += `<code class="rounded bg-bone/60 px-1 break-all">${esc(s.slice(1,-1))}</code>`;
  else if(s.startsWith('**')) out += `<strong>${esc(s.slice(2,-2))}</strong>`;
  else out += `<em>${esc(s.slice(1,-1))}</em>`;
  last = match.index+s.length;
 }
 return out+esc(text.slice(last));
}
const cells = line => line.trim().replace(/^\|/,'').replace(/\|$/,'').split(/(?<!\\)\|/).map(c=>c.trim().replace(/\\\|/g,'|'));
const separator = line => /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
export function renderManagerMarkdown(md) {
 const lines=String(md).replace(/\r\n/g,'\n').split('\n'), out=[];
 for(let i=0;i<lines.length;) {
  const line=lines[i];
  if(!line.trim()) {i++;continue;}
  const fence=line.match(/^\s*(`{3,}|~{3,})([\w-]*)\s*$/);
  if(fence) {
   const code=[];i++;
   while(i<lines.length && !new RegExp(`^\\s*${fence[1][0]}{${fence[1].length},}\\s*$`).test(lines[i])) code.push(lines[i++]);
   i++; out.push(`<pre class="my-6 overflow-x-auto rounded bg-bone/60 p-4"><code>${esc(code.join('\n'))}</code></pre>`);continue;
  }
  if(i+1<lines.length && line.includes('|') && separator(lines[i+1])) {
   const head=cells(line);i+=2;const rows=[];
   while(i<lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(cells(lines[i++]));
   out.push(`<div class="my-8 overflow-x-auto"><table class="w-full border-collapse text-left"><thead><tr>${head.map(c=>`<th class="border border-bone p-3">${inline(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${head.map((_,n)=>`<td class="border border-bone p-3">${inline(r[n]||'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);continue;
  }
  const h=line.match(/^(#{1,6})\s+(.*)$/);
  if(h) {out.push(`<h${h[1].length} class="font-display ${h[1].length===1?'text-4xl sm:text-6xl mb-10':'text-2xl sm:text-3xl mt-12 mb-5'}">${inline(h[2])}</h${h[1].length}>`);i++;continue;}
  const li=line.match(/^\s*(?:([-*])|(\d+)\.)\s+(.*)$/);
  if(li) {
   const ordered=!!li[2], items=[];
   while(i<lines.length) {
    const m=lines[i].match(/^\s*(?:([-*])|(\d+)\.)\s+(.*)$/);
    if(!m || !!m[2]!==ordered) break;
    items.push(`<li>${inline(m[3])}</li>`);i++;
   }
   out.push(`<${ordered?'ol':'ul'} class="my-6 space-y-3 pl-6 ${ordered?'list-decimal':'list-disc'}">${items.join('')}</${ordered?'ol':'ul'}>`);continue;
  }
  if(/^\s*---+\s*$/.test(line)) {out.push('<hr class="my-10 border-bone" />');i++;continue;}
  const p=[line];i++;
  while(i<lines.length && lines[i].trim() && !/^(?:#{1,6}\s|\s*[-*]\s|\s*\d+\.\s|\s*```|\s*~~~)/.test(lines[i]) && !(i+1<lines.length && separator(lines[i+1]))) p.push(lines[i++]);
  out.push(`<p class="my-6 text-lg leading-relaxed text-ink-soft">${inline(p.join(' '))}</p>`);
 }
 return out.join('\n');
}
