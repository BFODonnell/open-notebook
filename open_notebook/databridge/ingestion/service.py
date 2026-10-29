"""Durable import state machine, publication and automatic scoped registration."""

import json
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from loguru import logger

from open_notebook.database.repository import ensure_record_id, repo_query, repo_upsert
from open_notebook.databridge.ingestion import catalog
from open_notebook.databridge.ingestion.download import AcquisitionError, fetch
from open_notebook.databridge.ingestion.runtime import parse, root, workspace
from open_notebook.databridge.mcp import service as mcp
from open_notebook.databridge.mcp.client import digest
from open_notebook.databridge.mcp.models import ConnectionSpec, MCPConnection
from open_notebook.domain.notebook import Notebook, Source
from open_notebook.exceptions import (
    ConfigurationError,
    InvalidInputError,
    NotFoundError,
)
from open_notebook.utils.encryption import encrypt_value, get_secret_from_env

# Release-reviewed signature of the bundled, isolated Phase 2 broker. Enabling
# ingestion delegates only these fixed broker capabilities, never arbitrary MCP.
BROKER_FINGERPRINT = "70f188bb6eed37fdfac4e2e1d26786dacfa5c0d02dc54ffe6086ad8ae24e1633"


def future(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


async def preflight(resource_id: str) -> dict:
    resource = await catalog.record("db_resource", resource_id)
    item = resource["payload"]
    parent = await catalog.record("db_catalog", item["catalog_id"])
    classification = catalog.classify(
        parent["payload"]["metadata"].get("dcat", {}), item["metadata"]
    )
    if classification["status"] != "checking":
        return classification
    try:
        async with workspace() as folder:
            downloaded = await fetch(
                item["metadata"]["downloadURL"], folder / "payload"
            )
            if downloaded.content_type in {"text/html", "application/xhtml+xml"}:
                raise AcquisitionError("FORMAT_MISMATCH")
            profile = await parse(
                folder / "payload", folder / "preview.duckdb", classification["adapter"]
            )
        result = {
            "status": "ready",
            "reason": "VALIDATED",
            "adapter": classification["adapter"],
            "download": asdict(downloaded),
            "profile": profile,
            "checked_at": mcp.now(),
            "expires_at": future(900),
        }
    except AcquisitionError as error:
        result = {
            "status": "connector_required"
            if error.code
            in {
                "ARCHIVE_ADAPTER_REQUIRED",
                "ARCHIVE_SELECTION_REQUIRED",
                "COLUMN_TYPE_UNSUPPORTED",
                "JSON_STRUCTURE_UNSUPPORTED",
            }
            else "unavailable",
            "reason": error.code,
            "retryable": error.retryable,
            "checked_at": mcp.now(),
        }
    item["preflight"] = result
    await repo_upsert("db_resource", resource_id, {"payload": item}, True)
    return result


async def job_for(job_id: str, notebook_id: str) -> dict:
    job = await catalog.record("db_import", job_id)
    if job["notebook_id"] != notebook_id:
        raise NotFoundError("Import not available in this notebook")
    await Notebook.get(notebook_id)
    return job


def public_job(job: dict) -> dict:
    return {
        "id": job["id"],
        "status": job["status"],
        "stage": job["stage"],
        "notebook_id": job["notebook_id"],
        "resource_id": job["resource_id"],
        "version_id": job["version_id"],
        "cancel_requested": job.get("cancel_requested", False),
        "recoverable": job["status"] in {"failed", "cancelled"}
        or job.get("lease_until", "") < mcp.now()
        and job["status"] in {"queued", "running"},
        **job["payload"],
    }


async def submit(job_id: str):
    from api.command_service import CommandService

    try:
        command_id = await CommandService.submit_command_job(
            "open_notebook", "import_dataset", {"job_id": job_id}
        )
        await repo_query(
            "UPDATE $id SET command_id=$command",
            {"id": ensure_record_id(job_id), "command": command_id},
        )
    except Exception:
        await repo_query(
            "UPDATE $id SET status='failed', stage='failed', payload.error=$error WHERE status='queued'",
            {
                "id": ensure_record_id(job_id),
                "error": {"code": "QUEUE_UNAVAILABLE", "retryable": True},
            },
        )
        raise InvalidInputError(
            "Import could not be queued; retry from the import list"
        ) from None


async def create_import(
    resource_id: str, notebook_id: str, idempotency_key: str
) -> dict:
    await Notebook.get(notebook_id)
    UUID(idempotency_key)
    job_id = (
        "db_import:"
        + digest(
            {
                "resource": resource_id,
                "notebook": notebook_id,
                "request": idempotency_key,
            }
        )[:40]
    )
    existing = await repo_query("SELECT * FROM $id", {"id": ensure_record_id(job_id)})
    if existing:
        return public_job(existing[0])
    resource = (await catalog.record("db_resource", resource_id))["payload"]
    check = resource.get("preflight", {})
    if check.get("status") != "ready" or check.get("expires_at", "") < mcp.now():
        raise InvalidInputError("Inspect and validate this resource before importing")
    token = get_secret_from_env("DATABRIDGE_DUCKDB_TOKEN")
    if not token or len(token) < 20:
        raise ConfigurationError(
            "Automatic import registration requires the scoped DuckDB broker token"
        )
    active = await repo_query(
        "SELECT count() AS n FROM db_import WHERE status IN ['queued','running'] GROUP ALL"
    )
    if active and active[0]["n"] >= 20:
        raise InvalidInputError("Import queue is full")
    parent = (await catalog.record("db_catalog", resource["catalog_id"]))["payload"]
    data = {
        "status": "queued",
        "stage": "queued",
        "notebook_id": notebook_id,
        "resource_id": resource_id,
        "version_id": str(uuid4()),
        "lease_until": future(60),
        "cancel_requested": False,
        "payload": {
            "title": parent["title"],
            "catalog_id": resource["catalog_id"],
            "dataset_id": str(
                uuid5(NAMESPACE_URL, notebook_id + parent["catalog_identifier"])
            ),
            "catalog_snapshot": parent,
            "resource_snapshot": resource["metadata"],
            "preflight": check,
            "queued_at": mcp.now(),
            "history": [{"stage": "queued", "at": mcp.now()}],
        },
    }
    # CREATE (not UPSERT): duplicate concurrent idempotency keys cannot replace a job.
    try:
        await repo_query(
            "CREATE $id CONTENT $data", {"id": ensure_record_id(job_id), "data": data}
        )
    except Exception:
        existing = await repo_query(
            "SELECT * FROM $id", {"id": ensure_record_id(job_id)}
        )
        if not existing:
            raise
        return public_job(existing[0])
    await submit(job_id)
    return public_job(await job_for(job_id, notebook_id))


async def retry(job_id: str, notebook_id: str) -> dict:
    await job_for(job_id, notebook_id)
    claimed = await repo_query(
        "UPDATE $id SET status='queued', stage='queued', cancel_requested=false, lease_until=$lease WHERE status IN ['failed','cancelled'] OR (status IN ['queued','running'] AND lease_until < $now) RETURN AFTER",
        {"id": ensure_record_id(job_id), "lease": future(60), "now": mcp.now()},
    )
    if not claimed:
        raise InvalidInputError("Import is active or already complete")
    await submit(job_id)
    return public_job(await job_for(job_id, notebook_id))


async def cancel(job_id: str, notebook_id: str) -> dict:
    await job_for(job_id, notebook_id)
    rows = await repo_query(
        "UPDATE $id SET cancel_requested=true WHERE status IN ['queued','running'] AND stage NOT IN ['publishing','registering'] RETURN AFTER",
        {"id": ensure_record_id(job_id)},
    )
    if not rows:
        raise InvalidInputError("This import can no longer be cancelled")
    return public_job(rows[0])


async def process(job_id: str) -> bool:
    catalog.enabled()
    run_token = secrets.token_hex(16)
    claimed = await repo_query(
        "UPDATE $id SET status='running', run_token=$run_key, lease_until=$lease WHERE status='queued' RETURN AFTER",
        {"id": ensure_record_id(job_id), "run_key": run_token, "lease": future(900)},
    )
    if not claimed:
        return False
    job = claimed[0]
    payload = job["payload"]
    version = str(UUID(job["version_id"]))
    stage_file = root() / "staging" / (version + ".duckdb")

    async def transition(stage: str):
        current = await catalog.record("db_import", job_id)
        if current.get("run_token") != run_token:
            raise AcquisitionError("STALE_JOB")
        if current.get("cancel_requested") and stage not in {"registering", "ready"}:
            raise AcquisitionError("CANCELLED")
        payload["history"] = (
            payload.get("history", []) + [{"stage": stage, "at": mcp.now()}]
        )[-40:]
        await repo_query(
            "UPDATE $id SET stage=$stage, payload=$payload WHERE run_token=$run_key",
            {
                "id": ensure_record_id(job_id),
                "run_key": run_token,
                "stage": stage,
                "payload": payload,
            },
        )

    try:
        async with workspace() as folder:
            await transition("resolving")
            published = root() / "published" / (version + ".json")
            if not published.exists():
                await transition("downloading")
                info = await fetch(
                    payload["resource_snapshot"]["downloadURL"], folder / "payload"
                )
                if info.sha256 != payload["preflight"]["download"]["sha256"]:
                    raise AcquisitionError("SOURCE_CHANGED_RECHECK_REQUIRED")
                payload["download"] = {**asdict(info), "retrieved_at": mcp.now()}
                await transition("validating")
                if info.content_type in {"text/html", "application/xhtml+xml"}:
                    raise AcquisitionError("FORMAT_MISMATCH")
                await transition("parsing")
                # An interrupted native writer may leave a WAL; remove only this
                # job's unpublished staging file under the global work lock.
                stage_file.parent.mkdir(parents=True, exist_ok=True)
                for path in [stage_file, stage_file.with_suffix(".duckdb.wal")]:
                    if path.is_symlink():
                        raise AcquisitionError("STAGING_INVALID")
                    path.unlink(missing_ok=True)
                payload["profile"] = await parse(
                    folder / "payload", stage_file, payload["preflight"]["adapter"]
                )
                await transition("staging")
                await transition("profiling")
            elif "profile" not in payload or "download" not in payload:
                raise AcquisitionError("PUBLICATION_RECONCILIATION_REQUIRED")
            await transition("publishing")
            manifest = await mcp.publish_version(version, payload["dataset_id"])
            payload["manifest"] = manifest
            await transition("registering")
            connection_id = "db_connection:" + UUID(version).hex
            previous = await repo_query(
                "SELECT * FROM $id", {"id": ensure_record_id(connection_id)}
            )
            spec = ConnectionSpec(
                name=payload["title"][:80],
                backend="duckdb",
                endpoint_ref="duckdb",
                dialect="duckdb",
                notebooks=[job["notebook_id"]],
                tables=manifest["tables"],
                version_id=version,
                max_rows=100,
                timeout_seconds=30,
            )
            if (
                previous
                and ConnectionSpec(**previous[0]["spec"]).model_dump()
                != spec.model_dump()
            ):
                raise AcquisitionError("CONNECTION_CHANGED_REVIEW_REQUIRED")
            if not previous:
                token = get_secret_from_env("DATABRIDGE_DUCKDB_TOKEN")
                if not token:
                    raise AcquisitionError("BROKER_CREDENTIAL_UNAVAILABLE")
                connection = MCPConnection(
                    spec=spec.model_dump(),
                    encrypted_token=encrypt_value(token),
                    revision=str(uuid4()),
                )
                await repo_upsert(
                    "db_connection",
                    connection_id,
                    connection.model_dump(exclude={"id", "created", "updated"}),
                    True,
                )
            await mcp.discover(connection_id, BROKER_FINGERPRINT)
            pending = await mcp.plan(
                connection_id,
                job["notebook_id"],
                "SELECT COUNT(*) AS rows FROM data",
                None,
                {},
            )
            evidence = await mcp.execute(
                pending["id"], pending["approval_token"], job["notebook_id"]
            )
            if int(evidence["rows"][0]["rows"]) != payload["profile"]["rows"]:
                raise AcquisitionError("PUBLISHED_ROW_COUNT_MISMATCH")
            source_id = "source:" + UUID(version).hex
            summary = (
                "DataBridge dataset documentation (not raw rows or query evidence).\n"
                + json.dumps(
                    {
                        "title": payload["title"],
                        "version_id": version,
                        "connection_id": connection_id,
                        "publisher": payload["catalog_snapshot"]["publisher"],
                        "download_url": payload["download"]["final_url"],
                        "raw_sha256": payload["download"]["sha256"],
                        "rows": payload["profile"]["rows"],
                        "columns": payload["profile"]["columns"],
                        "warnings": payload["profile"]["warnings"],
                    },
                    ensure_ascii=False,
                )
            )
            await repo_upsert(
                "source",
                source_id,
                {
                    "title": "Dataset schema: " + payload["title"][:450],
                    "topics": ["databridge", "dataset-schema"],
                    "full_text": summary,
                },
                True,
            )
            relations = await repo_query(
                "SELECT id FROM reference WHERE in=$source AND out=$notebook",
                {
                    "source": ensure_record_id(source_id),
                    "notebook": ensure_record_id(job["notebook_id"]),
                },
            )
            if not relations:
                source = await Source.get(source_id)
                await source.add_to_notebook(job["notebook_id"])
            payload.update(
                connection_id=connection_id,
                source_id=source_id,
                health_evidence_id=evidence["id"],
                completed_at=mcp.now(),
            )
            payload.pop("error", None)
            await transition("ready")
            await repo_query(
                "UPDATE $id SET status='ready' WHERE run_token=$run_key",
                {"id": ensure_record_id(job_id), "run_key": run_token},
            )
        return True
    except Exception as error:
        logger.warning(
            "Import {} stopped at {} ({})",
            job_id,
            payload.get("history", [{}])[-1].get("stage"),
            type(error).__name__,
        )
        code = error.code if isinstance(error, AcquisitionError) else "IMPORT_FAILED"
        payload["error"] = {
            "code": code,
            "retryable": code
            not in {"SOURCE_CHANGED_RECHECK_REQUIRED", "DOWNLOAD_BLOCKED"},
            "correlation_id": job_id,
        }
        await repo_query(
            "UPDATE $id SET status=$status, stage=$status, payload=$payload WHERE run_token=$run_key",
            {
                "id": ensure_record_id(job_id),
                "run_key": run_token,
                "status": "cancelled" if code == "CANCELLED" else "failed",
                "payload": payload,
            },
        )
        return False
    finally:
        # The child is reaped before this point; no live writer is ever unlinked.
        if stage_file.is_file() and not stage_file.is_symlink():
            stage_file.unlink(missing_ok=True)
        stage_file.with_suffix(".duckdb.wal").unlink(missing_ok=True)


async def list_jobs(notebook_id: str) -> list[dict]:
    await Notebook.get(notebook_id)
    rows = await repo_query(
        "SELECT * FROM db_import WHERE notebook_id=$notebook ORDER BY payload.queued_at DESC LIMIT 100",
        {"notebook": notebook_id},
    )
    return [public_job(job) for job in rows]


async def notebook_context(notebook_id: str) -> dict:
    jobs = await list_jobs(notebook_id)
    datasets = []
    for job in jobs:
        if job["status"] != "ready":
            continue
        try:
            await mcp.connection_for(job["connection_id"], notebook_id)
        except NotFoundError:
            continue
        datasets.append(
            {
                "import_id": job["id"],
                "dataset_id": job["dataset_id"],
                "title": job["title"],
                "version_id": job["version_id"],
                "connection_id": job["connection_id"],
                "source_id": job["source_id"],
                "table": "data",
                "columns": job["profile"]["columns"],
                "rows": job["profile"]["rows"],
                "raw_sha256": job["download"]["sha256"],
                "database_sha256": job["manifest"]["sha256"],
            }
        )
    return {
        "notebook_id": notebook_id,
        "datasets": datasets,
        "sql_policy": "single-table SELECT; explicit query approval required",
        "conversational_analysis": False,
    }
