"""Deterministic model fixture only; real Esperanto/LiteLLM carry every request."""

import json
from time import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from scripts.databridge_p1 import fixture as baseline

app = FastAPI()
FAIL_SYNTHESIS = False


@app.get("/attempts")
async def attempts(message: str):
    return await baseline.get_attempts(message)


@app.post("/synthesis-failure/{enabled}")
async def failure(enabled: bool):
    global FAIL_SYNTHESIS
    FAIL_SYNTHESIS = enabled
    return {"enabled": enabled}


@app.post("/v1/chat/completions")
async def completion(request: Request):
    data = await request.json()
    system = str(data["messages"][0]["content"])
    if (
        "bounded database planner" not in system
        and "select evidence for an Open Notebook" not in system
    ):
        return await baseline.completion(request)
    payload = json.loads(data["messages"][-1]["content"])
    question = payload["question"].lower()
    if "provider outage" in question or FAIL_SYNTHESIS and "evidence" in payload:
        return JSONResponse(
            {
                "error": {
                    "message": "Synthetic provider unavailable",
                    "type": "server_error",
                }
            },
            status_code=503,
        )
    if "evidence" in payload:
        rows = payload["evidence"]["rows"]
        cells = [
            {"row": i, "column": key, "value": value}
            for i, row in enumerate(rows)
            for key, value in row.items()
        ][:30]
        if "invalid numeric" in question and cells:
            cells[0]["value"] = 999999
        output = {
            "status": "supported" if cells else "insufficient",
            "cells": cells,
            "quotes": [],
        }
        if payload["documents"] and "document" in question:
            doc = payload["documents"][0]
            output["quotes"] = [
                {"source_id": doc["source_id"], "quote": doc["excerpt"][:150]}
            ]
    else:
        chosen = payload["datasets"][0]
        fields = {c["original"]: c["column"] for c in chosen["columns"]}
        year, measure = fields["Report Year"], fields["Unlinked Passenger Trips"]
        sql = f"SELECT SUM({measure}) AS trips FROM data"
        output = {"action": "query", "import_id": chosen["import_id"], "sql": sql}
        if "trend" in question:
            output.update(
                sql=f"SELECT {year} AS year, SUM({measure}) AS trips FROM data GROUP BY {year} ORDER BY {year}",
                year_column="year",
                value_column="trips",
            )
        if "empty" in question:
            output["sql"] = f"SELECT {year} AS year FROM data WHERE {year}=1900"
        if "unsafe" in question:
            output["sql"] = "DELETE FROM data"
        if "outside" in question:
            output["import_id"] = "db_import:outside"
        if "join" in question:
            output["sql"] = (
                "SELECT a.c_1_report_year FROM data a JOIN data b ON a.c_1_report_year=b.c_1_report_year"
            )
        if "incompatible" in question or "cross source" in question:
            output = {"action": "incompatible"}
        if "caused" in question:
            output = {"action": "unsupported"}
        if "missing denominator" in question:
            output = {"action": "insufficient"}
        if question == "hello documents":
            output = {"action": "document"}
    return {
        "id": "chatcmpl-" + uuid4().hex,
        "object": "chat.completion",
        "created": int(time()),
        "model": data["model"],
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(output)},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 60, "total_tokens": 260},
    }
