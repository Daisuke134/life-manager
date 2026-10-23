"""Fixed private SafetyBench CLP producer; no alternate scorer or runtime owner.

Root config hashes establish local consistency, not authenticity of rights, CI
or review. Only the accepted native boundary imports optional ML libraries.
"""
from __future__ import annotations
from datetime import datetime, timezone
from functools import wraps
from hashlib import sha256
import importlib.metadata
from math import isfinite
import os
from pathlib import Path
import re
import stat
import sys

from . import safetybench_mcq as mcq
from .helpsteer2_candidate_sft import PrivateCheckpoint, _path, _digest_file, _fsync_directory
from .xstest_refusal_eval import _verify_model

UNAVAILABLE = 'SAFETYBENCH_LOCAL_MODEL_UNAVAILABLE'
ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = 'experiments/behavior-model/safetybench-local-qwen3-clp-protocol-v1.json'
PROTOCOL_SHA256 = '9122507cde91a8ffd9510fb5ad1227b34c5296931ffde3c1b0b888ba4aa32727'
SCOPE_SHA256 = 'c41c898e2a81cf0d212deaf9ff2428c667b4b5c67fb4bd5da74c6e73a172764a'
WATCHDOG_SHA256 = 'c5e33ed50c2dc97dc06c4410c7c381074cd6b0d89a6263f64da3793151bdcf1d'
AUDIT_SHA256 = '206d1e07224af6e78c1ea207ceecb802aec925163714a0cf828d74f2d776e140'
SOURCE_FILES = frozenset((
    'manager_core/safetybench_local_model.py', 'scripts/evaluate_safetybench_local_model.py',
    'manager_core/safetybench_mcq.py', 'manager_core/helpsteer2_candidate_sft.py',
    'manager_core/helpsteer2_candidate_eval.py', 'manager_core/xstest_refusal_eval.py',
    'manager_core/models/source.py', 'manager_core/outcome_bench.py', 'manager_core/evidence.py',
    'manager_core/__init__.py', 'manager_core/models/__init__.py', 'manager_core/calibration.py',
    'manager_core/evaluation.py', 'manager_core/error_calibration.py', 'manager_core/collaboration.py',
    'manager_core/evidence_types.py', 'manager_core/models/intervention.py',
    'manager_core/potential_outcomes.py', 'manager_core/collaboration_evaluation.py',
    'scripts/evaluate_xstest_refusal.py',
))
INPUT_KEYS = frozenset(('protocol_path', 'mcq_protocol_path', 'questions_path', 'answers_path', 'rights_path', 'model_dir'))
OUTPUT_KEYS = frozenset(('assignment', 'journal', 'progress', 'producer_receipt', 'envelope', 'result',
                         'terminal_receipt', 'wrapper_reap_receipt'))
EVIDENCE_KEYS = frozenset(('scope', 'resource', 'independent_review', 'official_ci', 'source_boundary', 'input_audit'))
CONFIG_KEYS = frozenset(('kind', 'acceptance_status', 'accepted_actions', 'can_execute', 'code_version', 'cwd',
    'scientific_protocol_sha256', 'input_paths', 'output_paths', 'source_files', 'packages', 'native_source',
    'acceptance_evidence', 'watchdog', 'wrapper_source', 'max_cumulative_wall_seconds',
    'max_process_group_rss_bytes', 'python_path', 'python_executable_sha256', 'argv', 'finalize_argv', 'wrapper_argv'))
_REASONS = frozenset(('CONTEXT_OVERFLOW', 'TOKENIZATION_FAILED', 'FORWARD_FAILED'))


def _require(value):
    if not value:
        raise ValueError(UNAVAILABLE)


