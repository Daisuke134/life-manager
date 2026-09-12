"""Deterministic evidence gates for a paid-work revision run."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any, Callable

_ASK_BUYER: Any = None

# The one semantic question, asked of a session that did not write the artifact.
# Vocabulary and rationale live in artifact_judge.py; only the two error ids are ours.
JUDGE_DELIVERABLE = "deliverable"
JUDGE_ABOUT_THE_DEAL = "about_the_deal"
ARTIFACT_ABOUT_THE_DEAL = "artifact_is_about_the_deal_not_the_deliverable"
ARTIFACT_JUDGEMENT_UNDETERMINABLE = "artifact_judgement_undeterminable"


class _StructureOnly:
    """Marker for a caller that is deliberately not asking the question yet.

    ★ This is not a waiver and it is not "the judge is optional". ★ It says: this
    particular call is an early screen, and the same package will be put to a real judge
    later in the same function before anything can reach a buyer.

    It exists for one call site -- ``paid_work_transaction.validate_and_promote``'s first
    validation, which runs before the project's own acceptance contract. The judge costs a
    model call; the structural checks and the contract are free and deterministic. Paying
    to learn that a package with a broken hash is also about the deal buys nothing.

    Anywhere else, ``None`` is the correct value and it refuses. If you find yourself
    reaching for this to make a test or a lane go green, that is the 2026-08-06 failure
    reappearing: a check that had nothing to look at, so it said yes.
    """

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return "STRUCTURE_ONLY"


STRUCTURE_ONLY = _StructureOnly()


def _ask_buyer_module() -> Any:
    """The question lane's blocked-state reader, loaded by path, or None.

    Read from the same file rather than reparsed here, so the gate below and the question
    that follows it can never disagree about what BLOCKED means. None is NOT "no block" --
    every caller must treat it as undeterminable, because a gate that cannot load its
    reader has not looked at anything.
    """
    global _ASK_BUYER
    if _ASK_BUYER is None:
        try:
            spec = importlib.util.spec_from_file_location(
                "ask_buyer", Path(__file__).with_name("ask_buyer.py")
            )
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except (OSError, ImportError, SyntaxError, ValueError):
            return None
        _ASK_BUYER = module
    return _ASK_BUYER


def _feedback_sha256(value: Any) -> str:
    """The buyer-feedback digest recorded in a requirements file, or empty."""
    try:
        payload = json.loads(Path(str(value)).expanduser().read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("feedback_sha256") or "").strip()


BLOCK_ABSENT = "absent"
BLOCK_STALE = "stale"
BLOCK_FRESH = "fresh"
BLOCK_UNDETERMINABLE = "undeterminable"


def blocked_evidence_verdict(
    project_root: str | Path,
    requirements_path: str | Path | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Four answers, because "I could not look" is not "there is nothing there".

    A two-valued version of this check fails open in exactly the way that shipped the
    meta-document on 2026-08-06: the bar could not see, so it said yes. An unreadable
    record, an unloadable reader, and a requirements file whose digest cannot be read all
    mean the same thing -- this gate did not run -- and callers must be able to tell that
    apart from a healthy project that was never blocked.

    A malformed BLOCKED record is deliberately NOT "no block". Otherwise the cheapest way
    past the contradiction check would be to write broken JSON, which is an incentive we
    must not create.

    - ``absent``: no record, or a record that determinately says something other than
      BLOCKED. The normal healthy case, and the only one that may proceed silently.
    - ``stale``: BLOCKED, but about feedback the buyer has since answered. Spent; the order
      must be able to move.
    - ``fresh``: BLOCKED about the feedback that is open right now.
    - ``undeterminable``: the check could not run. Never silent -- see each call site for
      which direction is the safe one there.
    """
    ask_buyer = _ask_buyer_module()
    if ask_buyer is None:
        return BLOCK_UNDETERMINABLE, None
    root = Path(str(project_root or "")).expanduser()
    try:
        path = root / ask_buyer.BLOCKED_EVIDENCE
        if not path.is_file():
            return BLOCK_ABSENT, None
        raw = path.read_text(encoding="utf-8")
    except (OSError, TypeError, ValueError):
        return BLOCK_UNDETERMINABLE, None
    try:
        payload = json.loads(raw)
    except ValueError:
        return BLOCK_UNDETERMINABLE, None
    if not isinstance(payload, dict):
        return BLOCK_UNDETERMINABLE, None
    state = ask_buyer.blocked_state(root)
    if state is None:
        # It parsed, and it says something other than BLOCKED. A determinate no.
        return BLOCK_ABSENT, None
    # Freshness is the whole point: the record survives rollback, so without it the first
    # unanswerable pass would either freeze the order forever or excuse every later one.
    digest = ask_buyer.blocker_key(state)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return BLOCK_UNDETERMINABLE, state
    source = requirements_path if requirements_path else state.get("requirements_path")
    if not source:
        return BLOCK_UNDETERMINABLE, state
    current = _feedback_sha256(source)
    if not current:
        return BLOCK_UNDETERMINABLE, state
    return (BLOCK_FRESH if current == digest else BLOCK_STALE), state


