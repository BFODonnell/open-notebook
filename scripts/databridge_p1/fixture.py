"""Deterministic, isolated OpenAI-compatible provider; never a production route."""

from time import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
attempts: dict[str, int] = {}


@app.get("/attempts")
async def get_attempts(message: str):
    return {"count": attempts.get(message, 0)}


@app.post("/v1/chat/completions")
async def completion(request: Request):
    data = await request.json()
    message = str(data["messages"][-1]["content"])
    attempts[message] = attempts.get(message, 0) + 1
    if "fixture-fail" in str(data["messages"]):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": "Fixture provider temporarily unavailable",
                    "type": "server_error",
                }
            },
        )
    return {
        "id": "chatcmpl-" + str(uuid4()),
        "object": "chat.completion",
        "created": int(time()),
        "model": data["model"],
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "The fixture answer is 42.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 10},
            "completion_tokens_details": {"reasoning_tokens": 5},
        },
    }
