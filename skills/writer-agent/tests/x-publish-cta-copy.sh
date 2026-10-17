#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TMP="$(mktemp -d /tmp/writer-x-publisher-cta.XXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
SCRIPTS="$TMP/skill/scripts"
RUN_DIR="$TMP/state/runs/daily-2026-10-15"
mkdir -p "$SCRIPTS/x-publish" "$SCRIPTS/_shared/lib" \
  "$TMP/repo/apps/life-manager/scripts/lib" "$TMP/repo/skills/_shared/lib" "$TMP/state" \
  "$TMP/home" "$TMP/bin" "$RUN_DIR/gates"
cp "$ROOT/skills/writer-agent/scripts/x-publish/publish-to-x.sh" "$SCRIPTS/x-publish/publish-to-x.sh"
cp "$ROOT/skills/writer-agent/scripts/writer-runtime-env.sh" "$SCRIPTS/writer-runtime-env.sh"
cp "$ROOT/skills/writer-agent/scripts/publisher_cta_copy.py" "$SCRIPTS/publisher_cta_copy.py"
cp "$ROOT/skills/writer-agent/scripts/publication_contract.py" "$SCRIPTS/publication_contract.py"
cat >"$SCRIPTS/pii-gate.py" <<'PY'
raise SystemExit(0)
PY
cat >"$SCRIPTS/quality-phase-terminal.py" <<'PY'
import json, os, sys
with open(os.environ["QUALITY_CAPTURE"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"pair": os.environ.get("ARTICLE_PUBLISH_PAIR"), "argv": sys.argv[1:]}) + "\n")
raise SystemExit(0)
PY
cat >"$TMP/repo/apps/life-manager/scripts/lib/load-env-file.sh" <<'SH'
lm_load_env_file() { :; }
SH
cat >"$TMP/repo/skills/_shared/lib/account-history.sh" <<'SH'
ah_record() { :; }
SH
cat >"$TMP/bin/publisher-python" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
REAL_PYTHON="${REAL_PYTHON:-$(command -v python3)}"
case "${1:-}" in
  */publisher_cta_copy.py) exec "$REAL_PYTHON" "$@" ;;
  */pii-gate.py) exit 0 ;;
  */publication-guard.py)
    case "${2:-}" in
      query-target) printf '{"found":false}\n' ;;
      register-intent) printf '{"registered":true}\n' ;;
      *) exit 2 ;;
    esac ;;
  */parse_markdown.py) printf '{"content_images":[{}]}\n' ;;
  */prep-x-md.py)
    printf '%s\n' "$X_SRC" >"$X_SOURCE_CAPTURE"
    cp "$X_SRC" "$X_DST"
    printf '\n![cover](cover.png)\n![body](body.png)\n' >>"$X_DST"
    ;;
  */x_chunked.py) printf 'DRAFT_URL: https://x.com/compose/articles/edit/12345678\n' ;;
  *) echo "unexpected publisher python command: $*" >&2; exit 2 ;;
esac
SH
chmod +x "$TMP/bin/publisher-python"
printf 'cover\n' >"$TMP/cover.png"
python3 - "$RUN_DIR" <<'PY'
import hashlib, json, sys
from pathlib import Path
run_dir = Path(sys.argv[1]).resolve()
run_id = run_dir.name
drafts = {}
for lang, artifact in (("ja", "article-ja"), ("en", "article-en")):
    path = run_dir / f"article-{lang}.md"
    path.write_text(
        f"# Article {lang}\n\nBody\n\n[Read more](https://writer.example/product?product_id=writer&run_id={run_id}&artifact_id={artifact}&variant_id=role-map&click_id=base-{lang})\n",
        encoding="utf-8",
    )
    drafts[lang] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
