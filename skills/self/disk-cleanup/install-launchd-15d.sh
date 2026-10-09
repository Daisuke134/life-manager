#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
HOME_DIR=${HOME:?HOME is required}
LABEL=com.anicca.disk-cleanup-15d
TARGET="$HOME_DIR/Library/LaunchAgents/$LABEL.plist"
TEMPLATE="$ROOT/skills/self/disk-cleanup/launchd/$LABEL.plist"
SCRIPT_SOURCE="$ROOT/bin/disk-cleanup-15d.sh"
SCRIPT="$HOME_DIR/.local/bin/disk-cleanup-15d.sh"
LOG_DIR="$HOME_DIR/.local/state/life-manager/life-manager-disk-cleanup/logs"
STDOUT_PATH="$LOG_DIR/maintenance-15d.out.log"
STDERR_PATH="$LOG_DIR/maintenance-15d.err.log"
LAUNCHCTL_SAFE="$ROOT/bin/launchctl-safe"
DOMAIN="gui/$(id -u)"
SCRIPT_TMP="$SCRIPT.tmp.$$"
PLIST_TMP="$TARGET.tmp.$$"
SCRIPT_BACKUP="$SCRIPT.backup.$$"
PLIST_BACKUP="$TARGET.backup.$$"
SCRIPT_RESTORE_TMP="$SCRIPT.restore.$$"
PLIST_RESTORE_TMP="$TARGET.restore.$$"
WAS_LOADED=0
HAVE_BACKUP=0
MUTATION_STARTED=0
INSTALL_COMMITTED=0
KEEP_BACKUPS=0

valid_job_list() {
  printf '%s\n' "$1" | awk '
    NR == 1 {
      if (NF != 3 || $1 != "PID" || $2 != "Status" || $3 != "Label") invalid = 1
      next
    }
    NF != 3 || ($1 != "-" && $1 !~ /^[0-9]+$/) ||
      ($2 != "-" && $2 !~ /^-?[0-9]+$/) || $3 == "" { invalid = 1 }
    NF == 3 { rows++ }
    END { if (NR < 1 || rows < 1 || invalid) exit 1 }
  '
}

job_list_has_label() {
  printf '%s\n' "$1" | awk -v label="$LABEL" \
    '$NF == label { found = 1 } END { exit !found }'
}

readback_matches() {
  printf '%s\n' "$1" | awk \
      -v expected="$2" -v expected_stdout="$3" \
      -v expected_stderr="$4" -v expected_interval="$5" '
    /^[[:space:]]*program = / {
      program = $0
      sub(/^[[:space:]]*program = /, "", program)
    }
    /^[[:space:]]*arguments = \{/ { in_args = 1; next }
    in_args && /^[[:space:]]*\}/ { in_args = 0; next }
    in_args {
      argument = $0
      sub(/^[[:space:]]+/, "", argument)
      if (argument != "") {
        argc++
        if (argc == 1) first_argument = argument
      }
    }
    /^[[:space:]]*stdout path = / {
      stdout_path = $0
      sub(/^[[:space:]]*stdout path = /, "", stdout_path)
    }
    /^[[:space:]]*stderr path = / {
      stderr_path = $0
      sub(/^[[:space:]]*stderr path = /, "", stderr_path)
    }
    /^[[:space:]]*run interval = / {
      run_interval = $0
      sub(/^[[:space:]]*run interval = /, "", run_interval)
    }
    END {
      if (program == expected && argc == 1 && first_argument == expected &&
          stdout_path == expected_stdout && stderr_path == expected_stderr &&
          run_interval == expected_interval " seconds") exit 0
      exit 1
    }
  '
}

previous_owner_still_loaded() {
  current_jobs=$("$LAUNCHCTL_SAFE" list) || return 1
  valid_job_list "$current_jobs" || return 1
  job_list_has_label "$current_jobs" || return 1
  current_readback=$("$LAUNCHCTL_SAFE" print "$DOMAIN/$LABEL") || return 1
  readback_matches "$current_readback" "$OLD_SCRIPT" "$OLD_STDOUT" \
    "$OLD_STDERR" "$OLD_INTERVAL"
}

rollback_previous() {
  rollback_jobs=$("$LAUNCHCTL_SAFE" list) || return 1
  valid_job_list "$rollback_jobs" || return 1
  if job_list_has_label "$rollback_jobs"; then
    "$LAUNCHCTL_SAFE" bootout "$DOMAIN/$LABEL" || return 1
  fi
  if [ "$HAVE_BACKUP" -eq 1 ]; then
    cp -p "$SCRIPT_BACKUP" "$SCRIPT_RESTORE_TMP" || return 1
    cp -p "$PLIST_BACKUP" "$PLIST_RESTORE_TMP" || return 1
    mv -f "$SCRIPT_RESTORE_TMP" "$SCRIPT" || return 1
    mv -f "$PLIST_RESTORE_TMP" "$TARGET" || return 1
    if [ "$WAS_LOADED" -eq 1 ]; then
      "$LAUNCHCTL_SAFE" bootstrap "$DOMAIN" "$TARGET" || return 1
      rollback_readback=$("$LAUNCHCTL_SAFE" print "$DOMAIN/$LABEL") || return 1
      readback_matches "$rollback_readback" "$OLD_SCRIPT" "$OLD_STDOUT" \
        "$OLD_STDERR" "$OLD_INTERVAL" || return 1
    fi
  fi
}

