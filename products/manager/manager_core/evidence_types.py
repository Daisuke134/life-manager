"""R008 evidence labels: source provenance and study design are not proof levels.

These rules prevent internal relabeling, not deliberate falsification of source
metadata. A reviewed source, sound experiment and external outcome evidence are
still required. Neither an RCT label nor a passing test proves Manager impact.
"""
from __future__ import annotations
from collections import Counter
from .evidence import validate_record

_DESIGN_LABELS = {
    'randomized_trial': 'rct',
    'observational_survey': 'survey',
    'simulation': 'simulation',
    'benchmark': 'benchmark',
}
_TITLES = {
    'rct': "Human randomized trial (authors' report; not Manager field impact)",
    'survey': 'Human observational survey (not an intervention effect)',
    'simulation': 'Simulation study (not a human field trial)',
    'benchmark': 'Offline benchmark (not a new human field trial)',
    'company_claim': 'Company-reported claim (not an independent RCT)',
    'review': 'Literature review (not an additional independent trial)',
    'tool_documentation': 'Tool documentation (not evidence of beneficiary benefit)',
}


def evidence_type(record: dict) -> str:
    """Derive a label from declared, source-reviewed metadata; never from score."""
    r = validate_record(record)
    source, design = r['source']['kind'], r['study']['design']
    if source == 'company_page':
        return 'company_claim'
    if source == 'official_docs':
        if design != 'software_documentation':
            raise ValueError('official documentation cannot be labeled an empirical study')
        return 'tool_documentation'
    if source == 'review_paper':
        if design != 'review':
            raise ValueError('review cannot be labeled a new primary trial')
        return 'review'
    if design not in _DESIGN_LABELS:
        raise ValueError('primary paper needs an explicit empirical/simulation design')
    return _DESIGN_LABELS[design]


def require_type(record: dict, requested: str) -> None:
    """Reject a display/consumer attempting to upgrade the source's category."""
    if requested not in _TITLES or evidence_type(record) != requested:
        raise ValueError(f'evidence type mismatch: requested {requested}')


def label(record: dict) -> str:
    return f"{_TITLES[evidence_type(record)]}; reading={record['review']['status']}"


def count_by_type(records: list[dict]) -> dict[str, int]:
    """Research inventory counts, NEVER counts of successful interventions."""
    return dict(sorted(Counter(evidence_type(r) for r in records).items()))
