import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

TEALIUM_MCP_URL = "https://us-west-2.prod.developer.tealiumapis.com/v1/personalization/mcp"

class AskRequest(BaseModel):
    visitor_id: str

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/ask")
async def ask(req: AskRequest):
    api_key = os.environ.get("TEALIUM_API_KEY")

    if not api_key:
        raise HTTPException(status_code=500, detail="Missing TEALIUM_API_KEY")

    try:
        response = requests.post(
            TEALIUM_MCP_URL,
            headers={
                "X-Tealium-Api-Key": api_key,
                "Content-Type": "application/json"
            },
            json={
                "visitor_id": req.visitor_id
            },
            timeout=10
        )

        return {
            "status": "success",
            "tealium_response": response.json()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
