#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/run" "$TMP/assets"
printf 'headline' >"$TMP/headline.png"
printf 'body' >"$TMP/run/body-diagram.png"
cat >"$TMP/article.md" <<'MD'
# Canonical media test

本文です。

```mermaid
flowchart TD
  A[縦長になる図] --> B[重複してはいけない]
```

<!-- canonical-media:start -->
![](headline-image.png)
![](body-diagram.png)
<!-- canonical-media:end -->
MD

X_SRC="$TMP/article.md" X_DST="$TMP/prepared.md" X_ASSETS="$TMP/assets" \
X_TITLE="Canonical media test" X_COVER="$TMP/headline.png" ARTICLE_RUN_DIR="$TMP/run" \
  /Users/anicca/.local/share/life-manager/venv/bin/python \
  "$ROOT/scripts/x-publish/prep-x-md.py" >/dev/null

grep -q 'body-diagram.png' "$TMP/prepared.md"
! grep -q 'fig1.png' "$TMP/prepared.md"
test "$(find "$TMP/assets" -type f -name '*.png' | wc -l | tr -d ' ')" = 0
echo "PASS: canonical X preparation keeps the immutable body asset only"
