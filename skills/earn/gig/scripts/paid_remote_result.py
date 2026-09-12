#!/usr/bin/env python3
"""Validate and resume authenticated remote paid work without duplicate mutation."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
SECRET = re.compile(r"(?i)(api[_ -]?key|token|password|secret|bearer)\s*[:=]")
UNORDERED_ARRAY_KEYS = frozenset(("tags", "keywords"))
EXTERNAL_WAIT_KINDS = {
    "authentication": ({"buyer", "provider"}, {
        "authentication_readback", "login_recovery_readback",
        "seller_login_recovery_readback", "authenticated_identity_readback",
        "official_authenticated_identity_readback", "deployment_access_readback",
    }),
    "buyer_reply": ({"buyer"}, {"buyer_reply_state", "inbox_thread_state"}),
    "provider_reply": ({"provider", "third_party"}, {
        "provider_reply_state", "inbox_thread_state",
    }),
    "provider_processing": ({"provider", "third_party"}, {
        "provider_job_state", "platform_review_state", "payment_settlement_state",
    }),
}


def _load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _canonical(value):
    def normalize(node):
        if isinstance(node, dict):
            normalized = {}
            for key, child in node.items():
                child = normalize(child)
                if key in UNORDERED_ARRAY_KEYS and isinstance(child, list):
                    child = sorted(child, key=lambda item: json.dumps(
                        item, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                    ))
                normalized[key] = child
            return normalized
        if isinstance(node, list):
            return [normalize(child) for child in node]
        return node

    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _legacy_sha(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _digest_matches(value, digest):
    return digest in {_sha(value), _legacy_sha(value)}


def _message_sha(message):
    if not isinstance(message, str):
        raise ValueError("customer message missing")
    return hashlib.sha256(message.encode()).hexdigest()


def _verifier_feedback_sha256(result):
    return result.get("buyer_feedback_sha256") or result.get("feedback_sha256")


def canonical_equal(left, right):
    return _canonical(left) == _canonical(right)


def requirements_digest(root, feedback):
    if not HEX64.fullmatch(str(feedback)):
        raise ValueError("invalid buyer feedback hash")
    path = Path(root).resolve() / "requirements" / "live-buyer-reply.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("invalid accumulated requirements source")
    payload = _load(path)
    digest = payload.get("accumulated_sha256") if isinstance(payload, dict) else None
    if (not isinstance(payload, dict) or payload.get("feedback_sha256") != feedback
            or not HEX64.fullmatch(str(digest or ""))):
        raise ValueError("invalid accumulated requirements digest")
    rows = payload.get("accumulated_requirements")
    if not isinstance(rows, list) or not rows:
        raise ValueError("invalid accumulated requirements rows")
    row_digests = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("attachments"), list):
            raise ValueError("invalid accumulated requirement row")
        canonical = {"text": str(row.get("text") or ""), "attachments": row["attachments"]}
        row_digest = hashlib.sha256(json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        if row.get("sha256") != row_digest:
            raise ValueError("accumulated requirement row digest mismatch")
        row_digests.append(row_digest)
    computed = hashlib.sha256(json.dumps(
        row_digests, ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()
    if computed != digest:
        raise ValueError("accumulated requirements digest mismatch")
    return digest


def builder_evidence_paths(root, result):
    root = Path(root).resolve()
    before = _inside(root, result.get("before_evidence"))
    after = _inside(root, result.get("after_evidence"))
    evidence_root = (root / "evidence").resolve()
    verifier_root = (evidence_root / "agent-PAID_REMOTE_VERIFY").resolve()
    for evidence in (before, after):
        if not evidence.is_file():
            raise ValueError("remote evidence missing")
        try:
            evidence.relative_to(evidence_root)
        except ValueError as error:
            raise ValueError("builder evidence escapes evidence root") from error
        try:
            evidence.relative_to(verifier_root)
        except ValueError:
            pass
        else:
            raise ValueError("builder evidence uses verifier-owned path")
    return before, after


def _inside(root, value):
    try:
        raw = Path(value)
        path = (Path(root) / raw if not raw.is_absolute() else raw).resolve()
        path.relative_to(root.resolve())
        return path
    except (OSError, ValueError, TypeError):
        raise ValueError("evidence path escapes project root")


def _validate_builder_contract(root, feedback, digest, pass_start, resume=False):
    root = Path(root).resolve()
    intent_path, result_path = root / "delivery/paid-remote-intent.json", root / "delivery/paid-remote-result.json"
    if not intent_path.is_file() or not result_path.is_file():
        raise ValueError("remote intent/result missing")
    intent, result = _load(intent_path), _load(result_path)
    if not resume and result_path.stat().st_mtime < float(pass_start):
        raise ValueError("remote result is stale")
    requirements_sha256 = requirements_digest(root, feedback)
    if (intent.get("buyer_feedback_sha256") != feedback or result.get("buyer_feedback_sha256") != feedback
            or intent.get("requirements_sha256") != requirements_sha256
            or result.get("requirements_sha256") != requirements_sha256):
        raise ValueError("buyer feedback hash mismatch")
    desired = intent.get("desired_state")
    if not HEX64.fullmatch(str(feedback)) or not isinstance(desired, dict):
        raise ValueError("invalid desired state")
    if intent.get("desired_state_sha256") != digest or not _digest_matches(desired, digest):
        raise ValueError("desired state digest mismatch")
    observed = result.get("observed_state")
    if (result.get("after_state_digest") != digest or not _digest_matches(observed, digest)
            or not canonical_equal(desired, observed)):
        raise ValueError("observed state digest mismatch")
    target = intent.get("target")
    if not target or result.get("target") != target:
        raise ValueError("remote target mismatch")
    if result.get("status") != "ok" or result.get("verified_after") is not True:
        raise ValueError("remote mutation is not verified")
    raw_message = result.get("customer_message")
    message = raw_message.strip() if isinstance(raw_message, str) else ""
    if not message or SECRET.search(message):
        raise ValueError("unsafe customer message")
    message_sha256 = _message_sha(raw_message)
    if (intent.get("message_sha256") != message_sha256
            or result.get("message_sha256") != message_sha256):
        raise ValueError("customer message hash mismatch")
    before, after = builder_evidence_paths(root, result)
    for evidence in (before, after):
        metadata = _load(evidence)
        if (metadata.get("target") != target or metadata.get("authenticated") is not True
                or metadata.get("requirements_sha256") != requirements_sha256
                or metadata.get("message_sha256") != message_sha256):
            raise ValueError("unauthenticated or mismatched browser evidence")
    if not canonical_equal(_load(after).get("observed_state"), result.get("observed_state")):
        raise ValueError("observed state evidence mismatch")
    if not resume and min(before.stat().st_mtime, after.stat().st_mtime) < float(pass_start):
        raise ValueError("remote evidence is stale")
    return root, intent, result, requirements_sha256, message_sha256, before, after


def validate_builder(root, feedback, digest, pass_start=0, resume=False):
    """Validate a durable builder checkpoint without claiming reviewer approval."""
    return _validate_builder_contract(root, feedback, digest, pass_start, resume)[2]


def validate_owner(root, feedback, digest, pass_start=0, resume=False):
    """Validate the paid owner's authenticated self-checkpoint deterministically."""
    return _validate_builder_contract(root, feedback, digest, pass_start, resume)[2]


