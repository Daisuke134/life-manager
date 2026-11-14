"""Validate the reconstructed renderer against the on-disk SFT file (ground truth)."""
import json
import pandas as pd
from sklearn.model_selection import train_test_split

TREATED_TEXT = "send a promotional e-mail featuring women's products."
CONTROL_TEXT = "send no e-mail."

def render_prompt(recency, history, mens, womens, zip_code, newbie, channel, treated):
    iv = TREATED_TEXT if treated else CONTROL_TEXT
    return (
        f"History: recency={recency}; spend={history}; mens={mens}; "
        f"womens={womens}; zip={zip_code}; newbie={newbie}; channel={channel}.\n"
        f"Intervention: {iv}\n"
        "Will the person visit the website within two weeks? "
        "Answer 1 for yes, 0 for no.\nAnswer:"
    )

df = pd.read_csv("/home/hatch/workspace/manager-v0-work/data/hillstrom.csv.gz")
df = df[df.segment.isin(["Womens E-Mail", "No E-Mail"])].reset_index(drop=True)
t = (df.segment == "Womens E-Mail").astype(int).values
y = df.visit.values
strat = t * 2 + y
idx = df.index.values
itr, ite, ytr, yte, ttr, tte = train_test_split(idx, y, t, test_size=0.3, random_state=0, stratify=strat)
print("split sizes:", len(itr), len(ite))

rendered = {}
for i in itr:
    r = df.loc[i]
    rendered[i] = (render_prompt(r.recency, r.history, r.mens, r.womens, r.zip_code,
                                 r.newbie, r.channel, bool(t[i])), f" {int(y[i])}")

sft = [json.loads(l) for l in open("/home/hatch/workspace/manager-v0-work/data/sft_train.jsonl")]
rendered_set = set(rendered.values())
hits = sum(1 for r in sft if (r["prompt"], r["completion"]) in rendered_set)
print(f"SFT rows matched exactly: {hits}/{len(sft)}")
assert hits == len(sft), "renderer mismatch"
print("RENDERER VALIDATED: all SFT prompt/completion pairs reproduced exactly.")
