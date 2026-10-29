import json
import os
import stat
import zipfile

import httpx
import pytest

from open_notebook.databridge.ingestion import catalog, download


@pytest.mark.parametrize(
    "url",
    [
        "http://data.transportation.gov/a.csv",
        "file:///etc/passwd",
        "https://localhost/a",
        "https://data.transportation.gov.evil.test/a",
        "https://data.transportation.gov:444/a",
        "https://user:pass@data.transportation.gov/a",
        "https://data.transportation.gov/a#fragment",
        "https://data.transportation.gov/a?api_key=secret",
        "https://data.transportation.gov\\@localhost/a",
        "https://data.transportation.gov/a\r\nHost: localhost",
    ],
)
def test_download_url_is_public_allowlisted_https(url):
    with pytest.raises(download.AcquisitionError):
        download.validate_public_url(url, {"data.transportation.gov"})


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
        "100.64.0.1",
        "198.18.0.1",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fd00:ec2::254",
        "::ffff:127.0.0.1",
        "2001:db8::1",
        "2002:7f00:0001::",
        "64:ff9b::7f00:1",
    ],
)
def test_nonpublic_ip_denied(ip):
    assert not download.public_ip(ip)


@pytest.mark.asyncio
async def test_mixed_dns_answer_fails_closed(monkeypatch):
    async def resolve(host):
        return ["93.184.216.34", "127.0.0.1"]

    monkeypatch.setattr(download, "resolve", resolve)
    with pytest.raises(download.AcquisitionError, match="DOWNLOAD_BLOCKED"):
        await download.pinned_target(
            "https://data.transportation.gov/file.csv", {"data.transportation.gov"}
        )


class Bytes(httpx.AsyncByteStream):
    def __init__(self, content):
        self.content = content

    async def __aiter__(self):
        yield self.content


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        download.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )

    async def resolve(host):
        return ["93.184.216.34"]

    monkeypatch.setattr(download, "resolve", resolve)


@pytest.mark.asyncio
async def test_dns_is_pinned_and_host_sni_preserved(monkeypatch, tmp_path):
    observed = []

    def handler(request):
        observed.append(request)
        return httpx.Response(200, stream=Bytes(b"a,b\n1,2\n"))

    transport(monkeypatch, handler)
    result = await download.fetch(
        "https://data.transportation.gov/a.csv", tmp_path / "file"
    )
    assert result.bytes == 8
    assert len(observed) == 1
    assert observed[0].url.host == "93.184.216.34"
    assert observed[0].headers["host"] == "data.transportation.gov"
    assert observed[0].extensions["sni_hostname"] == "data.transportation.gov"
    assert "x-api-key" not in observed[0].headers


@pytest.mark.parametrize(
    "location",
    [
        "http://data.transportation.gov/a",
        "https://localhost/a",
        "https://169.254.169.254/latest",
        "https://unapproved.test/a",
    ],
)
@pytest.mark.asyncio
async def test_redirect_revalidated_before_connect(monkeypatch, tmp_path, location):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": location}, stream=Bytes(b""))

    transport(monkeypatch, handler)
    with pytest.raises(download.AcquisitionError, match="DOWNLOAD_BLOCKED"):
        await download.fetch("https://data.transportation.gov/a.csv", tmp_path / "file")
    assert len(requests) == 1


@pytest.mark.parametrize(
    "status,headers,content,code",
    [
        (429, {}, b"", "RATE_LIMITED"),
        (404, {}, b"", "SOURCE_UNAVAILABLE"),
        (403, {}, b"", "SOURCE_AUTH_REQUIRED"),
        (200, {"content-length": "100"}, b"a", "TRANSFER_LIMIT"),
        (200, {}, b"a" * 33, "TRANSFER_LIMIT"),
        (200, {"content-encoding": "gzip"}, b"x", "HTTP_COMPRESSION_BLOCKED"),
        (200, {"content-length": "9"}, b"short", "INCOMPLETE_TRANSFER"),
    ],
)
@pytest.mark.asyncio
async def test_transfer_failure_limits(
    monkeypatch, tmp_path, status, headers, content, code
):
    transport(
        monkeypatch,
        lambda request: httpx.Response(status, headers=headers, stream=Bytes(content)),
    )
    with pytest.raises(download.AcquisitionError, match=code):
        await download.fetch(
            "https://data.transportation.gov/a.csv", tmp_path / "file", limit=32
        )


