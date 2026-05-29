#!/usr/bin/env bash
# Verify hermes-probe-tcc — sanity checks for CI/commit hooks.
#
# Confirms:
#   - the binary exists and is executable
#   - codesign verifies and signature is ad-hoc
#   - identifier matches org.hermes.probe-tcc
#   - embedded Info.plist contains the required Usage Description keys
#   - --json output starts with a v1 schema document

set -euo pipefail

PROBE_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="${1:-${PROBE_DIR}/build/hermes-probe-tcc}"

if [[ ! -x "${BIN}" ]]; then
    echo "FAIL: ${BIN} missing or not executable" >&2
    echo "      Run ${PROBE_DIR}/build.sh first." >&2
    exit 1
fi

echo "→ ${BIN}"

# 1. codesign verify.
echo "  • codesign verify"
codesign --verify --verbose=2 "${BIN}"

# 2. Identifier and signature kind.
SIG_OUTPUT=$(codesign --display --verbose=4 "${BIN}" 2>&1)
IDENTIFIER=$(echo "${SIG_OUTPUT}" | awk -F'=' '/^Identifier=/ { print $2 }')
SIGNATURE=$(echo "${SIG_OUTPUT}" | awk -F'=' '/^Signature=/ { print $2 }')

if [[ "${IDENTIFIER}" != "org.hermes.probe-tcc" ]]; then
    echo "FAIL: identifier is '${IDENTIFIER}', expected org.hermes.probe-tcc" >&2
    exit 1
fi
echo "  • identifier ok: ${IDENTIFIER}"

if [[ "${SIGNATURE}" != "adhoc" ]]; then
    echo "FAIL: signature kind is '${SIGNATURE}', expected 'adhoc' for v1 (Scenario A)" >&2
    exit 1
fi
echo "  • signature ok: ${SIGNATURE}"

# 3. Embedded Info.plist Usage Descriptions.
REQUIRED_KEYS=(
    NSAppleEventsUsageDescription
    NSMicrophoneUsageDescription
    NSCameraUsageDescription
    NSDocumentsFolderUsageDescription
    NSDesktopFolderUsageDescription
    NSDownloadsFolderUsageDescription
    NSSpeechRecognitionUsageDescription
)

# `strings -a` extracts every printable ASCII run from the binary,
# including the embedded Info.plist section. We just look for the
# required usage-description key names.
STRINGS_DUMP=$(strings -a "${BIN}")
for key in "${REQUIRED_KEYS[@]}"; do
    if ! grep -q "${key}" <<<"${STRINGS_DUMP}"; then
        echo "FAIL: embedded Info.plist missing key ${key}" >&2
        exit 1
    fi
done
echo "  • Info.plist usage keys ok"

# 4. Smoke-test JSON output.
echo "  • smoke-testing --json output"
JSON_OUT=$("${BIN}" --json 2>/dev/null || true)
if ! grep -q '"schema"[[:space:]]*:[[:space:]]*"https://hermes/probe-tcc/v1"' <<<"${JSON_OUT}"; then
    echo "FAIL: --json output does not declare v1 schema" >&2
    echo "First 200 bytes:" >&2
    echo "${JSON_OUT:0:200}" >&2
    exit 1
fi
echo "  • schema ok"

# 5. Rule-sync consistency: Swift constants must match sandbox-rules.yaml.
echo "  • checking SandboxRules.swift ↔ sandbox-rules.yaml"
python3 "${PROBE_DIR}/check_sandbox_rules.py" >/dev/null

# 6. Print cdhash for the maintainer's records.
CDHASH=$(echo "${SIG_OUTPUT}" | awk -F'=' '/^CDHash=/ { print $2 }')
echo ""
echo "OK — ${BIN}"
echo "    cdhash: ${CDHASH}"
