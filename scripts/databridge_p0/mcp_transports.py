"""Exercise real Docker MCP servers; compare clients on authenticated endpoints.

Only ephemeral synthetic SQLite data and random test tokens are used. Containers
bind loopback on Docker-assigned ports and are removed even on assertion failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sqlite3
import tempfile
from collections.abc import Sequence
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError
from mcp.types import TextContent

DBHUB = "bytebase/dbhub@sha256:aa04093100a15911c7ee326e870fa11480e1466342e8433fdd67b45c9af52ccf"
TOOLBOX = "us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox@sha256:7e4f7bfd93ccec33c066563a4ca700572e4ce95a8d45ba18577df8ee50b9481a"


def result_json(content: Sequence[object]) -> dict[str, Any]:
    assert len(content) == 1 and isinstance(content[0], TextContent)
    payload = json.loads(content[0].text)
    assert isinstance(payload, dict)
    return payload


async def docker(*args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), 60)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        # Arguments can contain test tokens; never echo them.
        raise RuntimeError(err.decode(errors="replace"))
    return (out + err if args[0] == "logs" else out).decode().strip()


def fixtures(root: Path) -> None:
    # Toolbox runs non-root; only synthetic public fixtures live in this directory.
    root.chmod(0o755)
    with sqlite3.connect(root / "sample.sqlite") as connection:
        connection.execute("CREATE TABLE sample (value INTEGER)")
        connection.executemany("INSERT INTO sample VALUES (?)", [(1,), (2,), (3,)])
    (root / "dbhub.toml").write_text(
        '[[sources]]\nid = "fixture"\ndsn = "sqlite:///fixtures/sample.sqlite"\n'
        '[[tools]]\nname = "execute_sql"\nsource = "fixture"\nreadonly = true\nmax_rows = 2\n'
        '[[tools]]\nname = "search_objects"\nsource = "fixture"\n',
        encoding="utf-8",
    )
    (root / "tools.yaml").write_text(
        "kind: source\nname: fixture\ntype: sqlite\n"
        'database: "file:/fixtures/sample.sqlite?mode=ro"\n'
        "---\nkind: tool\nname: sample-total\ntype: sqlite-sql\nsource: fixture\n"
        "description: Sum the three synthetic test rows.\n"
        "statement: SELECT SUM(value) AS total FROM sample\n",
        encoding="utf-8",
    )


async def official(url: str, token: str) -> dict:
    async with streamablehttp_client(
        url, headers={"Authorization": f"Bearer {token}"}, timeout=10
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool(
                "execute_sql", {"sql": "SELECT SUM(value) AS total FROM sample"}
            )
            assert not result.isError, result
            payload = result_json(result.content)
            assert payload["data"]["statements"][0]["rows"] == [{"total": 6}]
            return {
                "tools": [t.name for t in tools.tools],
                "result": result.model_dump(mode="json"),
            }


async def fastmcp(url: str, token: str) -> dict:
    transport = StreamableHttpTransport(
        url, headers={"Authorization": f"Bearer {token}"}
    )
    async with Client(transport, timeout=10) as client:
        tools = await client.list_tools()
        result = await client.call_tool(
            "execute_sql", {"sql": "SELECT SUM(value) AS total FROM sample"}
        )
        payload = result_json(result.content)
        assert payload["data"]["statements"][0]["rows"] == [{"total": 6}]
        return {
            "tools": [t.name for t in tools],
            "result": [c.model_dump(mode="json") for c in result.content],
        }


async def main() -> None:
    report: dict = {"fixture": "synthetic SQLite: 1, 2, 3", "checks": []}
    names: list[str] = []
    with tempfile.TemporaryDirectory(prefix="databridge-mcp-p0-") as directory:
        root = Path(directory)
        await asyncio.to_thread(fixtures, root)
        network = os.environ.get("P0_DOCKER_NETWORK")
        volume = os.environ.get("P0_DOCKER_VOLUME")
        mount = (
            f"type=volume,source={volume},target=/fixtures,volume-subpath={root.name},readonly"
            if volume
            else f"type=bind,source={root},target=/fixtures,readonly"
        )
        network_args = ["--network", network] if network else []
        try:
            endpoints = []
            for _ in range(2):
                name = "databridge-p0-dbhub-" + secrets.token_hex(4)
                token = secrets.token_urlsafe(24)
                names.append(name)
                await docker(
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--cpus",
                    "1",
                    "--memory",
                    "512m",
                    *network_args,
                    "--read-only",
                    "--tmpfs",
                    "/tmp",
                    "-p",
                    "127.0.0.1::8080",
                    "--mount",
                    mount,
                    "-e",
                    f"DBHUB_ALLOWED_HOSTS={name}",
                    "-e",
                    f"DBHUB_AUTH_TOKEN={token}",
                    DBHUB,
                    "--transport",
                    "http",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8080",
                    "--config",
                    "/fixtures/dbhub.toml",
                )
                port = (
                    "8080"
                    if network
                    else (await docker("port", name, "8080/tcp")).split(":")[-1]
                )
                host = f"{name}:8080" if network else f"127.0.0.1:{port}"
                endpoints.append((f"http://{host}/mcp", token))
            name = "databridge-p0-toolbox-" + secrets.token_hex(4)
            names.append(name)
            await docker(
                "run",
                "-d",
                "--name",
                name,
                "--cpus",
                "1",
                "--memory",
                "512m",
                *network_args,
                "--read-only",
                "--tmpfs",
                "/tmp",
                "-p",
                "127.0.0.1::5000",
                "--mount",
                mount,
                TOOLBOX,
                "--config",
                "/fixtures/tools.yaml",
                "--address",
                "0.0.0.0",
                "--disable-reload",
                "--disable-version-check",
            )
            port = (
                "5000"
                if network
                else (await docker("port", name, "5000/tcp")).split(":")[-1]
            )
            host = f"{name}:5000" if network else f"127.0.0.1:{port}"
            toolbox_url = f"http://{host}/mcp"
            async with httpx.AsyncClient(timeout=3) as http:
                for url, _ in endpoints:
                    for attempt in range(40):
                        try:
                            response = await http.get(
                                url.removesuffix("/mcp") + "/healthz"
                            )
                            if response.status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(0.25)
                    else:
                        raise AssertionError("DBHub startup timed out")
                    for headers in ({}, {"Authorization": "Bearer invalid-test-token"}):
                        response = await http.post(url, headers=headers, json={})
                        assert response.status_code == 401, response.status_code
                    report["checks"].append("DBHub missing/invalid bearer rejected")
            report["official"] = await asyncio.gather(
                *(official(*item) for item in endpoints)
            )
            report["fastmcp"] = await asyncio.gather(
                *(fastmcp(*item) for item in endpoints)
            )
            # Keep sessions separate: identical tool names must not merge authority.
            async with AsyncExitStack() as stack:
                read, write, _ = await stack.enter_async_context(
                    streamablehttp_client(
                        endpoints[0][0],
                        headers={"Authorization": f"Bearer {endpoints[0][1]}"},
                    )
                )
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                denied = await session.call_tool(
                    "execute_sql", {"sql": "DELETE FROM sample"}
                )
                report["denied_write"] = denied.model_dump(mode="json")
                assert denied.isError
                assert result_json(denied.content)["code"] == "READONLY_VIOLATION"
                capped = await session.call_tool(
                    "execute_sql", {"sql": "SELECT value FROM sample ORDER BY value"}
                )
                report["capped"] = capped.model_dump(mode="json")
                assert not capped.isError
                statement = result_json(capped.content)["data"]["statements"][0]
                assert statement["rows"] == [{"value": 1}, {"value": 2}]
                assert statement["truncated"] is True
                report["checks"].extend(
                    ["DBHub DELETE denied", "DBHub row cap enforced"]
                )
            async with streamablehttp_client(toolbox_url, timeout=10) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert {t.name for t in tools.tools} == {"sample-total"}
                    result = await session.call_tool("sample-total", {})
                    assert not result.isError, result
                    report["toolbox"] = result.model_dump(mode="json")
                    assert result_json(result.content) == {"total": 6}
                    try:
                        denied = await session.call_tool(
                            "execute_sql", {"sql": "DELETE FROM sample"}
                        )
                        assert denied.isError
                    except McpError as error:
                        assert "invalid tool name" in str(error)
                    report["checks"].append(
                        "Toolbox exposes only curated SELECT; arbitrary SQL tool rejected"
                    )
            print(json.dumps(report, indent=2))
        except BaseException:
            for name in names:
                if "toolbox" in name:
                    print(await docker("logs", name), flush=True)
            raise
        finally:
            for name in reversed(names):
                await docker("rm", "-f", name)


if __name__ == "__main__":
    if os.name == "nt":
        raise SystemExit(
            "Use Dockerfile.transports on Windows. The native OpenSSL failure can "
            "terminate Python without running container cleanup."
        )
    asyncio.run(main())
