#!/usr/bin/env bash
set -euo pipefail

# Run against a real simulator build; configuration is supplied privately by CI.
app_dir=$(cd "$(dirname "$0")/.." && pwd)
cd "$app_dir"
evidence_dir=${1:?Usage: run-soft-paywall-maestro.sh EVIDENCE_DIRECTORY}
mkdir -p "$evidence_dir/frames"
evidence_dir=$(cd "$evidence_dir" && pwd)
derived_dir=${RUNNER_TEMP:-/tmp}/anicca-soft-paywall-derived
simulator_id=$(xcrun simctl list devices available -j | python3 -c '
import json,sys
# iOS 18.4-18.5 cannot load sandbox products (RevenueCat FB17105187).
# Bind this to the Xcode 26.2 SDK selected by the real E2E job.
for runtime, devices in json.load(sys.stdin)["devices"].items():
    if runtime != "com.apple.CoreSimulator.SimRuntime.iOS-26-2":
        continue
    for device in devices:
        if device.get("isAvailable") and "iPhone" in device["name"]:
            print(device["udid"])
            sys.exit(0)
sys.exit("No available iOS 26.2 iPhone simulator for real StoreKit products")
')
xcrun simctl boot "$simulator_id"
xcrun simctl bootstatus "$simulator_id" -b
xcrun simctl status_bar "$simulator_id" override --time '9:41' --batteryState charged --batteryLevel 100

# Keep full build output off the console; preserve diagnostics on failure.
build_log=${RUNNER_TEMP:-/tmp}/anicca-soft-paywall-build.log
set +e
xcodebuild build -project aniccaios.xcodeproj -scheme aniccaios \
    -configuration Release -destination "platform=iOS Simulator,id=$simulator_id" \
    -derivedDataPath "$derived_dir" CODE_SIGNING_ALLOWED=NO \
    > "$build_log" 2>&1
build_result=$?
if [[ "$build_result" != 0 ]]; then
    cp "$build_log" "$evidence_dir/anicca-soft-paywall-build.log" || \
        printf '%s\n' 'Could not copy the build log into the evidence directory.' >&2
    printf '%s\n' '----- compiler errors -----'
    grep -E 'error:|fatal error:|\*\* BUILD (FAILED|SUCCEEDED)' "$build_log" | head -80 || true
    printf '%s\n' '----- build summary -----'
    tail -40 "$build_log"
    exit "$build_result"
fi
set -e
xcrun simctl install "$simulator_id" "$derived_dir/Build/Products/Release-iphonesimulator/aniccaios.app"

export MAESTRO_CLI_NO_ANALYTICS=1
maestro --version > "$evidence_dir/maestro-version.txt"
xcodebuild -version > "$evidence_dir/xcode-version.txt"
xcrun simctl list devices available -j > "$evidence_dir/simulators.json"
export SOFT_PAYWALL_SIMULATOR_ID="$simulator_id"
export SOFT_PAYWALL_EVIDENCE_DIR="$evidence_dir"
python3 - <<'PY'
import datetime, json, os, pathlib, subprocess
evidence = pathlib.Path(os.environ['SOFT_PAYWALL_EVIDENCE_DIR'])
metadata = {
    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'simulator_id': os.environ['SOFT_PAYWALL_SIMULATOR_ID'],
    'flow': 'maestro/v1.9.14/01-soft-paywall.yaml',
    'flows_in_recording_order': [
        'maestro/v1.9.14/02-adaptive-modules.yaml',
        'maestro/v1.9.14/01-soft-paywall.yaml',
    ],
    'configuration': 'real RevenueCat SDK configuration, no purchase mocks',
    'frames': 'frames/00-*.png through frames/16-*.png; 01c–01d, 02b–02h and 03b–03i cover new questions',
}
(evidence / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
PY

xcrun simctl io "$simulator_id" recordVideo --codec=h264 "$evidence_dir/experience.mp4" \
    > "$evidence_dir/recording.log" 2>&1 &
recording_pid=$!
recording_started_at=$SECONDS
recording_result=0
stop_recording() {
    if ! kill -0 "$recording_pid" 2>/dev/null; then
        recording_result=1
    else
        kill -INT "$recording_pid" 2>/dev/null || recording_result=1
    fi
    local recorder_exit=0
    wait "$recording_pid" || recorder_exit=$?
    if [[ "$recorder_exit" != 0 && "$recorder_exit" != 130 ]]; then
        recording_result=1
    fi
}
trap stop_recording EXIT
sleep 1
kill -0 "$recording_pid"
set +e
# Capture the other adaptive branches first. The canonical flow clears state
# again, so its original frames and final free-feed assertions stay independent.
maestro --device "$simulator_id" test --format JUNIT \
    -e "EVIDENCE_DIR=$evidence_dir" \
    --output "$evidence_dir/adaptive-result.xml" --debug-output "$evidence_dir/adaptive-maestro" \
    maestro/v1.9.14/02-adaptive-modules.yaml > "$evidence_dir/adaptive-maestro.log" 2>&1
adaptive_result=$?
maestro --device "$simulator_id" test --format JUNIT \
    -e "EVIDENCE_DIR=$evidence_dir" \
    --output "$evidence_dir/result.xml" --debug-output "$evidence_dir/maestro" \
    maestro/v1.9.14/01-soft-paywall.yaml > "$evidence_dir/maestro.log" 2>&1
main_result=$?
set -e
maestro_result=$main_result
if [[ "$maestro_result" == 0 && "$adaptive_result" != 0 ]]; then
    maestro_result=$adaptive_result
fi
printf '%s\n' "$adaptive_result" > "$evidence_dir/adaptive-exit-code.txt"
printf '%s\n' "$main_result" > "$evidence_dir/main-exit-code.txt"
recording_elapsed=$((SECONDS - recording_started_at))
stop_recording
trap - EXIT
printf '%s\n' "$maestro_result" > "$evidence_dir/exit-code.txt"
if [[ "$recording_result" != 0 || ! -s "$evidence_dir/experience.mp4" ]]; then
    printf '%s\n' 'Simulator recording failed or ended before the journey completed.' >&2
    exit 1
fi
xcrun swift scripts/verify-maestro-recording.swift "$evidence_dir/experience.mp4" "$recording_elapsed" \
    > "$evidence_dir/video-validation.json"
exit "$maestro_result"
