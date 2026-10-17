#!/usr/bin/env python3
"""Create and verify immutable per-publisher copies of a frozen Writer CTA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote_plus, urlsplit

from publication_contract import ACTIVE_PAIRS, NEWLY_DORMANT_PAIRS

# Single source: the publication contract decides which destinations publish.
ACTIVE_PUBLISHER_PAIRS = ACTIVE_PAIRS
# x-article/ja stays mapped so contracts persisted while it was still listed
# (2026-10-15..17 "active-four" runs) keep verifying; it is never staged.
PAIR_ARTIFACT_IDS = {
    "note/ja": "article-ja",
    "substack/ja": "article-ja",
    "substack/en": "article-en",
    "x-article/ja": "article-ja",
}
CTA_FIELDS = ("product_id", "run_id", "artifact_id", "variant_id", "click_id")
LINEAGE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
URL_RE = re.compile(r"https?://[^\s<>\]\[()\"']+")


def safe_variant_id(value: str) -> str:
    """Return a lineage-safe variant_id; derive a stable ASCII id from any other value.

    The model derives variant_id from the title, so a Japanese title yields Unicode
    (2026-10-18 run 20261017-150256 refused every pair). The frozen draft is untouched;
    each publisher copy carries the derived id and its receipt records it.
    """
    if not value or LINEAGE_ID_RE.fullmatch(value):
        return value
    return "v-" + _sha256_bytes(value.encode("utf-8"))[:16]


class PublisherCTAError(ValueError):
    """A publisher-specific CTA cannot be proven from the frozen source."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise PublisherCTAError(f"publisher CTA directory is a symlink: {path.parent}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise PublisherCTAError(f"{label} must be a regular non-symlink file: {path}")


