#!/usr/bin/env bash
set -euo pipefail

# 同時ビルドを停止
pkill -f "xcodebuild" || true

# 該当DerivedDataのみ削除（パスはXcodeログのderived名に合わせる）
DD_BASE="$HOME/Library/Developer/Xcode/DerivedData"
rm -rf "$DD_BASE/aniccaios-"*/Build/Intermediates.noindex/XCBuildData/build.db* || true
rm -rf "$DD_BASE/aniccaios-"*/Index.noindex || true

echo "✅ Cleaned locked build database and index."

