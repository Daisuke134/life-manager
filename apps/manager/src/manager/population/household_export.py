"""Stream synthetic household/person CSVs; audit every expanded record."""
import csv
import hashlib
from itertools import zip_longest
import os
from pathlib import Path
import tempfile
from .contracts import PopulationDataError
from .households import Household,integer

H_COLUMNS=('household_id','seed_serialno','size','hht','state')
P_COLUMNS=('person_id','household_id','source_order','age','sex','relationship')


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def validate_copies(households,copies):
    if not households or any(not isinstance(h,Household) for h in households) or len({h.serialno for h in households})!=len(households):
        raise PopulationDataError('invalid/duplicate household seeds')
    if not isinstance(copies,tuple) or len(copies)!=len(households):raise PopulationDataError('copy vector length mismatch')
    for value in copies:integer(value,0,1000000,'household copies')
    total=sum(copies);persons=sum(h.size*n for h,n in zip(households,copies))
    if not 0<total<=1000000 or persons>5000000:raise PopulationDataError('synthetic output limit exceeded or empty')
    return total,persons


def expanded(households,copies):
    number=0
    for h,n in zip(households,copies):
        for _ in range(n):
            number+=1;yield f'hh{number:09d}',h


def household_rows(households,copies):
    for hid,h in expanded(households,copies):yield (hid,h.serialno,str(h.size),str(h.hht),'44')


def person_rows(households,copies):
    for hid,h in expanded(households,copies):
        for p in h.persons:yield (f'{hid}-p{p.order:02d}',hid,str(p.order),str(p.age),str(p.sex),str(p.relationship))


def write_csv(path,columns,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='',dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name)
        try:
            writer=csv.writer(stream,lineterminator='\n');writer.writerow(columns);writer.writerows(rows)
            stream.flush();os.fsync(stream.fileno());stream.close()
            try:os.link(temporary,path)
            except FileExistsError:
                if file_hash(temporary)!=file_hash(path):raise PopulationDataError(f'refusing to overwrite different CSV: {path}')
        finally:temporary.unlink(missing_ok=True)
    return file_hash(path)


def export_population(households,copies,out):
    total,persons=validate_copies(households,copies);out=Path(out)
    hashes={'households.csv':write_csv(out/'households.csv',H_COLUMNS,household_rows(households,copies)),
            'persons.csv':write_csv(out/'persons.csv',P_COLUMNS,person_rows(households,copies))}
    return {'households':total,'persons':persons,'artifacts':hashes}


def audit_population(households,copies,out):
    total,persons=validate_copies(households,copies);out=Path(out)
    for name,columns,expected in [('households.csv',H_COLUMNS,household_rows(households,copies)),('persons.csv',P_COLUMNS,person_rows(households,copies))]:
        try:
            with (out/name).open(encoding='utf-8',newline='') as stream:
                reader=csv.reader(stream)
                if next(reader,None)!=list(columns):raise PopulationDataError(f'wrong synthetic header: {name}')
                for got,want in zip_longest(reader,expected):
                    if got is None or want is None or tuple(got)!=want:raise PopulationDataError(f'synthetic membership/ID/attribute/count mismatch: {name}')
        except (OSError,UnicodeError,csv.Error) as exc:raise PopulationDataError(f'cannot audit synthetic population: {exc}') from exc
    return {'households':total,'persons':persons,'orphan_persons':0,'duplicate_ids':0,'membership_errors':0,'attribute_errors':0}
