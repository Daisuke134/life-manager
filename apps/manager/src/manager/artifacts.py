"""Deterministic, integrity-checked artifacts with immutable atomic writes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from .population.contracts import PopulationDataError


def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_bytes(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name)
        try:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
            stream.close()
            try: os.link(temporary,path)
            except FileExistsError:
                if path.read_bytes()!=data: raise PopulationDataError(f'refusing to overwrite different artifact: {path}')
        finally: temporary.unlink(missing_ok=True)
    return hashlib.sha256(data).hexdigest()


def write_artifact(path, payload):
    def wrap(value):return canonical({'payload':value,'sha256':hashlib.sha256(canonical(value)).hexdigest()})+b'\n'
    data=b''.join(wrap(value) for value in payload) if Path(path).suffix=='.jsonl' else wrap(payload)
    return write_bytes(path,data)


def read_artifact(path):
    def unwrap(data):
        try:
            envelope=json.loads(data)
            if set(envelope)!={'payload','sha256'} or envelope['sha256']!=hashlib.sha256(canonical(envelope['payload'])).hexdigest():
                raise PopulationDataError(f'artifact hash mismatch: {path}')
            return envelope['payload']
        except (ValueError,KeyError,TypeError) as exc:
            raise PopulationDataError(f'invalid artifact: {path}') from exc
    raw=Path(path).read_text(encoding='utf-8')
    return [unwrap(line) for line in raw.splitlines()] if Path(path).suffix=='.jsonl' else unwrap(raw)
