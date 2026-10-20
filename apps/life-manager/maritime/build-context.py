#!/usr/bin/env python3
"""Make a secret-free ZIP from a main-derived immutable commit for Maritime."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import zipfile

MAX_COMPRESSED_BYTES = 500_000_000
MAX_UNPACKED_BYTES = 2_000_000_000
DOCKERFILE = 'apps/life-manager/maritime/Dockerfile'
EXCLUDED_PARTS = {'.git', '.worktrees', 'worktrees', '.cloak', '.codex', '.claude', '.superpowers',
                  'node_modules', '.venv', 'venv', 'state', 'memory', 'profiles', 'credentials', '__pycache__'}

def excluded(name):
    relative = PurePosixPath(name)
    parts = relative.parts
    # These are tracked publisher implementation modules, not browser/account
    # profiles. Keep only Python sources and the four declarative runtime maps.
    vendor = 'skills/capafy-autopublish/vendor/capafy-publisher/packaging/'
    source_profile = (
        (name.startswith(vendor + 'publish/profiles/') and relative.suffix == '.py')
        or (name.startswith(vendor + 'runtime/profiles/') and (relative.suffix == '.py'
            or name in {vendor + 'runtime/profiles/' + filename for filename in
                        ('claude_code.json', 'codex.json', 'hermes.json', 'openclaw.json')})))
    return (any((part.lower() in EXCLUDED_PARTS and not (part.lower() == 'profiles' and source_profile))
                or part.lower().startswith(('.env', '.codex-')) for part in parts)
            or parts[-1].lower() in {'credentials.json', 'auth.json', 'secrets.json', 'id_rsa', 'id_ed25519'}
            or relative.suffix.lower() in {'.jsonl', '.sqlite', '.sqlite3', '.db', '.pem', '.key', '.p12', '.pyc'})

def build_context(repo: Path, release_sha: str, output_zip: Path) -> dict:
    repo, output_zip = Path(repo).resolve(), Path(output_zip)
    if not isinstance(release_sha, str) or not re.fullmatch(r'[0-9a-f]{40}', release_sha):
        raise ValueError('maritime_build_release_invalid')
    child_env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL') if key in os.environ}
    child_env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', GIT_ATTR_NOSYSTEM='1')
    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, env=child_env, capture_output=True, check=True).stdout
    try:
        if git('cat-file', '-t', release_sha).strip() != b'commit':
            raise ValueError('maritime_build_release_invalid')
        git('merge-base', '--is-ancestor', release_sha, 'refs/remotes/origin/main')
    except subprocess.CalledProcessError:
        raise ValueError('maritime_build_release_not_main') from None
    output_zip.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(output_zip, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    destination = os.fdopen(fd, 'wb')
    process = None
    count = unpacked = skipped = 0
    docker = None
    try:
        process = subprocess.Popen(['git', 'archive', '--format=tar', release_sha], cwd=repo, env=child_env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with destination, zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            def write(name, stream, size, mode):
                nonlocal count, unpacked
                unpacked += size
                if unpacked > MAX_UNPACKED_BYTES:
                    raise ValueError('maritime_build_unpacked_limit')
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = (0o100755 if mode & 0o111 else 0o100644) << 16
                with archive.open(entry, 'w') as target:
                    shutil.copyfileobj(stream, target, length=1024 * 1024)
                count += 1
                if destination.tell() > MAX_COMPRESSED_BYTES:
                    raise ValueError('maritime_build_compressed_limit')
            with tarfile.open(fileobj=process.stdout, mode='r|') as source:
                for member in source:
                    name = member.name
                    relative = PurePosixPath(name)
                    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
                        raise ValueError('maritime_build_archive_path_invalid')
                    if member.isdir():
                        continue
                    if not member.isfile() or excluded(name):
                        skipped += 1
                        continue
                    if name == 'Dockerfile':
                        raise ValueError('maritime_build_root_dockerfile_conflict')
                    stream = source.extractfile(member)
                    if name == DOCKERFILE:
                        if member.size > 65536:
                            raise ValueError('maritime_build_dockerfile_invalid')
                        docker = stream.read()
                        stream = io.BytesIO(docker)
                    write(name, stream, member.size, member.mode)
            if docker is None:
                raise ValueError('maritime_build_dockerfile_missing')
            write('Dockerfile', io.BytesIO(docker), len(docker), 0o644)
        _, _stderr = process.communicate(timeout=30)
        if process.returncode != 0:
            raise ValueError('maritime_build_archive_failed')
        if output_zip.stat().st_size > MAX_COMPRESSED_BYTES:
            raise ValueError('maritime_build_compressed_limit')
        digest = hashlib.sha256()
        with output_zip.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        return {'sourceSha': release_sha, 'archiveSha256': digest.hexdigest(),
                'sizeBytes': output_zip.stat().st_size, 'unpackedBytes': unpacked,
                'fileCount': count, 'excludedCount': skipped, 'dockerfileSha256': hashlib.sha256(docker).hexdigest()}
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill(); process.communicate()
        output_zip.unlink(missing_ok=True)
        raise
    finally:
        destination.close()
        if process is not None:
            if process.stdout: process.stdout.close()
            if process.stderr: process.stderr.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_context(Path(__file__).resolve().parents[3], args.release, args.output)))
