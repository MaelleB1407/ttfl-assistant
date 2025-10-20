"""Database connection helpers shared across components."""
from __future__ import annotations

import os
import psycopg

DB_DSN = os.getenv("DB_DSN", "postgresql://injuries:injuries@postgres:5432/injuries")


def db_conn():
    """Return a new connection to the injuries database."""
    return psycopg.connect(DB_DSN)
