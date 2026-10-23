#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/runtime-paths.sh"

MODE="${1:-all}"
case "$MODE" in
  all)
    NAMES=(
      ai.anicca.job-search-browser
      ai.anicca.job-search-daily
      ai.anicca.job-search-inbox
      ai.anicca.job-search-learning
      ai.anicca.job-search-health
      ai.anicca.job-search-mercor
      ai.anicca.job-search-mercor-browser
    )
    ;;
  --browser-only)
    NAMES=(ai.anicca.job-search-browser)
    ;;
  --mercor-only)
    NAMES=(ai.anicca.job-search-mercor)
    ;;
  --mercor-browser-only)
    NAMES=(ai.anicca.job-search-mercor-browser)
    ;;
  *)
    print -u2 "install-launchd: usage: $0 [--browser-only|--mercor-only|--mercor-browser-only]"
    exit 2
    ;;
esac

MERCOR_PROFILE="${JOB_SEARCH_MERCOR_BROWSER_PROFILE:-$HOME/.cloak/profiles/job-search-mercor}"
MERCOR_PORT="${JOB_SEARCH_MERCOR_BROWSER_PORT:-9334}"
MERCOR_FINGERPRINT="${JOB_SEARCH_MERCOR_BROWSER_FINGERPRINT:-81234}"
MERCOR_STATE_NAME="mercor-browser"
if [[ "$MODE" == "--mercor-browser-only" || "$MODE" == "all" ]]; then
  if [[ "$MERCOR_PROFILE" != /* ]]; then
    print -u2 "install-launchd: Mercor browser profile must be absolute"
    exit 2
  fi
  MERCOR_DAILY_PROFILE="$HOME/.cloak/profiles/job-search-daily"
  if [[ "${MERCOR_PROFILE:A}" == "${MERCOR_DAILY_PROFILE:A}" ]]; then
    print -u2 "install-launchd: Mercor browser profile cannot be the daily browser profile"
    exit 2
  fi
  if [[ ! "$MERCOR_PORT" =~ '^[0-9]+$' ]]; then
    print -u2 "install-launchd: invalid Mercor browser port"
    exit 2
  fi
  if (( 10#$MERCOR_PORT < 1 || 10#$MERCOR_PORT > 65535 )); then
    print -u2 "install-launchd: invalid Mercor browser port"
    exit 2
  fi
  if (( 10#$MERCOR_PORT == 9222 )); then
    print -u2 "install-launchd: Mercor browser port cannot be 9222"
    exit 2
  fi
  if [[ ! "$MERCOR_FINGERPRINT" =~ '^[0-9]+$' ]]; then
    print -u2 "install-launchd: invalid Mercor browser fingerprint"
    exit 2
  fi
fi

UID_VALUE="$(id -u)"
mkdir -p "$JOB_SEARCH_LAUNCH_AGENT_DIR" "$JOB_SEARCH_STATE_ROOT/logs"
chmod 700 "$JOB_SEARCH_STATE_ROOT" "$JOB_SEARCH_STATE_ROOT/logs"

for name in "${NAMES[@]}"; do
  template="$JOB_SEARCH_APP_ROOT/launchd/$name.plist"
  installed="$JOB_SEARCH_LAUNCH_AGENT_DIR/$name.plist"
  program="${name##*-}"
  log_program="${name#ai.anicca.job-search-}"
  "$JOB_SEARCH_PYTHON" - \
    "$template" "$installed" \
    "$JOB_SEARCH_APP_ROOT/scripts/run-$program.sh" \
    "$JOB_SEARCH_STATE_ROOT/logs/$log_program.out.log" \
    "$JOB_SEARCH_STATE_ROOT/logs/$log_program.err.log" \
    "$MODE" "$MERCOR_PROFILE" "$MERCOR_PORT" "$MERCOR_FINGERPRINT" \
    "$MERCOR_STATE_NAME" <<'PY'
import os
import plistlib
import sys
from pathlib import Path

template, output, program, stdout, stderr, mode, profile, port, fingerprint, state_name = sys.argv[1:]
template, output, program, stdout, stderr = map(
    Path, (template, output, program, stdout, stderr)
)
value = plistlib.loads(template.read_bytes())
value["ProgramArguments"] = [str(program)]
value["StandardOutPath"] = str(stdout)
value["StandardErrorPath"] = str(stderr)
if template.name == "ai.anicca.job-search-mercor-browser.plist":
    value["EnvironmentVariables"] = {
        "JOB_SEARCH_BROWSER_PROFILE": profile,
        "JOB_SEARCH_BROWSER_PORT": port,
        "JOB_SEARCH_BROWSER_FINGERPRINT": fingerprint,
        "JOB_SEARCH_BROWSER_STATE_NAME": state_name,
    }
temporary = output.with_suffix(".plist.tmp")
temporary.write_bytes(plistlib.dumps(value, sort_keys=False))
os.chmod(temporary, 0o644)
temporary.replace(output)
PY
  "$JOB_SEARCH_PLUTIL" -lint "$installed" >/dev/null
done

if [[ "${JOB_SEARCH_SKIP_LAUNCHCTL:-0}" != "1" ]]; then
  for name in "${NAMES[@]}"; do
    "$JOB_SEARCH_LAUNCHCTL" bootout "gui/$UID_VALUE/$name" 2>/dev/null || true
    "$JOB_SEARCH_LAUNCHCTL" bootstrap \
      "gui/$UID_VALUE" "$JOB_SEARCH_LAUNCH_AGENT_DIR/$name.plist"
  done
fi
