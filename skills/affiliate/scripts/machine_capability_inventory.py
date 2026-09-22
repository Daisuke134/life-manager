#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SECRET = re.compile(
    r"(?:credential|secret|password|token|cookie|session|api[_-]?key|"
    r"access[_-]?key|refresh[_-]?token|private[_-]?key)", re.I
)
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
VERSION = re.compile(r"^[0-9][A-Za-z0-9.+-]{0,63}$")
CODEX_VERSION = re.compile(r"^codex-cli ([0-9][A-Za-z0-9.+-]{0,63})$")
class InventoryError(Exception):
    pass
def reject_secret(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or CONTROL.search(key) or SECRET.search(key):
                raise InventoryError
            reject_secret(item)
    elif isinstance(value, list):
        for item in value:
            reject_secret(item)
    elif isinstance(value, str) and (CONTROL.search(value) or SECRET.search(value)):
        raise InventoryError
def text(value):
    if not isinstance(value, str) or not value or CONTROL.search(value):
        raise InventoryError
    return value
def version_text(value):
    value = text(value)
    if not VERSION.fullmatch(value):
        raise InventoryError
    return value
def real(value):
    text(value)
    try:
        return Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise InventoryError
def signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode)
def stream_sha256(fd):
    digest = hashlib.sha256()
    try:
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    except OSError:
        raise InventoryError
    return digest.hexdigest()
def open_at(name, flags, parent=None):
    try:
        if parent is None:
            return os.open(str(name), flags)
        return os.open(str(name), flags, dir_fd=parent)
    except OSError:
        raise InventoryError
def fd_hash(fd, executable=False):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or (executable and not before.st_mode & 0o111):
        raise InventoryError
    digest = stream_sha256(fd)
    after = os.fstat(fd)
    if signature(before) != signature(after):
        raise InventoryError
    return digest, after.st_size, after
def bundle_version(info_fd):
    before = os.fstat(info_fd)
    if not stat.S_ISREG(before.st_mode):
        raise InventoryError
    try:
        with os.fdopen(os.dup(info_fd), "rb") as stream:
            info = plistlib.load(stream)
    except (OSError, ValueError):
        raise InventoryError
    after = os.fstat(info_fd)
    if signature(before) != signature(after):
        raise InventoryError
    if not isinstance(info, dict):
        raise InventoryError
    version = info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
    reject_secret(version)
    return version_text(version), after
def bundle_entry(parent, name, held_fd):
    try:
        entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except OSError:
        raise InventoryError
    if stat.S_ISLNK(entry.st_mode) or signature(entry) != signature(os.fstat(held_fd)):
        raise InventoryError
def inspect_app(entry):
    app = real(entry["path"])
    if app.suffix != ".app" or not app.is_dir():
        raise InventoryError
    executable = text(entry["executable"])
    if executable in (".", "..") or "/" in executable or not NAME.fullmatch(executable):
        raise InventoryError
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    root_fd = contents_fd = macos_fd = info_fd = binary_fd = -1
    try:
        root_fd = open_at(app, os.O_RDONLY | directory | nofollow)
        root_before = os.fstat(root_fd)
        if not stat.S_ISDIR(root_before.st_mode):
            raise InventoryError
        contents_fd = open_at("Contents", os.O_RDONLY | directory | nofollow, root_fd)
        macos_fd = open_at("MacOS", os.O_RDONLY | directory | nofollow, contents_fd)
        info_fd = open_at("Info.plist", os.O_RDONLY | nofollow, contents_fd)
        binary_fd = open_at(executable, os.O_RDONLY | nofollow, macos_fd)
        version, _ = bundle_version(info_fd)
        digest, size, _ = fd_hash(binary_fd, True)
        root_after = os.fstat(root_fd)
        root_path = os.lstat(str(app))
        if (stat.S_ISLNK(root_path.st_mode) or signature(root_before) != signature(root_after) or
                signature(root_path) != signature(root_after)):
            raise InventoryError
        bundle_entry(root_fd, "Contents", contents_fd)
        bundle_entry(contents_fd, "MacOS", macos_fd)
        bundle_entry(contents_fd, "Info.plist", info_fd)
        bundle_entry(macos_fd, executable, binary_fd)
        return record(entry["name"], "macos_app", app, version, digest, size)
    finally:
        for fd in (binary_fd, info_fd, macos_fd, contents_fd, root_fd):
            if fd >= 0:
                os.close(fd)
