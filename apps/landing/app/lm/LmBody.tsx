'use client';

import { Reveal } from '@/components/site/taste';
import { useLaunchLocale } from '@/lib/launchLocale';
import { launchStrings } from '@/lib/launchStrings';

const WEB_APP_CTA_URL = 'https://life-call-production.up.railway.app/lm?start_calendar=1';
const REPOSITORY_URL = 'https://github.com/Daisuke134/life-manager';

// The public landing page starts the existing Web Calendar connection in the same tab.
export default function LmBody() {
  const { locale } = useLaunchLocale();
  const t = launchStrings[locale].lm;
  return (
    <main className="w-full overflow-hidden px-4 pb-24 pt-12 md:pt-20">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <section className="relative border-y border-[hsl(var(--border))] py-10 md:py-16">
            <div className="pointer-events-none absolute -right-24 top-4 h-72 w-72 rounded-full bg-[hsl(var(--gold)/0.08)] blur-3xl" />
            <div className="relative grid gap-12 lg:grid-cols-[1.35fr_0.65fr] lg:items-end">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[hsl(var(--gold))]">
                  {t.publicEyebrow}
                </p>
                <h1 className="mt-5 max-w-4xl font-display text-4xl font-semibold leading-[0.98] tracking-[-0.04em] text-[hsl(var(--text-primary))] md:text-7xl">
                  {t.publicTitle}
                </h1>
                <p className="mt-7 max-w-2xl text-base leading-8 text-[hsl(var(--text-secondary))] md:text-lg">
                  {t.publicBody}
                </p>
                <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                  <a
                    href={WEB_APP_CTA_URL}
                    className="inline-flex items-center justify-center rounded-pill bg-[hsl(var(--gold))] px-7 py-3 text-sm font-semibold text-black transition-all hover:-translate-y-0.5 hover:brightness-95 active:translate-y-0"
                  >
                    {t.primaryCta}
                  </a>
                  <a
                    href={REPOSITORY_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center justify-center rounded-pill border border-[hsl(var(--border))] px-7 py-3 text-sm font-semibold text-[hsl(var(--text-primary))] transition-all hover:border-[hsl(var(--gold))]"
                  >
                    {t.sourceCta}
                  </a>
                </div>
              </div>

              <aside className="border-l border-[hsl(var(--border))] pl-6 md:pl-8">
                <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[hsl(var(--text-secondary))]">
                  {t.surfacesLabel}
                </p>
                <div className="mt-5 space-y-4">
                  <p className="border-t border-[hsl(var(--border))] pt-4 font-display text-xl text-[hsl(var(--text-primary))]">
                    {t.localSurface}
                  </p>
                  <p className="border-t border-[hsl(var(--border))] pt-4 font-display text-xl text-[hsl(var(--text-primary))]">
                    {t.cloudSurface}
                  </p>
                </div>
              </aside>
            </div>
          </section>
        </Reveal>

        <Reveal>
          <section className="py-16 md:py-24">
            <h2 className="max-w-3xl font-display text-3xl tracking-[-0.03em] text-[hsl(var(--text-primary))] md:text-5xl">
              {t.organsTitle}
            </h2>
            <div className="mt-10 grid border-y border-[hsl(var(--border))] md:grid-cols-3">
              {t.organs.map((organ) => (
                <article key={organ.index} className="border-b border-[hsl(var(--border))] py-7 md:border-b-0 md:border-r md:px-7 md:first:pl-0 md:last:border-r-0 md:last:pr-0">
                  <p className="font-mono text-xs text-[hsl(var(--gold))]">{organ.index}</p>
                  <h3 className="mt-8 font-display text-2xl text-[hsl(var(--text-primary))]">{organ.title}</h3>
                  <p className="mt-4 text-sm leading-7 text-[hsl(var(--text-secondary))]">{organ.body}</p>
                </article>
              ))}
            </div>
          </section>
        </Reveal>

        <div className="grid gap-6 lg:grid-cols-2">
          <Reveal>
            <section className="h-full rounded-card border border-[hsl(var(--border))] bg-[hsl(var(--surface))] p-7 md:p-10">
              <p className="font-mono text-xs uppercase tracking-[0.2em] text-[hsl(var(--gold))]">{t.wedgeEyebrow}</p>
              <h2 className="mt-5 font-display text-3xl tracking-[-0.02em] text-[hsl(var(--text-primary))]">
                {t.wedgeTitle}
              </h2>
              <p className="mt-5 text-sm leading-7 text-[hsl(var(--text-secondary))]">{t.wedgeBody}</p>
            </section>
          </Reveal>
          <Reveal>
            <section className="h-full rounded-card border border-[hsl(var(--gold)/0.5)] bg-[hsl(var(--gold)/0.06)] p-7 md:p-10">
              <p className="font-mono text-xs uppercase tracking-[0.2em] text-[hsl(var(--gold))]">{t.proofLabel}</p>
              <h2 className="mt-5 font-display text-3xl tracking-[-0.02em] text-[hsl(var(--text-primary))]">
                {t.evidenceTitle}
              </h2>
              <p className="mt-5 text-sm leading-7 text-[hsl(var(--text-secondary))]">{t.evidenceBody}</p>
              <p className="mt-4 border-t border-[hsl(var(--border))] pt-4 font-mono text-xs leading-6 text-[hsl(var(--text-secondary))]">
                {t.evidenceBoundary}
              </p>
            </section>
          </Reveal>
        </div>
      </div>
    </main>
  );
}
