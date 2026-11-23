"""Reviewed, fixed MA/Logan annual comparison; never arbitrary cross-file SQL."""

import csv
import hashlib
import secrets
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.databridge.ingestion import catalog, service
from open_notebook.databridge.ingestion.download import AcquisitionError, Download
from open_notebook.databridge.ingestion.publishers import CENSUS_URL
from open_notebook.databridge.mcp import service as mcp
from open_notebook.databridge.mcp.client import digest
from open_notebook.databridge.mcp.policy import POLICY_VERSION
from open_notebook.exceptions import InvalidInputError

TRANSIT_URL = "https://data.transportation.gov/api/v3/views/wwdp-t4re/export.csv?accessType=DOWNLOAD"
CONTRACT = {
    "version": "ma-logan-annual-v1",
    "geography": "NTD agency State MA maps to Census STATE 25, SUMLEV 040. Logan USW00014739 is a coastal Boston station, not a statewide weather estimate or an agency service-area exposure.",
    "time": "2022–2025 year labels: NTD annual agency report year (fiscal periods may differ), Census July 1 resident population (Vintage 2025), NOAA calendar-year summary. Descriptive contextual comparison only; no exact temporal exposure match or causal inference.",
    "grain": "Only Annual Total NTD rows. Require unique year/NTD ID/mode/type-of-service keys; sum once per year before attaching one population and one station record. UPT counts boardings, not unique people. Agency-headquarters state does not imply all trips occurred in that state.",
    "missing": "TRY_CAST comma-stripped UPT; retain missing and questionable counts. Per-resident ratio withheld if any UPT is missing/questionable. Weather NULLs stay missing; flagged precipitation withheld. Annual source/measurement flags do not certify daily completeness.",
    "join": "One row per report year, left join annual population and station by year; reject duplicate keys; absent years remain NULL. Never repeat population across transit rows.",
}


def queries(jobs: dict[str, dict]) -> list[dict]:
    def col(role, original):
        match = [
            c["column"]
            for c in jobs[role]["profile"]["columns"]
            if c["original"] == original
        ]
        if len(match) != 1:
            raise InvalidInputError(
                "Publisher schema changed: required column " + original
            )
        return '"' + match[0] + '"'

    year, state, period = (
        col("transit", c) for c in ("Report Year", "State", "Time Period")
    )
    trips = (
        "TRY_CAST(REPLACE("
        + col("transit", "Unlinked Passenger Trips (UPT)")
        + ", ',', '') AS BIGINT)"
    )
    flag = col("transit", "Unlinked Passenger Trips Questionable")
    where = f"{state}='MA' AND {period}='Annual Total' AND {year} BETWEEN 2022 AND 2025"
    statements = [
        (
            "transit",
            "transit",
            f"SELECT {year} AS report_year, COUNT(*) AS records, SUM({trips}) AS reported_trips, SUM(CASE WHEN {trips} IS NULL THEN 1 ELSE 0 END) AS missing_trips, SUM(CASE WHEN COALESCE({flag}, '') <> '' THEN 1 ELSE 0 END) AS questionable_trips FROM data WHERE {where} GROUP BY {year} ORDER BY {year}",
        )
    ]
    keys = ", ".join(col("transit", c) for c in ("NTD ID", "Mode", "Type Of Service"))
    for y in range(2022, 2026):
        statements.append(
            (
                "transit",
                f"grain_{y}",
                f"SELECT {keys}, COUNT(*) AS records FROM data WHERE {where} AND {year}={y} GROUP BY {keys}",
            )
        )
    population = ", ".join(
        f"{col('population', f'POPESTIMATE{y}')} AS pop_{y}" for y in range(2022, 2026)
    )
    statements.append(
        (
            "population",
            "population",
            f"SELECT {population} FROM data WHERE {col('population', 'SUMLEV')}='040' AND {col('population', 'STATE')}='25'",
        )
    )
    fields = ", ".join(
        f"{col('weather', c)} AS {a}"
        for c, a in [
            ("STATION", "station"),
            ("DATE", "report_year"),
            ("TAVG", "tavg"),
            ("PRCP", "prcp"),
            ("TAVG_ATTRIBUTES", "tavg_flags"),
            ("PRCP_ATTRIBUTES", "prcp_flags"),
        ]
    )
    statements.append(
        (
            "weather",
            "weather",
            f"SELECT {fields} FROM data WHERE {col('weather', 'STATION')}='USW00014739' AND {col('weather', 'DATE')} BETWEEN 2022 AND 2025 ORDER BY {col('weather', 'DATE')}",
        )
    )
    return [{"role": role, "name": name, "sql": sql} for role, name, sql in statements]


