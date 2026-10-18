"""Validated, immutable contracts for the ACS population component."""
from dataclasses import dataclass
from datetime import datetime
import math
import re


class PopulationDataError(ValueError):
    """Invalid data or an experiment whose preconditions are not satisfied."""


def numbers(values, size, name):
    if not isinstance(values, tuple) or len(values) != size:
        raise PopulationDataError(f'{name}: expected tuple of {size} numbers')
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise PopulationDataError(f'{name}: expected finite nonnegative numbers')


def total_valid(total):
    numbers((total,), 1, 'total')
    if total <= 0:
        raise PopulationDataError('total must be positive')


def same_total(values, total):
    if not math.isclose(math.fsum(values), total, rel_tol=1e-12, abs_tol=1e-8):
        raise PopulationDataError('counts do not sum to total')


def digest_valid(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise PopulationDataError('invalid SHA256')


def geo_valid(value):
    if not isinstance(value, str) or not re.fullmatch(r'0400000US[0-9]{2}', value):
        raise PopulationDataError('expected state-level GEO_ID')


@dataclass(frozen=True)
class SourceRef:
    url: str
    table: str
    period: str
    universe: str
    acquired_at: str
    extract_sha256: str

    def __post_init__(self):
        digest_valid(self.extract_sha256)
        if self.table != 'B17001' or self.period != '2020-2024' or self.universe != 'Population for whom poverty status is determined':
            raise PopulationDataError('unexpected ACS scope')
        if not isinstance(self.url, str) or not self.url.startswith('https://'):
            raise PopulationDataError('expected HTTPS source URL')
        try:
            if datetime.fromisoformat(self.acquired_at).tzinfo is None:
                raise ValueError('timezone required')
        except (ValueError, TypeError) as exc:
            raise PopulationDataError('invalid acquisition timestamp') from exc


@dataclass(frozen=True)
class JointTable:
    geo_id: str
    source: SourceRef
    counts: tuple[float, ...]
    total: float

    def __post_init__(self):
        geo_valid(self.geo_id)
        if not isinstance(self.source, SourceRef): raise PopulationDataError('invalid source')
        numbers(self.counts, 6, 'joint counts'); total_valid(self.total)
        same_total(self.counts, self.total)


@dataclass(frozen=True)
class Marginals:
    geo_id: str
    source: SourceRef
    poverty: tuple[float, float]
    age: tuple[float, float, float]
    total: float

    def __post_init__(self):
        geo_valid(self.geo_id)
        if not isinstance(self.source, SourceRef): raise PopulationDataError('invalid source')
        numbers(self.poverty, 2, 'poverty'); numbers(self.age, 3, 'age'); total_valid(self.total)
        same_total(self.poverty, self.total); same_total(self.age, self.total)


@dataclass(frozen=True)
class FitResult:
    geo_id: str
    method: str
    counts: tuple[float, ...]
    iterations: int
    max_residual: float
    seed_sha256: str | None
    target_source_sha256: str

    def __post_init__(self):
        geo_valid(self.geo_id); numbers(self.counts, 6, 'prediction'); total_valid(math.fsum(self.counts))
        if self.method not in ('independent', 'ipf'): raise PopulationDataError('unknown method')
        if type(self.iterations) is not int or self.iterations < 0: raise PopulationDataError('invalid iterations')
        numbers((self.max_residual,), 1, 'residual'); digest_valid(self.target_source_sha256)
        if self.seed_sha256 is not None: digest_valid(self.seed_sha256)


@dataclass(frozen=True)
class PopulationScore:
    geo_id: str
    method: str
    tvd: float
    max_cell_error_pp: float
    poverty_rate_error_pp: tuple[float | None, float | None, float | None]

    def __post_init__(self):
        geo_valid(self.geo_id)
        if self.method not in ('independent', 'ipf'):
            raise PopulationDataError('unknown score method')
        numbers((self.tvd,), 1, 'TVD')
        numbers((self.max_cell_error_pp,), 1, 'cell error')
        if self.tvd > 1 or self.max_cell_error_pp > 100:
            raise PopulationDataError('score outside probability/percentage-point range')
        if not isinstance(self.poverty_rate_error_pp, tuple) or len(self.poverty_rate_error_pp) != 3:
            raise PopulationDataError('expected immutable tuple of three age-rate errors')
        for rate in self.poverty_rate_error_pp:
            if rate is not None:
                numbers((rate,), 1, 'age-rate error')
                if rate > 100:
                    raise PopulationDataError('age-rate error exceeds 100 percentage points')
