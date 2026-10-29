"""Run inside the synthetic broker; bypass AST to verify engine defenses via MCP."""

import asyncio
import json
import os
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent


async def main():
    assert os.environ.get("DATABRIDGE_DUCKDB_TOKEN") == "p2-fixture-duckdb-token-only"
    database = next(Path("/datasets/published").glob("*.duckdb"))
    params = StdioServerParameters(
        command="/opt/motherduck/.venv/bin/python",
        args=[
            "-c",
            "import os; assert not any(k in os.environ for k in ['DATABRIDGE_DUCKDB_TOKEN','LITELLM_APP_VIRTUAL_KEY','OPEN_NOTEBOOK_ENCRYPTION_KEY']); from mcp_server_motherduck import main; main()",
            "--db-path",
            str(database),
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
        async with asyncio.timeout(30):
            async with stdio_client(params, errlog=errors) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    assert "switch_database_connection" not in {
                        t.name for t in tools.tools
                    }
                    print(
                        "PASS: isolated child receives no broker/application secrets or database switching tool",
                        flush=True,
                    )
                    for sql in [
                        "CREATE TABLE forbidden(value INTEGER)",
                        "SELECT * FROM read_csv('/etc/passwd')",
                        "SET enable_external_access=true",
                        "INSTALL httpfs",
                        "SELECT SUM(random()) FROM range(1000000000000)",
                    ]:
                        start = time.monotonic()
                        result = await client.call_tool("execute_query", {"sql": sql})
                        assert isinstance(result.content[0], TextContent)
                        content = (
                            {} if result.isError else json.loads(result.content[0].text)
                        )
                        assert result.isError or "error" in content, (sql, content)
                        assert time.monotonic() - start < 8
                        print("PASS: engine denial/timeout:", sql, flush=True)
    print("6 engine/child isolation checks passed", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
