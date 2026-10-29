"""Isolated, resource-limited parser. Takes local trusted paths, never URLs/SQL."""

import csv
import hashlib
import json
import math
import os
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

MAX_EXPANDED = 64 * 1024 * 1024
MAX_ROWS = 250000
MAX_COLUMNS = 100


def identifier(original: str, index: int) -> str:
    # Stable and unambiguous even when headers collide after normalization.
    name = re.sub("[^a-z0-9_]", "_", original.lower()).strip("_")[:48] or "column"
    return f"c_{index + 1}_{name}"


def unpack(path: Path) -> tuple[Path, str, dict]:
    with zipfile.ZipFile(path) as archive:
        files = archive.infolist()
        if not 1 <= len(files) <= 10:
            raise ValueError("ARCHIVE_LIMIT")
        expanded = 0
        candidates = []
        for info in files:
            name = info.filename
            parts = PurePosixPath(name)
            mode = info.external_attr >> 16
            if (
                "\\" in name
                or ":" in name
                or parts.is_absolute()
                or ".." in parts.parts
                or stat.S_ISLNK(mode)
                or info.flag_bits & 1
            ):
                raise ValueError("UNSAFE_ARCHIVE")
            if info.is_dir():
                continue
            if stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
                raise ValueError("UNSAFE_ARCHIVE")
            expanded += info.file_size
            if (
                expanded > MAX_EXPANDED
                or info.file_size > max(1, info.compress_size) * 100
            ):
                raise ValueError("ARCHIVE_LIMIT")
            suffix = parts.suffix.lower().lstrip(".")
            if suffix not in {"csv", "json", "jsonl", "parquet"}:
                raise ValueError("ARCHIVE_ADAPTER_REQUIRED")
            candidates.append((info, suffix))
        if len(candidates) != 1:
            raise ValueError("ARCHIVE_SELECTION_REQUIRED")
        info, kind = candidates[0]
        target = path.parent / "expanded"
        count, sha = 0, hashlib.sha256()
        with archive.open(info) as source, target.open("xb") as output:
            while chunk := source.read(65536):
                count += len(chunk)
                if count > MAX_EXPANDED or count > info.file_size:
                    raise ValueError("ARCHIVE_LIMIT")
                sha.update(chunk)
                output.write(chunk)
        if count != info.file_size:
            raise ValueError("INCOMPLETE_ARCHIVE")
        return (
            target,
            kind,
            {
                "member": info.filename,
                "expanded_bytes": count,
                "expanded_sha256": sha.hexdigest(),
            },
        )


def unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def stage(source: Path, database: Path, kind: str) -> dict:
    import duckdb

    archive = None
    if kind == "zip":
        source, kind, archive = unpack(source)
    with source.open("rb") as stream:
        prefix = stream.read(1024)
    if prefix.lstrip().startswith(b"<") or b"\x00" in prefix and kind != "parquet":
        raise ValueError("FORMAT_MISMATCH")
    # Strict structure validation before native parsers; no silently ignored rows.
    if kind == "csv":
        csv.field_size_limit(1024 * 1024)
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            originals = next(reader)
            if (
                not 1 <= len(originals) <= MAX_COLUMNS
                or any(not h or len(h) > 256 for h in originals)
                or len(set(originals)) != len(originals)
            ):
                raise ValueError("SCHEMA_LIMIT")
            count = 0
            for row in reader:
                count += 1
                if len(row) != len(originals) or count > MAX_ROWS:
                    raise ValueError("ROW_OR_STRUCTURE_LIMIT")
    elif kind in {"json", "jsonl"}:
        text = source.read_text(encoding="utf-8-sig")
        # Limit nesting before json decoding to bound malicious recursion.
        depth, quoted, escaped = 0, False, False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > 4:
                    raise ValueError("NESTED_JSON_UNSUPPORTED")
            elif char in "]}":
                depth -= 1
        rows = (
            json.loads(text, object_pairs_hook=unique_object)
            if kind == "json"
            else [
                json.loads(line, object_pairs_hook=unique_object)
                for line in text.splitlines()
                if line.strip()
            ]
        )
        if (
            not isinstance(rows, list)
            or not 1 <= len(rows) <= MAX_ROWS
            or any(not isinstance(row, dict) for row in rows)
        ):
            raise ValueError("JSON_RECORDS_REQUIRED")
        originals = list(rows[0])
        if not 1 <= len(originals) <= MAX_COLUMNS or any(
            not n or len(n) > 256 for n in originals
        ):
            raise ValueError("SCHEMA_LIMIT")
        for row in rows:
            if set(row) != set(originals) or any(
                isinstance(v, (dict, list))
                or isinstance(v, float)
                and not math.isfinite(v)
                for v in row.values()
            ):
                raise ValueError("JSON_STRUCTURE_UNSUPPORTED")
        # Convert scalars to CSV for the same loss-aware inference as CSV.
        converted = source.parent / "records.csv"
        with converted.open("x", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(originals)
            writer.writerows([[row[k] for k in originals] for row in rows])
        source, kind = converted, "csv"
        del rows, text
    elif kind == "parquet":
        with source.open("rb") as stream:
            stream.seek(-4, 2)
            if not prefix.startswith(b"PAR1") or stream.read() != b"PAR1":
                raise ValueError("FORMAT_MISMATCH")
    else:
        raise ValueError("ADAPTER_REQUIRED")
    with duckdb.connect(
        str(database),
        config={
            "memory_limit": "256MB",
            "threads": "1",
            "max_temp_directory_size": "128MB",
            "temp_directory": str(source.parent / "spill"),
        },
    ) as db:
        db.execute("SET allowed_paths = ?", [[str(source)]])
        db.execute(
            "SET autoinstall_known_extensions=false; SET autoload_known_extensions=false; SET enable_external_access=false; SET lock_configuration=true"
        )
        if kind == "csv":
            db.execute(
                "CREATE TEMP TABLE raw AS SELECT * FROM read_csv(?, header=true, all_varchar=true, delim=',', strict_mode=true, max_line_size=1048576)",
                [str(source)],
            )
        else:
            db.execute(
                "CREATE TEMP TABLE raw AS SELECT * FROM read_parquet(?) LIMIT 250001",
                [str(source)],
            )
        columns = db.execute("DESCRIBE raw").fetchall()
        if not 1 <= len(columns) <= MAX_COLUMNS:
            raise ValueError("SCHEMA_LIMIT")
        counted = db.execute("SELECT COUNT(*) FROM raw").fetchone()
        assert counted is not None
        count = counted[0]
        if not 1 <= count <= MAX_ROWS:
            raise ValueError("ROW_LIMIT")
        mapping, projections = [], []
        for i, (name, dtype, *_) in enumerate(columns):
            if len(name) > 256 or not re.fullmatch(
                r"(?:VARCHAR|BOOLEAN|(?:U?)(?:TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|DECIMAL\(\d+,\d+\)|DATE|TIMESTAMP(?:_\w+)?)",
                dtype,
            ):
                raise ValueError("COLUMN_TYPE_UNSUPPORTED")
            original_name = originals[i] if kind == "csv" else name
            safe = identifier(original_name, i)
            quoted = '"' + name.replace('"', '""') + '"'
            expression = quoted
            # Preserve all identifiers, including leading zeros, as text.
            identity = bool(
                re.search(
                    r"(^|[^a-z])(id|fips|geoid|zip|code)([^a-z]|$)",
                    original_name.lower(),
                )
            )
            if dtype == "VARCHAR" and not identity:
                numeric = db.execute(
                    f"SELECT count(*) FILTER (WHERE {quoted} IS NOT NULL), count(*) FILTER (WHERE {quoted} IS NOT NULL AND (TRY_CAST({quoted} AS BIGINT) IS NULL OR NOT regexp_full_match({quoted}, '-?(0|[1-9][0-9]*)'))) FROM raw"
                ).fetchone()
                assert numeric is not None
                if numeric[0] and numeric[1] == 0:
                    expression, dtype = f"CAST({quoted} AS BIGINT)", "BIGINT"
                else:
                    decimal = db.execute(
                        f"SELECT count(*) FILTER (WHERE {quoted} IS NOT NULL AND (NOT regexp_full_match({quoted}, '-?(0|[1-9][0-9]*)\\.[0-9]{{1,6}}') OR TRY_CAST({quoted} AS DECIMAL(24,6)) IS NULL)) FROM raw"
                    ).fetchone()
                    assert decimal is not None
                    if numeric[0] and decimal[0] == 0:
                        expression, dtype = (
                            f"CAST({quoted} AS DECIMAL(24,6))",
                            "DECIMAL(24,6)",
                        )
            if identity:
                expression, dtype = f"CAST({quoted} AS VARCHAR)", "VARCHAR"
            projections.append(f'{expression} AS "{safe}"')
            mapping.append({"original": original_name, "column": safe, "type": dtype})
        db.execute("CREATE TABLE data AS SELECT " + ",".join(projections) + " FROM raw")
        profile = []
        for item in mapping:
            col = '"' + item["column"] + '"'
            values = db.execute(
                f"SELECT count(*) FILTER (WHERE {col} IS NULL), CAST(min({col}) AS VARCHAR), CAST(max({col}) AS VARCHAR) FROM data"
            ).fetchone()
            assert values is not None
            nulls, minimum, maximum = values
            profile.append(
                {
                    **item,
                    "nulls": nulls,
                    "min": str(minimum)[:256] if minimum is not None else None,
                    "max": str(maximum)[:256] if maximum is not None else None,
                }
            )
        sample = db.execute("SELECT * FROM data LIMIT 5").fetchall()
        preview = [
            {
                mapping[i]["column"]: str(v)[:256] if v is not None else None
                for i, v in enumerate(row)
            }
            for row in sample
        ]
        db.execute("CHECKPOINT")
    if database.stat().st_size > 256 * 1024**2:
        raise ValueError("DATABASE_SIZE_LIMIT")
    return {
        "table": "data",
        "rows": count,
        "columns": mapping,
        "profile": profile,
        "preview": preview,
        "archive": archive,
        "warnings": [
            "Identifier columns remain text; numeric inference is conservative. Review publisher units and geography before comparison."
        ],
    }


def guard_parent():
    """A worker-only crash must not leave a native writer behind."""
    if sys.platform != "linux":
        raise ValueError("LINUX_RUNTIME_REQUIRED")
    import ctypes
    import signal

    expected = int(os.environ["DATABRIDGE_PARSER_PARENT_PID"])
    # PR_SET_PDEATHSIG. Check ppid after registration to close the startup race.
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise ValueError("PARENT_GUARD_UNAVAILABLE")
    if os.getppid() != expected:
        raise ValueError("PARENT_UNAVAILABLE")


def main():
    if sys.platform != "linux":
        raise ValueError("LINUX_RUNTIME_REQUIRED")
    guard_parent()
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    try:
        result = stage(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
        print(json.dumps(result, allow_nan=False))
    except Exception as error:
        code = (
            str(error)
            if isinstance(error, ValueError) and re.fullmatch("[A-Z_]+", str(error))
            else "INVALID_OR_UNSUPPORTED_DATA"
        )
        print(json.dumps({"error": code}))
        sys.exit(1)


if __name__ == "__main__":
    main()
