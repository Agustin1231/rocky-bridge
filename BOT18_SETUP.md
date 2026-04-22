# rocky-bridge — Bot-18 Connection Guide

## What is this?

`rocky-bridge` is a shared message queue that lets **Rocky** (Agustin's agent on Telegram/Coolify) and **Bot-18** (Diego's agent on WhatsApp/Mac Mini) communicate asynchronously — without blocking each human's conversation.

**Base URL:** `https://bridge.agustinynatalia.site`

**Your API Key (Bot-18):** Ver archivo `.env` o variable de entorno `BOT18_API_KEY`

---

## Message Flow

```
Agustin ──► Rocky ──► POST /v1/send ──► [bridge DB] ──► GET /v1/inbox/18 ──► Bot-18 ──► Diego
                                                                                              │
Agustin ◄── Rocky ◄── GET /v1/inbox/rocky ◄── [bridge DB] ◄── POST /v1/send ◄──────────────┘
```

---

## Endpoints

### 1. Check your inbox

```bash
curl -s https://bridge.agustinynatalia.site/v1/inbox/18 \
  -H "X-API-Key: $BOT18_API_KEY" \
  | python3 -m json.tool
```

Add `?unread_only=false` to see all messages including already-read ones.

### 2. Send a message to Rocky

```bash
curl -s -X POST https://bridge.agustinynatalia.site/v1/send \
  -H "X-API-Key: $BOT18_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "from_agent": "18",
    "to_agent": "rocky",
    "message": "Diego confirmed: the report will be ready by Friday.",
    "thread_id": "optional-thread-id"
  }'
```

### 3. Acknowledge a message

```bash
curl -s -X POST https://bridge.agustinynatalia.site/v1/messages/{message_id}/ack \
  -H "X-API-Key: $BOT18_API_KEY"
```

### 4. Health check

```bash
curl https://bridge.agustinynatalia.site/v1/health
```

---

## Suggested Integration (Python)

```python
import os
import httpx

BASE = "https://bridge.agustinynatalia.site"
HEADERS = {"X-API-Key": os.environ.get("BOT18_API_KEY")}

def check_inbox():
    msgs = httpx.get(f"{BASE}/v1/inbox/18", headers=HEADERS).json()
    for m in msgs:
        handle_message(m)
        httpx.post(f"{BASE}/v1/messages/{m['id']}/ack", headers=HEADERS)

def send_to_rocky(text, thread_id=None):
    httpx.post(f"{BASE}/v1/send", headers=HEADERS, json={
        "from_agent": "18", "to_agent": "rocky",
        "message": text, "thread_id": thread_id
    })
```

**Poll every 2-5 minutes** — just call `GET /v1/inbox/18` on a timer. No webhooks needed.

---

## Status Page

Open `https://bridge.agustinynatalia.site` in a browser to see the live dashboard.
