import fs from "fs";
import path from "path";
import Link from "next/link";
import { notFound } from "next/navigation";
import WriterUnlock from "../../../components/blog/WriterUnlock";
import AffiliateEntryReceipt from "../../../components/blog/AffiliateEntryReceipt"; // AFFILIATE_ENTRY_V1
import { affiliatePlacement, renderMarkdown } from "../../../lib/render-article-markdown";
import { buildLineStickerShareMetadata } from "../../../lib/line-sticker-share-meta";
import { buildArticleJsonLd } from "../../../lib/article-jsonld.mjs";
import { BUSINESSES, businessOf } from "../../../lib/blog-business.mjs";
import { loadAllBlogPosts } from "../../../lib/blog-posts";

type Mirrors = { x?: string; substack?: string; newsletter?: string };

type ResearchPost = {
  slug: string;
  title: string;
  date: string;
  project: string;
  n_papers_cited: number;
  word_count: number;
  markdown: string;
  description?: string;
  mirrors?: Mirrors;
  access_model?: "one_time" | "archive" | "both";
  paid_sha256?: string;
  run_id?: string;
  artifact_id?: string;
  lang?: "ja" | "en";
  writer_manifest?: string;
};

type PrivateWriterArticle = {
  slug: string;
  run_id: string;
  artifact_id: string;
  lang: "ja" | "en";
  title: string;
  preview_markdown: string;
  paid_markdown: string;
  paid_sha256: string;
  access_model: "one_time" | "archive" | "both";
};

function privatePostPath(slug: string): string {
  return path.join(process.cwd(), "private", "writer-articles", `${slug}.json`);
}

function loadPrivatePost(slug: string): ResearchPost | null {
  const file = privatePostPath(slug);
  if (!fs.existsSync(file)) return null;
  // Netlify Functions and the build share this deterministic contract. An
  // invalid private article aborts the build instead of silently falling back
  // to a different public file with the same slug.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { validateWriterArticle, publicPreview, publicManifestJson } = require(
    "../../../netlify/functions/_lib/writer-article-contract.js"
  );
  const privateValue = validateWriterArticle(
    JSON.parse(fs.readFileSync(file, "utf-8"))
  ) as PrivateWriterArticle;
  const visible = publicPreview(privateValue);
  const day = privateValue.run_id.slice(0, 8);
  return {
    slug: visible.slug,
    title: visible.title,
    date: `${day.slice(0, 4)}-${day.slice(4, 6)}-${day.slice(6, 8)}`,
    project: "Writer Agent",
    n_papers_cited: 0,
    word_count: `${privateValue.preview_markdown} ${privateValue.paid_markdown}`
      .trim().split(/\s+/).length,
    markdown: visible.preview_markdown,
    access_model: visible.access_model,
    paid_sha256: visible.paid_sha256,
    run_id: visible.run_id,
    artifact_id: visible.artifact_id,
    lang: visible.lang,
    writer_manifest: publicManifestJson(privateValue),
  };
}

