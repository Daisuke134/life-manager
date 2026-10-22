#!/usr/bin/env python3
"""Inspect public Nature source XLSX already downloaded; no new LLM inference."""
import json, hashlib, math, statistics, sys, zipfile, xml.etree.ElementTree as E
from pathlib import Path
BASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
def read_xlsx(path):
    with zipfile.ZipFile(path) as z:
        ss = []
        if "xl/sharedStrings.xml" in z.namelist():
            ss = ["".join(si.itertext()) for si in E.fromstring(z.read("xl/sharedStrings.xml"))]
        output = {}
        for name in z.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            rows = []
            for row in E.fromstring(z.read(name)).findall(".//s:row", NS):
                result = {}
                for cell in row:
                    v = cell.find("s:v", NS)
                    text = v.text if v is not None else "".join(cell.itertext())
                    if cell.attrib.get("t") == "s":
                        text = ss[int(text)]
                    result[cell.attrib["r"]] = text
                rows.append(result)
            output[name] = rows
        return output
def records(rows):
    headers = {"".join(filter(str.isalpha, k)): v for k, v in rows[0].items()}
    return [{headers["".join(filter(str.isalpha, k))]: v for k,v in row.items()} for row in rows[1:]]
def main():
    raw = read_xlsx(BASE / "fig1.xlsx")
    rows = records(raw["xl/worksheets/sheet1.xml"])
    assert len(rows) == 3356
    assert len({r["study"] for r in rows}) == 70
    models = records(raw["xl/worksheets/sheet2.xml"])
    assert len(models) == 8
    gpt4 = next(r for r in models if r["model"] == "gpt-4")
    assert abs(float(gpt4["cor_raw"]) - .8507895015768856) < 1e-12
    assert abs(float(gpt4["estimate"]) - .9151266459087334) < 1e-12
    x = [float(r["prediction"]) for r in rows]
    y = [float(r["estimate"]) for r in rows]
    mx, my = statistics.mean(x), statistics.mean(y)
    cov = sum((i-mx)*(j-my) for i,j in zip(x,y))
    xx = sum((i-mx)**2 for i in x)
    yy = sum((i-my)**2 for i in y)
    result = {
        "rows": len(rows), "studies": len({r["study"] for r in rows}),
        "published_model_rows": len(models), "published_gpt4_raw_r": float(gpt4["cor_raw"]),
        "naive_pooled_directed_r": cov / math.sqrt(xx*yy),
        "naive_pooled_ols_slope": cov / xx,
        "naive_pooled_rmse_scale0to1": math.sqrt(statistics.mean((i-j)**2 for i,j in zip(x,y))),
        "scope": "Released aggregates; dependent rows; no original cluster CI or random-reference32 protocol; no fresh model inference or human outcomes.",
        "sha256": {name: hashlib.sha256((BASE/name).read_bytes()).hexdigest()
                   for name in ["supplement.pdf", "fig1.xlsx", "fig2.xlsx", "fig3.xlsx"]}
    }
    print(json.dumps(result, indent=2))
if __name__ == "__main__":
    main()

