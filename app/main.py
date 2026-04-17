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
  body { background: #0d1117; color: #c9d1d9; font-family: monospace; padding: 2rem; }
  h1 { color: #58a6ff; font-size: 1.5rem; margin-bottom: 0.5rem; }
  .subtitle { color: #8b949e; margin-bottom: 2rem; }
  .status { display: inline-flex; align-items: center; gap: 0.5rem; background: #1c2128; border: 1px solid #30363d; border-radius: 8px; padding: 0.5rem 1rem; margin-bottom: 2rem; }
  .dot { width: 10px; height: 10px; background: #3fb950; border-radius: 50%; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
  .agents { display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }
  .agent { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; flex: 1; min-width: 200px; }
  .agent h2 { color: #58a6ff; margin-bottom: 0.5rem; }
  .agent p { color: #8b949e; font-size: 0.85rem; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; background: #161b22; border-radius: 8px; overflow: hidden; }
  th { background: #1c2128; color: #8b949e; padding: 0.75rem 1rem; text-align: left; font-size: 0.8rem; text-transform: uppercase; }
  td { padding: 0.75rem 1rem; border-top: 1px solid #21262d; font-size: 0.85rem; }
  td:first-child { color: #79c0ff; font-family: monospace; }
  .method { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }
  .get { background: #0d4a1f; color: #3fb950; }
  .post { background: #0d2d6b; color: #58a6ff; }
  .delete { background: #4a0d0d; color: #f85149; }
  .key-box { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; }
  .key-box h3 { color: #8b949e; font-size: 0.8rem; text-transform: uppercase; margin-bottom: 0.5rem; }
  .key { background: #0d1117; padding: 0.5rem; border-radius: 4px; font-family: monospace; font-size: 0.85rem; color: #f0883e; word-break: break-all; }
</style>
</head>
<body>
<h1>rocky-bridge</h1>
<p class="subtitle">Inter-Agent Message Queue — Rocky ↔ Bot-18</p>
<div class="status"><div class="dot"></div><span>Online</span></div>
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
<table>
  <thead><tr><th>Method</th><th>Endpoint</th><th>Description</th></tr></thead>
  <tbody>
    <tr><td><span class="method post">POST</span></td><td>/v1/send</td><td>Send a message to another agent</td></tr>
    <tr><td><span class="method get">GET</span></td><td>/v1/inbox/{agent}</td><td>Read pending messages</td></tr>
    <tr><td><span class="method post">POST</span></td><td>/v1/messages/{id}/ack</td><td>Acknowledge (mark as read)</td></tr>
    <tr><td><span class="method get">GET</span></td><td>/v1/health</td><td>Health check</td></tr>
  </tbody>
</table>
<div class="key-box">
  <h3>Bot-18 API Key</h3>
  <div class="key">8S26lZP4WqBe-6auoXCnk0RNZtg3SkSus5LTc5qfY5g</div>
</div>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def status_page():
    return STATUS_HTML

@app.get("/v1/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version="1.0.0")

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
