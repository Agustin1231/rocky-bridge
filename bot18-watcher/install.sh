#!/bin/bash
# Installer for Número 18 autonomous watcher (macOS · launchd).
#
# Usage:
#   BOT18_API_KEY=<key> bash install.sh
# or (one-liner from repo):
#   curl -fsSL https://raw.githubusercontent.com/Agustin1231/rocky-bridge/main/bot18-watcher/install.sh | BOT18_API_KEY=<key> bash
#
# What it does:
#   1. Creates ~/.bot18/ and copies watcher.py there
#   2. Renders the launchd plist with your paths + API key
#   3. Installs into ~/Library/LaunchAgents and loads it
#   4. Verifies the process is running

set -euo pipefail

LABEL="com.urpe.bot18-watcher"
INSTALL_DIR="${HOME}/.bot18"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
BRIDGE_URL="${BRIDGE_URL:-https://bridge.agustinynatalia.site}"
POLL_INTERVAL="${POLL_INTERVAL:-30}"

if [[ -z "${BOT18_API_KEY:-}" ]]; then
    echo "error: BOT18_API_KEY not set" >&2
    echo "usage: BOT18_API_KEY=<key> bash install.sh" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
    echo "error: python3 not found in PATH" >&2
    exit 1
fi

CLAUDE_BIN="$(command -v claude || true)"
if [[ -z "${CLAUDE_BIN}" ]]; then
    echo "warning: 'claude' not in PATH — the watcher will log errors until you install Claude Code CLI."
    CLAUDE_BIN="claude"
fi

echo "→ install dir:  ${INSTALL_DIR}"
echo "→ python3:      ${PYTHON_BIN}"
echo "→ claude:       ${CLAUDE_BIN}"
echo "→ bridge url:   ${BRIDGE_URL}"
echo "→ poll every:   ${POLL_INTERVAL}s"

mkdir -p "${INSTALL_DIR}"

SCRIPT_URL="${WATCHER_URL:-https://raw.githubusercontent.com/Agustin1231/rocky-bridge/main/bot18-watcher/watcher.py}"
PLIST_URL="${PLIST_URL:-https://raw.githubusercontent.com/Agustin1231/rocky-bridge/main/bot18-watcher/com.urpe.bot18-watcher.plist.tmpl}"

echo "→ downloading watcher.py"
curl -fsSL "${SCRIPT_URL}" -o "${INSTALL_DIR}/watcher.py"
chmod +x "${INSTALL_DIR}/watcher.py"

echo "→ downloading plist template"
TMP_PLIST="$(mktemp)"
curl -fsSL "${PLIST_URL}" -o "${TMP_PLIST}"

ESC_KEY="$(printf '%s' "${BOT18_API_KEY}" | sed 's/[\/&]/\\&/g')"
ESC_DIR="$(printf '%s' "${INSTALL_DIR}" | sed 's/[\/&]/\\&/g')"
ESC_PY="$(printf '%s' "${PYTHON_BIN}" | sed 's/[\/&]/\\&/g')"
ESC_CLAUDE="$(printf '%s' "${CLAUDE_BIN}" | sed 's/[\/&]/\\&/g')"
ESC_BRIDGE="$(printf '%s' "${BRIDGE_URL}" | sed 's/[\/&]/\\&/g')"

sed -i '' \
    -e "s/__PYTHON_BIN__/${ESC_PY}/g" \
    -e "s/__INSTALL_DIR__/${ESC_DIR}/g" \
    -e "s/__BOT18_API_KEY__/${ESC_KEY}/g" \
    -e "s/__BRIDGE_URL__/${ESC_BRIDGE}/g" \
    -e "s/__POLL_INTERVAL__/${POLL_INTERVAL}/g" \
    -e "s/__CLAUDE_BIN__/${ESC_CLAUDE}/g" \
    "${TMP_PLIST}" 2>/dev/null || \
sed -i \
    -e "s/__PYTHON_BIN__/${ESC_PY}/g" \
    -e "s/__INSTALL_DIR__/${ESC_DIR}/g" \
    -e "s/__BOT18_API_KEY__/${ESC_KEY}/g" \
    -e "s/__BRIDGE_URL__/${ESC_BRIDGE}/g" \
    -e "s/__POLL_INTERVAL__/${POLL_INTERVAL}/g" \
    -e "s/__CLAUDE_BIN__/${ESC_CLAUDE}/g" \
    "${TMP_PLIST}"

mkdir -p "$(dirname "${PLIST_DEST}")"
mv "${TMP_PLIST}" "${PLIST_DEST}"
chmod 600 "${PLIST_DEST}"

echo "→ loading launchd agent"
launchctl unload "${PLIST_DEST}" 2>/dev/null || true
launchctl load "${PLIST_DEST}"

sleep 2

if launchctl list | grep -q "${LABEL}"; then
    echo "✔ ${LABEL} loaded"
else
    echo "✘ agent not in launchctl list" >&2
    exit 1
fi

echo ""
echo "Installed. Logs:"
echo "  ${INSTALL_DIR}/watcher.log"
echo "  ${INSTALL_DIR}/watcher.stdout.log"
echo "  ${INSTALL_DIR}/watcher.stderr.log"
echo ""
echo "To stop:   launchctl unload ${PLIST_DEST}"
echo "To start:  launchctl load ${PLIST_DEST}"
echo "To remove: launchctl unload ${PLIST_DEST} && rm ${PLIST_DEST} && rm -rf ${INSTALL_DIR}"
