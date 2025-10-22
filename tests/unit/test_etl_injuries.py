"""Tests for ESPN injuries ETL helpers."""
from __future__ import annotations

import sys
import types

sys.modules.setdefault("pandas", types.ModuleType("pandas"))

psycopg_stub = types.ModuleType("psycopg")
psycopg_stub.Connection = object  # type: ignore[attr-defined]
psycopg_stub.Cursor = object  # type: ignore[attr-defined]
psycopg_stub.connect = lambda *args, **kwargs: None  # type: ignore[attr-defined]
sys.modules.setdefault("psycopg", psycopg_stub)

from etl.etl_injuries import _normalize_team_name


def test_normalize_team_name_variants() -> None:
    assert _normalize_team_name("LA Clippers") == "Los Angeles Clippers"
    assert _normalize_team_name("Phoenix Suns Suns") == "Phoenix Suns"
    assert _normalize_team_name("Boston Celtics") == "Boston Celtics"
