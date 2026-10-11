"""Company-bound resumes composed only from existing candidate facts."""
from __future__ import annotations

import asyncio
import base64
import hashlib
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys

from .application_reporting import _write_private_json
from .browser_agent.direct_cdp import DirectCDPPage
from .browser_agent.candidate_memory import CandidateMemoryView

SECTIONS = frozenset({'Summary', 'Experience', 'Projects', 'Education', 'Skills'})


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _target(row: dict) -> dict:
    return {key: str(row[key]) for key in ('application_id', 'company', 'title', 'canonical_url')}


def _directory(root: Path, row: dict) -> Path:
    root = Path(root).expanduser()
    directory = root / 'tailored' / hashlib.sha256(str(row['application_id']).encode()).hexdigest()
    if root.is_symlink() or (root / 'tailored').is_symlink() or directory.is_symlink():
        raise ValueError('unsafe_resume_directory')
    return directory


def compose(row: dict, memory: CandidateMemoryView, sections: dict) -> dict:
    if not isinstance(sections, dict) or not sections or any(key not in SECTIONS for key in sections):
        raise ValueError('invalid_section')
    facts = {item['concept']: item['claim'] for item in memory.grounding_facts()}
    ids = []
    blocks = []
    for heading, concepts in sections.items():
        if not isinstance(concepts, list) or not concepts:
            raise ValueError('invalid_fact_selection')
        for concept in concepts:
            if not isinstance(concept, str) or concept not in facts:
                raise ValueError('unknown_fact_id')
            if concept in ids:
                raise ValueError('duplicate_fact_id')
            ids.append(concept)
        blocks.append('<section><h2>' + heading + '</h2><ul>' + ''.join('<li>' + escape(facts[item]) + '</li>' for item in concepts) + '</ul></section>')
    name = memory.get('candidate.name')
    if not isinstance(name, str) or not name:
        raise ValueError('candidate_name_missing')
    contacts = []
    for key in ('candidate.application_email', 'candidate.base', 'candidate.linkedin_url', 'candidate.github_url'):
        if key in memory.concepts():
            value = memory.get(key)
            if isinstance(value, str) and value:
                contacts.append(escape(value))
    target = _target(row)
    html = ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<style>@page{size:A4;margin:13mm 16mm}body{font:10pt Arial,sans-serif;color:#111;line-height:1.3}h1{font-size:20pt;margin:0 0 4pt}h2{font-size:11pt;margin:12pt 0 4pt;border-bottom:1px solid #aaa}p{margin:3pt 0}ul{margin:0;padding-left:14pt}li{margin:0 0 5pt}section{break-inside:avoid}</style></head><body>'
            '<h1>' + escape(name) + '</h1><p>' + ' | '.join(contacts) + '</p><p>Application: '
            + escape(target['company']) + ' — ' + escape(target['title']) + '</p>' + ''.join(blocks) + '</body></html>')
    return {'target': target, 'profile_sha256': _digest(memory.value), 'fact_ids': ids,
            'html': html, 'claims': [facts[item] for item in ids]}


async def render_pdf(html: str, claims: list[str], destination: Path) -> bytes:
    root = Path(__file__).resolve().parents[3]
    script = root / 'skills/browser/scripts/cdp_context_lease.py'
    task = 'job-search-resume-render'
    env = os.environ.copy()
    env['CLOAK_CDP_BASE_URL'] = 'http://localhost:9222'
    if env.get('CLOAK_LEASE_HOLDER_PID'):
        env['AI_BROWSER_HOLDER_PID'] = env['CLOAK_LEASE_HOLDER_PID']

    async def lease_command(*arguments):
        process = await asyncio.create_subprocess_exec(sys.executable, str(script), *arguments,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
        out, _err = await asyncio.wait_for(process.communicate(), timeout=45)
        if process.returncode != 0:
            raise ValueError('resume_render_lease_failed')
        result = json.loads(out)
        if result.get('ok') is not True:
            raise ValueError('resume_render_lease_failed')
        return result

    lease = await lease_command('acquire', task, 'about:blank', '--no-seed')
    page = DirectCDPPage(lease['ws'], lease['target_id'])
    try:
        await page.connect()
        frame = await page.call('Page.getFrameTree')
        await page.call('Page.setDocumentContent', {'frameId': frame['frameTree']['frame']['id'], 'html': html})
        result = await page.call('Page.printToPDF', {'printBackground': True, 'preferCSSPageSize': True})
        data = base64.b64decode(result['data'])
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.write_bytes(data)
        destination.chmod(0o600)
        info = subprocess.run(['pdfinfo', str(destination)], capture_output=True, text=True, timeout=10, check=True).stdout
        pages = [line.split(':', 1)[1].strip() for line in info.splitlines() if line.startswith('Pages:')]
        if pages != ['1']:
            raise ValueError('resume_page_budget_exceeded')
        text = subprocess.run(['pdftotext', str(destination), '-'], capture_output=True, text=True, timeout=10, check=True).stdout
        normalized = ' '.join(text.split())
        if any(' '.join(claim.split()) not in normalized for claim in claims):
            raise ValueError('resume_claim_text_missing')
        return data
    finally:
        await page.close()
        await lease_command('release', task, '--token', lease['token'], '--generation', str(lease['generation']))


def store_artifact(root: Path, row: dict, material: dict, pdf: bytes) -> dict:
    if not pdf.startswith(b'%PDF-'):
        raise ValueError('invalid_resume_pdf')
    directory = _directory(root, row)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    directory.parent.chmod(0o700)
    digest = hashlib.sha256(pdf).hexdigest()
    path = directory / (digest + '.pdf')
    if path.is_symlink():
        raise ValueError('unsafe_resume_path')
    if path.exists() and path.read_bytes() != pdf:
        raise ValueError('immutable_resume_collision')
    if not path.exists():
        path.write_bytes(pdf)
        path.chmod(0o600)
    result = {'target': material['target'], 'profile_sha256': material['profile_sha256'],
              'fact_ids': material['fact_ids'], 'resume_sha256': digest, 'resume_file': path.name,
              'resume_variant': 'company_tailored', 'posting_language': 'en'}
    _write_private_json(directory / 'manifest.json', result)
    return result


def load_artifact(root: Path, row: dict, memory: CandidateMemoryView) -> dict | None:
    directory = _directory(root, row)
    manifest = directory / 'manifest.json'
    if not manifest.exists():
        return None
    if manifest.is_symlink() or manifest.stat().st_mode & 0o077:
        raise ValueError('unsafe_resume_manifest')
    result = json.loads(manifest.read_text())
    if result['target'] != _target(row):
        raise ValueError('target_binding_mismatch')
    if result['profile_sha256'] != _digest(memory.value):
        return None
    name = result['resume_file']
    if Path(name).name != name:
        raise ValueError('unsafe_resume_path')
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('unsafe_resume_path')
    if hashlib.sha256(path.read_bytes()).hexdigest() != result['resume_sha256']:
        raise ValueError('resume_hash_mismatch')
    return {**result, 'resume_path': str(path)}
