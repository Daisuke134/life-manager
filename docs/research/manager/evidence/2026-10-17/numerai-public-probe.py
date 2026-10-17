"""公開データのメタデータのみ取得。口座、学習、投稿、stakingは操作しない。"""
import argparse, json, importlib.metadata
from pathlib import Path
from numerapi import NumerAPI
parser=argparse.ArgumentParser()
parser.add_argument('--output-dir',required=True)
args=parser.parse_args()
p=Path(args.output_dir); p.mkdir(parents=True,exist_ok=True)
api=NumerAPI(public_id='',secret_key='')
files=api.list_datasets()
api.download_dataset('v6.0/features.json',dest_path=str(p/'features.json'))
m=json.loads((p/'features.json').read_text())
r={'numerapi_version':importlib.metadata.version('numerapi'),'public_api_only':True,'v6_files':[f for f in files if f.startswith('v6.0/')],'feature_set_counts':{k:len(v) for k,v in m.get('feature_sets',{}).items()},'training_run':False,'submission':False,'staking':False}
(p/'numerai-public-probe.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
