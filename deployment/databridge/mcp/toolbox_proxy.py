"""Fixed-destination authenticated boundary for the isolated Toolbox service."""

import asyncio
import os
import secrets

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

SLOTS = asyncio.Semaphore(4)
HEADERS = {
    "content-type",
    "accept",
    "mcp-session-id",
    "mcp-protocol-version",
    "last-event-id",
}


async def proxy(request: Request):
    expected = "Bearer " + os.environ["DATABRIDGE_TOOLBOX_TOKEN"]
    if request.headers.get("origin") or not secrets.compare_digest(
        request.headers.get("authorization", "").encode(), expected.encode()
    ):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            return JSONResponse({"error": "Request too large"}, status_code=413)
    try:
        async with asyncio.timeout(15), SLOTS:
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                # Never forward Authorization or accept an upstream URL from callers.
                async with client.stream(
                    request.method,
                    "http://toolbox:5000/mcp",
                    headers={k: v for k, v in request.headers.items() if k in HEADERS},
                    content=bytes(body),
                ) as response:
                    result = bytearray()
                    async for chunk in response.aiter_bytes():
                        result.extend(chunk)
                        if len(result) > 524288:
                            raise ValueError()
                    return Response(
                        bytes(result),
                        status_code=response.status_code,
                        headers={
                            k: v for k, v in response.headers.items() if k in HEADERS
                        },
                    )
    except Exception:
        return JSONResponse(
            {"error": "Toolbox unavailable or response limit exceeded"}, status_code=502
        )


async def health(request: Request):
    return JSONResponse({"ready": True})


if __name__ == "__main__":
    if len(os.environ["DATABRIDGE_TOOLBOX_TOKEN"]) < 20:
        raise ValueError("A strong Toolbox boundary token is required")
    uvicorn.run(
        Starlette(
            routes=[
                Route("/mcp", proxy, methods=["GET", "POST", "DELETE"]),
                Route("/health", health),
            ]
        ),
        host="0.0.0.0",
        port=8080,
        log_level="warning",
    )
