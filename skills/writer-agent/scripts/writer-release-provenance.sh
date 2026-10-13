#!/usr/bin/env bash
# Resolve the immutable release commit for Writer run provenance.
writer_harness_git_hash() {
  local candidate="${LIFE_MANAGER_RELEASE_SHA:-}"
  if [[ "$candidate" =~ ^[0-9a-f]{40}$ ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  candidate="$(git -C "${ARTICLE_ROOT:-.}" log -1 --format=%H -- SKILL.md scripts vendor 2>/dev/null)" || candidate=""
  if [[ "$candidate" =~ ^[0-9a-f]{40}$ ]]; then
    printf '%s\n' "$candidate"
  else
    printf 'UNKNOWN\n'
  fi
}
