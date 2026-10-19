import { createHash } from 'node:crypto';
export const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
export function validatePublication(value) {
 if(!Array.isArray(value?.articles)||!value.articles.length||!Array.isArray(value.media)) throw new Error('Invalid publication package');
 const seen=new Set();
 for(const a of value.articles) {
  if(!/^manager-[a-z0-9]+(?:-[a-z0-9]+)*-(ja|en)$/.test(a.slug)||!['ja','en'].includes(a.lang)||!a.slug.endsWith('-'+a.lang)||a.project!=='Manager') throw new Error('Invalid Manager article identity');
  if(seen.has(a.slug)) throw new Error('Duplicate article slug');seen.add(a.slug);
  if(a.package_path!==`${a.lang}/${a.slug}.md`) throw new Error('Invalid article path');
  if(!/^[a-f0-9]{64}$/.test(a.sha256)||typeof a.markdown!=='string'||digest(a.markdown)!==a.sha256) throw new Error('Article hash mismatch');
  if(a.canonical_url!==`https://aniccaai.com/blog/${a.slug}`||!a.title||!/^\d{4}-\d{2}-\d{2}$/.test(a.date)) throw new Error('Invalid article metadata');
 }
 for(const m of value.media) {
  if(!/^[a-f0-9]{64}$/.test(m.sha256)||!new RegExp(`^media/${m.sha256}\\.(png|jpg|jpeg|webp|gif)$`).test(m.package_path)||m.public_url!==`https://aniccaai.com/blog/manager/${m.package_path}`) throw new Error('Invalid media path or URL');
 }
 return value;
}
