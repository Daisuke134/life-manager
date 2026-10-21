"""Inert opt-in and assignment-health preparation for owned support routes.

GrowthBook assigns fictional units. SciPy evaluates sample-ratio mismatch.
Manager supplies contract validation, never a new allocator or consent service.
Self-supplied claims, configuration hashes and assignment rows authenticate
nothing. Every result forbids live action. Real-participant inputs are refused
before optional engines run. No network fetch, tracking callback, cookie,
storage, website update or experiment-activation path exists in this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import math
import re
from types import MappingProxyType


GROWTHBOOK_VERSION = "3.2.2"
SCIPY_VERSION = "1.15.3"
NUMPY_VERSION = "2.2.6"
ROUTES = MappingProxyType({domain: f"/manager-support/{domain}.html"
                          for domain in ("finance", "mental", "physical")})
CONTROL_ROUTE = "/manager-support/control.html"
MAX_SNAPSHOT_UNITS = 10_000
SYNTHETIC_ID = re.compile(r"synthetic-unit-[0-9]{6}")


@dataclass(frozen=True)
class ExperimentConfig:
    domain: str
    experiment_key: str
    seed: str
    treatment_route: str
    schema: str = "manager.synthetic-experiment.v1"
    unit_type: str = "SYNTHETIC_UNIT"
    hash_attribute: str = "id"
    hash_version: int = 2
    variations: tuple[str, str] = ("NO_ACTION", "OFFICIAL_RESOURCE_DIRECTORY")
    weights: tuple[float, float] = (.5, .5)
    coverage: float = 1.0
    control_route: str = CONTROL_ROUTE
    sdk_version: str = GROWTHBOOK_VERSION
    scipy_version: str = SCIPY_VERSION
    numpy_version: str = NUMPY_VERSION
    srm_alpha: float = .001
    min_cell_count: int = 5
    min_total_units: int = 14
    health_ttl_seconds: int = 3600
    data_class: str = "SYNTHETIC_ONLY"


@dataclass(frozen=True)
class SyntheticUnit:
    unit_id: str
    data_class: str = "SYNTHETIC_ONLY"


@dataclass(frozen=True)
class OptInClaim:
    """A fictional exercise input. This is not authenticated human consent."""
    unit_id: str
    config_sha256: str
    issued_at: datetime
    expires_at: datetime
    status: str = "GRANTED"
    purpose: str = "OFFLINE_SYNTHETIC_ASSIGNMENT"
    data_class: str = "SYNTHETIC_ONLY"


@dataclass(frozen=True)
class AssignmentRecord:
    unit_id: str
    config_sha256: str
    domain: str
    experiment_key: str
    seed: str
    unit_type: str
    hash_attribute: str
    hash_version: int
    variation_id: int
    variation: str
    assigned_at: datetime
    sdk_version: str = GROWTHBOOK_VERSION
    data_class: str = "SYNTHETIC_ONLY"


@dataclass(frozen=True)
class AssignmentSnapshot:
    """Declared unique assignments, never a verified exposure/participant log."""
    config_sha256: str
    observed_at: datetime
    assignments: tuple[AssignmentRecord, ...]


@dataclass(frozen=True)
class OfflineBoundary:
    # init=False prevents a caller from constructing a positive live flag.
    live_action_allowed: bool = field(default=False, init=False)
    experiment_enabled: bool = field(default=False, init=False)
    action_executed: bool = field(default=False, init=False)
    external_authority: str = field(default="NOT_ESTABLISHED", init=False)
    human_outcome: str = field(default="NOT_MEASURED", init=False)
    causal_lift_status: str = field(default="NOT_ESTIMATED", init=False)
    proof_level: str = field(default="P0", init=False)


@dataclass(frozen=True)
class AssignmentPreparation(OfflineBoundary):
    status: str
    assignment: AssignmentRecord | None = None
    decision: str = field(default="NO_ACTION", init=False)


@dataclass(frozen=True)
class AssignmentHealth(OfflineBoundary):
    status: str
    reason: str
    config_sha256: str | None = None
    snapshot_sha256: str | None = None
    assessed_at: datetime | None = None
    counts: tuple[int, int] | None = None
    total_units: int | None = None
    expected_counts: tuple[float, float] | None = None
    statistic: float | None = None
    p_value: float | None = None
    alpha: float = field(default=.001, init=False)


@dataclass(frozen=True)
class ExperimentDecision(OfflineBoundary):
    decision: str
    reason: str
    candidate_route: str | None = None
    assignment: AssignmentRecord | None = None
    health: AssignmentHealth | None = None


class OptionalDependencyUnavailable(RuntimeError):
    pass


def config_for(domain: str) -> ExperimentConfig:
    if type(domain) is not str or domain not in ROUTES:
        raise ValueError("only the existing finance, mental and physical routes are in scope")
    return ExperimentConfig(domain, f"manager-support-{domain}-v1",
                            f"manager-support-{domain}-synthetic-v1", ROUTES[domain])


def _valid_config(config) -> bool:
    if type(config) is not ExperimentConfig or type(config.domain) is not str or config.domain not in ROUTES:
        return False
    expected = config_for(config.domain)
    if any(type(getattr(config, f.name)) is not type(getattr(expected, f.name)) for f in fields(config)):
        return False
    return (all(type(w) is float for w in config.weights)
            and all(type(v) is str for v in config.variations) and config == expected)


def _json_default(value):
    if type(value) is datetime:
        return value.isoformat()
    raise TypeError("not a canonical contract value")


def _digest(value):
    # Artifact identity only. This SHA256 does not assign units or grant rights.
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False, default=_json_default).encode()
    return sha256(encoded).hexdigest()


def config_hash(config: ExperimentConfig) -> str:
    if not _valid_config(config):
        raise ValueError("configuration is not the fixed synthetic contract")
    return _digest(asdict(config))


def _aware(value) -> bool:
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None


def _unit_id(value) -> bool:
    return type(value) is str and SYNTHETIC_ID.fullmatch(value) is not None


def _require_version(package, expected):
    try:
        observed = version(package)
    except PackageNotFoundError as exc:
        raise OptionalDependencyUnavailable(f"{package}=={expected} is absent") from exc
    if observed != expected:
        raise OptionalDependencyUnavailable(f"{package} version differs from the pinned exercise")


@lru_cache(maxsize=1)
def _sdk_classes():
    _require_version("growthbook", GROWTHBOOK_VERSION)
    try:
        from growthbook import GrowthBook, Experiment
    except (ImportError, OSError) as exc:
        raise OptionalDependencyUnavailable("pinned GrowthBook could not load") from exc
    return GrowthBook, Experiment


def _valid_outcome(value, config):
    return (type(value) is tuple and len(value) == 2 and type(value[0]) is int
            and value[0] in (0, 1) and type(value[1]) is str
            and value[1] == config.variations[value[0]])


def _assign_with_sdk(config, unit_id):
    GrowthBook, Experiment = _sdk_classes()
    experiment = Experiment(
        key=config.experiment_key, variations=list(config.variations),
        weights=list(config.weights), coverage=config.coverage,
        seed=config.seed, hashAttribute=config.hash_attribute,
        hashVersion=config.hash_version, active=True,
        disableStickyBucketing=True,
    )
    client = GrowthBook(
        attributes={config.hash_attribute: unit_id}, enabled=True,
        api_host="", client_key="", remote_eval=False, streaming=False,
        defer_tracking=False, on_experiment_viewed=None, on_feature_usage=None,
        sticky_bucket_service=None, plugins=[],
    )
    try:
        result = client.run(experiment)
        outcome = result.variationId, result.value
        if (result.inExperiment is not True or result.hashUsed is not True
                or result.hashAttribute != config.hash_attribute
                or result.hashValue != unit_id or result.stickyBucketUsed is not False
                or not _valid_outcome(outcome, config)):
            raise ValueError("SDK did not produce a hashed assignment for this exact unit")
        return outcome
    finally:
        client.destroy()


@lru_cache(maxsize=1)
def _scipy_chisquare():
    _require_version("scipy", SCIPY_VERSION)
    _require_version("numpy", NUMPY_VERSION)
    try:
        from scipy.stats import chisquare
    except (ImportError, OSError) as exc:
        raise OptionalDependencyUnavailable("pinned SciPy could not load") from exc
    return chisquare


def _chisquare_with_scipy(counts, weights):
    result = _scipy_chisquare()(f_obs=list(counts),
                               f_exp=[sum(counts) * weight for weight in weights], ddof=0)
    return float(result.statistic), float(result.pvalue)


def _consent_error(config, unit, consent, now):
    if not _aware(now):
        return "INVALID_CLOCK"
    if type(unit) is not SyntheticUnit:
        return "INVALID_UNIT_ID"
    if unit.data_class != "SYNTHETIC_ONLY":
        return "REAL_PARTICIPANT_BLOCKED"
    if not _unit_id(unit.unit_id):
        return "INVALID_UNIT_ID"
    if (type(consent) is not OptInClaim or not _aware(consent.issued_at)
            or not _aware(consent.expires_at) or consent.expires_at <= consent.issued_at):
        return "MISSING_OR_INVALID_CONSENT"
    if (consent.unit_id != unit.unit_id or consent.config_sha256 != config_hash(config)
            or consent.purpose != "OFFLINE_SYNTHETIC_ASSIGNMENT"
            or consent.data_class != "SYNTHETIC_ONLY"):
        return "CONSENT_BINDING_MISMATCH"
    if consent.status == "REVOKED":
        return "CONSENT_REVOKED"
    if consent.status != "GRANTED":
        return "CONSENT_NOT_GRANTED"
    if now < consent.issued_at:
        return "CONSENT_NOT_YET_VALID"
    if now >= consent.expires_at:
        return "CONSENT_EXPIRED"
    return None


def _valid_record(record, config, observed_at):
    if (type(record) is not AssignmentRecord or not _unit_id(record.unit_id)
            or not _aware(record.assigned_at) or record.assigned_at > observed_at
            or record.data_class != "SYNTHETIC_ONLY"
            or record.config_sha256 != config_hash(config)
            or not _valid_outcome((record.variation_id, record.variation), config)):
        return False
    return all(type(getattr(record, name)) is type(getattr(config, name))
               and getattr(record, name) == getattr(config, name)
               for name in ("domain", "experiment_key", "seed", "unit_type", "hash_attribute", "hash_version", "sdk_version"))


def prepare_assignment(config, unit, consent, now, *, previous=None) -> AssignmentPreparation:
    """Obtain/replay a fictional SDK assignment without admitting any action."""
    if not _valid_config(config):
        return AssignmentPreparation("INVALID_CONFIGURATION")
    error = _consent_error(config, unit, consent, now)
    if error:
        return AssignmentPreparation(error)
    try:
        first = _assign_with_sdk(config, unit.unit_id)
        second = _assign_with_sdk(config, unit.unit_id)
    except OptionalDependencyUnavailable:
        return AssignmentPreparation("SDK_UNAVAILABLE")
    except Exception:
        return AssignmentPreparation("SDK_ASSIGNMENT_INVALID")
    if not _valid_outcome(first, config) or not _valid_outcome(second, config):
        return AssignmentPreparation("SDK_ASSIGNMENT_INVALID")
    if first != second:
        return AssignmentPreparation("ASSIGNMENT_DRIFT")
    if previous is not None:
        if (not _valid_record(previous, config, now) or previous.unit_id != unit.unit_id
                or (previous.variation_id, previous.variation) != first):
            return AssignmentPreparation("ASSIGNMENT_DRIFT")
        return AssignmentPreparation("SYNTHETIC_ASSIGNMENT_REUSED", previous)
    record = AssignmentRecord(
        unit.unit_id, config_hash(config), config.domain, config.experiment_key,
        config.seed, config.unit_type, config.hash_attribute, config.hash_version,
        first[0], first[1], now,
    )
    return AssignmentPreparation("SYNTHETIC_ASSIGNMENT_PREPARED", record)


def assignment_health(config, snapshot, now) -> AssignmentHealth:
    """Recompute unique-unit assignment counts and a fixed-ratio SRM diagnostic.

    All rows must replay under the actual SDK. Missing IDs, duplicates or stale
    snapshots are errors, not rows to discard until a desirable p-value appears.
    A healthy split supplies no outcome, treatment-effect or consent evidence.
    """
    if not _valid_config(config):
        return AssignmentHealth("UNAVAILABLE", "INVALID_CONFIGURATION")
    if not _aware(now):
        return AssignmentHealth("UNAVAILABLE", "INVALID_CLOCK")
    if (type(snapshot) is not AssignmentSnapshot or not _aware(snapshot.observed_at)
            or snapshot.observed_at > now or type(snapshot.assignments) is not tuple
            or len(snapshot.assignments) > MAX_SNAPSHOT_UNITS):
        return AssignmentHealth("UNAVAILABLE", "HEALTH_UNAVAILABLE")
    if snapshot.config_sha256 != config_hash(config):
        return AssignmentHealth("UNAVAILABLE", "CONFIGURATION_DRIFT")
    if (now - snapshot.observed_at).total_seconds() > config.health_ttl_seconds:
        return AssignmentHealth("UNAVAILABLE", "HEALTH_STALE")
    seen = set()
    for record in snapshot.assignments:
        if type(record) is not AssignmentRecord or not _unit_id(record.unit_id):
            return AssignmentHealth("UNAVAILABLE", "INVALID_ASSIGNMENT_RECORD")
        if record.unit_id in seen:
            return AssignmentHealth("UNAVAILABLE", "DUPLICATE_UNIT")
        seen.add(record.unit_id)
        if not _valid_record(record, config, snapshot.observed_at):
            return AssignmentHealth("UNAVAILABLE", "INVALID_ASSIGNMENT_RECORD")
    counts = [0, 0]
    try:
        for record in snapshot.assignments:
            observed = _assign_with_sdk(config, record.unit_id)
            if not _valid_outcome(observed, config) or observed != (record.variation_id, record.variation):
                return AssignmentHealth("UNAVAILABLE", "ASSIGNMENT_DRIFT")
            counts[record.variation_id] += 1
    except Exception:
        return AssignmentHealth("UNAVAILABLE", "HEALTH_UNAVAILABLE")
    counts = tuple(counts)
    expected = tuple(len(seen) * weight for weight in config.weights)
    diagnostic = dict(config_sha256=config_hash(config), snapshot_sha256=_digest(asdict(snapshot)),
                      assessed_at=now, counts=counts, total_units=len(seen), expected_counts=expected)
    if (len(seen) < config.min_total_units or min(counts) < config.min_cell_count
            or min(expected) < config.min_cell_count):
        return AssignmentHealth("UNAVAILABLE", "INSUFFICIENT_COUNTS", **diagnostic)
    try:
        statistic, p_value = _chisquare_with_scipy(counts, config.weights)
        if (type(statistic) not in (int, float) or type(p_value) not in (int, float)
                or not math.isfinite(statistic) or statistic < 0
                or not math.isfinite(p_value) or not 0 <= p_value <= 1):
            raise ValueError("invalid assignment-health result")
    except Exception:
        return AssignmentHealth("UNAVAILABLE", "HEALTH_UNAVAILABLE", **diagnostic)
    diagnostic.update(statistic=float(statistic), p_value=float(p_value))
    if p_value < config.srm_alpha:
        return AssignmentHealth("SAMPLE_RATIO_MISMATCH", "SAMPLE_RATIO_MISMATCH", **diagnostic)
    return AssignmentHealth("HEALTHY", "SRM_NOT_DETECTED", **diagnostic)


def evaluate_candidate(config, unit, consent, snapshot, now, *, previous=None) -> ExperimentDecision:
    """Return NO_ACTION or a SYNTHETIC_CANDIDATE, always with live action false.

    The API accepts no external-authority boolean or precomputed healthy flag.
    A future separately authorized human integration needs its own reviewed
    identity, consent, exposure, withdrawal, outcome and operational contracts.
    """
    prepared = prepare_assignment(config, unit, consent, now, previous=previous)
    if prepared.assignment is None:
        return ExperimentDecision("NO_ACTION", prepared.status)
    health = assignment_health(config, snapshot, now)
    if health.status != "HEALTHY":
        return ExperimentDecision("NO_ACTION", health.reason, assignment=prepared.assignment, health=health)
    matches = [r for r in snapshot.assignments if r.unit_id == unit.unit_id]
    if len(matches) != 1:
        return ExperimentDecision("NO_ACTION", "ASSIGNMENT_MISSING", health=health)
    assigned = matches[0]
    if (assigned.variation_id, assigned.variation) != (prepared.assignment.variation_id, prepared.assignment.variation):
        return ExperimentDecision("NO_ACTION", "ASSIGNMENT_DRIFT", health=health)
    if assigned.variation_id == 0:
        return ExperimentDecision("NO_ACTION", "CONTROL_HOLDOUT", assignment=assigned, health=health)
    return ExperimentDecision("SYNTHETIC_CANDIDATE", "OFFLINE_CONTRACT_ONLY",
                              candidate_route=config.treatment_route, assignment=assigned, health=health)