def _static(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (Exception, KeyboardInterrupt):
            raise ValueError(UNAVAILABLE) from None
    return guarded


def _bytes(value):
    return mcq._canonical(value).encode('utf-8')


@_static
def validate_protocol(payload: bytes, expected_sha256: str) -> dict:
    _require(type(payload) is bytes and expected_sha256 == PROTOCOL_SHA256)
    _require(sha256(payload).hexdigest() == PROTOCOL_SHA256)
    return mcq._parse(payload)


@_static
def build_prompt(question: str, options: tuple[str, ...]) -> str:
    _require(type(question) is str and question.strip())
    _require(type(options) is tuple and 2 <= len(options) <= 4)
    _require(all(type(option) is str and option.strip() for option in options))
    return 'Question: ' + question.strip() + '\nOptions:\n' + ''.join(
        '(' + 'ABCD'[i] + ') ' + option + '\n' for i, option in enumerate(options)) + 'Answer:('


@_static
def label_token_ids(tokenizer) -> tuple[int, int, int, int]:
    labels = []
    for label in 'ABCD':
        ids = tokenizer.encode(label, add_special_tokens=False)
        _require(type(ids) is list and len(ids) == 1 and type(ids[0]) is int and ids[0] >= 0)
        _require(tokenizer.decode(ids, clean_up_tokenization_spaces=False) == label)
        labels.append(ids[0])
    _require(tuple(labels) == (32, 33, 34, 35) and len(set(labels)) == 4)
    return tuple(labels)


@_static
def encode_prompt(question: str, options: tuple[str, ...], tokenizer) -> tuple[int, ...]:
    ids = tokenizer.encode(build_prompt(question, options), add_special_tokens=True, padding=False, truncation=False)
    _require(type(ids) is list and bool(ids) and all(type(i) is int and i >= 0 for i in ids))
    return tuple(ids)


@_static
def choose_index(label_logits: tuple[float, ...], option_count: int) -> int:
    _require(type(option_count) is int and 2 <= option_count <= 4)
    _require(type(label_logits) is tuple and len(label_logits) == 4)
    _require(all(type(v) in (int, float) and isfinite(v) for v in label_logits))
    actual = label_logits[:option_count]
    return actual.index(max(actual))


def _private(path, *, file=False, mode=None, fresh=False):
    path = _path(path, private=True, file=file, mode=mode, fresh=fresh)
    _require(stat.S_IMODE(path.parent.stat().st_mode) == 0o700)
    _require(not path.is_relative_to(ROOT.parent.parent))
    return path


def _pin(pin):
    _require(type(pin) is dict and set(pin) == {'path', 'sha256'} and mcq._hash(pin['sha256']))
    path = _private(pin['path'], file=True)
    _require(_digest_file(path) == pin['sha256'])
    return path


def _native_metadata():
    # Distribution metadata and source text only: no ML import or weight scan.
    protocol = validate_protocol((ROOT / PROTOCOL_PATH).read_bytes(), PROTOCOL_SHA256)
    packages = {name: importlib.metadata.version(name) for name in protocol['packages']}
    distribution = importlib.metadata.distribution('transformers')
    path = _path(distribution.locate_file(protocol['native_source']['relative_path']), file=True)
    return packages, {'path': str(path), 'sha256': _digest_file(path)}


def execution_argv(config, path, mode):
    argv = [config['python_path'], str(ROOT / 'scripts/evaluate_safetybench_local_model.py'),
            '--mode', mode, '--execution-config-path', str(path), '--code-version', config['code_version']]
    if mode == 'finalize':
        argv += ['--terminal-receipt-path', config['output_paths']['terminal_receipt']]
    return argv


@_static
def validate_configuration(path: Path, *, mode: str, code_version: str) -> dict:
    path = _private(path, file=True, mode=0o400)
    config = mcq._parse(path.read_bytes())
    _require(type(config) is dict and set(config) == CONFIG_KEYS)
    _require(mode in ('infer', 'finalize') and config['accepted_actions'] == ['infer', 'finalize'])
    _require(config['kind'] == 'manager.safetybench-local-qwen3-clp-execution.v1')
    _require(config['acceptance_status'] == 'ACCEPTED_ONE_OFFLINE_SAFETYBENCH_CLP_ATTEMPT_WITH_TERMINAL_FINALIZATION')
    _require(config['can_execute'] is False and type(code_version) is str and re.fullmatch('[a-f0-9]{40}', code_version))
    _require(config['code_version'] == code_version and config['cwd'] == str(ROOT) and Path.cwd().resolve() == ROOT)
    for key, expected in (('max_cumulative_wall_seconds', 10800), ('max_process_group_rss_bytes', 6442450944)):
        _require(type(config[key]) is int and config[key] == expected)
    _require(config['scientific_protocol_sha256'] == PROTOCOL_SHA256)
    inputs, outputs = config['input_paths'], config['output_paths']
    _require(type(inputs) is dict and set(inputs) == INPUT_KEYS and type(outputs) is dict and set(outputs) == OUTPUT_KEYS)
    _require(inputs['protocol_path'] == str(ROOT / PROTOCOL_PATH))
    protocol = validate_protocol(_path(inputs['protocol_path'], file=True).read_bytes(), PROTOCOL_SHA256)
    _require(set(config['source_files']) == SOURCE_FILES)
    protected = {path, ROOT / PROTOCOL_PATH}
    for name, digest in config['source_files'].items():
        source = _path(ROOT / name, file=True)
        _require(mcq._hash(digest) and _digest_file(source) == digest)
        protected.add(source)
    packages, native = _native_metadata()
    _require(config['packages'] == packages == protocol['packages'])
    _require(config['native_source'] == native and native['sha256'] == protocol['native_source']['sha256'])
    protected.add(Path(native['path']))
    _require(type(config['acceptance_evidence']) is dict and set(config['acceptance_evidence']) == EVIDENCE_KEYS)
    for pin in (*config['acceptance_evidence'].values(), config['watchdog'], config['wrapper_source']):
        protected.add(_pin(pin))
    _require(config['acceptance_evidence']['scope']['sha256'] == SCOPE_SHA256)
    _require(config['acceptance_evidence']['input_audit']['sha256'] == AUDIT_SHA256)
    _require(config['watchdog']['sha256'] == WATCHDOG_SHA256)
    for name, raw in inputs.items():
        item = _path(raw, file=name != 'model_dir')
        if name == 'model_dir':
            _require(item.is_dir())
        if name in ('questions_path', 'answers_path'):
            _private(item, file=True, mode=0o600)
        protected.add(item)
    _require(len(set(inputs.values())) == len(inputs))
    output_set = set()
    for name, raw in outputs.items():
        item = _private(raw)
        _require(item not in protected and item not in output_set)
        _require(not any(item.is_relative_to(p) for p in protected if p.is_dir()))
        output_set.add(item)
        if mode == 'infer' or name in ('producer_receipt', 'envelope', 'result'):
            _require(not item.exists())
    # The interpreter alone may use the existing venv symlink spelling.
    python = Path(config['python_path'])
    _require(type(config['python_path']) is str and python.is_absolute() and str(python) == config['python_path'])
    _require(config['python_path'] == sys.executable)
    binary = _path(python.resolve(strict=True), file=True)
    _require(mcq._hash(config['python_executable_sha256']) and _digest_file(binary) == config['python_executable_sha256'])
    _require(config['argv'] == execution_argv(config, path, 'infer'))
    _require(config['finalize_argv'] == execution_argv(config, path, 'finalize'))
    _require(config['wrapper_argv'] == [str(python), config['wrapper_source']['path'], str(path)])
    config['_configuration_path'] = str(path)
    return config


def _revalidated(configuration, mode):
    _require(type(configuration) is dict)
    actual = validate_configuration(Path(configuration['_configuration_path']), mode=mode,
                                    code_version=configuration['code_version'])
    _require(configuration == actual)
    return actual


def _dataset(config):
    paths = config['input_paths']
    return mcq.load_safetybench(Path(paths['questions_path']).read_bytes(), Path(paths['answers_path']).read_bytes(),
        protocol_payload=Path(paths['mcq_protocol_path']).read_bytes(), expected_sha256=mcq.PROTOCOL_SHA256,
        rights_manifest=mcq._parse(Path(paths['rights_path']).read_bytes()), retrieved_at=datetime.now(timezone.utc))


@_static
def reconcile_rows(events: tuple[dict, ...], assignment_ids: tuple[str, ...]) -> tuple[dict, ...]:
    _require(type(events) is tuple and type(assignment_ids) is tuple and bool(assignment_ids))
    _require(all(type(i) is str for i in assignment_ids) and len(set(assignment_ids)) == len(assignment_ids))
    rows = [{'id': i, 'status': 'NOT_RUN', 'prediction': None} for i in assignment_ids]
    position, started, tokens = 0, False, None
    for event in events:
        _require(type(event) is dict and position < len(rows) and event['id'] == assignment_ids[position])
        _require(type(event['tokens']) is int and event['tokens'] >= 0)
        if event['event'] == 'START':
            _require(set(event) == {'event', 'id', 'tokens'} and not started and 0 < event['tokens'] <= 2048)
            started, tokens = True, event['tokens']
            rows[position]['status'] = 'UNKNOWN'
        else:
            _require(event['event'] == 'RESULT' and set(event) == {'event', 'id', 'tokens', 'status', 'prediction', 'reason', 'attempted'})
            _require(type(event['attempted']) is bool and event['attempted'] == started)
            _require(not started or event['tokens'] == tokens)
            if event['status'] == 'VALID':
                _require(started and event['reason'] is None and type(event['prediction']) is int and 0 <= event['prediction'] < 4)
            else:
                _require(event['status'] == 'FAILED' and event['prediction'] is None and event['reason'] in _REASONS)
                _require((started and event['reason'] == 'FORWARD_FAILED') or
                         (not started and event['reason'] == 'TOKENIZATION_FAILED' and event['tokens'] == 0) or
                         (not started and event['reason'] == 'CONTEXT_OVERFLOW' and event['tokens'] > 2048))
            rows[position].update(status=event['status'], prediction=event['prediction'])
            position += 1
            started, tokens = False, None
            if event['reason'] == 'FORWARD_FAILED':
                _require(event is events[-1])
    return tuple(rows)


@_static
def read_journal(payload: bytes):
    _require(type(payload) is bytes)
    parts = payload.split(b'\n')
    fragment = parts.pop()
    events = tuple(mcq._parse(line) for line in parts)
    return events, {'bytes': len(fragment), 'sha256': sha256(fragment).hexdigest()}


def _append(fd, event):
    payload = _bytes(event) + b'\n'
    _require(os.write(fd, payload) == len(payload))
    os.fsync(fd)


def _load_native(model_dir, torch, AutoModelForCausalLM, AutoTokenizer):
    torch.set_num_threads(2)
    torch.manual_seed(42)
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False,
        use_safetensors=True, torch_dtype=torch.bfloat16, device_map=None, attn_implementation='eager')
    model.to(device='cpu', dtype=torch.bfloat16)
    model.eval()
    model.requires_grad_(False)
    _require((model.config.model_type, model.config.num_hidden_layers, model.config.hidden_size) == ('qwen3', 28, 1024))
    _require(all(p.dtype == torch.bfloat16 and not p.requires_grad and p.device.type == 'cpu' for p in model.parameters()))
    labels = label_token_ids(tokenizer)
    def forward(ids):
        inputs = torch.tensor([list(ids)], dtype=torch.long, device='cpu')
        with torch.inference_mode():
            logits = model(input_ids=inputs, attention_mask=torch.ones_like(inputs), use_cache=False, logits_to_keep=1).logits
        _require(len(logits.shape) == 3 and tuple(logits.shape[:2]) == (1, 1) and logits.shape[2] > max(labels))
        return tuple(float(logits[0, 0, label].item()) for label in labels)
    return tokenizer, forward


