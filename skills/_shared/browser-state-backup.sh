#!/usr/bin/env bash
# browser-state-backup.sh — daily snapshot + restore of every CloakBrowser profile's login state,
# so a chromium crash / OOM kill / disk-pressure profile wipe never forces a human back through
# login + 2FA. Covers ALL profiles under ~/.cloak/profiles/ (the shared daily-driver AND every
# per-account isolated profile, e.g. clip-en/clip-en2/clip-en3/clip-en4 for the clip-loop accounts),
# not just the daily-driver — a prior gap: session_vault.py + cdp_daily_driver_guard.sh only ever
# watched/backed up the daily-driver (:9222), so an isolated account profile's session could die
# silently with nothing noticing or banking it. This script is profile-agnostic and closes that gap.
#
# What gets backed up, and why (2026-07-16 audit of ~/.cloak):
#   1. Each profile's Default/Cookies + Default/Login Data (SQLite) + Local State (JSON) — the actual
#      browser-level login state. This is the thing that makes an account "logged in" at all.
#   2. ~/.cloak/vault/ — the existing session_vault.py cookie-JSON snapshots (daily-driver only today,
#      restored over CDP by cdp_daily_driver_guard.sh after every relaunch).
#   3. ~/.cloak/*.json directly under ~/.cloak (creds: ig-*.json, clip-accounts.json,
#      instagrapi-*.json, etc.) — account metadata + any saved instagrapi settings dumps.
#
# Why sqlite3 .backup instead of a plain `cp` for the Cookies DB: Chromium's Cookies file is a live
# SQLite database that may be open (WAL mode) while Chromium runs; a raw file copy can capture a
# torn/inconsistent snapshot mid-write. sqlite3's `.backup` command drives the SQLite Online Backup
# API, which — per the SQLite docs — "does not need to be locked for the duration of the copy, only
# for the brief periods of time when it is actually being read from", i.e. safe against a live DB.
# Source: https://www.sqlite.org/backup.html ("Online Backup API" / "Other Backup Techniques").
# Falls back to a plain cp only if sqlite3 itself is unavailable or errors.
#
# Usage:
#   browser-state-backup.sh                                   # snapshot today -> state-backups/<date>/
#   browser-state-backup.sh --restore <YYYY-MM-DD> [profile]   # restore one date, all profiles or just one
#
# Restore safety: refuses to overwrite a profile's Cookies/Local State while a chromium process is
# currently bound to that profile dir (filesystem-level swap under a live process is unsafe — corrupts
# the open DB handle). For a LIVE browser, use session_vault.py restore instead (CDP-level cookie
# injection, safe while running). This script is the COLD fallback: profile directory lost/corrupted,
# disk full, or chromium not currently running for that profile.
set -uo pipefail

CLOAK_DIR="$HOME/.cloak"
PROFILES_DIR="$CLOAK_DIR/profiles"
BACKUP_ROOT="$CLOAK_DIR/state-backups"
mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT" 2>/dev/null || true

_log() { echo "$(date '+%F %T') browser-state-backup: $*" >&2; }

_profile_running() {
  # true if some chromium process currently has --user-data-dir=<profile_dir>
  pgrep -f "user-data-dir=$1" >/dev/null 2>&1
}

_backup_profile() {
  local profile_dir="$1" dest_dir="$2"
  local name; name="$(basename "$profile_dir")"
  local out="$dest_dir/$name"
  mkdir -p "$out"

  if [ -f "$profile_dir/Default/Cookies" ]; then
    if command -v sqlite3 >/dev/null 2>&1 && sqlite3 "$profile_dir/Default/Cookies" ".backup '$out/Cookies'"; then
      _log "cookies backed up (sqlite3 .backup): $name"
    else
      cp "$profile_dir/Default/Cookies" "$out/Cookies" \
        && _log "cookies backed up (cp fallback): $name" \
        || _log "WARN: cookie backup FAILED for $name"
    fi
  fi
  if [ -f "$profile_dir/Default/Login Data" ]; then
    if command -v sqlite3 >/dev/null 2>&1 && sqlite3 "$profile_dir/Default/Login Data" ".backup '$out/Login Data'"; then
      :
    else
      cp "$profile_dir/Default/Login Data" "$out/Login Data" || true
    fi
  fi
  [ -f "$profile_dir/Local State" ] && cp "$profile_dir/Local State" "$out/Local State"
}

do_dump() {
  local date_tag; date_tag="$(date '+%F')"
  local dest="$BACKUP_ROOT/$date_tag"
  mkdir -p "$dest/profiles"

  local count=0
  for p in "$PROFILES_DIR"/*/; do
    [ -d "$p" ] || continue
    _backup_profile "${p%/}" "$dest/profiles"
    count=$((count + 1))
  done

  if [ -d "$CLOAK_DIR/vault" ]; then
    mkdir -p "$dest/vault"
    rsync -a "$CLOAK_DIR/vault/" "$dest/vault/" || true
  fi

  mkdir -p "$dest/creds"
  find "$CLOAK_DIR" -maxdepth 1 -name "*.json" -exec rsync -a {} "$dest/creds/" \;
  chmod -R go-rwx "$dest" 2>/dev/null || true

  # Protected generations are preserved; cleanup never deletes ~/.cloak or memory.

  _log "dump complete: date=$date_tag profiles=$count dest=$dest"
  echo "{\"ok\": true, \"date\": \"$date_tag\", \"profiles_backed_up\": $count, \"dest\": \"$dest\"}"
}

do_restore() {
  local date_tag="$1" only_profile="${2:-}"
  local src="$BACKUP_ROOT/$date_tag"
  if [ ! -d "$src" ]; then
    echo "{\"ok\": false, \"reason\": \"no backup for $date_tag\"}"
    return 1
  fi
  local restored=0 skipped=0
  for p in "$src"/profiles/*/; do
    [ -d "$p" ] || continue
    local name; name="$(basename "${p%/}")"
    if [ -n "$only_profile" ] && [ "$name" != "$only_profile" ]; then continue; fi
    local live="$PROFILES_DIR/$name"
    if _profile_running "$live"; then
      _log "SKIP restore for $name: chromium currently running on this profile (use session_vault.py restore for a live-safe cookie push instead)"
      skipped=$((skipped + 1))
      continue
    fi
    mkdir -p "$live/Default"
    [ -f "$p/Cookies" ] && cp "$p/Cookies" "$live/Default/Cookies" && _log "restored cookies: $name"
    [ -f "$p/Login Data" ] && cp "$p/Login Data" "$live/Default/Login Data"
    [ -f "$p/Local State" ] && cp "$p/Local State" "$live/Local State"
    restored=$((restored + 1))
  done
  if [ -d "$src/vault" ]; then rsync -a "$src/vault/" "$CLOAK_DIR/vault/" || true; fi
  if [ -d "$src/creds" ]; then rsync -a "$src/creds/" "$CLOAK_DIR/" || true; fi
  _log "restore complete: date=$date_tag profiles_restored=$restored profiles_skipped_running=$skipped"
  echo "{\"ok\": true, \"date\": \"$date_tag\", \"profiles_restored\": $restored, \"profiles_skipped_running\": $skipped}"
}

case "${1:-}" in
--restore)
  do_restore "${2:?usage: --restore YYYY-MM-DD [profile-name]}" "${3:-}"
  ;;
*)
  do_dump
  ;;
esac