async def prepare(
    notebook_id: str, transit: str, population: str, weather: str
) -> dict:
    catalog.enabled()
    jobs = {
        role: service.public_job(await service.job_for(key, notebook_id))
        for role, key in {
            "transit": transit,
            "population": population,
            "weather": weather,
        }.items()
    }
    if any(j["status"] != "ready" for j in jobs.values()):
        raise InvalidInputError(
            "Import all three sources before preparing the comparison"
        )
    if (
        jobs["transit"]["resource_snapshot"].get("downloadURL") != TRANSIT_URL
        or jobs["population"]["resource_snapshot"].get("downloadURL") != CENSUS_URL
    ):
        raise InvalidInputError(
            "Select the reviewed NTD Service and Census Vintage 2025 distributions"
        )
    weather_selection = (
        jobs["weather"]["resource_snapshot"]
        .get("rights_evidence", {})
        .get("selection", {})
    )
    if any(
        weather_selection.get(k) != v
        for k, v in {
            "dataset": "global-summary-of-the-year",
            "stations": "USW00014739",
            "units": "metric",
            "dataTypes": "TAVG,PRCP",
            "startDate": "2022-01-01",
            "endDate": "2025-12-31",
        }.items()
    ):
        raise InvalidInputError(
            "Select Boston Logan, 2022–2025, TAVG and PRCP, metric units"
        )
    sources = {
        role: {
            k: j[k]
            for k in (
                "id",
                "version_id",
                "connection_id",
                "manifest",
                "download",
                "provenance",
            )
        }
        for role, j in jobs.items()
    }
    identity = digest(
        {
            "notebook": notebook_id,
            "versions": {r: s["version_id"] for r, s in sources.items()},
            "contract": CONTRACT,
            "policy": POLICY_VERSION,
        }
    )[:40]
    job_id = "db_import:" + identity
    existing = await repo_query("SELECT * FROM $id", {"id": ensure_record_id(job_id)})
    if existing and existing[0]["status"] != "awaiting_approval":
        return service.public_job(existing[0])
    reviewed = []
    for statement in queries(jobs):
        plan = await mcp.plan(
            sources[statement["role"]]["connection_id"],
            notebook_id,
            statement["sql"],
            None,
            {},
        )
        plan.pop("approval_token")
        reviewed.append({**statement, "sql": plan["sql"], "plan": plan})
    token = secrets.token_urlsafe(32)
    payload = {
        "title": "Massachusetts transit, population and Boston Logan weather — annual context",
        "dataset_id": str(uuid5(NAMESPACE_URL, notebook_id + identity)),
        "catalog_snapshot": {
            "catalog_identifier": "analysis:" + identity,
            "publisher": "Open Notebook reviewed analysis",
            "description": " ".join(CONTRACT.values()),
            "metadata": {"dcat": {"rights": "public domain"}},
        },
        "resource_snapshot": {},
        "catalog_id": "analysis:" + identity,
        "analysis": {
            "contract": CONTRACT,
            "sources": sources,
            "queries": reviewed,
            "policy": POLICY_VERSION,
            "approval_hash": digest(token),
            "expires_at": service.future(900),
        },
        "provenance": {"analysis_contract": CONTRACT, "sources": sources},
        "queued_at": mcp.now(),
        "history": [{"stage": "awaiting_approval", "at": mcp.now()}],
    }
    if existing:
        updated = await repo_query(
            "UPDATE $id SET payload=$payload WHERE status='awaiting_approval' RETURN AFTER",
            {"id": ensure_record_id(job_id), "payload": payload},
        )
        if not updated:
            raise InvalidInputError("Comparison is already active; reload its status")
    else:
        await repo_query(
            "CREATE $id CONTENT $data",
            {
                "id": ensure_record_id(job_id),
                "data": {
                    "notebook_id": notebook_id,
                    "resource_id": "analysis:" + identity,
                    "version_id": str(uuid4()),
                    "status": "awaiting_approval",
                    "stage": "awaiting_approval",
                    "lease_until": service.future(900),
                    "cancel_requested": False,
                    "payload": payload,
                },
            },
        )
    return {
        **service.public_job(await service.job_for(job_id, notebook_id)),
        "approval_token": token,
    }


