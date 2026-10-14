#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DISPATCH="$ROOT/skills/writer-agent/scripts/platform-dispatch.sh"
TMP="$(mktemp -d /tmp/article-publisher-cta.XXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
RUN_ID="daily-2026-10-15"
RUN_DIR="$TMP/state/runs/$RUN_ID"
OUT="$TMP/out"
CALLS="$TMP/calls"
HELPER="$TMP/record-copy.sh"
MANIFEST="$RUN_DIR/gates/platform-dispatch.jsonl"
RESULTS="$RUN_DIR/gates/platform-dispatch-results.jsonl"
mkdir -p "$RUN_DIR/gates" "$OUT"

cat >"$HELPER" <<'HELPER'
#!/usr/bin/env bash
set -euo pipefail
source_file=""
publish_copy="${ARTICLE_PUBLISH_COPY_PATH:-}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --markdown-file) source_file="$2"; shift 2 ;;
    *.md) source_file="$1"; shift ;;
    *) shift ;;
  esac
  done
[ -n "$publish_copy" ] && source_file="$publish_copy"
[ -n "$source_file" ] && [ -f "$source_file" ]
slug="$(printf '%s' "$ARTICLE_PUBLISH_PAIR" | tr '/' '-')"
printf '%s\n' "$ARTICLE_PUBLISH_PAIR" >>"$CALLS"
cp "$source_file" "$OUT/$slug.md"
HELPER
chmod +x "$HELPER"
printf 'cover\n' >"$TMP/cover.png"

python3 - "$RUN_DIR" "$MANIFEST" "$HELPER" "$OUT" "$CALLS" "$TMP/cover.png" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

run_dir, manifest, helper, out_dir, calls, cover = map(Path, sys.argv[1:])
run_dir = run_dir.resolve()
run_id = run_dir.name
sources = {
    "ja": (
        "# Article JA\n\n本文です。\n\n"
        f"[続きを読む](https://writer.example/product?product_id=writer&run_id={run_id}"
        f"&artifact_id=article-ja&variant_id=role-map&click_id={run_id}-article-ja)\n"
    ),
    "en": (
        "---\ntitle: A useful guide\ntags: agents, writing\n---\n"
        "# Article EN\n\nUseful body.\n\n"
        f"[Read more](https://writer.example/product?product_id=writer&run_id={run_id}"
        f"&artifact_id=article-en&variant_id=role-map&click_id={run_id}-article-en)\n"
    ),
}
draft_rows = {}
for lang, body in sources.items():
    path = run_dir / f"article-{lang}.md"
    path.write_text(body, encoding="utf-8")
    draft_rows[lang] = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
state_path = run_dir / "gates" / "publication-state.json"
state_path.write_text(json.dumps({"run_id": run_id, "drafts": draft_rows}), encoding="utf-8")

jobs = [
    ("note", "ja", "note/ja", ["bash", str(helper), "--markdown-file", str(run_dir / "article-ja.md")]),
    ("substack-ja", "ja", "substack/ja", ["bash", str(helper), "--markdown-file", str(run_dir / "article-ja.md")]),
    ("substack-en", "en", "substack/en", ["bash", str(helper), "--markdown-file", str(run_dir / "article-en.md")]),
    ("x-article", "ja", "x-article/ja", ["bash", str(helper), str(run_dir / "article-ja.md")]),
]
with manifest.open("w", encoding="utf-8") as handle:
    for platform, lang, pair, argv in jobs:
        env = {
            "ARTICLE_RUN_DIR": str(run_dir),
            "ARTICLE_PUBLICATION_STATE": str(state_path),
            "ARTICLE_LEDGER": str(run_dir.parent.parent / "articles.jsonl"),
            "ARTICLE_PUBLISH_PAIR": pair,
            "ARTICLE_PUBLISH_CTA_V1": "1",
            "ARTICLE_PRODUCT_ID": "writer",
            "ARTICLE_PRODUCT_LANDING_URL": "https://writer.example/product",
            "CALLS": str(calls),
            "OUT": str(out_dir),
        }
        if platform == "x-article":
            env["X_COVER"] = str(cover)
        handle.write(json.dumps({"platform": platform, "lang": lang, "argv": argv, "env": env}) + "\n")
PY

sha_ja="$(shasum -a 256 "$RUN_DIR/article-ja.md" | cut -d' ' -f1)"
sha_en="$(shasum -a 256 "$RUN_DIR/article-en.md" | cut -d' ' -f1)"
bash "$DISPATCH" --manifest "$MANIFEST" --results "$RESULTS"

python3 - "$RUN_DIR" "$OUT" "$RESULTS" "$sha_ja" "$sha_en" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

