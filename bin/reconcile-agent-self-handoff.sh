#!/usr/bin/env bash
set -euo pipefail

parent_pid=""
old_service=""
helper_service=""
target_plist=""
installed_plist=""
handoff_plist=""
receipt_path=""
launchctl_safe=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --parent-pid) parent_pid="${2:-}"; shift 2 ;;
    --old-service) old_service="${2:-}"; shift 2 ;;
    --helper-service) helper_service="${2:-}"; shift 2 ;;
    --target-plist) target_plist="${2:-}"; shift 2 ;;
    --installed-plist) installed_plist="${2:-}"; shift 2 ;;
    --handoff-plist) handoff_plist="${2:-}"; shift 2 ;;
    --receipt) receipt_path="${2:-}"; shift 2 ;;
    --launchctl) launchctl_safe="${2:-}"; shift 2 ;;
    *) exit 64 ;;
  esac
done
case "$parent_pid" in ''|*[!0-9]*) exit 64 ;; esac
[ -n "$old_service" ] && [ -n "$helper_service" ] && [ -f "$target_plist" ] \
  && [ -n "$handoff_plist" ] && [ -n "$receipt_path" ] && [ -x "$launchctl_safe" ] || exit 69
[ -n "$installed_plist" ] || installed_plist="$target_plist"

