#!/usr/bin/env bash
# browser-guard.sh — the only supported way to reach a shared logged-in browser.
#
# Born from the 2026-07-26 collision: :9222 was a proxy onto the SAME browser as
# production :9223 (identical CDP browser UUID), so an "interactive" session and the
# gig loop drove one Chrome at once. Saves silently failed and the session burned.
#
# Contract:
#   acquire <identity>   -> stdout = CDP base URL, exit 0
#                           BUSY (someone holds it)          -> exit 9
#                           identity mismatch / not reachable -> exit 10
#   release <identity>   -> drop the lease
#   status  [identity]   -> JSON, exit 0
#
# BUSY is normal, not a crash: the caller skips this cycle and the next scheduled pass
# picks the work up. That is already how gig_single_instance.sh behaves for passes.
#
# No TTL by design. Liveness comes from the holder pid, not from a clock:
# tox-dev/filelock rejects lifetime-based locks (_api.py:501-530, issue #590) because a
# TTL can expire while the holder is still alive and hand one resource to two writers.
# flock(1) is not used either — macOS does not ship it, and an fd lock is process-scoped
# so it cannot span a caller's separate shell invocations. The lease is a lockfile
# claimed with O_EXCL carrying {host, pid}; a dead holder's lease is stolen, a live one
# is respected (trbs/pid create()/_inner_check(), with Chromium's hostname guard).
#
# The identity check is the part that would have caught the incident: after connecting,
# compare the CDP browser UUID against every other known endpoint. If two identities
# resolve to one browser, refuse — never "probably fine, continue".
set -uo pipefail

REGISTRY="${AI_BROWSER_REGISTRY:-$HOME/.config/ai/registry/browsers.toml}"
LEASE_DIR="${AI_BROWSER_LEASE_DIR:-$HOME/.cloak/leases}"
PY="${PY:-/opt/homebrew/bin/python3}"
[ -x "$PY" ] || PY=python3
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RESOLVER="${AI_BROWSER_ENDPOINT_RESOLVER:-$HERE/resolve_cdp_endpoint.py}"

# Matches gig_single_instance.sh: a holder that neither released nor refreshed within
# this window is presumed crashed. Long jobs call `beat` to stay owner.
STALE_SECONDS="${AI_BROWSER_STALE_SECONDS:-1800}"

EXIT_BUSY=9
EXIT_IDENTITY=10
EXIT_USAGE=64

usage() { echo "usage: $0 {acquire|beat|release|status} [identity]" >&2; exit "$EXIT_USAGE"; }
[ "$#" -ge 1 ] || usage
CMD="$1"; IDENTITY="${2:-}"

mkdir -p "$LEASE_DIR"

# ---- registry lookup (minimal TOML read; no third-party deps) -----------------
lookup() {
  "$PY" - "$REGISTRY" "$1" <<'PYEOF'
import json, re, sys, os
registry, want = sys.argv[1], sys.argv[2]
try:
    text = open(os.path.expanduser(registry), encoding="utf-8").read()
except OSError:
    print(json.dumps({"error": "registry_unreadable"})); raise SystemExit(0)
blocks = text.split("[[identity]]")[1:]
for block in blocks:
    def field(name):
        m = re.search(rf'^{name}\s*=\s*"([^"]*)"', block, re.M)
        return m.group(1) if m else None
    def num(name):
        m = re.search(rf'^{name}\s*=\s*(\d+)', block, re.M)
        return int(m.group(1)) if m else None
    if field("id") == want:
        print(json.dumps({
            "id": want,
            "profile": os.path.expanduser(field("profile") or ""),
            "owner": field("owner"),
            "declared_port": num("declared_port"),
        }))
        raise SystemExit(0)
print(json.dumps({"error": "unknown_identity"}))
PYEOF
}

# Fail closed when this port is really another identity's browser AND we are the one
# piggybacking. Duplicate UUIDs are never allowed: registry identities must be one-to-one
# with browser processes, even when one of them is the legitimate process.
assert_not_piggybacked() {
  local want_id="$1" uuid="$2"
  [ -n "$uuid" ] || return 0
  all_json="$($PY "$RESOLVER" --registry "$REGISTRY" --all 2>/dev/null)" || return 0
  "$PY" -c 'import json,sys
rows=json.loads(sys.argv[1]).get("identities") or []
want_id,want_uuid=sys.argv[2],sys.argv[3]
for row in rows:
    if row.get("identity") != want_id and row.get("uuid") == want_uuid:
        print("PIGGYBACK {}@{}".format(row.get("identity"), row.get("endpoint")))
        raise SystemExit(1)
raise SystemExit(0)' "$all_json" "$want_id" "$uuid"
}

