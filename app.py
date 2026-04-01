import os
import json
import httpx
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Any

# ── Config (set these as App Runner environment variables) ──────────────────
TEALIUM_MCP_URL = os.getenv(
    "TEALIUM_MCP_URL",
    "https://us-west-2.prod.developer.tealiumapis.com/v1/personalization/mcp",
)
TEALIUM_API_KEY = os.getenv("TEALIUM_API_KEY", "")
TEALIUM_ACCOUNT = os.getenv("TEALIUM_ACCOUNT", "")
TEALIUM_PROFILE = os.getenv("TEALIUM_PROFILE", "")
TEALIUM_ENGINE_ID = os.getenv("TEALIUM_ENGINE_ID", "")
TEALIUM_ORIGIN = os.getenv("TEALIUM_ORIGIN", "https://example.com")
TEALIUM_REFERER = os.getenv("TEALIUM_REFERER", "https://example.com")

# ── MCP JSON-RPC helpers ────────────────────────────────────────────────────

def mcp_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "X-Tealium-Api-Key": TEALIUM_API_KEY,
        "Origin": TEALIUM_ORIGIN,
        "Referer": TEALIUM_REFERER,
    }


def jsonrpc_request(method: str, params: dict, req_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params,
    }


async def call_mcp(method: str, params: dict) -> Any:
    """
    Send a single JSON-RPC request to the Tealium MCP endpoint.
    Handles both plain JSON and SSE-wrapped responses.
    """
    payload = jsonrpc_request(method, params)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(TEALIUM_MCP_URL, headers=mcp_headers(), json=payload)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            # Parse SSE stream — collect all data lines
            result_data = None
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    raw = line[len("data:"):].strip()
                    if raw and raw != "[DONE]":
                        try:
                            parsed = json.loads(raw)
                            if "result" in parsed:
                                result_data = parsed["result"]
                            elif "error" in parsed:
                                raise HTTPException(status_code=502, detail=parsed["error"])
                        except json.JSONDecodeError:
                            pass
            return result_data

        # Plain JSON response
        body = resp.json()
        if "error" in body:
            raise HTTPException(status_code=502, detail=body["error"])
        return body.get("result")


# ── MCP initialise (list available tools) ──────────────────────────────────

async def mcp_list_tools() -> list:
    result = await call_mcp("tools/list", {})
    return result.get("tools", []) if result else []


# ── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not TEALIUM_API_KEY:
        print("WARNING: TEALIUM_API_KEY is not set")
    yield


# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="Tealium MCP Client", lifespan=lifespan)


# ── Request / Response models ───────────────────────────────────────────────

class VisitorByAnonIdRequest(BaseModel):
    visitor_id: str
    suppress_not_found: Optional[bool] = False


class VisitorByAttributeRequest(BaseModel):
    attribute_id: str
    attribute_value: str
    suppress_not_found: Optional[bool] = False


def base_tool_params(suppress_not_found: bool = False) -> dict:
    """Common required params every Tealium MCP tool needs."""
    return {
        "account": TEALIUM_ACCOUNT,
        "profile": TEALIUM_PROFILE,
        "engineId": TEALIUM_ENGINE_ID,
        "Origin": TEALIUM_ORIGIN,
        "Referer": TEALIUM_REFERER,
        "suppressNotFound": suppress_not_found,
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/tools")
async def list_tools():
    """List all tools exposed by the Tealium MCP server."""
    try:
        tools = await mcp_list_tools()
        return {"tools": tools}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


@app.post("/visitor/anonymous")
async def get_visitor_by_anon_id(body: VisitorByAnonIdRequest):
    """
    Proxy: getPersonalizationContentByAnonymousId
    Retrieve visitor profile data using the Tealium anonymous visitor ID.
    """
    params = {
        **base_tool_params(body.suppress_not_found),
        "visitorId": body.visitor_id,
    }
    try:
        result = await call_mcp(
            "tools/call",
            {"name": "getPersonalizationContentByAnonymousId", "arguments": params},
        )
        return {"visitor_id": body.visitor_id, "data": result}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


@app.post("/visitor/attribute")
async def get_visitor_by_attribute(body: VisitorByAttributeRequest):
    """
    Proxy: getPersonalizationContentByVisitorId
    Retrieve visitor profile data using a known visitor ID attribute.
    """
    params = {
        **base_tool_params(body.suppress_not_found),
        "attributeId": body.attribute_id,
        "attributeValue": body.attribute_value,
    }
    try:
        result = await call_mcp(
            "tools/call",
            {"name": "getPersonalizationContentByVisitorId", "arguments": params},
        )
        return {
            "attribute_id": body.attribute_id,
            "attribute_value": body.attribute_value,
            "data": result,
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
