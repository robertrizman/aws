import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp
from agents.model_settings import ModelSettings

app = FastAPI()

TEALIUM_MCP_URL = "https://us-west-2.prod.developer.tealiumapis.com/v1/personalization/mcp"

class AskRequest(BaseModel):
    visitor_id: str
    question: str | None = None

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/ask")
async def ask(req: AskRequest):
    api_key = os.environ.get("TEALIUM_API_KEY")
    openai_api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise HTTPException(status_code=500, detail="Missing TEALIUM_API_KEY")
    if not openai_api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")

    account = os.environ.get("TEALIUM_ACCOUNT", "success-robert-rizman")
    profile = os.environ.get("TEALIUM_PROFILE", "moments")
    engine_id = os.environ.get("TEALIUM_ENGINE_ID", "be462595-ebb5-4f1a-bd99-dae9daadadd9")

    prompt = req.question or (
        f"Use the Tealium MCP tools to determine whether visitor "
        f"{req.visitor_id} is part of the VIP Audience."
    )

    async with MCPServerStreamableHttp(
        name="Tealium MCP Streamable HTTP Server",
        params={
            "url": TEALIUM_MCP_URL,
            "headers": {
                "X-Tealium-Api-Key": api_key,
                "Origin": "https://example.com",
                "Referer": "https://example.com",
            },
            "timeout": 10,
        },
        max_retry_attempts=3,
    ) as server:
        agent = Agent(
            name="Assistant",
            instructions=(
                "Use the Tealium MCP tools to answer questions.\n"
                f"Tealium Account: {account}\n"
                f"Tealium Profile: {profile}\n"
                f"Tealium Engine ID: {engine_id}\n"
            ),
            mcp_servers=[server],
            model_settings=ModelSettings(tool_choice="required"),
        )

        result = await Runner.run(agent, prompt)
        return {"answer": result.final_output}
