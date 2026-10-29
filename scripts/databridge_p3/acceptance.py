"""Real worker/download/parser/publication/MCP acceptance against synthetic TLS sources."""

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
from surreal_commands import get_command_status

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.databridge.ingestion.download import fetch
from open_notebook.databridge.ingestion.runtime import workspace

STATE = Path("/app/data/p3-acceptance.json")
CHECKS = []


def check(value, label):
    assert value, label
    CHECKS.append(label)
    print("PASS:", label, flush=True)


async def main(mode):
    assert os.getenv("DATAGOV_API_KEY") == "p3-synthetic-catalog-key-only"
    async with httpx.AsyncClient(
        base_url="http://localhost:5055",
        headers={"Authorization": "Bearer p1-fixture-password-only"},
        timeout=180,
    ) as client:

        async def api(method, path, body=None, expected=200):
            response = await client.request(method, "/api" + path, json=body)
            assert response.status_code == expected, (
                path,
                response.status_code,
                response.text[:600],
            )
            return response.json()

        async def wait(job, notebook):
            for _ in range(90):
                current = await api(
                    "GET",
                    "/databridge/imports/" + job["id"] + "?notebook_id=" + notebook,
                )
                if current["status"] not in {"queued", "running"}:
                    return current
                await asyncio.sleep(1)
            raise AssertionError("Worker import timed out")

        async def query(job, notebook):
            plan = await api(
                "POST",
                "/databridge/query/plans",
                {
                    "connection_id": job["connection_id"],
                    "notebook_id": notebook,
                    "sql": "SELECT SUM(c_4_unlinked_passenger_trips) AS trips FROM data",
                },
            )
            evidence = await api(
                "POST",
                "/databridge/query/plans/" + plan["id"] + "/execute",
                {"notebook_id": notebook, "approval_token": plan["approval_token"]},
            )
            check(
                evidence["rows"] == [{"trips": 700}],
                "Imported dataset returns exact synthetic total through real MCP",
            )
            return evidence

        if mode == "restart":
            state = json.loads(STATE.read_text())
            notebook = state["notebook"]
            for job in state["jobs"]:
                persisted = await api(
                    "GET",
                    "/databridge/imports/" + job["id"] + "?notebook_id=" + notebook,
                )
                check(
                    persisted["status"] == "ready"
                    and persisted["manifest"] == job["manifest"]
                    and persisted["download"] == job["download"],
                    "Version and provenance survive application/worker/database restart",
                )
                await query(persisted, notebook)
            context = await api(
                "GET", "/databridge/notebooks/" + notebook + "/datasets/context"
            )
            check(
                {j["version_id"] for j in state["jobs"]}
                <= {d["version_id"] for d in context["datasets"]}
                and context["conversational_analysis"]
                == (
                    os.getenv("DATABRIDGE_RESEARCH_ENABLED", "false").lower() == "true"
                ),
                "Notebook dataset discovery persists without claiming conversational analysis",
            )
        else:
            notebook = (
                await api(
                    "POST",
                    "/notebooks",
                    {
                        "name": "P3 acceptance notebook",
                        "description": "Synthetic public-data import tests",
                    },
                )
            )["id"]
            other = (
                await api(
                    "POST",
                    "/notebooks",
                    {"name": "P3 excluded scope", "description": "Scope test"},
                )
            )["id"]
            async with httpx.AsyncClient() as noauth:
                response = await noauth.get(
                    "http://localhost:5055/api/databridge/catalog/search"
                )
            check(
                response.status_code == 401,
                "Explorer retains upstream application authentication",
            )
            catalog = await api(
                "GET",
                "/databridge/catalog/search?q=National%20Transit%20Database&org_slug=dot&keyword=transit",
            )
            check(
                catalog["after"] == "fixture-next-cursor"
                and len(catalog["results"]) == 1,
                "Official v4-shaped search and agency/topic filters",
            )
            page = await api(
                "GET",
                "/databridge/catalog/search?q=National%20Transit%20Database&org_slug=dot&keyword=transit&after="
                + catalog["after"],
            )
            check(
                page["results"] == [] and page["after"] is None,
                "Cursor pagination uses after rather than page offsets",
            )
            detail = await api(
                "GET", "/databridge/catalog/datasets/" + catalog["results"][0]["id"]
            )
            check(
                "Synthetic" in detail["title"]
                and detail["metadata"]["dcat"]["temporal"] == "2022/2025",
                "Dataset metadata keeps publisher and report period",
            )
            resources = {r["metadata"]["title"]: r for r in detail["resources"]}
            check(
                resources["Excel adapter required"]["classification"]["status"]
                == "connector_required",
                "Unsupported Excel resource is explicitly classified",
            )
            check(
                resources["Blocked target"]["classification"]["status"]
                == "unavailable",
                "Unsafe publisher target is not importable",
            )
            for title, reason in [
                ("HTML masquerade", "FORMAT_MISMATCH"),
                ("Blocked redirect", "DOWNLOAD_BLOCKED"),
                ("Oversize transfer", "TRANSFER_LIMIT"),
            ]:
                result = await api(
                    "POST",
                    "/databridge/catalog/resources/"
                    + resources[title]["id"]
                    + "/preflight",
                )
                check(
                    result["status"] == "unavailable" and result["reason"] == reason,
                    title + " rejected by real download preflight",
                )
            error = await api(
                "GET", "/databridge/catalog/search?q=rate-limit", expected=502
            )
            check(
                "RATE_LIMITED" in json.dumps(error)
                and "p3-synthetic" not in json.dumps(error),
                "Catalog rate limit is visible without leaking API credentials",
            )
            jobs = []
            for kind in ["CSV", "JSON", "PARQUET", "ZIP"]:
                resource = resources["Synthetic " + kind]
                key = str(uuid4())
                body = {
                    "notebook_id": notebook,
                    "resource_id": resource["id"],
                    "idempotency_key": key,
                }
                if resource.get("preflight", {}).get("status") != "ready":
                    await api("POST", "/databridge/imports", body, 400)
                checked = await api(
                    "POST",
                    "/databridge/catalog/resources/" + resource["id"] + "/preflight",
                )
                check(
                    checked["status"] == "ready" and checked["profile"]["rows"] == 4,
                    kind + " real HTTPS transfer and isolated parser preview",
                )
                check(
                    checked["profile"]["preview"][0]["c_2_ntd_id"] == "00001",
                    kind + " preserves leading-zero agency identifiers",
                )
                queued = await api("POST", "/databridge/imports", body)
                duplicate = await api("POST", "/databridge/imports", body)
                check(
                    queued["id"] == duplicate["id"],
                    kind + " import request is idempotent",
                )
                done = await wait(queued, notebook)
                assert done["status"] == "ready", done.get("error")
                stored = await repo_query(
                    "SELECT * FROM $id", {"id": ensure_record_id(done["id"])}
                )
                command = await get_command_status(stored[0]["command_id"])
                # Queue bookkeeping can complete shortly after the durable ready event.
                for _ in range(20):
                    if command.status == "completed":
                        break
                    await asyncio.sleep(0.3)
                    command = await get_command_status(stored[0]["command_id"])
                check(
                    command.status == "completed",
                    kind + " executed by the real background worker",
                )
                check(
                    done["download"]["sha256"] == checked["download"]["sha256"]
                    and done["manifest"]["version_id"] == done["version_id"],
                    kind
                    + " provenance binds downloaded bytes to immutable publication",
                )
                stages = {h["stage"] for h in done["history"]}
                check(
                    {
                        "queued",
                        "downloading",
                        "parsing",
                        "publishing",
                        "registering",
                        "ready",
                    }
                    <= stages,
                    kind + " observable durable processing stages",
                )
                await query(done, notebook)
                await api(
                    "GET",
                    "/databridge/imports/" + done["id"] + "?notebook_id=" + other,
                    expected=404,
                )
                check(True, kind + " imported provenance is notebook scoped")
                source = await api("GET", "/sources/" + done["source_id"])
                check(
                    source["title"].startswith("Dataset schema:")
                    and source["notebooks"] == [notebook]
                    and source["embedded_chunks"] == 0
                    and "00001" not in source["full_text"],
                    kind
                    + " automatically attaches documentation without embedding raw rows",
                )
                jobs.append(done)
            context = await api(
                "GET", "/databridge/notebooks/" + notebook + "/datasets/context"
            )
            check(
                len(context["datasets"]) == 4
                and context["conversational_analysis"]
                == (
                    os.getenv("DATABRIDGE_RESEARCH_ENABLED", "false").lower() == "true"
                ),
                "Research-agent interface exposes active notebook versions and the DB-DATA-02 boundary",
            )
            check(
                (
                    await api(
                        "GET", "/databridge/notebooks/" + other + "/datasets/context"
                    )
                )["datasets"]
                == [],
                "Other notebook sees no imported database records",
            )
            # Crash recovery: a stale running record is requeued and reuses the
            # already-published immutable manifest, without another download.
            recovered = jobs[-1]
            await repo_query(
                "UPDATE $id SET status='running', stage='registering', lease_until='2000-01-01'",
                {"id": ensure_record_id(recovered["id"])},
            )
            pending = await api(
                "POST",
                "/databridge/imports/" + recovered["id"] + "/retry",
                {"notebook_id": notebook},
            )
            done = await wait(pending, notebook)
            check(
                done["status"] == "ready"
                and done["version_id"] == recovered["version_id"]
                and done["manifest"] == recovered["manifest"],
                "Interrupted registration reconciles the same immutable version",
            )
            jobs[-1] = done
            async with workspace() as folder:
                await fetch(
                    "https://data.transportation.gov/metrics",
                    folder / "metrics",
                    limit=4096,
                )
                metrics = json.loads((folder / "metrics").read_text())
            check(
                metrics["key_leaks"] == 0,
                "Data.gov API key never reaches publisher requests",
            )
            check(
                not any(
                    path.exists()
                    for job in jobs
                    for path in [
                        Path(os.environ["DATABRIDGE_DATA_ROOT"])
                        / "staging"
                        / (job["version_id"] + suffix)
                        for suffix in (".duckdb", ".duckdb.wal")
                    ]
                ),
                "No raw/staging files remain after successful imports",
            )
            STATE.write_text(json.dumps({"notebook": notebook, "jobs": jobs}))
        print(
            json.dumps({"mode": mode, "passed": len(CHECKS), "checks": CHECKS}),
            flush=True,
        )


if __name__ == "__main__":
    import sys

    asyncio.run(main(sys.argv[1]))
