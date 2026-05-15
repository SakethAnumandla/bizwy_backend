from datetime import datetime
from typing import Optional

from fastapi import HTTPException

DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
)


def parse_bill_date(value: str) -> datetime:
    """Parse common date strings (e.g. 15/05/2026, 2026-05-15, ISO)."""
    if not value or not str(value).strip():
        raise HTTPException(status_code=400, detail="bill_date is required")

    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue

    raise HTTPException(
        status_code=400,
        detail=(
            "Invalid bill_date. Use formats like 15/05/2026, 15-05-2026, "
            "2026-05-15, or ISO datetime."
        ),
    )
