#!/bin/sh
set -eu
umask 077

if [ -z "${ANICCA_PRODUCTION_XCCONFIG_B64:-}" ]; then
  printf '%s\n' 'Missing Xcode Cloud secret ANICCA_PRODUCTION_XCCONFIG_B64' >&2
  exit 1
fi

app_dir=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
config_dir="$app_dir/Configs"
mkdir -p "$config_dir"
config_file=$(mktemp "$config_dir/.Production.xcconfig.XXXXXX")
trap 'rm -f "$config_file"' EXIT

printf '%s' "$ANICCA_PRODUCTION_XCCONFIG_B64" | /usr/bin/base64 --decode > "$config_file"
if [ ! -s "$config_file" ]; then
  printf '%s\n' 'Decoded production configuration is empty' >&2
  exit 1
fi

chmod 600 "$config_file"
mv -f "$config_file" "$config_dir/Production.xcconfig"
