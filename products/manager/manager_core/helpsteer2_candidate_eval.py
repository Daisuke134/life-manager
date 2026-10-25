"""Private, dev-only likelihood of exact published HelpSteer2 candidates.

No generation, training, judge, intervention or benefit measurement. Optional
ML packages are imported only by run_local after every local binding passes.
Source hashes establish consistency, not authenticity or privacy certification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import gzip
from hashlib import sha256
from io import BytesIO
import importlib.metadata
import json
from math import isfinite
from pathlib import Path
import re
from types import MappingProxyType

from .models.source import Source
from .outcome_bench import EvidenceBundle, reproduction_manifest

PROTOCOL_SHA256 = '586d8701a26305ea56ffab0d095db72d4fb64974977528d7581511ff7c8ef529'
UNAVAILABLE = 'HELPSTEER2_DEV_UNAVAILABLE'
_REVISION = '990b2711a36180dd19d9c94b8627844866f8982a'
_URL = 'https://huggingface.co/datasets/nvidia/HelpSteer2'
_QUALITY = ('helpfulness', 'correctness', 'coherence', 'complexity', 'verbosity')
_POLICIES = ('BASE_QWEN', 'SHORTER_CANDIDATE_RULE', 'NO_ACTION')
_RIGHTS_SHA256 = '0b76b970e877dc17a6fc21c18979c9c7efaf4e1e6053c01a9c13577ee2920a41'


def _require(condition):
    if not condition:
        raise ValueError(UNAVAILABLE)


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _json(payload):
    return json.loads(payload, object_pairs_hook=_object,
                      parse_constant=lambda _: _require(False))


def _hash(text):
    _require(type(text) is str and bool(text))
    return sha256(text.encode('utf-8')).hexdigest()


def validate_protocol(payload: bytes, expected_sha256: str) -> dict:
    """Both supplied and built-in hashes must bind the immutable protocol."""
    try:
        _require(type(payload) is bytes and expected_sha256 == PROTOCOL_SHA256)
        _require(sha256(payload).hexdigest() == PROTOCOL_SHA256)
        return _json(payload)
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def validate_rights(manifest: dict, protocol: dict) -> dict:
    """The operating-purpose holds are independent of CC BY's legal scope."""
    try:
        _require(manifest['schema'] == 'manager.source-rights.v1')
        matches = [r for r in manifest['sources'] if r['id'] == 'helpsteer2-candidates']
        _require(len(matches) == 1)
        record = matches[0]
        _require(sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                                  ensure_ascii=False).encode()).hexdigest() == _RIGHTS_SHA256)
        _require(record['license_expression'] == 'CC-BY-4.0')
        _require(record['source_url'] == _URL + '/tree/' + _REVISION)
        _require(record['license_evidence_url'] == _URL + '/blob/' + _REVISION + '/README.md')
        _require(record['license_evidence_sha'] == protocol['dataset_revision'] == _REVISION)
        expected = {key: 'allowed_with_conditions' for key in
                    ('study_read', 'local_research', 'commercial_evaluation')}
        expected.update({key: 'hold' for key in
                         ('commercial_training', 'product_use', 'raw_redistribution')})
        _require(record['permissions'] == expected)
        _require(record['artifact'] == {
            'revision': _REVISION, 'files': protocol['source_artifacts'],
            'role': 'dev_candidate_evaluation_only', 'publication': 'metadata_only'})
        _require(record['license_review'] == {
            'declaration': 'dataset_card', 'independent_license_file': 'ABSENT',
            'cc_by_4_legalcode': 'REVIEWED', 'third_party_privacy_rights': 'NOT_GUARANTEED'})
        _require(record['attribution']['creators'] == ['NVIDIA'])
        _require(record['attribution']['license_url'] == 'https://creativecommons.org/licenses/by/4.0/')
        _require(type(record['attribution']['changes']) is str and bool(record['attribution']['changes']))
        _require(type(record['requirements']) is list and bool(record['requirements'])
                 and all(type(x) is str and bool(x) for x in record['requirements']))
        return _json(json.dumps(record))
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def _verify_file(path, pin, *, source_id, url):
    try:
        path = Path(path)
        _require(path.is_file() and not path.is_symlink())
        payload = path.read_bytes()
        _require(len(payload) == pin['bytes'])
        source = Source(source_id, url, 'CC-BY-4.0', 'allowed_with_conditions', pin['sha256'],
                        datetime.fromtimestamp(path.stat().st_mtime, timezone.utc), 'public_nonpersonal')
        source.verify_content(payload)
        return source
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def _verify_model(directory, pins):
    directory = Path(directory)
    _require(directory.is_dir() and not directory.is_symlink())
    _require({p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()} == set(pins))
    for name, pin in pins.items():
        path = directory / name
        _require(path.is_file() and not path.is_symlink() and path.stat().st_size == pin['bytes'])
        digest = sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        _require(digest.hexdigest() == pin['sha256'])


