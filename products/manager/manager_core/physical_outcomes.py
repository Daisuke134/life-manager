"""D005–D007: offline physical-session joins and descriptive diagnostics.

Source objects, calibration records and meter identities are supplied declarations,
not authenticated field evidence. No function here actuates a device, establishes
causality, estimates clinical outcomes, or upgrades supplied inputs above P0.
"""
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Mapping

from manager_core.evaluation import exploratory_mean_difference
from manager_core.models.source import Source, _aware, _text
from manager_core.outcome_bench import _currency, _minor


UNITS = {
    "indoor_pm25": "ug/m3", "outdoor_pm25": "ug/m3",
    "indoor_temperature": "degC", "outdoor_temperature": "degC",
    "indoor_relative_humidity": "%", "outdoor_relative_humidity": "%",
    "power": "W", "noise": "dBA",
}
ENVIRONMENT_CHANNELS = tuple(channel for channel in UNITS if channel not in ("power", "noise"))


def _finite(value):
    return type(value) in (int, float) and isfinite(value) and abs(value) <= 1e15


def _source(value):
    if not isinstance(value, Source):
        raise ValueError("public nonpersonal Source required")


@dataclass(frozen=True)
class Calibration:
    instrument_id: str
    channel: str
    unit: str
    lower: float
    upper: float
    valid_from: datetime
    valid_until: datetime
    source: Source

    def __post_init__(self):
        _text(self.instrument_id)
        if self.channel not in UNITS or self.unit != UNITS[self.channel]:
            raise ValueError("known calibration channel and canonical unit required")
        if not _finite(self.lower) or not _finite(self.upper) or self.lower >= self.upper:
            raise ValueError("finite ordered calibration range required")
        _aware(self.valid_from)
        _aware(self.valid_until)
        if self.valid_from >= self.valid_until:
            raise ValueError("ordered calibration validity interval required")
        _source(self.source)


@dataclass(frozen=True)
class PhysicalReading:
    observation_id: str
    session_id: str
    zone_id: str
    instrument_id: str
    channel: str
    recorded_at: datetime
    value: float | None
    unit: str
    source: Source
    calibration: Calibration | None
    missing_reason: str | None = None

    def __post_init__(self):
        for item in (self.observation_id, self.session_id, self.zone_id, self.instrument_id, self.unit):
            _text(item)
        if self.channel not in UNITS:
            raise ValueError("known physical channel required")
        _aware(self.recorded_at)
        _source(self.source)
        if self.calibration is not None and not isinstance(self.calibration, Calibration):
            raise ValueError("Calibration or explicit unknown required")
        if self.value is None or self.missing_reason is not None:
            _text(self.missing_reason)
        # Bad values/units are retained as rejected rows by the analyzer, not lost.


@dataclass(frozen=True)
class PhysicalSessionDesign:
    session_id: str
    intervention_zone: str
    control_zone: str
    actuator_id: str
    executor_source_id: str
    before_start: datetime
    after_start: datetime
    end: datetime
    max_skew_seconds: float
    protocol: Source
    control_condition: str = "NO_ACTION"

    def __post_init__(self):
        for item in (self.session_id, self.intervention_zone, self.control_zone, self.actuator_id, self.executor_source_id):
            _text(item)
        for moment in (self.before_start, self.after_start, self.end):
            _aware(moment)
        if not self.before_start < self.after_start < self.end or self.intervention_zone == self.control_zone:
            raise ValueError("distinct zones and ordered before/after windows required")
        if not _finite(self.max_skew_seconds) or not 0 <= self.max_skew_seconds <= 3600:
            raise ValueError("predeclared synchronization tolerance from 0 to 3600 seconds required")
        _source(self.protocol)
        if self.protocol.retrieved_at > self.before_start:
            raise ValueError("prospective protocol reference required; metadata alone is not preregistration proof")
        if self.control_condition != "NO_ACTION":
            raise ValueError("explicit contemporaneous NO_ACTION control required")

    def period(self, at):
        if self.before_start <= at < self.after_start:
            return "before"
        if self.after_start <= at < self.end:
            return "after"
        return None


@dataclass(frozen=True)
class RejectedObservation:
    reading: PhysicalReading
    reason: str


