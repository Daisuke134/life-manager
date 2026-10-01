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
readback_file="$(mktemp "${TMPDIR:-/tmp}/lm-reconciler-handoff-readback.XXXXXX")"
trap 'rm -f "$readback_file"' EXIT

write_receipt() {
  RECEIPT_PATH="$receipt_path" STATUS="$1" ERROR_DETAIL="${2:-}" \
    TARGET_PLIST="$target_plist" OLD_SERVICE="$old_service" HELPER_SERVICE="$helper_service" \
    PARENT_PID="$parent_pid" READBACK_FILE="$readback_file" "$runtime_python" - <<'PY'
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
receipt = {
    "schema_version": 1,
    "schema": "life-manager.reconciler.self-handoff.v1",
    "status": os.environ["STATUS"],
    "error": os.environ.get("ERROR_DETAIL") or None,
    "old_service": os.environ["OLD_SERVICE"],
    "helper_service": os.environ["HELPER_SERVICE"],
    "parent_pid": int(os.environ["PARENT_PID"]),
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
"$launchctl_safe" bootout "$domain/$old_service" >/dev/null 2>&1 || { write_receipt failed "old_bootout_failed"; exit 1; }

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
[ "$old_absent" -eq 1 ] || { write_receipt failed "old_still_loaded"; exit 1; }

if [ "$target_plist" != "$installed_plist" ]; then
  mv "$target_plist" "$installed_plist"
  target_plist="$installed_plist"
fi

"$launchctl_safe" bootstrap "$domain" "$target_plist" >/dev/null 2>&1 \
  || { write_receipt failed "target_bootstrap_failed"; exit 1; }

target_detail=""
target_rc=0
target_detail="$($launchctl_safe print "$domain/$old_service" 2>&1)" || target_rc=$?
[ "$target_rc" -eq 0 ] || { write_receipt failed "target_readback_failed"; exit 1; }
TARGET_DETAIL="$target_detail" TARGET_PLIST="$target_plist" "$runtime_python" - <<'PY' >"$readback_file"
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

write_receipt ok ""
rm -f "$handoff_plist"
"$launchctl_safe" bootout "$domain/$helper_service" >/dev/null 2>&1 || true
