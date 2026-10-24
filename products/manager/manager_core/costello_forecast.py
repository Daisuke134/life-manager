"""Source-specific numeric forecast contract. No ML imports or execution authority.

Participant reports are targets, not facts, welfare measurements or permissions.
The prepared split is fixed separately; this module does not select on outcomes.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import os
import stat


ERROR = 'COSTELLO_FORECAST_UNAVAILABLE'
DESIGN_SHA256 = 'f9010431cc7dd4a2edfda9db901fb7265986c032a125ad0f725f291f0180d6ca'
PROMPT_PREFIX = ('Predict the participant-reported post-dialogue confidence on a 0-100 scale from the baseline confidence and assigned condition. '
                 'Treatment is a focal-belief AI dialogue; Control is an unrelated dialogue. '
                 'This is a statistical forecast, not a judgment of truth. '
                 'Return only a JSON object with one integer field post_belief.\n')
STATES = ('VALID', 'INVALID', 'UNKNOWN', 'NOT_RUN', 'ABSTAIN')
ROOT = Path(__file__).resolve().parents[1]


def require(value):
    if not value:
        raise ValueError(ERROR)


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value)
        value[key] = item
    return value


def _json(raw):
    require(type(raw) is str and len(raw) <= 100000)
    def invalid(_):
        raise ValueError(ERROR)
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid)
    except (ValueError, TypeError):
        raise ValueError(ERROR) from None


def parse_prediction(raw):
    require(type(raw) is str and len(raw) <= 128)
    value = _json(raw)
    require(type(value) is dict and set(value) == {'post_belief'})
    number = value['post_belief']
    require(type(number) is int and 0 <= number <= 100)
    return number


@dataclass(frozen=True)
class ForecastCase:
    row_key: str = field(repr=False)
    participant_key: str = field(repr=False)
    pre: int = field(repr=False)
    condition: str = field(repr=False)
    target: int | None = field(repr=False)

    def __post_init__(self):
        require(all(type(x) is str and 0 < len(x) <= 256
                    for x in (self.row_key, self.participant_key)))
        require(type(self.pre) is int and 50 <= self.pre <= 100)
        require(self.condition in ('Control', 'Treatment'))
        require(self.target is None or type(self.target) is int and 0 <= self.target <= 100)

    @property
    def prompt(self):
        return PROMPT_PREFIX + json.dumps(dict(baseline_confidence=self.pre,
            assigned_condition=self.condition), sort_keys=True) + '\n'


def parse_case(row):
    require(type(row) is dict and set(row) == {'row_key', 'participant_key', 'prompt', 'target'})
    prompt = row['prompt']
    require(type(prompt) is str and prompt.startswith(PROMPT_PREFIX))
    payload = _json(prompt[len(PROMPT_PREFIX):])
    require(type(payload) is dict and set(payload) == {'baseline_confidence', 'assigned_condition'})
    target = None if row['target'] is None else parse_prediction(row['target'])
    case = ForecastCase(row['row_key'], row['participant_key'], payload['baseline_confidence'],
                        payload['assigned_condition'], target)
    require(case.prompt == prompt)
    return case


def validate_disjoint(parts):
    require(type(parts) is dict and set(parts) == {'train_selected', 'development', 'evaluation'})
    seen_rows, seen_people = set(), set()
    for cases in parts.values():
        require(type(cases) is tuple and cases)
        rows, people = set(), set()
        for case in cases:
            require(type(case) is ForecastCase)
            case.__post_init__()
            require(case.row_key not in rows and case.participant_key not in people)
            rows.add(case.row_key)
            people.add(case.participant_key)
        require(not seen_rows & rows and not seen_people & people)
        seen_rows.update(rows)
        seen_people.update(people)


def _private_bytes(path, expected_sha256, mode):
    path = Path(path)
    require(path.is_absolute() and path == path.resolve(strict=True))
    require(not any(p.is_symlink() for p in (path, *path.parents)))
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == mode)
    require(stat.S_IMODE(path.parent.stat().st_mode) == 0o700)
    require(info.st_size <= 4000000)
    data = path.read_bytes()
    require(sha256(data).hexdigest() == expected_sha256)
    return data


def _prepared_manifest(directory):
    design_raw = (ROOT / 'experiments/behavior-model/costello-numeric-forecast-design-v1.json').read_bytes()
    require(sha256(design_raw).hexdigest() == DESIGN_SHA256)
    design = _json(design_raw.decode())
    directory = Path(directory)
    manifest = _json(_private_bytes(directory/'manifest.json',
        design['prepared_private_manifest_sha256'], 0o400).decode())
    return design, manifest


def read_training(directory):
    """Native training never opens development/evaluation files or their labels."""
    design, manifest = _prepared_manifest(directory)
    pin = manifest['parts']['train_selected']
    require(pin == design['public_part_counts']['train_selected'])
    raw = _private_bytes(Path(directory)/'train_selected.jsonl', pin['sha256'], 0o600)
    cases = tuple(parse_case(_json(line)) for line in raw.decode().splitlines())
    require(len(cases) == 128 and all(c.target is not None for c in cases))
    require(len({c.row_key for c in cases}) == len(cases)
            and len({c.participant_key for c in cases}) == len(cases))
    return cases


def build_training_example(case, tokenizer):
    from .helpsteer2_candidate_eval import completion_mask
    require(type(case) is ForecastCase and case.target is not None)
    case.__post_init__()
    user = [dict(role='user', content=case.prompt)]
    prefix = tokenizer.apply_chat_template(user, tokenize=True, add_generation_prompt=True,
                                           enable_thinking=False, truncation=False)
    target = json.dumps(dict(post_belief=case.target), separators=(',', ':'))
    full = tokenizer.apply_chat_template(user+[dict(role='assistant',content=target)],
        tokenize=True, add_generation_prompt=False, enable_thinking=False, truncation=False)
    mask = completion_mask(prefix,full)
    return dict(input_ids=list(mask.input_ids),completion_mask=[int(x != -100) for x in mask.labels])


def read_prepared(directory):
    design, manifest = _prepared_manifest(directory)
    directory = Path(directory)
    expected = {'train_pool': (738,738), 'train_selected': (128,128),
                'development': (584,568), 'evaluation': (762,738)}
    require(set(manifest['parts']) == set(expected))
    parts = {}
    for name, (assigned, labelled) in expected.items():
        pin = manifest['parts'][name]
        require(pin == design['public_part_counts'][name])
        rows = _private_bytes(directory/(name+'.jsonl'), pin['sha256'], 0o600).decode().splitlines()
        cases = tuple(parse_case(_json(line)) for line in rows)
        require(len(cases) == assigned and sum(c.target is not None for c in cases) == labelled)
        parts[name] = cases
    validate_disjoint({k:parts[k] for k in ('train_selected','development','evaluation')})
    pool = parts.pop('train_pool')
    require(len({c.participant_key for c in pool}) == len(pool)
            and len({c.row_key for c in pool}) == len(pool))
    selected = tuple(sorted(pool, key=lambda c: sha256(
        ('costello-forecast-train128-v1\0'+c.participant_key).encode()).hexdigest())[:128])
    require(parts['train_selected'] == selected)
    return parts


@dataclass(frozen=True)
class Prediction:
    state: str
    raw: str | None = field(repr=False)

    def __post_init__(self):
        require(self.state in STATES)
        require(self.raw is None or type(self.raw) is str and len(self.raw) <= 128)
        if self.state == 'VALID':
            parse_prediction(self.raw)
        if self.state in ('UNKNOWN','NOT_RUN','ABSTAIN'):
            require(self.raw is None)


def score_predictions(cases, predictions):
    require(type(cases) is tuple and type(predictions) is dict)
    require(all(type(c) is ForecastCase for c in cases))
    keys = {c.row_key for c in cases}
    require(len(keys) == len(cases) and set(predictions) <= keys)
    states = dict.fromkeys(STATES, 0)
    errors, worst = [], []
    for case in cases:
        case.__post_init__()
        p = predictions.get(case.row_key, Prediction('NOT_RUN', None))
        require(type(p) is Prediction)
        p.__post_init__()
        states[p.state] += 1
        if case.target is not None:
            error = abs(parse_prediction(p.raw)-case.target) if p.state == 'VALID' else 100
            worst.append(error)
            if p.state == 'VALID':
                errors.append(error)
    labelled = sum(c.target is not None for c in cases)
    abstention_only = bool(cases) and states['ABSTAIN'] == len(cases)
    return dict(assigned=len(cases), human_labelled=labelled, human_label_missing=len(cases)-labelled,
        states=states, valid_labelled=len(errors), mae_valid_labelled=sum(errors)/len(errors) if errors else None,
        rmse_valid_labelled=(sum(x*x for x in errors)/len(errors))**0.5 if errors else None,
        worst_case_mae_all_labelled=sum(worst)/len(worst) if worst and not abstention_only else None,
        coverage=states['VALID']/len(cases) if cases else None,
        complete_forecast=bool(cases) and states['VALID'] == len(cases),
        proof='P0', human_benefit='NOT_MEASURED', can_execute=False)
