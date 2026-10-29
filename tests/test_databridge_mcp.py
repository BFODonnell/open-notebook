"""Fail-closed policy and lifecycle contracts; real MCP tests live in scripts/."""

import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from open_notebook.databridge.mcp.client import (
    BoundedStream,
    endpoint,
    validate_input_schema,
)
from open_notebook.databridge.mcp.models import ConnectionSpec
from open_notebook.databridge.mcp.policy import readonly_sql
from open_notebook.databridge.mcp.service import require_admin
from open_notebook.databridge.mcp.versions import publish, published_manifest
from open_notebook.exceptions import AuthenticationError, ConfigurationError

pytest.importorskip("duckdb", reason="Install the databridge extra for MCP tests")
pytest.importorskip("sqlglot", reason="Install the databridge extra for MCP tests")

TABLES = {"sample": ["value", "label"]}
UNSAFE = [
    "DROP TABLE sample",
    "UPDATE sample SET value=9",
    "INSERT INTO sample VALUES(1)",
    "DELETE FROM sample",
    "ALTER TABLE sample ADD x INT",
    "SELECT value FROM sample; SELECT 1",
    "COPY sample TO '/tmp/leak'",
    "ATTACH '/tmp/other.db' AS other",
    "PRAGMA database_list",
    "SET enable_external_access=true",
    "INSTALL httpfs",
    "LOAD httpfs",
    "CALL evil()",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT read_blob('https://evil') FROM sample",
    "SELECT pg_read_file('/etc/passwd') FROM sample",
    "SELECT pg_sleep(100) FROM sample",
    "SELECT set_config('statement_timeout','0',false) FROM sample",
    "SELECT lo_import('/tmp/x') FROM sample",
    "SELECT value FROM other",
    "SELECT secret FROM sample",
    "SELECT * FROM sample",
    "SELECT value FROM other.public.sample",
    "SELECT value FROM private.sample",
    "SELECT value FROM sample -- unsafe comment",
    "SELECT /* comment */ value FROM sample",
    "WITH x AS (DELETE FROM sample RETURNING *) SELECT * FROM x",
    "SELECT value FROM sample FOR UPDATE",
    "SELECT value INTO output FROM sample",
    "SELECT value FROM sample UNION SELECT secret FROM sample",
    "SELECT a.value FROM sample a CROSS JOIN sample b",
    "SELECT (SELECT value FROM sample) FROM sample",
    "SELECT value FROM sample LIMIT -1",
    "SELECT value FROM sample OFFSET 100000000",
    "SELECT random() FROM sample",
    "SELECT current_setting('password') FROM sample",
]


@pytest.mark.parametrize("dialect", ["postgres", "duckdb", "sqlite"])
@pytest.mark.parametrize("sql", UNSAFE)
def test_unsafe_sql_is_rejected(sql, dialect):
    with pytest.raises(ValueError):
        readonly_sql(sql, dialect, TABLES, 10)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT value FROM sample",
        "SELECT SUM(value) AS total FROM sample",
        "SELECT COUNT(*) AS n FROM sample",
        "SELECT label, SUM(value) AS total FROM sample GROUP BY label ORDER BY total DESC",
        "SELECT value FROM sample WHERE value BETWEEN 1 AND 3 LIMIT 2",
        "SELECT value FROM sample WHERE label = '-- this is data'",
    ],
)
def test_bounded_select_subset(sql):
    safe = readonly_sql(sql, "duckdb", TABLES, 3)
    assert "LIMIT" in safe
    assert safe == readonly_sql(safe, "duckdb", TABLES, 3)


def test_parameters_are_escaped_ast_values():
    sql = readonly_sql(
        "SELECT value FROM sample WHERE label=:name",
        "postgres",
        TABLES,
        2,
        {"name": "'; DROP TABLE sample; --"},
    )
    import sqlglot

    tree = sqlglot.parse_one(sql, read="postgres")
    assert tree.args["where"].this.expression.this == "'; DROP TABLE sample; --"
    assert len(sqlglot.parse(sql, read="postgres")) == 1