def fresh_blocked_state(
    project_root: str | Path,
    requirements_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """The BLOCKED diagnosis only when it is definitely about the current feedback.

    Convenience over ``blocked_evidence_verdict()``. Callers that must distinguish "no
    block" from "could not tell" have to use the verdict directly -- this collapses both
    to None.
    """
    verdict, state = blocked_evidence_verdict(project_root, requirements_path)
    return state if verdict == BLOCK_FRESH else None


def resolve_fresh_blocked_after_review(
    project_root: str | Path,
    requirements_path: str | Path,
    feedback_sha256: str,
    artifact_sha256: str,
) -> Path | None:
    """Archive a current BLOCKED record after an exact-artifact fresh review.

    This function does not decide whether an artifact is deliverable.  Its only caller
    invokes it after a fresh read-only reviewer has approved the artifact and after the
    caller has rechecked the artifact/requirements snapshots.  The hashes make that
    resolution durable and auditable without weakening the normal delivery gate.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", feedback_sha256):
        raise ValueError("invalid feedback sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256):
        raise ValueError("invalid artifact sha256")
    root = Path(project_root).expanduser().resolve()
    verdict, state = blocked_evidence_verdict(root, requirements_path)
    if verdict != BLOCK_FRESH:
        return None
    if not isinstance(state, dict) or state.get("feedback_sha256") != feedback_sha256:
        raise ValueError("fresh blocked evidence feedback mismatch")
    source = root / "evidence" / "acceptance-blocked.json"
    if source.is_symlink() or not source.is_file():
        raise ValueError("fresh blocked evidence is not an owned regular file")
    archive_dir = root / "evidence" / "resolved-blocked"
    if archive_dir.is_symlink():
        raise ValueError("resolved blocked archive is a symlink")
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.resolve().relative_to(root)
    target = archive_dir / f"{feedback_sha256}-{artifact_sha256}.json"
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or target.read_bytes() != source.read_bytes():
            raise FileExistsError(f"resolved blocked evidence collision: {target}")
        source.unlink()
        return target
    source.rename(target)
    return target


def _owned_file(value: Any, root: Path) -> tuple[Path | None, str | None]:
    path = Path(str(value or "")).expanduser()
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None, "path_outside_project_root"
    if not resolved.is_file() or resolved.stat().st_size == 0:
        return None, "file_missing_or_empty"
    return resolved, None


def _require_fresh(path: Path | None, label: str, min_mtime: float, errors: list[str]) -> None:
    """Reject evidence records that predate the pass that requested them."""
    if path is None or min_mtime <= 0:
        return
    try:
        if path.stat().st_mtime < min_mtime:
            errors.append(f"{label}_stale")
    except OSError:
        errors.append(f"{label}_missing_or_empty")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_contract_errors(root: Path, payload: dict[str, Any], artifact: Path | None) -> list[str]:
    root = root.resolve()
    artifact = artifact.resolve() if artifact is not None else None
    errors: list[str] = []
    required = payload.get("required_assets")
    produced = payload.get("artifact_assets")
    if not isinstance(required, list) or not isinstance(produced, list):
        return ["asset_contract_missing"]
    covered: dict[str, int] = {}
    has_visual_assets = False
    for asset in produced:
        if not isinstance(asset, dict):
            errors.append("artifact_asset_invalid")
            continue
        asset_id = str(asset.get("asset_id") or "").strip()
        path, reason = _owned_file(asset.get("path"), root)
        size = asset.get("bytes")
        digest = str(asset.get("sha256") or "")
        mime = str(asset.get("mime_type") or "").strip()
        provenance = str(asset.get("provenance") or "").strip()
        member = str(asset.get("archive_member") or "").strip()
        data: bytes | None = None
        if not asset_id or reason or not isinstance(size, int) or size <= 0 or not provenance:
            errors.append("artifact_asset_binding_invalid")
            continue
        try:
            if member:
                if artifact is None or path != artifact or artifact.suffix.casefold() != ".zip":
                    raise ValueError
                with zipfile.ZipFile(artifact) as archive:
                    data = archive.read(member)
            elif path is not None:
                data = path.read_bytes()
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            data = None
        expected_mime = mimetypes.guess_type(member or (path.name if path else ""))[0]
        mime_matches = mime == expected_mime or {mime, expected_mime} == {"audio/wav", "audio/x-wav"}
        if (data is None or len(data) != size or not data
                or hashlib.sha256(data).hexdigest() != digest
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not mime or (expected_mime and not mime_matches)):
            errors.append("artifact_asset_integrity_mismatch")
            continue
        covered[asset_id] = covered.get(asset_id, 0) + 1
        if mime.startswith("image/"):
            has_visual_assets = True
    for item in required:
        minimum = item.get("minimum_count") if isinstance(item, dict) else None
        if (not isinstance(item, dict) or not isinstance(minimum, int) or minimum < 1
                or covered.get(str(item.get("asset_id") or ""), 0) < minimum):
            errors.append("required_asset_missing")
    if has_visual_assets:
        review = root / "evidence" / "controller-artifact-review" / str(payload.get("package_sha256") or "") / "review-manifest.json"
        try:
            receipt = json.loads(review.read_text(encoding="utf-8"))
            pages = receipt.get("pages")
            if (receipt.get("artifact_sha256") != payload.get("package_sha256")
                    or not isinstance(pages, list) or not pages):
                errors.append("required_visual_review_missing")
            for row in pages or []:
                page = Path(str(row.get("path") or "")).resolve()
                page.relative_to(root)
                if (not page.is_file()
                        or _sha256(page) != str(row.get("sha256") or "")):
                    errors.append("required_visual_review_missing")
                    break
        except (OSError, AttributeError, ValueError, json.JSONDecodeError):
            errors.append("required_visual_review_missing")
    return errors


def _version_number(value: str) -> int | None:
    match = re.fullmatch(r"v(\d+)", value.strip(), re.IGNORECASE)
    return int(match.group(1)) if match else None


def validate_paid_work(
    project_root: str | Path,
    delivery_evidence_path: str | Path,
    manifest_path: str | Path | None = None,
    min_mtime: float = 0,
    allow_current_version: bool = False,
    require_delivery_evidence: bool = True,
    artifact_judge: Callable[..., tuple[str, str]] | None = None,
    allow_fresh_blocked_for_review: bool = False,
    allow_review_ready: bool = False,
) -> tuple[bool, list[str]]:
    """Validate a builder's versioned artifact before browser submission.

    ``artifact_judge`` answers one question about the artifact -- is it the thing the
    buyer bought, or a document about the transaction -- and is expected to be
    ``artifact_judge.default_judge`` in production. Signature:
    ``judge(project_root, artifact_path, requirements_path) -> (verdict, reason)``.

    ★ Omitting it is a refusal, not a waiver. ★ ``None`` produces
    ``artifact_judgement_undeterminable``, exactly as an unreachable or malformed judge
    does. The default deliberately does NOT mean "structural checks only, ship it": every
    incident this file records is a check that quietly had nothing to look at and
    therefore said yes -- the BLOCKED contradiction check the builder could disarm by
    staying silent, and before that the bootstrap validator that only measured file size.
    A gate that can be forgotten will be forgotten.

    ``allow_fresh_blocked_for_review`` is only a pre-review aperture: it permits a
    builder-declared ``BLOCKED_NON_DELEGABLE`` bundle, or suppresses one current-BLOCKED
    contradiction, solely so a fresh reviewer can decide it. It grants no delivery
    authorization. The production caller must still obtain a fresh exact-artifact review
    and rerun this validator with the default ``False`` before any buyer-visible effect.
    """
    root = Path(project_root).expanduser().resolve()
    manifest = Path(manifest_path or root / "delivery" / "paid-work-result.json").expanduser()
    errors: list[str] = []
    try:
        freshness_floor = max(float(min_mtime or 0), 0.0)
    except (TypeError, ValueError):
        freshness_floor = 0.0
        errors.append("min_mtime_invalid")
    try:
        manifest.resolve().relative_to(root)
    except ValueError:
        errors.append("manifest_outside_project_root")
    if manifest.is_file():
        _require_fresh(manifest, "manifest", freshness_floor, errors)
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
        errors.append("paid_work_manifest_missing_or_invalid")
    if not isinstance(payload, dict):
        payload = {}
        errors.append("paid_work_manifest_not_object")
    review_ready = allow_review_ready and payload.get("status") == "REVIEW_READY"
    blocked_review = (allow_fresh_blocked_for_review
                      and payload.get("status") == "BLOCKED_NON_DELEGABLE")
    if payload.get("status") != "ok" and not review_ready and not blocked_review:
        errors.append("paid_work_status_not_ok")
    recorded_root = Path(str(payload.get("project_root") or "")).expanduser()
    try:
        if recorded_root.resolve() != root:
            errors.append("project_root_binding_mismatch")
    except OSError:
        errors.append("project_root_binding_invalid")
    requirements, reason = _owned_file(payload.get("requirements_path"), root)
    if reason:
        errors.append(f"requirements_{reason}")
    _require_fresh(requirements, "requirements", freshness_floor, errors)
    artifact, reason = _owned_file(payload.get("artifact_path"), root)
    if reason:
        errors.append(f"artifact_{reason}")
    # Large existing artifacts may be repacked in place during this pass and
    # retain their filesystem mtime.  The manifest's SHA256 is the freshness
    # binding for that payload; the feedback, acceptance, manifest, and stable
    # delivery records above/below are the records that must be rewritten now.
    version = str(payload.get("artifact_version") or "").strip()
    if not version:
        errors.append("artifact_version_missing")
    elif artifact is not None and version not in artifact.name:
        errors.append("artifact_version_not_in_filename")
    acceptance, reason = _owned_file(payload.get("acceptance_evidence_path"), root)
    if reason:
        errors.append(f"acceptance_{reason}")
    _require_fresh(acceptance, "acceptance", freshness_floor, errors)
    expected_acceptance = ("REVIEW_READY" if review_ready else
                           "BLOCKED_NON_DELEGABLE" if blocked_review else "PASS")
    if payload.get("acceptance_status") != expected_acceptance:
        errors.append("acceptance_status_not_pass")
    # The builder's two records about the same pass must not contradict each other.
    #
    # Order 91000002 wrote BLOCKED into evidence/acceptance-blocked.json -- 「成果物の種類、
    # 内容、素材、仕様の指定なし」, the generic validator FAILing with artifact_missing -- and
    # PASS into this manifest, in the same pass. The manifest drove a real delivery of a
    # 1879-byte meta-document to a paying buyer and the BLOCKED record was read by nobody.
    #
    # No judgement is made here about which record is true. A package assembled while the
    # builder was still saying it could not build is not a delivery either way, and this
    # is the one check that could have stopped that one deterministically.
    #
    # ★ Fails CLOSED. ★ "The check could not run" is not "the check passed" -- that
    # equivalence is the incident. An unreadable BLOCKED record, an unloadable reader, or
    # a requirements file whose digest cannot be read all refuse the delivery here.
    elif not blocked_review:
        blocked_verdict, _blocked_state = blocked_evidence_verdict(root, requirements)
        if blocked_verdict == BLOCK_FRESH and not allow_fresh_blocked_for_review:
            errors.append("acceptance_pass_contradicts_blocked_evidence")
        elif blocked_verdict == BLOCK_UNDETERMINABLE:
            errors.append("blocked_evidence_undeterminable")
    acceptance_payload: dict[str, Any] = {}
    if acceptance is not None:
        try:
            loaded = json.loads(acceptance.read_text(encoding="utf-8"))
            acceptance_payload = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            errors.append("acceptance_evidence_invalid_json")
    if acceptance_payload.get("status") != expected_acceptance:
        errors.append("acceptance_evidence_status_not_pass")
    acceptance_delta = acceptance_payload.get("acceptance_delta")
    if not isinstance(acceptance_delta, list) or not any(isinstance(item, str) and item.strip() for item in acceptance_delta):
        errors.append("acceptance_evidence_delta_empty")
    delta = payload.get("acceptance_delta")
    if not isinstance(delta, list) or not any(isinstance(item, str) and item.strip() for item in delta):
        errors.append("acceptance_delta_empty")
    elif acceptance_delta != delta:
        errors.append("acceptance_delta_manifest_mismatch")
    version_number = _version_number(version)
    if version_number is None:
        errors.append("artifact_version_not_vN")
    state_path = root / "state.json"
    current_version = ""
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                current_version = str(
                    state.get("current_version")
                    or state.get("latest_artifact_version")
                    or state.get("artifact_version")
                    or ""
                )
        except (OSError, json.JSONDecodeError):
            errors.append("project_state_invalid_json")
    current_number = _version_number(current_version) if current_version else None
    if (
        current_number is not None
        and version_number is not None
        and version_number <= current_number
        and not (allow_current_version and version_number == current_number)
    ):
        errors.append("artifact_version_not_newer_than_project_state")
    package_hash = str(payload.get("package_sha256") or "")
    if artifact is None or not re.fullmatch(r"[0-9a-f]{64}", package_hash) or _sha256(artifact) != package_hash:
        errors.append("package_sha256_mismatch")
    errors.extend(_asset_contract_errors(root, payload, artifact))
    for candidate in (requirements, artifact, acceptance):
        if candidate is not None and "downloads" in str(candidate).casefold():
            errors.append("downloads_path_forbidden")

    if require_delivery_evidence:
        evidence = Path(delivery_evidence_path).expanduser()
        if not evidence.is_file() or evidence.stat().st_size == 0:
            errors.append("delivery_evidence_missing_or_empty")
        else:
            _require_fresh(evidence, "delivery_evidence", freshness_floor, errors)
            try:
                evidence_payload = json.loads(evidence.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                evidence_payload = {}
                errors.append("delivery_evidence_invalid")
            if not isinstance(evidence_payload, dict):
                evidence_payload = {}
                errors.append("delivery_evidence_not_object")
            for key in ("artifact_path", "artifact_version", "acceptance_evidence_path", "acceptance_status", "package_sha256", "acceptance_delta"):
                if evidence_payload.get(key) != payload.get(key):
                    errors.append(f"delivery_evidence_{key}_mismatch")
            accepted_evidence_statuses = (None, "ok", "REVIEW_READY") if review_ready else (None, "ok")
            if evidence_payload.get("status") not in accepted_evidence_statuses:
                errors.append("delivery_evidence_status_not_ok")

    # ── Is this even the thing the buyer bought? ──────────────────────────────────
    #
    # Everything above is structure: hashes bind, versions increase, paths stay inside the
    # project, two records agree. A 2173-byte 「ご依頼内容の確認資料」 satisfies all of it,
    # and on 2026-08-07 three of them did, one after another, each one PASSing its own
    # acceptance. The generic bootstrap validator these projects carry checks that the file
    # exists, exceeds 1024 bytes and has an allowed extension -- so nothing anywhere in the
    # pass looked at what the file was.
    #
    # Asked last, and only of an otherwise clean package, for two reasons. It costs a
    # model call, and an artifact already failing a structural check is not going to be
    # delivered whatever the answer -- so a broken manifest never bills. It also keeps the
    # count at the one call per order per pass that 31-gig-todo10 §2.4 budgeted, since
    # validate_and_promote runs this function three times over the same bytes.
    #
    # ★ Fails CLOSED, and the direction is worth stating because four call sites in this
    # codebase read a verdict like this and two of them fail the other way: here the
    # question is "may I ship?", so anything short of a definite yes refuses. ★ Judge
    # unreachable, judge timed out, malformed result, unknown verdict string and "no judge
    # was supplied" all land on artifact_judgement_undeterminable and all stop the
    # delivery. A gate that ships when it cannot see is the 2026-08-06 incident.
    if not errors and artifact is not None and artifact_judge is not STRUCTURE_ONLY:
        if artifact_judge is None:
            errors.append(ARTIFACT_JUDGEMENT_UNDETERMINABLE)
        else:
            try:
                verdict, _reason = artifact_judge(root, artifact, requirements)
            except Exception:  # noqa: BLE001 - a judge that crashes has not cleared anything
                verdict = ""
            if verdict == JUDGE_ABOUT_THE_DEAL:
                errors.append(ARTIFACT_ABOUT_THE_DEAL)
            elif verdict != JUDGE_DELIVERABLE:
                errors.append(ARTIFACT_JUDGEMENT_UNDETERMINABLE)
    return not errors, errors


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--delivery-evidence", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--min-mtime", type=float, default=0)
    args = parser.parse_args()
    from artifact_judge import default_judge  # noqa: PLC0415 - CLI-only dependency

    ok, errors = validate_paid_work(
        args.project_root, args.delivery_evidence, args.manifest, args.min_mtime,
        artifact_judge=default_judge,
    )
    print(json.dumps({"ok": ok, "errors": errors}, ensure_ascii=False, separators=(",", ":")))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
