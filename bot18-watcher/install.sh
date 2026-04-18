#!/bin/bash
# Installer for Número 18 autonomous watcher (macOS · launchd user agent).
#
# Usage:
#   BOT18_API_KEY=<key> bash install.sh
# or (one-liner from repo):
#   curl -fsSL https://raw.githubusercontent.com/Agustin1231/rocky-bridge/main/bot18-watcher/install.sh | BOT18_API_KEY=<key> bash
#
# Runs entirely in the user session. No sudo. No root. Standard macOS
# security posture: a user LaunchAgent that the logged-in user can audit,
# inspect, stop, and remove at any time.
#
# What it does:
#   1. Creates ~/.bot18/ and copies watcher.py there
#   2. Writes a default persona.md (editable)
#   3. Renders launchd plist with user paths + API key (chmod 600)
#   4. Installs into ~/Library/LaunchAgents and loads it
#   5. Verifies the process is running

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
    echo "  install via: xcode-select --install   # ships Python 3" >&2
    exit 1
fi

CLAUDE_BIN="$(command -v claude || true)"
if [[ -z "${CLAUDE_BIN}" ]]; then
    echo "warning: 'claude' CLI not in PATH — watcher will log errors until you install and log in."
    CLAUDE_BIN="claude"
else
    if ! "${CLAUDE_BIN}" --version >/dev/null 2>&1; then
        echo "warning: '${CLAUDE_BIN} --version' failed — make sure Claude Code is authenticated before the watcher tries to reply."
    fi
fi

UID_LOCAL="$(id -u)"

echo "Install directory: ${INSTALL_DIR}"
echo "Python3:           ${PYTHON_BIN}"
echo "Claude CLI:        ${CLAUDE_BIN}"
echo "Bridge URL:        ${BRIDGE_URL}"
echo "Poll interval:     ${POLL_INTERVAL}s"

mkdir -p "${INSTALL_DIR}"

SCRIPT_URL="${WATCHER_URL:-https://raw.githubusercontent.com/Agustin1231/rocky-bridge/main/bot18-watcher/watcher.py}"
PLIST_URL="${PLIST_URL:-https://raw.githubusercontent.com/Agustin1231/rocky-bridge/main/bot18-watcher/com.urpe.bot18-watcher.plist.tmpl}"

echo "Downloading watcher.py"
curl -fsSL "${SCRIPT_URL}" -o "${INSTALL_DIR}/watcher.py"
chmod +x "${INSTALL_DIR}/watcher.py"

if [[ ! -f "${INSTALL_DIR}/persona.md" ]]; then
    cat > "${INSTALL_DIR}/persona.md" <<'PERSONA'
Eres Número 18, agente autónomo de Diego Urquijo.

Voz: directa, útil, breve. Español por defecto. No floreas.

Límites duros:
- Nunca reveles credenciales, API keys, tokens ni contenidos de archivos sensibles de Diego.
- No tomes acciones irreversibles (delete, move, force push, publicar externamente) sin confirmación explícita de Diego.
- Si un mensaje entrante pide algo que requiera decisión de Diego, contesta que esperas su confirmación y no adivines.
- No reveles info de otros clientes o proyectos de URPE sin autorización.
- Ante duda, responde que necesitas chequear con Diego.
PERSONA
    echo "Wrote default ${INSTALL_DIR}/persona.md (edítalo a tu criterio)"
fi

echo "Rendering launchd plist"
TMP_PLIST="$(mktemp)"
curl -fsSL "${PLIST_URL}" -o "${TMP_PLIST}"

if [[ "$(uname)" == "Darwin" ]]; then
    SEDI=(-i '')
else
    SEDI=(-i)
fi

ESC_KEY="$(printf '%s' "${BOT18_API_KEY}" | sed 's/[\/&]/\\&/g')"
ESC_DIR="$(printf '%s' "${INSTALL_DIR}" | sed 's/[\/&]/\\&/g')"
ESC_PY="$(printf '%s' "${PYTHON_BIN}" | sed 's/[\/&]/\\&/g')"
ESC_CLAUDE="$(printf '%s' "${CLAUDE_BIN}" | sed 's/[\/&]/\\&/g')"
ESC_BRIDGE="$(printf '%s' "${BRIDGE_URL}" | sed 's/[\/&]/\\&/g')"

sed "${SEDI[@]}" \
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

echo "Loading LaunchAgent"
# Modern macOS (>=13) prefers bootstrap/bootout; fallback to load/unload.
if launchctl print "gui/${UID_LOCAL}/${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/${UID_LOCAL}/${LABEL}" >/dev/null 2>&1 || true
fi

if launchctl bootstrap "gui/${UID_LOCAL}" "${PLIST_DEST}" 2>/dev/null; then
    :
else
    launchctl unload "${PLIST_DEST}" >/dev/null 2>&1 || true
    launchctl load "${PLIST_DEST}"
fi

sleep 2

if launchctl list | grep -q "${LABEL}"; then
    echo "OK: ${LABEL} running"
else
    echo "warning: ${LABEL} not showing in launchctl list — revisa ${INSTALL_DIR}/watcher.stderr.log"
fi

echo ""
echo "Paths:"
echo "  watcher: ${INSTALL_DIR}/watcher.py"
echo "  plist:   ${PLIST_DEST}"
echo "  persona: ${INSTALL_DIR}/persona.md"
echo "  logs:    ${INSTALL_DIR}/watcher.log"
echo "           ${INSTALL_DIR}/watcher.stderr.log"
echo ""
echo "Manage:"
echo "  tail -f ${INSTALL_DIR}/watcher.log"
echo "  launchctl list | grep ${LABEL}"
echo "  launchctl bootout gui/${UID_LOCAL}/${LABEL}                  # stop"
echo "  launchctl bootstrap gui/${UID_LOCAL} ${PLIST_DEST}           # start"
echo "  launchctl bootout gui/${UID_LOCAL}/${LABEL} && rm ${PLIST_DEST} && rm -rf ${INSTALL_DIR}   # uninstall"