@dataclass(frozen=True)
class CandidateCase:
    row_id: int
    prompt_sha256: str
    response_sha256: tuple[str, str]
    human_choice: int
    preference_strength: int
    quality_rows: tuple[int, int]
    quality_labels: tuple = field(repr=False)
    full_sequence_token_counts: tuple[int, int]
    prompt: str = field(repr=False)
    responses: tuple[str, str] = field(repr=False)
    native_split: str = 'train'
    semantic_split: str = 'train'


def _reconstruct_cases(specs, preference_rows, quality_rows):
    """Join original quality train rows by exact text; never accept caller gold.

    Private helper permits fictional fixtures. The only executable research
    entry obtains specs and rows from hash-verified original local files.
    """
    try:
        _require(len(specs) == 8)
        ids = [s['preference_row_1based'] for s in specs]
        _require(all(type(i) is int and 1 <= i <= len(preference_rows) for i in ids)
                 and len(set(ids)) == 8)
        wanted = set()
        for spec in specs:
            _require(spec['native_preference_split'] == 'train')
            row = preference_rows[spec['preference_row_1based'] - 1]
            _require(row['split'] == 'train')  # raw train -> semantic train, never val.
            _require(_hash(row['prompt']) == spec['prompt_sha256'])
            for i in (1, 2):
                response = row[f'response_{i}']
                _require(_hash(response) == spec['response_sha256'][i - 1])
                wanted.add((row['prompt'], response))
        joined = {}
        for index, row in enumerate(quality_rows, 1):
            key = (row['prompt'], row['response'])
            if key in wanted:
                _require(key not in joined)
                labels = {k: row[k] for k in _QUALITY}
                _require(all(type(v) is int and 0 <= v <= 4 for v in labels.values()))
                joined[key] = (index, MappingProxyType(labels))
        _require(set(joined) == wanted)
        cases = []
        for spec in specs:
            row_id = spec['preference_row_1based']
            row = preference_rows[row_id - 1]
            strength = row['preference_strength']
            _require(type(strength) is int and strength in (-3, -2, -1, 1, 2, 3))
            pairs = [joined[(row['prompt'], row[f'response_{i}'])] for i in (1, 2)]
            _require(len(spec['full_sequence_token_counts']) == 2 and all(
                type(n) is int and 1 <= n <= 256 for n in spec['full_sequence_token_counts']))
            cases.append(CandidateCase(row_id, spec['prompt_sha256'], tuple(spec['response_sha256']),
                1 if strength < 0 else 2, strength, tuple(p[0] for p in pairs), tuple(p[1] for p in pairs),
                tuple(spec['full_sequence_token_counts']), row['prompt'],
                (row['response_1'], row['response_2'])))
        _require(len({c.prompt_sha256 for c in cases}) == 8)
        return tuple(cases)
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def _read_rows(path, source):
    # Parse the very bytes that were verified, rather than re-open unbound text.
    payload = Path(path).read_bytes()
    source.verify_content(payload)
    with gzip.open(BytesIO(payload), 'rt', encoding='utf-8') as stream:
        return [_json(line) for line in stream]


def load_verified_inputs(*, protocol_path, expected_sha256, data_dir, model_dir, rights_path, code_version):
    """All configuration/data/model guards run before any optional ML import."""
    try:
        _require(type(code_version) is str and re.fullmatch('[a-f0-9]{40}', code_version) is not None)
        protocol = validate_protocol(Path(protocol_path).read_bytes(), expected_sha256)
        rights = validate_rights(_json(Path(rights_path).read_bytes()), protocol)
        data_dir = Path(data_dir)
        _require(data_dir.is_dir() and not data_dir.is_symlink())
        sources = {}
        for name, pin in protocol['source_artifacts'].items():
            sources[name] = _verify_file(data_dir / name, pin, source_id='helpsteer2:' + name,
                url=_URL + '/resolve/' + _REVISION + '/' + name)
        _verify_model(model_dir, protocol['model_files'])
        preferences = _read_rows(data_dir / 'preference/preference.jsonl.gz', sources['preference/preference.jsonl.gz'])
        quality = _read_rows(data_dir / 'train.jsonl.gz', sources['train.jsonl.gz'])
        _require(len(preferences) == 9125 and len(quality) == 20324)
        _require(sum(r['split'] == 'train' for r in preferences) == 8677
                 and sum(r['split'] == 'val' for r in preferences) == 448)
        cases = _reconstruct_cases(protocol['dev_cases'], preferences, quality)
        return protocol, rights, sources, cases
    except Exception:
        raise ValueError(UNAVAILABLE) from None


