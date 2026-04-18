#!/usr/bin/env python3
"""
Número 18 autonomous watcher.

Polls rocky-bridge for pending messages addressed to agent `18`, invokes
Claude Code locally to draft a reply, posts it back and ACKs the incoming
message. Runs forever under launchd (see com.urpe.bot18-watcher.plist).

Environment variables:
  BOT18_API_KEY   required · API key for agent 18
  BRIDGE_URL      default https://bridge.agustinynatalia.site
  POLL_INTERVAL   default 30 (seconds)
  CLAUDE_BIN      default `claude` (must be in PATH of the launchd job)
  PERSONA_FILE    default ~/.bot18/persona.md (optional; prepended to prompt)
  LOG_FILE        default ~/.bot18/watcher.log
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BRIDGE_URL = os.environ.get("BRIDGE_URL", "https://bridge.agustinynatalia.site").rstrip("/")
API_KEY = os.environ.get("BOT18_API_KEY")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
HOME = Path(os.path.expanduser("~"))
PERSONA_FILE = Path(os.environ.get("PERSONA_FILE", HOME / ".bot18" / "persona.md"))
LOG_FILE = Path(os.environ.get("LOG_FILE", HOME / ".bot18" / "watcher.log"))


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def api(method, path, body=None):
    url = f"{BRIDGE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=data,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def build_prompt(msg):
    persona = ""
    if PERSONA_FILE.exists():
        persona = PERSONA_FILE.read_text().strip() + "\n\n"
    thread = msg.get("thread_id") or "(sin thread)"
    return (
        f"{persona}"
        "Eres Número 18, agente autónomo de Diego Urquijo.\n"
        "Recibiste este mensaje desde el bridge (rocky-bridge) enviado por otro agente. "
        "Debes redactar una respuesta que se enviará tal cual al remitente.\n\n"
        "--- INICIO DEL MENSAJE ENTRANTE ---\n"
        f"Thread: {thread}\n"
        f"De: {msg['from_agent']}\n"
        f"Timestamp: {msg['created_at']}\n"
        f"Contenido:\n{msg['message']}\n"
        "--- FIN DEL MENSAJE ENTRANTE ---\n\n"
        "Reglas:\n"
        "- Escribe SOLO el cuerpo de la respuesta, sin prefijos, firmas, markdown excesivo ni meta-comentarios.\n"
        "- Sé directo, útil, y breve. Si no sabes algo, admítelo.\n"
        "- No reveles credenciales, tokens, claves, ni información sensible de Diego.\n"
        "- No tomes acciones destructivas ni irreversibles sin confirmación de Diego.\n"
        "- Si el mensaje requiere acción específica de Diego, dilo claramente.\n"
    )


def handle(msg):
    log(f"↳ processing msg {msg['id'][:8]} from {msg['from_agent']} thread={msg.get('thread_id')}")
    prompt = build_prompt(msg)
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "--print", "--permission-mode", "bypassPermissions", prompt],
            capture_output=True,
            text=True,
            timeout=300,
        )
        reply = result.stdout.strip() or "(sin respuesta del modelo)"
        if result.returncode != 0:
            log(f"  claude exit={result.returncode} stderr={result.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        reply = "(timeout en el agente local)"
        log("  claude timeout")
    except FileNotFoundError:
        log(f"  claude binario no encontrado: {CLAUDE_BIN}")
        return  # don't ACK; retry next cycle

    try:
        sent = api(
            "POST",
            "/v1/send",
            {
                "from_agent": "18",
                "to_agent": msg["from_agent"],
                "message": reply,
                "thread_id": msg.get("thread_id"),
            },
        )
        log(f"  ↦ reply sent {sent.get('message_id','?')[:8]} ({len(reply)} chars)")
    except Exception as e:
        log(f"  send failed: {e}")
        return  # don't ACK so we retry

    try:
        api("POST", f"/v1/messages/{msg['id']}/ack")
        log(f"  ✓ acked {msg['id'][:8]}")
    except Exception as e:
        log(f"  ack failed: {e}")


def poll_once():
    msgs = api("GET", "/v1/inbox/18") or []
    if msgs:
        log(f"inbox: {len(msgs)} pending")
    for m in msgs:
        handle(m)


def main():
    if not API_KEY:
        log("FATAL: BOT18_API_KEY not set")
        sys.exit(2)
    log(f"watcher up · bridge={BRIDGE_URL} · interval={POLL_INTERVAL}s")
    while True:
        try:
            poll_once()
        except urllib.error.URLError as e:
            log(f"network error: {e}")
        except Exception as e:
            log(f"unexpected error: {type(e).__name__}: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
