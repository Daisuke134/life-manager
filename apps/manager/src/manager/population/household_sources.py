"""Bounded public-source fetches and verifiable immutable snapshots."""
from datetime import datetime,timezone
from pathlib import Path
import tempfile
from urllib.request import urlopen
from manager.artifacts import read_artifact,write_artifact,write_bytes,sha256
from .contracts import PopulationDataError
from .pums import read_pums,read_controls

URLS={
 'housing.zip':'https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/csv_hri.zip',
 'persons.zip':'https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/csv_pri.zip',
 'b11016.dat':'https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b11016.dat'}


def verify_sources(directory):
    directory=Path(directory);manifest=read_artifact(directory/'source.json')
    try:
        if manifest['schema_version']!=1 or manifest['state']!='44' or manifest['period']!='2020-2024' or manifest['table_hash_scope']!='state_extract':
            raise PopulationDataError('unexpected household source scope')
        if datetime.fromisoformat(manifest['acquired_at']).tzinfo is None:raise PopulationDataError('source timestamp requires timezone')
        if set(manifest['files'])!=set(URLS):raise PopulationDataError('missing household sources')
        for name,url in URLS.items():
            entry=manifest['files'][name];path=directory/name
            cap=8*1024*1024 if name.endswith('.dat') else 64*1024*1024
            if entry['url']!=url or type(entry['bytes']) is not int or not 0<entry['bytes']<=cap or path.stat().st_size!=entry['bytes'] or sha256(path)!=entry['sha256']:
                raise PopulationDataError(f'household source hash/scope mismatch: {name}')
        return manifest
    except (KeyError,ValueError,TypeError,OSError) as exc:
        if isinstance(exc,PopulationDataError):raise
        raise PopulationDataError(f'invalid household source manifest: {exc}') from exc


def fetch_household_sources(out,*,max_zip_bytes=64*1024*1024):
    out=Path(out)
    if out.exists() and any(out.iterdir()):raise PopulationDataError('source destination must be empty')
    if type(max_zip_bytes) is not int or not 0<max_zip_bytes<=64*1024*1024:raise PopulationDataError('invalid download limit')
    try:
        data={}
        for name,url in URLS.items():
            with urlopen(url,timeout=40) as response:
                if getattr(response,'status',200)!=200:raise PopulationDataError('source HTTP error')
                if name.endswith('.zip'):
                    raw=response.read(max_zip_bytes+1)
                    if len(raw)>max_zip_bytes:raise PopulationDataError('ZIP download limit exceeded')
                else:
                    limit=8*1024*1024;header=response.readline(limit+1);consumed=len(header)
                    while True:
                        if consumed>limit:raise PopulationDataError('control download limit exceeded')
                        line=response.readline(limit-consumed+1);consumed+=len(line)
                        if not line or consumed>limit:raise PopulationDataError('RI control row missing within limit')
                        if line.startswith(b'0400000US44|'):break
                    raw=header+line
                data[name]=raw
        with tempfile.TemporaryDirectory() as d:
            staging=Path(d)
            for name,raw in data.items():(staging/name).write_bytes(raw)
            read_pums(staging/'housing.zip',staging/'persons.zip');read_controls(staging/'b11016.dat')
        for name,raw in data.items():write_bytes(out/name,raw)
        manifest={'schema_version':1,'state':'44','period':'2020-2024','acquired_at':datetime.now(timezone.utc).isoformat(),
                  'table_hash_scope':'state_extract','files':{name:{'url':url,'bytes':len(data[name]),'sha256':sha256(out/name)} for name,url in URLS.items()}}
        write_artifact(out/'source.json',manifest)
        return manifest
    except (OSError,UnicodeError,ValueError) as exc:
        if isinstance(exc,PopulationDataError):raise
        raise PopulationDataError(f'household fetch failed: {exc}') from exc