@dataclass(frozen=True)
class CompletionMask:
    input_ids: tuple[int, ...] = field(repr=False)
    labels: tuple[int, ...] = field(repr=False)
    scored_tokens: int


def completion_mask(prompt_ids, full_ids):
    """Keep native causal shifting: labels at positions >=1 through EOS only."""
    try:
        prompt, full = tuple(prompt_ids), tuple(full_ids)
        _require(bool(prompt) and len(prompt) < len(full) <= 256)
        _require(all(type(t) is int and t >= 0 for t in (*prompt, *full)))
        _require(full[:len(prompt)] == prompt)
        completion = full[len(prompt):]
        _require(completion.count(151645) == 1)
        stop = len(prompt) + completion.index(151645)
        labels = tuple(t if len(prompt) <= i <= stop else -100 for i, t in enumerate(full))
        count = sum(t != -100 for t in labels[1:])
        _require(count > 0)
        return CompletionMask(full, labels, count)
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def _choose(values, hashes):
    _require(len(values) == len(hashes) == 2)
    return min(range(2), key=lambda i: (values[i], hashes[i])) + 1, values[0] == values[1]


def _summary(rows):
    counts = {state: sum(r['status'] == state for r in rows)
              for state in ('COMPLETED', 'FAILED', 'ABSTAIN', 'NOT_RUN', 'UNKNOWN')}
    covered = counts['COMPLETED']
    correct = sum(r['status'] == 'COMPLETED' and r['choice'] == r['human_choice'] for r in rows)
    return dict(assigned=len(rows), attempted=len(rows) - counts['NOT_RUN'],
                completed=covered + counts['ABSTAIN'], covered=covered,
                failed=counts['FAILED'], abstained=counts['ABSTAIN'],
                unknown=counts['UNKNOWN'], unattempted=counts['NOT_RUN'],
                correct=correct, conditional_accuracy=correct / covered if covered else None,
                coverage=covered / len(rows), nll=None, groups=rows)


def _empty_results(cases):
    rows = []
    for case in cases:
        rows.append(dict(preference_row_1based=case.row_id, prompt_sha256=case.prompt_sha256,
            response_sha256=list(case.response_sha256), native_preference_split=case.native_split,
            semantic_split=case.semantic_split, human_choice=case.human_choice,
            preference_strength=case.preference_strength, quality_train_rows_1based=list(case.quality_rows),
            published_quality_labels=[dict(q) for q in case.quality_labels],
            full_sequence_token_counts=list(case.full_sequence_token_counts),
            completion_token_counts=None, status='NOT_RUN', choice=None, tie=None, nll=None))
    return dict(policies={p: _summary(_json(json.dumps(rows))) for p in _POLICIES},
        model_requests=dict(assigned=16, attempted=0, completed=0, failed=0, unknown=0, unattempted=16))