def validate_wait(root, feedback, digest, pass_start=0):
    """Validate an incomplete remote effect as a durable, nonterminal wait."""
    root = Path(root).resolve()
    intent_path = root / "delivery/paid-remote-intent.json"
    result_path = root / "delivery/paid-remote-result.json"
    if not intent_path.is_file() or not result_path.is_file():
        raise ValueError("remote wait intent/result missing")
    if result_path.stat().st_mtime < float(pass_start):
        raise ValueError("remote wait result is stale")
    intent, result = _load(intent_path), _load(result_path)
    requirements_sha256 = requirements_digest(root, feedback)
    if (intent.get("buyer_feedback_sha256") != feedback
            or result.get("buyer_feedback_sha256") != feedback
            or intent.get("requirements_sha256") != requirements_sha256
            or result.get("requirements_sha256") != requirements_sha256):
        raise ValueError("remote wait feedback mismatch")
    desired, observed = intent.get("desired_state"), result.get("observed_state")
    if (not isinstance(desired, dict)
            or intent.get("desired_state_sha256") != digest
            or not _digest_matches(desired, digest)
            or result.get("after_state_digest") != digest
            or not _digest_matches(observed, digest)
            or not canonical_equal(desired, observed)):
        raise ValueError("remote wait state mismatch")
    outcome = result.get("business_outcome")
    receipts = outcome.get("official_receipts") if isinstance(outcome, dict) else None
    authentication_wait = (
        result.get("authenticated") is False
        and isinstance(receipts, list)
        and any(
            isinstance(receipt, dict)
                and receipt.get("kind") in {
                    "authentication_readback", "login_recovery_readback",
                    "seller_login_recovery_readback",
                    "authenticated_identity_readback",
                    "official_authenticated_identity_readback",
                }
            and isinstance(receipt.get("provider"), str)
            and bool(receipt["provider"].strip())
            and isinstance(receipt.get("url") or receipt.get("official_url"), str)
            and bool((receipt.get("url") or receipt.get("official_url")).strip())
            and isinstance(receipt.get("readback"), str)
            and bool(receipt["readback"].strip())
            for receipt in receipts
        )
    )
    if (not intent.get("target") or result.get("target") != intent.get("target")
            or result.get("authenticated") is not True and not authentication_wait):
        raise ValueError("remote wait target mismatch")
    effect_done = outcome.get("required_effect_satisfied") if isinstance(outcome, dict) else None
    output_done = outcome.get("required_output_satisfied") if isinstance(outcome, dict) else None
    if (result.get("status") != "blocked" or not isinstance(outcome, dict)
            or not isinstance(effect_done, bool) or not isinstance(output_done, bool)
            or (effect_done and output_done)
            or not isinstance(outcome.get("remaining_work"), list)
            or not outcome["remaining_work"]
            or not isinstance(result.get("blocker"), str)
            or not result["blocker"].strip()):
        raise ValueError("not an external wait")
    if not isinstance(receipts, list) or not receipts:
        raise ValueError("remote wait receipt missing")
    wait = outcome.get("wait_receipt")
    dependency_kind = wait.get("dependency_kind") if isinstance(wait, dict) else None
    allowed = EXTERNAL_WAIT_KINDS.get(dependency_kind)
    if (not isinstance(wait, dict)
            or wait.get("kind") != "external_dependency"
            or allowed is None
            or wait.get("responsible_party") not in allowed[0]
            or not isinstance(wait.get("required_event"), str)
            or not wait["required_event"].strip()
            or not isinstance(wait.get("receipt_refs"), list)
            or not wait["receipt_refs"]
            or any(not isinstance(ref, str) or not ref.strip()
                   for ref in wait["receipt_refs"])
            or len(set(wait["receipt_refs"])) != len(wait["receipt_refs"])):
        raise ValueError("remote wait is not a proved external dependency")
    readback_present = False
    for receipt in receipts:
        url = receipt.get("url") or receipt.get("official_url") if isinstance(receipt, dict) else None
        legacy_result = receipt.get("result") if isinstance(receipt, dict) else None
        kind = receipt.get("kind") if isinstance(receipt, dict) else None
        if (not isinstance(receipt, dict)
                or not isinstance(receipt.get("provider"), str) or not receipt["provider"].strip()
                or (not isinstance(kind, str) or not kind.strip())
                and (not isinstance(legacy_result, str) or not legacy_result.strip())
                or not isinstance(url, str) or not url.strip()):
            raise ValueError("invalid remote wait receipt")
        readback_present = readback_present or (
            isinstance(receipt.get("readback"), str) and bool(receipt["readback"].strip())
        ) or (
            isinstance(legacy_result, str) and bool(legacy_result.strip())
        ) or (
            receipt.get("exact_readback") is True
            and isinstance(receipt.get("readback_source"), str)
            and bool(receipt["readback_source"].strip())
        )
    if not readback_present:
        raise ValueError("remote wait readback missing")
    receipts_by_ref = {}
    for receipt in receipts:
        for ref in (receipt.get("effect_key"), receipt.get("url"), receipt.get("official_url")):
            if isinstance(ref, str) and ref.strip():
                receipts_by_ref[ref] = receipt
    for ref in wait["receipt_refs"]:
        receipt = receipts_by_ref.get(ref)
        if receipt is None:
            raise ValueError("external dependency receipt reference missing")
        if receipt.get("kind") not in allowed[1]:
            raise ValueError("external dependency receipt kind mismatch")
        if not ((isinstance(receipt.get("readback"), str)
                 and bool(receipt["readback"].strip()))
                or (isinstance(receipt.get("result"), str)
                    and bool(receipt["result"].strip()))
                or (receipt.get("exact_readback") is True
                    and isinstance(receipt.get("readback_source"), str)
                    and bool(receipt["readback_source"].strip()))):
            raise ValueError("external dependency receipt lacks readback")
    return result