runtime_python="${LIFE_MANAGER_RUNTIME_PYTHON:-$(command -v python3 || true)}"
if [ -n "$runtime_python" ] && [[ "$runtime_python" != /* ]]; then
  runtime_python="$(command -v "$runtime_python" || true)"
fi
[ -n "$runtime_python" ] && [ -x "$runtime_python" ] || exit 69
domain="gui/$(id -u)"
wait_seconds="${LIFE_MANAGER_SELF_HANDOFF_WAIT_SECONDS:-120}"
case "$wait_seconds" in ''|*[!0-9]*) exit 64 ;; esac
lock_wait_seconds="${LIFE_MANAGER_RECONCILER_HANDOFF_LOCK_WAIT_SECONDS:-2400}"
case "$lock_wait_seconds" in ''|*[!0-9]*) exit 64 ;; esac
script_root="$(cd "$(dirname "$0")/.." && pwd -P)"
readback_file="$(mktemp "${TMPDIR:-/tmp}/lm-reconciler-handoff-readback.XXXXXX")"
run_lock_holder_pid=""
run_lock_status_path=""

release_run_lock() {
  if [ -n "$run_lock_holder_pid" ]; then
    kill "$run_lock_holder_pid" 2>/dev/null || true
    wait "$run_lock_holder_pid" 2>/dev/null || true
    run_lock_holder_pid=""
  fi
  if [ -n "$run_lock_status_path" ]; then
    rm -f "$run_lock_status_path"
    run_lock_status_path=""
  fi
}

trap 'release_run_lock; rm -f "$readback_file"' EXIT

write_receipt() {
  RECEIPT_PATH="$receipt_path" STATUS="$1" ERROR_DETAIL="${2:-}" \
    TARGET_PLIST="$target_plist" OLD_SERVICE="$old_service" HELPER_SERVICE="$helper_service" \
    PARENT_PID="$parent_pid" READBACK_FILE="$readback_file" \
    RUN_LOCK_STATUS_PATH="$run_lock_status_path" \
    OLD_SERVICE_STATE="${old_state:-}" OLD_SERVICE_PID="${old_pid:-}" \
    "$runtime_python" - <<'PY'
import json, os, pathlib, plistlib, tempfile, time
try:
    plist = plistlib.loads(pathlib.Path(os.environ["TARGET_PLIST"]).read_bytes())
except Exception:
    plist = {}
readback = {}
try:
    readback = json.loads(pathlib.Path(os.environ["READBACK_FILE"]).read_text())
except Exception:
    pass
run_lock = {}
try:
    run_lock = json.loads(pathlib.Path(os.environ["RUN_LOCK_STATUS_PATH"]).read_text())
except (OSError, ValueError, KeyError):
    pass
old_pid = os.environ.get("OLD_SERVICE_PID", "")
receipt = {
    "schema_version": 1,
    "schema": "life-manager.reconciler.self-handoff.v1",
    "status": os.environ["STATUS"],
    "error": os.environ.get("ERROR_DETAIL") or None,
    "old_service": os.environ["OLD_SERVICE"],
    "helper_service": os.environ["HELPER_SERVICE"],
    "parent_pid": int(os.environ["PARENT_PID"]),
    "old_service_state": os.environ.get("OLD_SERVICE_STATE") or None,
    "old_service_pid": int(old_pid) if old_pid.isdigit() and int(old_pid) > 1 else None,
    "run_lock": run_lock or None,
    "target_release_sha": (plist.get("EnvironmentVariables") or {}).get("LIFE_MANAGER_RELEASE_SHA"),
    "target_arguments": list(map(str, plist.get("ProgramArguments") or [])),
    "readback": readback,
    "recorded_at": time.time(),
}
path = pathlib.Path(os.environ["RECEIPT_PATH"])
path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(receipt, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
finally:
    pathlib.Path(temp).unlink(missing_ok=True)
PY
}

if [ "$parent_pid" -ne 0 ]; then
  deadline=$(( $(date -u +%s) + wait_seconds ))
  while kill -0 "$parent_pid" 2>/dev/null; do
    [ "$(date -u +%s)" -lt "$deadline" ] || { write_receipt failed "parent_timeout"; exit 75; }
    sleep 0.25
  done
fi

"$launchctl_safe" preflight >/dev/null 2>&1 || { write_receipt failed "preflight_failed"; exit 69; }

fail_handoff() {
  local reason="$1" exit_code="$2"
  write_receipt failed "$reason"
  release_run_lock
  rm -f "$handoff_plist"
  "$launchctl_safe" bootout "$domain/$helper_service" >/dev/null 2>&1 || true
  exit "$exit_code"
}

# Use the exact per-label lock held by lm-loop-run so a scheduled run cannot begin
# between the final idle readback and bootout. Keep this process alive through the
# target release SHA/argv readback below; its exclusive flock is the handoff barrier.
run_lock_status_path="$(mktemp "${TMPDIR:-/tmp}/lm-reconciler-handoff-lock.XXXXXX")"
PYTHONPATH="$script_root${PYTHONPATH:+:$PYTHONPATH}" "$runtime_python" \
  "$script_root/runtime/loop/reconciler_handoff_run_lock.py" \
  --label "$old_service" --status-path "$run_lock_status_path" \
  --parent-pid "$$" --timeout-seconds "$lock_wait_seconds" &
run_lock_holder_pid=$!
while :; do
  lock_state="pending"
  if [ -s "$run_lock_status_path" ]; then
    lock_state="$("$runtime_python" - "$run_lock_status_path" 2>/dev/null <<'PY'
import json, pathlib, sys
try:
    value = json.loads(pathlib.Path(sys.argv[1]).read_text())
    state = value.get("status")
    print(state if isinstance(state, str) else "unknown")
except (OSError, ValueError):
    print("unknown")
PY
    )"
  fi
  case "$lock_state" in
    acquired) break ;;
    pending) ;;
    timeout) fail_handoff "handoff_run_lock_timeout" 75 ;;
    *) fail_handoff "handoff_run_lock_${lock_state}" 69 ;;
  esac
  kill -0 "$run_lock_holder_pid" 2>/dev/null || fail_handoff "handoff_run_lock_holder_exited" 69
  sleep 0.2
done

# The helper's parent can be the short-lived handoff watcher, not the old reconciler
# process. Read the actual service state while holding the same per-label lock.
deadline=$(( $(date -u +%s) + wait_seconds ))
idle_observations=0
old_service_was_absent=0
while :; do
  old_detail=""
  old_rc=0
  old_detail="$($launchctl_safe print "$domain/$old_service" 2>&1)" || old_rc=$?
  if [ "$old_rc" -ne 0 ]; then
    if printf '%s' "$old_detail" | grep -Eqi 'could not find service|service not found|absent'; then
      old_service_was_absent=1
      old_state="not_loaded"
      old_pid=""
      break
    fi
    fail_handoff "old_service_readback_failed" 69
  fi
  old_state="$(printf '%s\n' "$old_detail" | sed -nE 's/^[[:space:]]*state = ([[:alnum:]_-]+)[[:space:]]*$/\1/p' | head -n 1)"
  old_pid="$(printf '%s\n' "$old_detail" | sed -nE 's/^[[:space:]]*pid = ([0-9]+)[[:space:]]*$/\1/p' | head -n 1)"
  case "$old_state" in
    waiting|idle)
      if [ -n "$old_pid" ]; then
        case "$old_pid" in
          0|1|*[!0-9]*)
            fail_handoff "old_service_pid_invalid" 69
            ;;
        esac
      fi
      if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
        idle_observations=0
      else
        idle_observations=$((idle_observations + 1))
        [ "$idle_observations" -ge 2 ] && break
      fi
      ;;
    running)
      case "$old_pid" in
        ''|0|1|*[!0-9]*)
          fail_handoff "old_service_running_pid_missing" 69
          ;;
      esac
      idle_observations=0
      ;;
    *)
      fail_handoff "old_service_state_unknown" 69
      ;;
  esac
  [ "$(date -u +%s)" -lt "$deadline" ] || {
    fail_handoff "old_service_active_timeout" 75
  }
  sleep 1
done

if [ "$old_service_was_absent" -eq 0 ]; then
  "$launchctl_safe" bootout "$domain/$old_service" >/dev/null 2>&1 \
    || fail_handoff "old_bootout_failed" 1

  old_absent=0
  for _ in $(seq 1 50); do
    detail=""
    rc=0
    detail="$($launchctl_safe print "$domain/$old_service" 2>&1)" || rc=$?
    if [ "$rc" -ne 0 ] && printf '%s' "$detail" | grep -Eqi 'could not find service|service not found|absent'; then
      old_absent=1
      break
    fi
    sleep 0.1
  done
  [ "$old_absent" -eq 1 ] || fail_handoff "old_still_loaded" 1
fi

if [ "$target_plist" != "$installed_plist" ]; then
  mv "$target_plist" "$installed_plist"
  target_plist="$installed_plist"
fi

"$launchctl_safe" bootstrap "$domain" "$target_plist" >/dev/null 2>&1 \
  || fail_handoff "target_bootstrap_failed" 1

target_detail=""
target_rc=0
target_detail="$($launchctl_safe print "$domain/$old_service" 2>&1)" || target_rc=$?
[ "$target_rc" -eq 0 ] || fail_handoff "target_readback_failed" 1
if ! TARGET_DETAIL="$target_detail" TARGET_PLIST="$target_plist" "$runtime_python" - <<'PY' >"$readback_file"
import json, os, pathlib, plistlib
plist = plistlib.loads(pathlib.Path(os.environ["TARGET_PLIST"]).read_bytes())
expected = list(map(str, plist.get("ProgramArguments") or []))
expected_sha = (plist.get("EnvironmentVariables") or {}).get("LIFE_MANAGER_RELEASE_SHA")
text = os.environ["TARGET_DETAIL"]
section = None
arguments = []
environment = {}
for raw in text.splitlines():
    line = raw.strip()
    if line in {"arguments = {", "environment = {"}:
        section = line.split()[0]
        continue
    if section and line == "}":
        section = None
        continue
    if section == "arguments" and line:
        arguments.append(line)
    elif section == "environment" and " => " in line:
        key, value = line.split(" => ", 1)
        environment[key] = value
actual_sha = environment.get("LIFE_MANAGER_RELEASE_SHA")
if arguments != expected or actual_sha != expected_sha:
    raise SystemExit("target readback mismatch")
print(json.dumps({"verified": True, "loaded_arguments": arguments,
                  "loaded_release_sha": actual_sha}, sort_keys=True))
PY
then
  fail_handoff "target_readback_mismatch" 69
fi

write_receipt ok ""
rm -f "$handoff_plist"
"$launchctl_safe" bootout "$domain/$helper_service" >/dev/null 2>&1 || true