def _run_dir(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise PublisherCTAError("ARTICLE_RUN_DIR must be a real directory")
    resolved = path.resolve(strict=True)
    if not LINEAGE_ID_RE.fullmatch(resolved.name):
        raise PublisherCTAError("run directory name is not a safe run_id")
    return resolved


def _read_state(run_dir: Path) -> tuple[dict, dict[str, Path], dict[str, str]]:
    gates_dir = run_dir / "gates"
    if gates_dir.is_symlink() or not gates_dir.is_dir():
        raise PublisherCTAError("run gates directory must be a real directory")
    state_path = gates_dir / "publication-state.json"
    _regular_file(state_path, "publication state")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PublisherCTAError("publication state is unreadable or malformed") from error
    if not isinstance(state, dict) or state.get("run_id") != run_dir.name:
        raise PublisherCTAError("publication state does not match the run directory")
    drafts = state.get("drafts")
    if not isinstance(drafts, dict) or set(drafts) != {"ja", "en"}:
        raise PublisherCTAError("publication state must bind both frozen language drafts")
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for lang in ("ja", "en"):
        record = drafts.get(lang)
        if not isinstance(record, dict):
            raise PublisherCTAError(f"publication state has no frozen {lang} draft")
        path = Path(str(record.get("path", "")))
        _regular_file(path, f"frozen {lang} draft")
        expected = (run_dir / f"article-{lang}.md").resolve(strict=True)
        if path.resolve(strict=True) != expected:
            raise PublisherCTAError(f"frozen {lang} draft is outside the run directory")
        digest = str(record.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or _sha256_file(path) != digest:
            raise PublisherCTAError(f"frozen {lang} draft SHA does not match publication state")
        paths[lang] = expected
        hashes[lang] = digest
    return state, paths, hashes


def _same_landing(url: str, landing_url: str) -> bool:
    try:
        candidate = urlsplit(url)
        landing = urlsplit(landing_url)
    except ValueError:
        return False
    if (
        candidate.scheme not in {"http", "https"}
        or candidate.scheme != landing.scheme
        or not candidate.netloc
        or candidate.netloc.lower() != landing.netloc.lower()
    ):
        return False
    base_path = landing.path.rstrip("/")
    candidate_path = candidate.path.rstrip("/")
    return candidate_path == base_path or candidate_path.startswith(f"{base_path}/")


def _rewrite_one_cta(
    source: str,
    *,
    run_id: str,
    pair: str,
    landing_url: str,
    product_id: str,
) -> tuple[str, dict[str, str]]:
    if pair not in PAIR_ARTIFACT_IDS:
        raise PublisherCTAError(f"unsupported active publisher pair: {pair}")
    try:
        landing = urlsplit(landing_url)
    except ValueError as error:
        raise PublisherCTAError("ARTICLE_PRODUCT_LANDING_URL is malformed") from error
    if landing.scheme not in {"http", "https"} or not landing.netloc:
        raise PublisherCTAError("ARTICLE_PRODUCT_LANDING_URL must be absolute HTTP(S)")
    if not isinstance(product_id, str) or not LINEAGE_ID_RE.fullmatch(product_id):
        raise PublisherCTAError("ARTICLE_PRODUCT_ID is missing or unsafe")

    candidates: list[tuple[re.Match[str], str, list[tuple[str, str]]]] = []
    for match in URL_RE.finditer(source):
        raw_url = match.group(0)
        url = raw_url.rstrip(".,;:!?")
        if not _same_landing(url, landing_url):
            continue
        parsed = urlsplit(url)
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        if any(key in dict(pairs) for key in CTA_FIELDS):
            candidates.append((match, url, pairs))
    if len(candidates) != 1:
        raise PublisherCTAError(
            f"expected exactly one lineage CTA for {pair}; found {len(candidates)}"
        )

    match, url, pairs = candidates[0]
    fields: dict[str, str] = {}
    for field in CTA_FIELDS:
        values = [value for key, value in pairs if key == field]
        if len(values) == 1 and field == "variant_id":
            values = [safe_variant_id(values[0])]
        if len(values) != 1 or not LINEAGE_ID_RE.fullmatch(values[0]):
            raise PublisherCTAError(f"CTA {field} is missing, duplicated, or unsafe")
        fields[field] = values[0]
    expected_artifact = PAIR_ARTIFACT_IDS[pair]
    if fields["product_id"] != product_id:
        raise PublisherCTAError("CTA product_id does not match the selected product")
    if fields["run_id"] != run_id:
        raise PublisherCTAError("CTA run_id does not match the current run")
    if fields["artifact_id"] != expected_artifact:
        raise PublisherCTAError(f"CTA artifact_id does not match {pair}")

    pair_slug = pair.replace("/", "-")
    publisher_click_id = f"{fields['click_id']}-{pair_slug}"
    if not LINEAGE_ID_RE.fullmatch(publisher_click_id):
        raise PublisherCTAError("publisher click_id is unsafe or exceeds 128 characters")

    query_start = url.find("?")
    if query_start < 0:
        raise PublisherCTAError("lineage CTA has no query string")
    fragment_start = url.find("#", query_start)
    query_end = fragment_start if fragment_start >= 0 else len(url)
    raw_query = url[query_start + 1 : query_end]
    raw_parts = raw_query.split("&")
    replaced = 0
    new_parts = []
    for raw_part in raw_parts:
        raw_key, separator, raw_value = raw_part.partition("=")
        if unquote_plus(raw_key) == "click_id":
            replaced += 1
            raw_value = quote(publisher_click_id, safe="-_.~")
            new_parts.append(f"{raw_key}{separator or '='}{raw_value}")
        elif (
            unquote_plus(raw_key) == "variant_id"
            and unquote_plus(raw_value) != fields["variant_id"]
        ):
            new_parts.append(f"{raw_key}={quote(fields['variant_id'], safe='-_.~:')}")
        else:
            new_parts.append(raw_part)
    if replaced != 1:
        raise PublisherCTAError("CTA click_id query parameter is missing or duplicated")
    rewritten_url = (
        url[: query_start + 1]
        + "&".join(new_parts)
        + (url[query_end:] if fragment_start >= 0 else "")
    )
    trailing = match.group(0)[len(url) :]
    rewritten = source[: match.start()] + rewritten_url + trailing + source[match.end() :]
    return rewritten, {**fields, "click_id": publisher_click_id}


def _paths(run_dir: Path, pair: str) -> tuple[Path, Path, Path]:
    slug = pair.replace("/", "-")
    directory = run_dir / "gates" / "publisher-cta"
    return directory / f"{slug}.md", directory / f"{slug}.json", directory / "contract.json"


def _load_json(path: Path, label: str) -> dict:
    _regular_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PublisherCTAError(f"{label} is malformed") from error
    if not isinstance(value, dict):
        raise PublisherCTAError(f"{label} must be an object")
    return value


def _contract_pairs(contract: dict) -> tuple[str, ...]:
    """Accept the current active pairs, optionally plus newly dormant legacy extras."""
    pairs = contract.get("active_pairs")
    if (
        not isinstance(pairs, list)
        or len(pairs) != len(set(pairs))
        or not set(ACTIVE_PUBLISHER_PAIRS) <= set(pairs)
        or not set(pairs) - set(ACTIVE_PUBLISHER_PAIRS) <= set(NEWLY_DORMANT_PAIRS)
    ):
        raise PublisherCTAError("publisher CTA contract does not match frozen publication state")
    return tuple(pairs)


def prepare_all(
    run_dir: Path, *, landing_url: str, product_id: str
) -> dict[str, dict[str, str]]:
    run_dir = _run_dir(run_dir)
    state, source_paths, source_hashes = _read_state(run_dir)
    _, _, contract_path = _paths(run_dir, ACTIVE_PUBLISHER_PAIRS[0])
    pairs = ACTIVE_PUBLISHER_PAIRS
    if contract_path.exists():
        pairs = _contract_pairs(_load_json(contract_path, "publisher CTA contract"))
    prepared: dict[str, dict[str, str]] = {}
    copies: dict[str, bytes] = {}
    for pair in pairs:
        lang = pair.rsplit("/", 1)[1]
        source_path = source_paths[lang]
        source_text = source_path.read_text(encoding="utf-8")
        copy_text, lineage = _rewrite_one_cta(
            source_text,
            run_id=run_dir.name,
            pair=pair,
            landing_url=landing_url,
            product_id=product_id,
        )
        copy_path, receipt_path, _ = _paths(run_dir, pair)
        copy_bytes = copy_text.encode("utf-8")
        receipt = {
            "version": 1,
            "pair": pair,
            **lineage,
            "landing_url": landing_url,
            "source_path": str(source_path),
            "source_sha256": source_hashes[lang],
            "receipt_path": str(receipt_path),
            "copy_path": str(copy_path),
            "copy_sha256": _sha256_bytes(copy_bytes),
        }
        prepared[pair] = receipt
        copies[pair] = copy_bytes

    if len({row["click_id"] for row in prepared.values()}) != len(pairs):
        raise PublisherCTAError("publisher click_id values are not unique")

    contract = {
        "version": 1,
        "run_id": run_dir.name,
        "active_pairs": list(pairs),
        "landing_url": landing_url,
        "product_id": product_id,
        "source_sha256_by_lang": source_hashes,
        "copy_sha256_by_pair": {
            pair: receipt["copy_sha256"] for pair, receipt in prepared.items()
        },
    }
    directory = run_dir / "gates" / "publisher-cta"
    if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
        raise PublisherCTAError("publisher CTA directory is not a real directory")
    directory.mkdir(parents=True, exist_ok=True)
    if contract_path.exists() and _load_json(contract_path, "publisher CTA contract") != contract:
        raise PublisherCTAError("publisher CTA contract conflicts with current frozen sources")
    for pair, receipt in prepared.items():
        copy_path, receipt_path, _ = _paths(run_dir, pair)
        expected_bytes = copies[pair]
        if copy_path.exists():
            _regular_file(copy_path, "publisher CTA copy")
            if copy_path.read_bytes() != expected_bytes:
                raise PublisherCTAError(f"publisher CTA copy conflicts for {pair}")
        else:
            _write_atomic(copy_path, expected_bytes)
        if receipt_path.exists():
            existing = _load_json(receipt_path, "publisher CTA receipt")
            if existing != receipt:
                raise PublisherCTAError(f"publisher CTA receipt conflicts for {pair}")
        else:
            _write_atomic(receipt_path, _json_bytes(receipt))

    if not contract_path.exists():
        _write_atomic(contract_path, _json_bytes(contract))
    return prepared


def publisher_copy_path(run_dir: Path, pair: str, source: Path) -> Path:
    if pair not in PAIR_ARTIFACT_IDS:
        raise PublisherCTAError(f"unsupported active publisher pair: {pair}")
    run_dir = _run_dir(run_dir)
    source = Path(source)
    _regular_file(source, "frozen publisher source")
    expected_source = (run_dir / f"article-{pair.rsplit('/', 1)[1]}.md").resolve(strict=True)
    if source.resolve(strict=True) != expected_source:
        raise PublisherCTAError(f"publisher source is outside the frozen run for {pair}")

    copy_path, receipt_path, contract_path = _paths(run_dir, pair)
    if not contract_path.exists():
        directory = contract_path.parent
        if directory.exists():
            if directory.is_symlink() or not directory.is_dir():
                raise PublisherCTAError("publisher CTA directory is not a real directory")
            raise PublisherCTAError("publisher CTA v1 directory exists without its contract marker")
        return source
    contract = _load_json(contract_path, "publisher CTA contract")
    state, source_paths, source_hashes = _read_state(run_dir)
    if (
        contract.get("version") != 1
        or contract.get("run_id") != run_dir.name
        or pair not in _contract_pairs(contract)
        or not isinstance(contract.get("landing_url"), str)
        or not isinstance(contract.get("product_id"), str)
        or contract.get("source_sha256_by_lang") != source_hashes
    ):
        raise PublisherCTAError("publisher CTA contract does not match frozen publication state")
    receipt = _load_json(receipt_path, "publisher CTA receipt")
    lang = pair.rsplit("/", 1)[1]
    source_text = expected_source.read_text(encoding="utf-8")
    copy_text, lineage = _rewrite_one_cta(
        source_text,
        run_id=run_dir.name,
        pair=pair,
        landing_url=contract["landing_url"],
        product_id=contract["product_id"],
    )
    expected_copy = copy_text.encode("utf-8")
    expected_receipt = {
        "version": 1,
        "pair": pair,
        **lineage,
        "landing_url": contract["landing_url"],
        "source_path": str(expected_source),
        "source_sha256": source_hashes[lang],
        "receipt_path": str(receipt_path),
        "copy_path": str(copy_path),
        "copy_sha256": _sha256_bytes(expected_copy),
    }
    if (
        receipt != expected_receipt
        or contract.get("copy_sha256_by_pair", {}).get(pair)
        != expected_receipt["copy_sha256"]
    ):
        raise PublisherCTAError(f"publisher CTA receipt is not bound to {pair}")
    _regular_file(copy_path, "publisher CTA copy")
    if copy_path.read_bytes() != expected_copy:
        raise PublisherCTAError(f"publisher CTA copy changed after receipt for {pair}")
    return copy_path


def verify_copy(run_dir: Path, pair: str, source: Path, copy_path: Path) -> Path:
    expected = publisher_copy_path(run_dir, pair, source)
    if expected == Path(source) or Path(copy_path).resolve(strict=True) != expected.resolve(strict=True):
        raise PublisherCTAError(f"publisher CTA copy does not match the v1 receipt for {pair}")
    return expected


def verify_legacy_source(run_dir: Path, pair: str, source: Path) -> Path:
    """Return the frozen source only for historical runs with no v1 artifacts."""
    expected = publisher_copy_path(run_dir, pair, source)
    if expected.resolve(strict=True) != Path(source).resolve(strict=True):
        raise PublisherCTAError(f"publisher CTA v1 contract requires its copy for {pair}")
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--run-dir", required=True)
    prepare_parser.add_argument("--landing-url", required=True)
    prepare_parser.add_argument("--product-id", required=True)
    verify_parser = subparsers.add_parser("verify-copy")
    verify_parser.add_argument("--run-dir", required=True)
    verify_parser.add_argument("--pair", required=True)
    verify_parser.add_argument("--source", required=True)
    verify_parser.add_argument("--copy", required=True)
    legacy_parser = subparsers.add_parser("verify-legacy")
    legacy_parser.add_argument("--run-dir", required=True)
    legacy_parser.add_argument("--pair", required=True)
    legacy_parser.add_argument("--source", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            receipts = prepare_all(
                Path(args.run_dir), landing_url=args.landing_url, product_id=args.product_id
            )
            print(json.dumps(receipts, ensure_ascii=False, sort_keys=True))
        elif args.command == "verify-copy":
            path = verify_copy(
                Path(args.run_dir), args.pair, Path(args.source), Path(args.copy)
            )
            print(str(path))
        else:
            path = verify_legacy_source(
                Path(args.run_dir), args.pair, Path(args.source)
            )
            print(str(path))
    except PublisherCTAError as error:
        print(f"publisher CTA refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