def validate(root, feedback, digest, pass_start, resume=False, verifier=None):
    root, intent, result, requirements_sha256, message_sha256, before, after = \
        _validate_builder_contract(root, feedback, digest, pass_start, resume)
    target = intent["target"]
    if not verifier:
        raise ValueError("fresh remote verifier missing")
    verifier = Path(verifier).resolve()
    if verifier.name != "remote-verifier-result.json" or verifier.parent.name != "agent-PAID_REMOTE_VERIFY" or not verifier.is_file():
        raise ValueError("invalid managed verifier path")
    if not resume and verifier.stat().st_mtime <= after.stat().st_mtime:
        raise ValueError("remote verifier is stale")
    checked = _load(verifier)
    verifier_feedback = _verifier_feedback_sha256(checked)
    if checked.get("verified") is not True or verifier_feedback != feedback \
            or checked.get("target") != target \
            or checked.get("desired_digest", checked.get("desired_state_digest")) != digest \
            or checked.get("observed_digest") != digest \
            or not canonical_equal(checked.get("observed_state"), result.get("observed_state")) \
            or checked.get("requirements_sha256") != requirements_sha256 \
            or checked.get("message_sha256") != message_sha256:
        raise ValueError("remote verifier mismatch")
    verifier_evidence = [value for value in (checked.get("before_evidence"), checked.get("after_evidence")) if value]
    if not verifier_evidence and isinstance(checked.get("evidence"), list):
        verifier_evidence = checked["evidence"]
    if not verifier_evidence:
        raise ValueError("verifier evidence missing")
    for value in verifier_evidence:
        evidence = _inside(verifier.parent, value)
        if not evidence.is_file():
            raise ValueError("verifier evidence missing or escapes managed directory")
        metadata = _load(evidence)
        if (metadata.get("target") != target or metadata.get("authenticated") is not True
                or metadata.get("requirements_sha256") != requirements_sha256
                or metadata.get("message_sha256") != message_sha256):
            raise ValueError("verifier evidence identity mismatch")
        if not canonical_equal(metadata.get("observed_state"), result.get("observed_state")):
            raise ValueError("verifier observed state evidence mismatch")
    return result