run_dir, out_dir, results = map(Path, sys.argv[1:4])
sha_ja, sha_en = sys.argv[4:]
run_id = run_dir.name
expected = {
    "note/ja": ("ja", "article-ja", f"{run_id}-article-ja-note-ja"),
    "substack/ja": ("ja", "article-ja", f"{run_id}-article-ja-substack-ja"),
    "substack/en": ("en", "article-en", f"{run_id}-article-en-substack-en"),
    "x-article/ja": ("ja", "article-ja", f"{run_id}-article-ja-x-article-ja"),
}
click_ids = set()
for pair, (lang, artifact_id, click_id) in expected.items():
    slug = pair.replace("/", "-")
    source = run_dir / f"article-{lang}.md"
    copy = out_dir / f"{slug}.md"
    assert copy.is_file(), f"publisher copy missing for {pair}"
    source_body = source.read_text(encoding="utf-8")
    copy_body = copy.read_text(encoding="utf-8")
    match = re.search(r"https://writer\.example/product\?[^)\s]+", copy_body)
    assert match, f"measurable CTA missing from {pair} copy"
    query = parse_qs(urlsplit(match.group(0)).query, keep_blank_values=True)
    assert query["click_id"] == [click_id], f"wrong publisher click_id for {pair}: {query.get('click_id')}"
    assert query["product_id"] == ["writer"]
    assert query["run_id"] == [run_id]
    assert query["artifact_id"] == [artifact_id]
    assert query["variant_id"] == ["role-map"]
    expected_copy = source_body.replace(
        f"click_id={run_id}-{artifact_id})",
        f"click_id={click_id})",
    )
    assert copy_body == expected_copy, f"non-click_id source bytes changed for {pair}"
    click_ids.add(click_id)

assert len(click_ids) == 4, "active publisher click IDs must be pair-unique"
assert hashlib.sha256((run_dir / "article-ja.md").read_bytes()).hexdigest() == sha_ja
assert hashlib.sha256((run_dir / "article-en.md").read_bytes()).hexdigest() == sha_en
rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()]
assert len(rows) == 4 and all(row["status"] == "ok" for row in rows)
PY

cp -R "$RUN_DIR/gates/publisher-cta" "$TMP/receipts-before-retry"
bash "$DISPATCH" --manifest "$MANIFEST" --results "$RESULTS"
diff -r "$TMP/receipts-before-retry" "$RUN_DIR/gates/publisher-cta"

BAD_RUN_DIR="$TMP/bad-state/runs/daily-2026-10-16"
BAD_OUT="$TMP/bad-out"
BAD_CALLS="$TMP/bad-calls"
BAD_MANIFEST="$BAD_RUN_DIR/gates/platform-dispatch.jsonl"
mkdir -p "$BAD_RUN_DIR/gates" "$BAD_OUT"
python3 - "$RUN_DIR" "$BAD_RUN_DIR" "$MANIFEST" "$BAD_MANIFEST" "$OUT" "$BAD_OUT" "$CALLS" "$BAD_CALLS" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

source_run, bad_run, manifest, bad_manifest, _old_out, bad_out, _old_calls, bad_calls = map(Path, sys.argv[1:])
source_run = source_run.resolve()
bad_run = bad_run.resolve()
bad_run_id = bad_run.name
drafts = {}
for lang in ("ja", "en"):
    body = (source_run / f"article-{lang}.md").read_text(encoding="utf-8")
    body = body.replace(source_run.name, bad_run_id)
    if lang == "en":
        body = "\n".join(line for line in body.splitlines() if "writer.example/product?" not in line) + "\n"
    path = bad_run / f"article-{lang}.md"
    path.write_text(body, encoding="utf-8")
    drafts[lang] = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
state_path = bad_run / "gates" / "publication-state.json"
state_path.write_text(json.dumps({"run_id": bad_run_id, "drafts": drafts}), encoding="utf-8")
rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
with bad_manifest.open("w", encoding="utf-8") as handle:
    for row in rows:
        row["argv"] = [arg.replace(str(source_run), str(bad_run)) for arg in row["argv"]]
        row["env"].update({
            "ARTICLE_RUN_DIR": str(bad_run),
            "ARTICLE_PUBLICATION_STATE": str(state_path),
            "ARTICLE_LEDGER": str(bad_run.parent.parent / "articles.jsonl"),
            "CALLS": str(bad_calls),
            "OUT": str(bad_out),
        })
        handle.write(json.dumps(row) + "\n")
PY

set +e
bash "$DISPATCH" --manifest "$BAD_MANIFEST" --results "$BAD_RUN_DIR/gates/results.jsonl" >"$TMP/bad.out" 2>&1
bad_rc=$?
set -e
test "$bad_rc" -ne 0
test ! -e "$BAD_CALLS" || {
  echo "FAIL: a publisher ran despite an incomplete CTA set" >&2
  exit 1
}

PARTIAL_MANIFEST="$TMP/partial.jsonl"
PARTIAL_CALLS="$TMP/partial-calls"
PARTIAL_OUT="$TMP/partial-out"
mkdir -p "$PARTIAL_OUT"
python3 - "$BAD_MANIFEST" "$PARTIAL_MANIFEST" "$PARTIAL_CALLS" "$PARTIAL_OUT" <<'PY'
import json, sys
source, destination, calls, out_dir = sys.argv[1:]
row = json.loads(open(source, encoding="utf-8").readline())
row["env"]["CALLS"] = calls
row["env"]["OUT"] = out_dir
with open(destination, "w", encoding="utf-8") as handle:
    handle.write(json.dumps(row) + "\n")
PY
set +e
bash "$DISPATCH" --manifest "$PARTIAL_MANIFEST" --results "$TMP/partial-results.jsonl" >"$TMP/partial.out" 2>&1
partial_rc=$?
set -e
test "$partial_rc" -ne 0
test ! -e "$PARTIAL_CALLS" || {
  echo "FAIL: a partial first dispatch reached a publisher" >&2
  exit 1
}

echo 'PASS: each active publisher receives a stable unique click_id copy; frozen source bytes remain unchanged'
