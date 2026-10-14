#!/usr/bin/env bash
# Execute JSONL argv jobs in the foreground, recording every result after preflight passes.
set -uo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

MANIFEST=""
RESULTS=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    --results) RESULTS="$2"; shift 2 ;;
    *) echo "FATAL: unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -f "$MANIFEST" ] && [ -n "$RESULTS" ] || { echo "FATAL: --manifest and --results required" >&2; exit 2; }

# Validate the complete plan and prepare local publisher copies before the first publisher effect.
# JSON argv preserves literal dollars and cannot be reinterpreted by a second shell. Shell -c
# forms are rejected because they can detach background work and report completion early.
if ! python3 - "$MANIFEST" "$SCRIPT_DIR" <<'PY'
import json, os, re, sys
from pathlib import Path

manifest = Path(sys.argv[1])
script_dir = Path(sys.argv[2])
errors = []
rows = []
active_pair_platform = {
    "note/ja": {("note", "ja")},
    "substack/ja": {("substack-ja", "ja"), ("substack", "ja")},
    "substack/en": {("substack-en", "en"), ("substack", "en")},
    "x-article/ja": {("x-article", "ja")},
}
v1_rows = []
for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
        continue
    try:
        row = json.loads(line)
    except json.JSONDecodeError as exc:
        errors.append(f"line {number}: invalid JSON: {exc}")
        continue
    rows.append((number, row))

for number, row in rows:
    platform = row.get("platform")
    lang = row.get("lang")
    argv = row.get("argv")
    env = row.get("env", {})
    if not isinstance(platform, str) or not platform or lang not in {"ja", "en"}:
        errors.append(f"line {number}: platform/lang required")
        continue
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
        errors.append(f"line {number}: argv must be a non-empty JSON string array")
        continue
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        errors.append(f"line {number}: env must be a JSON string object")
        continue
    shell = os.path.basename(argv[0])
    if shell in {"bash", "sh", "zsh", "dash", "ksh"} and len(argv) > 1 and argv[1] in {"-c", "-lc", "-cl"}:
        errors.append(f"line {number}: shell -c/background dispatch is forbidden; provide foreground argv")
    if platform in {"x", "x-ja", "x-en", "x-article"}:
        cover = env.get("X_COVER", "")
        if not cover or not Path(cover).is_file():
            errors.append(f"line {number}: X_COVER must name an existing file")
    if platform == "devto":
        try:
            markdown = Path(argv[argv.index("--markdown-file") + 1])
        except (ValueError, IndexError):
            errors.append(f"line {number}: Dev.to argv must include --markdown-file")
        else:
            try:
                content = markdown.read_text(encoding="utf-8")
            except OSError:
                errors.append(f"line {number}: Dev.to markdown file is unreadable: {markdown}")
            else:
                if not re.search(r"^tags:\s*\S", content, re.MULTILINE):
                    errors.append(f"line {number}: Dev.to markdown requires non-empty tags frontmatter")
    pair = env.get("ARTICLE_PUBLISH_PAIR", "")
    run_dir_value = env.get("ARTICLE_RUN_DIR", "")
    cta_mode = env.get("ARTICLE_PUBLISH_CTA_V1", "")
    if cta_mode and cta_mode != "1":
        errors.append(f"line {number}: ARTICLE_PUBLISH_CTA_V1 must be exactly 1 when present")
    cta_v1 = env.get("ARTICLE_PUBLISH_CTA_V1", "") == "1"
    contract_path = (
        Path(run_dir_value) / "gates" / "publisher-cta" / "contract.json"
        if run_dir_value else None
    )
    if pair in active_pair_platform and contract_path is not None and contract_path.exists() and not cta_v1:
        errors.append(f"line {number}: existing publisher CTA v1 run requires ARTICLE_PUBLISH_CTA_V1=1")
    if cta_v1:
        expected = active_pair_platform.get(pair)
        if expected is None or (platform, lang) not in expected:
            errors.append(f"line {number}: publisher pair does not match platform/lang")
            continue
        if not run_dir_value:
            errors.append(f"line {number}: ARTICLE_RUN_DIR is required for publisher CTA v1")
            continue
        try:
            run_dir = Path(run_dir_value).resolve(strict=True)
        except OSError as error:
            errors.append(f"line {number}: ARTICLE_RUN_DIR is unreadable: {error}")
            continue
        source = run_dir / f"article-{lang}.md"
        if not source.is_file() or source.is_symlink():
            errors.append(f"line {number}: frozen publisher source is missing or unsafe: {source}")
        else:
            source_args = []
            for argument in argv:
                try:
                    candidate = Path(argument)
                    if candidate.is_absolute() and candidate.resolve(strict=True) == source:
                        source_args.append(argument)
                except (OSError, RuntimeError):
                    continue
            if len(source_args) != 1:
                errors.append(f"line {number}: argv must contain the absolute frozen source exactly once")
        expected_state = str((run_dir / "gates" / "publication-state.json").resolve())
        expected_ledger = str((run_dir.parent.parent / "articles.jsonl").resolve())
        actual_state = Path(env.get("ARTICLE_PUBLICATION_STATE", "")).resolve(strict=False)
        actual_ledger = Path(env.get("ARTICLE_LEDGER", "")).resolve(strict=False)
        if str(actual_state) != expected_state:
            errors.append(f"line {number}: publication state must be this run's canonical state")
        if str(actual_ledger) != expected_ledger:
            errors.append(f"line {number}: ledger must be this run's canonical article ledger")
        if not env.get("ARTICLE_PRODUCT_LANDING_URL") and not os.environ.get("ARTICLE_PRODUCT_LANDING_URL"):
            errors.append(f"line {number}: ARTICLE_PRODUCT_LANDING_URL is required for publisher CTA v1")
        if not env.get("ARTICLE_PRODUCT_ID") and not os.environ.get("ARTICLE_PRODUCT_ID"):
            errors.append(f"line {number}: ARTICLE_PRODUCT_ID is required for publisher CTA v1")
        v1_rows.append((number, row, run_dir.resolve()))

