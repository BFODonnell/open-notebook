"""Regression fixtures for demo defects; no live publisher traffic."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from open_notebook.databridge.ingestion import catalog, discovery, service
from open_notebook.databridge.ingestion.download import Download
from open_notebook.databridge.ingestion.parser import stage

URL = "https://www.transit.dot.gov/ntd/data-product/2023-annual-database-operating-expenses"
CSV = "https://data.transportation.gov/export.csv"
PUBLIC = {
    "access_level": "public",
    "dcat": {"accessLevel": "public", "rights": ["CC0 1.0"]},
}


@pytest.mark.asyncio
async def test_large_distribution_list_does_not_hide_other_search_results(monkeypatch):
    monkeypatch.setattr(catalog, "enabled", lambda: None)
    monkeypatch.setattr(catalog, "repo_query", AsyncMock(return_value=[]))
    monkeypatch.setattr(catalog, "repo_upsert", AsyncMock())
    monkeypatch.setattr(
        catalog,
        "request",
        AsyncMock(
            return_value={
                "results": [
                    {"dcat": {"title": "Oversized", "distribution": [{}] * 31}},
                    {
                        "access_level": "public",
                        "dcat": {
                            "title": "Usable",
                            "rights": ["CC0 1.0"],
                            "distribution": [{"downloadURL": CSV}],
                        },
                    },
                ]
            }
        ),
    )
    page = await catalog.search("weather", "", "", "", 5)
    assert len(page["results"]) == 2
    assert page["results"][0]["resources_status"] == "CATALOG_RECORD_LIMIT"
    assert page["results"][0]["resources"] == []
    assert len(page["results"][1]["resources"]) == 1


@pytest.mark.parametrize(
    "declaration",
    [
        "CC0 1.0",
        [" CC0 1.0 "],
        {"@id": "https://creativecommons.org/publicdomain/zero/1.0/"},
        [{"name": "CC0-1.0"}],
    ],
)
@pytest.mark.parametrize("scope", ["root", "dcat", "resource"])
@pytest.mark.parametrize("field", ["rights", "license"])
def test_explicit_rights_across_catalog_schema(declaration, scope, field):
    metadata: dict = {"access_level": "public", "dcat": {"accessLevel": "public"}}
    resource = {"downloadURL": URL, "mediaType": "text/html"}
    target = (
        metadata
        if scope == "root"
        else metadata["dcat"]
        if scope == "dcat"
        else resource
    )
    target[field] = declaration
    assert (
        catalog.classify(metadata, resource)["reason"]
        == "LANDING_PAGE_DISCOVERY_REQUIRED"
    )


@pytest.mark.parametrize(
    "rights",
    [
        None,
        "",
        [],
        "public",
        ["public"],
        "permission required",
        ["CC0 1.0", "noncommercial"],
        {"unknown": "CC0 1.0"},
    ],
)
def test_ambiguous_missing_or_restrictive_rights_fail_closed(rights):
    assert (
        catalog.classify(
            {"accessLevel": "public", "rights": rights}, {"downloadURL": CSV}
        )["reason"]
        == "RIGHTS_REVIEW_REQUIRED"
    )


def test_resource_restrictions_override_dataset_license():
    assert (
        catalog.classify(PUBLIC, {"downloadURL": CSV, "rights": "all rights reserved"})[
            "reason"
        ]
        == "RIGHTS_REVIEW_REQUIRED"
    )
    assert (
        catalog.classify(PUBLIC, {"downloadURL": CSV, "accessLevel": "non-public"})[
            "reason"
        ]
        == "ACCESS_RESTRICTED"
    )
    assert (
        catalog.classify(PUBLIC, {"downloadURL": "https://localhost/data.csv"})[
            "reason"
        ]
        == "HOST_POLICY_REJECTED"
    )


def test_discovery_bounds_and_deduplicates_safe_downloads():
    parser = discovery.Downloads(URL)
    parser.feed(
        '<a href="/files/a.xlsx">Expenses</a><a href="/files/a.xlsx"> same</a><a href="/files/b.csv">CSV</a><a href="https://localhost/private.csv">bad</a><a href="/files/x.csv?token=secret">bad</a><a href="/other-page">no crawl</a>'
    )
    assert list(parser.links) == [
        "https://www.transit.dot.gov/files/a.xlsx",
        "https://www.transit.dot.gov/files/b.csv",
    ]
    with pytest.raises(ValueError, match="DISCOVERY_FILE_LIMIT"):
        parser.feed("".join(f'<a href="/{n}.csv">x</a>' for n in range(31)))


@pytest.mark.asyncio
async def test_discovery_returns_candidates_and_landing_provenance(
    monkeypatch, tmp_path
):
    async def fetch(url, destination, **kwargs):
        assert kwargs["limit"] == 2 * 1024**2
        destination.write_text(
            '<a href="/files/expenses.xlsx">Expenses</a><a href="/files/expenses.csv">CSV</a>'
        )
        return Download("hash", 100, URL, "text/html", None, None)

    monkeypatch.setattr(discovery, "fetch", fetch)
    monkeypatch.setattr(discovery, "repo_upsert", AsyncMock())
    monkeypatch.setattr(
        "open_notebook.database.repository.repo_query", AsyncMock(return_value=[])
    )
    result = await discovery.discover(
        {"catalog_id": "db_catalog:1", "metadata": {"downloadURL": URL}},
        {"catalog_identifier": "catalog-url", "metadata": PUBLIC},
        tmp_path,
    )
    assert result["reason"] == "DOWNLOAD_SELECTION_REQUIRED"
    assert len(result["resources"]) == 2
    for resource in result["resources"]:
        assert resource["provenance"]["landing_page_url"] == URL
        assert resource["classification"]["reason"] == "PREFLIGHT_REQUIRED"


def workbook(tmp_path, multiple=False, formula=False):
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Agencies"
    sheet.append(["NTD ID", "Agency Name", "Expenses"])
    sheet.append(["00001", "Demo Transit", "=1+2" if formula else 123])
    if multiple:
        book.create_sheet("Other").append(["Header"])
    path = tmp_path / "input"
    book.save(path)
    book.close()
    return path


def test_xlsx_values_schema_and_identifier_preservation(tmp_path):
    result = stage(workbook(tmp_path), tmp_path / "out.duckdb", "xlsx")
    assert result["rows"] == 1
    assert result["preview"][0]["c_1_ntd_id"] == "00001"
    assert result["preview"][0]["c_3_expenses"] == "123"
    assert result["workbook"]["sheet"] == "Agencies"


def test_multi_sheet_requires_selection_and_never_executes_formulas(tmp_path):
    source = workbook(tmp_path, multiple=True)
    assert stage(source, tmp_path / "out.duckdb", "xlsx") == {
        "sheets": ["Agencies", "Other"]
    }
    assert stage(source, tmp_path / "out.duckdb", "xlsx", "Agencies")["rows"] == 1


def test_workbook_formulas_rejected(tmp_path):
    with pytest.raises(ValueError, match="WORKBOOK_FORMULA_OR_ERROR_UNSUPPORTED"):
        stage(workbook(tmp_path, formula=True), tmp_path / "out.duckdb", "xlsx")


@pytest.mark.asyncio
async def test_import_deduplicates_new_request_keys_and_notebook_scope(monkeypatch):
    resource = {
        "catalog_id": "db_catalog:1",
        "metadata": {"downloadURL": CSV},
        "preflight": {
            "status": "ready",
            "expires_at": "2099",
            "download": {"sha256": "bytes"},
        },
    }
    parent = {"metadata": PUBLIC, "catalog_identifier": "same-dataset", "title": "Test"}
    records = {}

    async def record(table, key):
        return {"payload": resource if table == "db_resource" else parent}

    async def query(sql, params=None):
        params = params or {}
        key = str(params.get("id"))
        if sql.startswith("CREATE"):
            records[key] = {"id": key, **params["data"]}
            return [records[key]]
        if sql.startswith("SELECT * FROM $id"):
            return [records[key]] if key in records else []
        return []

    async def job_for(key, notebook):
        return records[key]

    monkeypatch.setattr(catalog, "record", record)
    monkeypatch.setattr(service, "repo_query", query)
    monkeypatch.setattr(service, "job_for", job_for)
    monkeypatch.setattr(service.Notebook, "get", AsyncMock())
    monkeypatch.setattr(service, "get_secret_from_env", lambda name: "x" * 24)
    submit = AsyncMock()
    monkeypatch.setattr(service, "submit", submit)
    one = await service.create_import("db_resource:1", "notebook:demo", str(uuid4()))
    two = await service.create_import("db_resource:1", "notebook:demo", str(uuid4()))
    assert one["id"] == two["id"] and submit.await_count == 1
    other = await service.create_import("db_resource:1", "notebook:other", str(uuid4()))
    assert other["id"] != one["id"] and submit.await_count == 2
    with pytest.raises(Exception, match="valid destination notebook"):
        await service.create_import("db_resource:1", "", str(uuid4()))


@pytest.mark.asyncio
async def test_preflight_reports_publisher_denial_after_cc0_acceptance(
    monkeypatch, tmp_path
):
    from contextlib import asynccontextmanager

    from open_notebook.databridge.ingestion.download import AcquisitionError

    resource = {
        "catalog_id": "db_catalog:1",
        "metadata": {"downloadURL": URL, "mediaType": "text/html"},
    }

    async def record(table, key):
        return {
            "payload": resource
            if table == "db_resource"
            else {"metadata": PUBLIC, "catalog_identifier": "catalog-url"}
        }

    @asynccontextmanager
    async def workspace():
        yield tmp_path

    monkeypatch.setattr(catalog, "record", record)
    monkeypatch.setattr(service, "workspace", workspace)
    monkeypatch.setattr(service, "repo_upsert", AsyncMock())
    monkeypatch.setattr(
        discovery,
        "fetch",
        AsyncMock(side_effect=AcquisitionError("SOURCE_ACCESS_DENIED")),
    )
    result = await service.preflight("db_resource:1")
    assert result["reason"] == "SOURCE_ACCESS_DENIED"
    assert resource["preflight"] == result


@pytest.mark.parametrize(
    "name,body",
    [
        ("../unsafe.xml", b"x"),
        ("xl/vbaProject.bin", b"x"),
        ("xl/externalLinks/link.xml", b"x"),
        ("xl/bomb.xml", b"a" * 100000),
    ],
)
def test_workbook_container_security(tmp_path, name, body):
    import zipfile

    source = tmp_path / "book"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, body)
    with pytest.raises(
        ValueError,
        match="UNSAFE_ARCHIVE|WORKBOOK_ACTIVE_CONTENT_UNSUPPORTED|WORKBOOK_LIMIT",
    ):
        stage(source, tmp_path / "out.duckdb", "xlsx")