@pytest.mark.parametrize(
    "metadata,status",
    [
        ({"accessLevel": "non-public"}, "unavailable"),
        ({"accessLevel": "restricted public"}, "unavailable"),
        ({"accessLevel": "public", "rights": "permission required"}, "unavailable"),
        ({"accessLevel": "public"}, "checking"),
        ({}, "unavailable"),
    ],
)
def test_rights_are_not_inferred_from_public_catalog(metadata, status):
    resource = {
        "downloadURL": "https://data.transportation.gov/file.csv",
        "format": "CSV",
    }
    assert catalog.classify(metadata, resource)["status"] == status


def test_excel_api_and_ambiguous_formats_require_adapters():
    for resource in [
        {"accessURL": "https://data.transportation.gov/api"},
        {"downloadURL": "https://data.transportation.gov/file.xlsx", "format": "XLSX"},
        {"downloadURL": "https://data.transportation.gov/file.csv", "format": "JSON"},
    ]:
        assert (
            catalog.classify({"accessLevel": "public"}, resource)["status"]
            == "connector_required"
        )


@pytest.fixture
def parser():
    pytest.importorskip("duckdb")
    from open_notebook.databridge.ingestion.parser import stage

    return stage


@pytest.mark.parametrize(
    "kind,content",
    [
        ("csv", b"Year,NTD ID,Trips\n2022,0001,10\n2023,0002,20\n"),
        (
            "json",
            json.dumps(
                [
                    {"Year": 2022, "NTD ID": "0001", "Trips": 10},
                    {"Year": 2023, "NTD ID": "0002", "Trips": 20},
                ]
            ).encode(),
        ),
        (
            "jsonl",
            b'{"Year":2022,"NTD ID":"0001","Trips":10}\n{"Year":2023,"NTD ID":"0002","Trips":20}\n',
        ),
    ],
)
def test_formats_and_identifier_mapping(parser, tmp_path, kind, content):
    import duckdb

    source = tmp_path / "input"
    source.write_bytes(content)
    result = parser(source, tmp_path / "version.duckdb", kind)
    assert result["rows"] == 2
    assert result["preview"][0]["c_2_ntd_id"] == "0001"
    with duckdb.connect(str(tmp_path / "version.duckdb"), read_only=True) as db:
        assert db.execute("SELECT SUM(c_3_trips) FROM data").fetchone() == (30,)


def test_parquet_is_local_and_preserves_data(parser, tmp_path):
    import duckdb

    source = tmp_path / "input.parquet"
    with duckdb.connect() as db:
        db.execute(
            "COPY (SELECT 2022 AS year, '001' AS agency_id, 42 AS trips) TO ? (FORMAT PARQUET)",
            [str(source)],
        )
    result = parser(source, tmp_path / "version.duckdb", "parquet")
    assert result["rows"] == 1 and result["preview"][0]["c_2_agency_id"] == "001"


@pytest.mark.parametrize(
    "kind,content",
    [
        ("csv", b"<!doctype html><html>login</html>"),
        ("csv", b"a,b\n1,2,3\n"),
        ("csv", b"a,a\n1,2\n"),
        ("csv", b"a\n"),
        ("json", b'{"records":[]}'),
        ("json", b'[{"a":{"nested":1}}]'),
        ("json", b'[{"a":NaN}]'),
        ("json", b'[{"a":1,"a":2}]'),
        ("json", b'[{"a":1},{"b":2}]'),
        ("parquet", b"PAR1not-parquetPAR1"),
    ],
)
def test_malformed_and_unsupported_data_rejected(parser, tmp_path, kind, content):
    (tmp_path / "input").write_bytes(content)
    with pytest.raises(Exception):
        parser(tmp_path / "input", tmp_path / "version.duckdb", kind)


