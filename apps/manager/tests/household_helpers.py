import csv
import hashlib
import io
from pathlib import Path
import zipfile
from manager.artifacts import write_artifact

H_FIELDS=('RT','SERIALNO','STATE','WGTP','NP','TYPEHUGQ','HHT')
P_FIELDS=('RT','SERIALNO','STATE','SPORDER','PWGTP','AGEP','SEX','RELSHIPP')


def rows():
    hs=[dict(zip(H_FIELDS,v)) for v in [
        ('H','A','44','2','1','1','4'),('H','B','44','1','2','1','1'),
        ('H','C','44','1','3','1','2'),('H','D','44','1','2','1','5'),
        ('H','E','44','1','3','1','5'),('H','V','44','1','0','1',''),('H','G','44','0','1','2','')]]
    ps=[]
    for serial,ages,rels in [('A',[70],[20]),('B',[40,39],[20,21]),('C',[38,10,7],[20,25,25]),
                              ('D',[30,29],[20,22]),('E',[21,22,23],[20,34,34]),('G',[75],[37])]:
        for i,(age,rel) in enumerate(zip(ages,rels),1):
            ps.append(dict(zip(P_FIELDS,('P',serial,'44',str(i),'3',str(age),'1',str(rel)))))
    return hs,ps


def zip_rows(path,member,fields,data):
    stream=io.StringIO();writer=csv.DictWriter(stream,fields);writer.writeheader();writer.writerows(data)
    with zipfile.ZipFile(path,'w') as z:z.writestr(member,stream.getvalue())


def fixture(root,housing=None,persons=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);hs,ps=rows()
    zip_rows(root/'housing.zip','psam_h44.csv',H_FIELDS,hs if housing is None else housing)
    zip_rows(root/'persons.zip','psam_p44.csv',P_FIELDS,ps if persons is None else persons)
    estimates=[10,5,3,2,0,0,0,0,5,4,1,0,0,0,0,0]
    header=['GEO_ID']+[f'B11016_{kind}{i:03}' for i in range(1,17) for kind in ('E','M')]
    line=['0400000US44']+[str(v) for value in estimates for v in (value,1)]
    (root/'b11016.dat').write_text('|'.join(header)+'\n'+'|'.join(line)+'\n')
    from manager.population.household_sources import URLS
    files={name:{'url':url,'bytes':(root/name).stat().st_size,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()} for name,url in URLS.items()}
    write_artifact(root/'source.json',{'schema_version':1,'state':'44','period':'2020-2024','acquired_at':'2026-10-18T00:00:00+00:00','files':files,'table_hash_scope':'state_extract'})
    return root
