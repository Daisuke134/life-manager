"""Build data/teachings.json from SuttaCentral bilara-data (Sujato, CC0).
Raw files in scripts/raw-dhp-sujato/ were fetched from
https://github.com/suttacentral/bilara-data/tree/published/translation/en/sujato/sutta/kn/dhp
"""
import json, glob, os, re
here = os.path.dirname(__file__)
out = []
for f in sorted(glob.glob(os.path.join(here, 'raw-dhp-sujato', '*.json')), key=lambda p: int(os.path.basename(p).split('-')[0])):
    d = json.load(open(f))
    chapter = None
    verses = {}
    for k, v in d.items():
        uid, seg = k.split(':')
        if seg == '0.3':
            chapter = re.sub(r'^\d+\.\s*', '', v.strip())
        if seg.startswith('0.'):
            continue
        n = int(uid[3:])
        verses.setdefault(n, []).append(v.strip())
    for n, lines in sorted(verses.items()):
        text = ' '.join(l for l in lines if l)
        out.append({
            'id': f'dhp{n}', 'title': f'Dhammapada {n} ({chapter})', 'collection': 'Dhammapada',
            'chapter': chapter, 'teacher': 'The Buddha (attributed)', 'translator': 'Bhikkhu Sujato',
            'text': text, 'tags': [chapter.lower()] if chapter else [],
            'source_url': f'https://suttacentral.net/dhp{n}/en/sujato',
            'license': 'CC0 1.0 (SuttaCentral / Bhikkhu Sujato)'})
json.dump({'schema_version': 'anicca.monk-teachings.v1', 'count': len(out),
           'sources': [{'name': 'SuttaCentral bilara-data', 'url': 'https://github.com/suttacentral/bilara-data', 'license': 'CC0 1.0'}],
           'teachings': out}, open(os.path.join(here, '..', 'data', 'teachings.json'), 'w'), ensure_ascii=False, indent=0)
print(len(out))
