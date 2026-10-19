#!/usr/bin/env bash
# The Substack preview gate and note cookie extraction run in Writer-owned browser state only:
# an ephemeral headless CloakBrowser context or a Writer-owned storage_state file. None of these
# paths may reach Dais's personal Chrome (identity interactive:dais, the daily-driver profile, CDP
# port 9222) or wrap the publisher in a shared-browser lease.
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd -P)"
port="92""22"
fail=0
check() {
  local file="$1"; shift
  local pattern
  for pattern in "$@"; do
    if grep -nF -- "$pattern" "$SCRIPTS/$file" >&2; then
      printf 'writer-preview contract: %s references %s\n' "$file" "$pattern" >&2
      fail=1
    fi
  done
}

check substack-publish/verify-preview.py \
  "$port" interactive:dais daily-driver with-browser cdp_context_lease connect_over_cdp
check substack-publish/substack-agent-prompt.md "$port" daily-driver
check _shared/publish-substack-mermaid.sh "$port" interactive:dais daily-driver with-browser
check note-publish/extract-note-cookies.py "$port" interactive:dais daily-driver .cloak/profiles
# The Substack publication branch no longer runs under a personal-browser lease. The X Article
# preflight in the same file is a later slice (x-article is dormant).
check article-resume-pending.sh interactive:dais with-browser.sh

[ "$fail" -eq 0 ] || exit 1
printf 'writer-preview owned-browser contract: PASS\n'