if errors:
    for error in errors:
        print(f"PREFLIGHT: {error}", file=sys.stderr)
    raise SystemExit(2)
if not rows:
    print("PREFLIGHT: manifest has no jobs", file=sys.stderr)
    raise SystemExit(2)
if v1_rows:
    v1_pairs = [row.get("env", {}).get("ARTICLE_PUBLISH_PAIR") for _, row, _ in v1_rows]
    runs = {run_dir for _, _, run_dir in v1_rows}
    state_paths = {row.get("env", {}).get("ARTICLE_PUBLICATION_STATE") for _, row, _ in v1_rows}
    ledger_paths = {row.get("env", {}).get("ARTICLE_LEDGER") for _, row, _ in v1_rows}
    landing_urls = {
        row.get("env", {}).get("ARTICLE_PRODUCT_LANDING_URL") or os.environ.get("ARTICLE_PRODUCT_LANDING_URL", "")
        for _, row, _ in v1_rows
    }
    product_ids = {
        row.get("env", {}).get("ARTICLE_PRODUCT_ID") or os.environ.get("ARTICLE_PRODUCT_ID", "")
        for _, row, _ in v1_rows
    }
    if len(v1_pairs) != len(set(v1_pairs)):
        print("PREFLIGHT: duplicate publisher CTA v1 pair", file=sys.stderr)
        raise SystemExit(2)
    if (
        len(runs) != 1
        or len(state_paths) != 1
        or len(ledger_paths) != 1
        or len(landing_urls) != 1
        or len(product_ids) != 1
        or len(v1_rows) != len(rows)
    ):
        print("PREFLIGHT: publisher CTA v1 rows must share one run and contain only active publisher pairs", file=sys.stderr)
        raise SystemExit(2)
    run_dir = next(iter(runs))
    contract_path = run_dir / "gates" / "publisher-cta" / "contract.json"
    existing_contract = contract_path.is_file()
    if not existing_contract and set(v1_pairs) != set(active_pair_platform):
        print("PREFLIGHT: first publisher CTA v1 dispatch requires all four active pairs", file=sys.stderr)
        raise SystemExit(2)
    if set(v1_pairs) - set(active_pair_platform):
        print("PREFLIGHT: publisher CTA v1 manifest includes a non-active pair", file=sys.stderr)
        raise SystemExit(2)
    try:
        sys.path.insert(0, str(script_dir))
        from publisher_cta_copy import PublisherCTAError, prepare_all

        first_env = v1_rows[0][1]["env"]
        prepare_all(
            run_dir,
            landing_url=next(iter(landing_urls)),
            product_id=next(iter(product_ids)),
        )
    except (PublisherCTAError, KeyError, OSError, ValueError) as error:
        print(f"PREFLIGHT: publisher CTA copies could not be prepared: {error}", file=sys.stderr)
        raise SystemExit(2) from error