@pytest.mark.parametrize(
    "params",
    [{}, {"x": 1, "extra": 2}, {"x": [1]}, {"x": float("nan")}, {"x": "x" * 1025}],
)
def test_bad_parameters(params):
    with pytest.raises(ValueError):
        readonly_sql(
            "SELECT value FROM sample WHERE value=:x", "duckdb", TABLES, 3, params
        )


def test_administrator_is_distinct(monkeypatch):
    monkeypatch.setenv("DATABRIDGE_MCP_ENABLED", "true")
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "app-password")
    monkeypatch.setenv("DATABRIDGE_MCP_ADMIN_KEY", "separate-long-administrator-key")
    with pytest.raises(AuthenticationError):
        require_admin("app-password")
    require_admin("separate-long-administrator-key")
    monkeypatch.setenv("DATABRIDGE_MCP_ADMIN_KEY", "app-password")
    with pytest.raises(ConfigurationError):
        require_admin("app-password")


def test_endpoint_is_operator_configured(monkeypatch):
    spec = ConnectionSpec(
        name="test",
        backend="dbhub",
        endpoint_ref="approved",
        dialect="postgres",
        notebooks=["notebook:one"],
    )
    monkeypatch.setenv(
        "DATABRIDGE_MCP_ENDPOINTS",
        json.dumps(
            {
                "approved": {
                    "url": "http://dbhub:8080/mcp",
                    "backend": "dbhub",
                    "readonly": True,
                }
            }
        ),
    )
    assert endpoint(spec) == "http://dbhub:8080/mcp"
    spec.endpoint_ref = "attacker"
    with pytest.raises(ConfigurationError):
        endpoint(spec)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "$ref": "https://attacker/schema"},
        {
            "type": "object",
            "properties": {"sql": {"type": "string", "pattern": "(a+)+$"}},
        },
        {"type": "object", "properties": {"sql": {"type": "object"}}},
    ],
)
def test_untrusted_schemas_cannot_fetch_urls_or_run_regex(schema):
    with pytest.raises(ValueError):
        validate_input_schema(schema)


@pytest.mark.asyncio
async def test_transport_stops_oversized_stream():
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 524288
            yield b"overflow"

    with pytest.raises(ValueError):
        async for _ in BoundedStream(Stream()):
            pass


def staged(root: Path, count: int) -> str:
    import duckdb

    key = str(uuid4())
    folder = root / "staging"
    folder.mkdir(exist_ok=True)
    with duckdb.connect(str(folder / f"{key}.duckdb")) as db:
        db.execute(
            "CREATE TABLE sample AS SELECT range AS value FROM range(?)", [count]
        )
        db.execute("CHECKPOINT")
    return key


@pytest.mark.skipif(os.name == "nt", reason="Publication runs in Linux deployment")
def test_versions_remain_immutable_and_tampering_is_denied(tmp_path):
    dataset = str(uuid4())
    first, second = staged(tmp_path, 3), staged(tmp_path, 6)
    a = publish(tmp_path, first, dataset)
    b = publish(tmp_path, second, dataset)
    assert a["sha256"] != b["sha256"]
    assert published_manifest(tmp_path, first)["sha256"] == a["sha256"]
    assert publish(tmp_path, first, dataset) == a
    with pytest.raises(ValueError):
        publish(tmp_path, first, str(uuid4()))
    path = tmp_path / "published" / f"{first}.duckdb"
    path.chmod(0o644)
    with path.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError):
        published_manifest(tmp_path, first)


@pytest.mark.skipif(os.name == "nt", reason="Publication runs in Linux deployment")
def test_publish_rejects_paths_symlinks_and_live_wal(tmp_path):
    key = staged(tmp_path, 3)
    with pytest.raises(ValueError):
        publish(tmp_path, "../../secret", str(uuid4()))
    path = tmp_path / "staging" / f"{key}.duckdb"
    wal = Path(str(path) + ".wal")
    wal.write_text("live transaction")
    with pytest.raises(ValueError):
        publish(tmp_path, key, str(uuid4()))
    wal.unlink()
    link = tmp_path / "staging" / f"{uuid4()}.duckdb"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        publish(tmp_path, link.stem, str(uuid4()))
