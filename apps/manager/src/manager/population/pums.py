"""Read documented PUMS fields and validate complete household membership."""
from collections import defaultdict
from contextlib import contextmanager
import csv
import io
from pathlib import Path
import zipfile
from .contracts import PopulationDataError
from .households import Person,Household,HouseholdControls

MAX_MEMBER_BYTES=128*1024*1024
MAX_ROWS=1000000
H_FIELDS={'RT','SERIALNO','STATE','WGTP','NP','TYPEHUGQ','HHT'}
P_FIELDS={'RT','SERIALNO','STATE','SPORDER','PWGTP','AGEP','SEX','RELSHIPP'}
CONTROL_HEADER=('GEO_ID',)+tuple(f'B11016_{kind}{i:03}' for i in range(1,17) for kind in ('E','M'))


def numeric(value,name):
    if not isinstance(value,str) or not value.isascii() or not value.isdecimal() or len(value)>12:
        raise PopulationDataError(f'invalid {name}')
    return int(value)


@contextmanager
def csv_rows(path,member,required):
    try:
        if Path(path).stat().st_size>64*1024*1024:raise PopulationDataError('PUMS ZIP too large')
        with zipfile.ZipFile(path) as archive:
            matches=[v for v in archive.infolist() if v.filename==member]
            if len(matches)!=1 or matches[0].file_size>MAX_MEMBER_BYTES:raise PopulationDataError('missing/duplicate/oversized PUMS CSV member')
            with archive.open(matches[0]) as stream,io.TextIOWrapper(stream,encoding='utf-8-sig',newline='') as text:
                reader=csv.DictReader(text)
                fields=reader.fieldnames
                if not fields or len(fields)!=len(set(fields)) or not required<=set(fields):raise PopulationDataError('invalid PUMS header')
                def checked():
                    for count,row in enumerate(reader,1):
                        if count>MAX_ROWS or None in row or any(v is None for v in row.values()):raise PopulationDataError('malformed/oversized PUMS rows')
                        yield row
                yield checked()
    except (OSError,zipfile.BadZipFile,UnicodeError,csv.Error,RuntimeError) as exc:
        raise PopulationDataError(f'cannot read PUMS archive: {exc}') from exc


def read_pums(housing_zip,persons_zip):
    housing={};members=defaultdict(list);seen=set()
    stats={'housing_rows':0,'person_rows':0,'vacant_units':0,'group_quarters_units':0,'group_quarters_persons':0}
    with csv_rows(housing_zip,'psam_h44.csv',H_FIELDS) as rows:
        for row in rows:
            if row['RT']!='H' or row['STATE']!='44':raise PopulationDataError('wrong housing record type/state')
            key=row['SERIALNO']
            if key in housing:raise PopulationDataError('duplicate housing SERIALNO')
            unit=numeric(row['TYPEHUGQ'],'TYPEHUGQ');size=numeric(row['NP'],'NP');weight=numeric(row['WGTP'],'WGTP')
            if unit not in (1,2,3) or size>20 or weight>9999:raise PopulationDataError('invalid housing type/size/weight')
            if unit!=1:
                if weight!=0 or size!=1:raise PopulationDataError('invalid GQ placeholder')
                stats['group_quarters_units']+=1
            elif size==0:stats['vacant_units']+=1
            housing[key]=(unit,size,weight,row['HHT']);stats['housing_rows']+=1
    with csv_rows(persons_zip,'psam_p44.csv',P_FIELDS) as rows:
        for row in rows:
            if row['RT']!='P' or row['STATE']!='44':raise PopulationDataError('wrong person record type/state')
            p=Person(row['SERIALNO'],numeric(row['SPORDER'],'SPORDER'),numeric(row['AGEP'],'AGEP'),
                     numeric(row['SEX'],'SEX'),numeric(row['RELSHIPP'],'RELSHIPP'),numeric(row['PWGTP'],'PWGTP'))
            key=(p.serialno,p.order)
            if key in seen:raise PopulationDataError('duplicate person order')
            seen.add(key);stats['person_rows']+=1
            if p.serialno not in housing:raise PopulationDataError('orphan person')
            unit,size,weight,hht=housing[p.serialno]
            if unit!=1:
                if p.relationship!=(37 if unit==2 else 38):raise PopulationDataError('GQ type and relationship disagree')
                stats['group_quarters_persons']+=1
            elif size==0 or p.relationship>=37:raise PopulationDataError('person in vacant unit or wrong universe')
            else:members[p.serialno].append(p)
    result=[]
    for key,(unit,size,weight,hht) in sorted(housing.items()):
        if unit==1 and size>0:
            result.append(Household(key,size,numeric(hht,'HHT'),weight,tuple(sorted(members[key],key=lambda p:p.order))))
    if not result:raise PopulationDataError('no occupied households')
    stats['occupied_households']=len(result);stats['household_persons']=sum(h.size for h in result)
    return tuple(result),stats


def read_controls(path):
    try:
        if Path(path).stat().st_size>8*1024*1024:raise PopulationDataError('control extract too large')
        with Path(path).open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream,delimiter='|');fields=reader.fieldnames
            if not fields or len(fields)!=len(set(fields)) or set(fields)!=set(CONTROL_HEADER):raise PopulationDataError('wrong B11016 header')
            rows=list(reader)
        if len(rows)!=1 or rows[0].get('GEO_ID')!='0400000US44' or None in rows[0] or any(v is None for v in rows[0].values()):
            raise PopulationDataError('expected exactly one RI control row')
        row=rows[0];e=lambda i:numeric(row[f'B11016_E{i:03}'],f'B11016 E{i:03}')
        joint=(0,e(3),sum(e(i) for i in range(4,9)),e(10),e(11),sum(e(i) for i in range(12,17)))
        if sum(joint[:3])!=e(2) or sum(joint[3:])!=e(9) or e(2)+e(9)!=e(1):raise PopulationDataError('B11016 leaf/parent totals disagree')
        return HouseholdControls(e(1),(e(2),e(9)),tuple(joint[i]+joint[i+3] for i in range(3))),joint
    except (OSError,UnicodeError,csv.Error) as exc:raise PopulationDataError(f'cannot read controls: {exc}') from exc
