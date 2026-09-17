#!/bin/bash

# iOS App Store Release Automation Script
# Usage: ./scripts/release-ios.sh [--upload]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_NAME="aniccaios"
SCHEME="aniccaios"
CONFIGURATION="Release"
ARCHIVE_PATH="${PROJECT_DIR}/build/${PROJECT_NAME}.xcarchive"
EXPORT_PATH="${PROJECT_DIR}/build/ipa"
EXPORT_OPTIONS_PLIST="${PROJECT_DIR}/ExportOptions.plist"
TEAM_ID="S5U8UH3JLJ"
BUNDLE_ID="ai.anicca.app.ios"

# Parse arguments
UPLOAD=false
if [[ "$1" == "--upload" ]]; then
    UPLOAD=true
fi

# Load environment variables if .env.ios exists
if [ -f "${PROJECT_DIR}/.env.ios" ]; then
    echo -e "${GREEN}✓${NC} Loading environment variables from .env.ios"
    source "${PROJECT_DIR}/.env.ios"
fi

echo "=================================================="
echo "  iOS App Store Release Automation"
echo "=================================================="
echo ""
echo "Project: ${PROJECT_NAME}"
echo "Scheme: ${SCHEME}"
echo "Configuration: ${CONFIGURATION}"
echo "Upload to App Store: ${UPLOAD}"
echo ""

# Step 1: Clean build
echo -e "${YELLOW}[1/5]${NC} Cleaning build..."
cd "${PROJECT_DIR}"
xcodebuild clean \
    -project "${PROJECT_NAME}.xcodeproj" \
    -scheme "${SCHEME}" \
    -configuration "${CONFIGURATION}" \
    > /dev/null 2>&1

echo -e "${GREEN}✓${NC} Clean completed"
echo ""

# Step 2: Archive
echo -e "${YELLOW}[2/5]${NC} Creating archive..."
echo "This may take a few minutes..."

xcodebuild archive \
    -project "${PROJECT_NAME}.xcodeproj" \
    -scheme "${SCHEME}" \
    -configuration "${CONFIGURATION}" \
    -archivePath "${ARCHIVE_PATH}" \
    -destination "generic/platform=iOS" \
    -allowProvisioningUpdates \
    DEVELOPMENT_TEAM="${TEAM_ID}" \
    | xcbeautify || xcodebuild archive \
    -project "${PROJECT_NAME}.xcodeproj" \
    -scheme "${SCHEME}" \
    -configuration "${CONFIGURATION}" \
    -archivePath "${ARCHIVE_PATH}" \
    -destination "generic/platform=iOS" \
    -allowProvisioningUpdates \
    DEVELOPMENT_TEAM="${TEAM_ID}"

echo -e "${GREEN}✓${NC} Archive created successfully"
echo ""

# Step 3: Validate archive
echo -e "${YELLOW}[3/5]${NC} Validating archive..."

ARCHIVE_INFO_PLIST="${ARCHIVE_PATH}/Info.plist"
if [ ! -f "${ARCHIVE_INFO_PLIST}" ]; then
    echo -e "${RED}✗${NC} Archive Info.plist not found!"
    exit 1
fi

# Check for ApplicationProperties
if /usr/libexec/PlistBuddy -c "Print :ApplicationProperties" "${ARCHIVE_INFO_PLIST}" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Archive is valid (ApplicationProperties found)"

    # Display archive information
    APP_PATH=$(/usr/libexec/PlistBuddy -c "Print :ApplicationProperties:ApplicationPath" "${ARCHIVE_INFO_PLIST}")
    BUNDLE_ID_ARCHIVED=$(/usr/libexec/PlistBuddy -c "Print :ApplicationProperties:CFBundleIdentifier" "${ARCHIVE_INFO_PLIST}")
    VERSION=$(/usr/libexec/PlistBuddy -c "Print :ApplicationProperties:CFBundleShortVersionString" "${ARCHIVE_INFO_PLIST}")
    BUILD=$(/usr/libexec/PlistBuddy -c "Print :ApplicationProperties:CFBundleVersion" "${ARCHIVE_INFO_PLIST}")

    echo ""
    echo "  Application Path: ${APP_PATH}"
    echo "  Bundle ID: ${BUNDLE_ID_ARCHIVED}"
    echo "  Version: ${VERSION}"
    echo "  Build: ${BUILD}"
