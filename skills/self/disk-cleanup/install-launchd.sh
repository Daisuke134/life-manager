#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
HOME_DIR=${HOME:?HOME is required}
LABEL=com.anicca.disk-watchdog
TARGET="$HOME_DIR/Library/LaunchAgents/$LABEL.plist"
TEMPLATE="$ROOT/skills/self/disk-cleanup/launchd/$LABEL.plist"
WATCHDOG_SOURCE="$ROOT/bin/disk-watchdog.sh"
WATCHDOG_SCRIPT="$HOME_DIR/.local/bin/disk-watchdog.sh"
LAUNCHCTL_SAFE="$ROOT/bin/launchctl-safe"
DOMAIN="gui/$(id -u)"

"$LAUNCHCTL_SAFE" preflight >/dev/null || exit $?
LOADED_JOBS=$("$LAUNCHCTL_SAFE" list) || {
  printf '%s\n' "cannot verify loaded launchd jobs" >&2
  exit 1
}
if ! printf '%s\n' "$LOADED_JOBS" | awk '
  NR == 1 {
    if (NF != 3 || $1 != "PID" || $2 != "Status" || $3 != "Label") invalid = 1
    next
  }
  NF != 3 || ($1 != "-" && $1 !~ /^[0-9]+$/) ||
    ($2 != "-" && $2 !~ /^-?[0-9]+$/) || $3 == "" { invalid = 1 }
  NF == 3 { rows++ }
  END { if (NR < 1 || rows < 1 || invalid) exit 1 }
'; then
  printf '%s\n' "launchd job list has an invalid format" >&2
  exit 1
fi
if printf '%s\n' "$LOADED_JOBS" | awk -v label="$LABEL" \
    '$NF == label { found = 1 } END { exit !found }'; then
  "$LAUNCHCTL_SAFE" bootout "$DOMAIN/$LABEL"
fi

mkdir -p "$HOME_DIR/Library/LaunchAgents" "$HOME_DIR/.local/bin" \
  "$HOME_DIR/.local/state/life-manager/life-manager-disk-cleanup/logs"
WATCHDOG_TMP="$WATCHDOG_SCRIPT.tmp.$$"
PLIST_TMP="$TARGET.tmp.$$"
cp "$WATCHDOG_SOURCE" "$WATCHDOG_TMP"
chmod 755 "$WATCHDOG_TMP"
mv -f "$WATCHDOG_TMP" "$WATCHDOG_SCRIPT"
sed -e "s#__WATCHDOG_SCRIPT__#$WATCHDOG_SCRIPT#g" \
  -e "s#__HOME__#$HOME_DIR#g" "$TEMPLATE" > "$PLIST_TMP"
plutil -lint "$PLIST_TMP" >/dev/null
mv -f "$PLIST_TMP" "$TARGET"

"$LAUNCHCTL_SAFE" bootstrap "$DOMAIN" "$TARGET"
"$LAUNCHCTL_SAFE" kickstart "$DOMAIN/$LABEL"
READBACK=$("$LAUNCHCTL_SAFE" print "$DOMAIN/$LABEL") || {
  printf '%s\n' "watchdog launchd readback failed" >&2
  exit 1
}
if ! printf '%s\n' "$READBACK" | awk -v expected="$WATCHDOG_SCRIPT" '
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
  END {
    if (program == expected && argc == 1 && first_argument == expected) exit 0
    exit 1
  }
'; then
  printf '%s\n' "watchdog launchd program/argv readback mismatch" >&2
  exit 1
fi
printf '%s\n' "$TARGET"
