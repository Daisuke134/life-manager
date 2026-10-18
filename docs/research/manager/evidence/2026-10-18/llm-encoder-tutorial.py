"""上流の文章化関数だけを架空データで実行。モデル学習・推論なし。"""
import argparse, importlib.util, json
from pathlib import Path
import pandas as pd
parser=argparse.ArgumentParser()
parser.add_argument('--upstream',required=True,help='llm-pop-synth checkout directory')
args=parser.parse_args()
p=Path(args.upstream)/'utils/text_encoder.py'
s=importlib.util.spec_from_file_location('research_text_encoder',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
encoder=m.TextEncoder(feature_order=['Age','Worktype','NumHH'])
text=encoder.encode_row(pd.Series({'Age':'30-39','Worktype':6,'NumHH':3}))
assert text=='Age group is 30-39, Work type is Manager/Office, Number of household members is 3.'
print(json.dumps({'mode':'fictional_record_upstream_text_encoder_only','encoded_text':text,'model_training':False,'llm_inference':False,'data':'fictional record, not real person'},indent=2))