PY
then
  exit 2
fi

mkdir -p "$(dirname "$RESULTS")"
: >"$RESULTS"
failed=0
while IFS= read -r job_json; do
  [ -n "$job_json" ] || continue
  platform=$(printf '%s' "$job_json" | jq -r '.platform')
  lang=$(printf '%s' "$job_json" | jq -r '.lang')
  raw_file="$(mktemp /tmp/article-dispatch.XXXXXX)" || exit 2
  python3 - "$job_json" "$SCRIPT_DIR" >"$raw_file" 2>&1 <<'PY'
import json, os, subprocess, sys
from pathlib import Path

job = json.loads(sys.argv[1])
script_dir = Path(sys.argv[2])
env = os.environ.copy()
env.update(job.get("env", {}))
argv = list(job["argv"])
if env.get("ARTICLE_PUBLISH_CTA_V1") == "1":
    try:
        sys.path.insert(0, str(script_dir))
        from publisher_cta_copy import publisher_copy_path

        pair = env["ARTICLE_PUBLISH_PAIR"]
        run_dir = Path(env["ARTICLE_RUN_DIR"])
        source = run_dir / f"article-{pair.rsplit('/', 1)[1]}.md"
        copy_path = publisher_copy_path(run_dir, pair, source)
        if copy_path == source:
            raise ValueError("publisher CTA v1 contract has no publisher copy")
        env["ARTICLE_PUBLISH_COPY_PATH"] = str(copy_path)
        print(json.dumps({"publisher_copy_pair": pair, "publisher_copy_path": str(copy_path)}, separators=(",", ":")))
    except Exception as error:
        print(f"publisher CTA copy refused: {error}", file=sys.stderr)
        raise SystemExit(2) from error
completed = subprocess.run(argv, env=env, check=False)
raise SystemExit(completed.returncode)
PY
  rc=$?
  cat "$raw_file"
  [ "$rc" -eq 0 ] || failed=1
  python3 - "$RESULTS" "$platform" "$lang" "$rc" "$raw_file" <<'PY'
import json, sys
from datetime import datetime, timezone
path, platform, lang, rc, raw_path = sys.argv[1:]
raw = open(raw_path, encoding="utf-8", errors="replace").read()
row = {
    "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "platform": platform,
    "lang": lang,
    "status": "ok" if int(rc) == 0 else "failed",
    "exit_code": int(rc),
    "raw_output": raw,
}
with open(path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
PY
  rm -f "$raw_file"
done < <(python3 - "$MANIFEST" <<'PY'
import json, sys

rows = [
    json.loads(line)
    for line in open(sys.argv[1], encoding="utf-8")
    if line.strip()
]

def priority(row):
    platform = row["platform"]
    if platform == "note":
        return 0
    if platform.startswith("substack"):
        return 1
    if platform == "zenn":
        return 3
    return 2

for _, row in sorted(enumerate(rows), key=lambda item: (priority(item[1]), item[0])):
    print(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
PY
)

[ "$failed" -eq 0 ]
