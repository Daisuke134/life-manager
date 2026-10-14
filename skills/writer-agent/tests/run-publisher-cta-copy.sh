#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TMP="$(mktemp -d /tmp/writer-run-publisher-cta.XXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
SKILL="$TMP/skill"
RUN_DIR="$TMP/state/runs/daily-2026-10-15"
STATE="$RUN_DIR/gates/publication-state.json"
PUBLISH_CAPTURE="$TMP/publish-calls.jsonl"
QUALITY_CAPTURE="$TMP/quality-calls.jsonl"
mkdir -p "$SKILL/scripts/_shared" "$TMP/repo/skills/_shared/lib" \
  "$TMP/repo/apps/life-manager/scripts/lib" \
  "$TMP/state" "$RUN_DIR/gates" "$TMP/home" "$TMP/bin"
cp "$ROOT/skills/writer-agent/scripts/run.sh" "$SKILL/scripts/run.sh"
cp "$ROOT/skills/writer-agent/scripts/writer-runtime-env.sh" "$SKILL/scripts/writer-runtime-env.sh"
cp "$ROOT/skills/writer-agent/scripts/publisher_cta_copy.py" "$SKILL/scripts/publisher_cta_copy.py"

cat >"$SKILL/scripts/quality-phase-terminal.py" <<'PY'
import json, os, sys
with open(os.environ["QUALITY_CAPTURE"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"pair": os.environ.get("ARTICLE_PUBLISH_PAIR"), "argv": sys.argv[1:]}) + "\n")
raise SystemExit(0)
PY
cat >"$SKILL/scripts/publish-note.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
md=""
while [ "$#" -gt 0 ]; do
  case "$1" in --markdown-file) md="$2"; shift 2 ;; *) shift ;; esac
done
python3 - "$PUBLISH_CAPTURE" "$ARTICLE_PUBLISH_PAIR" "$md" <<'PY'
import json, sys
with open(sys.argv[1], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"pair": sys.argv[2], "markdown": sys.argv[3]}) + "\n")
PY
printf 'DRAFT (unpublished) https://note.test/draft stage1_ok=true stage2_ok=true\n'
SH
cat >"$SKILL/scripts/_shared/publish-substack-mermaid.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
md="$2"
python3 - "$PUBLISH_CAPTURE" "$ARTICLE_PUBLISH_PAIR" "$md" <<'PY'
import json, sys
with open(sys.argv[1], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"pair": sys.argv[2], "markdown": sys.argv[3]}) + "\n")
PY
printf 'DRAFT (unpublished) https://substack.test/draft\n'
SH
cat >"$SKILL/scripts/propose.sh" <<'SH'
#!/usr/bin/env bash
printf '{"pattern":{"source_id":"test","niche_tags":["test"]}}\n'
SH
cat >"$TMP/repo/skills/_shared/lib/account-history.sh" <<'SH'
ah_record() { :; }
SH
cat >"$TMP/repo/apps/life-manager/scripts/lib/load-env-file.sh" <<'SH'
lm_load_env_file() { :; }
SH
cat >"$TMP/bin/curl" <<'SH'
#!/usr/bin/env bash
printf '404'
SH
chmod +x "$SKILL/scripts/publish-note.sh" "$SKILL/scripts/_shared/publish-substack-mermaid.sh" "$SKILL/scripts/propose.sh" "$TMP/bin/curl"

python3 - "$RUN_DIR" "$STATE" <<'PY'
import hashlib, json, sys
from pathlib import Path
run_dir, state_path = map(Path, sys.argv[1:])
run_id = run_dir.name
drafts = {}
for lang, artifact in (("ja", "article-ja"), ("en", "article-en")):
    path = run_dir / f"article-{lang}.md"
    path.write_text(
        f"# Article {lang}\n\nBody\n\n[Read more](https://writer.example/product?product_id=writer&run_id={run_id}&artifact_id={artifact}&variant_id=role-map&click_id=base-{lang})\n",
        encoding="utf-8",
    )
    drafts[lang] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
state_path.write_text(json.dumps({"run_id": run_id, "drafts": drafts}), encoding="utf-8")
PY
python3 "$ROOT/skills/writer-agent/scripts/publisher_cta_copy.py" prepare \
  --run-dir "$RUN_DIR" --landing-url https://writer.example/product --product-id writer >/dev/null

