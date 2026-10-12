from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


BUSINESS_ROLE_FAMILIES = frozenset(
    {
        "product",
        "program",
        "solutions",
        "gtm",
        "partnerships",
        "customer_success",
        "technical_account",
        "technical_business",
        "sales_engineering",
        "business_development",
    }
)

JAPANESE_PATTERN = re.compile(r"[ぁ-んァ-ヶ一-龯々]")
ASCII_LETTER_PATTERN = re.compile(r"[A-Za-z]")
RESUME_VARIANTS = ("engineering", "technical_business", "japanese")


def load_resume_manifest(materials_root: Path) -> dict[str, Path]:
    root = Path(materials_root).expanduser().resolve()
    manifest = root / "manifest.v1.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid resume manifest: {error}") from error
    resumes = value.get("resumes") if isinstance(value, dict) else None
    if value.get("version") != 1 or not isinstance(resumes, dict):
        raise ValueError("resume manifest must be version 1 with resumes")
    resolved = {}
    for variant in RESUME_VARIANTS:
        relative = resumes.get(variant)
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError(f"resume manifest missing {variant}")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("resume manifest paths must stay under materials root")
        target = (root / path).resolve()
        if root not in target.parents or not target.is_file():
            raise ValueError(f"resume manifest file is unavailable: {variant}")
        resolved[variant] = target
    return resolved


def list_resume_paths(materials_root: Path) -> tuple[Path, ...]:
    values = load_resume_manifest(materials_root)
    return tuple(dict.fromkeys(values[variant] for variant in RESUME_VARIANTS))


def detect_posting_language(posting_text: str) -> str:
    japanese_count = len(JAPANESE_PATTERN.findall(posting_text))
    ascii_count = len(ASCII_LETTER_PATTERN.findall(posting_text))
    comparable_count = japanese_count + ascii_count
    if (
        japanese_count >= 8
        and comparable_count > 0
        and japanese_count / comparable_count >= 0.18
    ):
        return "ja"
    return "en"


def _normalized_role_family(role_family: str) -> str:
    return re.sub(r"[\s-]+", "_", role_family.strip().casefold())


def select_resume(
    *,
    posting_text: str,
    role_family: str,
    materials_root: Path,
    posting_language: str | None = None,
) -> dict[str, str]:
    language = posting_language or detect_posting_language(posting_text)
    if language not in {"ja", "en"}:
        raise ValueError("posting_language must be ja or en")

    if language == "ja":
        variant = "japanese"
    elif _normalized_role_family(role_family) in BUSINESS_ROLE_FAMILIES:
        variant = "technical_business"
    else:
        variant = "engineering"

    resume_path = load_resume_manifest(materials_root)[variant]
    digest = hashlib.sha256(resume_path.read_bytes()).hexdigest()
    return {
        "posting_language": language,
        "resume_variant": variant,
        "resume_path": str(resume_path),
        "resume_sha256": digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role-family")
    parser.add_argument("--materials-root", required=True, type=Path)
    parser.add_argument("--list-resumes", action="store_true")
    parser.add_argument("--posting-language", choices=("ja", "en"))
    parser.add_argument("--posting-text-file", type=Path)
    arguments = parser.parse_args()
    if arguments.list_resumes:
        print(json.dumps([str(path) for path in list_resume_paths(arguments.materials_root)]))
        return 0
    if not arguments.role_family:
        parser.error("--role-family is required unless --list-resumes is used")
    posting_text = (
        arguments.posting_text_file.read_text(encoding="utf-8")
        if arguments.posting_text_file
        else sys.stdin.read()
    )
    print(
        json.dumps(
            select_resume(
                posting_text=posting_text,
                role_family=arguments.role_family,
                materials_root=arguments.materials_root,
                posting_language=arguments.posting_language,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