else
    echo -e "${RED}✗${NC} Archive validation failed: ApplicationProperties not found!"
    echo ""
    echo "This means the archive will appear in 'Other Items' in Xcode Organizer."
    echo "Please check your project settings."
    exit 1
fi
echo ""

# Step 4: Export IPA
echo -e "${YELLOW}[4/5]${NC} Exporting IPA for App Store..."

if [ ! -f "${EXPORT_OPTIONS_PLIST}" ]; then
    echo -e "${RED}✗${NC} ExportOptions.plist not found at: ${EXPORT_OPTIONS_PLIST}"
    echo "Please run this script from the project root directory."
    exit 1
fi

# Remove previous export if exists
rm -rf "${EXPORT_PATH}"

xcodebuild -exportArchive \
    -archivePath "${ARCHIVE_PATH}" \
    -exportPath "${EXPORT_PATH}" \
    -exportOptionsPlist "${EXPORT_OPTIONS_PLIST}" \
    -allowProvisioningUpdates \
    | xcbeautify || xcodebuild -exportArchive \
    -archivePath "${ARCHIVE_PATH}" \
    -exportPath "${EXPORT_PATH}" \
    -exportOptionsPlist "${EXPORT_OPTIONS_PLIST}" \
    -allowProvisioningUpdates

IPA_FILE="${EXPORT_PATH}/${PROJECT_NAME}.ipa"
if [ -f "${IPA_FILE}" ]; then
    IPA_SIZE=$(du -h "${IPA_FILE}" | cut -f1)
    echo -e "${GREEN}✓${NC} IPA exported successfully"
    echo "  Location: ${IPA_FILE}"
    echo "  Size: ${IPA_SIZE}"
else
    echo -e "${RED}✗${NC} IPA export failed!"
    exit 1
fi
echo ""

# Step 5: Upload to App Store Connect (optional)
if [ "${UPLOAD}" = true ]; then
    echo -e "${YELLOW}[5/5]${NC} Uploading to App Store Connect..."

    if [ -z "${APPLE_ID}" ]; then
        echo -e "${RED}✗${NC} APPLE_ID is not set!"
        echo "Please set APPLE_ID in .env.ios file or export it as an environment variable."
        exit 1
    fi

    if [ -z "${APP_SPECIFIC_PASSWORD}" ]; then
        echo -e "${RED}✗${NC} APP_SPECIFIC_PASSWORD is not set!"
        echo "Please set APP_SPECIFIC_PASSWORD in .env.ios file or export it as an environment variable."
        echo ""
        echo "To generate an App-Specific Password:"
        echo "1. Go to https://appleid.apple.com"
        echo "2. Sign in with your Apple ID"
        echo "3. In the 'Security' section, click 'Generate Password' under 'App-Specific Passwords'"
        echo "4. Save the generated password in .env.ios"
        exit 1
    fi

    echo "Uploading ${IPA_FILE}..."
    echo "This may take several minutes..."

    xcrun altool --upload-app \
        --type ios \
        --file "${IPA_FILE}" \
        --username "${APPLE_ID}" \
        --password "${APP_SPECIFIC_PASSWORD}"

    echo -e "${GREEN}✓${NC} Upload completed successfully!"
    echo ""
    echo "The build will appear in App Store Connect within a few minutes."
    echo "You can check the status at: https://appstoreconnect.apple.com"
else
    echo -e "${YELLOW}[5/5]${NC} Skipping upload (use --upload flag to upload)"
    echo ""
    echo "To upload manually later, run:"
    echo "  xcrun altool --upload-app --type ios --file \"${IPA_FILE}\" --username YOUR_APPLE_ID --password YOUR_APP_SPECIFIC_PASSWORD"
fi

echo ""
echo "=================================================="
echo -e "${GREEN}✓ Release process completed successfully!${NC}"
echo "=================================================="
echo ""
echo "Next steps:"
if [ "${UPLOAD}" = false ]; then
    echo "  1. To upload to App Store Connect, run:"
    echo "     ./scripts/release-ios.sh --upload"
else
    echo "  1. Go to App Store Connect: https://appstoreconnect.apple.com"
    echo "  2. Wait for the build to be processed (usually 5-15 minutes)"
    echo "  3. Add the build to TestFlight or submit for App Review"
fi
echo ""
