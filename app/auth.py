import os
from fastapi import Header, HTTPException

AGENT_KEYS = {
    os.getenv("ROCKY_API_KEY", ""): "rocky",
    os.getenv("BOT18_API_KEY", ""): "18",
}

def get_current_agent(x_api_key: str = Header(...)) -> str:
    agent = AGENT_KEYS.get(x_api_key)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return agent
