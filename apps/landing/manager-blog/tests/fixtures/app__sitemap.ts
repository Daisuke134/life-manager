import type { MetadataRoute } from "next";
import {
  AFFIRMATION_HREFLANG_TRIPLES,
  alternatesFor,
} from "@/lib/affirmation-alternates";
import { loadAllBlogPosts } from "@/lib/blog-posts";
import { BUSINESSES } from "@/lib/blog-business.mjs";
import { allEnAffirmationSlugs } from "@/lib/en-affirmation-problems";
import { allEsAffirmationSlugs } from "@/lib/es-affirmation-problems";
import { JA_AFFIRMATION_PROBLEMS } from "@/lib/ja-affirmation-problems";
import { allKokoroTypeIds } from "@/lib/kokoro-quiz";
import { LM_JA_GUIDES } from "@/lib/lm-ja-guides";

const BASE_URL = "https://aniccaai.com";

// Static top-level pages. Paths must exist (no 404s). No trailing-slash
// duplicates of redirect-only aliases.
const STATIC_PATHS = [
  "/affirmation-app",
  "/affirmation-app/ja",
  "/affirmation-app/ja/a",
  "/affirmation-app/ja/wallpaper",
  "/affirmation-app/ja/shindan",
  "/affirmation-app/es/a",
  "/letter",
  "/tegami",
  "/en",
  "/honne",
  "/honne/ja",
  "/honne/support",
  "/honne/privacy",
  "/honne/privacy/ja",
  "/pdf-insight",
  "/dais",
  "/breath-calm",
  "/calmcortisol",
  "/thankful",
  "/ai-cafe-tokyo/",
  "/ai-grave/",
  "/lm",
  "/lm/ja",
  "/lm/ja/departure-calculator",
  "/lm/guide",
  "/tools/social-jet-lag-calculator",
];

function tripleLanguagesForEnSlug(enSlug: string) {
  const triple = AFFIRMATION_HREFLANG_TRIPLES.find((t) => t.en === enSlug);
  return triple ? alternatesFor(triple) : undefined;
}

export default function sitemap(): MetadataRoute.Sitemap {
  const staticEntries: MetadataRoute.Sitemap = STATIC_PATHS.map((p) => ({
    url: `${BASE_URL}${p}`,
  }));

  const blogEntries: MetadataRoute.Sitemap = loadAllBlogPosts().map((post) => ({
    url: `${BASE_URL}/blog/${post.slug}`,
    lastModified: post.date || undefined,
  }));

  // One hub per business (2026-10-18): each business's articles form their own cluster.
  const businessHubEntries: MetadataRoute.Sitemap = Object.keys(BUSINESSES).map((key) => ({
    url: `${BASE_URL}/blog/c/${key}`,
  }));

  // Hand-written Japanese Life Manager guides (separate from the Writer's /blog posts).
  const lmGuideEntries: MetadataRoute.Sitemap = LM_JA_GUIDES.map((g) => ({
    url: `${BASE_URL}/lm/guide/${g.slug}`,
    lastModified: g.date,
  }));

  const jaAffirmationEntries: MetadataRoute.Sitemap =
    JA_AFFIRMATION_PROBLEMS.map((problem) => {
      const triple = AFFIRMATION_HREFLANG_TRIPLES.find((t) => t.ja === problem.slug);
      const languages = triple ? alternatesFor(triple) : undefined;
      return {
        url: `${BASE_URL}/affirmation-app/ja/a/${problem.slug}`,
        ...(languages ? { alternates: { languages } } : {}),
      };
    });

  const enAffirmationEntries: MetadataRoute.Sitemap = allEnAffirmationSlugs().map(
    (slug) => {
      const languages = tripleLanguagesForEnSlug(slug);
      return {
        url: `${BASE_URL}/affirmation-app/a/${slug}`,
        ...(languages ? { alternates: { languages } } : {}),
      };
    },
  );

  const esAffirmationEntries: MetadataRoute.Sitemap = allEsAffirmationSlugs().map(
    (slug) => {
      const triple = AFFIRMATION_HREFLANG_TRIPLES.find((t) => t.es === slug);
      const languages = triple ? alternatesFor(triple) : undefined;
      return {
        url: `${BASE_URL}/affirmation-app/es/a/${slug}`,
        ...(languages ? { alternates: { languages } } : {}),
      };
    },
  );

  const kokoroTypeEntries: MetadataRoute.Sitemap = allKokoroTypeIds().map((type) => ({
    url: `${BASE_URL}/affirmation-app/ja/shindan/${type}`,
  }));

  const all = [
    ...staticEntries,
    ...jaAffirmationEntries,
    ...enAffirmationEntries,
    ...esAffirmationEntries,
    ...kokoroTypeEntries,
    ...lmGuideEntries,
    ...blogEntries,
    ...businessHubEntries,
  ];

  // Deduplicate by URL (defensive).
  const seen = new Set<string>();
  return all.filter((entry) => {
    if (seen.has(entry.url)) return false;
    seen.add(entry.url);
    return true;
  });
}
