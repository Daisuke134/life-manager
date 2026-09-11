#!/usr/bin/env python3
"""One DOM contract for every marketplace adapter: exactly one match, or say what you saw.

Three marketplaces each wrote their own strict matcher, and all three threw the same information
away. Measured 2026-09-07, each having cost days:

    Coconala   source_not_found        discarded the observed page title
    Coconala   form_state:absent       collapsed two causes with opposite fixes
    Lancers    proposal_form_changed   81 skips in one day, naming none of ten selectors
    CrowdWorks selector_unobserved     had the selector in hand and dropped it

The failure is never the strict matching itself -- a form field that matches twice is as broken as
one that matches zero times, and a lane that submits into an ambiguous form is worse than one that
refuses. The failure is refusing anonymously, because a marketplace changes its markup eventually
and the lane then reports "nothing was suitable" forever.

So: keep the strictness, and make the refusal name the selector, the count, and the page it was
looking at. A lane using this can be repaired from one wake's evidence instead of a day's
archaeology.

Adapters stay thin. This does not know what a proposal is, what a form means, or which field
matters -- only that the caller asked for exactly one of something and did not get it.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable, Optional

__all__ = [
    "DomContractError",
    "exactly_one",
    "visible_one",
    "record_failure",
    "failures",
]


class DomContractError(Exception):
    """A selector did not match exactly one element.

    Carries `.selector`, `.found`, `.why` and `.observed` so a caller can re-raise its own stable
    reason code without losing what was seen.
    """

    def __init__(self, selector: str, why: str, found: Any = None, observed: Any = None):
        super().__init__(f"{why}:{selector}")
        self.selector, self.why, self.found, self.observed = selector, why, found, observed


def _evidence_path(evidence_dir: Path, evidence_path: Optional[Path] = None) -> Path:
    return Path(evidence_path) if evidence_path is not None else Path(evidence_dir) / "dom-contract-failures.jsonl"


def record_failure(
    evidence_dir: Path,
    *,
    platform: str,
    selector: str,
    why: str,
    found: Any = None,
    observed: Any = None,
    evidence_path: Optional[Path] = None,
) -> None:
    """Append one line describing a refusal. Never raises: diagnostics must not fail a lane."""
    try:
        row = {
            "platform": str(platform),
            "selector": str(selector)[:300],
            "why": str(why),
            "found": found,
            "observed": observed,
            "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        path = _evidence_path(evidence_dir, evidence_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        return


def failures(evidence_dir: Path) -> list[dict]:
    """Read back what was recorded. Used by tests and by whoever repairs the selectors."""
    path = _evidence_path(evidence_dir)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _observe(observe: Optional[Callable[[], Any]]) -> Any:
    """The page's own identity at the moment of refusal. A selector alone cannot say
    'you were on the login page', which is how a session failure reads as a markup change."""
    if observe is None:
        return None
    try:
        return observe()
    except Exception:
        return None


def exactly_one(
    locator: Any,
    *,
    platform: str,
    evidence_dir: Path,
    selector: Optional[str] = None,
    observe: Optional[Callable[[], Any]] = None,
    evidence_path: Optional[Path] = None,
) -> Any:
    """Return the locator when it matches exactly one element, else record and raise.

    `selector` is optional because a Playwright locator's repr already carries it; pass it when the
    caller has the string and the repr would be less readable.
    """
    name = selector if selector is not None else str(locator)
    try:
        found = int(locator.count())
    except Exception:
        record_failure(evidence_dir, platform=platform, selector=name,
                       why="count_failed", observed=_observe(observe), evidence_path=evidence_path)
        raise DomContractError(name, "count_failed", None) from None

    if found != 1:
        observed = _observe(observe)
        record_failure(evidence_dir, platform=platform, selector=name,
                       why="count_not_one", found=found, observed=observed,
                       evidence_path=evidence_path)
        raise DomContractError(name, "count_not_one", found, observed)
    return locator


def visible_one(
    locator: Any,
    *,
    platform: str,
    evidence_dir: Path,
    selector: Optional[str] = None,
    observe: Optional[Callable[[], Any]] = None,
    evidence_path: Optional[Path] = None,
) -> Any:
    """`exactly_one`, and the element must be visible.

    The visibility probe is deliberately separate from the verdict. Re-raising every exception from
    `is_visible()` was how a detached node -- the ordinary sign that the page re-rendered under the
    lane -- became the one failure that stayed anonymous.
    """
    value = exactly_one(locator, platform=platform, evidence_dir=evidence_dir,
                        selector=selector, observe=observe, evidence_path=evidence_path)
    name = selector if selector is not None else str(locator)
    try:
        visible = value.is_visible()
    except Exception:
        observed = _observe(observe)
        record_failure(evidence_dir, platform=platform, selector=name,
                       why="visibility_check_failed", found=1, observed=observed,
                       evidence_path=evidence_path)
        raise DomContractError(name, "visibility_check_failed", 1, observed) from None

    if not visible:
        observed = _observe(observe)
        record_failure(evidence_dir, platform=platform, selector=name,
                       why="not_visible", found=1, observed=observed,
                       evidence_path=evidence_path)
        raise DomContractError(name, "not_visible", 1, observed)
    return value