def inspect_codex_cli(entry):
    executable = real(entry["path"])
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    fd = open_at(executable, os.O_RDONLY | nofollow)
    try:
        digest, size, before = fd_hash(fd, True)
        isolated_home = (
            Path.home()
            / ".local"
            / "state"
            / "life-manager"
            / "affiliate"
            / "machine"
            / "codex-version-home"
        )
        isolated_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        codex_home = isolated_home / ".codex"
        codex_home.mkdir(mode=0o700, exist_ok=True)
        try:
            os.chmod(isolated_home, 0o700)
            os.chmod(codex_home, 0o700)
            completed = subprocess.run(
                [str(executable), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOME": str(isolated_home),
                    "CODEX_HOME": str(codex_home),
                    "LC_ALL": "C",
                },
            )
        except OSError:
            raise InventoryError
        match = CODEX_VERSION.fullmatch(completed.stdout.strip())
        after = os.fstat(fd)
        current = os.lstat(executable)
        if (completed.returncode != 0 or completed.stderr or not match or
                signature(before) != signature(after) or
                stat.S_ISLNK(current.st_mode) or signature(before) != signature(current)):
            raise InventoryError
        return record(entry["name"], "codex_cli", executable,
                      version_text(match.group(1)), digest, size)
    except (OSError, subprocess.SubprocessError):
        raise InventoryError
    finally:
        os.close(fd)
def record(name, kind, canonical, version, digest, size):
    return {"name": name, "kind": kind, "canonical_path": str(canonical),
            "version": version, "size_bytes": size, "sha256": digest}
def inspect(entry):
    if not isinstance(entry, dict):
        raise InventoryError
    name, kind = text(entry.get("name")), entry.get("kind")
    if not NAME.fullmatch(name):
        raise InventoryError
    if kind == "macos_app":
        return inspect_app(entry)
    if kind == "codex_cli" and name == "codex-cli":
        return inspect_codex_cli(entry)
    raise InventoryError
def parse_request(path):
    try:
        raw = path.read_bytes()
        request = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise InventoryError
    if not isinstance(request, dict) or set(request) != {"capabilities"}:
        raise InventoryError
    reject_secret(request)
    entries = request.get("capabilities")
    if not isinstance(entries, list) or not entries:
        raise InventoryError
    names = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise InventoryError
        name = text(entry.get("name"))
        if not NAME.fullmatch(name) or name in names:
            raise InventoryError
        kind = entry.get("kind")
        allowed = ({"name", "kind", "path", "executable"}
                   if kind == "macos_app" else {"name", "kind", "path"})
        if kind not in ("macos_app", "codex_cli") or set(entry) != allowed:
            raise InventoryError
        names.add(name)
    return raw, entries
def write_receipt(path, payload):
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
        temp = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if path.is_file() and not path.is_symlink() and path.read_bytes() == data:
                temp.unlink()
                return
            os.replace(str(temp), str(path))
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temp.exists():
                temp.unlink()
    except OSError:
        raise InventoryError

def refresh_receipt(request, receipt):
    if platform.system() != "Darwin":
        raise InventoryError
    raw, entries = parse_request(request)
    capabilities = [inspect(item) for item in sorted(entries, key=lambda item: item["name"])]
    payload = {"schema_version": 1, "status": "READY", "platform": "macOS",
        "architecture": platform.machine(), "capabilities": capabilities,
        "request_sha256": hashlib.sha256(raw).hexdigest()}
    write_receipt(receipt, payload)
    return payload

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    refresh_receipt(args.request, args.receipt)
    return 0
if __name__ == "__main__":
    try:
        sys.exit(main())
    except (InventoryError, OSError, TypeError, ValueError):
        print("machine capability inventory: rejected", file=sys.stderr)
        sys.exit(1)