pair_for() {
  case "$1" in
    note) echo note/ja ;;
    substack-ja) echo substack/ja ;;
    substack-en) echo substack/en ;;
  esac
}
source_for() {
  case "$1" in
    substack-en) echo "$RUN_DIR/article-en.md" ;;
    *) echo "$RUN_DIR/article-ja.md" ;;
  esac
}
copy_for() {
  local slug
  slug="$(pair_for "$1" | tr '/' '-')"
  echo "$RUN_DIR/gates/publisher-cta/$slug.md"
}
run_channel() {
  local channel="$1" pair="$2" source="$3" copy="$4" publication="$5"
  HOME="$TMP/home" PATH="$TMP/bin:$PATH" \
    LIFE_MANAGER_REPO="$TMP/repo" LIFE_MANAGER_ENV_FILE="$TMP/home/missing.env" \
    NOTE_URLNAME="test-writer" SUBSTACK_PUBLICATION_JA="test-ja.substack.com" \
    SUBSTACK_PUBLICATION_EN="test-en.substack.com" \
    ARTICLE_SKILL_DIR="$SKILL" ARTICLE_STATE_DIR="$TMP/state" \
    ARTICLE_RUN_DIR="$RUN_DIR" ARTICLE_PUBLICATION_STATE="$STATE" \
    ARTICLE_LEDGER="$TMP/state/articles.jsonl" ARTICLE_PRODUCT_ID="writer" \
    ARTICLE_PRODUCT_LANDING_URL="https://writer.example/product" \
    ARTICLE_PUBLISH_CTA_V1="1" ARTICLE_PUBLISH_PAIR="$pair" \
    ARTICLE_PUBLISH_COPY_PATH="$copy" QUALITY_CAPTURE="$QUALITY_CAPTURE" \
    PUBLISH_CAPTURE="$PUBLISH_CAPTURE" \
    bash "$SKILL/scripts/run.sh" --channel "$channel" --phase publish \
      --markdown-file "$source" --title "Useful title" --meta "Useful description" >/dev/null
}

run_channel note note/ja "$RUN_DIR/article-ja.md" "$(copy_for note)" note
run_channel substack-ja substack/ja "$RUN_DIR/article-ja.md" "$(copy_for substack-ja)" test-ja.substack.com
run_channel substack-en substack/en "$RUN_DIR/article-en.md" "$(copy_for substack-en)" test-en.substack.com

python3 - "$QUALITY_CAPTURE" "$PUBLISH_CAPTURE" "$RUN_DIR" <<'PY'
import json, sys
from pathlib import Path
quality_path, publish_path, run_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
quality = [json.loads(line) for line in quality_path.read_text(encoding="utf-8").splitlines()]
published = [json.loads(line) for line in publish_path.read_text(encoding="utf-8").splitlines()]
expected = {
    "note/ja": "note-ja.md",
    "substack/ja": "substack-ja.md",
    "substack/en": "substack-en.md",
}
assert len(quality) == len(published) == 3
for row in quality:
    pair = row["pair"]
    expected_source = str(run_dir / ("article-en.md" if pair == "substack/en" else "article-ja.md"))
    assert row["argv"][-1] == expected_source, f"quality gates saw a derived copy for {pair}"
for row in published:
    pair = row["pair"]
    assert Path(row["markdown"]).name == expected[pair], f"publisher did not receive pair copy for {pair}"
PY

before="$(wc -l <"$PUBLISH_CAPTURE" | tr -d ' ')"
set +e
HOME="$TMP/home" PATH="$TMP/bin:$PATH" \
  LIFE_MANAGER_REPO="$TMP/repo" LIFE_MANAGER_ENV_FILE="$TMP/home/missing.env" \
  NOTE_URLNAME="test-writer" SUBSTACK_PUBLICATION_JA="test-ja.substack.com" \
  SUBSTACK_PUBLICATION_EN="test-en.substack.com" \
  ARTICLE_SKILL_DIR="$SKILL" ARTICLE_STATE_DIR="$TMP/state" \
  ARTICLE_RUN_DIR="$RUN_DIR" ARTICLE_PUBLICATION_STATE="$STATE" \
  ARTICLE_LEDGER="$TMP/state/articles.jsonl" ARTICLE_PRODUCT_ID="writer" \
  ARTICLE_PRODUCT_LANDING_URL="https://writer.example/product" \
  ARTICLE_PUBLISH_PAIR="note/ja" QUALITY_CAPTURE="$QUALITY_CAPTURE" \
  PUBLISH_CAPTURE="$PUBLISH_CAPTURE" \
  bash "$SKILL/scripts/run.sh" --channel note --phase publish \
    --markdown-file "$RUN_DIR/article-ja.md" --title "Useful title" --meta "Useful description" \
    >"$TMP/legacy-v1-refusal.out" 2>&1
legacy_rc=$?
set -e
after="$(wc -l <"$PUBLISH_CAPTURE" | tr -d ' ')"
test "$legacy_rc" -ne 0
test "$before" = "$after" || {
  echo "FAIL: run.sh published a v1 run without its copy contract" >&2
  exit 1
}

echo 'PASS: run.sh gates the frozen article and sends the verified publisher copy'
