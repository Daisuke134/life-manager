from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from .agent_runner import AgentRunner, wrap_untrusted
from .state import is_excluded_employer


_FIELDS = {"company", "host", "tenant", "site", "search_text"}


def validate_sources(
    value: dict[str, Any], exclusions: frozenset[str] = frozenset()
) -> tuple[dict[str, str], ...]:
    rows = value.get("sources") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        raise ValueError("sources must be an array")
    accepted = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != _FIELDS:
            raise ValueError("source fields do not match the contract")
        source = {key: str(row[key]).strip() for key in _FIELDS}
        host = source["host"].casefold()
        if (
            not source["company"]
            or is_excluded_employer(source["company"], exclusions)
            or not host.endswith(".myworkdayjobs.com")
            or "/" in host
            or not re.fullmatch(r"[A-Za-z0-9_-]+", source["tenant"])
            or not re.fullmatch(r"[A-Za-z0-9_-]+", source["site"])
            or not source["search_text"]
        ):
            continue
        source["host"] = host
        identity = (
            host,
            source["tenant"],
            source["site"],
            source["search_text"].casefold(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        accepted.append(source)
    if not accepted:
        raise ValueError("model returned no valid non-excluded Workday sources")
    return tuple(accepted)


def merge_sources(
    previous: tuple[dict[str, str], ...],
    discovered: tuple[dict[str, str], ...],
) -> tuple[dict[str, str], ...]:
    merged = []
    seen = set()
    # The refreshed query wins for a known board; keeping the previous row first
    # leaves location-limited search text permanently in the active registry.
    for source in discovered + previous:
        identity = (source["host"], source["tenant"], source["site"])
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(source)
    return tuple(merged)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-memory", required=True, type=Path)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    previous = ""
    previous_sources: tuple[dict[str, str], ...] = ()
    if args.previous and args.previous.is_file():
        previous = args.previous.read_text(encoding="utf-8")
        previous_sources = validate_sources(json.loads(previous))
    memory = args.candidate_memory.read_text(encoding="utf-8")
    memory_value = json.loads(memory)
    exclusions = frozenset()
    for concept in memory_value.get("concepts", []):
        if concept.get("concept") == "candidate.employer_exclusions":
            raw = concept.get("value")
            if isinstance(raw, list) and all(
                isinstance(item, str) and item.strip() for item in raw
            ):
                exclusions = frozenset(item.strip() for item in raw)
            break
    previous_sources = tuple(
        source
        for source in previous_sources
        if not is_excluded_employer(source["company"], exclusions)
    )
    prompt = (
        "Act as the source-discovery agent for a worldwide autonomous job hunter. "
        "Use available internet/search tools now. Find diverse employers currently "
        "hiring through official Workday career sites. Remote, onsite, and hybrid roles "
        "worldwide are all in scope; do not limit discovery to Tokyo, Japan, or any other "
        "country. Do not choose jobs or judge candidate fit. Choose focused searches for "
        "full-time professional roles where the candidate can answer application questions "
        "truthfully. Include implementation, customer, product, operations, marketing, "
        "consulting, support, analyst, specialist, associate, engineering, and manager work. "
        "Do not exclude a role because its title contains Senior, Lead, Principal, Director, "
        "or Manager; use the responsibilities and mandatory requirements. Exclude only "
        "internships, CEO/C-suite scope, or unrelated regulated professions. Do not search "
        "for AI as a keyword alone when the candidate's implementation, customer, product, "
        "or agent-deployment evidence suggests a more precise query. Use a short "
        "Workday-native search_text of two or three role/skill terms; never return a sentence, "
        "a city or country name, or a work-arrangement term such as remote, onsite, or hybrid. "
        "For every previous source identity, return a refreshed search_text using grounded "
        "role or skill terms and no location-specific search terms, so old searches cannot "
        "keep narrowing the active registry. Then add other diverse Workday employers. "
        "Return the exact CXS source identity needed to query each official site: "
        "company, myworkdayjobs host, tenant, site, and a focused Workday search_text "
        "chosen from the candidate's grounded experience. Return multiple rows for a "
        "company when distinct searches are useful. Validate each source against its "
        "official HTTPS Workday page or CXS endpoint. Do not return excluded employers "
        "from candidate memory. Do not limit results to companies seen previously. "
        "Return only the schema.\n\n"
        + wrap_untrusted("candidate_memory", memory)
        + ("\n\n" + wrap_untrusted("previous_sources", previous) if previous else "")
    )
    runner = AgentRunner(evidence_root=args.evidence_root, runner_path=args.runner)
    result = runner.run(
        task="improve",
        prompt=prompt,
        schema_path=args.schema,
        workdir=args.workdir,
        run_id=f"workday-sources-{uuid.uuid4().hex}",
    )
    sources = merge_sources(previous_sources, validate_sources(result, exclusions))
    output = {"version": 1, "sources": list(sources)}
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