@dataclass(frozen=True)
class SynchronizedFrame:
    zone_id: str
    at: datetime
    period: str
    observations: tuple[PhysicalReading, ...]
    missing_channels: tuple[str, ...]

    @property
    def indoor_pm25(self):
        return next(row.value for row in self.observations if row.channel == "indoor_pm25")


@dataclass(frozen=True)
class ContemporaneousPair:
    treated: SynchronizedFrame
    control: SynchronizedFrame


@dataclass(frozen=True)
class DescriptiveComparison:
    before_gap: float | None
    after_gap: float | None
    change_in_gap: float | None
    status: str
    unit: str = "ug/m3"
    causal_effect: None = None
    confidence_interval: None = None


@dataclass(frozen=True)
class MeterSummary:
    zone_id: str
    period: str
    channel: str
    unit: str
    count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class PhysicalSessionResult:
    design: PhysicalSessionDesign
    readings: tuple[PhysicalReading, ...]
    excluded: tuple[RejectedObservation, ...]
    sources: tuple[Source, ...]
    frames: tuple[SynchronizedFrame, ...]
    pairs: tuple[ContemporaneousPair, ...]
    comparison: DescriptiveComparison
    meters: tuple[MeterSummary, ...]
    harm_measurement_status: str
    cost_minor: int | None
    currency: str | None
    cost_source: Source | None
    measurement_authentication: str = "NOT_VERIFIED"
    health_outcome_status: str = "NOT_MEASURED"
    proof_level: str = "P0"
    action: str = "NO_ACTION"
    energy_kwh: None = None
    net_benefit: None = None


def _quality(design, row):
    if row.session_id != design.session_id:
        return "SESSION_MISMATCH"
    if row.zone_id not in (design.intervention_zone, design.control_zone):
        return "ZONE_MISMATCH"
    if design.period(row.recorded_at) is None:
        return "OUTSIDE_SESSION_WINDOW"
    if row.source.retrieved_at < row.recorded_at:
        return "READBACK_PRECEDES_OBSERVATION"
    if row.unit != UNITS[row.channel]:
        return "UNIT_MISMATCH"
    if row.value is None:
        return "MISSING_VALUE"
    if row.missing_reason is not None:
        return "SOURCE_QUALITY_FLAG"
    if not _finite(row.value):
        return "INVALID_VALUE"
    if ((row.channel in ("indoor_pm25", "outdoor_pm25", "power") and row.value < 0)
            or (row.channel.endswith("relative_humidity") and not 0 <= row.value <= 100)):
        return "OUTSIDE_PHYSICAL_RANGE"
    cal = row.calibration
    if cal is None:
        return "CALIBRATION_MISSING"
    if (cal.instrument_id, cal.channel, cal.unit) != (row.instrument_id, row.channel, row.unit):
        return "CALIBRATION_MISMATCH"
    if not cal.valid_from <= row.recorded_at < cal.valid_until:
        return "CALIBRATION_EXPIRED"
    if not cal.lower <= row.value <= cal.upper:
        return "OUT_OF_CALIBRATION_RANGE"
    if row.instrument_id == design.actuator_id:
        return "ACTUATOR_SELF_READING"
    if row.source.source_id == design.executor_source_id:
        return "EXECUTOR_ONLY_READING"
    return None


def _near(design, left, right):
    return abs((left - right).total_seconds()) <= design.max_skew_seconds


def _frames(design, accepted):
    anchors = tuple(row for row in accepted if row.channel == "indoor_pm25")
    result = []
    for anchor in sorted(anchors, key=lambda row: (row.recorded_at, row.zone_id, row.observation_id)):
        period = design.period(anchor.recorded_at)
        selected, missing = [anchor], []
        for channel in ENVIRONMENT_CHANNELS[1:]:
            matches = [row for row in accepted if row.channel == channel and row.zone_id == anchor.zone_id
                       and design.period(row.recorded_at) == period and _near(design, row.recorded_at, anchor.recorded_at)]
            reverse = [] if len(matches) != 1 else [other for other in anchors if other.zone_id == anchor.zone_id
                       and design.period(other.recorded_at) == period and _near(design, matches[0].recorded_at, other.recorded_at)]
            if len(matches) == len(reverse) == 1:
                selected.append(matches[0])
            else:
                missing.append(channel)
        result.append(SynchronizedFrame(anchor.zone_id, anchor.recorded_at, period, tuple(selected), tuple(missing)))
    return tuple(result)


