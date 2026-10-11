"""User-facing calendar dates in the configured service timezone."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def service_today(now_utc: datetime | None = None, *, timezone_name: str | None = None):
    if timezone_name is None:
        from app.core.config import get_settings
        timezone_name = get_settings().service_timezone
    current = now_utc or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(ZoneInfo(timezone_name)).date()