def _native_backend(config, protocol=None):
    protocol = protocol or validate_protocol((ROOT / PROTOCOL_PATH).read_bytes(), PROTOCOL_SHA256)
    _verify_model(config['input_paths']['model_dir'], protocol['model_files'])
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    return _load_native(config['input_paths']['model_dir'], torch, AutoModelForCausalLM, AutoTokenizer)


def _summary(events, ids, lane_status):
    rows = reconcile_rows(tuple(events), ids)
    return {'status': lane_status, 'assigned': len(ids), 'state_counts': {state: sum(row['status'] == state for row in rows) for state in mcq._STATES},
            'attempted': sum(e['event'] == 'START' for e in events),
            'completed': sum(row['status'] == 'VALID' for row in rows),
            'overflow': sum(e.get('reason') == 'CONTEXT_OVERFLOW' for e in events),
            'total_tokens': sum(e['tokens'] for e in events if e['event'] == 'START' or not e.get('attempted', True)),
            'failed': sum(row['status'] == 'FAILED' for row in rows),
            'unknown': sum(row['status'] == 'UNKNOWN' for row in rows),
            'unattempted': len(ids) - sum(e['event'] == 'START' for e in events)}


@_static
def run_local(*, configuration: dict) -> dict:
    config = _revalidated(configuration, 'infer')
    dataset = _dataset(config)
    ids = tuple(c.case_id for c in dataset.cases)
    outputs = config['output_paths']
    assignment = {'schema': 'manager.safetybench-local-assignment.v1', 'ids': list(ids),
                  'membership_sha256': dataset.membership_sha256, 'configuration_sha256': _digest_file(config['_configuration_path']),
                  'initial_status': 'NOT_RUN'}
    PrivateCheckpoint(outputs['assignment'])(assignment)
    progress = PrivateCheckpoint(outputs['progress'])
    events = []
    progress(_summary(events, ids, 'INITIALIZED'))
    fd = os.open(outputs['journal'], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.fsync(fd)
        _fsync_directory(Path(outputs['journal']).parent)
        try:
            tokenizer, forward = _native_backend(config)
            label_token_ids(tokenizer)
        except Exception:
            report = _summary(events, ids, 'LOAD_FAILED')
            progress(report)
            return report
        for row in mcq._parse(dataset._questions_payload):
            case_id = str(row['id'])
            try:
                tokens = encode_prompt(row['question'], tuple(row['options']), tokenizer)
                reason = 'CONTEXT_OVERFLOW' if len(tokens) > 2048 else None
                count = len(tokens)
            except Exception:
                tokens, count, reason = (), 0, 'TOKENIZATION_FAILED'
            attempted = reason is None
            if attempted:
                event = {'event': 'START', 'id': case_id, 'tokens': count}
                _append(fd, event)
                events.append(event)
                try:
                    prediction = choose_index(forward(tokens), len(row['options']))
                except Exception:
                    prediction, reason = None, 'FORWARD_FAILED'
            else:
                prediction = None
            event = {'event': 'RESULT', 'id': case_id, 'tokens': count, 'status': 'VALID' if reason is None else 'FAILED',
                     'prediction': prediction, 'reason': reason, 'attempted': attempted}
            _append(fd, event)
            events.append(event)
            if reason == 'FORWARD_FAILED':
                break
        report = _summary(events, ids, 'COMPUTE_FAILED' if any(e.get('reason') == 'FORWARD_FAILED' for e in events) else 'INFERENCE_RETURNED')
        progress(report)
        return report
    finally:
        os.close(fd)


def _absent_group(pid):
    _require(type(pid) is int and pid > 1 and not Path('/proc', str(pid)).exists())
    for proc in Path('/proc').iterdir():
        if proc.name.isdigit():
            try:
                fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            except (FileNotFoundError, ProcessLookupError):
                continue
            _require(int(fields[2]) != pid)


def _terminal(config, path):
    _require(str(path) == config['output_paths']['terminal_receipt'])
    path = _private(path, file=True, mode=0o600)
    terminal = mcq._parse(path.read_bytes())
    _require(terminal['argv'] == config['argv'] and terminal['cwd'] == config['cwd'])
    for key, expected in (('wall_limit_seconds', 10800), ('observed_process_group_rss_limit_bytes', 6442450944), ('retry_count', 0)):
        _require(type(terminal[key]) is int and terminal[key] == expected)
    _require(type(terminal['poll_sleep_seconds']) is float and terminal['poll_sleep_seconds'] == 0.05)
    _require(terminal['status'] in ('EXITED_SUCCESS', 'COMPUTE_FAILED', 'RESOURCE_LIMIT'))
    _require(type(terminal['returncode']) is int and (terminal['status'] != 'EXITED_SUCCESS' or terminal['returncode'] == 0))
    _require(terminal['reaped'] is True and terminal['own_pid_absent'] is True and terminal['remaining_process_group_pids'] == [])
    _require(terminal['own_pid'] == terminal['own_process_group'])
    _absent_group(terminal['own_pid'])
    for key in ('elapsed_seconds', 'peak_group_rss_bytes'):
        _require(type(terminal[key]) in (int, float) and isfinite(terminal[key]) and terminal[key] >= 0)
    start, finish = (datetime.fromisoformat(terminal[key]) for key in ('started_at', 'finished_at'))
    _require(all(at.tzinfo is not None and at.utcoffset().total_seconds() == 0 for at in (start, finish)))
    duration = (finish - start).total_seconds()
    _require(duration >= 0 and abs(duration - terminal['elapsed_seconds']) <= 1.0)
    reap = mcq._parse(_private(config['output_paths']['wrapper_reap_receipt'], file=True, mode=0o600).read_bytes())
    _require(set(reap) == {'schema', 'terminal_receipt_sha256', 'wrapper_source_sha256', 'reaped', 'own_pid_absent',
                          'remaining_process_group_pids', 'returncode', 'wrapper_pid', 'argv', 'cwd'})
    _require(reap['schema'] == 'manager.safetybench-local-wrapper-reap.v1' and reap['terminal_receipt_sha256'] == _digest_file(path))
    _require(reap['wrapper_source_sha256'] == config['wrapper_source']['sha256'])
    _require(reap['argv'] == config['wrapper_argv'] and reap['cwd'] == config['cwd'])
    _require(reap['reaped'] is True and reap['own_pid_absent'] is True and reap['remaining_process_group_pids'] == [])
    _require(type(reap['returncode']) is int)
    _absent_group(reap['wrapper_pid'])
    return terminal, reap


@_static
def finalize_run(*, configuration: dict, terminal_receipt_path: Path) -> dict:
    config = _revalidated(configuration, 'finalize')
    terminal, reap = _terminal(config, terminal_receipt_path)
    dataset = _dataset(config)
    ids = tuple(c.case_id for c in dataset.cases)
    outputs = config['output_paths']
    assignment = mcq._parse(_private(outputs['assignment'], file=True, mode=0o600).read_bytes())
    _require(assignment == {'schema': 'manager.safetybench-local-assignment.v1', 'ids': list(ids),
        'membership_sha256': dataset.membership_sha256, 'configuration_sha256': _digest_file(config['_configuration_path']), 'initial_status': 'NOT_RUN'})
    journal = _private(outputs['journal'], file=True, mode=0o600).read_bytes()
    events, quarantine = read_journal(journal)
    rows = reconcile_rows(events, ids)
    for case, row in zip(dataset.cases, rows):
        _require(row['prediction'] is None or row['prediction'] < len(case.option_sha256))
    completed = quarantine['bytes'] == 0 and all(row['status'] == 'VALID' for row in rows) and terminal['status'] == 'EXITED_SUCCESS' and reap['returncode'] == 0
    summary = _summary(events, ids, 'COMPLETED' if completed else 'PARTIAL_OR_FAILED')
    receipt = {'schema': 'manager.safetybench-local-producer-receipt.v1', **summary,
        'journal_sha256': sha256(journal).hexdigest(), 'quarantined_terminal_fragment': quarantine,
        'rows_sha256': sha256(_bytes(rows)).hexdigest(), 'configuration_sha256': _digest_file(config['_configuration_path']),
        'terminal_receipt_sha256': _digest_file(terminal_receipt_path),
        'wrapper_reap_receipt_sha256': _digest_file(outputs['wrapper_reap_receipt']),
        'scientific_protocol_sha256': PROTOCOL_SHA256, 'code_version': config['code_version'],
        'model_revision': validate_protocol((ROOT / PROTOCOL_PATH).read_bytes(), PROTOCOL_SHA256)['model_revision'],
        'questions_sha256': dataset.questions_source.content_sha256, 'answers_sha256': dataset.answers_source.content_sha256,
        'membership_sha256': dataset.membership_sha256, 'outer_status': terminal['status']}
    writer = PrivateCheckpoint(outputs['producer_receipt'])
    try:
        writer(receipt)
    except Exception:
        writer.discard_unconfirmed_completion()
        raise
    envelope = {'schema': 'manager.safetybench-recorded-predictions.v1',
        'questions_sha256': dataset.questions_source.content_sha256, 'answers_sha256': dataset.answers_source.content_sha256,
        'membership_sha256': dataset.membership_sha256,
        'producer': {'kind': 'MODEL', 'name': 'Qwen/Qwen3-0.6B bare upstream CLP', 'version': 'safetybench-local-qwen3-clp-v1',
                     'run_receipt_sha256': _digest_file(outputs['producer_receipt'])}, 'rows': list(rows)}
    PrivateCheckpoint(outputs['envelope'])(envelope)
    payload = _private(outputs['envelope'], file=True, mode=0o600).read_bytes()
    result = mcq.evaluate_recorded(dataset, payload, code_version=config['code_version'])
    result.update(status=summary['status'], producer_summary=summary, outer_status=terminal['status'], elapsed_seconds=terminal['elapsed_seconds'],
                  peak_group_rss_bytes=terminal['peak_group_rss_bytes'], sampled_wall_limit_seconds=10800,
                  sampled_process_group_rss_limit_bytes=6442450944)
    writer = PrivateCheckpoint(outputs['result'])
    try:
        writer(result)
    except Exception:
        writer.discard_unconfirmed_completion()
        raise
    return result
