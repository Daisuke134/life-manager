#!/usr/bin/env python3
"""Mandatory publisher boundary around publication_resume + platform reality readback."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import stat
import sys
from pathlib import Path

from publication_remote import probe, x_post_effect_uncertain
from publication_resume import (
    DORMANT_PAIRS,
    InvariantError,
    PublicationStore,
    SUPPORTED_PAIRS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from runtime.host.disk_admission import is_cleanup_disk_recovery_signal  # noqa: E402


def assert_disk_control_state_safe() -> None:
    """Keep control state trusted; ignore cleanup low-space, honor operator stops."""
    canonical_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    control_dir = canonical_home / ".local" / "state" / "life-manager" / "state"
    try:
        root = control_dir.lstat()
    except OSError as error:
        raise InvariantError("disk_control_state_unavailable") from error
    if (not stat.S_ISDIR(root.st_mode) or control_dir.is_symlink()
            or root.st_uid != os.getuid() or root.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
        raise InvariantError("disk_control_state_unsafe")
    flag = control_dir / "disk-writers.stop"
    try:
        entry = flag.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise InvariantError("disk_control_state_unavailable") from error
    if not stat.S_ISREG(entry.st_mode):
        raise InvariantError("disk_control_state_unsafe")
    if is_cleanup_disk_recovery_signal(flag):
        return
    raise InvariantError("disk_writers_stop")


def store_from_env(*, validate_boundary: bool = True) -> PublicationStore:
    run_dir = os.environ.get("ARTICLE_RUN_DIR", "")
    state = os.environ.get("ARTICLE_PUBLICATION_STATE", "")
    ledger = os.environ.get("ARTICLE_LEDGER", "")
    if not run_dir or not state or not ledger:
        raise InvariantError(
            "ARTICLE_RUN_DIR, ARTICLE_PUBLICATION_STATE and ARTICLE_LEDGER are mandatory "
            "for managed publication"
        )
    store = PublicationStore(Path(state), Path(ledger))
    if validate_boundary:
        store.validate_managed_boundary(Path(run_dir))
    return store


def managed_article_context() -> bool:
    return any((
        os.environ.get("ARTICLE_AUTOPUBLISH") == "1",
        bool(os.environ.get("ARTICLE_RUN_DIR")),
        bool(os.environ.get("ARTICLE_PUBLISH_PAIR")),
        bool(os.environ.get("ARTICLE_PUBLICATION_STATE")),
        bool(os.environ.get("ARTICLE_LEDGER")),
    ))


def manual_or_store() -> PublicationStore | None:
    if not managed_article_context():
        return None
    return store_from_env()


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--pair", required=True, choices=SUPPORTED_PAIRS)
    preflight.add_argument("--target-kind", required=True)
    preflight.add_argument("--target", required=True)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--pair", required=True, choices=SUPPORTED_PAIRS)
    query = sub.add_parser("query-target")
    query.add_argument("--pair", required=True, choices=SUPPORTED_PAIRS)
    register = sub.add_parser("register-intent")
    register.add_argument("--pair", required=True, choices=SUPPORTED_PAIRS)
    register.add_argument("--target-kind", required=True)
    register.add_argument("--target", required=True)
    dormant_skip = sub.add_parser("register-dormant-skip")
    dormant_skip.add_argument("--pair", required=True, choices=DORMANT_PAIRS)
    dormant_skip.add_argument("--reason", default="dormant-destination")
    correct = sub.add_parser("correct-protected-target")
    correct.add_argument(
        "--pair", required=True, choices=("x-article/ja",)
    )
    correct.add_argument("--target-kind", required=True)
    correct.add_argument("--target", required=True)
    correct.add_argument("--evidence-json", required=True)
    recover = sub.add_parser("recover-ambiguous")
    recover.add_argument(
        "--pair",
        required=True,
        choices=(
            "note/ja",
            "x-article/en",
            "x-article/ja",
            "x-post/ja",
            "devto/en",
            "substack/ja",
            "substack/en",
        ),
    )
    recover_unavailable = sub.add_parser("recover-unavailable")
    recover_unavailable.add_argument(
        "--pair",
        required=True,
        choices=("devto/en",),
    )
    stale_quality = sub.add_parser("recover-stale-quality")
    stale_quality.add_argument(
        "--pair",
        required=True,
        choices=("devto/en", "substack/ja", "substack/en"),
    )
    cleared = sub.add_parser("clear-unavailable")
    cleared.add_argument("--pair", required=True, choices=SUPPORTED_PAIRS)
    unavailable = sub.add_parser("mark-unavailable")
    unavailable.add_argument("--pair", required=True, choices=SUPPORTED_PAIRS)
    unavailable.add_argument("--reason", required=True)
    quarantine_media = sub.add_parser("quarantine-missing-media")
    quarantine_media.add_argument(
        "--pair", required=True, choices=("x-article/ja", "x-article/en")
    )
    quarantine_media.add_argument("--reason", required=True)
    quarantine_identity = sub.add_parser("quarantine-identity-conflict")
    quarantine_identity.add_argument(
        "--pair", required=True, choices=("substack/en",)
    )
    migrate_identity = sub.add_parser("migrate-substack-en-identity")
    migrate_identity.add_argument("--identity", required=True)
    sub.add_parser("terminalize-invalid-x-post")
    sub.add_parser("plan")
    manual = sub.add_parser("manual-check")
    manual.add_argument("--pair", required=True, choices=SUPPORTED_PAIRS)
    args = parser.parse_args()
    if args.command == "preflight" and managed_article_context():
        assert_disk_control_state_safe()
    if args.command in {"quarantine-identity-conflict", "migrate-substack-en-identity"}:
        # This is the one migration command whose purpose is to repair the
        # legacy equal-identity boundary; the method itself performs the
        # canonical path/layout and remote-proof checks before writing state.
        store = store_from_env(validate_boundary=False)
    else:
        store = manual_or_store()
    if store is None:
        result = {"action": "manual-unmanaged"}
    elif args.command == "manual-check":
        result = {"action": "managed", "pair": args.pair}
    elif args.command == "query-target":
        entry = store.read().get("pairs", {}).get(args.pair)
        result = {"found": bool(entry), "target": entry.get("target") if entry else None}
    elif args.command == "register-intent":
        result = store.register_intent(args.pair, args.target_kind, args.target)
    elif args.command == "register-dormant-skip":
        result = store.register_dormant_skip(args.pair, args.reason)
    elif args.command == "correct-protected-target":
        result = store.correct_protected_target(
            args.pair,
            args.target_kind,
            args.target,
            json.loads(args.evidence_json),
        )
    elif args.command == "recover-ambiguous":
        entry = store.read().get("pairs", {}).get(args.pair)
        if not entry:
            raise InvariantError(
                f"no persisted intent for {args.pair}"
            )
        result = store.recover_ambiguous_intent(
            args.pair,
            probe(args.pair, entry["target"], state=store.read()),
        )
    elif args.command == "recover-unavailable":
        entry = store.read().get("pairs", {}).get(args.pair)
        if not entry:
            raise InvariantError(
                f"no persisted intent for {args.pair}"
            )
        result = store.recover_unavailable_live(
            args.pair,
            probe(args.pair, entry["target"], state=store.read()),
        )
    elif args.command == "recover-stale-quality":
        result = store.recover_stale_quality_receipt(args.pair)
    elif args.command == "clear-unavailable":
        result = store.clear_unavailable(args.pair)
    elif args.command == "mark-unavailable":
        result = store.mark_unavailable(args.pair, args.reason)
    elif args.command == "quarantine-missing-media":
        state = store.read()
        entry = state.get("pairs", {}).get(args.pair)
        if not isinstance(entry, dict) or not entry.get("target"):
            raise InvariantError(f"no persisted target for {args.pair}")
        if entry.get("receipt") or entry.get("status") == "live":
            raise InvariantError(
                "missing-media quarantine refuses a receipt or live state"
            )
        if isinstance(entry.get("existing_publication"), dict):
            raise InvariantError(
                "missing-media quarantine refuses a protected publication"
            )
        if entry.get("target_kind") != "x-draft-url":
            raise InvariantError("missing-media quarantine requires an X draft URL")
        if x_post_effect_uncertain(state):
            raise InvariantError(
                "missing-media quarantine refuses uncertain X effect evidence"
            )
        remote = probe(args.pair, str(entry["target"]), state=state)
        if not isinstance(remote, dict):
            raise InvariantError("missing-media quarantine received malformed remote proof")
        result = store.quarantine_missing_media(
            args.pair, str(entry["target"]), args.reason, remote
        )
    elif args.command == "quarantine-identity-conflict":
        entry = store.read().get("pairs", {}).get(args.pair)
        if not isinstance(entry, dict) or not entry.get("target"):
            raise InvariantError(f"no persisted target for {args.pair}")
        remote = probe(args.pair, str(entry["target"]), state=store.read())
        result = store.quarantine_identity_conflict(
            args.pair, str(entry["target"]), remote
        )
    elif args.command == "migrate-substack-en-identity":
        result = store.migrate_quarantined_substack_en_identity(args.identity)
    elif args.command == "terminalize-invalid-x-post":
        result = store.terminalize_invalid_x_post_length()
    elif args.command == "plan":
        result = store.plan()
    elif args.command == "preflight":
        if os.environ.get("ARTICLE_REMOTE_FIXTURE"):
            raise InvariantError("production remote fixture injection is forbidden")
        entry = store.read().get("pairs", {}).get(args.pair)
        if not entry:
            raise InvariantError(f"no pre-registered stable intent for {args.pair}")
        if entry.get("target_kind") != args.target_kind or entry.get("target") != args.target:
            raise InvariantError(f"preflight target does not match registered intent for {args.pair}")
        store.assert_ready(args.pair)
        result = store.guard(
            args.pair,
            probe(args.pair, entry["target"], state=store.read()),
        )
    else:
        entry = store.read().get("pairs", {}).get(args.pair)
        if not entry:
            raise InvariantError(f"no persisted intent for {args.pair}")
        result = store.guard(
            args.pair,
            probe(args.pair, entry["target"], state=store.read()),
        )
        if result.get("action") != "skip-live":
            raise InvariantError(f"remote reality is not live after publish for {args.pair}")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InvariantError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        raise SystemExit(2)