case "$CMD" in
  acquire)
    [ -n "$IDENTITY" ] || usage
    info="$(lookup "$IDENTITY")"
    case "$info" in *unknown_identity*|*registry_unreadable*)
      echo "guard: $info" >&2; exit "$EXIT_IDENTITY" ;;
    esac
    resolved="$($PY "$RESOLVER" --registry "$REGISTRY" --identity "$IDENTITY" 2>/dev/null)" || {
      echo "guard: CDP endpoint unavailable for $IDENTITY" >&2; exit "$EXIT_IDENTITY"; }
    endpoint_url="$($PY -c 'import json,sys; print(json.loads(sys.argv[1])["endpoint"])' "$resolved")"
    port="$($PY -c 'import json,sys; print(json.loads(sys.argv[1])["port"])' "$resolved")"
    uuid="$($PY -c 'import json,sys; print(json.loads(sys.argv[1])["uuid"])' "$resolved")"
    [ -n "$uuid" ] || { echo "guard: CDP endpoint has no browser UUID for $IDENTITY" >&2; exit "$EXIT_IDENTITY"; }

    if msg="$(assert_not_piggybacked "$IDENTITY" "$uuid")"; then :; else
      echo "guard: $IDENTITY at :$port resolves to $msg — refusing (identity collision)" >&2
      exit "$EXIT_IDENTITY"
    fi

    lease="$LEASE_DIR/$(printf '%s' "$IDENTITY" | tr '/:' '__').lease"
    # Lockfile + holder identity + pid liveness, NOT flock(1). Two reasons, both learned
    # the hard way: macOS ships no flock(1) (the first version silently fell through to
    # BUSY), and an fd lock is process-scoped so it cannot span a caller's separate shell
    # invocations — gig_single_instance.sh documents exactly this. The shape is trbs/pid's
    # create()/_inner_check(): claim atomically with O_EXCL, and if a lease already exists,
    # a dead holder's lease is stolen while a live holder's is respected. Holder identity
    # includes the hostname, mirroring Chromium's ProcessSingleton, so a lease written on
    # another machine is never assumed dead.
    if ! "$PY" - "$lease" "$IDENTITY" "$port" "$uuid" "${AI_BROWSER_HOLDER_PID:-$PPID}" "$(hostname -s)" "$STALE_SECONDS" <<'PYEOF'
import json, os, sys, time
lease, identity, port, uuid, pid, host, stale = sys.argv[1:8]
stale = int(stale)
payload = json.dumps({"identity": identity, "pid": int(pid), "host": host,
                      "port": int(port), "uuid": uuid,
                      "acquired_at": int(time.time())}, ensure_ascii=False)

def pid_alive(p, h):
    if h != host:
        return True                      # another machine: never presume it died
    try:
        os.kill(int(p), 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True                      # exists, just not ours

def claim():
    fd = os.open(lease, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(payload + "\n")

try:
    claim()
    raise SystemExit(0)
except FileExistsError:
    pass

try:
    held = json.loads(open(lease, encoding="utf-8").read().strip().splitlines()[-1])
except Exception:
    held = None

if held:
    age = time.time() - float(held.get("acquired_at") or 0)
    # Two independent liveness signals, because neither alone is sufficient here:
    #   * a live holder pid means a long-running wrapper still owns the browser;
    #   * a fresh timestamp covers the agent case, where the acquiring shell exits
    #     immediately and its pid is dead within milliseconds. gig_single_instance.sh
    #     hit exactly this and chose timestamps for the same reason.
    if pid_alive(held.get("pid"), held.get("host", host)) or age < stale:
        print(json.dumps(held, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)

os.unlink(lease)                         # holder is gone and the lease is stale
try:
    claim()
except FileExistsError:
    raise SystemExit(1)                  # someone beat us in the gap: treat as busy
raise SystemExit(0)
PYEOF
    then
      echo "guard: BUSY — $IDENTITY held by $(tail -1 "$lease" 2>/dev/null)" >&2
      exit "$EXIT_BUSY"
    fi
    echo "$endpoint_url"
    exit 0 ;;

  beat)
    # Refresh the timestamp so a long-running holder is not presumed crashed.
    [ -n "$IDENTITY" ] || usage
    lease="$LEASE_DIR/$(printf '%s' "$IDENTITY" | tr '/:' '__').lease"
    "$PY" - "$lease" <<'PYEOF' || true
import json, sys, time
lease = sys.argv[1]
try:
    row = json.loads(open(lease, encoding="utf-8").read().strip().splitlines()[-1])
except Exception:
    raise SystemExit(0)
row["acquired_at"] = int(time.time())
open(lease, "w", encoding="utf-8").write(json.dumps(row, ensure_ascii=False) + "\n")
PYEOF
    echo "BEAT $IDENTITY"
    exit 0 ;;

  release)
    [ -n "$IDENTITY" ] || usage
    lease="$LEASE_DIR/$(printf '%s' "$IDENTITY" | tr '/:' '__').lease"
    rm -f "$lease" 2>/dev/null || true
    echo "RELEASED $IDENTITY"
    exit 0 ;;

  status)
    all_json="$($PY "$RESOLVER" --registry "$REGISTRY" --all 2>/dev/null)" || {
      echo '{"identities":[],"collisions":{}}'; exit 0;
    }
    "$PY" -c 'import json,os,sys
rows=json.loads(sys.argv[1]).get("identities") or []
lease_dir,only=sys.argv[2],sys.argv[3]
selected=[]
for row in rows:
    identity=row.get("identity")
    if not identity or (only and identity != only): continue
    lease=os.path.join(os.path.expanduser(lease_dir),identity.replace("/","_").replace(":","_")+".lease")
    holder=""
    if os.path.exists(lease): holder=(open(lease,encoding="utf-8").read().strip().splitlines() or [""])[-1]
    row=dict(row); row["holder"]=holder; selected.append(row)
by_uuid={}
for row in selected:
    if row.get("uuid"): by_uuid.setdefault(row["uuid"],[]).append(row["identity"])
collisions={uuid:ids for uuid,ids in by_uuid.items() if len(ids)>1}
print(json.dumps({"identities":selected,"collisions":collisions},ensure_ascii=False))' \
      "$all_json" "$LEASE_DIR" "${IDENTITY:-}"
    exit 0 ;;

  *) usage ;;
esac
