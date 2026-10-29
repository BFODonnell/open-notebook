"""Official Data.gov v4 adapter and immutable cached resource snapshots."""

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from open_notebook.database.repository import ensure_record_id, repo_query, repo_upsert
from open_notebook.databridge.ingestion.download import (
    AcquisitionError,
    fetch,
    hosts,
    validate_public_url,
)
from open_notebook.databridge.mcp.client import digest
from open_notebook.databridge.mcp.service import now, require_enabled
from open_notebook.exceptions import (
    ConfigurationError,
    InvalidInputError,
    NotFoundError,
)
from open_notebook.utils.encryption import get_secret_from_env

BASE = "https://api.gsa.gov/technology/datagov/v4/"


def enabled():
    require_enabled()
    if os.getenv("DATABRIDGE_INGESTION_ENABLED", "false").lower() != "true":
        raise NotFoundError("Open Data Explorer is disabled")


async def record(table: str, key: str) -> dict:
    if not key.startswith(table + ":"):
        raise NotFoundError("Catalog or import record not found")
    rows = await repo_query("SELECT * FROM $id", {"id": ensure_record_id(key)})
    if not rows:
        raise NotFoundError("Catalog or import record not found")
    return rows[0]


async def request(path: str, params: dict | None = None) -> dict:
    key = get_secret_from_env("DATAGOV_API_KEY")
    if not key or key == "DEMO_KEY":
        raise ConfigurationError(
            "Configure a personal DATAGOV_API_KEY for catalog access"
        )
    url = BASE + path + ("?" + urlencode(params) if params else "")
    with tempfile.TemporaryDirectory(prefix="databridge-catalog-") as directory:
        target = Path(directory) / "response"
        # API responses/keys cannot redirect to publisher endpoints.
        await fetch(
            url, target, allowed={"api.gsa.gov"}, limit=2 * 1024**2, api_key=key
        )
        try:
            result = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, UnicodeError):
            raise AcquisitionError("CATALOG_RESPONSE_INVALID") from None


def classify(dcat: dict, resource: dict) -> dict:
    if (
        str(dcat.get("accessLevel", "")).lower() != "public"
        or resource.get("accessLevel", "public") != "public"
    ):
        return {"status": "unavailable", "reason": "ACCESS_RESTRICTED"}
    # Data.gov's DOT DCAT uses ["public"]. Only that exact declaration (or
    # absence) is recognized; free-text licensing/restrictions require review.
    for rights in (dcat.get("rights"), resource.get("rights")):
        if rights not in (None, "", [], "public", ["public"]):
            return {"status": "unavailable", "reason": "RIGHTS_REVIEW_REQUIRED"}
    url = resource.get("downloadURL")
    if not isinstance(url, str):
        return {"status": "connector_required", "reason": "DIRECT_DOWNLOAD_REQUIRED"}
    try:
        validate_public_url(url, hosts())
    except AcquisitionError:
        return {"status": "unavailable", "reason": "DOWNLOAD_BLOCKED"}
    hints = [
        str(resource.get("format", "")).lower(),
        str(resource.get("mediaType", "")).lower(),
        Path(urlsplit(url).path).suffix.lstrip(".").lower(),
    ]
    formats = {
        "csv": {"csv", "text/csv"},
        "json": {"json", "application/json"},
        "jsonl": {"jsonl", "ndjson", "application/x-ndjson"},
        "parquet": {
            "parquet",
            "application/vnd.apache.parquet",
            "application/x-parquet",
        },
        "zip": {"zip", "application/zip"},
    }
    candidates = {
        kind for kind, labels in formats.items() if labels.intersection(hints)
    }
    if len(candidates) != 1:
        return {"status": "connector_required", "reason": "FORMAT_ADAPTER_REQUIRED"}
    return {
        "status": "checking",
        "reason": "PREFLIGHT_REQUIRED",
        "adapter": candidates.pop(),
    }


