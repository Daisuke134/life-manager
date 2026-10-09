"""Copy the hooklab-02 HyperFrames project and swap only its copy for one real Hook Lab output."""
import html, json, shutil, sys
from pathlib import Path

BASE = Path.home() / ".local/state/life-manager/marketing/capafy-videos"
SRC = BASE / "hooklab-02"


def q(text):
    return html.escape(text, quote=False).replace("'", "&#39;")


def make(spec):
    dst = BASE / spec["slug"]
    if dst.exists():
        raise SystemExit(f"exists: {dst}")
    shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("renders", "snapshots", "postiz-receipts.jsonl", "node_modules"))
    hook = dst / "compositions/hook.html"
    s = hook.read_text()
    s = s.replace(">Your video is good.<", f">{q(spec['hook_a'])}<").replace(">They swipe in 3 seconds.<", f">{q(spec['hook_b'])}<")
    hook.write_text(s)
    cards = dst / "compositions/cards.html"
    s = cards.read_text()
    s = s.replace(">3 winning hooks<", f">{q(spec['title'])}<")
    old = [("Contrarian", "Stop going to the gym every day.", "Day 1 is where you quit"),
           ("Question", "Why does everyone quit by January 20th?", "The January 20th wall"),
           ("Mistake", "You&#39;re not lazy. You&#39;re doing week one wrong.", "Week 1 mistake")]
    for (ol, oq, ot), (nl, nq, nt) in zip(old, spec["cards"]):
        for a, b in ((f'"cd-label">{ol}<', f'"cd-label">{q(nl)}<'),
                     (f"&ldquo;{oq}&rdquo;", f"&ldquo;{q(nq)}&rdquo;"),
                     (f"On-screen: {ot}<", f"On-screen: {q(nt)}<")):
            assert a in s, (spec["slug"], a)
            s = s.replace(a, b, 1)
    if spec.get("badge"):
        s = s.replace(">Recommended<", f">{q(spec['badge'])}<", 1)
    cards.write_text(s)
    if spec.get("cta_head"):
        cta = dst / "compositions/cta.html"
        c = cta.read_text()
        for a, b in (("Search Hook Lab<br />on Capafy", spec["cta_head"]), (">Win the first 3 seconds.<", f">{q(spec['cta_sub'])}<")):
            assert a in c, a
            c = c.replace(a, b, 1)
        cta.write_text(c)
    (dst / "BRIEF.md").write_text(f"# Brief — {spec['slug']}\n\nCopy of hooklab-02 with copy swapped for a real Hook Lab output.\nSource output: {spec['source']}\n")
    return dst


if __name__ == "__main__":
    for spec in json.load(open(sys.argv[1])):
        print(make(spec))
