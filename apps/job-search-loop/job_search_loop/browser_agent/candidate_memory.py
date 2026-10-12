from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _flatten(prefix: str, value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _flatten(f"{prefix}.{key}" if prefix else key, child)
    else:
        yield prefix, value


def _private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_candidate_memory(
    *, profile_path: Path, resume_paths: tuple[Path, ...], output_path: Path
) -> dict[str, Any]:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    candidate = profile.get("candidate") if isinstance(profile, dict) else None
    facts = profile.get("facts") if isinstance(profile, dict) else None
    if not isinstance(candidate, dict) or not isinstance(facts, list):
        raise ValueError("private profile is missing candidate/facts")
    email = candidate.get("application_email")
    if not isinstance(email, str) or "@" not in email or any(c.isspace() for c in email):
        raise ValueError("candidate.application_email is invalid")
    if not resume_paths:
        raise ValueError("at least one resume is required")

    resume_sources = []
    resume_texts: dict[str, str] = {}
    for path in resume_paths:
        resolved = path.expanduser().resolve(strict=True)
        digest = _sha(resolved)
        completed = subprocess.run(
            ["pdftotext", "-layout", str(resolved), "-"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        resume_texts[digest] = _normalized(completed.stdout)
        resume_sources.append({"sha256": digest, "filename": resolved.name})

    concepts: list[dict[str, Any]] = []
    for concept, value in _flatten("candidate", candidate):
        concepts.append(
            {"concept": concept, "value": value, "provenance": ["private_profile"]}
        )
    for fact in facts:
        if not isinstance(fact, dict) or not all(isinstance(fact.get(k), str) for k in ("id", "claim", "evidence")):
            raise ValueError("profile fact is invalid")
        claim = fact["claim"]
        matched = [digest for digest, text in resume_texts.items() if _normalized(claim) in text]
        concepts.append(
            {
                "concept": f"fact.{fact['id']}",
                "value": claim,
                "evidence": fact["evidence"],
                "provenance": ["private_profile", *[f"resume_sha256:{v}" for v in matched]],
            }
        )
    memory = {
        "schema_version": 1,
        "profile_sha256": _sha(profile_path),
        "resume_sources": sorted(resume_sources, key=lambda value: value["sha256"]),
        "concepts": sorted(concepts, key=lambda value: value["concept"]),
    }
    _private_json(output_path, memory)
    return {
        "schema_version": 1,
        "memory_path": str(output_path.resolve()),
        "memory_sha256": _sha(output_path),
        "concept_count": len(concepts),
        "resume_count": len(resume_sources),
    }


@dataclass(frozen=True, slots=True)
class CandidateMemoryView:
    value: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "CandidateMemoryView":
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema_version") != 1:
            raise ValueError("unsupported Candidate Memory schema")
        return cls(value)

    def get(self, concept: str) -> Any:
        matches = [item for item in self.value["concepts"] if item["concept"] == concept]
        if len(matches) != 1:
            raise KeyError(concept)
        return matches[0]["value"]

    def concepts(self) -> tuple[str, ...]:
        """Return only safe schema identifiers, never private candidate values."""
        return tuple(str(item["concept"]) for item in self.value["concepts"])

    def grounding_facts(self) -> tuple[dict[str, Any], ...]:
        """Expose resume/profile claims, excluding candidate contact fields.

        This is the ai-job-search grounding boundary used by the browser model for
        novel employer questions. Values under ``candidate.*`` remain private and
        are resolved only inside typed runtime actions.
        """
        return tuple(
            {
                "concept": str(item["concept"]),
                "claim": str(item["value"]),
                "provenance": tuple(str(value) for value in item.get("provenance", ())),
            }
            for item in self.value["concepts"]
            if str(item.get("concept", "")).startswith("fact.")
            and not str(item.get("concept", "")).startswith("fact.profile.mailing_address")
            and isinstance(item.get("value"), str)
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--resume", required=True, action="append", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = build_candidate_memory(
        profile_path=args.profile, resume_paths=tuple(args.resume), output_path=args.output
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