def archive(path, name, body, mode=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(name)
        info.compress_type = zipfile.ZIP_DEFLATED
        if mode:
            info.external_attr = mode << 16
        z.writestr(info, body)


@pytest.mark.parametrize(
    "name,body,mode",
    [
        ("../escape.csv", b"x\n1\n", None),
        ("/absolute.csv", b"x\n1\n", None),
        ("x\\escape.csv", b"x\n1\n", None),
        ("link.csv", b"elsewhere", stat.S_IFLNK | 0o777),
        ("nested.zip", b"PK", None),
        ("bomb.csv", b"x" * 1024 * 1024, None),
    ],
)
def test_archive_security(parser, tmp_path, name, body, mode):
    archive(tmp_path / "zip", name, body, mode)
    with pytest.raises(ValueError):
        parser(tmp_path / "zip", tmp_path / "version.duckdb", "zip")
    assert not (tmp_path.parent / "escape.csv").exists()


def test_single_member_zip_has_independent_checksum(parser, tmp_path):
    archive(tmp_path / "zip", "data.csv", b"value\n1\n2\n")
    result = parser(tmp_path / "zip", tmp_path / "version.duckdb", "zip")
    assert result["rows"] == 2 and result["archive"]["member"] == "data.csv"
    assert len(result["archive"]["expanded_sha256"]) == 64


@pytest.mark.skipif(os.name == "nt", reason="Isolated ingestion runtime is Linux")
@pytest.mark.asyncio
async def test_real_isolated_parser_and_work_cleanup(tmp_path, monkeypatch, parser):
    from open_notebook.databridge.ingestion.runtime import parse, workspace

    monkeypatch.setenv("DATABRIDGE_DATA_ROOT", str(tmp_path))
    async with workspace() as folder:
        (folder / "input").write_text("value\n1\n2\n")
        result = await parse(folder / "input", folder / "db.duckdb", "csv")
        assert result["rows"] == 2
    assert not folder.exists()


@pytest.mark.asyncio
async def test_redirect_dns_rebinding_rejected(monkeypatch, tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "/next.csv"}, stream=Bytes(b""))

    transport(monkeypatch, handler)
    answers = iter([["93.184.216.34"], ["127.0.0.1"]])

    async def resolve(host):
        return next(answers)

    monkeypatch.setattr(download, "resolve", resolve)
    with pytest.raises(download.AcquisitionError, match="DOWNLOAD_BLOCKED"):
        await download.fetch("https://data.transportation.gov/a.csv", tmp_path / "data")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_catalog_key_cannot_follow_cross_host_redirect(monkeypatch, tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            302,
            headers={"location": "https://data.transportation.gov/file.csv"},
            stream=Bytes(b""),
        )

    transport(monkeypatch, handler)
    with pytest.raises(download.AcquisitionError, match="DOWNLOAD_BLOCKED"):
        await download.fetch(
            "https://api.gsa.gov/search",
            tmp_path / "data",
            allowed={"api.gsa.gov", "data.transportation.gov"},
            api_key="test-key",
        )
    assert len(calls) == 1 and calls[0].headers["x-api-key"] == "test-key"


@pytest.mark.parametrize("rights", ["public", ["public"], None, ""])
def test_official_dot_public_rights_declaration(rights):
    result = catalog.classify(
        {"accessLevel": "public", "rights": rights},
        {
            "mediaType": "text/csv",
            "downloadURL": "https://data.transportation.gov/api/v3/views/wwdp-t4re/export.csv?accessType=DOWNLOAD",
        },
    )
    assert result["status"] == "checking"


@pytest.mark.asyncio
async def test_catalog_requires_personal_key_not_demo(monkeypatch):
    monkeypatch.setenv("DATAGOV_API_KEY", "DEMO_KEY")
    monkeypatch.delenv("DATAGOV_API_KEY_FILE", raising=False)
    from open_notebook.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError):
        await catalog.request("search")


@pytest.mark.asyncio
async def test_cached_catalog_cursor_normalizes_missing_null(monkeypatch):
    monkeypatch.setattr(catalog, "enabled", lambda: None)

    async def query(*args):
        return [{"payload": {"results": []}}]

    monkeypatch.setattr(catalog, "repo_query", query)
    result = await catalog.search("", "", "", "cursor", 10)
    assert result["after"] is None


@pytest.mark.skipif(os.name == "nt", reason="Linux parent-death protection")
@pytest.mark.asyncio
async def test_native_child_dies_when_only_its_parent_is_killed():
    import asyncio
    import signal
    import sys
    from pathlib import Path

    if sys.platform != "linux":
        pytest.skip("Linux parent-death protection")
    child = "from open_notebook.databridge.ingestion.parser import guard_parent; import time; guard_parent(); print('guarded', flush=True); time.sleep(60)"
    launcher = (
        "import subprocess, os, sys, time; "
        "env = dict(os.environ, DATABRIDGE_PARSER_PARENT_PID=str(os.getpid())); "
        f"child = subprocess.Popen([sys.executable, '-c', {child!r}], env=env, stdout=subprocess.PIPE); "
        "print(str(child.pid) + ':' + child.stdout.readline().decode().strip(), flush=True); time.sleep(60)"
    )
    parent = await asyncio.create_subprocess_exec(
        sys.executable, "-c", launcher, stdout=asyncio.subprocess.PIPE
    )
    child_pid = None
    try:
        assert parent.stdout is not None
        line = (await asyncio.wait_for(parent.stdout.readline(), 5)).decode().strip()
        pid, ready = line.split(":")
        child_pid = int(pid)
        assert ready == "guarded"
        parent.kill()
        await parent.wait()
        status = Path(f"/proc/{child_pid}/stat")
        for _ in range(30):
            if not status.exists() or status.read_text().split()[2] == "Z":
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("Native parser outlived its parent")
    finally:
        if parent.returncode is None:
            parent.kill()
            await parent.wait()
        if child_pid:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
