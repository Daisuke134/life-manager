from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from .candidate_memory import CandidateMemoryView

_ANYWHERE_LOCATION_PREFERENCE = "anywhere"


@dataclass(frozen=True, slots=True)
class ExperienceIntervalV1:
    start: date
    end: date
    provenance: str


@dataclass(frozen=True, slots=True)
class InferenceDecisionV1:
    concept: str
    value: Any
    kind: str
    provenance: tuple[str, ...]


def experience_years(intervals: tuple[ExperienceIntervalV1, ...]) -> float:
    if not intervals:
        return 0.0
    spans = sorted((item.start.toordinal(), item.end.toordinal(), item.provenance) for item in intervals)
    if any(end < start for start, end, _ in spans):
        raise ValueError("experience interval ends before it starts")
    merged: list[list[int]] = []
    for start, end, _ in spans:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    days = sum(end - start + 1 for start, end in merged)
    return round(days / 365.2425, 1)


def map_current_option(value: Any, options: tuple[str, ...]) -> Any:
    if not options:
        return value
    normalized = {item.casefold().strip(): item for item in options}
    text = str(value).casefold().strip()
    if text in normalized:
        return normalized[text]
    if isinstance(value, bool):
        for candidate in (("yes", "true") if value else ("no", "false")):
            if candidate in normalized:
                return normalized[candidate]
    if isinstance(value, (int, float)):
        scored = []
        for option in options:
            numbers = re.findall(r"\d+(?:\.\d+)?", option.replace(",", ""))
            if numbers:
                scored.append((min(abs(float(number) - float(value)) for number in numbers), option))
        if scored:
            return min(scored)[1]
    for conservative in ("prefer not to say", "decline to answer", "not applicable", "none", "no"):
        if conservative in normalized:
            return normalized[conservative]
    return options[0]


class StableInferencePolicy:
    def __init__(self, memory: CandidateMemoryView) -> None:
        self._memory = memory

    def _candidate(self, key: str) -> Any:
        return self._memory.get(f"candidate.{key}")

    def resolve(
        self,
        concept: str,
        *,
        options: tuple[str, ...] = (),
        country: str = "Japan",
        target_location: str = "",
        intervals: tuple[ExperienceIntervalV1, ...] = (),
        generated_narrative: str = "",
        narrative_provenance: tuple[str, ...] = (),
    ) -> InferenceDecisionV1:
        provenance: tuple[str, ...]
        if concept == "compensation.minimum_jpy":
            value, provenance = self._candidate("compensation_floor_jpy"), ("candidate.compensation_floor_jpy",)
            kind = "exact"
        elif concept == "compensation.target_jpy":
            value, provenance = self._candidate("compensation_target_jpy"), ("candidate.compensation_target_jpy",)
            kind = "exact"
        elif concept == "compensation.stretch_jpy":
            value, provenance = self._candidate("compensation_stretch_jpy"), ("candidate.compensation_stretch_jpy",)
            kind = "exact"
        elif concept == "availability.start_date":
            value, provenance, kind = self._candidate("start_date"), ("candidate.start_date",), "exact"
        elif concept.startswith("experience.") and concept.endswith(".years"):
            value = experience_years(intervals)
            provenance = tuple(item.provenance for item in intervals) or ("least_claiming_zero_duration",)
            kind = "derived" if intervals else "conservative"
        elif concept == "work_authorization.authorized":
            authorizations = self._candidate("work_authorizations")
            value = any(str(item.get("country", "")).casefold() == country.casefold() and str(item.get("status", "")).casefold() in {"authorized", "citizen", "permanent"} for item in authorizations)
            provenance, kind = ("candidate.work_authorizations",), "derived"
        elif concept == "work_authorization.sponsorship_required":
            authorized = self.resolve("work_authorization.authorized", country=country)
            value, provenance, kind = not bool(authorized.value), authorized.provenance, "derived"
        elif concept == "mobility.relocation":
            preferences = self._candidate("location_preferences")
            target = target_location.casefold().strip()
            normalized_preferences = tuple(str(item).casefold().strip() for item in preferences)
            # "Anywhere" is an explicit preference, not evidence of work authorization.
            value = bool(target) and (
                _ANYWHERE_LOCATION_PREFERENCE in normalized_preferences
                or any(
                    target in item or item in target
                    for item in normalized_preferences
                )
            )
            provenance, kind = ("candidate.location_preferences",), "derived"
        elif concept.startswith("demographic."):
            value, provenance, kind = "Prefer not to say", ("non_disclosure_policy",), "conservative"
        elif concept.startswith("narrative.") and generated_narrative.strip() and narrative_provenance:
            value, provenance, kind = generated_narrative.strip(), narrative_provenance, "generated"
        else:
            value, provenance, kind = "Not provided", ("least_claiming_fallback",), "conservative"
        return InferenceDecisionV1(concept, map_current_option(value, options), kind, provenance)
