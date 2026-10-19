// One hub per business on /blog/c/<key>. Every Life Manager business publishes to /blog, and
// the old shared `project` field lumped LINE stickers and eBook posts under capafy-distribute,
// so the blog read as one undifferentiated stream (2026-10-18). Post URLs never move; the hubs,
// breadcrumbs and same-business related links give each business its own topical cluster.
export const BUSINESSES = {
  'ai-creator-tools': {
    label: 'AI Creator Tools',
    intro: 'Hooks, short-form scripts and video ideas from the Capafy agents we build: Hook Lab, TikTok Script Pro and YouTube Script Writer.',
  },
  'line-stickers': {
    label: 'LINE Stickers',
    intro: 'Original LINE sticker sets, the story behind each set and where to get them.',
  },
  ebook: {
    label: 'The Anicca Reset (eBook)',
    intro: 'Short readings and practices from The Anicca Reset.',
  },
  'ai-voice-tools': {
    label: 'AI Voice Tools',
    intro: 'Hands-on guides to AI voice, dubbing and transcription tools for creators.',
  },
  anicca: {
    label: 'Anicca App & Mindfulness',
    intro: 'The Anicca app, mindfulness and impermanence in everyday life.',
  },
  notes: {
    label: 'Build Notes',
    intro: 'How we build and run autonomous agents: engineering notes and experiments.',
  },
};

export function businessOf(slug, project) {
  const s = String(slug || '');
  const p = String(project || '').toLowerCase();
  if (s.startsWith('line-sticker') || p.includes('line') && p.includes('スタンプ')) return 'line-stickers';
  if (s.startsWith('ebook-')) return 'ebook';
  if (/^(elevenlabs|elevenagents)|ai-voice/.test(s) || /affiliate|ai voice|ai customer support/.test(p)) return 'ai-voice-tools';
  if (s.startsWith('anicca-') || p.startsWith('anicca') || /^ai-(mindfulness|responsibility)/.test(s)) return 'anicca';
  if (p === 'capafy-distribute' || s.startsWith('capafy-')) return 'ai-creator-tools';
  return 'notes';
}
