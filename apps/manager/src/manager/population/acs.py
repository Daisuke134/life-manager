"""Read bounded official ACS Summary File state extracts, without an API key."""
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.request import urlopen

from .contracts import PopulationDataError, SourceRef

URL = 'https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b17001.dat'
FIPS = tuple('01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56'.split())
STATE_IDS = frozenset('0400000US'+x for x in (*FIPS, '72'))
HEADER = ('GEO_ID',) + tuple(f'B17001_{kind}{i:03}' for i in range(1,60) for kind in ('E','M'))


def _parse(data):
    try:
        reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig')), delimiter='|')
        fields=reader.fieldnames
        if fields is None or len(fields) != len(set(fields)) or set(fields) != set(HEADER):
            raise PopulationDataError('wrong table or missing/duplicate ACS columns')
        rows=tuple(reader)
        seen=set()
        for row in rows:
            geo=row.get('GEO_ID')
            if geo not in STATE_IDS or geo in seen or None in row or any(v is None for v in row.values()):
                raise PopulationDataError('duplicate, malformed or unexpected state row')
            seen.add(geo)
            for i in range(1,60):
                value=row[f'B17001_E{i:03}']
                if not re.fullmatch(r'[0-9]+',value):
                    raise PopulationDataError(f'missing or invalid estimate: {geo}/E{i:03}')
        if seen != STATE_IDS: raise PopulationDataError('incomplete state coverage (expected 50 states, DC, PR)')
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise PopulationDataError('unreadable ACS file') from exc


def read_acs_extract(path: Path):
    path=Path(path)
    try:
        data=path.read_bytes()
        manifest=json.loads(path.with_suffix('.json').read_text())
        source=SourceRef(**{key:manifest[key] for key in SourceRef.__dataclass_fields__})
        if manifest.get('hash_scope') != 'state_extract' or manifest.get('records') != 52:
            raise PopulationDataError('invalid extract manifest scope')
        if hashlib.sha256(data).hexdigest() != source.extract_sha256:
            raise PopulationDataError('extract hash mismatch')
        return source,_parse(data)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc,PopulationDataError): raise
        raise PopulationDataError(f'cannot read source extract: {exc}') from exc


def fetch_acs_extract(destination: Path, *, timeout_seconds=30, max_bytes=8388608):
    destination=Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise PopulationDataError('destination must be empty; keep previous snapshots')
    if type(max_bytes) is not int or max_bytes <= 0: raise PopulationDataError('invalid byte limit')
    try:
        with urlopen(URL, timeout=timeout_seconds) as response:
            if getattr(response,'status',200) != 200: raise PopulationDataError('source HTTP error')
            header=response.readline(max_bytes+1)
            consumed=len(header)
            fields=header.decode('utf-8-sig').rstrip('\r\n').split('|')
            if len(fields) != len(set(fields)) or set(fields) != set(HEADER):
                raise PopulationDataError('wrong official table header')
            selected=[header]; seen=set()
            while seen != STATE_IDS:
                line=response.readline(max_bytes-consumed+1)
                consumed+=len(line)
                if consumed > max_bytes: raise PopulationDataError('source byte limit reached before state coverage')
                if not line: raise PopulationDataError('source ended before complete state coverage')
                geo=line.split(b'|',1)[0].decode('utf-8')
                if re.fullmatch(r'0400000US[0-9]{2}',geo):
                    if geo in seen or geo not in STATE_IDS: raise PopulationDataError('duplicate/unexpected state')
                    selected.append(line); seen.add(geo)
        data=b''.join(selected)
        _parse(data)
        source=SourceRef(URL,'B17001','2020-2024','Population for whom poverty status is determined',
                         datetime.now(timezone.utc).isoformat(),hashlib.sha256(data).hexdigest())
        destination.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination) as staging:
            staging=Path(staging)
            (staging/'source.dat').write_bytes(data)
            (staging/'source.json').write_text(json.dumps(dict(asdict(source),hash_scope='state_extract',records=52),indent=2)+'\n')
            # No-replace publication: another fetch may have won after the initial check.
            os.link(staging/'source.dat', destination/'source.dat')
            os.link(staging/'source.json', destination/'source.json')
        return source
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc,PopulationDataError): raise
        raise PopulationDataError(f'official ACS fetch failed: {exc}') from exc