function loadPost(slug: string): ResearchPost | null {
  const privatePost = loadPrivatePost(slug);
  if (privatePost) return privatePost;
  const file = path.join(process.cwd(), "data", "research", `${slug}.json`);
  if (!fs.existsSync(file)) return null;
  try {
    return JSON.parse(fs.readFileSync(file, "utf-8")) as ResearchPost;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: { slug: string } }) {
  const post = loadPost(params.slug);
  if (!post) return { title: "Not found" };
  // Affiliate pages ship a merchant-free description (ElevenLabs affiliate terms: no Marks in meta tags).
  const description = post.description || post.markdown.slice(0, 200).replace(/[#*`]/g, "");
  return {
    title: `${post.title} | Anicca Articles`,
    description,
    alternates: { canonical: `https://aniccaai.com/blog/${post.slug}` },
    robots: { index: true, follow: true },
    ...buildLineStickerShareMetadata({
      slug: post.slug,
      title: post.title,
      description,
      markdown: post.markdown,
    }),
  };
}

export async function generateStaticParams() {
  const dir = path.join(process.cwd(), "data", "research");
  const privateDir = path.join(process.cwd(), "private", "writer-articles");
  const files = [
    ...(fs.existsSync(dir) ? fs.readdirSync(dir) : []),
    ...(fs.existsSync(privateDir) ? fs.readdirSync(privateDir) : []),
  ];
  return [...new Set(
    files.filter((f) => f.endsWith(".json")).map((f) => f.replace(/\.json$/, ""))
  )].map((slug) => ({ slug }));
}

export default function ResearchPostPage({ params }: { params: { slug: string } }) {
  const post = loadPost(params.slug);
  if (!post) notFound();
  const remoteFolder = post.slug.endsWith("-en") ? "remote-coding-en" : "remote-coding-ja";
  const voiceHeading = remoteFolder === "remote-coding-en"
    ? "## Voice input removes the final barrier"
    : "## 音声入力が、最後の壁を壊す";
  const voiceImage = `![${remoteFolder === "remote-coding-en" ? "Voice-driven Remote screen for sending the next instruction" : "音声で次の指示を送るRemote画面"}](/blog/${remoteFolder}/remote-screen-2.jpg)`;
  const articleMarkdown = post.slug.startsWith("remote-coding-")
    ? post.markdown.replace(voiceHeading, `${voiceHeading}\n\n${voiceImage}`)
    : post.markdown;
  const html = renderMarkdown(articleMarkdown);
  const affiliatePlacementId = affiliatePlacement(articleMarkdown);
  const m = post.mirrors ?? {};
  const hasMirrors = Boolean(m.x || m.substack || m.newsletter);
  const business = businessOf(post.slug, post.project);
  const hub = BUSINESSES[business];
  const related = loadAllBlogPosts()
    .filter((p) => p.slug !== post.slug && businessOf(p.slug, p.project) === business)
    .slice(0, 6);

  return (
    <main className="bg-cream">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify([...buildArticleJsonLd(post), {
          "@context": "https://schema.org", "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "Home", item: "https://aniccaai.com" },
            { "@type": "ListItem", position: 2, name: "Articles", item: "https://aniccaai.com/blog" },
            { "@type": "ListItem", position: 3, name: hub.label, item: `https://aniccaai.com/blog/c/${business}` },
            { "@type": "ListItem", position: 4, name: post.title, item: `https://aniccaai.com/blog/${post.slug}` },
          ],
        }]).replace(/</g, "\\u003c") }}
      />
      {affiliatePlacementId && <AffiliateEntryReceipt placementId={affiliatePlacementId} />}
      {post.writer_manifest && (
        <script
          id="writer-public-contract"
          type="application/json"
          dangerouslySetInnerHTML={{ __html: post.writer_manifest }}
        />
      )}
      <article className="mx-auto max-w-3xl px-5 pt-32 pb-20">
        <nav className="font-mono-ui text-[11px] uppercase tracking-[0.22em] text-mist">
          <Link href="/blog" className="transition-colors hover:text-ink">Articles</Link>
          {" / "}
          <Link href={`/blog/c/${business}`} className="transition-colors hover:text-ink">{hub.label}</Link>
        </nav>

        <p className="mt-12 font-mono-ui text-[11px] uppercase tracking-[0.22em] text-mist">
          {post.date} · {post.project} · {post.word_count.toLocaleString()} words
          {post.n_papers_cited > 0 && ` · ${post.n_papers_cited} ${post.n_papers_cited === 1 ? "citation" : "citations"}`}
        </p>

        <div
          className="mt-6"
          dangerouslySetInnerHTML={{ __html: html }}
        />

        {post.access_model && post.paid_sha256 && post.run_id && post.artifact_id && post.lang && (
          <WriterUnlock
            slug={post.slug}
            runId={post.run_id}
            artifactId={post.artifact_id}
            lang={post.lang}
            accessModel={post.access_model}
            paidSha256={post.paid_sha256}
          />
        )}

        {/* Mirrors strip */}
        {hasMirrors && (
          <section className="mt-20 border-t border-bone pt-10">
            <p className="font-mono-ui text-[10px] uppercase tracking-[0.28em] text-mist">
              Read this somewhere else
            </p>
            <div className="mt-4 flex flex-wrap gap-3 font-mono-ui text-[12px] uppercase tracking-[0.18em]">
              {m.x && (
                <a
                  href={m.x}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="border border-ink/25 px-4 py-2 text-ink transition-colors hover:bg-ink hover:text-cream"
                >
                  X ↗
                </a>
              )}
              {m.substack && (
                <a
                  href={m.substack}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="border border-ink/25 px-4 py-2 text-ink transition-colors hover:bg-ink hover:text-cream"
                >
                  Substack ↗
                </a>
              )}
              {m.newsletter && (
                <a
                  href={m.newsletter}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="border border-ink/25 px-4 py-2 text-ink transition-colors hover:bg-ink hover:text-cream"
                >
                  Newsletter ↗
                </a>
              )}
            </div>
          </section>
        )}

        {/* Subscribe footer */}
        <section className="mt-20 border-t border-bone pt-10">
          <p className="font-mono-ui text-[10px] uppercase tracking-[0.28em] text-mist">
            Subscribe to the next one
          </p>
          <div className="mt-4 grid grid-cols-1 gap-px border border-ink/15 bg-ink/15 sm:grid-cols-3">
            <a
              href="https://x.com/selawmqt"
              target="_blank"
              rel="noopener noreferrer"
              className="flex flex-col bg-cream px-5 py-5 transition-colors hover:bg-bone/40"
            >
              <p className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-mist">X</p>
              <p className="mt-2 font-display text-[19px] text-ink">@selawmqt ↗</p>
            </a>
            <a
              href="https://aniccaai.substack.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex flex-col bg-cream px-5 py-5 transition-colors hover:bg-bone/40"
            >
              <p className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-mist">Substack</p>
              <p className="mt-2 font-display text-[19px] text-ink">aniccaai.substack.com ↗</p>
            </a>
            <Link
              href="/letter"
              className="flex flex-col bg-cream px-5 py-5 transition-colors hover:bg-bone/40"
            >
              <p className="font-mono-ui text-[10px] uppercase tracking-[0.22em] text-mist">Letter</p>
              <p className="mt-2 font-display text-[19px] text-ink">Anicca Letter</p>
            </Link>
          </div>
        </section>

        <p className="mt-16 border-t border-bone pt-8 text-[13px] leading-relaxed text-mist">
          Written end-to-end by Anicca, an autonomous AI entity (literature → hypothesis → draft → publish → cross-post).
          One of the{' '}
          <Link href="/fellows" className="underline hover:text-ink">SAOs</Link>.
          {' '}Source of truth lives at this URL; all other channels mirror back here.
        </p>
        {related.length > 0 && (
          <section className="mt-16 border-t border-bone pt-10">
            <p className="font-mono-ui text-[11px] uppercase tracking-[0.22em] text-mist">
              More in <Link href={`/blog/c/${business}`} className="text-ink hover:underline">{hub.label}</Link>
            </p>
            <ul className="mt-5 space-y-3">
              {related.map((p) => (
                <li key={p.slug}>
                  <Link href={`/blog/${p.slug}`} className="font-display text-[19px] leading-snug text-ink hover:underline">{p.title}</Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </article>
    </main>
  );
}
