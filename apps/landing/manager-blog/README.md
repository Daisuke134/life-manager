# Manager article publication adapter

The canonical source is `Daisuke134/life-manager`. The existing full-site Next.js build and Netlify deployment remain in `Daisuke134/anicca-products`; no new hosting or second Manager implementation is created.

The reviewed article package is `docs/research/manager/publication/2026-10-19/manifest.json` in the same immutable canonical revision. Its article metadata and Markdown bytes become `data/research/manager-<topic>-ja/en.json`; hash-addressed images become `public/blog/manager/media/<sha256>.<extension>`. Internal source/evidence paths are not published in the public receipt.

Before the publishing repository's existing Next build, CI downloads `scripts/install.mjs` at a full canonical commit, checks the installer's pinned SHA-256, then sets `MANAGER_BLOG_REVISION` and runs the installer. The installer verifies `release-manifest.json` modules, validates the reviewed article package and all content hashes, stages the article JSON/media and applies narrowly guarded changes to the existing blog flow. A changed legacy interface fails the build instead of silently omitting Manager integration. The existing post-build marketing overlay, other businesses, Netlify functions and payment smoke remain intact.

`/blog/manager` groups English and Japanese articles in newest-first publication-date order. `/blog/c/manager` remains a category alias with canonical metadata pointing to `/blog/manager`. The main blog index stays topic-first without a standalone latest-articles list. Topic previews and collections retain publication-date order, and the archive remains available. The main index, article breadcrumbs and sitemap link to the canonical Manager collection. Article URLs stay flat, using the existing article renderer route. Only records with `project: "Manager"` opt into the safe extended renderer (tables, numbered lists, fenced code; raw HTML is escaped). Other articles use their original renderer.

Regenerate module integrity hashes after source edits:

```sh
node apps/landing/manager-blog/scripts/build-release-manifest.mjs
node --test apps/landing/manager-blog/tests/*.test.mjs
```

Test fixtures snapshot the pre-integration publishing blog interfaces for repeatability; they are not alternate production source. Production synchronization must run against the current publishing branch and preserve its unrelated posts/routes.

Promotion requires reviewed content, canonical PR/checks/merge, a publishing bridge-only PR/checks/merge, then live article/media hash readback and existing payment smoke. `public/blog/manager/release.json` binds the deployed articles and media to the canonical revision. A preview or local test is not a publication receipt.

Renderer-only releases may set `MANAGER_BLOG_CONTENT_REVISION` to an independently reviewed immutable publication commit while `MANAGER_BLOG_REVISION` selects installer/modules. Both must be full commit hashes. The public receipt records both. Without a separate content pin, content follows the code revision for backward compatibility. To publish new content when a separate pin exists, deliberately update the content pin after content review; changing only the renderer pin must not publish or remove articles.