def analyze_physical_session(design: PhysicalSessionDesign, readings: tuple[PhysicalReading, ...], *,
                             cost_minor: int | None = None, currency: str | None = None,
                             cost_source: Source | None = None, snapshots: Mapping[str, bytes] | None = None):
    """Join declared public measurements; return arithmetic without evidence promotion.

    Unambiguous mutual time matches are required, with no control or covariate
    reuse. Windows are [start, end). Measurements outside them are preserved as
    excluded. W samples do not imply kWh; dBA samples get ranges, not LAeq.
    """
    if not isinstance(design, PhysicalSessionDesign) or not isinstance(readings, tuple) or any(not isinstance(row, PhysicalReading) for row in readings):
        raise ValueError("typed immutable design and reading tuple required")
    if len({row.observation_id for row in readings}) != len(readings):
        raise ValueError("unique observation IDs required")
    _minor(cost_minor, optional=True)
    if currency is not None:
        _currency(currency)
    if cost_minor is not None and (currency is None or cost_source is None):
        raise ValueError("known cost requires its currency and source")
    if cost_source is not None:
        _source(cost_source)
    sources = {}
    references = [design.protocol] + ([cost_source] if cost_source else [])
    for row in readings:
        references.append(row.source)
        if row.calibration is not None:
            references.append(row.calibration.source)
    for ref in references:
        if ref.source_id in sources and sources[ref.source_id] != ref:
            raise ValueError("one source ID cannot identify inconsistent provenance")
        sources[ref.source_id] = ref
    if snapshots is not None:
        if not isinstance(snapshots, Mapping) or any(key not in sources for key in snapshots):
            raise ValueError("snapshot keys must identify declared sources")
        for key, payload in snapshots.items():
            sources[key].verify_content(payload)
    accepted, excluded = [], []
    for row in readings:
        reason = _quality(design, row)
        if reason:
            excluded.append(RejectedObservation(row, reason))
        else:
            accepted.append(row)
    frames = _frames(design, accepted)
    treated = [frame for frame in frames if not frame.missing_channels and frame.zone_id == design.intervention_zone]
    control = [frame for frame in frames if not frame.missing_channels and frame.zone_id == design.control_zone]
    pairs = []
    for frame in treated:
        matches = [other for other in control if other.period == frame.period and _near(design, frame.at, other.at)]
        reverse = [] if len(matches) != 1 else [other for other in treated if other.period == frame.period and _near(design, matches[0].at, other.at)]
        if len(matches) == len(reverse) == 1:
            pairs.append(ContemporaneousPair(frame, matches[0]))
    gaps = {}
    for period in ("before", "after"):
        period_pairs = [pair for pair in pairs if pair.treated.period == period]
        gaps[period] = exploratory_mean_difference([p.treated.indoor_pm25 for p in period_pairs],
                                                   [p.control.indoor_pm25 for p in period_pairs]) if period_pairs else None
    complete = all(value is not None for value in gaps.values())
    comparison = DescriptiveComparison(gaps["before"], gaps["after"], gaps["after"] - gaps["before"] if complete else None,
                                       "DESCRIPTIVE_ONLY" if complete else "INCOMPLETE_CONTEMPORANEOUS_COMPARISON")
    meters = []
    for zone in (design.intervention_zone, design.control_zone):
        for period in ("before", "after"):
            for channel in ("power", "noise"):
                rows = [row for row in accepted if row.zone_id == zone and design.period(row.recorded_at) == period and row.channel == channel]
                values = [row.value for row in rows]
                meters.append(MeterSummary(zone, period, channel, UNITS[channel], len(rows), min(values) if values else None,
                                           max(values) if values else None, sum(values) / len(values) if values and channel == "power" else None,
                                           tuple(row.observation_id for row in rows)))
    harm_status = "DECLARED_MEASUREMENTS_ONLY" if all(meter.count for meter in meters) else "INCOMPLETE"
    return PhysicalSessionResult(design, readings, tuple(excluded), tuple(sources.values()), frames, tuple(pairs), comparison,
                                 tuple(meters), harm_status, cost_minor, currency, cost_source)