async def approve(job_id: str, notebook_id: str, token: str) -> dict:
    job = await service.job_for(job_id, notebook_id)
    analysis = job["payload"].get("analysis", {})
    if not analysis or not secrets.compare_digest(
        analysis.get("approval_hash", ""), digest(token)
    ):
        raise InvalidInputError("Comparison approval is invalid; review again")
    claimed = await repo_query(
        "UPDATE $id SET status='queued', stage='queued', payload.analysis.approved=true, lease_until=$lease WHERE status='awaiting_approval' AND payload.analysis.approval_hash=$hash AND payload.analysis.expires_at > $now RETURN AFTER",
        {
            "id": ensure_record_id(job_id),
            "hash": digest(token),
            "now": mcp.now(),
            "lease": service.future(60),
        },
    )
    if not claimed:
        raise InvalidInputError(
            "Comparison approval expired or was already used; reload its status"
        )
    await service.submit(job_id)
    return service.public_job(await service.job_for(job_id, notebook_id))


def combine(evidence: dict) -> list[dict]:
    transit = evidence["transit"]["rows"]
    if len({r["report_year"] for r in transit}) != len(transit):
        raise AcquisitionError("COMPARISON_DUPLICATE_YEAR")
    for row in transit:
        grain = evidence[f"grain_{row['report_year']}"]["rows"]
        if (
            len(grain) >= 100
            or any(r["records"] != 1 for r in grain)
            or len(grain) != row["records"]
        ):
            raise AcquisitionError("TRANSIT_GRAIN_REVIEW_REQUIRED")
    populations = evidence["population"]["rows"]
    if len(populations) != 1:
        raise AcquisitionError("POPULATION_GEOGRAPHY_REVIEW_REQUIRED")
    weather = evidence["weather"]["rows"]
    if len({r["report_year"] for r in weather}) != len(weather):
        raise AcquisitionError("WEATHER_DUPLICATE_YEAR")
    by_year = {int(r["report_year"]): r for r in weather}
    output = []
    for row in transit:
        y = int(row["report_year"])
        pop = populations[0].get(f"pop_{y}")
        obs = by_year.get(y, {})
        prcp_flags = str(obs.get("prcp_flags") or "")
        parts = prcp_flags.split(",")
        usable_prcp = (
            len(parts) == 2 and not parts[0].strip() and bool(parts[1].strip())
        )
        usable_temp = bool(str(obs.get("tavg_flags") or "").strip())
        trips = row.get("reported_trips")
        ratio = (
            trips / pop
            if pop
            and trips is not None
            and row["missing_trips"] == 0
            and row["questionable_trips"] == 0
            else None
        )
        output.append(
            {
                **row,
                "reported_trips": trips,
                "state_fips": "25",
                "population_july1": pop,
                "population_vintage": 2025,
                "trips_per_resident_context": ratio,
                "logan_tavg_c": obs.get("tavg") if usable_temp else None,
                "logan_prcp_mm": obs.get("prcp") if usable_prcp else None,
                "weather_station": "USW00014739",
                "tavg_source_flag": obs.get("tavg_flags"),
                "prcp_measurement_source_flags": obs.get("prcp_flags"),
                "weather_annual_record_available": bool(obs),
            }
        )
    if not output:
        raise AcquisitionError("COMPARISON_NO_OVERLAP")
    return output


async def materialize(payload: dict, notebook_id: str, folder: Path) -> Download:
    analysis = payload["analysis"]
    if (
        not analysis.get("approved")
        or analysis["policy"] != POLICY_VERSION
        or analysis["contract"] != CONTRACT
    ):
        raise AcquisitionError("COMPARISON_REVIEW_REQUIRED")
    evidence = {}
    for statement in analysis["queries"]:
        source = analysis["sources"][statement["role"]]
        job = service.public_job(await service.job_for(source["id"], notebook_id))
        if (
            job["status"] != "ready"
            or job["version_id"] != source["version_id"]
            or job["manifest"] != source["manifest"]
        ):
            raise AcquisitionError("COMPARISON_SOURCE_CHANGED")
        plan = await mcp.plan(
            source["connection_id"], notebook_id, statement["sql"], None, {}
        )
        if any(
            plan[k] != statement["plan"][k]
            for k in (
                "sql",
                "revision",
                "fingerprint",
                "version_id",
                "dataset_sha256",
                "policy",
            )
        ):
            raise AcquisitionError("COMPARISON_REVIEW_REQUIRED")
        evidence[statement["name"]] = await mcp.execute(
            plan["id"], plan["approval_token"], notebook_id
        )
    rows = combine(evidence)
    path = folder / "payload"
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload["provenance"].update(
        query_evidence=evidence,
        transformation_sha256=digest(CONTRACT),
        result_sha256=digest(rows),
    )
    payload["preflight"] = {"adapter": "csv"}
    raw = path.read_bytes()
    return Download(
        hashlib.sha256(raw).hexdigest(),
        len(raw),
        payload["catalog_snapshot"]["catalog_identifier"],
        "text/csv",
        None,
        None,
    )
