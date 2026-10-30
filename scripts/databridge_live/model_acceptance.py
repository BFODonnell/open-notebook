"""Explicitly authorized paid model check against the existing imported NTD data."""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx


async def main():
    if (
        sys.argv[1:] != ["--paid-model-check"]
        or os.getenv("LLM_MODEL") != "openrouter-gpt-6-astra"
    ):
        raise SystemExit(
            "This check makes paid GPT-6 Astra calls; explicit flag and configured model required"
        )
    imported = json.loads(Path("/app/data/databridge-live-state.json").read_text())
    output = Path("/app/data/databridge-live-model-check.json")
    state = {
        "model_alias": os.environ["LLM_MODEL"],
        "notebook_id": imported["notebook_id"],
        "version_id": imported["job"]["version_id"],
    }
    async with httpx.AsyncClient(
        base_url="http://localhost:5055/api",
        headers={"Authorization": "Bearer " + os.environ["OPEN_NOTEBOOK_PASSWORD"]},
        timeout=180,
    ) as client:

        async def api(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            assert response.status_code == 200, (
                path,
                response.status_code,
                response.text[:300],
            )
            return response.json()

        source = imported["job"]["source_id"]
        session = await api(
            "POST",
            f"/sources/{source}/chat/sessions",
            json={"source_id": source, "title": "Live GPT-6 Astra source validation"},
        )
        state["source_session"] = session["id"]
        output.write_text(json.dumps(state))
        response = await client.post(
            f"/sources/{source}/chat/sessions/{session['id']}/messages",
            json={
                "message": "In two sentences, describe what this source document contains. Distinguish schema/provenance documentation from raw database records. Do not invent ridership figures."
            },
        )
        response.raise_for_status()
        events = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert not any(event["type"] == "error" for event in events), [
            e for e in events if e["type"] == "error"
        ]
        state["source_answer"] = next(
            e["content"] for e in events if e["type"] == "ai_message"
        )
        assert (
            state["source_answer"]
            and "fixture answer is 42" not in state["source_answer"]
        )
        output.write_text(json.dumps(state))
        print("PASS: live source chat returned a real response", flush=True)

        session = await api(
            "POST",
            "/chat/sessions",
            json={
                "notebook_id": imported["notebook_id"],
                "title": "Live GPT-6 Astra NTD row counts",
            },
        )
        state["notebook_session"] = session["id"]
        scope = {"notebook_id": imported["notebook_id"], "session_id": session["id"]}
        result = await api(
            "POST",
            "/chat/execute",
            json={
                "session_id": session["id"],
                "message": "How many records are present in each Report Year in the imported NTD dataset? Count rows only, group and order by Report Year, include all years. Do not calculate ridership or compare sources.",
                "context": {},
            },
        )
        turn_id = result["messages"][-1]["database_turn_id"]
        state["turn_id"] = turn_id
        output.write_text(json.dumps(state))
        reviewed = await api(
            "POST", f"/databridge/research/{turn_id}/review", json=scope
        )
        sql = reviewed["plan"]["sql"]
        assert (
            "COUNT(*)" in sql
            and "GROUP BY" in sql
            and "c_7_report_year" in sql
            and "LIMIT" in sql
            and "WHERE" not in sql
        )
        print("PASS: live model generated authorized year-count SQL", flush=True)
        answer = await api(
            "POST",
            f"/databridge/research/{turn_id}/execute",
            json={
                **scope,
                "plan_id": reviewed["plan"]["id"],
                "approval_token": reviewed["approval_token"],
            },
        )
        state["research"] = answer
        output.write_text(json.dumps(state))
        assert answer["state"] == "completed", answer["state"]
        actual = sorted(sorted(row.values()) for row in answer["evidence"]["rows"])
        expected = sorted(sorted(row.values()) for row in imported["query"]["rows"])
        assert actual == expected
        assert answer["evidence"]["version_id"] == imported["job"]["version_id"]
        print(
            "PASS: real MCP counts and verified synthesis match the known live import",
            flush=True,
        )
        for _ in range(60):
            usage = await api("GET", "/databridge/usage")
            rows = [r for r in usage["records"] if r["session_id"] == session["id"]]
            if {"database_plan", "database_synthesize"} <= {r["task"] for r in rows}:
                break
            await asyncio.sleep(1)
        assert {"database_plan", "database_synthesize"} <= {r["task"] for r in rows}
        assert all(
            r["input_tokens"] is not None for r in rows if r["status"] == "success"
        )
        state["usage"] = rows
        state["budget_limit_usd"] = usage["budget_limit_usd"]
        output.write_text(json.dumps(state, indent=2))
        print(
            json.dumps(
                {
                    "status": "passed",
                    "model": state["model_alias"],
                    "source_chat": True,
                    "notebook_planning_mcp_synthesis": True,
                    "usage_records": len(rows),
                    "pricing_status": [r["pricing_status"] for r in rows],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
