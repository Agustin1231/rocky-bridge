import aiosqlite
import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "./data/bridge.db")

async def get_db():
    Path(DATABASE_URL).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                message TEXT NOT NULL,
                thread_id TEXT,
                created_at TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0,
                attachments TEXT
            )
        """)
        try:
            await db.execute("ALTER TABLE messages ADD COLUMN attachments TEXT")
        except aiosqlite.OperationalError:
            pass
        await db.commit()
        yield db
