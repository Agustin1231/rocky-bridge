# rocky-bridge

Inter-agent message queue between Rocky (Telegram/Coolify) and Bot-18 (WhatsApp/Mac Mini).

**Live:** https://bridge.agustinynatalia.site

## Stack

- FastAPI + Python 3.12 + aiosqlite (SQLite)
- Docker deployed on Coolify

## Endpoints

```
POST /v1/send               → queue a message
GET  /v1/inbox/{agent}      → read pending messages
POST /v1/messages/{id}/ack  → mark as read
GET  /v1/health             → health check
GET  /                      → status dashboard
```

Auth: `X-API-Key` header.

## Setup

```bash
cp .env.example .env  # fill in API keys
docker compose up -d
```

## For Bot-18

See `BOT18_SETUP.md` or open `guide.html` in a browser.
