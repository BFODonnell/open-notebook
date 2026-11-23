"""Verify UI-created sources through MCP, then independently from publisher CSVs.

Run inside the live app: uv run --no-sync python /app/verify_three_source.py
No fixtures, browser storage access, credentials in output or direct DB queries.
"""

import asyncio
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import httpx

from open_notebook.databridge.ingestion.download import fetch

NOTEBOOK = os.getenv(
    "DATABRIDGE_DEMO_NOTEBOOK", "Transit Population Weather - Verified Live Demo"
)


async def main():
    root = Path("/app/data/three-source-live")
    root.mkdir(exist_ok=True)
    async with httpx.AsyncClient(
        base_url="http://localhost:5055/api",
        headers={"Authorization": "Bearer " + os.environ["OPEN_NOTEBOOK_PASSWORD"]},
        timeout=240,
    ) as client:

        async def api(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        notebook = next(
            n for n in await api("GET", "/notebooks") if n["name"] == NOTEBOOK
        )
        scope = {"notebook_id": notebook["id"]}
        jobs = await api("GET", "/databridge/imports", params=scope)
        (root / "jobs.json").write_text(json.dumps(jobs, indent=2))
        assert len(jobs) == 4, [(j["title"], j["status"]) for j in jobs]
        assert all(j["status"] == "ready" for j in jobs), [
            (j["title"], j.get("error")) for j in jobs
        ]
        assert len({j["version_id"] for j in jobs}) == 4
        evidence = {}

        async def query(job, sql):
            plan = await api(
                "POST",
                "/databridge/query/plans",
                json={**scope, "connection_id": job["connection_id"], "sql": sql},
            )
            # Every statement below is explicit, read-only and within this user's
            # requested verification scope. Capture canonical SQL before executing.
            print("REVIEW", job["version_id"], plan["sql"], flush=True)
            return await api(
                "POST",
                f"/databridge/query/plans/{plan['id']}/execute",
                json={**scope, "approval_token": plan["approval_token"]},
            )

        for job in jobs:
            schema = await api(
                "GET",
                f"/databridge/mcp/servers/{job['connection_id']}/schema",
                params=scope,
            )
            count = await query(job, "SELECT COUNT(*) AS records FROM data")
            assert count["rows"][0]["records"] == job["profile"]["rows"]
            evidence[job["id"]] = {
                "schema": schema,
                "count": count,
                "provenance": job["provenance"],
            }
            print(
                "VERIFIED", job["title"], count["rows"], len(job["profile"]["columns"])
            )
        derived = next(j for j in jobs if j.get("analysis"))
        columns = {c["original"]: c["column"] for c in derived["profile"]["columns"]}
        sql = (
            "SELECT "
            + ", ".join(f'"{v}" AS "{k}"' for k, v in columns.items())
            + ' FROM data ORDER BY "'
            + columns["report_year"]
            + '"'
        )
        result = await query(derived, sql)
        evidence["comparison"] = result
        null_check = await query(
            derived,
            f'SELECT COUNT(*) AS withheld FROM data WHERE "{columns["trips_per_resident_context"]}" IS NULL',
        )
        evidence["withheld_ratios"] = null_check
        assert null_check["rows"][0]["withheld"] == sum(
            bool(r["missing_trips"] or r["questionable_trips"]) for r in result["rows"]
        )
        (root / "mcp-evidence.json").write_text(json.dumps(evidence, indent=2))
        print("COMPARISON", json.dumps(result["rows"], indent=2))

        files = {}
        for role, source in derived["analysis"]["sources"].items():
            path = root / (role + ".csv")
            path.unlink(missing_ok=True)
            download = await fetch(source["download"]["final_url"], path)
            assert download.sha256 == source["download"]["sha256"], (
                "Upstream changed; independent comparison needs the original bytes"
            )
            with path.open(encoding="utf-8-sig", newline="") as stream:
                files[role] = list(csv.DictReader(stream))
        # Independent Python CSV calculation, deliberately not comparison.combine
        # or DuckDB; match exact source bytes and cross-check published results.
        grouped = defaultdict(list)
        for row in files["transit"]:
            if (
                row["State"] == "MA"
                and row["Time Period"] == "Annual Total"
                and row["Report Year"] in {"2022", "2023", "2024", "2025"}
            ):
                grouped[int(row["Report Year"])].append(row)
        populations = [
            r
            for r in files["population"]
            if r["SUMLEV"] == "040" and r["STATE"] == "25"
        ]
        assert len(populations) == 1
        weather = {
            int(r["DATE"]): r for r in files["weather"] if r["STATION"] == "USW00014739"
        }
        verified = []
        for actual in result["rows"]:
            year = actual["report_year"]
            rows = grouped[year]
            assert (
                max(
                    Counter(
                        (r["NTD ID"], r["Mode"], r["Type Of Service"]) for r in rows
                    ).values()
                )
                == 1
            )
            numbers = []
            for row in rows:
                try:
                    numbers.append(
                        int(row["Unlinked Passenger Trips (UPT)"].replace(",", ""))
                    )
                except ValueError:
                    pass
            missing = len(rows) - len(numbers)
            flags = sum(bool(r["Unlinked Passenger Trips Questionable"]) for r in rows)
            population = int(populations[0][f"POPESTIMATE{year}"])
            assert actual["records"] == len(rows)
            assert actual["reported_trips"] == sum(numbers)
            assert actual["missing_trips"] == missing
            assert actual["questionable_trips"] == flags
            assert actual["population_july1"] == population
            if missing or flags:
                assert actual.get("trips_per_resident_context") is None
            else:
                assert (
                    abs(
                        float(actual["trips_per_resident_context"])
                        - sum(numbers) / population
                    )
                    < 1e-6
                )
            obs = weather[year]
            assert abs(float(actual["logan_tavg_c"]) - float(obs["TAVG"])) < 1e-6
            assert abs(float(actual["logan_prcp_mm"]) - float(obs["PRCP"])) < 1e-6
            assert actual["prcp_measurement_source_flags"] == obs["PRCP_ATTRIBUTES"]
            verified.append(
                {
                    "year": year,
                    "records": len(rows),
                    "reported_trips": sum(numbers),
                    "population": population,
                    "logan_tavg_c": obs["TAVG"],
                    "logan_prcp_mm": obs["PRCP"],
                }
            )
        # A new request UUID for the same source bytes must not create another job.
        from uuid import uuid4

        original = next(j for j in jobs if "Service (by Mode" in j["title"])
        await api(
            "POST", f"/databridge/catalog/resources/{original['resource_id']}/preflight"
        )
        retry = await api(
            "POST",
            "/databridge/imports",
            json={
                **scope,
                "resource_id": original["resource_id"],
                "idempotency_key": str(uuid4()),
            },
        )
        assert retry["id"] == original["id"]
        repeat_comparison = await api(
            "POST",
            "/databridge/comparisons/review",
            json={
                **scope,
                **{
                    role: source["id"]
                    for role, source in derived["analysis"]["sources"].items()
                },
            },
        )
        assert repeat_comparison["id"] == derived["id"]
        assert repeat_comparison["status"] == "ready"
        assert len(await api("GET", "/databridge/imports", params=scope)) == 4
        (root / "independent.json").write_text(json.dumps(verified, indent=2))
        print("INDEPENDENT_VERIFICATION_PASSED", json.dumps(verified))


if __name__ == "__main__":
    asyncio.run(main())
