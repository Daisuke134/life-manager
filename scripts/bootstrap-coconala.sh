#!/bin/bash
set -euo pipefail

# Share checkout validation and runtime selection with the public Mac entrypoint.
bootstrap="$(curl -fsSL https://raw.githubusercontent.com/Daisuke134/life-manager/main/scripts/bootstrap.sh)"
exec /bin/bash -c "$bootstrap" life-manager coconala "$@"
