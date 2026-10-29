"""Official SDK sessions: isolated credentials, bounded transport, revalidation."""

import asyncio
import hashlib
import json
import os
from datetime import timedelta
from urllib.parse import urlsplit

import httpx

from open_notebook.databridge.mcp.models import ConnectionSpec, MCPConnection
from open_notebook.exceptions import ConfigurationError, ExternalServiceError
from open_notebook.utils.encryption import decrypt_value
from open_notebook.utils.url_validation import validate_url

_slots = asyncio.Semaphore(4)
WIRE_LIMIT = 524288


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def validate_input_schema(schema: dict) -> None:
    """Accept bounded scalar arguments only; never resolve remote JSON refs."""
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise ValueError("Invalid tool schema") from None
    if not isinstance(schema.get("additionalProperties", False), bool):
        raise ValueError("Nested tool schemas are not supported")
    if schema.get("type") != "object" or len(schema.get("properties", {})) > 20:
        raise ValueError("Unsupported tool input schema")
    if set(schema) - {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "$schema",
        "title",
        "description",
    }:
        raise ValueError("Unsupported schema keywords")
    for definition in schema.get("properties", {}).values():
        if definition.get("type") not in {"string", "integer", "number", "boolean"}:
            raise ValueError("Only scalar tool parameters are supported")
        if set(definition) - {
            "type",
            "description",
            "title",
            "default",
            "enum",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
        }:
            raise ValueError("Unsupported parameter constraint")
    if not set(schema.get("required", [])) <= set(schema.get("properties", {})):
        raise ValueError("Invalid required tool parameters")


def endpoint(spec: ConnectionSpec) -> str:
    try:
        config = json.loads(os.environ.get("DATABRIDGE_MCP_ENDPOINTS", "{}"))[
            spec.endpoint_ref
        ]
        url = config["url"]
        parts = urlsplit(url)
        if config["backend"] != spec.backend or not config.get("readonly"):
            raise ValueError()
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError()
        return url
    except (KeyError, TypeError, ValueError):
        raise ConfigurationError(
            "MCP endpoint is not operator-approved for this backend"
        ) from None


class BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > WIRE_LIMIT:
                raise ValueError("MCP transport byte limit exceeded")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class BoundedTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        response = await super().handle_async_request(request)
        if response.headers.get("content-encoding", "identity") != "identity":
            await response.aclose()
            raise ValueError("Compressed MCP responses are not allowed")
        response.stream = BoundedStream(response.stream)
        return response


async def exchange(
    connection: MCPConnection, tool: str | None = None, arguments: dict | None = None
) -> dict:
    from jsonschema import Draft202012Validator
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.types import TextContent

    spec = ConnectionSpec(**connection.spec)
    url = endpoint(spec)
    await validate_url(url, "DataBridge MCP")
    headers = {"Accept-Encoding": "identity"}
    if connection.encrypted_token:
        headers["Authorization"] = "Bearer " + decrypt_value(connection.encrypted_token)
    try:
        async with asyncio.timeout(spec.timeout_seconds), _slots:
            async with httpx.AsyncClient(
                headers=headers,
                transport=BoundedTransport(retries=0),
                timeout=spec.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as http:
                async with streamable_http_client(url, http_client=http) as (
                    read,
                    write,
                    _,
                ):
                    async with ClientSession(
                        read,
                        write,
                        read_timeout_seconds=timedelta(seconds=spec.timeout_seconds),
                    ) as session:
                        initialized = await session.initialize()
                        discovered = await session.list_tools()
                        if discovered.nextCursor or len(discovered.tools) > 40:
                            raise ValueError("Tool discovery limit exceeded")
                        tools = sorted(
                            [
                                t.model_dump(mode="json", exclude_none=True)
                                for t in discovered.tools
                            ],
                            key=lambda t: t["name"],
                        )
                        fingerprint = digest(
                            {
                                "server": initialized.serverInfo.model_dump(),
                                "tools": tools,
                            }
                        )
                        if tool is None:
                            return {
                                "fingerprint": fingerprint,
                                "tools": tools,
                                "server": initialized.serverInfo.model_dump(),
                            }
                        if (
                            not connection.approved_fingerprint
                            or fingerprint != connection.approved_fingerprint
                        ):
                            raise ValueError(
                                "MCP capabilities changed; administrator reapproval required"
                            )
                        approved = next(
                            (t for t in connection.approved_tools if t["name"] == tool),
                            None,
                        )
                        if approved is None:
                            raise ValueError("Tool is not approved")
                        schema = {
                            **approved["inputSchema"],
                            "additionalProperties": False,
                        }
                        Draft202012Validator(schema).validate(arguments or {})
                        result = await session.call_tool(tool, arguments or {})
                        if result.isError or any(
                            not isinstance(c, TextContent) for c in result.content
                        ):
                            raise ValueError("MCP tool rejected the operation")
                        if len(result.model_dump_json().encode()) > WIRE_LIMIT:
                            raise ValueError("MCP result too large")
                        return {
                            "content": [
                                json.loads(c.text)
                                for c in result.content
                                if isinstance(c, TextContent)
                            ],
                            "structured": result.structuredContent,
                        }
    except (Exception, BaseExceptionGroup):
        # SDK exception groups and remote error text may contain credentials,
        # paths or SQL values. Keep them out of API errors and tracebacks.
        raise ExternalServiceError(
            "MCP operation failed: check service, credentials, approved capabilities and query limits. No automatic retry was made."
        ) from None


def result_rows(result: dict, backend: str) -> list[dict]:
    content = result["content"]
    if backend == "dbhub":
        payload = content[0]
        if not payload.get("success") or len(payload["data"]["statements"]) != 1:
            raise ValueError("Unexpected DBHub result")
        statement = payload["data"]["statements"][0]
        if statement.get("truncated"):
            raise ValueError("Server truncated query results")
        rows = statement["rows"]
    elif backend == "duckdb":
        payload = result.get("structured") or content[0]
        rows = payload["rows"]
    else:
        rows = []
        for item in content:
            rows.extend(item if isinstance(item, list) else [item])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Unexpected MCP row format")
    return rows
