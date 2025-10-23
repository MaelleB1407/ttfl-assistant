"""Database connection helpers shared across components."""
from __future__ import annotations

import os
import psycopg

DB_DSN = os.getenv("DB_DSN", "postgresql://ttfl:ttfl@postgres:5432/ttfl_database")


def db_conn():
    """Return a new connection to the ttfl database."""
    return psycopg.connect(DB_DSN)
