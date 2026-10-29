"""Registry, one-use query approvals and durable evidence in upstream SurrealDB."""

import asyncio
import json
import math
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from open_notebook.database.repository import ensure_record_id, repo_query, repo_upsert
from open_notebook.databridge.mcp.client import (
    digest,
    endpoint,
    exchange,
    result_rows,
    validate_input_schema,
)
from open_notebook.databridge.mcp.models import (
    ConnectionSpec,
    ConnectionWrite,
    DatasetVersion,
    MCPConnection,
    QueryPlan,
    QueryRun,
)
from open_notebook.databridge.mcp.policy import POLICY_VERSION, readonly_sql
from open_notebook.databridge.mcp.versions import publish, version_key
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ExternalServiceError,
    InvalidInputError,
    NotFoundError,
)
from open_notebook.utils.encryption import encrypt_value, get_secret_from_env


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_enabled() -> None:
    if os.getenv("DATABRIDGE_MCP_ENABLED", "false").lower() != "true":
        raise NotFoundError("Database connections are disabled")
    password = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
    admin_key = get_secret_from_env("DATABRIDGE_MCP_ADMIN_KEY")
    if not password or not admin_key or len(admin_key) < 20 or admin_key == password:
        raise ConfigurationError(
            "MCP requires application and separate administrator authentication"
        )


def require_admin(key: str | None) -> None:
    require_enabled()
    expected = get_secret_from_env("DATABRIDGE_MCP_ADMIN_KEY") or ""
    if not key or not secrets.compare_digest(key.encode(), expected.encode()):
        raise AuthenticationError("Database administrator authentication required")


async def connection_for(
    connection_id: str, notebook_id: str, *, active=True
) -> MCPConnection:
    require_enabled()
    if not connection_id.startswith("db_connection:"):
        raise NotFoundError("Connection not available")
    connection = await MCPConnection.get(connection_id)
    if notebook_id not in connection.spec["notebooks"] or (
        active and not connection.spec["enabled"]
    ):
        raise NotFoundError("Connection not available in this notebook")
    await Notebook.get(notebook_id)
    return connection


async def write_connection(
    data: ConnectionWrite, connection_id: str | None = None
) -> dict:
    require_enabled()
    spec = ConnectionSpec(**data.model_dump(exclude={"token"}))
    endpoint(spec)
    for notebook in spec.notebooks:
        await Notebook.get(notebook)
    if spec.backend == "duckdb":
        if spec.dialect != "duckdb" or not spec.version_id:
            raise InvalidInputError("DuckDB requires an immutable version")
        version = await DatasetVersion.get(
            "db_dataset_version:" + version_key(spec.version_id)
        )
        if any(
            t not in version.manifest["tables"]
            or not set(cols) <= set(version.manifest["tables"][t])
            for t, cols in spec.tables.items()
        ):
            raise InvalidInputError(
                "Connection columns must belong to its dataset version"
            )
    elif spec.version_id:
        raise InvalidInputError("Only DuckDB connections select local versions")
    if spec.backend == "toolbox":
        if not spec.curated_tools or spec.schema_tool not in spec.curated_tools:
            raise InvalidInputError(
                "Toolbox requires approved curated tools and a schema tool"
            )
    if not spec.tables:
        raise InvalidInputError("Connections require a schema table/column allowlist")
    if spec.backend == "dbhub" and spec.dialect != "postgres":
        raise InvalidInputError(
            "Phase 2 DBHub execution is certified only for PostgreSQL"
        )
    encrypted = None
    if connection_id:
        old = await MCPConnection.get(connection_id)
        encrypted = old.encrypted_token
    if data.token is not None:
        encrypted = (
            encrypt_value(data.token.get_secret_value())
            if data.token.get_secret_value()
            else None
        )
    connection = MCPConnection(
        id=connection_id,
        spec=spec.model_dump(),
        encrypted_token=encrypted,
        revision=str(uuid4()),
    )
    await connection.save()
    return connection.public()


async def discover(connection_id: str, approve: str | None = None) -> dict:
    connection = await MCPConnection.get(connection_id)
    try:
        discovery = await exchange(connection)
    except ExternalServiceError:
        connection.health = "unavailable"
        connection.last_test = now()
        await connection.save()
        raise
    spec = ConnectionSpec(**connection.spec)
    needed = (
        {"execute_sql", "search_objects"}
        if spec.backend == "dbhub"
        else (
            {"execute_query", "describe_version"}
            if spec.backend == "duckdb"
            else set(spec.curated_tools)
        )
    )
    tools = [t for t in discovery["tools"] if t["name"] in needed]
    if {t["name"] for t in tools} != needed:
        raise InvalidInputError("Required approved capabilities are missing")
    try:
        for tool in tools:
            validate_input_schema(tool["inputSchema"])
    except ValueError:
        raise InvalidInputError(
            "Tool input schema is outside the approved scalar subset"
        ) from None
    if approve is not None:
        if approve != discovery["fingerprint"]:
            raise InvalidInputError("Tool signatures changed; inspect discovery again")
        connection.approved_fingerprint = approve
        connection.approved_tools = tools
        connection.revision = str(uuid4())
    connection.health = (
        "ready"
        if connection.approved_fingerprint == discovery["fingerprint"]
        else "approval_required"
    )
    connection.last_test = now()
    await connection.save()
    return {**discovery, "health": connection.health}


