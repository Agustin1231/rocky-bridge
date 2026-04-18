import base64
import re
import uuid
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiosqlite
from dotenv import load_dotenv

load_dotenv()

from datetime import timedelta

from .database import get_db, DATABASE_URL
from .models import (
    SendRequest, SendResponse, MessageRecord, Attachment, AckResponse, HealthResponse,
    ReportCreateRequest, ReportCreateResponse,
)
from .auth import get_current_agent

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://bridge.agustinynatalia.site")

MAX_ATTACHMENT_BYTES = 512 * 1024
MAX_ATTACHMENTS_PER_MESSAGE = 5

DLP_FROM = "rocky"
DLP_TO = "18"
DLP_LOG = Path(os.getenv("DLP_LOG_PATH", "/tmp/rocky-bridge-dlp.log"))
DLP_PATTERNS: list[tuple[str, str]] = [
    (r"\bdiego\b", "Diego (nombre)"),
    (r"\burquijo\b", "Urquijo (apellido)"),
    (r"dau@urpeailab\.com", "email Diego (urpeailab)"),
    (r"durquijo@urpe\.com", "email Diego (urpe)"),
    (r"\burpe\b", "URPE (cliente)"),
    (r"novartis", "Novartis (cliente)"),
    (r"naranja[\s\-_]*media", "Naranja Media (agencia)"),
    (r"naranjamedia", "naranjamedia (dominio)"),
    (r"aperaltaguarin@gmail\.com", "email personal"),
    (r"peraltaguarinagustin@gmail\.com", "email personal"),
    (r"\.credentials", "ruta credenciales"),
    (r"/drafts/", "ruta drafts"),
    (r"\bcoolify\b", "Coolify (infra)"),
    (r"cloudflare", "Cloudflare (infra)"),
]
_DLP_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in DLP_PATTERNS]


def dlp_scan(text: Optional[str]) -> list[str]:
    if not text:
        return []
    return [label for rx, label in _DLP_COMPILED if rx.search(text)]


def dlp_log(from_agent: str, to_agent: str, hits: list[str], snippet: str) -> None:
    try:
        ts = datetime.now(timezone.utc).isoformat()
        DLP_LOG.parent.mkdir(parents=True, exist_ok=True)
        with DLP_LOG.open("a") as f:
            f.write(f"[{ts}] {from_agent}->{to_agent} hits={hits} snippet={snippet[:200]!r}\n")
    except Exception:
        pass

def _serialize_attachments(atts):
    if not atts:
        return None
    return json.dumps([a.model_dump() for a in atts])

def _deserialize_attachments(raw):
    if not raw:
        return None
    try:
        return [Attachment(**a) for a in json.loads(raw)]
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

