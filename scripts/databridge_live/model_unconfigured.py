"""Fail closed until a real model is configured for the live-data workspace."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()


@app.post("/v1/chat/completions")
async def unconfigured_model():
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "type": "invalid_request_error",
                "code": "model_not_found",
                "message": "This validation endpoint is not a live language model. Register and select a real provider model in Models before using notebook or source chat.",
            }
        },
    )
