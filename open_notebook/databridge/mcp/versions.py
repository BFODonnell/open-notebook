"""Publication interface for closed staging files; no ingestion or URL access."""

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from open_notebook.databridge.mcp.policy import IDENTIFIER


def version_key(value: str) -> str:
    return str(UUID(value))


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def published_manifest(root: Path, version: str) -> dict:
    version = version_key(version)
    manifest_file = root / "published" / f"{version}.json"
    database = root / "published" / f"{version}.duckdb"
    if manifest_file.is_symlink() or database.is_symlink():
        raise ValueError("Dataset symlinks are forbidden")
    manifest = json.loads(manifest_file.read_text())
    if manifest["version_id"] != version or file_hash(database) != manifest["sha256"]:
        raise ValueError("Dataset version integrity check failed")
    return manifest


def publish(root: Path, staging_id: str, dataset_id: str) -> dict:
    # The deployed runtime is Linux. An OS lock serializes quotas/publication
    # across API processes and releases automatically after a crash.
    if sys.platform == "win32":
        raise ValueError("Publish through the Linux DataBridge runtime")
    import fcntl

    root.mkdir(parents=True, exist_ok=True)
    with (root / ".publication.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _publish(root, staging_id, dataset_id)


def _publish(root: Path, staging_id: str, dataset_id: str) -> dict:
    import duckdb

    version = version_key(staging_id)
    dataset = version_key(dataset_id)
    published = root / "published"
    published.mkdir(parents=True, exist_ok=True)
    if (published / f"{version}.json").exists():
        manifest = published_manifest(root, version)
        if manifest["dataset_id"] != dataset:
            raise ValueError("Version already belongs to another dataset")
        return manifest
    source = root / "staging" / f"{version}.duckdb"
    if (
        source.is_symlink()
        or not source.is_file()
        or Path(str(source) + ".wal").exists()
    ):
        raise ValueError("A closed, checkpointed staging file is required")
    if not 0 < source.stat().st_size <= 256 * 1024 * 1024:
        raise ValueError("Dataset exceeds 256 MiB publication limit")
    existing = list(published.glob("*.duckdb*"))
    if (
        len(existing) >= 50
        or sum(p.stat().st_size for p in existing) + source.stat().st_size > 2 * 1024**3
    ):
        raise ValueError("Publication storage quota exceeded")
    # A live writer is rejected by DuckDB's file lock. No file is overwritten.
    with duckdb.connect(
        str(source),
        read_only=True,
        config={
            "enable_external_access": "false",
            "memory_limit": "256MB",
            "threads": "1",
        },
    ) as db:
        rows = db.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema='main' ORDER BY table_name, ordinal_position"
        ).fetchall()
        views = db.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_type != 'BASE TABLE'"
        ).fetchone()
        if views and views[0]:
            raise ValueError("Published versions must contain base tables only")
        # Retain the source's read lock while copying so a different writer
        # cannot change the file between schema validation and publication.
        temporary_db = published / f"{version}.duckdb.pending"
        with source.open("rb") as src, temporary_db.open("xb") as dst:
            import shutil

            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
    tables: dict[str, list[str]] = {}
    for table, column, _ in rows:
        if not IDENTIFIER.fullmatch(table) or not IDENTIFIER.fullmatch(column):
            raise ValueError("Unsupported table or column identifier")
        tables.setdefault(table, []).append(column)
    if not tables or len(tables) > 30 or any(len(c) > 100 for c in tables.values()):
        raise ValueError("Dataset schema exceeds publication limits")
    target = published / f"{version}.duckdb"
    # No file becomes discoverable until the final manifest exists. Neither
    # version data nor manifest can replace an existing path.
    os.link(temporary_db, target)
    temporary_db.unlink()
    target.chmod(0o444)
    manifest = {
        "version_id": version,
        "dataset_id": dataset,
        "sha256": file_hash(target),
        "tables": tables,
        "schema": [list(row) for row in rows],
        "schema_sha256": hashlib.sha256(
            json.dumps(rows, separators=(",", ":")).encode()
        ).hexdigest(),
        "bytes": target.stat().st_size,
    }
    temporary = published / f"{version}.json.pending"
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream)
        stream.flush()
        os.fsync(stream.fileno())
    # Link, not replace: duplicate/concurrent publication can never overwrite.
    os.link(temporary, published / f"{version}.json")
    temporary.unlink()
    directory = os.open(published, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return manifest
