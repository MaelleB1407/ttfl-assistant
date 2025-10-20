"""Database connection helpers shared across components."""
from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg import Connection

DB_DSN: str = os.getenv("DB_DSN", "postgresql://injuries:injuries@postgres:5432/injuries")


def db_conn() -> Connection[Any]:
    """Return a new connection to the injuries database."""
    return psycopg.connect(DB_DSN)