async def schema(connection_id: str, notebook_id: str) -> dict:
    connection = await connection_for(connection_id, notebook_id)
    spec = ConnectionSpec(**connection.spec)
    if spec.backend == "duckdb":
        result = await exchange(
            connection, "describe_version", {"version_id": spec.version_id}
        )
        manifest = result.get("structured") or result["content"][0]
        # Do not expose other tables/columns from the physical version.
        return {
            "tables": spec.tables,
            "columns": [
                r
                for r in manifest["schema"]
                if r[0] in spec.tables and r[1] in spec.tables[r[0]]
            ],
            "version_id": spec.version_id,
        }
    if spec.backend == "dbhub":
        names = ",".join("'" + table + "'" for table in spec.tables)
        sql = (
            "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name IN ("
            + names
            + ") ORDER BY table_name, ordinal_position LIMIT 1000"
        )
        rows = result_rows(
            await exchange(connection, "execute_sql", {"sql": sql}), "dbhub"
        )
        rows = [
            r
            for r in rows
            if r["table_name"] in spec.tables
            and r["column_name"] in spec.tables[r["table_name"]]
        ]
    else:
        rows = result_rows(await exchange(connection, spec.schema_tool, {}), "toolbox")
        if any(
            not {"table_name", "column_name", "data_type"} <= row.keys() for row in rows
        ):
            raise InvalidInputError(
                "Schema tool must return normalized column metadata"
            )
        rows = [
            {k: row[k] for k in ("table_name", "column_name", "data_type")}
            for row in rows
            if row["table_name"] in spec.tables
            and row["column_name"] in spec.tables[row["table_name"]]
        ]
    if len(json.dumps(rows).encode()) > spec.max_bytes:
        raise InvalidInputError("Schema result exceeds byte limit")
    return {"tables": spec.tables, "columns": rows}


async def record_audit(payload: dict) -> QueryRun:
    run = QueryRun(payload={"timestamp": now(), "policy": POLICY_VERSION, **payload})
    await run.save()
    return run


async def plan(
    connection_id: str,
    notebook_id: str,
    sql: str | None,
    tool: str | None,
    parameters: dict,
) -> dict:
    try:
        connection = await connection_for(connection_id, notebook_id)
        spec = ConnectionSpec(**connection.spec)
        if not connection.approved_fingerprint:
            raise InvalidInputError("Administrator capability approval required")
        if spec.backend == "toolbox":
            from jsonschema import Draft202012Validator

            if (
                sql
                or not tool
                or tool not in spec.curated_tools
                or tool == spec.schema_tool
            ):
                raise ValueError("Select an approved analytical tool")
            approved = next(t for t in connection.approved_tools if t["name"] == tool)
            if any(
                isinstance(v, float) and not math.isfinite(v)
                for v in parameters.values()
            ):
                raise ValueError("Non-finite parameters are forbidden")
            if not Draft202012Validator(
                {**approved["inputSchema"], "additionalProperties": False}
            ).is_valid(parameters):
                raise ValueError("Invalid curated tool parameters")
            canonical = None
        else:
            if tool:
                raise ValueError("SQL connections do not accept arbitrary tool names")
            canonical = readonly_sql(
                sql or "", spec.dialect, spec.tables, spec.max_rows, parameters
            )
        if len(json.dumps(parameters).encode()) > 4096:
            raise ValueError("Parameter size limit exceeded")
        payload = {
            "connection_id": connection_id,
            "notebook_id": notebook_id,
            "revision": connection.revision,
            "fingerprint": connection.approved_fingerprint,
            "sql": canonical,
            "tool": tool,
            "parameters": parameters if spec.backend == "toolbox" else {},
            "version_id": spec.version_id,
            "policy": POLICY_VERSION,
        }
        if spec.version_id:
            version = await DatasetVersion.get(
                "db_dataset_version:" + version_key(spec.version_id)
            )
            payload["dataset_sha256"] = version.manifest["sha256"]
    except (ValueError, StopIteration) as error:
        await record_audit(
            {
                "status": "denied",
                "connection_id": connection_id,
                "notebook_id": notebook_id,
                "request_sha256": digest(
                    {"sql": sql, "tool": tool, "parameters": parameters}
                ),
            }
        )
        raise InvalidInputError(
            "Query rejected by the read-only policy or parameter schema"
        ) from error
    except (NotFoundError, InvalidInputError):
        await record_audit(
            {
                "status": "denied",
                "connection_id": connection_id,
                "notebook_id": notebook_id,
            }
        )
        raise
    token = secrets.token_urlsafe(32)
    query = QueryPlan(
        payload=payload,
        approval_hash=digest(token),
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )
    await query.save()
    return {
        "id": query.id,
        "approval_token": token,
        "expires_at": query.expires_at,
        **payload,
    }


