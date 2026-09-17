#!/bin/bash
set -euo pipefail
DERIVED_SDK_PATH="${DERIVED_DATA_DIR}/SourcePackages/checkouts/webrtc/src/sdk/objc"
DEST="${SRCROOT}/aniccaios/WebRTCShims"
if [ -d "${DERIVED_SDK_PATH}" ]; then
  rsync -a --delete "${DERIVED_SDK_PATH}/" "${DEST}/objc/"
else
  echo "⚠️ WebRTC checkout not found yet; skipping header sync."
fi


