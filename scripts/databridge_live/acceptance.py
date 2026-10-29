"""Live catalog/application acceptance. No direct download or database registration."""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx

STATE = Path("/app/data/databridge-live-state.json")


async def main(mode):
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:5055/api",
        headers={"Authorization": "Bearer " + os.environ["OPEN_NOTEBOOK_PASSWORD"]},
        timeout=240,
        trust_env=False,
    ) as client:

        async def api(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            if response.status_code != 200:
                # Application errors are sanitized; never log request headers.
                raise RuntimeError(
                    f"{path}: HTTP {response.status_code}: {response.text[:300]}"
                )
            return response.json()

        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        if mode == "search":
            page = await api(
                "GET",
                "/databridge/catalog/search",
                params={"q": "2022 2025 NTD Annual Data Service", "per_page": 10},
            )
            state["search"] = page
            print(
                json.dumps(
                    [{"id": r["id"], "title": r["title"]} for r in page["results"]],
                    indent=2,
                )
            )
        elif mode == "inspect":
            chosen = next(
                r
                for r in state["search"]["results"]
                if "Service (by Mode and Time Period)" in r["title"]
            )
            detail = await api("GET", "/databridge/catalog/datasets/" + chosen["id"])
            state["detail"] = detail
            print(
                json.dumps(
                    {
                        "title": detail["title"],
                        "resources": [
                            {
                                "id": r["id"],
                                "metadata": r["metadata"],
                                "classification": r["classification"],
                            }
                            for r in detail["resources"]
                        ],
                    },
                    indent=2,
                )
            )
        elif mode == "preflight":
            resource = next(
                r
                for r in state["detail"]["resources"]
                if r["classification"].get("adapter") == "csv"
            )
            state["resource_id"] = resource["id"]
            state["preflight"] = await api(
                "POST", "/databridge/catalog/resources/" + resource["id"] + "/preflight"
            )
            print(json.dumps(state["preflight"], indent=2))
        elif mode == "import":
            assert state["preflight"]["status"] == "ready", (
                "Import requires successful bounded preflight"
            )
            if "notebook_id" not in state:
                notebook = await api(
                    "POST",
                    "/notebooks",
                    json={
                        "name": "Live FTA NTD validation",
                        "description": "Official public data; no cross-source or causal comparisons",
                    },
                )
                state["notebook_id"] = notebook["id"]
            job = await api(
                "POST",
                "/databridge/imports",
                json={
                    "resource_id": state["resource_id"],
                    "notebook_id": state["notebook_id"],
                    "idempotency_key": str(uuid4()),
                },
            )
            state["job_id"] = job["id"]
            STATE.write_text(json.dumps(state))
            print(json.dumps({"job_id": job["id"], "status": job["status"]}))
        elif mode == "status":
            for _ in range(90):
                job = await api(
                    "GET",
                    "/databridge/imports/" + state["job_id"],
                    params={"notebook_id": state["notebook_id"]},
                )
                if job["status"] not in {"queued", "running"}:
                    break
                await asyncio.sleep(2)
            state["job"] = job
            print(json.dumps(job, indent=2))
        elif mode == "verify":
            from surreal_commands import get_command_status

            from open_notebook.database.repository import ensure_record_id, repo_query

            job = state["job"]
            stored = await repo_query(
                "SELECT * FROM $id", {"id": ensure_record_id(job["id"])}
            )
            command = await get_command_status(stored[0]["command_id"])
            assert command.status == "completed"
            assert job["download"]["sha256"] == state["preflight"]["download"]["sha256"]
            assert job["manifest"]["version_id"] == job["version_id"]
            assert {
                "queued",
                "downloading",
                "parsing",
                "publishing",
                "registering",
                "ready",
            } <= {h["stage"] for h in job["history"]}
            source = await api("GET", "/sources/" + job["source_id"])
            assert job["version_id"] in source["full_text"]
            linked = await repo_query(
                "SELECT id FROM reference WHERE in=$source AND out=$notebook",
                {
                    "source": ensure_record_id(job["source_id"]),
                    "notebook": ensure_record_id(state["notebook_id"]),
                },
            )
            assert linked
            state["verification"] = {
                "worker_command_id": stored[0]["command_id"],
                "worker_status": command.status,
                "download_hash_matches_preview": True,
                "notebook_source_linked": True,
                "immutable_version_matches_manifest": True,
                "processing_stages_present": True,
            }
            print(json.dumps(state["verification"], indent=2))
        elif mode in {"query", "restart"}:
            job = state["job"]
            assert job["status"] == "ready", "Import must be ready"
            context = await api(
                "GET",
                "/databridge/notebooks/" + state["notebook_id"] + "/datasets/context",
            )
            assert any(
                d["version_id"] == job["version_id"] for d in context["datasets"]
            )
            year = next(
                c["column"]
                for c in job["profile"]["columns"]
                if c["original"].lower().replace("_", " ") == "report year"
            )
            sql = f'SELECT "{year}" AS year, COUNT(*) AS rows FROM data GROUP BY "{year}" ORDER BY "{year}"'
            plan = await api(
                "POST",
                "/databridge/query/plans",
                json={
                    "connection_id": job["connection_id"],
                    "notebook_id": state["notebook_id"],
                    "sql": sql,
                },
            )
            assert "COUNT(*)" in plan["sql"] and "LIMIT" in plan["sql"]
            evidence = await api(
                "POST",
                "/databridge/query/plans/" + plan["id"] + "/execute",
                json={
                    "notebook_id": state["notebook_id"],
                    "approval_token": plan["approval_token"],
                },
            )
            assert (
                evidence["status"] == "success"
                and evidence["version_id"] == job["version_id"]
            )
            assert (
                sum(row["rows"] for row in evidence["rows"]) == job["profile"]["rows"]
            )
            if mode == "restart":
                assert evidence["rows"] == state["query"]["rows"]
                assert evidence["result_sha256"] == state["query"]["result_sha256"]
            state[mode] = evidence
            state["context"] = context
            print(json.dumps(evidence, indent=2))
        else:
            raise ValueError(mode)
        STATE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