def _receipt(root, feedback, digest, target, requirements_sha256=None):
    ledger = root / "events.jsonl"
    if not ledger.exists():
        return None
    key = hashlib.sha256(f"{feedback}:{target}:{digest}".encode()).hexdigest()
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("kind") == "live_system_delivery_recorded" and row.get("key") == key \
                and row.get("buyer_feedback_sha256") == feedback and row.get("result_digest") == digest \
                and (requirements_sha256 is None or row.get("requirements_sha256") == requirements_sha256):
            return row
    return None


def record(root, feedback, digest, pass_start=0, verifier=None):
    root = Path(root).resolve()
    requirements_sha256 = requirements_digest(root, feedback)
    result = validate(root, feedback, digest, pass_start, verifier=verifier)
    key = hashlib.sha256(f"{feedback}:{result['target']}:{digest}".encode()).hexdigest()
    if _receipt(root, feedback, digest, result["target"], requirements_sha256):
        return
    safe = {"kind": "live_system_delivery_recorded", "key": key,
            "buyer_feedback_sha256": feedback, "target": result["target"],
            "result_digest": digest, "verified_after": True,
            "requirements_sha256": requirements_sha256,
            "message_sha256": _message_sha(result["customer_message"])}
    with (root / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(safe, ensure_ascii=False, separators=(",", ":")) + "\n")


