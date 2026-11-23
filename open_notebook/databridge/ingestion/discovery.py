"""One-page, bounded download discovery using the normal SSRF-safe transport."""

from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from open_notebook.database.repository import repo_upsert
from open_notebook.databridge.ingestion import catalog
from open_notebook.databridge.ingestion.download import (
    AcquisitionError,
    fetch,
    hosts,
    validate_public_url,
)
from open_notebook.databridge.mcp.client import digest

MAX_LINKS = 30


class Downloads(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.links: dict[str, str] = {}
        self.current: str | None = None
        self.seen = 0

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        self.current = None
        self.seen += 1
        if self.seen > 2000:
            raise AcquisitionError("DISCOVERY_LINK_LIMIT")
        href = dict(attrs).get("href")
        if not href:
            return
        url = urljoin(self.base, href)
        if Path(urlsplit(url).path).suffix.lower() not in {
            ".csv",
            ".json",
            ".jsonl",
            ".ndjson",
            ".parquet",
            ".zip",
            ".xlsx",
        }:
            return
        try:
            validate_public_url(url, hosts())
        except AcquisitionError:
            return
        if url not in self.links:
            if len(self.links) >= MAX_LINKS:
                raise AcquisitionError("DISCOVERY_FILE_LIMIT")
            self.links[url] = ""
        self.current = url

    def handle_endtag(self, tag):
        if tag == "a":
            self.current = None

    def handle_data(self, data):
        if self.current:
            self.links[self.current] = (self.links[self.current] + data)[:512]


async def child(item: dict, metadata: dict, provenance: dict) -> dict:
    ref = (
        "db_resource:"
        + digest(
            {
                "catalog": item["catalog_id"],
                "resource": metadata,
                "provenance": provenance,
            }
        )[:40]
    )
    payload = {
        "catalog_id": item["catalog_id"],
        "metadata": metadata,
        "provenance": provenance,
    }
    # Preserve an already validated identical candidate.
    from open_notebook.database.repository import ensure_record_id, repo_query

    if not await repo_query("SELECT id FROM $id", {"id": ensure_record_id(ref)}):
        await repo_upsert("db_resource", ref, {"payload": payload}, True)
    return {"id": ref, **payload}


async def discover(item: dict, parent: dict, folder: Path) -> dict:
    url = item["metadata"].get("downloadURL") or item["metadata"]["accessURL"]
    downloaded = await fetch(url, folder / "landing", limit=2 * 1024**2)
    if downloaded.content_type not in {"text/html", "application/xhtml+xml"}:
        raise AcquisitionError("LANDING_PAGE_FORMAT_UNSUPPORTED")
    parser = Downloads(downloaded.final_url)
    parser.feed((folder / "landing").read_text(encoding="utf-8", errors="replace"))
    provenance = {
        "landing_page_url": url,
        "landing_page": asdict(downloaded),
        "catalog_url": parent["catalog_identifier"],
    }
    resources = []
    for url, title in parser.links.items():
        metadata = {
            **item["metadata"],
            "downloadURL": url,
            "title": title.strip() or Path(urlsplit(url).path).name,
        }
        metadata.pop("mediaType", None)
        metadata.pop("format", None)
        candidate = await child(item, metadata, provenance)
        candidate["classification"] = catalog.classify(parent["metadata"], metadata)
        resources.append(candidate)
    return {
        "status": "connector_required",
        "reason": "DOWNLOAD_SELECTION_REQUIRED"
        if resources
        else "NO_SUPPORTED_DOWNLOADS",
        "resources": resources,
    }
