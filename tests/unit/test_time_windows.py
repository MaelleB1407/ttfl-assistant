"""Tests for time window utilities."""
from __future__ import annotations

import sys
import types
from datetime import datetime
from zoneinfo import ZoneInfo

psycopg_stub = types.ModuleType("psycopg")
psycopg_stub.Connection = object  # type: ignore[attr-defined]
psycopg_stub.Cursor = object  # type: ignore[attr-defined]
psycopg_stub.connect = lambda *args, **kwargs: None  # type: ignore[attr-defined]
sys.modules.setdefault("psycopg", psycopg_stub)
sys.modules.setdefault("pandas", types.ModuleType("pandas"))

from common.time_windows import PARIS, paris_today, paris_window


def test_paris_window_default_hours() -> None:
    """Ensure the default window spans 18:00→08:00 Paris converted to UTC."""
    start_utc, end_utc = paris_window("2024-03-15")

    expected_start = datetime(2024, 3, 15, 18, 0, tzinfo=PARIS).astimezone(ZoneInfo("UTC"))
    expected_end = datetime(2024, 3, 16, 8, 0, tzinfo=PARIS).astimezone(ZoneInfo("UTC"))

    assert start_utc == expected_start
    assert end_utc == expected_end


def test_paris_window_custom_hours() -> None:
    """The helper accepts custom start/end hours."""
    start_utc, end_utc = paris_window("2024-12-10", start_h=16, end_h_next=6)

    expected_start = datetime(2024, 12, 10, 16, 0, tzinfo=PARIS).astimezone(ZoneInfo("UTC"))
    expected_end = datetime(2024, 12, 11, 6, 0, tzinfo=PARIS).astimezone(ZoneInfo("UTC"))

    assert start_utc == expected_start
    assert end_utc == expected_end


def test_paris_today_format() -> None:
    """Result should be parseable using the default YYYY-MM-DD format."""
    today_str = paris_today()
    assert len(today_str) == 10
    datetime.strptime(today_str, "%Y-%m-%d")
