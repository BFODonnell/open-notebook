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


def rights_status(metadata: dict, resource: dict) -> dict | None:
    """Read explicit dataset/distribution declarations, never infer reuse from access.

    Only known schema locations are inspected: unrelated landing-page text and
    sibling distributions must not grant rights to this resource. Any unknown or
    conflicting declaration wins over a recognized license.
    """
    dcat = metadata.get("dcat", {})
    scopes = [metadata, dcat if isinstance(dcat, dict) else {}, resource]
    access = [s[k] for s in scopes for k in ("accessLevel", "access_level") if k in s]
    if not access or any(
        not isinstance(a, str) or a.strip().lower() != "public" for a in access
    ):
        return {"status": "unavailable", "reason": "ACCESS_RESTRICTED"}

    def values(value):
        if value is None or value == "" or value == []:
            return []
        if isinstance(value, list):
            return [v for item in value for v in values(item)]
        if isinstance(value, dict):
            if set(value) - {"@id", "@value", "@type", "name", "title", "url"}:
                return [None]
            known = [
                value[k]
                for k in ("@id", "@value", "name", "title", "url")
                if k in value
            ]
            return [v for item in known for v in values(item)] if known else [None]
        return [value]

    declarations = [
        v
        for scope in scopes
        for key in ("rights", "license")
        for v in values(scope.get(key))
    ]
    supported = {
        "cc0",
        "cc0 1.0",
        "cc0-1.0",
        "public domain",
        "https://creativecommons.org/publicdomain/zero/1.0",
        "http://creativecommons.org/publicdomain/zero/1.0",
        "https://creativecommons.org/publicdomain/zero/1.0/legalcode",
        "https://www.usa.gov/government-works",
    }
    normalized = [
        " ".join(v.split()).lower().rstrip("/") if isinstance(v, str) else ""
        for v in declarations
    ]
    # DOT's legacy "public" is an access-style marker, not sufficient alone.
    if (
        not normalized
        or not any(v in supported for v in normalized)
        or any(v not in supported | {"public"} for v in normalized)
    ):
        return {"status": "unavailable", "reason": "RIGHTS_REVIEW_REQUIRED"}
    return None


def classify(metadata: dict, resource: dict) -> dict:
    if blocked := rights_status(metadata, resource):
        return blocked
    url = resource.get("downloadURL")
    if not isinstance(url, str):
        url = resource.get("accessURL")
        if not isinstance(url, str):
            return {
                "status": "connector_required",
                "reason": "DIRECT_DOWNLOAD_REQUIRED",
            }
    try:
        validate_public_url(url, hosts())
    except AcquisitionError as error:
        return {"status": "unavailable", "reason": error.code}
    hints = [
        str(resource.get("format", "")).lower(),
        str(resource.get("mediaType", "")).lower(),
        Path(urlsplit(url).path).suffix.lstrip(".").lower(),
    ]
    formats = {
        "xlsx": {
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
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
    if candidates and not resource.get("downloadURL"):
        return {"status": "connector_required", "reason": "DIRECT_DOWNLOAD_REQUIRED"}
    if len(candidates) != 1:
        if not candidates and (
            "text/html" in hints
            or Path(urlsplit(url).path).suffix.lower() in {"", ".html", ".htm"}
        ):
            return {
                "status": "checking",
                "reason": "LANDING_PAGE_DISCOVERY_REQUIRED",
                "adapter": "html",
            }
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
        # Keep the bounded record inspectable without aborting unrelated search
        # results or silently selecting a subset of its distributions.
        snapshot["resources_status"] = "CATALOG_RECORD_LIMIT"
        distributions = []
    for distribution in distributions:
        if not isinstance(distribution, dict):
            continue
        resource_ref = (
            "db_resource:" + digest({"catalog": ref, "resource": distribution})[:40]
        )
        payload = {
            "catalog_id": ref,
            "metadata": distribution,
            "classification": classify(item, distribution),
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
        payload = cached[0]["payload"]
        return {
            "after": None,
            **payload,
            "results": [await dataset(r["id"]) for r in payload["results"]],
        }
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
    if not payload["resources"] and not payload.get("resources_status"):
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
    for resource in resources:
        resource["classification"] = classify(payload["metadata"], resource["metadata"])
        # Policy changes also apply to previously cached preflights.
        if resource["classification"]["status"] == "unavailable":
            resource.pop("preflight", None)
    return {"id": ref, **payload, "resources": resources}
