# Sourced by publish_prepare.sh and publish_finish.sh. Dais 2026-10-08: an Agent in
# skills/capafy/FROZEN.json is never prepared or submitted by the factory, whatever
# the reason (UPDATE.json, resumed draft, exception note). Only Dais edits it by hand.
capafy_refuse_frozen() {
  local frozen_file id
  frozen_file="${CAPAFY_FROZEN_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../capafy" && pwd)/FROZEN.json}"
  [ -f "$frozen_file" ] || return 0
  for id in "$@"; do
    [ -n "$id" ] || continue
    if python3 -c 'import json,sys; sys.exit(0 if sys.argv[2] in {str(a) for a in json.load(open(sys.argv[1])).get("agent_ids") or []} else 1)' "$frozen_file" "$id"; then
      echo "FROZEN_AGENT_REFUSED agent_id=$id (skills/capafy/FROZEN.json)" >&2
      exit 3
    fi
  done
}
