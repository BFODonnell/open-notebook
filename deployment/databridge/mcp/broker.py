"""Version-scoped MotherDuck process broker. No Docker socket or app secrets.

The official SDK serves HTTP and speaks stdio to the isolated accepted server.
Each request owns its version's process until completion/cancellation. No process
can switch files, and no untrusted filesystem path or launch command is accepted.
"""

import asyncio
import json
import os
import secrets
from datetime import timedelta
from pathlib import Path

import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import TextContent
from starlette.responses import JSONResponse

from open_notebook.databridge.mcp.policy import readonly_sql
from open_notebook.databridge.mcp.versions import published_manifest, version_key

ROOT = Path("/datasets")
SLOTS = asyncio.Semaphore(2)
server = FastMCP(
    "databridge-immutable-duckdb",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=["duckdb-broker:8080", "localhost:8080", "127.0.0.1:8080"]
    ),
)


@server.tool()
async def describe_version(version_id: str) -> dict:
    """Read a verified immutable version's bounded schema."""
    try:
        async with asyncio.timeout(10), SLOTS:
            manifest = await asyncio.to_thread(
                published_manifest, ROOT, version_key(version_id)
            )
        return {
            "version_id": manifest["version_id"],
            "sha256": manifest["sha256"],
            "schema": manifest["schema"],
        }
    except Exception:
        raise ValueError(
            "Dataset version unavailable or integrity check failed"
        ) from None


@server.tool()
async def execute_query(version_id: str, sql: str) -> dict:
    """Run one bounded SELECT on one approved immutable dataset version."""
    try:
        async with asyncio.timeout(20), SLOTS:
            version = version_key(version_id)
            manifest = await asyncio.to_thread(published_manifest, ROOT, version)
            canonical = readonly_sql(sql, "duckdb", manifest["tables"], 1000)
            params = StdioServerParameters(
                command="/opt/motherduck/.venv/bin/python",
                args=[
                    "-c",
                    "from mcp_server_motherduck import main; main()",
                    "--db-path",
                    str(ROOT / "published" / f"{version}.duckdb"),
                    "--no-ephemeral-connections",
                    "--max-rows",
                    "1000",
                    "--max-chars",
                    "262144",
                    "--query-timeout",
                    "3",
                    "--init-sql",
                    "SET enable_external_access=false; SET autoinstall_known_extensions=false; SET autoload_known_extensions=false; SET threads=1; SET memory_limit='256MB'; SET lock_configuration=true;",
                ],
                env={"HOME": "/tmp", "PYTHONUTF8": "1"},
            )
            with open(os.devnull, "w") as errors:
                async with stdio_client(params, errlog=errors) as (read, write):
                    async with ClientSession(
                        read, write, read_timeout_seconds=timedelta(seconds=10)
                    ) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        if "switch_database_connection" in {
                            t.name for t in tools.tools
                        }:
                            raise ValueError("Unsafe server capabilities")
                        response = await session.call_tool(
                            "execute_query", {"sql": canonical}
                        )
                        if (
                            response.isError
                            or len(response.content) != 1
                            or not isinstance(response.content[0], TextContent)
                        ):
                            raise ValueError("Query failed")
                        payload = json.loads(response.content[0].text)
                        if "error" in payload or payload.get("truncated"):
                            raise ValueError("Query failed or was truncated")
                        columns = payload["columns"]
                        names = [
                            c["name"] if isinstance(c, dict) else c for c in columns
                        ]
                        rows = [
                            dict(zip(names, row, strict=True))
                            for row in payload["rows"]
                        ]
                        result = {
                            "rows": rows,
                            "version_id": version,
                            "dataset_sha256": manifest["sha256"],
                        }
                        if len(json.dumps(result).encode()) > 262144:
                            raise ValueError("Result too large")
                        return result
    except (Exception, BaseExceptionGroup):
        raise ValueError(
            "Version query failed or exceeded policy/resource limits"
        ) from None


class AuthBoundary:
    def __init__(self, app):
        self.app = app
        self.key = os.environ["DATABRIDGE_DUCKDB_TOKEN"]
        if len(self.key) < 20:
            raise ValueError("A strong broker token is required")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] == "/health" and scope["method"] == "GET":
            return await JSONResponse({"ready": True})(scope, receive, send)
        headers = dict(scope["headers"])
        expected = ("Bearer " + self.key).encode()
        if headers.get(b"origin") or not secrets.compare_digest(
            headers.get(b"authorization", b""), expected
        ):
            return await JSONResponse({"error": "Unauthorized"}, status_code=401)(
                scope, receive, send
            )
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > 65536:
                raise ValueError("Request too large")
            return message

        return await self.app(scope, bounded_receive, send)


if __name__ == "__main__":
    uvicorn.run(
        AuthBoundary(server.streamable_http_app()),
        host="0.0.0.0",
        port=8080,
        log_level="warning",
    )
