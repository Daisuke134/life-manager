import Link from "next/link";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import { loadAllBlogPosts } from "../../../../lib/blog-posts";
import { BUSINESSES, businessOf } from "../../../../lib/blog-business.mjs";

const SITE = "https://aniccaai.com";

export function generateStaticParams() {
  return Object.keys(BUSINESSES).map((business) => ({ business }));
}

export function generateMetadata({ params }: { params: { business: string } }) {
  const hub = BUSINESSES[params.business];
  if (!hub) return { title: "Not found" };
  return {
    title: `${hub.label} | Anicca Articles`,
    description: hub.intro,
    alternates: { canonical: `${SITE}/blog/c/${params.business}` },
    robots: { index: true, follow: true },
  };
}

export default function BusinessHub({ params }: { params: { business: string } }) {
  const hub = BUSINESSES[params.business];
  if (!hub) notFound();
  const posts = loadAllBlogPosts().filter((p) => businessOf(p.slug, p.project) === params.business);
  const url = `${SITE}/blog/c/${params.business}`;
  return (
    <main className="bg-cream">
      <JsonLd data={{
        "@context": "https://schema.org", "@type": "CollectionPage", name: hub.label, url, description: hub.intro,
        mainEntity: { "@type": "ItemList", numberOfItems: posts.length,
          itemListElement: posts.slice(0, 100).map((p, i) => ({ "@type": "ListItem", position: i + 1, url: `${SITE}/blog/${p.slug}`, name: p.title })) },
      }} />
      <JsonLd data={{
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: SITE },
          { "@type": "ListItem", position: 2, name: "Articles", item: `${SITE}/blog` },
          { "@type": "ListItem", position: 3, name: hub.label, item: url },
        ],
      }} />
      <section className="mx-auto max-w-4xl px-5 pt-32 pb-20">
        <nav className="font-mono-ui text-[11px] uppercase tracking-[0.22em] text-mist">
          <Link href="/blog" className="hover:text-ink">Articles</Link> / {hub.label}
        </nav>
        <h1 className="mt-6 font-display text-[44px] leading-[1.05] text-ink sm:text-[56px]">{hub.label}</h1>
        <p className="mt-5 max-w-2xl text-[18px] leading-relaxed text-ink-soft">{hub.intro}</p>
        <ul className="mt-12 divide-y divide-bone border-y border-bone">
          {posts.map((p) => (
            <li key={p.slug} className="py-5">
              <Link href={`/blog/${p.slug}`} className="group block">
                <p className="font-mono-ui text-[11px] uppercase tracking-[0.22em] text-mist">{p.date}</p>
                <p className="mt-2 font-display text-[22px] leading-snug text-ink group-hover:underline">{p.title}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
