"""Synthetic official-v4-shaped catalog plus HTTPS publisher, never live NTD data."""

import asyncio
import io
import json
import tempfile
import zipfile
from pathlib import Path

import duckdb
from fastapi import FastAPI, Request
from starlette.responses import (
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

app = FastAPI()
CSV = b"Report Year,NTD ID,County FIPS,Unlinked Passenger Trips\n2022,00001,01001,100\n2023,00001,01001,150\n2024,00001,01001,200\n2025,00001,01001,250\n"
ROWS = [
    {
        "Report Year": y,
        "NTD ID": "00001",
        "County FIPS": "01001",
        "Unlinked Passenger Trips": trips,
    }
    for y, trips in zip(range(2022, 2026), [100, 150, 200, 250])
]
with tempfile.TemporaryDirectory() as folder:
    file = Path(folder) / "fixture.parquet"
    with duckdb.connect() as db:
        db.execute(
            'CREATE TABLE source ("Report Year" INTEGER, "NTD ID" VARCHAR, "County FIPS" VARCHAR, "Unlinked Passenger Trips" INTEGER)'
        )
        db.executemany(
            "INSERT INTO source VALUES (?,?,?,?)", [list(row.values()) for row in ROWS]
        )
        db.execute("COPY source TO ? (FORMAT PARQUET)", [str(file)])
    PARQUET = file.read_bytes()
zipped = io.BytesIO()
with zipfile.ZipFile(zipped, "w", zipfile.ZIP_DEFLATED) as archive:
    archive.writestr(zipfile.ZipInfo("sample.csv"), CSV)
ZIP = zipped.getvalue()
COUNTS = {"catalog": 0, "publisher": 0, "key_leaks": 0}
CHANGED = False


@app.get("/technology/datagov/v4/search")
async def search(
    request: Request,
    q: str = "",
    after: str = "",
    org_slug: str = "",
    keyword: str = "",
    per_page: int = 10,
):
    COUNTS["catalog"] += 1
    if request.headers.get("X-Api-Key") != "p3-synthetic-catalog-key-only":
        return JSONResponse({}, 403)
    if q == "rate-limit":
        return JSONResponse({}, 429, headers={"retry-after": "1"})
    if after:
        return {"results": [], "sort": "relevance"}
    resources = [
        {
            "title": "Synthetic " + kind.upper(),
            "format": kind.upper(),
            "downloadURL": "https://data.transportation.gov/files/sample." + kind,
        }
        for kind in ["csv", "json", "parquet", "zip"]
    ]
    resources += [
        {
            "title": "Excel adapter required",
            "format": "XLSX",
            "downloadURL": "https://data.transportation.gov/files/sample.xlsx",
        },
        {
            "title": "Blocked target",
            "format": "CSV",
            "downloadURL": "https://localhost/secret.csv",
        },
        {
            "title": "HTML masquerade",
            "format": "CSV",
            "downloadURL": "https://data.transportation.gov/files/html.csv",
        },
        {
            "title": "Blocked redirect",
            "format": "CSV",
            "downloadURL": "https://data.transportation.gov/files/redirect.csv",
        },
        {
            "title": "Oversize transfer",
            "format": "CSV",
            "downloadURL": "https://data.transportation.gov/files/large.csv",
        },
        {
            "title": "Slow transfer",
            "format": "CSV",
            "downloadURL": "https://data.transportation.gov/files/slow.csv",
        },
    ]
    dcat = {
        "identifier": "databridge-synthetic-ntd",
        "title": "Synthetic NTD 2022–2025 service fixture",
        "description": "Synthetic values only. Not official NTD statistics. <script>alert('untrusted metadata')</script>",
        "publisher": {"name": "DataBridge synthetic fixture"},
        "accessLevel": "public",
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
        "temporal": "2022/2025",
        "spatial": "Synthetic county 01001; not an agency service-area crosswalk",
        "modified": "2026-10-29",
        "distribution": resources,
    }
    return {
        "results": [
            {
                "identifier": dcat["identifier"],
                "dcat": dcat,
                "organization": {"slug": "dot"},
                "last_harvested_date": "2026-10-29",
            }
        ],
        "after": "fixture-next-cursor",
        "sort": "relevance",
    }


@app.get("/files/{name}")
async def download_file(name: str, request: Request):
    COUNTS["publisher"] += 1
    if "x-api-key" in request.headers:
        COUNTS["key_leaks"] += 1
        return Response(status_code=403)
    if name == "html.csv":
        return Response("<html>Login required</html>", media_type="text/html")
    if name == "redirect.csv":
        return RedirectResponse("https://localhost/private", status_code=302)
    if name == "large.csv":
        return Response(b"x", headers={"content-length": str(33 * 1024**2)})
    if name == "slow.csv":

        async def stream():
            yield CSV[:20]
            await asyncio.sleep(8)
            yield CSV[20:]

        return StreamingResponse(stream(), media_type="text/csv")
    bodies = {
        "sample.csv": (CSV.replace(b",250", b",999") if CHANGED else CSV, "text/csv"),
        "sample.json": (json.dumps(ROWS).encode(), "application/json"),
        "sample.parquet": (PARQUET, "application/vnd.apache.parquet"),
        "sample.zip": (ZIP, "application/zip"),
    }
    if name not in bodies:
        return Response(status_code=404)
    content, media_type = bodies[name]
    return Response(content, media_type=media_type, headers={"etag": "synthetic-v1"})


@app.get("/metrics")
async def metrics():
    return COUNTS


@app.post("/change")
async def change():
    global CHANGED
    CHANGED = not CHANGED
    return {"changed": CHANGED}
