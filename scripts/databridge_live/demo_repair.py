"""Reproduce and verify the demo against real catalog/application endpoints."""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

STATE = Path("/app/data/databridge-demo-repair.json")


async def main(mode):
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:5055/api",
        headers={"Authorization": "Bearer " + os.environ["OPEN_NOTEBOOK_PASSWORD"]},
        timeout=240,
        trust_env=False,
    ) as client:

        async def api(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        if mode == "inspect":
            notebooks = await api("GET", "/notebooks")
            demo = next(n for n in notebooks if n["name"] == "Demo")
            state["notebook_id"] = demo["id"]
            jobs = await api(
                "GET", "/databridge/imports", params={"notebook_id": demo["id"]}
            )
            print(json.dumps({"demo": demo["id"], "jobs": jobs}, indent=2))
            state["datasets"] = []
            for title in [
                "2023 Annual Database Operating Expenses",
                "2023 Annual Database Agency Information",
                "2024 NTD Annual Data - Reporter Agency Information",
            ]:
                page = await api(
                    "GET",
                    "/databridge/catalog/search",
                    params={"q": title, "per_page": 10},
                )
                chosen = next(r for r in page["results"] if r["title"] == title)
                detail = await api(
                    "GET", "/databridge/catalog/datasets/" + chosen["id"]
                )
                state["datasets"].append(detail)
                print(json.dumps(detail, indent=2))
        elif mode == "verify":
            jobs = await api(
                "GET",
                "/databridge/imports",
                params={"notebook_id": state["notebook_id"]},
            )
            state["jobs"] = jobs
            print(
                json.dumps(
                    [
                        {
                            "id": j["id"],
                            "status": j["status"],
                            "stage": j["stage"],
                            "error": j.get("error"),
                            "source": j.get("source_id"),
                        }
                        for j in jobs
                    ],
                    indent=2,
                )
            )
            state["verified"] = []
            for job in jobs:
                if job["status"] != "ready":
                    continue
                scope = {"notebook_id": state["notebook_id"]}
                schema = await api(
                    "GET",
                    f"/databridge/mcp/servers/{job['connection_id']}/schema",
                    params=scope,
                )
                plan = await api(
                    "POST",
                    "/databridge/query/plans",
                    json={
                        **scope,
                        "connection_id": job["connection_id"],
                        "sql": "SELECT COUNT(*) AS rows FROM data",
                    },
                )
                result = await api(
                    "POST",
                    f"/databridge/query/plans/{plan['id']}/execute",
                    json={**scope, "approval_token": plan["approval_token"]},
                )
                assert int(result["rows"][0]["rows"]) == job["profile"]["rows"]
                state["verified"].append(
                    {"job_id": job["id"], "schema": schema, "evidence": result}
                )
                print(
                    json.dumps(
                        {
                            "job": job["id"],
                            "rows": result["rows"],
                            "columns": len(job["profile"]["columns"]),
                            "version": job["version_id"],
                            "download": job["download"],
                            "provenance": job.get("provenance"),
                        },
                        indent=2,
                    )
                )
        elif mode == "preflight":
            for dataset in state["datasets"]:
                detail = await api(
                    "GET", "/databridge/catalog/datasets/" + dataset["id"]
                )
                resource = next(
                    (
                        r
                        for r in detail["resources"]
                        if r["classification"].get("adapter") == "csv"
                    ),
                    detail["resources"][0],
                )
                check = await api(
                    "POST", f"/databridge/catalog/resources/{resource['id']}/preflight"
                )
                dataset["checked_resource"] = resource["id"]
                dataset["check"] = check
                print(
                    json.dumps(
                        {
                            "title": dataset["title"],
                            "classification": resource["classification"],
                            "preflight": {
                                k: v for k, v in check.items() if k != "profile"
                            },
                        },
                        indent=2,
                    )
                )
        elif mode == "chat":
            session = await api(
                "POST",
                "/chat/sessions",
                json={
                    "notebook_id": state["notebook_id"],
                    "title": "Demo repair: actual dataset row count",
                },
            )
            scope = {"notebook_id": state["notebook_id"], "session_id": session["id"]}
            result = await api(
                "POST",
                "/chat/execute",
                json={
                    "session_id": session["id"],
                    "message": "How many rows are in the imported 2024 NTD Annual Data - Reporter Agency Information dataset? Count all records in that dataset only. Do not infer ridership or expense trends.",
                    "context": {},
                },
            )
            state["chat_session"] = session["id"]
            state["chat_start"] = result
            STATE.write_text(json.dumps(state, indent=2))
            turn = result["messages"][-1]["database_turn_id"]
            reviewed = await api(
                "POST", f"/databridge/research/{turn}/review", json=scope
            )
            print(
                json.dumps(
                    {
                        "sql": reviewed["plan"]["sql"],
                        "version": reviewed["plan"]["version_id"],
                    },
                    indent=2,
                ),
                flush=True,
            )
            state["chat_reviewed"] = reviewed
            STATE.write_text(json.dumps(state, indent=2))
            sql = reviewed["plan"]["sql"]
            # The user authorized count verification; do not execute a different plan.
            assert (
                "COUNT(*)" in sql.upper()
                and "WHERE" not in sql.upper()
                and "GROUP BY" not in sql.upper()
            )
            answer = await api(
                "POST",
                f"/databridge/research/{turn}/execute",
                json={
                    **scope,
                    "plan_id": reviewed["plan"]["id"],
                    "approval_token": reviewed["approval_token"],
                },
            )
            state["chat_answer"] = answer
            assert answer["state"] == "completed", answer["state"]
            assert (
                answer["evidence"]["rows"][0]["row_count"]
                == state["jobs"][0]["profile"]["rows"]
            )
            print(
                json.dumps(
                    {
                        "state": answer["state"],
                        "answer": answer["answer"],
                        "sql": answer["evidence"]["sql"],
                        "rows": answer["evidence"]["rows"],
                    },
                    indent=2,
                )
            )
        STATE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
