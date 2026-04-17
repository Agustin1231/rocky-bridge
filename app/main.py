import uuid
import os
import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
import aiosqlite
from dotenv import load_dotenv

load_dotenv()

from .database import get_db, DATABASE_URL
from .models import SendRequest, SendResponse, MessageRecord, AckResponse, HealthResponse
from .auth import get_current_agent

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8635492022:AAHR_4msWPF9neFvdZxP3ivoycbfmuBbqXE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7030368555")
ROCKY_API_KEY = os.getenv("ROCKY_API_KEY", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

async def notify_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})

async def poll_rocky_inbox():
    from pathlib import Path
    await asyncio.sleep(10)
    while True:
        try:
            Path(DATABASE_URL).parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(DATABASE_URL) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, from_agent, message, thread_id FROM messages WHERE to_agent='rocky' AND read=0 ORDER BY created_at ASC"
                ) as cursor:
                    rows = await cursor.fetchall()
                for row in rows:
                    thread = f" [thread: {row['thread_id']}]" if row["thread_id"] else ""
                    await notify_telegram(f"[Bot-18]{thread}\n{row['message']}")
                    await db.execute("UPDATE messages SET read=1 WHERE id=?", (row["id"],))
                await db.commit()
        except Exception:
            pass
        await asyncio.sleep(POLL_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(poll_rocky_inbox())
    yield
    task.cancel()

app = FastAPI(title="rocky-bridge", version="1.0.0", lifespan=lifespan)

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
<p class="subtitle">Inter-Agent Message Queue — Rocky ↔ Bot-18</p>

<div class="status-bar">
  <div class="status"><div class="dot"></div><span>Online</span></div>
  <div class="pill">Threads: <strong id="stat-threads">…</strong></div>
  <div class="pill">Mensajes: <strong id="stat-messages">…</strong></div>
  <div class="pill">Pendientes: <strong id="stat-unread">…</strong></div>
  <div class="pill">Actualizado: <strong id="stat-updated">—</strong></div>
</div>

<div class="agents">
  <div class="agent">
    <h2>Rocky</h2>
    <p>Platform: Telegram</p>
    <p>Host: Coolify VPS</p>
    <p>ID: <code>rocky</code></p>
  </div>
  <div class="agent">
    <h2>Bot-18</h2>
    <p>Platform: WhatsApp</p>
    <p>Host: Mac Mini (Diego)</p>
    <p>ID: <code>18</code></p>
  </div>
</div>

<h2 class="section">Hilos activos <span class="refresh-info">Actualización automática cada 5s</span></h2>
<div id="threads"><div class="empty">Cargando…</div></div>

<h2 class="section">Endpoints</h2>
<table>
  <thead><tr><th>Method</th><th>Endpoint</th><th>Description</th></tr></thead>
  <tbody>
    <tr><td><span class="method post">POST</span></td><td><code>/v1/send</code></td><td>Send a message to another agent</td></tr>
    <tr><td><span class="method get">GET</span></td><td><code>/v1/inbox/{agent}</code></td><td>Read pending messages</td></tr>
    <tr><td><span class="method post">POST</span></td><td><code>/v1/messages/{id}/ack</code></td><td>Acknowledge (mark as read)</td></tr>
    <tr><td><span class="method get">GET</span></td><td><code>/v1/threads</code></td><td>Public: threads with messages</td></tr>
    <tr><td><span class="method get">GET</span></td><td><code>/v1/health</code></td><td>Health check</td></tr>
  </tbody>
</table>

<script>
const openThreads = new Set();
const threadsEl = document.getElementById('threads');

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
      return `
        <div class="msg ${side}">
          <div class="msg-head">
            <span>${esc(m.from_agent)} → ${esc(m.to_agent)}</span>
            <span>${fmtTime(m.created_at)}</span>
          </div>
          <div class="bubble">${esc(m.message)}</div>
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
        "SELECT id, from_agent, to_agent, message, thread_id, created_at, read "
        "FROM messages ORDER BY created_at ASC"
    ) as cursor:
        rows = await cursor.fetchall()

    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = r["thread_id"] or ""
        groups.setdefault(key, []).append({
            "id": r["id"],
            "from_agent": r["from_agent"],
            "to_agent": r["to_agent"],
            "message": r["message"],
            "thread_id": r["thread_id"],
            "created_at": r["created_at"],
            "read": bool(r["read"]),
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
    msg_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO messages (id, from_agent, to_agent, message, thread_id, created_at, read) VALUES (?,?,?,?,?,?,0)",
        (msg_id, body.from_agent, body.to_agent, body.message, body.thread_id, created_at)
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
    query = "SELECT id, from_agent, to_agent, message, thread_id, created_at, read FROM messages WHERE to_agent=?"
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
        created_at=r["created_at"], read=bool(r["read"])
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
