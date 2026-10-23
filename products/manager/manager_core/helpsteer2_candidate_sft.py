"""One private finite native PEFT/TRL entry. Imports remain stdlib until G6 checks.

The external execution config is an operator assertion bound to actual files;
its hashes are consistency checks, not cryptographic proof of review or authority.
No evaluation, generation, retry/resume, custom loss or optimizer loop is provided.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import gzip
from hashlib import sha256
from io import BytesIO
import importlib.metadata
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import unicodedata

from .helpsteer2_candidate_eval import (_json, _hash, _verify_file, _verify_model,
                                        completion_mask, CandidateCase, _QUALITY)

PROTOCOL_SHA256 = 'eb2e585321d954d507af52b1bf71db9eb3b7ae3150273484909b6aeeae48a53d'
MANIFEST_SHA256 = '7547ff63f7c06f8196689b3890288417154012d71e9609d0a3db232eeb0f182e'
RIGHTS_SHA256 = 'f41063b9ae281bc5bc1677655cb5a5997b1c9b5de8857ac180480176d71a1be5'
UNAVAILABLE = 'HELPSTEER2_SFT_UNAVAILABLE'
ROOT = Path(__file__).resolve().parents[1]
REQUIRED_NATIVE_FILES = frozenset(('adapter_model.safetensors', 'adapter_config.json',
                                   'tokenizer.json', 'tokenizer_config.json', 'training_args.bin'))
ALLOWED_NATIVE_FILES = REQUIRED_NATIVE_FILES | frozenset(('README.md','added_tokens.json',
    'special_tokens_map.json','chat_template.jinja','vocab.json','merges.txt'))
# The complete repository import closure of reused primitives and FD silence.
SOURCE_FILES = frozenset((
    'manager_core/helpsteer2_candidate_sft.py', 'scripts/train_helpsteer2_candidate_sft.py',
    'manager_core/helpsteer2_candidate_eval.py', 'manager_core/models/source.py',
    'manager_core/evidence.py', 'manager_core/outcome_bench.py',
    'manager_core/__init__.py', 'manager_core/models/__init__.py',
    'manager_core/calibration.py', 'manager_core/evaluation.py',
    'manager_core/error_calibration.py', 'manager_core/collaboration.py',
    'manager_core/evidence_types.py', 'manager_core/models/intervention.py',
    'manager_core/potential_outcomes.py', 'manager_core/collaboration_evaluation.py',
    'scripts/evaluate_xstest_refusal.py', 'manager_core/xstest_refusal_eval.py',
))
EVIDENCE_KEYS = frozenset(('G0','G1','G2','G3','G4','G5','G6',
                           'official_ci','independent_review','source_boundary'))


def _require(condition):
    if not condition:
        raise ValueError(UNAVAILABLE)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _digest_file(path):
    result = sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def _path(path, *, private=False, mode=None, file=False, fresh=False):
    raw = os.fspath(path)
    path = Path(path)
    _require(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)))
    _require(raw == str(path) and path == path.resolve(strict=False))
    _require(path.parent.is_dir())
    if private:
        parent = path.parent.stat()
        _require(parent.st_uid == os.getuid() and stat.S_IMODE(parent.st_mode) & 0o077 == 0)
    if fresh:
        _require(not path.exists())
    if file:
        info = path.stat()
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
        if private:
            _require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0)
        if mode is not None:
            _require(stat.S_IMODE(info.st_mode) == mode)
    return path


def validate_protocol(payload: bytes, expected_sha256: str) -> dict:
    try:
        _require(type(payload) is bytes and expected_sha256 == PROTOCOL_SHA256)
        _require(sha256(payload).hexdigest() == PROTOCOL_SHA256)
        return _json(payload)
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def validate_rights(payload, protocol):
    try:
        _require(payload['schema'] == 'manager.source-rights.v1')
        matches = [r for r in payload['sources'] if r['id'] == protocol['rights']['record_id']]
        _require(len(matches) == 1)
        record = matches[0]
        _require(sha256(_canonical(record)).hexdigest() == RIGHTS_SHA256
                 == protocol['rights']['record_canonical_sha256'])
        return record
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def _verify_evidence(pin):
    _require(type(pin) is dict and set(pin) == {'path', 'sha256'})
    path = _path(pin['path'], private=True, file=True)
    _require(re.fullmatch('[a-f0-9]{64}', pin['sha256']) is not None)
    _require(_digest_file(path) == pin['sha256'])


def validate_execution_config(path, *, protocol, code_version, input_paths):
    """Validate local frozen operator evidence; never infer remote CI authenticity."""
    path = _path(path, private=True, file=True, mode=0o400)
    config = _json(path.read_bytes())
    _require(config['kind'] == 'manager.helpsteer2-private-sft-execution.v1')
    _require(config['acceptance_status'] == 'ACCEPTED_ONE_OFFLINE_TRAINING_ATTEMPT')
    _require(config['can_execute'] is False)
    input_keys = {'protocol_path','manifest_path','data_dir','model_dir','rights_path'}
    _require(set(input_paths) == set(config['input_paths']) == input_keys)
    for name, actual in input_paths.items():
        _require(str(_path(actual)) == str(_path(config['input_paths'][name])))
    _path(config['adapter_dir'],private=True)
    _path(config['output'],private=True)
    _require(config['scientific_protocol_sha256'] == PROTOCOL_SHA256)
    _require(config['manifest_sha256'] == MANIFEST_SHA256 == protocol['manifest']['sha256'])
    _require(config['rights_record_sha256'] == RIGHTS_SHA256)
    _require(type(code_version) is str and re.fullmatch('[a-f0-9]{40}', code_version) is not None)
    _require(config['code_version'] == code_version)
    _require(config['cwd'] == str(ROOT) and Path.cwd().resolve() == ROOT)
    _require(type(config['max_cumulative_wall_seconds']) is int and config['max_cumulative_wall_seconds'] == 900)
    _require(type(config['max_process_group_rss_bytes']) is int and config['max_process_group_rss_bytes'] == 6442450944)
    _require(config['accepted_gates'] == ['G0','G1','G2','G3','G4','G5','G6'])
    _require(set(config['source_files']) == SOURCE_FILES)
    for name, digest in config['source_files'].items():
        source = _path(ROOT / name, file=True)
        _require(re.fullmatch('[a-f0-9]{64}', digest) is not None and _digest_file(source) == digest)
    _require(set(config['acceptance_evidence']) == EVIDENCE_KEYS)
    for pin in config['acceptance_evidence'].values():
        _verify_evidence(pin)
        _require(Path(pin['path']).resolve() != path)
    _verify_evidence(config['watchdog'])
    _require(Path(config['watchdog']['path']).resolve() != path)
    return config


def validate_execution_paths(config, *, adapter_dir, metadata_output_path):
    adapter = _path(adapter_dir,private=True,fresh=True)
    output = _path(metadata_output_path,private=True)
    _require(str(adapter) == str(_path(config['adapter_dir'],private=True)))
    _require(str(output) == str(_path(config['output'],private=True)))
    _require(adapter != output)


def validate_manifest(manifest):
    groups = (('train27',27,'train','train','train'),
              ('development8',8,'train','train','dev'),
              ('final16',16,'val','validation','final_test'))
    all_ids, prompt_hashes, response_hashes = set(), set(), set()
    for name, size, raw, native, proposed in groups:
        specs = manifest[name]
        _require(type(specs) is list and len(specs) == size)
        for spec in specs:
            row_id = spec['source_preference_row_1based']
            _require(type(row_id) is int and row_id > 0 and row_id not in all_ids)
            all_ids.add(row_id)
            _require((spec['raw_preference_split'],spec['native_split'],spec['proposed_split']) == (raw,native,proposed))
            ph = {spec['prompt_exact_sha256'], spec['prompt_canonical_sha256']}
            rh = set(spec['response_exact_sha256']) | set(spec['response_canonical_sha256'])
            _require(len(spec['response_exact_sha256']) == len(spec['response_canonical_sha256']) == 2)
            _require(all(type(h) is str and re.fullmatch('[a-f0-9]{64}',h) for h in ph | rh))
            _require(not ph & prompt_hashes and not rh & response_hashes)
            _require(spec['response_exact_sha256'][0] != spec['response_exact_sha256'][1]
                     and spec['response_canonical_sha256'][0] != spec['response_canonical_sha256'][1])
            prompt_hashes.update(ph)
            response_hashes.update(rh)
            for key in ('quality_rows_1based','full_sequence_token_counts','completion_mask_token_lengths_by_candidate'):
                values = spec[key]
                _require(type(values) is list and len(values) == 2 and all(type(n) is int and n > 0 for n in values))
                if key != 'quality_rows_1based': _require(all(n <= 256 for n in values))
            if name == 'train27':
                strength, choice = spec['preference_strength'], spec['human_choice']
                _require(type(strength) is int and strength in (-3,-2,-1,1,2,3))
                _require(type(choice) is int and choice == (1 if strength < 0 else 2))
                _require(spec['chosen_original_response_sha256'] == spec['response_exact_sha256'][choice-1])
    excluded = manifest['excluded_train_preference_rows_1based']
    _require(type(excluded) is list and len(excluded) == len(set(excluded)) == 5
             and all(type(i) is int and i > 0 for i in excluded) and not set(excluded) & all_ids)
    exposure = manifest['exposure']
    _require(exposure['final_content_qc_exposed'] is True and exposure['fully_blind_or_pristine'] is False)
    _require(exposure['final_model_scoring'] == exposure['final_optimizer_use'] == 'NOT_RUN_PER_RECORDED_METADATA')
    _require(exposure['paraphrase_pretraining_contamination'] == 'UNKNOWN')


@dataclass(frozen=True)
class SelectedCase(CandidateCase):
    completion_token_counts: tuple[int, int] = field(default=(0,0))


def _canonical_hash(text):
    return _hash(' '.join(unicodedata.normalize('NFKC', text).split()))


def reconstruct_cases(manifest, preferences, quality):
    """Only selected original rows are present; no dev/final preference parsing."""
    validate_manifest(manifest)
    specs = manifest['train27']
    _require(set(preferences) == {s['source_preference_row_1based'] for s in specs})
    quality_ids = [i for s in specs for i in s['quality_rows_1based']]
    _require(len(set(quality_ids)) == 54 and set(quality) == set(quality_ids))
    cases = []
    for spec in specs:
        row_id = spec['source_preference_row_1based']
        row = preferences[row_id]
        _require(row['split'] == 'train')
        strength = row['preference_strength']
        _require(type(strength) is int and strength in (-3,-2,-1,1,2,3) and strength == spec['preference_strength'])
        _require(_hash(row['prompt']) == spec['prompt_exact_sha256'])
        _require(_canonical_hash(row['prompt']) == spec['prompt_canonical_sha256'])
        responses = (row['response_1'],row['response_2'])
        labels = []
        for i, response in enumerate(responses):
            _require(_hash(response) == spec['response_exact_sha256'][i])
            _require(_canonical_hash(response) == spec['response_canonical_sha256'][i])
            q = quality[spec['quality_rows_1based'][i]]
            _require(q['prompt'] == row['prompt'] and q['response'] == response)
            values = {k:q[k] for k in _QUALITY}
            _require(all(type(v) is int and 0 <= v <= 4 for v in values.values()))
            labels.append(values)
        cases.append(SelectedCase(row_id, spec['prompt_exact_sha256'], tuple(spec['response_exact_sha256']),
            spec['human_choice'],strength,tuple(spec['quality_rows_1based']),tuple(labels),
            tuple(spec['full_sequence_token_counts']), row['prompt'], responses,
            completion_token_counts=tuple(spec['completion_mask_token_lengths_by_candidate'])))
    return tuple(cases)


def read_selected_rows(path, source, wanted, *, expected_lines):
    payload = Path(path).read_bytes()
    source.verify_content(payload)
    _require(type(wanted) is set and all(type(i) is int and i > 0 for i in wanted))
    rows, count = {}, 0
    with gzip.open(BytesIO(payload), 'rt', encoding='utf-8') as stream:
        for count, line in enumerate(stream, 1):
            if count in wanted:  # Deliberately skip JSON parsing of every other row.
                rows[count] = _json(line)
    _require(count == expected_lines and set(rows) == wanted)
    return rows


def verify_package_versions(protocol):
    for name, version in protocol['packages'].items():
        _require(importlib.metadata.version(name) == version)


def load_verified_inputs(*, protocol_path, expected_sha256, manifest_path, data_dir,
                         model_dir, rights_path, code_version, execution_config_path):
    try:
        protocol = validate_protocol(_path(protocol_path,file=True).read_bytes(), expected_sha256)
        config = validate_execution_config(execution_config_path, protocol=protocol, code_version=code_version,
            input_paths=dict(protocol_path=protocol_path,manifest_path=manifest_path,data_dir=data_dir,
                             model_dir=model_dir,rights_path=rights_path))
        rights = validate_rights(_json(_path(rights_path,file=True).read_bytes()), protocol)
        raw = _path(manifest_path,file=True).read_bytes()
        _require(len(raw) == protocol['manifest']['bytes'] and sha256(raw).hexdigest() == MANIFEST_SHA256)
        manifest = _json(raw)
        validate_manifest(manifest)
        _require(manifest['dataset_id'] == protocol['dataset_id']
                 and manifest['dataset_revision'] == protocol['dataset_revision'])
        # Metadata version lookup does not import optional ML modules.
        verify_package_versions(protocol)
        data_dir = _path(data_dir)
        _require(data_dir.is_dir())
        sources = {}
        for name,pin in protocol['source_artifacts'].items():
            source_path = _path(data_dir/name,file=True)
            sources[name] = _verify_file(source_path,pin,source_id='helpsteer2:'+name,
                url='https://huggingface.co/datasets/nvidia/HelpSteer2/resolve/'+protocol['dataset_revision']+'/'+name)
        _path(model_dir)
        _verify_model(model_dir,protocol['model_files'])
        prefs = read_selected_rows(data_dir/'preference/preference.jsonl.gz',
            sources['preference/preference.jsonl.gz'],
            {s['source_preference_row_1based'] for s in manifest['train27']}, expected_lines=9125)
        quality = read_selected_rows(data_dir/'train.jsonl.gz',sources['train.jsonl.gz'],
            {i for s in manifest['train27'] for i in s['quality_rows_1based']}, expected_lines=20324)
        cases = reconstruct_cases(manifest,prefs,quality)
        return protocol, rights, sources, cases, config
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def build_selected_example(case, tokenizer):
    index = case.human_choice - 1
    _require(case.human_choice in (1,2))
    user = [dict(role='user', content=case.prompt)]
    prefix = tokenizer.apply_chat_template(user,tokenize=True,add_generation_prompt=True,
                                           enable_thinking=False,truncation=False)
    full = tokenizer.apply_chat_template(user+[dict(role='assistant',content=case.responses[index])],
        tokenize=True,add_generation_prompt=False,enable_thinking=False,truncation=False)
    mask = completion_mask(prefix,full)
    _require(len(mask.input_ids) == case.full_sequence_token_counts[index])
    _require(mask.scored_tokens == case.completion_token_counts[index])
    return dict(input_ids=list(mask.input_ids),completion_mask=[int(v != -100) for v in mask.labels])


def planned_windows(rows, accumulation):
    _require(type(rows) is int and rows > 0 and type(accumulation) is int and accumulation > 0)
    return (accumulation,) * (rows//accumulation) + ((rows%accumulation,) if rows%accumulation else ())


def native_sft_kwargs(protocol, output_dir):
    recipe = protocol['recipe']
    cfg = dict(recipe['training'])
    _require(cfg['num_train_epochs'] == 1 and cfg['max_steps'] == -1
             and cfg['per_device_train_batch_size'] == 1 and cfg['gradient_accumulation_steps'] == 4)
    _require(cfg['expected_optimizer_opportunities'] == 7
             and tuple(cfg['planned_accumulation_windows']) == planned_windows(27,4))
    for key in ('expected_optimizer_opportunities','planned_accumulation_windows','sampler',
                'actual_consumed_row_order','resume'):
        cfg.pop(key)
    cfg.update(protocol['native_contract']['sft_config'])
    cfg['output_dir'] = str(output_dir)
    return cfg


def verify_optimizer_membership(trainable, optimizer):
    expected = {id(p) for p in trainable.values()}
    actual = [id(p) for group in optimizer.param_groups for p in group['params']]
    _require(bool(expected) and len(actual) == len(set(actual)) and set(actual) == expected)


def _inventory_metadata(inventory):
    _require(type(inventory) is dict and REQUIRED_NATIVE_FILES <= set(inventory) <= ALLOWED_NATIVE_FILES)
    for name, pin in inventory.items():
        _require(type(name) is str and Path(name).name == name)
        _require(set(pin) == {'sha256','bytes'} and type(pin['bytes']) is int and pin['bytes'] > 0)
        _require(type(pin['sha256']) is str and re.fullmatch('[a-f0-9]{64}',pin['sha256']) is not None)


class Lifecycle:
    """Observation only: callbacks never substitute for the standard training loop."""
    def __init__(self, *, progress, code_version):
        _require(type(code_version) is str and re.fullmatch('[a-f0-9]{40}',code_version) is not None)
        self.progress, self.started = progress, time.monotonic()
        self.receipt = dict(schema='manager.helpsteer2-private-sft-result.v1',
            code_version=code_version, scientific_protocol_sha256=PROTOCOL_SHA256,
            manifest_sha256=MANIFEST_SHA256,rights_record_sha256=RIGHTS_SHA256,
            status='NOT_RUN',event='PREIMPORT',event_sequence=0,global_step=None,
            backward_may_have_begun=False,backward_microbatches_completed_lower_bound=0,
            optimizer_opportunities_observed=0,optimizer_step_returns_observed=0,
            optimizer_skips_observed=0,optimizer_skip_unknown_returns=0,
            last_step_was_skipped=None,train_returned=False,save_returned=False,
            artifact_inventory=None,artifact_inventory_sha256=None,
            changed_adapter_tensors=None,parameter_change='UNKNOWN',
            actual_consumed_row_order='NOT_OBSERVED',base_numeric_in_memory_unchanged='NOT_MEASURED',
            human_benefit='NOT_MEASURED',proof_level='P0_FINITE_ORIGINAL_CANDIDATE_ONLY',
            evaluation='NOT_RUN',can_execute=False)
        self._train_started = False
        self._step_open = False
        self._pre_step = False
        self._optimizer_returned = False
        self._publish()

    def _publish(self):
        self.receipt['elapsed_seconds'] = time.monotonic()-self.started
        if self.progress is not None: self.progress(self.snapshot())

    def snapshot(self):
        return _json(json.dumps(self.receipt,allow_nan=False))

    def observe(self,event, *, global_step=None,finite_gradients=None,step_was_skipped=None):
        r = self.receipt
        _require(r['status'] not in ('COMPLETED','FAILED'))
        if global_step is not None:
            _require(type(global_step) is int and global_step >= 0)
            r['global_step'] = global_step
        if event == 'IMPORT_LOAD_START':
            _require(r['event'] == 'PREIMPORT')
        elif event == 'TRAIN_BEGIN':
            _require(not self._train_started and global_step == 0 and not self._step_open)
            self._train_started = True
        elif event == 'STEP_BEGIN':
            _require(self._train_started and not self._step_open and not r['train_returned']
                     and global_step == r['optimizer_step_returns_observed'])
            self._step_open,self._pre_step,self._optimizer_returned = True,False,False
            r['backward_may_have_begun'] = True
        elif event == 'SUBSTEP_END':
            _require(self._step_open and not self._pre_step)
            r['backward_microbatches_completed_lower_bound'] += 1
        elif event == 'PRE_OPTIMIZER_STEP':
            _require(self._step_open and not self._pre_step)
            # Reaching this event establishes the final backward completed even if finite checking fails.
            r['backward_microbatches_completed_lower_bound'] += 1
            r['finite_gradients_at_last_pre_optimizer'] = finite_gradients
            r['event'],r['event_sequence'] = event,r['event_sequence']+1
            self._publish()
            _require(finite_gradients is True)
            self._pre_step = True
            r['optimizer_opportunities_observed'] += 1
        elif event == 'OPTIMIZER_STEP_RETURNED':
            _require(self._pre_step and not self._optimizer_returned)
            _require(step_was_skipped is None or type(step_was_skipped) is bool)
            self._optimizer_returned = True
            r['optimizer_step_returns_observed'] += 1
            r['last_step_was_skipped'] = step_was_skipped
            r['optimizer_skips_observed'] += int(step_was_skipped is True)
            r['optimizer_skip_unknown_returns'] += int(step_was_skipped is None)
        elif event == 'STEP_END':
            _require(self._optimizer_returned and self._step_open)
            _require(global_step == r['optimizer_step_returns_observed'])
            self._step_open = False
        elif event == 'TRAIN_RETURNED':
            _require(not self._step_open and r['optimizer_opportunities_observed'] ==
                r['optimizer_step_returns_observed'] == global_step == 7
                and r['backward_microbatches_completed_lower_bound'] == 27)
            r['train_returned'] = True
        elif event == 'SAVE_STARTED':
            _require(r['train_returned'] and r['event'] == 'TRAIN_RETURNED')
        elif event == 'SAVE_RETURNED':
            _require(r['event'] == 'SAVE_STARTED')
            r['save_returned'] = True
        else:
            raise ValueError(UNAVAILABLE)
        r['status'],r['event'] = 'IN_PROGRESS',event
        r['event_sequence'] += 1
        self._publish()

    def freeze(self, *, inventory, changed_adapter_tensors):
        _require(self.receipt['save_returned'] and self.receipt['event'] == 'SAVE_RETURNED')
        _inventory_metadata(inventory)
        _require(type(changed_adapter_tensors) is int and changed_adapter_tensors >= 0)
        r = self.receipt
        r.update(artifact_inventory=inventory,artifact_inventory_sha256=sha256(_canonical(inventory)).hexdigest(),
            changed_adapter_tensors=changed_adapter_tensors,
            parameter_change='CHANGE_OBSERVED' if changed_adapter_tensors else 'NO_CHANGE_OBSERVED',
            event='ARTIFACT_FROZEN',status='COMPLETED',event_sequence=r['event_sequence']+1)
        self._publish()

    def fail(self):
        self.receipt.update(status='FAILED',event='FAILED',event_sequence=self.receipt['event_sequence']+1)
        self._publish()


def _fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


class PrivateCheckpoint:
    """Fresh output only; each observation atomically replaces our owned0600 file."""
    def __init__(self, path):
        self.path = _path(path,private=True,fresh=True)
        self.inode = None

    def __call__(self, report):
        if self.inode is None:
            _path(self.path,private=True,fresh=True)
        else:
            current = _path(self.path,private=True,file=True,mode=0o600).stat()
            _require((current.st_dev,current.st_ino) == self.inode)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w',dir=self.path.parent,prefix='.helpsteer2-sft-',
                    encoding='utf-8',delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(),0o600)
                json.dump(report,stream,sort_keys=True,ensure_ascii=True,allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            # Initial publication uses link for exclusive no-overwrite semantics.
            if self.inode is None:
                os.link(temporary,self.path)
                temporary.unlink()
            else:
                os.replace(temporary,self.path)
            _fsync_directory(self.path.parent)
            info = self.path.stat()
            self.inode = (info.st_dev,info.st_ino)
        finally:
            if temporary is not None: temporary.unlink(missing_ok=True)


def create_adapter_dir(path):
    path = _path(path,private=True,fresh=True)
    path.mkdir(mode=0o700)
    _require(stat.S_IMODE(path.stat().st_mode) == 0o700)
    _fsync_directory(path.parent)
    return path


def freeze_inventory(directory):
    directory = _path(directory)
    _require(directory.is_dir() and stat.S_IMODE(directory.stat().st_mode) == 0o700)
    inventory = {}
    for path in directory.iterdir():
        _path(path,file=True)
        _require(path.stat().st_uid == os.getuid())
        os.chmod(path,0o600)
        with path.open('rb') as stream: os.fsync(stream.fileno())
        inventory[path.name] = dict(bytes=path.stat().st_size,sha256=_digest_file(path))
    _inventory_metadata(inventory)
    _fsync_directory(directory)
    return inventory


def _trainables(model, torch):
    """Expected names/shapes come from the already hash-bound native Qwen config."""
    config = model.config
    _require(config.model_type == 'qwen3' and config.num_hidden_layers == 28 and config.hidden_size == 1024)
    expected = {}
    rank = 8
    for layer in range(config.num_hidden_layers):
        for target, heads in (('q_proj',config.num_attention_heads),('v_proj',config.num_key_value_heads)):
            prefix = f'base_model.model.model.layers.{layer}.self_attn.{target}.lora_'
            expected[prefix+'A.default.weight'] = (rank,config.hidden_size)
            expected[prefix+'B.default.weight'] = (heads*config.head_dim,rank)
    named = {name:p for name,p in model.named_parameters() if p.requires_grad}
    _require(set(named) == set(expected))
    for name,p in named.items():
        _require(tuple(p.shape) == expected[name] and p.dtype == torch.float32)
        _require(bool(torch.isfinite(p).all().item()))
    return named


def validate_saved_config(config, model_dir):
    _require(config['r'] == 8 and config['lora_alpha'] == 8 and config['lora_dropout'] == 0
             and set(config['target_modules']) == {'q_proj','v_proj'} and config['bias'] == 'none'
             and config['task_type'] == 'CAUSAL_LM' and config['inference_mode'] is True
             and config['peft_type'] == 'LORA' and config['init_lora_weights'] is True
             and config['modules_to_save'] is None
             and config['base_model_name_or_path'] == str(model_dir))


def _native_train(protocol, cases, model_dir, adapter_dir, observer):
    """Only this boundary imports ML; callers must complete all preimport guards."""
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback
    from trl import SFTConfig, SFTTrainer
    from safetensors import safe_open

    torch.set_num_threads(2)
    torch.manual_seed(42)
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir),local_files_only=True,trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(str(model_dir),local_files_only=True,
        trust_remote_code=False,use_safetensors=True,torch_dtype=torch.bfloat16,device_map=None,
        attn_implementation='eager')
    model.config.use_cache = False
    examples = [build_selected_example(case,tokenizer) for case in cases]
    _require(len(examples) == 27)
    lora = dict(protocol['recipe']['lora'])
    lora.pop('adapter_dtype')
    lora.update(inference_mode=False)
    # A single standard SFTTrainer owns PEFT wrapping, loss and optimizer steps.
    trainer = SFTTrainer(model=model,args=SFTConfig(**native_sft_kwargs(protocol,adapter_dir)),
        train_dataset=Dataset.from_list(examples),processing_class=tokenizer,peft_config=LoraConfig(**lora))
    trainable = _trainables(trainer.model,torch)
    initial = {name:p.detach().clone() for name,p in trainable.items()}
    trainer.create_optimizer()
    verify_optimizer_membership(trainable,trainer.optimizer)
    observer.receipt['trainable_parameters'] = [dict(name=name,shape=list(p.shape),
        count=p.numel(),dtype=str(p.dtype)) for name,p in trainable.items()]
    observer.receipt['trainable_parameter_count'] = sum(p.numel() for p in trainable.values())
    observer.receipt['initial_adapter_finite'] = True
    observer.receipt['optimizer_membership_verified_before_backward'] = True
    observer._publish()

    class Observer(TrainerCallback):
        def on_train_begin(self,args,state,control,**kwargs):
            verify_optimizer_membership(trainable,kwargs['optimizer'])
            observer.observe('TRAIN_BEGIN',global_step=state.global_step)
        def on_step_begin(self,args,state,control,**kwargs):
            observer.observe('STEP_BEGIN',global_step=state.global_step)
        def on_substep_end(self,args,state,control,**kwargs):
            observer.observe('SUBSTEP_END',global_step=state.global_step)
        def on_pre_optimizer_step(self,args,state,control,**kwargs):
            finite = all(p.grad is not None and bool(torch.isfinite(p.grad).all().item()) for p in trainable.values())
            observer.observe('PRE_OPTIMIZER_STEP',global_step=state.global_step,finite_gradients=finite)
        def on_optimizer_step(self,args,state,control,**kwargs):
            skipped = getattr(kwargs['optimizer'],'step_was_skipped',None)
            observer.observe('OPTIMIZER_STEP_RETURNED',global_step=state.global_step,step_was_skipped=skipped)
        def on_step_end(self,args,state,control,**kwargs):
            observer.observe('STEP_END',global_step=state.global_step)

    trainer.add_callback(Observer())
    trainer.train()
    observer.observe('TRAIN_RETURNED',global_step=trainer.state.global_step)
    final = _trainables(trainer.model,torch)
    changed = sum(not torch.equal(initial[name],p.detach()) for name,p in final.items())
    observer.observe('SAVE_STARTED')
    trainer.save_model(str(adapter_dir))
    observer.observe('SAVE_RETURNED')
    config = _json((Path(adapter_dir)/'adapter_config.json').read_bytes())
    validate_saved_config(config,model_dir)
    with safe_open(str(Path(adapter_dir)/'adapter_model.safetensors'),framework='pt',device='cpu') as saved:
        keys = set(saved.keys())
        expected_saved = {name.replace('.default.weight','.weight') for name in final}
        _require(keys == expected_saved)
        for name,p in final.items():
            value = saved.get_tensor(name.replace('.default.weight','.weight'))
            _require(bool(torch.isfinite(value).all().item()) and torch.equal(value,p.detach().cpu()))
    inventory = freeze_inventory(adapter_dir)
    observer.freeze(inventory=inventory,changed_adapter_tensors=changed)


def run_local(*, progress=None, **configuration):
    """External900s/6GiB process-group watchdog must cover this entire process."""
    observer = None
    old_umask = os.umask(0o077)
    try:
        adapter_dir = _path(configuration.pop('adapter_dir'),private=True,fresh=True)
        output = configuration.pop('metadata_output_path')
        checkpoint = PrivateCheckpoint(output)
        def publish(report):
            checkpoint(report)
            if progress is not None: progress(report)
        observer = Lifecycle(progress=publish,code_version=configuration['code_version'])
        protocol,rights,sources,cases,config = load_verified_inputs(**configuration)
        validate_execution_paths(config,adapter_dir=adapter_dir,metadata_output_path=output)
        adapter_dir = create_adapter_dir(adapter_dir)
        observer.receipt.update(packages=protocol['packages'],model_files=protocol['model_files'],
            model_revision=protocol['model_revision'],source_artifacts=protocol['source_artifacts'],
            attribution=rights['attribution'],execution_config_sha256=_digest_file(configuration['execution_config_path']))
        observer.observe('IMPORT_LOAD_START')
        # Reuse FD-level suppression even when called directly without the CLI.
        from scripts.evaluate_xstest_refusal import _silence
        with _silence():
            _native_train(protocol,cases,configuration['model_dir'],adapter_dir,observer)
        return observer.snapshot()
    except (Exception,KeyboardInterrupt):
        if observer is not None:
            try: observer.fail()
            except Exception: pass  # Keep the last durable lower bound if the writer failed.
        raise ValueError(UNAVAILABLE) from None
    finally:
        os.umask(old_umask)
