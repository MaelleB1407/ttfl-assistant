"""Utilities to deal with the Paris 18h→8h window shared everywhere."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
_UTC = ZoneInfo("UTC")


def paris_window(
    date_str: str, start_h: int = 18, end_h_next: int = 8
) -> tuple[datetime, datetime]:
    """Return the UTC datetimes covering the Paris window for a given date."""
    base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=PARIS)
    start_paris = base.replace(hour=start_h, minute=0, second=0, microsecond=0)
    end_paris = (base + timedelta(days=1)).replace(
        hour=end_h_next, minute=0, second=0, microsecond=0
    )
    return start_paris.astimezone(_UTC), end_paris.astimezone(_UTC)


def paris_today(fmt: str = "%Y-%m-%d") -> str:
    """Return today's date in Paris timezone with the given strftime format."""
    return datetime.now(PARIS).strftime(fmt)
