#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
HELPER="$SCRIPT_DIR/../scripts/writer-release-provenance.sh"
ARTICLE_DAILY="$SCRIPT_DIR/../article-daily.sh"

if [[ ! -f "$HELPER" ]]; then
  printf 'FAIL: release provenance helper does not exist\n' >&2
  exit 1
fi
source "$HELPER"

assert_equals() {
  local expected="$1" actual="$2" label="$3"
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL: %s expected=%s actual=%s\n' "$label" "$expected" "$actual" >&2
    exit 1
  fi
}

FAKE_GIT_SHA="$(printf '%040d' 2)"
FAKE_GIT_FAIL=0
ARTICLE_ROOT="/immutable-release"
git() {
  [[ "$FAKE_GIT_FAIL" == 0 ]] || return 1
  printf '%s\n' "$FAKE_GIT_SHA"
}

LIFE_MANAGER_RELEASE_SHA="$(printf '%040d' 1)"
assert_equals "$LIFE_MANAGER_RELEASE_SHA" "$(writer_harness_git_hash)" "release environment SHA wins"

unset LIFE_MANAGER_RELEASE_SHA
assert_equals "$FAKE_GIT_SHA" "$(writer_harness_git_hash)" "local checkout fallback"

LIFE_MANAGER_RELEASE_SHA="invalid"
assert_equals "$FAKE_GIT_SHA" "$(writer_harness_git_hash)" "invalid environment SHA falls back"

unset LIFE_MANAGER_RELEASE_SHA
FAKE_GIT_FAIL=1
assert_equals "UNKNOWN" "$(writer_harness_git_hash)" "missing provenance stays explicit"

if ! grep -q 'writer_harness_git_hash' "$ARTICLE_DAILY"; then
  printf 'FAIL: article-daily does not use the provenance helper\n' >&2
  exit 1
fi

printf 'PASS: Writer release provenance capture\n'