async def execute(plan_id: str, token: str, notebook_id: str) -> dict:
    if not plan_id.startswith("db_query_plan:"):
        raise NotFoundError("Query plan not available")
    query = await QueryPlan.get(plan_id)
    payload = query.payload
    if payload["notebook_id"] != notebook_id:
        raise NotFoundError("Query plan not available")
    connection = await connection_for(payload["connection_id"], notebook_id)
    if (
        connection.revision != payload["revision"]
        or payload["policy"] != POLICY_VERSION
    ):
        await record_audit(
            {
                "status": "denied",
                "connection_id": connection.id,
                "notebook_id": notebook_id,
                "plan_id": plan_id,
                "reason": "stale_plan",
            }
        )
        raise InvalidInputError("Connection or policy changed; create a new plan")
    claimed = await repo_query(
        "UPDATE $id SET state='running' WHERE state='pending' AND approval_hash=$hash AND expires_at > $now RETURN AFTER",
        {"id": ensure_record_id(plan_id), "hash": digest(token), "now": now()},
    )
    if not claimed:
        await record_audit(
            {
                "status": "denied",
                "connection_id": connection.id,
                "notebook_id": notebook_id,
                "plan_id": plan_id,
                "reason": "invalid_approval",
            }
        )
        raise InvalidInputError("Approval expired, invalid, or already used")
    spec = ConnectionSpec(**connection.spec)
    run = await record_audit({**payload, "plan_id": plan_id, "status": "running"})
    try:
        if spec.backend == "toolbox":
            tool, arguments = payload["tool"], payload["parameters"]
        else:
            canonical = readonly_sql(
                payload["sql"], spec.dialect, spec.tables, spec.max_rows
            )
            tool = "execute_query" if spec.backend == "duckdb" else "execute_sql"
            arguments = {"sql": canonical}
            if spec.backend == "duckdb":
                arguments["version_id"] = spec.version_id
        response = await exchange(connection, tool, arguments)
        if spec.backend == "duckdb":
            identity = response.get("structured") or response["content"][0]
            if (
                identity.get("dataset_sha256") != payload["dataset_sha256"]
                or identity.get("version_id") != payload["version_id"]
            ):
                raise ValueError("Dataset identity changed")
        rows = result_rows(response, spec.backend)
        encoded = json.dumps(
            rows,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        if len(rows) > spec.max_rows or len(encoded) > spec.max_bytes:
            raise ValueError("Result limit exceeded")
        run.payload.update(
            {
                "status": "success",
                "rows": rows,
                "row_count": len(rows),
                "bytes": len(encoded),
                "result_sha256": digest(rows),
                "completed_at": now(),
            }
        )
        await run.save()
        return {"id": run.id, **run.payload}
    except (Exception, BaseExceptionGroup):
        run.payload.update({"status": "failed", "completed_at": now()})
        await run.save()
        raise ExternalServiceError(
            "Query failed or exceeded limits. Inspect the connection and create a new plan to retry."
        ) from None


async def publish_version(staging_id: str, dataset_id: str) -> dict:
    try:
        manifest = await asyncio.to_thread(
            publish,
            Path(os.getenv("DATABRIDGE_DATA_ROOT", "data/databridge")),
            staging_id,
            dataset_id,
        )
    except Exception:
        raise InvalidInputError(
            "Publication failed: check staging file, immutability and quotas"
        ) from None
    record_id = "db_dataset_version:" + manifest["version_id"]
    existing = await repo_query(
        "SELECT * FROM $id", {"id": ensure_record_id(record_id)}
    )
    if existing:
        if digest(existing[0]["manifest"]) != digest(manifest):
            raise InvalidInputError("An immutable dataset version cannot be changed")
        return {"id": record_id, **manifest}
    # File publication precedes durable registration. Orphans are not exposed
    # through the app; retrying the same staging ID repairs registration safely.
    await repo_upsert("db_dataset_version", record_id, {"manifest": manifest}, True)
    return {"id": record_id, **manifest}
