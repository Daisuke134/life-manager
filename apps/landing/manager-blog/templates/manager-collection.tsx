import fs from "fs";
import path from "path";
import Link from "next/link";
import JsonLd from "@/components/JsonLd";

type Entry = { slug: string; title: string; description?: string; lang: "en" | "ja"; series_order?: number };
const url = "https://aniccaai.com/blog/manager";
export const metadata = {
  title: "Manager Research & Build Notes | Anicca",
  description: "From synthetic populations to behavior models and interventions. Learn what we build, how we test it, and what remains uncertain. End suffering.",
  alternates: { canonical: url },
};
export default function ManagerCollection() {
  const folder = path.join(process.cwd(), "data", "research");
  const posts: Entry[] = fs.readdirSync(folder).filter(f => /^manager-.*\.json$/.test(f)).map(f => JSON.parse(fs.readFileSync(path.join(folder, f), "utf8"))).filter(p => p.project === "Manager");
  posts.sort((a, b) => (a.series_order ?? 999) - (b.series_order ?? 999) || a.slug.localeCompare(b.slug));
  return <main className="bg-cream">
    <JsonLd data={{ "@context": "https://schema.org", "@type": "CollectionPage", name: "Manager", url, mainEntity: { "@type": "ItemList", numberOfItems: posts.length, itemListElement: posts.map((p,i) => ({ "@type": "ListItem", position: i+1, name: p.title, url: `https://aniccaai.com/blog/${p.slug}` })) } }} />
    <section className="mx-auto max-w-4xl px-5 pt-32 pb-20">
      <nav className="font-mono-ui text-xs uppercase tracking-widest text-mist"><Link href="/blog" className="hover:text-ink">Articles</Link> / Manager</nav>
      <h1 className="mt-6 font-display text-5xl text-ink">Manager</h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-soft">Our mission is End suffering. These articles follow the work toward Manager: building synthetic populations, testing behavior models, and studying interventions. A working simulation is a starting point for evidence, not proof of real-world benefit.</p>
      <nav className="mt-6 flex gap-6 text-ink underline"><a href="#english">English</a><a href="#japanese">日本語</a></nav>
      {([['en','English','english'],['ja','日本語','japanese']] as const).map(([lang,label,id]) => <section key={lang} id={id} className="mt-14 scroll-mt-8">
        <h2 className="font-display text-3xl text-ink">{label}</h2>
        <ul className="mt-6 divide-y divide-bone border-y border-bone">{posts.filter(p => p.lang === lang).map(p => <li key={p.slug} className="py-6">
          <Link href={`/blog/${p.slug}`} className="group block"><h3 className="font-display text-2xl leading-snug text-ink group-hover:underline">{p.title}</h3><p className="mt-3 text-base leading-relaxed text-ink-soft">{p.description}</p></Link>
        </li>)}</ul>
      </section>)}
    </section>
  </main>;
}
