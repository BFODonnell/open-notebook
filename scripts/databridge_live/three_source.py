"""Live diagnostics for the three-source workflow. Run inside the live app."""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

SQL = """SELECT c_7_report_year AS report_year, COUNT(*) AS records,
SUM(TRY_CAST(REPLACE(c_51_unlinked_passenger_trips__upt, ',', '') AS BIGINT)) AS reported_trips,
SUM(CASE WHEN TRY_CAST(REPLACE(c_51_unlinked_passenger_trips__upt, ',', '') AS BIGINT) IS NULL THEN 1 ELSE 0 END) AS missing_or_unparseable
FROM data WHERE c_3_state = 'MA' AND c_20_time_period = 'Annual Total'
GROUP BY c_7_report_year ORDER BY c_7_report_year"""
URLS = {
    "population": "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv",
    "weather": "https://www.ncei.noaa.gov/access/services/data/v1?dataset=global-summary-of-the-year&startDate=2022-01-01&endDate=2025-12-31&stations=USW00014739&dataTypes=TAVG,PRCP&format=csv&units=metric&includeAttributes=true&includeStationName=true&includeStationLocation=true",
    "noaa_metadata": "https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc%3AC00947/xml",
    "census_rights": "https://www.census.gov/about/policies/copyright.html",
}


async def main():
    from open_notebook.databridge.ingestion.download import AcquisitionError, fetch

    root = Path("/app/data/three-source-probes") / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    root.mkdir(parents=True)
    async with httpx.AsyncClient(
        base_url="http://localhost:5055/api",
        headers={"Authorization": "Bearer " + os.environ["OPEN_NOTEBOOK_PASSWORD"]},
        timeout=180,
    ) as client:
        notebooks = (await client.get("/notebooks")).json()
        notebook = next(n for n in notebooks if "Full Demo" in n["name"])
        jobs = (
            await client.get(
                "/databridge/imports", params={"notebook_id": notebook["id"]}
            )
        ).json()
        job = next(
            j
            for j in jobs
            if j.get("version_id") == "de1163f2-eb82-407d-baf6-c62347bad636"
        )
        (root / "transit-job.json").write_text(json.dumps(job, indent=2))
        scope = {"notebook_id": notebook["id"], "connection_id": job["connection_id"]}
        response = await client.post(
            "/databridge/query/plans", json={**scope, "sql": SQL}
        )
        review = response.json()
        review.pop("approval_token", None)
        print("SQL", response.status_code, json.dumps(review)[:1000])
        (root / "sql-review.json").write_text(json.dumps(review, indent=2))
        session = (
            await client.post(
                "/chat/sessions",
                json={
                    "notebook_id": notebook["id"],
                    "title": "Reproduce annual UPT aggregation",
                },
            )
        ).json()
        answer = await client.post(
            "/chat/execute",
            json={
                "session_id": session["id"],
                "context": {},
                "message": "For the imported NTD Service dataset, calculate the sum of Unlinked Passenger Trips (UPT) by Report Year where State is MA and Time Period is Annual Total. Convert comma-formatted trip values to numbers. Include the number of records for each year and missing or unparseable trip counts. Do not infer causality.",
            },
        )
        (root / "chat-probe.json").write_text(answer.text)
        print("CHAT", answer.status_code, answer.text[-1800:])
        result = (
            await client.get(
                "/databridge/catalog/search",
                params={"q": "Global Summary of the Year", "per_page": 5},
            )
        ).json()
        (root / "noaa-catalog.json").write_text(json.dumps(result, indent=2))
        print(
            "NOAA CATALOG",
            [
                (
                    r["title"],
                    r["metadata"].get("access_level"),
                    r["metadata"].get("dcat", {}).get("rights"),
                )
                for r in result.get("results", [])
            ],
        )

    async def download(name, url):
        target = root / name
        target.unlink(missing_ok=True)
        try:
            result = await fetch(
                url,
                target,
                allowed={"www2.census.gov", "www.census.gov", "www.ncei.noaa.gov"},
            )
            print(name, result)
            if name in {"weather", "population"}:
                print(target.read_text()[:1600])
        except AcquisitionError as error:
            print(name, error.code)

    await asyncio.gather(*(download(k, v) for k, v in URLS.items()))


if __name__ == "__main__":
    asyncio.run(main())
