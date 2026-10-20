#!/usr/bin/env python3
"""Read-only proof for one tenant artifact; never returns file contents."""
import argparse
import hashlib
import json
import os
import re
import stat

MAX_BYTES = 20 * 1024 * 1024


def prove_artifact(tenant_id, artifact_ref, *, data_root='/data', expected_tenant=None):
    expected_tenant = expected_tenant if expected_tenant is not None else os.environ.get('LM_RUNTIME_TENANT_ID')
    if (tenant_id != expected_tenant or not isinstance(tenant_id, str)
            or not re.fullmatch(r'lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', tenant_id)
            or not isinstance(artifact_ref, str) or not artifact_ref.startswith('artifact://') or '\0' in artifact_ref):
        raise ValueError('artifact_invalid')
    parts = artifact_ref[len('artifact://'):].split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise ValueError('artifact_invalid')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(data_root, flags)
    try:
        for part in [tenant_id, 'build', *parts[:-1]]:
            child = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        file = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(file)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
                raise ValueError('artifact_unavailable')
            digest = hashlib.sha256()
            total = 0
            while True:
                chunk = os.read(file, 1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ValueError('artifact_unavailable')
                digest.update(chunk)
            if total != info.st_size:
                raise ValueError('artifact_changed')
            return {'tenantId': tenant_id, 'artifactRef': artifact_ref, 'size': total, 'sha256': digest.hexdigest()}
        finally:
            os.close(file)
    finally:
        os.close(directory)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tenant', required=True)
    parser.add_argument('--artifact', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prove_artifact(args.tenant, args.artifact)))
    except (ValueError, OSError):
        print(json.dumps({'errorClass': 'artifact_unavailable'}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