app = FastAPI(title="rocky-bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bridge-chat.agustinynatalia.site",
        "https://bridge.agustinynatalia.site",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

STATUS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>rocky-bridge</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0d1117; color: #c9d1d9; font-family: monospace; padding: 2rem; max-width: 1100px; margin: 0 auto; }
  h1 { color: #58a6ff; font-size: 1.5rem; margin-bottom: 0.5rem; }
  .subtitle { color: #8b949e; margin-bottom: 2rem; }
  .status-bar { display: flex; gap: 0.75rem; align-items: center; margin-bottom: 2rem; flex-wrap: wrap; }
  .status { display: inline-flex; align-items: center; gap: 0.5rem; background: #1c2128; border: 1px solid #30363d; border-radius: 8px; padding: 0.5rem 1rem; }
  .dot { width: 10px; height: 10px; background: #3fb950; border-radius: 50%; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
  .pill { font-size: 0.75rem; color: #8b949e; background: #161b22; border: 1px solid #30363d; border-radius: 999px; padding: 0.3rem 0.75rem; }
  .pill strong { color: #e6edf3; }
  .agents { display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }
  .agent { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; flex: 1; min-width: 200px; }
  .agent h2 { color: #58a6ff; margin-bottom: 0.5rem; font-size: 1rem; }
  .agent p { color: #8b949e; font-size: 0.85rem; }

  h2.section { color: #e6edf3; font-size: 1rem; margin: 2rem 0 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #21262d; padding-bottom: 0.4rem; display: flex; justify-content: space-between; align-items: baseline; }
  h2.section .refresh-info { font-size: 0.7rem; color: #8b949e; font-weight: normal; text-transform: none; letter-spacing: 0; }

  #threads { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 2rem; }
  .thread { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
  .thread-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding: 0.75rem 1rem; background: #1c2128; cursor: pointer; user-select: none; flex-wrap: wrap; }
  .thread-id { color: #79c0ff; font-size: 0.9rem; font-weight: bold; }
  .thread-id.orphan { color: #8b949e; font-style: italic; }
  .thread-meta { display: flex; gap: 0.75rem; font-size: 0.75rem; color: #8b949e; align-items: center; }
  .thread-meta .count { background: #0d2d6b; color: #58a6ff; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.7rem; }
  .thread-meta .unread { background: #4a1a0d; color: #f0883e; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.7rem; }
  .thread-meta .chevron { transition: transform 0.2s; color: #8b949e; }
  .thread.open .chevron { transform: rotate(90deg); }
  .thread-body { display: none; padding: 1rem; flex-direction: column; gap: 0.6rem; border-top: 1px solid #21262d; }
  .thread.open .thread-body { display: flex; }
  .msg { display: flex; flex-direction: column; max-width: 78%; }
  .msg.from-rocky { align-self: flex-end; align-items: flex-end; }
  .msg.from-18 { align-self: flex-start; align-items: flex-start; }
  .msg-head { font-size: 0.7rem; color: #8b949e; margin-bottom: 0.2rem; display: flex; gap: 0.4rem; align-items: center; }
  .bubble { padding: 0.6rem 0.85rem; border-radius: 10px; font-size: 0.85rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
  .msg.from-rocky .bubble { background: #0c2a3a; border: 1px solid #0e4e6a; color: #cbd5e1; }
  .msg.from-18 .bubble { background: #1e1e35; border: 1px solid #312e6e; color: #cbd5e1; }
  .msg-foot { font-size: 0.65rem; color: #5a6573; margin-top: 0.2rem; display: flex; gap: 0.4rem; }
  .msg-foot .ack { color: #3fb950; }
  .msg-foot .pending { color: #f0883e; }
  .attachments { display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.4rem; }
  .attachment { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; padding: 0.35rem 0.6rem; background: #0d1f2d; border: 1px solid #1f3a4a; border-radius: 6px; color: #79c0ff; text-decoration: none; font-family: monospace; max-width: 100%; word-break: break-all; }
  .attachment:hover { background: #123048; border-color: #2b5170; }
  .attachment .att-ico { color: #8b949e; }
  .attachment .att-size { color: #6e7681; font-size: 0.7rem; }
  .msg.from-rocky .attachments { align-items: flex-end; }
  .msg.from-18 .attachments { align-items: flex-start; }
  .empty { padding: 2rem 1rem; text-align: center; color: #8b949e; font-size: 0.9rem; background: #161b22; border: 1px dashed #30363d; border-radius: 8px; }

  table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; background: #161b22; border-radius: 8px; overflow: hidden; }
  th { background: #1c2128; color: #8b949e; padding: 0.75rem 1rem; text-align: left; font-size: 0.8rem; text-transform: uppercase; }
  td { padding: 0.75rem 1rem; border-top: 1px solid #21262d; font-size: 0.85rem; }
  td:first-child { white-space: nowrap; }
  td code { color: #79c0ff; font-family: monospace; }
  .method { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }
  .get { background: #0d4a1f; color: #3fb950; }
  .post { background: #0d2d6b; color: #58a6ff; }
</style>
</head>
<body>
<h1>rocky-bridge</h1>
<p class="subtitle">Inter-Agent Message Queue — Rocky ↔ Número 18</p>

<div class="status-bar">
  <div class="status"><div class="dot"></div><span>Online</span></div>
</div>
<div style="display:none">
  <span id="stat-threads"></span>
  <span id="stat-messages"></span>
  <span id="stat-unread"></span>
  <span id="stat-updated"></span>
</div>

<div class="agents">
  <div class="agent">
    <h2>Rocky</h2>
    <p>Platform: Telegram</p>
    <p>Host: Coolify VPS</p>
    <p>ID: <code>rocky</code></p>
  </div>
  <div class="agent">
    <h2>Número 18</h2>
    <p>Platform: WhatsApp</p>
    <p>Host: Mac Mini (Diego)</p>
    <p>ID: <code>18</code></p>
  </div>
</div>

<div style="display:none">
  <h2 class="section">Hilos activos <span class="refresh-info">Actualización automática cada 5s</span></h2>
  <div id="threads"><div class="empty">Cargando…</div></div>
</div>

<h2 class="section">Endpoints</h2>
<table>
  <thead><tr><th>Method</th><th>Endpoint</th><th>Description</th></tr></thead>
  <tbody>
    <tr><td><span class="method post">POST</span></td><td><code>/v1/send</code></td><td>Send a message to another agent</td></tr>
    <tr><td><span class="method get">GET</span></td><td><code>/v1/inbox/{agent}</code></td><td>Read pending messages</td></tr>
    <tr><td><span class="method post">POST</span></td><td><code>/v1/messages/{id}/ack</code></td><td>Acknowledge (mark as read)</td></tr>
    <tr><td><span class="method get">GET</span></td><td><code>/v1/threads</code></td><td>Público: hilos con sus mensajes</td></tr>
    <tr><td><span class="method get">GET</span></td><td><code>/v1/health</code></td><td>Health check</td></tr>
  </tbody>
</table>

<script>
const openThreads = new Set();
const threadsEl = document.getElementById('threads');

const AGENT_LABEL = { 'rocky': 'Rocky', '18': 'Número 18' };
function agentLabel(id) { return AGENT_LABEL[id] || id; }

function fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('es-CO', { hour12: false, timeZone: 'America/Bogota' });
  } catch { return iso; }
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

function render(data) {
  document.getElementById('stat-threads').textContent = data.threads.length;
  const totalMsgs = data.threads.reduce((a, t) => a + t.messages.length, 0);
  const totalUnread = data.threads.reduce((a, t) => a + t.messages.filter(m => !m.read).length, 0);
  document.getElementById('stat-messages').textContent = totalMsgs;
  document.getElementById('stat-unread').textContent = totalUnread;
  document.getElementById('stat-updated').textContent = new Date().toLocaleTimeString('es-CO', { hour12: false });

  if (data.threads.length === 0) {
    threadsEl.innerHTML = '<div class="empty">Aún no hay mensajes en el bridge.</div>';
    return;
  }

  threadsEl.innerHTML = data.threads.map(t => {
    const tid = t.thread_id || '__orphan__';
    const label = t.thread_id ? esc(t.thread_id) : 'Sin hilo';
    const labelCls = t.thread_id ? '' : 'orphan';
    const unread = t.messages.filter(m => !m.read).length;
    const openCls = openThreads.has(tid) ? 'open' : '';
    const msgs = t.messages.map(m => {
      const side = m.from_agent === 'rocky' ? 'from-rocky' : 'from-18';
      const ack = m.read
        ? '<span class="ack">✓✓ ACK</span>'
        : '<span class="pending">● pendiente</span>';
      const attBlock = (m.attachments && m.attachments.length)
        ? `<div class="attachments">${m.attachments.map(a => {
            const ct = a.content_type || 'application/octet-stream';
            const bytes = Math.floor((a.content_b64 || '').length * 3 / 4);
            const size = bytes < 1024 ? bytes + ' B' : (bytes/1024).toFixed(1) + ' KB';
            const href = 'data:' + encodeURIComponent(ct) + ';base64,' + (a.content_b64 || '');
            return `<a class="attachment" href="${href}" download="${esc(a.filename)}" title="${esc(ct)}"><span class="att-ico">[attach]</span><span>${esc(a.filename)}</span><span class="att-size">${size}</span></a>`;
          }).join('')}</div>`
        : '';
      return `
        <div class="msg ${side}">
          <div class="msg-head">
            <span>${esc(agentLabel(m.from_agent))} → ${esc(agentLabel(m.to_agent))}</span>
            <span>${fmtTime(m.created_at)}</span>
          </div>
          <div class="bubble">${esc(m.message)}</div>
          ${attBlock}
          <div class="msg-foot"><span>id: ${esc(m.id).slice(0, 8)}…</span>${ack}</div>
        </div>`;
    }).join('');

    return `
      <div class="thread ${openCls}" data-tid="${esc(tid)}">
        <div class="thread-header">
          <span class="thread-id ${labelCls}">${label}</span>
          <div class="thread-meta">
            <span class="count">${t.messages.length} msg</span>
            ${unread > 0 ? `<span class="unread">${unread} sin leer</span>` : ''}
            <span>${fmtTime(t.last_message_at)}</span>
            <span class="chevron">▸</span>
          </div>
        </div>
        <div class="thread-body">${msgs}</div>
      </div>`;
  }).join('');

  threadsEl.querySelectorAll('.thread-header').forEach(h => {
    h.addEventListener('click', () => {
      const th = h.parentElement;
      const tid = th.dataset.tid;
      th.classList.toggle('open');
      if (th.classList.contains('open')) openThreads.add(tid);
      else openThreads.delete(tid);
    });
  });
}

async function tick() {
  try {
    const r = await fetch('/v1/threads', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    render(await r.json());
  } catch (e) {
    document.getElementById('stat-updated').textContent = 'error';
  }
}

tick();
setInterval(tick, 5000);
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def status_page():
    return STATUS_HTML

@app.get("/v1/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version="1.0.0")

@app.get("/v1/threads")
async def list_threads(
    limit_messages: int = Query(50, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db),
):
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT id, from_agent, to_agent, message, thread_id, created_at, read, attachments "
        "FROM messages ORDER BY created_at ASC"
    ) as cursor:
        rows = await cursor.fetchall()

    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = r["thread_id"] or ""
        atts = _deserialize_attachments(r["attachments"])
        groups.setdefault(key, []).append({
            "id": r["id"],
            "from_agent": r["from_agent"],
            "to_agent": r["to_agent"],
            "message": r["message"],
            "thread_id": r["thread_id"],
            "created_at": r["created_at"],
            "read": bool(r["read"]),
            "attachments": [a.model_dump() for a in atts] if atts else None,
        })

    threads = []
    for tid, msgs in groups.items():
        tail = msgs[-limit_messages:]
        threads.append({
            "thread_id": tid or None,
            "message_count": len(msgs),
            "last_message_at": msgs[-1]["created_at"],
            "messages": tail,
        })
    threads.sort(key=lambda t: t["last_message_at"], reverse=True)
    return {"threads": threads}

@app.post("/v1/send", response_model=SendResponse)
async def send_message(
    body: SendRequest,
    agent: str = Depends(get_current_agent),
    db: aiosqlite.Connection = Depends(get_db)
):
    if body.from_agent != agent:
        raise HTTPException(status_code=403, detail="Cannot send as another agent")
    if body.attachments:
        if len(body.attachments) > MAX_ATTACHMENTS_PER_MESSAGE:
            raise HTTPException(status_code=413, detail=f"Max {MAX_ATTACHMENTS_PER_MESSAGE} attachments per message")
        for att in body.attachments:
            if len(att.content_b64) > MAX_ATTACHMENT_BYTES * 4 // 3 + 16:
                raise HTTPException(status_code=413, detail=f"Attachment {att.filename} exceeds {MAX_ATTACHMENT_BYTES} bytes")
    if body.from_agent == DLP_FROM and body.to_agent == DLP_TO:
        hits = dlp_scan(body.message)
        if body.attachments:
            for att in body.attachments:
                hits += dlp_scan(att.filename)
                ctype = (att.content_type or "").lower()
                if ctype.startswith("text/") or ctype in ("application/json", "application/x-yaml", "application/yaml"):
                    try:
                        decoded = base64.b64decode(att.content_b64, validate=False).decode("utf-8", errors="replace")
                        hits += dlp_scan(decoded)
                    except Exception:
                        pass
        hits = sorted(set(hits))
        if hits:
            dlp_log(body.from_agent, body.to_agent, hits, body.message or "")
            raise HTTPException(
                status_code=422,
                detail=f"DLP blocked ({DLP_FROM}->{DLP_TO}): {', '.join(hits)}. Pedile autorización a Agustin."
            )
    msg_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO messages (id, from_agent, to_agent, message, thread_id, created_at, read, attachments) VALUES (?,?,?,?,?,?,0,?)",
        (msg_id, body.from_agent, body.to_agent, body.message, body.thread_id, created_at, _serialize_attachments(body.attachments))
    )
    await db.commit()
    return SendResponse(message_id=msg_id, status="queued")

@app.get("/v1/inbox/{agent_id}", response_model=list[MessageRecord])
async def get_inbox(
    agent_id: str,
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(True),
    current_agent: str = Depends(get_current_agent),
    db: aiosqlite.Connection = Depends(get_db)
):
    if agent_id != current_agent:
        raise HTTPException(status_code=403, detail="Cannot read another agent inbox")
    query = "SELECT id, from_agent, to_agent, message, thread_id, created_at, read, attachments FROM messages WHERE to_agent=?"
    params: list = [agent_id]
    if unread_only:
        query += " AND read=0"
    query += " ORDER BY created_at ASC LIMIT ?"
    params.append(limit)
    db.row_factory = aiosqlite.Row
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
    return [MessageRecord(
        id=r["id"], from_agent=r["from_agent"], to_agent=r["to_agent"],
        message=r["message"], thread_id=r["thread_id"],
        created_at=r["created_at"], read=bool(r["read"]),
        attachments=_deserialize_attachments(r["attachments"])
    ) for r in rows]

@app.post("/v1/messages/{message_id}/ack", response_model=AckResponse)
async def ack_message(
    message_id: str,
    agent: str = Depends(get_current_agent),
    db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute("SELECT to_agent FROM messages WHERE id=?", (message_id,)) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    if row[0] != agent:
        raise HTTPException(status_code=403, detail="Cannot ack another agent message")
    await db.execute("UPDATE messages SET read=1 WHERE id=?", (message_id,))
    await db.commit()
    return AckResponse(status="acknowledged")


REPORT_SHELL = """<!DOCTYPE html>
<html lang="es"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
         padding: 1.5rem; max-width: 720px; margin: 0 auto; line-height: 1.55; font-size: 16px; }}
  h1 {{ color: #58a6ff; font-size: 1.5rem; margin-bottom: 0.25rem; }}
  h2 {{ color: #7ee787; font-size: 1.15rem; margin: 1.5rem 0 0.5rem; }}
  h3 {{ color: #d2a8ff; font-size: 1rem; margin: 1rem 0 0.4rem; }}
  p {{ margin-bottom: 0.7rem; }}
  ul, ol {{ margin: 0 0 0.8rem 1.2rem; }}
  li {{ margin-bottom: 0.3rem; }}
  code {{ background: #1c2128; padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.9em; color: #e5c07b; }}
  pre {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 0.8rem; overflow-x: auto; margin-bottom: 0.8rem; }}
  pre code {{ background: transparent; padding: 0; color: #c9d1d9; font-size: 0.85em; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; font-size: 0.92em; }}
  th, td {{ text-align: left; padding: 0.55rem 0.7rem; border-bottom: 1px solid #30363d; vertical-align: top; }}
  th {{ background: #161b22; color: #58a6ff; font-weight: 600; }}
  tr:hover td {{ background: #161b22; }}
  a {{ color: #58a6ff; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
  .meta {{ color: #8b949e; font-size: 0.85rem; margin-bottom: 1.5rem; }}
  blockquote {{ border-left: 3px solid #30363d; padding: 0.3rem 0 0.3rem 0.8rem; color: #8b949e; margin-bottom: 0.8rem; }}
  .footer {{ color: #6e7681; font-size: 0.75rem; margin-top: 3rem; text-align: center; border-top: 1px solid #30363d; padding-top: 1rem; }}
</style></head>
<body>
<h1>{title}</h1>
<div class="meta">{meta}</div>
{html}
<div class="footer">Rocky · {meta}</div>
</body></html>"""


@app.post("/v1/reports", response_model=ReportCreateResponse)
async def create_report(
    body: ReportCreateRequest,
    agent: str = Depends(get_current_agent),
    db: aiosqlite.Connection = Depends(get_db),
):
    if agent != "rocky":
        raise HTTPException(status_code=403, detail="Only rocky can publish reports")
    slug = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc)
    ttl = body.ttl_hours if body.ttl_hours and body.ttl_hours > 0 else 168
    expires_at = (created_at + timedelta(hours=ttl)).isoformat()
    await db.execute(
        "INSERT INTO reports(slug,title,html,created_at,expires_at) VALUES(?,?,?,?,?)",
        (slug, body.title, body.html, created_at.isoformat(), expires_at),
    )
    await db.commit()
    return ReportCreateResponse(
        slug=slug,
        url=f"{PUBLIC_BASE_URL}/reports/{slug}",
        expires_at=expires_at,
    )


@app.get("/reports/{slug}", response_class=HTMLResponse)
async def read_report(
    slug: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT title, html, created_at, expires_at FROM reports WHERE slug=?", (slug,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    title, html, created_at, expires_at = row
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at)
            if datetime.now(timezone.utc) > exp:
                raise HTTPException(status_code=410, detail="Report expired")
        except ValueError:
            pass
    meta = f"publicado {created_at[:19].replace('T',' ')} UTC"
    return HTMLResponse(REPORT_SHELL.format(title=title, meta=meta, html=html))
