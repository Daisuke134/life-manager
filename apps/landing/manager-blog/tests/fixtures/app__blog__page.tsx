import Link from 'next/link';
import JsonLd from '@/components/JsonLd';
import type {ReactNode} from 'react';
import { BUSINESSES } from '../../lib/blog-business.mjs';
import { businessOf, editorialOf } from '../../lib/blog-business.mjs';
import {loadAllBlogPosts} from '../../lib/blog-posts';
import {MediaNav,MediaFooter,ArticleList} from '../../components/blog/OwnedMedia';
export const metadata={title:'Articles | Anicca',description:'Explore research, product guides, publishing and the work behind Anicca by topic.',alternates:{canonical:'https://aniccaai.com/blog'}};
// Preserve the canonical Manager overlay's category-link integration point.
function TopicLink({topic,children}:{topic:string;children:ReactNode}){
 const key=topic;
 if(key==='manager')return <Link href="/blog/manager">{children}</Link>;
 return <Link href={`/blog/c/${key}`}>{children}</Link>;
}
export default function BlogIndex(){
 const corpus=loadAllBlogPosts();
 const posts=corpus.filter(p=>editorialOf(p.slug,p.project) !== 'Research').slice(0,6);
 const groups=[['Research',['research']],['Products & publishing',['anicca','thankful','ai-creator-tools','line-stickers','ebook','ebook-publishing']],['Build Notes & Labs',['notes','ai-voice-tools']]] as const;
 const topics=groups.flatMap(([,keys])=>keys.map(key=>{
  const hub=BUSINESSES[key];
  const articles=corpus.filter(p=>key==='research'?editorialOf(p.slug,p.project)==='Research':editorialOf(p.slug,p.project)!=='Research'&&businessOf(p.slug,p.project)===key).slice(0,2);
  return {key,...hub,href:`/blog/c/${key}`,articles};
 })).filter(topic=>topic.articles.length>0);
 return <main className="media-page"><MediaNav/><div className="media-wrap">
 <JsonLd data={{'@context':'https://schema.org','@type':'CollectionPage',name:'Anicca Articles',url:'https://aniccaai.com/blog',description:metadata.description,mainEntity:{'@type':'ItemList',numberOfItems:topics.length,itemListElement:topics.map((topic,i)=>({'@type':'ListItem',position:i+1,url:`https://aniccaai.com${topic.href}`,name:topic.label}))}}}/>
 <header className="media-hero"><p className="article-topic">The work, in words</p><h1>Explore by topic.</h1><p>Research, useful product guides, publishing and experiments. Choose an area to explore the work behind Anicca.</p><Link href="/blog/archive/1" className="media-button">Browse all articles</Link></header>
 {groups.map(([label,keys])=>{const entries=topics.filter(topic=>keys.some(key=>key===topic.key));return entries.length>0&&<section key={label}><h2>{label}</h2><div className="topic-directory">{entries.map(topic=><article key={topic.key} data-topic={topic.key}><h3><TopicLink topic={topic.key}>{topic.label}</TopicLink></h3><p>{topic.intro}</p>{topic.key==='research'&&<p><Link href="/blog/manager">Manager research collection</Link></p>}<ul>{topic.articles.map(p=><li key={p.slug} data-article-preview={p.slug}><Link href={`/blog/${p.slug}`}>{p.title}</Link><time dateTime={p.date}>{p.date}</time></li>)}</ul><span className="topic-browse"><TopicLink topic={topic.key}>Browse {topic.label}</TopicLink></span></article>)}</div></section>})}
 <section aria-labelledby="latest-heading"><h2 id="latest-heading">Latest articles</h2><ArticleList posts={posts}/><Link href="/blog/archive/1">All articles</Link></section>
 <section aria-label="Elsewhere"><h2>Elsewhere</h2><p>Follow Anicca through our other channels.</p><div className="media-actions"><a href="https://x.com/selawmqt">X updates</a><a href="https://aniccaai.substack.com">Substack</a><Link href="/letter">Anicca Letter</Link></div></section>
 <MediaFooter/></div></main>;
}
