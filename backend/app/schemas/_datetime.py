"""Shared response serialization type for timestamps.

Server timestamps are stored naive-UTC (SQLite drops tzinfo on the way
in and returns naive datetimes). Response models serialize them with an
explicit ``Z`` so browser ``new Date(...)`` parses UTC instead of
silently treating the string as local time.
"""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


# when_used='json': serialize only on the response path (model_dump(mode=
# "json")) — python-mode model_dump must keep handing datetimes to the ORM.
UTCDateTime = Annotated[
    datetime, PlainSerializer(_utc_iso, return_type=str, when_used="json")
]