async def cache_dataset(item: dict) -> dict:
    dcat = item.get("dcat") or {}
    if not isinstance(dcat, dict) or len(json.dumps(item).encode()) > 131072:
        raise AcquisitionError("CATALOG_RECORD_LIMIT")
    identity = str(dcat.get("identifier") or item.get("identifier") or digest(item))
    ref = "db_catalog:" + digest(item)[:40]
    snapshot = {
        "catalog_identifier": identity,
        "title": str(dcat.get("title") or item.get("title") or "Untitled")[:512],
        "description": str(dcat.get("description") or item.get("description") or "")[
            :16000
        ],
        "publisher": dcat.get("publisher") or item.get("publisher"),
        "metadata": item,
        "cached_at": now(),
    }
    resources = []
    distributions = dcat.get("distribution") or []
    if not isinstance(distributions, list) or len(distributions) > 30:
        raise AcquisitionError("CATALOG_RECORD_LIMIT")
    for distribution in distributions:
        if not isinstance(distribution, dict):
            continue
        resource_ref = (
            "db_resource:" + digest({"catalog": ref, "resource": distribution})[:40]
        )
        payload = {
            "catalog_id": ref,
            "metadata": distribution,
            "classification": classify(dcat, distribution),
        }
        # A search must not erase a completed preflight for the same snapshot.
        if not await repo_query(
            "SELECT id FROM $id", {"id": ensure_record_id(resource_ref)}
        ):
            await repo_upsert("db_resource", resource_ref, {"payload": payload}, True)
        resources.append(
            {
                "id": resource_ref,
                "title": str(
                    distribution.get("title")
                    or distribution.get("format")
                    or "Resource"
                )[:512],
                **payload,
            }
        )
    snapshot["resources"] = [r["id"] for r in resources]
    await repo_upsert("db_catalog", ref, {"payload": snapshot}, True)
    return {"id": ref, **snapshot, "resources": resources}


async def search(
    q: str, org_slug: str, keyword: str, after: str, per_page: int
) -> dict:
    enabled()
    params = {"q": q, "per_page": per_page, "sort": "relevance"}
    params.update(
        {
            k: v
            for k, v in {
                "org_slug": org_slug,
                "keyword": keyword,
                "after": after,
            }.items()
            if v
        }
    )
    cache_id = "db_catalog_cache:" + digest(params)
    cached = await repo_query(
        "SELECT * FROM $id WHERE expires_at > time::now()",
        {"id": ensure_record_id(cache_id)},
    )
    if cached:
        return {"after": None, **cached[0]["payload"]}
    result = await request("search", params)
    if not isinstance(result.get("results"), list) or len(result["results"]) > per_page:
        raise AcquisitionError("CATALOG_RESPONSE_INVALID")
    cards = [
        await cache_dataset(item)
        for item in result["results"]
        if isinstance(item, dict)
    ]
    cursor = result.get("after")
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 4096):
        raise AcquisitionError("CATALOG_RESPONSE_INVALID")
    response = {"results": cards, "after": cursor, "source": BASE, "cached_at": now()}
    await repo_query(
        "UPSERT $id SET payload=$payload, expires_at=time::now()+5m",
        {"id": ensure_record_id(cache_id), "payload": response},
    )
    return response


async def dataset(ref: str) -> dict:
    saved = await record("db_catalog", ref)
    payload = saved["payload"]
    if not payload["resources"]:
        harvest = payload["metadata"].get("harvest_record")
        if harvest:
            try:
                parsed = urlsplit(harvest)
                key = str(UUID(parsed.path.rstrip("/").split("/")[-1]))
                if parsed.hostname != "api.gsa.gov":
                    raise ValueError()
            except (ValueError, TypeError):
                raise InvalidInputError(
                    "Catalog harvest reference is invalid"
                ) from None
            dcat = await request("harvest_record/" + key + "/transformed")
            # A detail refresh is a new immutable catalog snapshot.
            return await cache_dataset({**payload["metadata"], "dcat": dcat})
    resources = [
        {"id": key, **(await record("db_resource", key))["payload"]}
        for key in payload["resources"]
    ]
    return {"id": ref, **payload, "resources": resources}
