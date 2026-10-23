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
CORE_PLAN = ROOT / 'docs/plans/2026-10-22-manager-core-execution-plan.md'
EXPECTED_E = [f'E{i:02d}' for i in range(1, 17)]
EXPECTED_F = ['F005', 'F006', 'F008', 'F009']
ALLOWED = {'done', 'todo', 'blocked', 'skipped'}
SYMBOLS = {'done': '✅', 'todo': '⬜', 'blocked': '⛔', 'skipped': '⏭️'}


def validate(tasks):
    if not isinstance(tasks, list):
        raise ValueError('expected an array of task objects')
    by_id = {t.get('id'): t for t in tasks if isinstance(t, dict)}
    if len(by_id) != len(tasks) or 'F009' not in by_id:
        raise ValueError('unique 113-task Manager registry and F009 gate required')
    order = by_id['F009']
    if (order.get('technical_execution_sequence') != EXPECTED_E
        or order.get('technical_execution_plan') != str(CORE_PLAN.relative_to(ROOT))
        or order.get('acceptance_sequence') != EXPECTED_F):
        raise ValueError('E01-E16 execution order/cursor or F acceptance order out of sync')
    completed = order.get('technical_execution_completed')
    receipts = order.get('technical_execution_receipts')
    if not isinstance(completed, list) or not isinstance(receipts, dict):
        raise ValueError('E01-E16 completed prefix and receipts are required')
    if completed != EXPECTED_E[:len(completed)]:
        raise ValueError('E01-E16 completed stages must be a contiguous ordered prefix')
    expected_cursor = EXPECTED_E[len(completed)] if len(completed) < len(EXPECTED_E) else None
    if ('technical_execution_cursor' not in order
        or order['technical_execution_cursor'] != expected_cursor):
        raise ValueError('E01-E16 cursor must name the next unfinished stage or be null after E16')
    for stage in completed:
        receipt = receipts.get(stage)
        if not isinstance(receipt, dict):
            raise ValueError(f'{stage} is complete without a receipt')
        run_id = receipt.get('run_id')
        full_suite_total = receipt.get('full_suite_total')
        minimum_suite_total = 504 if stage == 'E01' else 512
        if (receipt.get('status') != 'PASSED'
            or type(run_id) is not int or run_id <= 0
            or type(full_suite_total) is not int or full_suite_total < minimum_suite_total):
            raise ValueError(f'{stage} receipt does not meet the passed run and full-suite contract')
    acceptance_prefix_closed = False
    for gate_id in order['acceptance_sequence']:
        gate = by_id[gate_id]
        if (gate.get('evidence_scope') != 'OWNED_PUBLIC_DIGITAL_P2_ONLY'
            or gate.get('beneficiary_outcome') != 'NOT_MEASURED'):
            raise ValueError(f'{gate_id} must preserve P2-only scope and unmeasured beneficiary outcome')
        if gate.get('status') == 'done':
            if acceptance_prefix_closed:
                raise ValueError('F acceptance gates must be a contiguous ordered prefix')
            if completed != EXPECTED_E or order['technical_execution_cursor'] is not None:
                raise ValueError('F acceptance requires the complete E01-E16 passed prefix')
            evidence = gate.get('completion_evidence')
            if (not isinstance(evidence, list) or not evidence
                or any(not isinstance(path, str) or not path.strip() for path in evidence)):
                raise ValueError(f'{gate_id} completion evidence must be a nonempty list of paths')
        else:
            acceptance_prefix_closed = True
    if (by_id.get('F004', {}).get('status') != 'skipped'
        or by_id.get('F007', {}).get('status') != 'skipped'):
        raise ValueError('retired external prerequisites or unverified field gate status')
    # Validate the machine-readable sequence here. The separate contract test
    # validates headings in the actual plan; the renderer stays portable and
    # reproducible with only tasks.json, as required by R006.
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
        unfinished = [dep for dep in t['depends'] if by_id[dep]['status'] != 'done']
        if t['status'] == 'done' and unfinished:
            raise ValueError(f"done task has unfinished dependencies: {t['id']}")
        if t['status'] == 'skipped' and (not t.get('waiver_reason') or not t.get('waiver_scope')):
            raise ValueError(f"skipped task without waiver: {t['id']}")
        seen.add(t['id'])


def render(tasks):
    by_id = {t['id']: t for t in tasks}
    cursor = by_id['F009']['technical_execution_cursor']
    acceptance_sequence = by_id['F009']['acceptance_sequence']
    accepted_gates = sum(by_id[gate]['status'] == 'done' for gate in acceptance_sequence)
    beneficiary_outcomes = {by_id[gate].get('beneficiary_outcome', 'NOT_RECORDED')
                            for gate in acceptance_sequence}
    beneficiary_outcome = (next(iter(beneficiary_outcomes))
                           if len(beneficiary_outcomes) == 1 else 'MIXED_OR_UNRECORDED')
    execution_progress = (
        'E01–E16実装完了。F受入は別に証拠確認'
        if cursor is None else f'**現在の次タスク:** `{cursor}`'
    )
    groups = list(dict.fromkeys(t['section'] for t in tasks))
    sums = Counter(t['status'] for t in tasks)
    lines = [
      '# Manager — atomic learning & engineering backlog', '',
      'Status: 2026-10-22 JST. Manager-only task registry in `tasks.json`; the Life Manager project SSOT is unchanged.', '',
      f"Total: {len(tasks)} · Done: {sums['done']} · Todo: {sums['todo']} · Blocked: {sums['blocked']} · Skipped: {sums['skipped']}", '',
      '✅ = original acceptance and dependencies verified; ⬜ = acceptance incomplete (preparation may exist); ⛔ = outside dependency; ⏭️ = scientific waiver (not success). A research task is not evidence of real-world impact.', '',
      'Manager is a Buddhist AI entity / Digital Buddha with its own mission, source scope and runtime, even when its source is in the same GitHub repository. This identity does not establish consciousness, enlightenment or measured human benefit.', '',
      '## 唯一の実装順（E01〜E16を先に、一件ずつ）', '',
      '**ManagerのSSOT（状態・依存・現在位置）:** [tasks.json](tasks.json) の `F009.technical_execution_sequence` と `technical_execution_cursor`。Life Manager の別SSOTは変更しない。', '',
      execution_progress, '',
      '実装は **E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16** の順。各Eの合格条件は [Superpowers core plan](../plans/2026-10-22-manager-core-execution-plan.md)。先にF005等を実装する順序は廃止。', '',
      '**実装後に検証する受け入れ条件:** **F005 → F006 → F008 → F009**。Fはタスク台帳上の限定能力releaseの受け入れゲートであって、Eより先に着手する工程ではない。実際のP1/P2証拠がある条件から判定し、架空試験やGitHub Actions成功だけでは完了にしない。', '',
      '**対象外:** F004（第三者の資金管理者）とF007（施設所有者・屋内センサー）は `skipped`（未実施・未達成）で、実装の依存条件にしない。他者の設備・口座を操作する場合の権限は引き続き必要。', '',
      '**編集作業の優先順:** Manager本体・agentを先に完成させ、P01〜P07（日英記事、書籍、スライド、カルーセル、漫画、サイト）の新規制作は後段へ保留する。E実装の現在位置は移動しない。', '',
      '下のPhase 06表は受け入れ条件の一覧であり、時系列の作業順を示すものではない。', '',
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
      f'- Owned-public digital technical P2 acceptance: {accepted_gates}/{len(acceptance_sequence)} gates marked done.',
      f'- Beneficiary human outcome: {beneficiary_outcome}.', '',
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