finish() {
  status=$?
  trap - EXIT HUP INT TERM
  rm -f "$SCRIPT_TMP" "$PLIST_TMP" "$SCRIPT_RESTORE_TMP" "$PLIST_RESTORE_TMP"
  if [ "$MUTATION_STARTED" -eq 1 ] && [ "$INSTALL_COMMITTED" -eq 0 ]; then
    if rollback_previous; then
      if [ "$HAVE_BACKUP" -eq 1 ] && [ "$WAS_LOADED" -eq 1 ]; then
        printf '%s\n' "15-day maintenance install failed; previous owner restored" >&2
      elif [ "$HAVE_BACKUP" -eq 1 ]; then
        printf '%s\n' "15-day maintenance install failed; previous files restored, owner remains unloaded" >&2
      else
        printf '%s\n' "15-day maintenance install failed; new owner unloaded, no prior owner existed" >&2
      fi
    else
      KEEP_BACKUPS=1
      if [ "$HAVE_BACKUP" -eq 1 ]; then
        printf '%s\n' "15-day maintenance rollback failed; inspect retained backups: $SCRIPT_BACKUP $PLIST_BACKUP" >&2
      else
        printf '%s\n' "15-day maintenance rollback failed and no prior owner backup exists" >&2
      fi
      status=1
    fi
  fi
  if [ "$KEEP_BACKUPS" -ne 1 ]; then
    rm -f "$SCRIPT_BACKUP" "$PLIST_BACKUP"
  fi
  exit "$status"
}

trap finish EXIT
trap 'exit 1' HUP INT TERM

"$LAUNCHCTL_SAFE" preflight >/dev/null || exit $?
LOADED_JOBS=$("$LAUNCHCTL_SAFE" list) || {
  printf '%s\n' "cannot verify loaded launchd jobs" >&2
  exit 1
}
if ! valid_job_list "$LOADED_JOBS"; then
  printf '%s\n' "launchd job list has an invalid format" >&2
  exit 1
fi
if job_list_has_label "$LOADED_JOBS"; then
  WAS_LOADED=1
fi
mkdir -p "$HOME_DIR/Library/LaunchAgents" "$HOME_DIR/.local/bin" \
  "$HOME_DIR/.local/state/life-manager/life-manager-disk-cleanup/logs"
cp "$SCRIPT_SOURCE" "$SCRIPT_TMP"
chmod 755 "$SCRIPT_TMP"
sed -e "s#__MAINTENANCE_15D_SCRIPT__#$SCRIPT#g" \
  -e "s#__HOME__#$HOME_DIR#g" "$TEMPLATE" > "$PLIST_TMP"
plutil -lint "$PLIST_TMP" >/dev/null

if [ -e "$SCRIPT" ] || [ -L "$SCRIPT" ] || [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  if [ ! -f "$SCRIPT" ] || [ -L "$SCRIPT" ] || [ ! -f "$TARGET" ] || [ -L "$TARGET" ]; then
    printf '%s\n' "existing 15-day owner files are incomplete or unsafe" >&2
    exit 1
  fi
  cp -p "$SCRIPT" "$SCRIPT_BACKUP"
  cp -p "$TARGET" "$PLIST_BACKUP"
  plutil -lint "$PLIST_BACKUP" >/dev/null
  OLD_SCRIPT=$(plutil -extract ProgramArguments.0 raw -o - "$PLIST_BACKUP")
  OLD_STDOUT=$(plutil -extract StandardOutPath raw -o - "$PLIST_BACKUP")
  OLD_STDERR=$(plutil -extract StandardErrorPath raw -o - "$PLIST_BACKUP")
  OLD_INTERVAL=$(plutil -extract StartInterval raw -o - "$PLIST_BACKUP")
  HAVE_BACKUP=1
elif [ "$WAS_LOADED" -eq 1 ]; then
  printf '%s\n' "loaded 15-day owner has no restorable files" >&2
  exit 1
fi
if [ "$WAS_LOADED" -eq 1 ]; then
  OLD_READBACK=$("$LAUNCHCTL_SAFE" print "$DOMAIN/$LABEL") || {
    printf '%s\n' "cannot read back existing 15-day owner" >&2
    exit 1
  }
  if ! readback_matches "$OLD_READBACK" "$OLD_SCRIPT" "$OLD_STDOUT" \
      "$OLD_STDERR" "$OLD_INTERVAL"; then
    printf '%s\n' "loaded 15-day owner differs from its installed plist" >&2
    exit 1
  fi
  MUTATION_STARTED=1
  if "$LAUNCHCTL_SAFE" bootout "$DOMAIN/$LABEL"; then
    :
  else
    bootout_status=$?
    if previous_owner_still_loaded; then
      MUTATION_STARTED=0
    fi
    exit "$bootout_status"
  fi
fi
MUTATION_STARTED=1
mv -f "$SCRIPT_TMP" "$SCRIPT"
mv -f "$PLIST_TMP" "$TARGET"

"$LAUNCHCTL_SAFE" bootstrap "$DOMAIN" "$TARGET"
READBACK=$("$LAUNCHCTL_SAFE" print "$DOMAIN/$LABEL") || {
  printf '%s\n' "15-day maintenance launchd readback failed" >&2
  exit 1
}
if ! readback_matches "$READBACK" "$SCRIPT" "$STDOUT_PATH" "$STDERR_PATH" 1296000; then
  printf '%s\n' "15-day maintenance launchd program/argv/log/interval readback mismatch" >&2
  exit 1
fi
INSTALL_COMMITTED=1
printf '%s\n' "$TARGET"