def evaluate_cases(cases, encode, mean_loss, *, progress=None):
    """Single fixed batch; fail-stop model lane, no retry; preserve rule coverage.

    Injection seam is for stdlib synthetic tests. run_local is the guarded
    research entry. Root watchdog alone handles process interruption/unknowns.
    """
    _require(len(cases) == 8 and len({c.row_id for c in cases}) == 8)
    initial = _empty_results(cases)
    results = {p: initial['policies'][p]['groups'] for p in _POLICIES}
    requests = initial['model_requests']

    def snapshot():
        result = dict(policies={p: _summary(rows) for p, rows in results.items()}, model_requests=requests)
        if progress is not None:
            progress(result)
        return result

    snapshot()
    encoded = []
    for case in cases:
        try:
            masks = tuple(encode(case))
            _require(len(masks) == 2 and all(type(m) is CompletionMask for m in masks))
            _require(tuple(len(m.input_ids) for m in masks) == case.full_sequence_token_counts)
            encoded.append(masks)
        except Exception:
            encoded.append(None)
    for index, (case, masks) in enumerate(zip(cases, encoded)):
        for policy in _POLICIES:
            results[policy][index]['completion_token_counts'] = [m.scored_tokens for m in masks] if masks else None
        results['NO_ACTION'][index]['status'] = 'ABSTAIN'
        rule = results['SHORTER_CANDIDATE_RULE'][index]
        if masks is None:
            rule['status'] = 'FAILED'
        else:
            rule['choice'], rule['tie'] = _choose(tuple(m.scored_tokens for m in masks), case.response_sha256)
            rule['status'] = 'COMPLETED'
        results['BASE_QWEN'][index]['nll'] = [None, None]
    snapshot()
    stopped = False
    for index, (case, masks) in enumerate(zip(cases, encoded)):
        base = results['BASE_QWEN'][index]
        if stopped:
            continue
        if masks is None:
            base['status'] = 'FAILED'
            stopped = True
            snapshot()
            continue
        losses = []
        for i, mask in enumerate(masks):
            requests['attempted'] += 1
            requests['unattempted'] -= 1
            requests['unknown'] += 1
            base['status'] = 'UNKNOWN'
            snapshot()  # Persist uncertainty BEFORE a potentially interrupted forward.
            try:
                value = mean_loss(mask)
                _require(type(value) in (int, float) and isfinite(value) and value >= 0)
                total = value * mask.scored_tokens
                _require(isfinite(total))
                base['nll'][i] = dict(mean=value, summed=total, scored_tokens=mask.scored_tokens)
                losses.append(value)
                requests['completed'] += 1
            except Exception:
                requests['failed'] += 1
                base['status'] = 'FAILED'
                stopped = True
            requests['unknown'] -= 1
            if stopped:
                snapshot()
                break
            if i == 0:
                snapshot()
        if not stopped:
            base['choice'], base['tie'] = _choose(losses, case.response_sha256)
            base['status'] = 'COMPLETED'
            snapshot()
    return snapshot()


def _validate_results(results):
    """Allowlist numeric/hash metadata so an export cannot carry source text."""
    _require(type(results) is dict and set(results) == {'policies', 'model_requests'})
    _require(set(results['policies']) == set(_POLICIES))
    for policy, summary in results['policies'].items():
        rows = summary['groups']
        _require(type(rows) is list and len(rows) == 8)
        _require(len({r['preference_row_1based'] for r in rows}) == 8)
        for row in rows:
            _require(set(row) == {'preference_row_1based', 'prompt_sha256', 'response_sha256',
                'native_preference_split', 'semantic_split', 'human_choice', 'preference_strength',
                'quality_train_rows_1based', 'published_quality_labels', 'full_sequence_token_counts',
                'completion_token_counts', 'status', 'choice', 'tie', 'nll'})
            _require(type(row['preference_row_1based']) is int and row['preference_row_1based'] > 0)
            _require(row['native_preference_split'] == row['semantic_split'] == 'train')
            _require(type(row['human_choice']) is int and row['human_choice'] in (1, 2))
            _require(type(row['preference_strength']) is int and row['preference_strength'] in (-3, -2, -1, 1, 2, 3))
            _require(row['human_choice'] == (1 if row['preference_strength'] < 0 else 2))
            _require(type(row['response_sha256']) is list and len(row['response_sha256']) == 2)
            _require(all(type(h) is str and re.fullmatch('[a-f0-9]{64}', h) is not None
                         for h in [row['prompt_sha256'], *row['response_sha256']]))
            for key in ('quality_train_rows_1based', 'full_sequence_token_counts', 'completion_token_counts'):
                values = row[key]
                if key == 'completion_token_counts' and values is None:
                    continue
                _require(type(values) is list and len(values) == 2 and all(type(n) is int and n > 0 for n in values))
                if key != 'quality_train_rows_1based':
                    _require(all(n <= 256 for n in values))
            labels = row['published_quality_labels']
            _require(type(labels) is list and len(labels) == 2)
            for item in labels:
                _require(set(item) == set(_QUALITY) and all(type(n) is int and 0 <= n <= 4 for n in item.values()))
            _require(row['status'] in ('COMPLETED', 'FAILED', 'ABSTAIN', 'NOT_RUN', 'UNKNOWN'))
            _require(row['choice'] is None or (type(row['choice']) is int and row['choice'] in (1, 2)))
            _require(row['tie'] is None or type(row['tie']) is bool)
            if policy != 'BASE_QWEN':
                _require(row['nll'] is None)
            elif row['nll'] is not None:
                _require(type(row['nll']) is list and len(row['nll']) == 2)
                for loss in row['nll']:
                    if loss is None:
                        continue
                    _require(set(loss) == {'mean', 'summed', 'scored_tokens'})
                    _require(type(loss['scored_tokens']) is int and 1 <= loss['scored_tokens'] <= 256)
                    _require(all(type(loss[k]) in (int, float) and isfinite(loss[k]) and loss[k] >= 0
                                 for k in ('mean', 'summed')))
                    _require(loss['summed'] == loss['mean'] * loss['scored_tokens'])
            if row['status'] == 'COMPLETED':
                _require(row['choice'] in (1, 2) and type(row['tie']) is bool)
            else:
                _require(row['choice'] is None and row['tie'] is None)
            if policy == 'NO_ACTION':
                _require(row['status'] in ('ABSTAIN', 'NOT_RUN'))
        _require(summary == _summary(rows))
    requests = results['model_requests']
    _require(set(requests) == {'assigned', 'attempted', 'completed', 'failed', 'unknown', 'unattempted'})
    _require(all(type(n) is int and 0 <= n <= 16 for n in requests.values()))
    _require(requests['assigned'] == 16 and requests['attempted'] + requests['unattempted'] == 16
             and requests['attempted'] == requests['completed'] + requests['failed'] + requests['unknown'])


