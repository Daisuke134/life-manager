"""Consistent SQLite snapshots and fail-closed isolated state restoration.

Checksums detect accidental damage, not malicious edits. A restored database is
always quarantined because a snapshot can predate an external side effect.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile


QUARANTINE_FILE = "RESTORE_RECONCILIATION_REQUIRED.json"
_BACKUP_FILES = {"cycle.sqlite", "manifest.json"}


class StateRecoveryError(RuntimeError):
    """Backup or restore cannot be proven safe from the available evidence."""


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _private_directory(path, label):
    original = Path(path)
    if original.is_symlink():
        raise StateRecoveryError(f"{label} must not be a symlink")
    try:
        resolved = original.resolve(strict=True)
    except OSError as exc:
        raise StateRecoveryError(f"{label} must exist") from exc
    if not resolved.is_dir():
        raise StateRecoveryError(f"{label} must be a directory")
    return resolved


def _outside_source(path: Path, source: Path, label: str):
    if _inside(path, source) or _inside(source, path):
        raise StateRecoveryError(f"{label} and source tree must be separate")


@contextmanager
def _owner_lock(root: Path):
    lock_path = root / "owner.lock"
    if lock_path.is_symlink():
        raise StateRecoveryError("owner lock must not be a symlink")
    try:
        with lock_path.open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StateRecoveryError("active owner prevents state backup") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    except OSError as exc:
        raise StateRecoveryError("owner lock cannot be acquired") from exc


def _integrity_check(path: Path):
    try:
        uri = path.resolve(strict=True).as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=15) as db:
            rows = db.execute("PRAGMA integrity_check").fetchall()
    except (OSError, sqlite3.DatabaseError) as exc:
        raise StateRecoveryError("SQLite integrity check failed") from exc
    if rows != [("ok",)]:
        raise StateRecoveryError("SQLite integrity check failed")


def _sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_backup(state_root, destination, *, source_root):
    """Create an exclusive consistent snapshot while no owned cycle is active."""
    source = _private_directory(source_root, "source tree")
    root = _private_directory(state_root, "state store")
    _outside_source(root, source, "state store")
    dest = Path(destination)
    if dest.is_symlink() or dest.exists():
        raise StateRecoveryError("backup destination must be new")
    dest_parent = dest.parent.resolve(strict=True)
    _outside_source(dest_parent, source, "backup destination")
    resolved_destination = dest.resolve(strict=False)
    if _inside(resolved_destination, root) or _inside(root, resolved_destination):
        raise StateRecoveryError("backup destination must be outside live state")
    source_db = root / "cycle.sqlite"
    if source_db.is_symlink() or not source_db.is_file():
        raise StateRecoveryError("owner state database is missing or not a regular file")

    with _owner_lock(root):
        temporary = Path(tempfile.mkdtemp(prefix=".manager-state-backup-", dir=dest_parent))
        try:
            target_db = temporary / "cycle.sqlite"
            with sqlite3.connect(source_db, timeout=15) as src, sqlite3.connect(target_db) as dst:
                src.backup(dst, pages=256, sleep=0.01)
            _integrity_check(target_db)
            manifest = {
                "schema_version": 1,
                "backup_kind": "consistent_sqlite_snapshot_only",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "database_file": "cycle.sqlite",
                "bytes": target_db.stat().st_size,
                "sha256": _sha256(target_db),
                "sqlite_integrity_check": "ok",
                "recovery_status": "EXTERNAL_EFFECTS_MAY_POSTDATE_SNAPSHOT",
            }
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            # The manifest is the completion marker; publish it only after the
            # database snapshot and integrity/hash checks have completed.
            dest.mkdir(mode=0o700)
            try:
                os.replace(target_db, dest / "cycle.sqlite")
                os.replace(temporary / "manifest.json", dest / "manifest.json")
            except BaseException:
                shutil.rmtree(dest, ignore_errors=True)
                raise
            return {"status": "VERIFIED_SNAPSHOT_ONLY", **manifest}
        except StateRecoveryError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise StateRecoveryError("state backup failed") from exc
        finally:
            shutil.rmtree(temporary, ignore_errors=True)


def verify_backup(backup_dir):
    """Verify file set, digest, size and SQLite integrity before restore."""
    backup = _private_directory(backup_dir, "backup")
    if {p.name for p in backup.iterdir()} != _BACKUP_FILES:
        raise StateRecoveryError("backup must contain only cycle.sqlite and manifest.json")
    if any(p.is_symlink() or not p.is_file() for p in backup.iterdir()):
        raise StateRecoveryError("backup files must be regular files")
    try:
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateRecoveryError("backup manifest is invalid") from exc
    database = backup / "cycle.sqlite"
    if (type(manifest) is not dict or manifest.get("schema_version") != 1
            or manifest.get("backup_kind") != "consistent_sqlite_snapshot_only"
            or manifest.get("database_file") != "cycle.sqlite"
            or manifest.get("recovery_status") != "EXTERNAL_EFFECTS_MAY_POSTDATE_SNAPSHOT"
            or manifest.get("sqlite_integrity_check") != "ok"
            or type(manifest.get("bytes")) is not int
            or type(manifest.get("sha256")) is not str
            or manifest["bytes"] != database.stat().st_size
            or manifest["sha256"] != _sha256(database)):
        raise StateRecoveryError("backup manifest does not match database snapshot")
    _integrity_check(database)
    return manifest


def restore_backup(backup_dir, destination, *, source_root):
    """Restore into a brand-new isolated directory, always requiring reconcile."""
    source = _private_directory(source_root, "source tree")
    backup = _private_directory(backup_dir, "backup")
    _outside_source(backup, source, "backup")
    manifest = verify_backup(backup)
    dest = Path(destination)
    if dest.is_symlink() or dest.exists():
        raise StateRecoveryError("restore destination must not exist; live state is never overwritten")
    dest_parent = dest.parent.resolve(strict=True)
    _outside_source(dest_parent, source, "restore destination")
    if _inside(dest.resolve(strict=False), backup):
        raise StateRecoveryError("restore destination must be outside its backup")

    staging = Path(tempfile.mkdtemp(prefix=".manager-state-restore-", dir=dest_parent))
    # Write quarantine first so interruption at any later point cannot leave a
    # restorable database that the runtime mistakes for current owner state.
    quarantine = {
        "status": "RESTORE_RECONCILIATION_REQUIRED",
        "reason": "snapshot may predate an external effect or target advance",
        "backup_sha256": manifest["sha256"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dispatch_allowed": False,
    }
    (staging / QUARANTINE_FILE).write_text(
        json.dumps(quarantine, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    temporary_db = staging / ".cycle.sqlite.restore"
    try:
        with sqlite3.connect(backup / "cycle.sqlite", timeout=15) as src, sqlite3.connect(temporary_db) as dst:
            src.backup(dst, pages=256, sleep=0.01)
        _integrity_check(temporary_db)
        if _sha256(temporary_db) != manifest["sha256"]:
            raise StateRecoveryError("restored database hash differs from verified snapshot")
        os.replace(temporary_db, staging / "cycle.sqlite")
        if dest.exists() or dest.is_symlink():
            raise StateRecoveryError("restore destination appeared during restore")
        os.rename(staging, dest)
    except BaseException:
        temporary_db.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"status": "RESTORED_QUARANTINED", "dispatch_allowed": False,
            "state_dir": str(dest), "backup_sha256": manifest["sha256"]}


def restore_requires_reconciliation(state_root):
    """Any restore marker blocks dispatch, including malformed marker files."""
    marker = Path(state_root) / QUARANTINE_FILE
    return marker.exists() or marker.is_symlink()
