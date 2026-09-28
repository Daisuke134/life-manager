#!/usr/bin/env bash
# Install the pinned optional Camofox fallback into the Life Manager cache.
set -euo pipefail

COMMIT="8b5b0959adfadadae38ecce9d7eed706ab102bf1"
ARCHIVE_SHA256="7cf8ad48696b676e066d85bf98895fea58d033daf6cfda2a3727b63464a08830"
ARCHIVE_URL="https://codeload.github.com/jo-inc/camofox-browser/tar.gz/$COMMIT"
CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/life-manager/camofox-browser"
FINAL_ROOT="$CACHE_ROOT/$COMMIT"

sha256_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    sha256sum "$1" | awk '{print $1}'
  fi
}

verified() {
  [ -f "$FINAL_ROOT/archive.tar.gz" ] &&
    [ "$(sha256_file "$FINAL_ROOT/archive.tar.gz")" = "$ARCHIVE_SHA256" ] &&
    [ -f "$FINAL_ROOT/source/LICENSE" ] &&
    [ -f "$FINAL_ROOT/source/package-lock.json" ] &&
    [ -f "$FINAL_ROOT/source/server.js" ] &&
    [ -d "$FINAL_ROOT/source/node_modules" ]
}

if ! verified; then
  command -v curl >/dev/null
  command -v python3 >/dev/null
  command -v npm >/dev/null
  mkdir -p "$CACHE_ROOT"
  TEMP_ROOT="$(mktemp -d "$CACHE_ROOT/.${COMMIT}.tmp.XXXXXX")"
  trap 'rm -rf "$TEMP_ROOT"' EXIT
  curl --fail --location --retry 3 --silent --show-error \
    "$ARCHIVE_URL" -o "$TEMP_ROOT/archive.tar.gz"
  [ "$(sha256_file "$TEMP_ROOT/archive.tar.gz")" = "$ARCHIVE_SHA256" ] || {
    echo "camofox archive checksum mismatch" >&2
    exit 1
  }
  python3 - "$TEMP_ROOT/archive.tar.gz" <<'PY'
import pathlib
import sys
import tarfile

with tarfile.open(sys.argv[1], "r:gz") as bundle:
    roots = set()
    for member in bundle.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise SystemExit("unsafe camofox archive member")
        roots.add(path.parts[0])
    if len(roots) != 1:
        raise SystemExit("camofox archive must have one root")
PY
  mkdir -p "$TEMP_ROOT/source"
  tar -xzf "$TEMP_ROOT/archive.tar.gz" --strip-components=1 -C "$TEMP_ROOT/source"
  [ -f "$TEMP_ROOT/source/LICENSE" ]
  [ -f "$TEMP_ROOT/source/package-lock.json" ]
  [ -f "$TEMP_ROOT/source/server.js" ]
  # stdout is the source-directory contract for callers using command
  # substitution, so package-manager chatter belongs on stderr. `npm ci`
  # deliberately skips lifecycle scripts; rebuild the required native binding
  # explicitly so a changed Node ABI cannot leave Camoufox browserConnected:false.
  (cd "$TEMP_ROOT/source" && npm ci --ignore-scripts >&2 && npm rebuild better-sqlite3 --foreground-scripts >&2)
  if [ -e "$FINAL_ROOT" ]; then
    rm -rf "$FINAL_ROOT"
  fi
  mv "$TEMP_ROOT" "$FINAL_ROOT"
  trap - EXIT
fi

printf '%s\n' "$FINAL_ROOT/source"