def result_manifest(results, *, code_version):
    try:
        _validate_results(results)
        evidence = reproduction_manifest(EvidenceBundle('helpsteer2-dev:' + _REVISION,
            'manager-helpsteer2-dev', ()), code_version=code_version)
        return dict(results, schema='manager.helpsteer2-dev-result.v1', code_version=code_version,
            protocol_sha256=PROTOCOL_SHA256, purpose='DEVELOPMENT_CANDIDATE_LIKELIHOOD_ONLY',
            human_response_labels='Published labels apply only to exact original candidate responses',
            new_response_human_quality=None, pressure=None, dependency=None, harms=None,
            behavior_change=None, human_benefit='NOT_MEASURED', proof_level='P0', can_execute=False,
            pretraining_contamination='UNKNOWN', evidence=evidence)
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def run_local(*, progress=None, **configuration):
    """Explicit research CLI only. No network, generation, backward or optimizer.

    Caller must provide the root-owned cumulative 900s/6GiB process-group
    watchdog starting before this call, including model load and hashing.
    """
    try:
        protocol, rights, sources, cases = load_verified_inputs(**configuration)
        def checkpoint(results):
            if progress is not None:
                progress(result_manifest(results, code_version=configuration['code_version']))

        checkpoint(_empty_results(cases))  # Before optional imports and model load.
        for name, version in protocol['packages'].items():
            _require(importlib.metadata.version(name) == version)
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(2)
        torch.manual_seed(42)
        tokenizer = AutoTokenizer.from_pretrained(str(configuration['model_dir']),
            local_files_only=True, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(str(configuration['model_dir']),
            local_files_only=True, trust_remote_code=False, use_safetensors=True,
            torch_dtype=torch.bfloat16, device_map=None)
        model.to(device='cpu', dtype=torch.bfloat16)
        model.eval()

        def encode(case):
            user = [dict(role='user', content=case.prompt)]
            prefix = tokenizer.apply_chat_template(user, tokenize=True, add_generation_prompt=True,
                enable_thinking=False, truncation=False)
            return tuple(completion_mask(prefix, tokenizer.apply_chat_template(
                user + [dict(role='assistant', content=response)], tokenize=True,
                add_generation_prompt=False, enable_thinking=False, truncation=False))
                for response in case.responses)

        def mean_loss(mask):
            ids = torch.tensor([mask.input_ids], dtype=torch.long, device='cpu')
            labels = torch.tensor([mask.labels], dtype=torch.long, device='cpu')
            with torch.inference_mode():
                loss = model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels,
                             use_cache=False).loss
            return float(loss.item())

        report = result_manifest(evaluate_cases(cases, encode, mean_loss, progress=checkpoint),
                                 code_version=configuration['code_version'])
        report.update(dataset_revision=protocol['dataset_revision'], model_id=protocol['model_id'],
            model_revision=protocol['model_revision'], model_files=protocol['model_files'],
            source_artifacts=protocol['source_artifacts'], packages=protocol['packages'],
            computation=protocol['computation'], attribution=rights['attribution'],
            source_rights=rights['permissions'], source_license_review=rights['license_review'],
            source_snapshots=[dict(source_id=s.source_id, sha256=s.content_sha256,
                                   retrieved_at=s.retrieved_at.isoformat(),
                                   retrieved_at_basis='local file mtime, not upstream publication')
                              for s in sources.values()])
        if progress is not None:
            progress(report)
        return report
    except Exception:
        raise ValueError(UNAVAILABLE) from None
