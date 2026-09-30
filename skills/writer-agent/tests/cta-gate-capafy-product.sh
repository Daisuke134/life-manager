#!/usr/bin/env bash
# cta-gate-capafy-product.sh — proves cta-gate.sh accepts a Capafy-skill CTA unchanged.
#
# cta-gate.sh already validates whatever ARTICLE_PRODUCT_LANDING_URL is set to for the run;
# it never hardcodes aniccaai.com. This is the direct proof for the new Capafy product: the
# same gate, unmodified, PASSes a capafy.ai/agent/<id> CTA carrying the extra ct= campaign key,
# and still FAILs when that CTA is missing -- the fail-closed behavior is not weakened for the
# new product.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GATE="$ROOT/scripts/cta-gate.sh"
TMP="$(mktemp -d /tmp/article-cta-capafy.XXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT

export ARTICLE_PRODUCT_LANDING_URL="https://capafy.ai/agent/8123079349"
RUN_ID="daily-2026-09-29"
ARTICLE="$TMP/article-ja.md"

cat >"$ARTICLE" <<EOF
# 見出し

本文。

[Hook Labを試す](https://capafy.ai/agent/8123079349?product_id=capafy-skills&run_id=$RUN_ID&artifact_id=article-ja&variant_id=hook-variant&click_id=$RUN_ID-article-ja&ct=article-hook-lab)
EOF

OUT="$(bash "$GATE" "$ARTICLE" --run-id "$RUN_ID" --artifact-id article-ja)"
printf '%s\n' "$OUT" | /usr/bin/grep -q '"verdict":"PASS"'
printf '%s\n' "$OUT" | /usr/bin/grep -q '"destination":"capafy.ai"'

NO_CTA="$TMP/article-en.md"
printf '# Heading\n\nBody with no product link at all.\n' >"$NO_CTA"
set +e
FAIL_OUT="$(bash "$GATE" "$NO_CTA" --run-id "$RUN_ID" --artifact-id article-en)"
rc=$?
set -e
[ "$rc" -eq 1 ]
printf '%s\n' "$FAIL_OUT" | /usr/bin/grep -q '"verdict":"FAIL"'

echo 'PASS: cta-gate.sh accepts a Capafy-skill CTA and still fails closed without one'
