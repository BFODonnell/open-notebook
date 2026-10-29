"""Fixture-only, real HTTP/MCP/SurrealDB acceptance. See README for restart steps."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import duckdb
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.databridge.mcp.client import digest
from open_notebook.databridge.mcp.models import MCPConnection
from open_notebook.utils.encryption import decrypt_value

STATE = Path("/app/data/p2-acceptance.json")
CHECKS = []
PREFIX = "/api/databridge"
ADMIN = "p2-fixture-admin-key-only"


def check(condition, message):
    assert condition, message
    CHECKS.append(message)
    print("PASS:", message, flush=True)


async def protocol(url, token, tool, args):
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.list_tools()
                return await session.call_tool(tool, args)


async def main(mode):
    assert os.getenv("SURREAL_PASSWORD") == "p1-fixture-only", "Fixture-only runner"
    async with httpx.AsyncClient(
        base_url="http://localhost:5055",
        headers={"Authorization": "Bearer p1-fixture-password-only"},
        timeout=45,
    ) as client:

        async def api(method, path, data=None, expected=200, admin=True):
            response = await client.request(
                method,
                PREFIX + path,
                json=data,
                headers={"X-DataBridge-Admin": ADMIN} if admin else {},
            )
            assert response.status_code == expected, (
                path,
                response.status_code,
                response.text[:400],
            )
            return response.json()

        async def approve(connection):
            path = "/mcp/servers/" + connection["id"]
            found = await api("POST", path + "/discover")
            await api("POST", path + "/approve", {"fingerprint": found["fingerprint"]})
            return found

        async def plan(connection, notebook, **kwargs):
            body = {"connection_id": connection["id"], "notebook_id": notebook}
            if connection["backend"] == "toolbox":
                body.update(tool="sample-total", parameters={"minimum": 1})
            else:
                body["sql"] = "SELECT SUM(value) AS total FROM sample"
            body.update(kwargs)
            return await api("POST", "/query/plans", body)

        async def execute(pending, notebook, expected=200, token=None):
            return await api(
                "POST",
                "/query/plans/" + pending["id"] + "/execute",
                {
                    "notebook_id": notebook,
                    "approval_token": token or pending["approval_token"],
                },
                expected,
            )

        async def total(connection, notebook, expected):
            result = await execute(await plan(connection, notebook), notebook)
            check(
                len(result["rows"]) == 1
                and int(result["rows"][0]["total"]) == expected,
                connection["name"] + " real MCP result",
            )
            check(
                result["result_sha256"] == digest(result["rows"]),
                "Canonical evidence hash",
            )
            return result

        if mode != "seed":
            state = json.loads(STATE.read_text())
            nb, connections = state["notebook"], state["connections"]
            if mode in {"outage", "drift"}:
                await execute(await plan(connections["dbhub"], nb), nb, 502)
                runs = await api(
                    "GET",
                    f"/query/runs?connection_id={connections['dbhub']['id']}&notebook_id={nb}",
                )
                check(
                    runs[0]["status"] == "failed" and "rows" not in runs[0],
                    mode + " produces durable failure, no fabricated rows",
                )
            elif mode == "restart":
                for backend, connection in connections.items():
                    await total(connection, nb, 6)
                old = await api(
                    "GET", f"/evidence/{state['evidence']['id']}?notebook_id={nb}"
                )
                check(
                    old == state["evidence"],
                    "Evidence, version and hashes survive application/SurrealDB/broker restart",
                )
                check(
                    len(await api("GET", "/dataset-versions")) >= 2,
                    "Immutable versions survive restart",
                )
            else:
                raise ValueError("Unknown mode")
        else:

            async def notebook(name):
                result = await client.post(
                    "/api/notebooks",
                    json={"name": name, "description": "P2 synthetic fixture"},
                )
                result.raise_for_status()
                return result.json()["id"]

            nb, other = (
                await notebook("P2 acceptance"),
                await notebook("P2 excluded scope"),
            )
            unauth = await httpx.AsyncClient().get(
                "http://localhost:5055" + PREFIX + "/mcp/servers?notebook_id=" + nb
            )
            check(unauth.status_code == 401, "Application authentication required")
            await api("GET", "/mcp/endpoints", expected=401, admin=False)
            check(
                True,
                "Application password alone cannot administer database connections",
            )

            dataset = str(uuid4())

            async def publish(count):
                version = str(uuid4())
                path = (
                    Path(os.environ["DATABRIDGE_DATA_ROOT"])
                    / "staging"
                    / (version + ".duckdb")
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                with duckdb.connect(str(path)) as db:
                    db.execute("CREATE TABLE sample(value INTEGER)")
                    db.executemany(
                        "INSERT INTO sample VALUES (?)",
                        [(n,) for n in range(1, count + 1)],
                    )
                    db.execute("CHECKPOINT")
                payload = {"staging_id": version, "dataset_id": dataset}
                result = await api("POST", "/dataset-versions/publish", payload)
                repeated = await api("POST", "/dataset-versions/publish", payload)
                check(
                    result == repeated,
                    "Publication retry safely reconciles existing manifest/registry",
                )
                return result

            first, second = await publish(3), await publish(6)
            check(
                first["sha256"] != second["sha256"]
                and first["schema_sha256"] == second["schema_sha256"],
                "Immutable content versions, stable schema identity",
            )
            await api(
                "POST",
                "/dataset-versions/publish",
                {"staging_id": "../escape", "dataset_id": dataset},
                400,
            )
            await api(
                "POST",
                "/dataset-versions/publish",
                {"staging_id": first["version_id"], "dataset_id": str(uuid4())},
                400,
            )
            check(True, "Publication rejects path traversal and version reassignment")
            connections = {}
            evidence = None
            for backend in ["dbhub", "toolbox", "duckdb"]:
                spec: dict = {
                    "name": backend,
                    "backend": backend,
                    "endpoint_ref": backend,
                    "dialect": "duckdb" if backend == "duckdb" else "postgres",
                    "notebooks": [nb],
                    "tables": {"sample": ["value"]},
                    "token": f"p2-fixture-{backend}-token-only",
                    "max_rows": 2,
                    "max_bytes": 1024,
                    "timeout_seconds": 30,
                }
                if backend == "duckdb":
                    spec["version_id"] = first["version_id"]
                if backend == "toolbox":
                    spec.update(
                        curated_tools=[
                            "sample-total",
                            "sample-schema",
                            "sample-slow",
                            "sample-wide",
                        ],
                        schema_tool="sample-schema",
                    )
                await api(
                    "POST", "/mcp/servers", {**spec, "endpoint_ref": "unapproved"}, 422
                )
                connection = await api("POST", "/mcp/servers", spec)
                connections[backend] = connection
                body = {
                    "connection_id": connection["id"],
                    "notebook_id": nb,
                    "sql": "SELECT value FROM sample",
                }
                await api("POST", "/query/plans", body, 400)
                found = await approve(connection)
                check(
                    found["tools"] and found["server"],
                    backend
                    + " real initialize/list_tools and explicit signature approval",
                )
                schema = await api(
                    "GET", f"/mcp/servers/{connection['id']}/schema?notebook_id={nb}"
                )
                check(bool(schema["columns"]), backend + " real schema discovery")
                if backend != "duckdb":
                    assert all(
                        row["column_name"] == "value" for row in schema["columns"]
                    )
                check(
                    "secret" not in json.dumps(schema),
                    backend + " schema respects database/connection column scope",
                )
                evidence = await total(connection, nb, 6)
                await api(
                    "GET",
                    f"/evidence/{evidence['id']}?notebook_id={other}",
                    expected=404,
                )
                await api("POST", "/query/plans", {**body, "notebook_id": other}, 404)
                check(
                    True, backend + " connection and evidence notebook scope enforced"
                )
                stored = await MCPConnection.get(connection["id"])
                assert stored.encrypted_token is not None
                check(
                    stored.encrypted_token != spec["token"]
                    and decrypt_value(stored.encrypted_token) == spec["token"],
                    backend + " token encrypted at rest",
                )
                public = json.dumps(await api("GET", "/mcp/servers?notebook_id=" + nb))
                check(
                    spec["token"] not in public
                    and "encrypted_token" not in public
                    and "postgres://" not in public,
                    backend + " public registry excludes credential values",
                )

                if backend != "toolbox":
                    capped = await execute(
                        await plan(
                            connection, nb, sql="SELECT value FROM sample LIMIT 999"
                        ),
                        nb,
                    )
                    check(
                        len(capped["rows"]) == 2,
                        backend + " application row cap enforced before execution",
                    )
                    for sql in [
                        "DELETE FROM sample",
                        "SELECT value FROM sample; DROP TABLE sample",
                        "SELECT secret FROM sample",
                        "SELECT value FROM hidden.sample",
                        "SELECT * FROM read_csv('/etc/passwd')",
                        "SELECT pg_sleep(3) FROM sample",
                        "SELECT value FROM sample -- comment",
                        "WITH x AS (DELETE FROM sample RETURNING *) SELECT * FROM x",
                        "SELECT value FROM sample JOIN sample x USING(value)",
                    ]:
                        await api("POST", "/query/plans", {**body, "sql": sql}, 400)
                    check(
                        True,
                        backend
                        + " writes, multi-statements, files, hidden columns/catalogs, functions, comments, CTEs and joins rejected",
                    )
                    runs = await api(
                        "GET",
                        f"/query/runs?connection_id={connection['id']}&notebook_id={nb}",
                    )
                    denied = [
                        r
                        for r in runs
                        if r["status"] == "denied" and "request_sha256" in r
                    ]
                    check(
                        len(denied) >= 9 and all("sql" not in r for r in denied),
                        backend + " rejected SQL has hash-only audit records",
                    )
                else:
                    for values in [
                        {"minimum": "1; DROP TABLE sample"},
                        {"minimum": 1, "extra": "x"},
                    ]:
                        await api(
                            "POST",
                            "/query/plans",
                            {
                                "connection_id": connection["id"],
                                "notebook_id": nb,
                                "tool": "sample-total",
                                "parameters": values,
                            },
                            400,
                        )
                    check(
                        True, "Toolbox rejects parameter injection and extra arguments"
                    )
                    for tool in ["sample-wide", "sample-slow"]:
                        started = time.monotonic()
                        await execute(
                            await plan(connection, nb, tool=tool, parameters={}),
                            nb,
                            502,
                        )
                        check(
                            time.monotonic() - started < 12,
                            tool + " bounded failure (byte cap or database timeout)",
                        )

            # One-use approvals are claimed atomically, including concurrent requests.
            connection = connections["dbhub"]
            pending = await plan(connection, nb)
            await execute(pending, nb, 400, "incorrect")
            results = await asyncio.gather(
                *[
                    client.post(
                        PREFIX + "/query/plans/" + pending["id"] + "/execute",
                        json={
                            "notebook_id": nb,
                            "approval_token": pending["approval_token"],
                        },
                    )
                    for _ in range(2)
                ]
            )
            check(
                sorted(r.status_code for r in results) == [200, 400],
                "Concurrent approval is executed exactly once",
            )
            await execute(pending, nb, 400)
            pending = await plan(connection, nb)
            await repo_query(
                "UPDATE $id SET expires_at='2000-01-01T00:00:00+00:00'",
                {"id": ensure_record_id(pending["id"])},
            )
            await execute(pending, nb, 400)
            check(True, "Wrong, expired and replayed approvals cannot execute")

            pending = await plan(connection, nb)
            stored = await MCPConnection.get(connection["id"])
            await api(
                "PUT",
                "/mcp/servers/" + connection["id"],
                {**stored.spec, "enabled": False},
            )
            await execute(pending, nb, 404)
            await api("PUT", "/mcp/servers/" + connection["id"], stored.spec)
            await approve(connection)
            await execute(pending, nb, 400)
            check(
                True, "Disabling, updating or reapproving invalidates pending execution"
            )

            # Separate bearer values must never be reused across MCP services/sessions.
            for backend in ["dbhub", "toolbox", "duckdb"]:
                stored = await MCPConnection.get(connections[backend]["id"])
                wrong = await api(
                    "POST",
                    "/mcp/servers",
                    {
                        **stored.spec,
                        "name": "wrong-token",
                        "token": "p2-fixture-wrong-token-only",
                    },
                )
                error = await api(
                    "POST", "/mcp/servers/" + wrong["id"] + "/discover", expected=502
                )
                check(
                    "p2-fixture" not in json.dumps(error),
                    backend + " wrong credential fails without disclosure",
                )
                await total(connections[backend], nb, 6)
            async with httpx.AsyncClient() as http:
                for host in ["dbhub", "toolbox-gateway", "duckdb-broker"]:
                    response = await http.post(
                        f"http://{host}:8080/mcp",
                        headers={"Authorization": "Bearer not-the-service-token"},
                        json={},
                    )
                    check(
                        response.status_code == 401,
                        host + " independently authenticates MCP transport",
                    )

            # Test defense below the application's AST gate with real MCP tools.
            for sql in ["DELETE FROM sample", "SELECT secret FROM sample"]:
                response = await protocol(
                    "http://dbhub:8080/mcp",
                    "p2-fixture-dbhub-token-only",
                    "execute_sql",
                    {"sql": sql},
                )
                check(
                    response.isError
                    or '"success":false'
                    in response.model_dump_json().replace('\\"', '"').replace(" ", ""),
                    "DBHub/database defense rejects " + sql.split()[0],
                )
            started = time.monotonic()
            response = await protocol(
                "http://dbhub:8080/mcp",
                "p2-fixture-dbhub-token-only",
                "execute_sql",
                {"sql": "SELECT pg_sleep(4)"},
            )
            check(
                time.monotonic() - started < 8
                and (
                    response.isError or "timeout" in response.model_dump_json().lower()
                ),
                "DBHub database statement timeout is active",
            )
            response = await protocol(
                "http://duckdb-broker:8080/mcp",
                "p2-fixture-duckdb-token-only",
                "execute_query",
                {
                    "version_id": first["version_id"],
                    "sql": "SELECT * FROM read_csv('/etc/passwd')",
                },
            )
            check(
                response.isError,
                "DuckDB broker rejects external reads independently of application",
            )
            response = await protocol(
                "http://duckdb-broker:8080/mcp",
                "p2-fixture-duckdb-token-only",
                "describe_version",
                {"version_id": str(uuid4())},
            )
            check(response.isError, "Unknown immutable version is unavailable")
            stored = await MCPConnection.get(connections["duckdb"]["id"])
            newer = await api(
                "POST",
                "/mcp/servers",
                {
                    **stored.spec,
                    "name": "duckdb-version-two",
                    "version_id": second["version_id"],
                    "token": "p2-fixture-duckdb-token-only",
                },
            )
            await approve(newer)
            new_result = await total(newer, nb, 21)
            old_result = await total(connections["duckdb"], nb, 6)
            check(
                new_result["version_id"] == second["version_id"]
                and old_result["version_id"] == first["version_id"],
                "Old and new immutable database selections coexist",
            )
            check(
                new_result["dataset_sha256"] == second["sha256"]
                and old_result["dataset_sha256"] == first["sha256"],
                "Evidence binds each query to the exact published database hash",
            )
            STATE.write_text(
                json.dumps(
                    {"notebook": nb, "connections": connections, "evidence": evidence}
                )
            )
        print(
            json.dumps({"mode": mode, "passed": len(CHECKS), "checks": CHECKS}),
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
