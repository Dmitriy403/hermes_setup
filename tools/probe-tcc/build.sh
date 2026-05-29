#!/usr/bin/env bash
# Build hermes-probe-tcc — a single Mach-O TCC probe binary.
# v1: ad-hoc signed (Scenario A). See tools/probe-tcc/README.md.

set -euo pipefail

PROBE_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${PROBE_DIR}/build"
BIN="${BUILD_DIR}/hermes-probe-tcc"
PLIST="${PROBE_DIR}/Info.plist"
ENTS="${PROBE_DIR}/entitlements.plist"

IDENTIFIER="${IDENTIFIER:-org.hermes.probe-tcc}"
TARGET="${TARGET:-arm64-apple-macosx13.0}"

mkdir -p "${BUILD_DIR}"

echo "→ compiling for ${TARGET}"
swiftc \
    -O \
    -target "${TARGET}" \
    -framework Foundation \
    -framework CoreGraphics \
    -framework CoreServices \
    -framework ApplicationServices \
    -framework AVFoundation \
    -framework IOKit \
    -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker "${PLIST}" \
    -Xlinker -no_uuid \
    -o "${BIN}" \
    "${PROBE_DIR}/Sources/"*.swift

echo "→ codesign --sign - --identifier ${IDENTIFIER}"
codesign \
    --force \
    --sign - \
    --identifier "${IDENTIFIER}" \
    --entitlements "${ENTS}" \
    "${BIN}"

echo "→ verifying signature"
codesign --verify --verbose=2 "${BIN}"

# Strip quarantine attribute if present (downloads may carry it).
xattr -d com.apple.quarantine "${BIN}" 2>/dev/null || true

# Print cdhash so CI logs record it and the maintainer can update
# manifest/probe-tcc.yaml.
CDHASH=$(codesign --display --verbose=4 "${BIN}" 2>&1 | awk -F'=' '/^CDHash=/ { print $2 }')
echo ""
echo "→ binary:  ${BIN}"
echo "→ cdhash:  ${CDHASH}"
echo ""
echo "Next: copy build/hermes-probe-tcc → bin/hermes-probe-tcc and update"
echo "      manifest/probe-tcc.yaml's expected_cdhash."
