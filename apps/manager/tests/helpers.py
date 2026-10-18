"""Entirely fictitious ACS-shaped data for offline tests, never empirical evidence."""
import csv
import hashlib
import io
import json
from pathlib import Path

FIPS = '01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56'.split()
HEADER = ['GEO_ID'] + [f'B17001_{kind}{i:03}' for i in range(1,60) for kind in ('E','M')]

def fixture_bytes():
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=HEADER, delimiter='|', lineterminator='\n')
    writer.writeheader()
    for fips in FIPS + ['72']:
        row = {key: '1' for key in HEADER}
        row['GEO_ID'] = '0400000US' + fips
        for i,n in {1:52,2:26,3:13,17:13,31:26,32:13,46:13}.items():
            row[f'B17001_E{i:03}'] = str(n)
        writer.writerow(row)
    return stream.getvalue().encode()

def write_fixture(directory, data=None):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    data = fixture_bytes() if data is None else data
    path = directory/'source.dat'; path.write_bytes(data)
    manifest = dict(url='https://example.invalid/fictitious-b17001.dat', table='B17001',
                    period='2020-2024', universe='Population for whom poverty status is determined',
                    acquired_at='2026-10-18T00:00:00+00:00', extract_sha256=hashlib.sha256(data).hexdigest(),
                    hash_scope='state_extract', records=52)
    (directory/'source.json').write_text(json.dumps(manifest))
    return path

def source():
    from manager.population.contracts import SourceRef
    return SourceRef('https://example.invalid/fictitious-b17001.dat','B17001','2020-2024',
                     'Population for whom poverty status is determined','2026-10-18T00:00:00+00:00','a'*64)
