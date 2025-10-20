"""Shared helpers for Dash app, ETL scripts and email report."""

from .time_windows import PARIS, paris_window, paris_today
from .db import db_conn, DB_DSN
from .injuries import load_injuries_for_window

__all__ = [
    "PARIS",
    "paris_window",
    "paris_today",
    "db_conn",
    "DB_DSN",
    "load_injuries_for_window",
]
