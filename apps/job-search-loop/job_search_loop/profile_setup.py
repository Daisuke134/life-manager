from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import ConfigError, validate_profile


PLACEHOLDERS = {
    "replace_me",
    "replace me",
    "todo",
    "tbd",
    "unknown",
    "example",
}


class ProfileSetupError(RuntimeError):
    pass


def propose_profile(
    *,
    facts: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    resume_path: Path,
) -> dict[str, Any]:
    """Build a Mercor profile proposal bound to private verified facts and a PDF."""
    if not resume_path.expanduser().is_file():
        raise ProfileSetupError("resume file is unavailable")
    fact_map: dict[str, Mapping[str, Any]] = {}
    for fact in facts:
        identifier = fact.get("id") if isinstance(fact, Mapping) else None
        if not isinstance(identifier, str) or not identifier.strip():
            continue
        fact_map[identifier.strip()] = fact
    if not fact_map:
        raise ProfileSetupError("verified fact bank is empty")
    normalized_claims: list[dict[str, str]] = []
    fact_ids: list[str] = []
    for claim in claims:
        fact_id = claim.get("fact_id") if isinstance(claim, Mapping) else None
        text = claim.get("text") if isinstance(claim, Mapping) else None
        if not isinstance(fact_id, str) or fact_id.strip() not in fact_map:
            raise ProfileSetupError("claim requires a verified fact id")
        if not isinstance(text, str) or not text.strip():
            raise ProfileSetupError("profile claim text is required")
        if _contains_placeholder(text):
            raise ProfileSetupError("profile claim contains a placeholder")
        row = {"fact_id": fact_id.strip(), "text": text.strip()}
        section = claim.get("section") if isinstance(claim, Mapping) else None
        if section is not None:
            if not isinstance(section, str) or not section.strip():
                raise ProfileSetupError("profile claim section is invalid")
            row["section"] = section.strip()
        normalized_claims.append(row)
        if row["fact_id"] not in fact_ids:
            fact_ids.append(row["fact_id"])
    if not normalized_claims:
        raise ProfileSetupError("profile proposal needs at least one verified claim")
    resume_sha256 = hashlib.sha256(resume_path.expanduser().read_bytes()).hexdigest()
    fields = {"claims": normalized_claims}
    field_hashes = {
        key: hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for key, value in fields.items()
    }
    version_payload = {
        "fact_ids": fact_ids,
        "fields": fields,
        "field_hashes": field_hashes,
        "resume_sha256": resume_sha256,
    }
    profile_version = hashlib.sha256(
        json.dumps(version_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "version": 1,
        "profile_version": profile_version,
        "fact_ids": fact_ids,
        "fields": fields,
        "field_hashes": field_hashes,
        "resume_sha256": resume_sha256,
    }


def activate_profile(proposal: Mapping[str, Any], readback: Mapping[str, Any]) -> bool:
    """Activate only an authenticated, exact profile and résumé readback."""
    return (
        isinstance(proposal, Mapping)
        and isinstance(readback, Mapping)
        and readback.get("authenticated") is True
        and readback.get("resume_visible") is True
        and readback.get("parser_reviewed") is True
        and readback.get("profile_version") == proposal.get("profile_version")
        and readback.get("resume_sha256") == proposal.get("resume_sha256")
        and readback.get("field_hashes") == proposal.get("field_hashes")
    )


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in PLACEHOLDERS or normalized.startswith("replace_me_")
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    return False


def prepare_profile(value: Any) -> dict[str, Any]:
    if _contains_placeholder(value):
        raise ProfileSetupError("profile contains a placeholder value")
    try:
        profile = validate_profile(value)
    except ConfigError as error:
        raise ProfileSetupError(str(error)) from error
    candidate = profile["candidate"]
    email = candidate.get("application_email")
    if (
        not isinstance(email, str)
        or "@" not in email
        or any(character.isspace() for character in email)
    ):
        raise ProfileSetupError(
            "profile.candidate.application_email must be a valid email"
        )
    materials = profile.get("materials")
    resumes = materials.get("resumes") if isinstance(materials, dict) else None
    if not isinstance(resumes, dict):
        raise ProfileSetupError("profile.materials.resumes is required")
    engineering = resumes.get("engineering")
    if not isinstance(engineering, str) or not Path(engineering).is_absolute():
        raise ProfileSetupError("engineering resume path must be absolute")
    for variant in ("engineering", "technical_business", "japanese"):
        source = resumes.get(variant) or engineering
        path = Path(source)
        if not path.is_absolute() or not path.is_file():
            raise ProfileSetupError(f"{variant} resume file is unavailable")
        resumes[variant] = str(path)
    for field in ("target_role_families", "location_preferences"):
        items = candidate.get(field)
        if (
            not isinstance(items, list)
            or not items
            or any(not isinstance(item, str) or not item.strip() for item in items)
        ):
            raise ProfileSetupError(f"profile.candidate.{field} must be a non-empty string array")
        candidate[field] = [item.strip() for item in items]
    exclusions = candidate.get("employer_exclusions", [])
    if not isinstance(exclusions, list) or any(
        not isinstance(item, str) or not item.strip() for item in exclusions
    ):
        raise ProfileSetupError(
            "profile.candidate.employer_exclusions must be a string array"
        )
    candidate["employer_exclusions"] = [item.strip() for item in exclusions]
    floor = candidate.get("compensation_floor_jpy")
    target = candidate.get("compensation_target_jpy")
    if not isinstance(floor, int) or isinstance(floor, bool) or floor <= 0:
        raise ProfileSetupError(
            "profile.candidate.compensation_floor_jpy must be a positive integer"
        )
    if (
        not isinstance(target, int)
        or isinstance(target, bool)
        or target < floor
    ):
        raise ProfileSetupError(
            "profile.candidate.compensation_target_jpy must be an integer at or above the floor"
        )
    return profile


def collect_interactive() -> dict[str, Any]:
    name = input("Full name: ").strip()
    email = input("Application email: ").strip()
    engineering_resume = input("Engineering/default resume PDF (absolute path): ").strip()
    business_resume = input(
        "Technical-business resume PDF (blank to reuse default): "
    ).strip()
    japanese_resume = input("Japanese resume PDF (blank to reuse default): ").strip()
    target_roles = [
        item.strip()
        for item in input("Target role families (comma-separated): ").split(",")
        if item.strip()
    ]
    locations = [
        item.strip()
        for item in input("Acceptable work locations (comma-separated): ").split(",")
        if item.strip()
    ]
    try:
        compensation_floor = int(
            input("Minimum acceptable annual base salary in JPY: ").strip()
        )
        compensation_target = int(
            input("Target annual base salary in JPY: ").strip()
        )
    except ValueError as error:
        raise ProfileSetupError("compensation values must be integers") from error
    exclusions = [
        item.strip()
        for item in input("Employers to exclude (comma-separated, blank for none): ").split(",")
        if item.strip()
    ]
    facts: list[dict[str, str]] = []
    while True:
        claim = input("Verified fact claim (blank when finished): ").strip()
        if not claim:
            break
        evidence = input("Evidence for this fact: ").strip()
        if not evidence:
            raise ProfileSetupError("each fact requires evidence")
        facts.append(
            {
                "id": f"fact-{len(facts) + 1:03d}",
                "claim": claim,
                "evidence": evidence,
            }
        )
    if not facts:
        raise ProfileSetupError("at least one verified fact is required")
    return prepare_profile(
        {
            "version": 1,
            "candidate": {
                "name": name,
                "application_email": email,
                "target_role_families": target_roles,
                "location_preferences": locations,
                "compensation_floor_jpy": compensation_floor,
                "compensation_target_jpy": compensation_target,
                "employer_exclusions": exclusions,
            },
            "materials": {
                "resumes": {
                    "engineering": engineering_resume,
                    "technical_business": business_resume or engineering_resume,
                    "japanese": japanese_resume or engineering_resume,
                }
            },
            "facts": facts,
        }
    )


def _load_answers(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileSetupError(f"invalid answers file: {error}") from error
    return prepare_profile(value)


def write_profile(
    value: dict[str, Any],
    *,
    output: Path,
    replace: bool,
) -> dict[str, Any]:
    if output.exists() and not replace:
        raise ProfileSetupError(
            f"private profile already exists: {output}; use --replace to replace it"
        )
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output.parent, 0o700)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "version": 1,
        "profile_path": str(output),
        "fact_count": len(value["facts"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    parsed = parser.parse_args(argv)
    try:
        value = (
            _load_answers(parsed.answers)
            if parsed.answers is not None
            else collect_interactive()
        )
        receipt = write_profile(value, output=parsed.output, replace=parsed.replace)
    except (ProfileSetupError, EOFError) as error:
        print(f"job-search profile setup: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
