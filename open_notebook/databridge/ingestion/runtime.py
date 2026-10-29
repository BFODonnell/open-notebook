"""Bounded local work area shared by API preview and the existing worker."""

import asyncio
import json
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from open_notebook.databridge.ingestion.download import AcquisitionError


def root() -> Path:
    return Path(os.getenv("DATABRIDGE_DATA_ROOT", "data/databridge"))


@asynccontextmanager
async def workspace():
    if sys.platform == "win32":
        raise AcquisitionError("LINUX_RUNTIME_REQUIRED")
    import fcntl

    base = root() / "work"
    base.mkdir(parents=True, exist_ok=True)
    # One transfer/parse at a time across API/worker processes. Waiting holds no
    # downloaded file; crashed processes release this OS lock automatically.
    with (base / ".lock").open("a") as lock:
        try:
            async with asyncio.timeout(120):
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        await asyncio.sleep(0.2)
        except TimeoutError:
            raise AcquisitionError("IMPORT_BUSY", True) from None
        # Only our UUID-named work folders; never follow a symlink or touch
        # staging/published files. This also reconciles interrupted transfers.
        for old in base.iterdir():
            if old.is_dir() and not old.is_symlink():
                from uuid import UUID

                try:
                    UUID(old.name)
                except ValueError:
                    continue
                if old.resolve().parent == base.resolve():
                    await asyncio.to_thread(shutil.rmtree, old)
        folder = base / str(uuid4())
        folder.mkdir(mode=0o700)
        try:
            yield folder
        finally:
            await asyncio.to_thread(shutil.rmtree, folder, True)
            fcntl.flock(lock, fcntl.LOCK_UN)


async def parse(source: Path, database: Path, adapter: str) -> dict:
    # No application secrets, proxy variables, or caller-provided command/SQL.
    env = {
        "PATH": os.defpath,
        "HOME": str(source.parent),
        "PYTHONPATH": str(Path(__file__).resolve().parents[3]),
        "OPENBLAS_NUM_THREADS": "1",
        "MALLOC_ARENA_MAX": "2",
        "DATABRIDGE_PARSER_PARENT_PID": str(os.getpid()),
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "open_notebook.databridge.ingestion.parser",
        str(source),
        str(database),
        adapter,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(60):
            output, _ = await process.communicate()
        if len(output) > 262144:
            raise AcquisitionError("PROFILE_LIMIT")
        result = json.loads(output)
        if process.returncode or "error" in result:
            raise AcquisitionError(result.get("error", "PARSE_FAILED"))
        return result
    except AcquisitionError:
        raise
    except (ValueError, TimeoutError):
        raise AcquisitionError("PARSE_FAILED") from None
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
