"""Executable P0 experiment; no app imports, user data, or provider calls.

uv run --project scripts/databridge_p0 --frozen python \
    scripts/databridge_p0/duckdb_concurrency.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator

import duckdb
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent


def result_rows(result: CallToolResult) -> list:
    assert not result.isError
    assert len(result.content) == 1
    content = result.content[0]
    assert isinstance(content, TextContent)
    return json.loads(content.text)["rows"]


def build(path: Path, rows: int) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE sample AS SELECT range AS value FROM range(?)", [rows]
        )
        connection.execute("CHECKPOINT")


def aggregate(path: Path) -> tuple[int, int]:
    with duckdb.connect(str(path), read_only=True) as connection:
        row = connection.execute("SELECT count(*), sum(value) FROM sample").fetchone()
        assert row is not None
        return int(row[0]), int(row[1])


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def child(mode: str, path: Path) -> asyncio.subprocess.Process:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).resolve()),
        mode,
        str(path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return process


async def finish(process: asyncio.subprocess.Process) -> tuple[int, str]:
    stdout, stderr = await asyncio.wait_for(process.communicate(b"release\n"), 20)
    assert process.returncode is not None
    return process.returncode, (stdout + stderr).decode(errors="replace")


@asynccontextmanager
async def server(path: Path) -> AsyncIterator[ClientSession]:
    executable = Path(__file__).parent / "motherduck" / ".venv"
    executable /= "Scripts/python.exe" if os.name == "nt" else "bin/python"
    executable = Path(os.environ.get("P0_MOTHERDUCK_PYTHON", str(executable)))
    # Each trusted version has its own process; paths are never tool arguments.
    params = StdioServerParameters(
        # Resolving a POSIX venv symlink would launch the base Python without deps.
        command=str(executable.absolute()),
        args=[
            "-c",
            "from mcp_server_motherduck import main; main()",
            "--db-path",
            str(path),
            "--no-ephemeral-connections",
            "--max-rows",
            "10",
            "--max-chars",
            "2000",
            "--query-timeout",
            "5",
        ],
        env={"PYTHONUTF8": "1"},
    )
    with (
        tempfile.TemporaryDirectory(prefix="databridge-p0-mcp-log-") as log_directory,
        open(Path(log_directory) / "server.log", "w+", encoding="utf-8") as errors,
    ):
        async with stdio_client(params, errlog=errors) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=20)
            ) as session:
                await session.initialize()
                yield session


class ConcurrencyProof(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="databridge-p0-")
        self.root = Path(self.temporary.name)
        self.old = self.root / "version-1.duckdb"
        await asyncio.to_thread(build, self.old, 100)
        self.original_hash = await asyncio.to_thread(digest, self.old)
        self.processes: list[asyncio.subprocess.Process] = []

    async def asyncTearDown(self) -> None:
        for process in self.processes:
            if process.returncode is None:
                process.kill()
                await process.wait()
        await asyncio.to_thread(self.temporary.cleanup)

    async def start(self, mode: str, path: Path) -> asyncio.subprocess.Process:
        process = await child(mode, path)
        self.processes.append(process)
        return process

    async def ready(self, process: asyncio.subprocess.Process) -> None:
        assert process.stdout is not None
        self.assertEqual(
            (await asyncio.wait_for(process.stdout.readline(), 20)).strip(), b"READY"
        )

    async def test_same_file_writer_rejected_while_reader_holds_lock(self) -> None:
        reader = await self.start("hold-reader", self.old)
        await self.ready(reader)
        writer = await self.start("try-write", self.old)
        code, output = await finish(writer)
        self.assertEqual(code, 0, output)
        self.assertIn("LOCK_REJECTED", output)
        self.assertEqual((await finish(reader))[0], 0)
        self.assertEqual(await asyncio.to_thread(aggregate, self.old), (100, 4950))

    async def test_reader_rejected_while_writer_holds_same_file(self) -> None:
        writer = await self.start("hold-writer", self.old)
        await self.ready(writer)
        with self.assertRaises(duckdb.IOException):
            await asyncio.to_thread(aggregate, self.old)
        self.assertEqual((await finish(writer))[0], 0)

    async def test_versioned_publish_during_real_mcp_reads(self) -> None:
        staged = self.root / "staging.duckdb"
        published = self.root / "version-2.duckdb"
        async with server(self.old) as first, server(self.old) as second:
            tool_names = {tool.name for tool in (await first.list_tools()).tools}
            self.assertIn("execute_query", tool_names)
            self.assertNotIn("switch_database_connection", tool_names)
            writer = await self.start("stage", staged)
            await self.ready(writer)  # writer transaction remains open until finish()
            for _ in range(20):
                results = await asyncio.gather(
                    *[
                        session.call_tool(
                            "execute_query",
                            {
                                "sql": "SELECT count(*) AS n, sum(value) AS total FROM sample"
                            },
                        )
                        for session in (first, second)
                    ]
                )
                for result in results:
                    self.assertEqual(result_rows(result), [[100, 4950]])
            self.assertFalse(published.exists())
            self.assertEqual((await finish(writer))[0], 0)
            self.assertFalse(Path(str(staged) + ".wal").exists())
            self.assertEqual(await asyncio.to_thread(aggregate, staged), (200, 19900))
            await asyncio.to_thread(staged.rename, published)
            async with server(published) as new:
                result = await new.call_tool(
                    "execute_query", {"sql": "SELECT sum(value) AS total FROM sample"}
                )
                self.assertEqual(result_rows(result), [[19900]])
            result = await first.call_tool(
                "execute_query", {"sql": "SELECT sum(value) FROM sample"}
            )
            self.assertEqual(result_rows(result), [[4950]])
            denied = await first.call_tool(
                "execute_query", {"sql": "DELETE FROM sample"}
            )
            # Server may serialize a DuckDB error as text instead of isError.
            self.assertTrue(
                denied.isError or "read-only" in denied.model_dump_json().lower()
            )
        self.assertEqual(await asyncio.to_thread(digest, self.old), self.original_hash)
        # Restarted server can reopen durable published data.
        async with server(published) as restarted:
            result = await restarted.call_tool(
                "execute_query", {"sql": "SELECT sum(value) FROM sample"}
            )
            self.assertEqual(result_rows(result), [[19900]])

    async def test_aborted_stage_does_not_change_published_version(self) -> None:
        staged = self.root / "failed.duckdb"
        writer = await self.start("abort-stage", staged)
        await self.ready(writer)
        self.assertEqual(await asyncio.to_thread(aggregate, self.old), (100, 4950))
        self.assertEqual((await finish(writer))[0], 0)
        self.assertEqual(await asyncio.to_thread(digest, self.old), self.original_hash)
        with self.assertRaises(duckdb.CatalogException):
            await asyncio.to_thread(aggregate, staged)


def child_main(mode: str, path: Path) -> None:
    if mode == "try-write":
        try:
            connection = duckdb.connect(str(path))
        except duckdb.IOException:
            print("LOCK_REJECTED")
            return
        connection.close()
        raise AssertionError("Writer unexpectedly acquired a reader-held file")
    with duckdb.connect(str(path), read_only=mode == "hold-reader") as connection:
        if mode in {"stage", "abort-stage"}:
            connection.execute("BEGIN")
            connection.execute(
                "CREATE TABLE sample AS SELECT range AS value FROM range(200)"
            )
        print("READY", flush=True)
        input()
        if mode in {"stage", "abort-stage"}:
            connection.execute("COMMIT" if mode == "stage" else "ROLLBACK")
            connection.execute("CHECKPOINT")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in {
        "hold-reader",
        "hold-writer",
        "try-write",
        "stage",
        "abort-stage",
    }:
        child_main(sys.argv[1], Path(sys.argv[2]))
    else:
        print(
            json.dumps({"duckdb": duckdb.__version__, "platform": sys.platform}),
            flush=True,
        )
        unittest.main(verbosity=2)
