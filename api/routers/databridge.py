"""Password-protected, read-only gateway usage. No dynamic endpoint selection."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from open_notebook.databridge.usage import UsagePage, read_usage
from open_notebook.exceptions import InvalidInputError

router = APIRouter()


@router.get("/databridge/usage", response_model=UsagePage)
async def usage(
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = Query(1, ge=1, le=100000),
):
    end = end or datetime.now(timezone.utc)
    start = start or end - timedelta(days=7)
    if start.tzinfo is None or end.tzinfo is None or start > end:
        raise InvalidInputError("Use ordered, timezone-aware usage dates")
    return await read_usage(
        start.astimezone(timezone.utc), end.astimezone(timezone.utc), page
    )