def resume(root, feedback, digest, verifier):
    root = Path(root).resolve()
    requirements_sha256 = requirements_digest(root, feedback)
    result = validate(root, feedback, digest, 0, resume=True, verifier=verifier)
    answer_path = root / "delivery/paid-answer.json"
    receipt = _receipt(root, feedback, digest, result["target"], requirements_sha256)
    if not answer_path.is_file() or not receipt:
        raise ValueError("validated remote receipt or answer missing")
    answer = _load(answer_path)
    message = answer.get("message")
    message_sha256 = _message_sha(message) if isinstance(message, str) else None
    result_sha256 = _message_sha(result["customer_message"])
    if (answer.get("requirements_sha256") != requirements_sha256
            or answer.get("message_sha256") != message_sha256
            or message_sha256 != receipt.get("message_sha256")
            or message_sha256 != result_sha256):
        raise ValueError("paid answer message hash mismatch")


def write_answer(root, feedback, digest, pass_start, verifier):
    result = validate(root, feedback, digest, pass_start, verifier=verifier)
    path = Path(root) / "delivery/paid-answer.json"
    tmp = path.with_suffix(".tmp")
    requirements_sha256 = requirements_digest(root, feedback)
    tmp.write_text(json.dumps({"version": 1, "status": "answer", "message": result["customer_message"],
                               "requirements_sha256": requirements_sha256,
                               "message_sha256": _message_sha(result["customer_message"])}, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def record_owner(root, feedback, digest, pass_start=0):
    root = Path(root).resolve()
    requirements_sha256 = requirements_digest(root, feedback)
    result = validate_owner(root, feedback, digest, pass_start)
    key = hashlib.sha256(f"{feedback}:{result['target']}:{digest}".encode()).hexdigest()
    if _receipt(root, feedback, digest, result["target"], requirements_sha256):
        return
    safe = {"kind": "live_system_delivery_recorded", "key": key,
            "buyer_feedback_sha256": feedback, "target": result["target"],
            "result_digest": digest, "verified_after": True,
            "verification_owner": "paid-owner",
            "requirements_sha256": requirements_sha256,
            "message_sha256": _message_sha(result["customer_message"])}
    with (root / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(safe, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_answer_owner(root, feedback, digest, pass_start=0):
    result = validate_owner(root, feedback, digest, pass_start)
    path = Path(root) / "delivery/paid-answer.json"
    tmp = path.with_suffix(".tmp")
    requirements_sha256 = requirements_digest(root, feedback)
    message = result["customer_message"]
    tmp.write_text(json.dumps({"version": 1, "status": "answer", "message": message,
                               "requirements_sha256": requirements_sha256,
                               "message_sha256": _message_sha(message)}, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def resume_owner(root, feedback, digest):
    root = Path(root).resolve()
    requirements_sha256 = requirements_digest(root, feedback)
    result = validate_owner(root, feedback, digest, 0, resume=True)
    answer_path = root / "delivery/paid-answer.json"
    receipt = _receipt(root, feedback, digest, result["target"], requirements_sha256)
    if not answer_path.is_file() or not receipt:
        raise ValueError("validated remote receipt or answer missing")
    answer = _load(answer_path)
    message = answer.get("message")
    message_sha256 = _message_sha(message) if isinstance(message, str) else None
    if (answer.get("requirements_sha256") != requirements_sha256
            or answer.get("message_sha256") != message_sha256
            or message_sha256 != receipt.get("message_sha256")
            or message_sha256 != _message_sha(result["customer_message"])):
        raise ValueError("paid answer message hash mismatch")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "record", "answer", "resume"))
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--feedback-sha256", required=True)
    parser.add_argument("--desired-digest", required=True)
    parser.add_argument("--pass-start", type=float, default=0)
    parser.add_argument("--verifier")
    args = parser.parse_args()
    try:
        if args.command == "validate": validate(args.project_root, args.feedback_sha256, args.desired_digest, args.pass_start, verifier=args.verifier)
        elif args.command == "record": record(args.project_root, args.feedback_sha256, args.desired_digest, args.pass_start, args.verifier)
        elif args.command == "resume": resume(args.project_root, args.feedback_sha256, args.desired_digest, args.verifier)
        else: write_answer(args.project_root, args.feedback_sha256, args.desired_digest, args.pass_start, args.verifier)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