(run_dir / "gates" / "publication-state.json").write_text(
    json.dumps({"run_id": run_id, "drafts": drafts}), encoding="utf-8"
)
PY
# x-article/ja is dormant (publication_contract.DORMANT_PAIRS); only a contract persisted
# while it was still listed (2026-10-15..17 active-four runs) carries an X copy.
python3 - "$ROOT/skills/writer-agent/scripts" "$RUN_DIR" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import publisher_cta_copy
from publication_contract import NEWLY_DORMANT_PAIRS
publisher_cta_copy.ACTIVE_PUBLISHER_PAIRS += NEWLY_DORMANT_PAIRS
publisher_cta_copy.prepare_all(Path(sys.argv[2]), landing_url="https://writer.example/product", product_id="writer")
PY
COPY="$RUN_DIR/gates/publisher-cta/x-article-ja.md"

HOME="$TMP/home" PATH="$TMP/bin:$PATH" REAL_PYTHON="$(command -v python3)" \
  LIFE_MANAGER_REPO="$TMP/repo" LIFE_MANAGER_ENV_FILE="$TMP/home/missing.env" \
  WRITER_BROWSER_PYTHON="$TMP/bin/publisher-python" WRITER_STATE_DIR="$TMP/state/writer" \
  X_COVER="$TMP/cover.png" X_SOURCE_CAPTURE="$TMP/x-source.txt" \
  ARTICLE_RUN_DIR="$RUN_DIR" \
  ARTICLE_PUBLICATION_STATE="$RUN_DIR/gates/publication-state.json" \
  ARTICLE_LEDGER="$TMP/state/articles.jsonl" ARTICLE_PRODUCT_ID=writer \
  ARTICLE_PRODUCT_LANDING_URL=https://writer.example/product \
  ARTICLE_PUBLISH_CTA_V1=1 ARTICLE_PUBLISH_PAIR=x-article/ja \
  ARTICLE_PUBLISH_COPY_PATH="$COPY" ARTICLE_QUALITY_ADVISORY=1 \
  QUALITY_CAPTURE="$TMP/quality-calls.jsonl" \
  bash "$SCRIPTS/x-publish/publish-to-x.sh" publish "$RUN_DIR/article-ja.md" --mode draft --lang ja \
  >"$TMP/out.txt"

test "$(cat "$TMP/x-source.txt")" = "$COPY"
rg -q 'click_id=base-ja-x-article-ja' "$TMP/state/writer/note-work/article-ja-x.md"
rg -q 'click_id=base-ja\)' "$RUN_DIR/article-ja.md"
python3 - "$TMP/quality-calls.jsonl" "$RUN_DIR/article-ja.md" <<'PY'
import json, sys
row = json.loads(open(sys.argv[1], encoding="utf-8").readline())
assert row["argv"][-1] == sys.argv[2], "X quality phase saw the publisher copy instead of the frozen source"
PY
rg -q 'DRAFT_URL: https://x.com/compose/articles/edit/12345678' "$TMP/out.txt"

set +e
HOME="$TMP/home" PATH="$TMP/bin:$PATH" REAL_PYTHON="$(command -v python3)" \
  LIFE_MANAGER_REPO="$TMP/repo" LIFE_MANAGER_ENV_FILE="$TMP/home/missing.env" \
  WRITER_BROWSER_PYTHON="$TMP/bin/publisher-python" WRITER_STATE_DIR="$TMP/state/writer" \
  X_COVER="$TMP/cover.png" X_SOURCE_CAPTURE="$TMP/x-source.txt" \
  ARTICLE_RUN_DIR="$RUN_DIR" \
  ARTICLE_PUBLICATION_STATE="$RUN_DIR/gates/publication-state.json" \
  ARTICLE_LEDGER="$TMP/state/articles.jsonl" ARTICLE_PRODUCT_ID=writer \
  ARTICLE_PRODUCT_LANDING_URL=https://writer.example/product \
  ARTICLE_PUBLISH_PAIR=x-article/ja QUALITY_CAPTURE="$TMP/quality-calls.jsonl" \
  bash "$SCRIPTS/x-publish/publish-to-x.sh" publish "$RUN_DIR/article-ja.md" --mode draft --lang ja \
  >"$TMP/legacy.out" 2>&1
legacy_rc=$?
set -e
test "$legacy_rc" -ne 0
rg -q 'publisher CTA v1 contract requires its copy' "$TMP/legacy.out"
echo 'PASS: X draft staging prepares the per-publisher copy while preserving the canonical article'
