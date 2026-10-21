#!/usr/bin/env python3
"""Render the scoped Manager backlog from the existing JSON task registry.

The JSON file is NEVER rebuilt from hard-coded defaults: new task additions,
dependencies and statuses are retained. Use --check to verify a committed view.
"""
import argparse
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/roadmap/tasks.json'
VIEW = ROOT / 'docs/roadmap/ATOMIC_BACKLOG.md'
ALLOWED = {'done', 'todo', 'blocked', 'skipped'}
SYMBOLS = {'done': '✅', 'todo': '⬜', 'blocked': '⛔', 'skipped': '⏭️'}


def validate(tasks):
    if not isinstance(tasks, list):
        raise ValueError('expected an array of task objects')
    seen = set()
    for t in tasks:
        if t['id'] in seen:
            raise ValueError(f"duplicate id: {t['id']}")
        if t['status'] not in ALLOWED:
            raise ValueError(f"invalid status: {t['id']}")
        if not t['learn'] or not t['change'] or not t['verify']:
            raise ValueError(f"task lacks atomic acceptance: {t['id']}")
        if not set(t['depends']) <= seen:
            raise ValueError(f"dependency missing/forward/cyclic: {t['id']}")
        if t['status'] == 'skipped' and (not t.get('waiver_reason') or not t.get('waiver_scope')):
            raise ValueError(f"skipped task without waiver: {t['id']}")
        seen.add(t['id'])


def render(tasks):
    groups = list(dict.fromkeys(t['section'] for t in tasks))
    sums = Counter(t['status'] for t in tasks)
    lines = [
      '# Manager — atomic learning & engineering backlog', '',
      'Status: 2026-10-22 JST. Manager-only task registry in `tasks.json`; the Life Manager project SSOT is unchanged.', '',
      f"Total: {len(tasks)} · Done: {sums['done']} · Todo: {sums['todo']} · Blocked: {sums['blocked']} · Skipped: {sums['skipped']}", '',
      '✅ = original acceptance and dependencies verified; ⬜ = acceptance incomplete (preparation may exist); ⛔ = outside dependency; ⏭️ = scientific waiver (not success). A research task is not evidence of real-world impact.', '',
      'Manager has a separate product identity, source scope and runtime, even when its source is in the same GitHub repository.', '',
      '## Definitions of done', '',
      '- Study: source-backed research note and stated verification succeeds.',
      '- Implementation: tests and documented acceptance conditions pass.',
      '- Real-world intervention: external proof plus harm/comparator accounting; simulation never proves beneficiary benefit.', '',
    ]
    for group in groups:
        lines.extend([f'## {group}', '', '| 状態・ID | 依存 | 理解する | 作る・更新する | 完了の確認 |', '|---|---|---|---|---|'])
        for t in tasks:
            if t['section'] != group:
                continue
            dependencies = ', '.join(t['depends']) or '—'
            ext = '' if t.get('external', 'none')=='none' else ' **外部条件:** '+t['external']
            if t['status'] == 'skipped':
                ext += ' **Waiver (not completed):** '+t['waiver_reason']
            fields = (SYMBOLS[t['status']]+' `'+t['id']+'`',dependencies,t['learn'],t['change'],t['verify']+ext)
            safe_fields = [str(field).replace('|', '\\|').replace('\n',' ') for field in fields]
            lines.append('| ' + ' | '.join(safe_fields) + ' |')
        lines.append('')
    lines.extend([
      '## Evidence and provenance', '',
      '- R006 rights register: `docs/research-rights.md` and `docs/research/source-rights.json`. Unknown downstream permissions remain HOLD.',
      '- imozuru research uses original links and local short excerpts; third-party original text is not automatically redistributable.',
      '- No Manager field intervention or human suffering reduction has yet been proven.', '',
      '- Phase06–12 implementation evidence and remaining original acceptances: `docs/verification/PHASE06_TO_12_ACCEPTANCE_20261022.md`.', '',
    ])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='compare view with registry without editing anything')
    options = parser.parse_args()
    tasks = json.loads(DATA.read_text(encoding='utf-8'))
    validate(tasks)
    output = render(tasks)
    if options.check:
        if not VIEW.exists() or VIEW.read_text(encoding='utf-8') != output:
            raise SystemExit('BACKLOG VIEW OUT OF SYNC; run python3 scripts/make_roadmap.py')
        print(f'PASS {len(tasks)} tasks; task JSON untouched')
    else:
        VIEW.write_text(output, encoding='utf-8')
        print(f"Rendered {len(tasks)} tasks; status={dict(Counter(x['status'] for x in tasks))}")

if __name__ == '__main__':
    main()
